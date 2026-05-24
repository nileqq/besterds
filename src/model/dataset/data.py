import sys
import time
from pathlib import Path

import pandas as pd

from src.model import get_data as gd
from src.model.dataset.prepare_data.ema_feature import EMAFeature
from src.model.dataset.prepare_data.place_feature import PlaceFeature
from src.model.dataset.prepare_data.skipped_feature import SkippedFeature

FEATURE_DIR = Path(__file__).with_suffix("")
if str(FEATURE_DIR) not in sys.path:
    sys.path.insert(0, str(FEATURE_DIR))

# Prepares data for .csv file
# Launch it using: python -m src.model.dataset.data command;

cheaters = [
    "--dark--", "-0.50", "777dimasik777", 
    "9kitsune", "9ovem", "9xcuze", "_hemlock_",
    "bhumi_20", "bibek_sah", "bromate04", "bricked_", "bro_gona_rock",
    "snb", "BVSAKETH", "zilinj", "ItzManu", "tooxpert", "Impredator810", 
    "woLx10", 
]

trusted = [
    "Goddless", "shvepsi_", "Aldk", "Away_in_the_heavens", "tourist",
    "varunkumar_cr7", "CODER__RAM", "kishan_455", "conqueror_of_timosh",
    "34z12000", "adarshsolanki2004", "Erik_piza", "hexp", "frostcat", "khba",
    "kuro_10206", "_procastinaRukii", "seeforty4040", "Jayadev_S_Gorakavi",
    "soullless", "chromate00", "cry", "nkamzabek", "lyjiang", "DuyMinh3005",
    "Christine-", "comed111", "Ekber_Ekber"
]


def _get_rating_row(client: gd.GetData, is_cheater: bool, period: int = 5) -> dict | None:
    try:
        contests = client.get_contest_list()

        if len(contests) < 3:
            raise ValueError("Not enough rated contests")

        rating_deltas = [
            contest["newRating"] - contest["oldRating"]
            for contest in contests
        ]

        return {
            "handle": client.handle,
            **EMAFeature().extract(rating_deltas, period=period),
            "max_place_surprise_window_rms": SkippedFeature.get_expected_place(
                contests,
                period=period,
                window_size=5,
            ),
            **PlaceFeature.get_rank_ratio_log_features(client, contests),
            **SkippedFeature.extract_skipped_contests_features(client, contests),
            "is_cheater": is_cheater,
        }
    except Exception as e:
        print(f"Error upon request {client.handle}: {e}")
        return None


def build_dataset_rows():
    dataset_rows = []

    for handle in cheaters:
        row = _get_rating_row(gd.GetData(handle), is_cheater=True)
        if row is not None:
            dataset_rows.append(row)
        time.sleep(2.1)

    for handle in trusted:
        row = _get_rating_row(gd.GetData(handle), is_cheater=False)
        if row is not None:
            dataset_rows.append(row)
        time.sleep(2.1)

    return dataset_rows


def main():
    df = pd.DataFrame(build_dataset_rows())
    df.to_csv("cheating_dataset.csv", index=False)

    print("Dataset loaded succesfully in 'cheating_dataset.csv'!")
    print(df.head(3))


if __name__ == "__main__":
    main()
