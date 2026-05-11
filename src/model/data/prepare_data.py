import pandas as pd
import time
from src.model import get_data as gd
import numpy as np

# Prepares data for .csv file
# Launch it using: python -m src.model.data.prepare_data command;

cheaters = [
    "--dark--", "-0.50", "777dimasik777", 
    "9kitsune", "9ovem", "9xcuze", "_hemlock_",
    "bhumi_20", "bibek_sah", "bromate04", "bricked_", "bro_gona_rock",
]

trusted = [
    "Goddless", "shvepsi_", "Aldk", "Away_in_the_heavens", "tourist",
    "varunkumar_cr7", "CODER__RAM", "kishan_455", "conqueror_of_timosh",
    "34z12000", "adarshsolanki2004", "Erik_piza", "hexp", "frostcat", "khba",
]

def calculate_ema(values, period=5):
    values = np.array(values, dtype=float)

    if len(values) == 0:
        return np.array([])

    alpha = 2 / (period + 1)

    result = np.zeros(len(values))
    result[0] = values[0]

    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    
    return result

def extract_ema_features(deltas, period=5, skip_first=5):
    arr = np.array(deltas, dtype=float)

    if len(arr) == 0:
        return {
            "contest_count": 0.0,
            "ema_last": 0.0,
            "ema_slope_last_5": 0.0,
            "positive_residual_rms": 0.0,
            "late_positive_residual_rms": 0.0,
            "late_max_positive_residual": 0.0,
        }

    ema = calculate_ema(arr, period=period)

    residuals = np.zeros(len(arr))
    residuals[0] = 0.0

    for i in range(1, len(arr)):
        residuals[i] = arr[i] - ema[i - 1]

    positive_residuals = residuals[residuals > 0]

    late_residuals = residuals[skip_first:]
    late_positive_residuals = late_residuals[late_residuals > 0]

    return {
        "contest_count": len(arr),
        "ema_last": float(ema[-1]),
        "ema_slope_last_5": float(ema[-1] - ema[-5]) if len(ema) >= 5 else float(ema[-1] - ema[0]),
        "positive_residual_rms": float(np.sqrt(np.mean(positive_residuals ** 2))) if len(positive_residuals) else 0.0,
        "late_positive_residual_rms": float(np.sqrt(np.mean(late_positive_residuals ** 2))) if len(late_positive_residuals) else 0.0,
        "late_max_positive_residual": float(np.max(late_positive_residuals)) if len(late_positive_residuals) else 0.0,
    }

def _get_rating_row(client: gd.GetData, is_cheater: bool, period: int = 5) -> dict:
    try:
        info_list = client.get_contest_list()

        if len(info_list) < 3:
            raise Exception("")

        rating = []
        ema = 0
        for i in range(len(info_list)):
            rating.append(info_list[i]['newRating'] - info_list[i]['oldRating'])

        features = extract_ema_features(rating, period=period)
        
        return {
            "handle": client.handle, 
            **features,
            "is_cheater": is_cheater
        }
    except Exception as e:
        print(f"Error upon request {client.handle}: {e}")
        return None

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

df = pd.DataFrame(dataset_rows)
df.to_csv("cheating_dataset.csv", index=False)

print("Dataset loaded succesfully in 'cheating_dataset.csv'!")
print(df.head(3))
