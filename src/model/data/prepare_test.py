import pandas as pd
import time
from src.model import get_data as gd
import numpy as np
import argparse
import contextlib
import io

cheaters = [
    "born_to_play", "bow_before_your_king", "bricked_", "bro_gona_rock",
    "bromate04", "bshah", "chatgpt_llm", "chiffin", "deeppaws",
    "12345vai", "2740", "504timeout", "darkhome", "darkstreak", 
    "darkpast", "darshan23100", "gagansharma001"
]

trusted = [
    "KluydQ", "Benq", "tourist", "ecnerwala", "jiangly",
    "soullless", "feev1x", "dog", "WansurMyKing667", "nileq",
    "autaons"
]

FEATURE_COLS = [
    "contest_count",
    "ema_last",
    "ema_slope_last_5",
    "positive_residual_rms",
    "late_positive_residual_rms",
    "late_max_positive_residual",
    "skipped_ratio",
    "skipped_contests_count",
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


def extract_skipped_contests_features(client: gd.GetData, contests: list) -> dict:
    skipped_ones = client.get_skipped_count()

    return {
        "skipped_ratio": skipped_ones / len(contests),
        "skipped_contests_count": skipped_ones,
    }


def get_rating_features(handle: str, period: int = 5):
    client = gd.GetData(handle)
    info_list = client.get_contest_list()

    if len(info_list) < 3:
        raise ValueError("Not enough rated contests to make prediction")

    rating = []
    for contest in info_list:
        rating.append(contest["newRating"] - contest["oldRating"])

    return {
        "handle": handle,
        **extract_ema_features(rating, period=period),
        **extract_skipped_contests_features(client, info_list),
    }


def load_model():
    with contextlib.redirect_stdout(io.StringIO()):
        from src.model import model as model_module

    return model_module.x


def predict_row(model, row):
    x = [row[col] for col in FEATURE_COLS]
    score = model.predict_score(x)
    prediction = model.predict(x)

    return score, prediction


def predict_handle(handle: str):
    model = load_model()
    row = get_rating_features(handle)
    score, prediction = predict_row(model, row)

    return row, score, prediction


def build_test_rows():
    rows = []

    for handle in cheaters:
        try:
            rows.append({**get_rating_features(handle), "is_cheater": 1})
        except Exception as e:
            print(f"Error upon request {handle}: {e}")
        time.sleep(2.1)

    for handle in trusted:
        try:
            rows.append({**get_rating_features(handle), "is_cheater": 0})
        except Exception as e:
            print(f"Error upon request {handle}: {e}")
        time.sleep(2.1)

    return rows


def evaluate_test_rows():
    model = load_model()
    rows = build_test_rows()
    results = []

    for row in rows:
        score, prediction = predict_row(model, row)
        results.append({
            "handle": row["handle"],
            "expected": row["is_cheater"],
            "prediction": prediction,
            "score": score,
            "correct": int(prediction == row["is_cheater"]),
        })

    if not results:
        print("No test rows collected.")
        return

    df = pd.DataFrame(results)
    accuracy = df["correct"].mean()

    print(df.to_string(index=False))
    print(f"accuracy: {accuracy:.4f}")


def main():
    parser = argparse.ArgumentParser(description="Predict whether Codeforces handle looks like a cheater.")
    parser.add_argument("handle", nargs="?", help="Codeforces handle")
    parser.add_argument("--test", action="store_true", help="Evaluate handles from cheaters/trusted lists")
    args = parser.parse_args()

    if args.test:
        evaluate_test_rows()
        return

    if args.handle is None:
        parser.error("handle is required unless --test is used")

    row, score, prediction = predict_handle(args.handle)
    label = "cheater" if prediction == 1 else "not cheater"

    print(f"handle: {row['handle']}")
    print(f"score: {score:.6f}")
    print(f"prediction: {label}")


if __name__ == "__main__":
    main()
