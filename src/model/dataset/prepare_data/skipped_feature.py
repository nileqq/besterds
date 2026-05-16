from src.model.get_data import GetData
import numpy as np
from ema_feature import EMAFeature

class SkippedFeature:
    def get_expected_place(contests: list, period=5, window_size=8, skip_first=5):
        """
        Returns the strongest place-surprise window.
        Higher value means the user had a short suspicious streak of unusually good ranks.
        """

        if window_size <= 0:
            raise ValueError("window_size must be > 0")

        ranks = [
            contest["rank"]
            for contest in contests
            if contest.get("rank", 0) > 0
        ]

        if len(ranks) <= 1:
            return 0.0

        log_ranks = np.log1p(np.array(ranks, dtype=float))
        expected_log_ranks = EMAFeature().calculate_ema(log_ranks, period=period)

        surprises = np.zeros(len(log_ranks))
        for i in range(1, len(log_ranks)):
            surprises[i] = max(0.0, expected_log_ranks[i - 1] - log_ranks[i])

        surprises = surprises[skip_first:]

        if len(surprises) == 0:
            return 0.0

        if len(surprises) < window_size:
            return float(np.sqrt(np.mean(surprises ** 2)))

        best_window_score = 0.0
        for start in range(len(surprises) - window_size + 1):
            window = surprises[start:start + window_size]
            window_score = float(np.sqrt(np.mean(window ** 2)))
            best_window_score = max(best_window_score, window_score)

        return best_window_score
    
    def extract_skipped_contests_features(client: GetData, contests: list) -> dict:
        """
        Counts rated contests and returns ratio: skipped / all
        """

        skipped_ones = client.get_skipped_count(contests=contests)

        return {
            "skipped_ratio": skipped_ones / len(contests),
            "skipped_contests_count": skipped_ones
        }
