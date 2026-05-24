import math

import numpy as np

from src.model.get_data import GetData


class PlaceFeature:
    MIN_RATING_LIMIT = -500
    MAX_RATING_LIMIT = 6000
    RATING_RANGE_LEN = MAX_RATING_LIMIT - MIN_RATING_LIMIT
    ELO_OFFSET = RATING_RANGE_LEN
    RATING_OFFSET = -MIN_RATING_LIMIT
    DEFAULT_RATING = 1400
    ELO_WIN_PROB = np.array(
        [
            1 / (1 + math.pow(10, rating_diff / 400))
            for rating_diff in range(-RATING_RANGE_LEN, RATING_RANGE_LEN + 1)
        ],
        dtype=float,
    )
    _contest_seed_cache = {}

    @staticmethod
    def get_rank_ratio_log_features(
        client: GetData,
        contests: list,
        skip_first=5,
        max_contests=20,
        candidate_count=4,
    ) -> dict:
        """
        Returns the strongest recent rank overperformance:
        log(expected_rank_by_old_rating / actual_rank).
        """

        selected_contests = contests[skip_first:]

        if max_contests is not None:
            selected_contests = selected_contests[-max_contests:]

        selected_contests = PlaceFeature.pick_candidate_contests(
            selected_contests,
            candidate_count=candidate_count,
        )

        rank_ratio_logs = []
        for contest in selected_contests:
            rank_ratio_log = PlaceFeature.get_rank_ratio_log(client, contest)

            if rank_ratio_log is not None:
                rank_ratio_logs.append(max(0.0, rank_ratio_log))

        return {
            "max_rank_ratio_log": max(rank_ratio_logs, default=0.0),
        }

    @staticmethod
    def pick_candidate_contests(contests: list, candidate_count=4) -> list:
        if len(contests) <= candidate_count:
            return contests

        by_rank = sorted(
            contests,
            key=lambda contest: PlaceFeature.to_int(contest.get("rank"), default=10**9),
        )[:candidate_count]
        by_delta = sorted(
            contests,
            key=lambda contest: (
                PlaceFeature.to_int(contest.get("newRating"), default=0)
                - PlaceFeature.to_int(contest.get("oldRating"), default=0)
            ),
            reverse=True,
        )[:candidate_count]

        candidates = {}
        for contest in [*by_rank, *by_delta]:
            contest_id = contest.get("contestId")
            if contest_id is not None:
                candidates[int(contest_id)] = contest

        return list(candidates.values())

    @staticmethod
    def to_int(value, default=None):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_rank_ratio_log(client: GetData, contest: dict) -> float | None:
        contest_id = contest.get("contestId")
        actual_rank = PlaceFeature.to_int(contest.get("rank"))
        old_rating = PlaceFeature.to_int(contest.get("oldRating"))

        if contest_id is None or actual_rank is None or old_rating is None:
            return None

        if actual_rank <= 0:
            return None

        try:
            rating_changes = client.get_contest_rating_changes(contest_id)
        except Exception:
            return None

        handle = client.handle.strip().lower()
        own_change = next(
            (
                change
                for change in rating_changes
                if str(change.get("handle", "")).strip().lower() == handle
            ),
            None,
        )

        if own_change is not None:
            old_rating = PlaceFeature.to_int(own_change.get("oldRating"), old_rating)
            actual_rank = PlaceFeature.to_int(own_change.get("rank"), actual_rank)

        expected_rank = PlaceFeature.get_expected_rank(
            contest_id,
            rating_changes,
            old_rating,
        )

        if expected_rank <= 0 or actual_rank <= 0:
            return None

        return float(math.log(expected_rank / actual_rank))

    @staticmethod
    def get_expected_rank(contest_id, rating_changes: list, old_rating: int) -> float:
        seed = PlaceFeature.get_contest_seed(contest_id, rating_changes)
        rating = PlaceFeature.clamp_rating(old_rating)
        seed_index = rating + PlaceFeature.ELO_OFFSET + PlaceFeature.RATING_OFFSET

        # The histogram includes the target contestant, so remove the self-vs-self 0.5 term.
        return float(seed[seed_index] - PlaceFeature.ELO_WIN_PROB[PlaceFeature.ELO_OFFSET])

    @staticmethod
    def get_contest_seed(contest_id, rating_changes: list):
        contest_id = int(contest_id)

        if contest_id in PlaceFeature._contest_seed_cache:
            return PlaceFeature._contest_seed_cache[contest_id]

        counts = np.zeros(PlaceFeature.RATING_RANGE_LEN, dtype=float)
        for change in rating_changes:
            rating = PlaceFeature.normalize_rating(change.get("oldRating"))
            counts[rating + PlaceFeature.RATING_OFFSET] += 1

        seed = PlaceFeature.fft_convolve(PlaceFeature.ELO_WIN_PROB, counts)
        seed += 1.0
        PlaceFeature._contest_seed_cache[contest_id] = seed
        return seed

    @staticmethod
    def normalize_rating(value):
        rating = PlaceFeature.to_int(value, default=PlaceFeature.DEFAULT_RATING)

        if rating == 0:
            rating = PlaceFeature.DEFAULT_RATING

        return PlaceFeature.clamp_rating(rating)

    @staticmethod
    def clamp_rating(rating):
        rating = PlaceFeature.to_int(rating, default=PlaceFeature.DEFAULT_RATING)
        return min(
            max(rating, PlaceFeature.MIN_RATING_LIMIT),
            PlaceFeature.MAX_RATING_LIMIT - 1,
        )

    @staticmethod
    def fft_convolve(a, b):
        result_len = len(a) + len(b) - 1
        fft_len = 1 << (result_len - 1).bit_length()
        result = np.fft.irfft(
            np.fft.rfft(a, fft_len) * np.fft.rfft(b, fft_len),
            fft_len,
        )
        return result[:result_len]
