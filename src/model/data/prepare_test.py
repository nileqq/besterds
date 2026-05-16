import pandas as pd
import time
from src.model import get_data as gd
import numpy as np
import argparse

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
    "max_place_surprise_window_rms",
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
    skipped_ones = client.get_skipped_count(contests=contests)

    return {
        "skipped_ratio": skipped_ones / len(contests),
        "skipped_contests_count": skipped_ones,
    }


def get_expected_place(contests: list, period=5, window_size=5, skip_first=5) -> float:
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
    expected_log_ranks = calculate_ema(log_ranks, period=period)

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
        "max_place_surprise_window_rms": get_expected_place(info_list, period=period),
        **extract_skipped_contests_features(client, info_list),
    }


def load_model():
    from src.model.model import Model

    return Model().train(verbose=False)


def predict_row(model, row):
    x = [row.get(col, 0.0) for col in FEATURE_COLS]
    score = model.predict_score(x)
    prediction = model.predict(x)

    return score, prediction


def predict_handle(handle: str):
    model = load_model()
    row = get_rating_features(handle)
    score, prediction = predict_row(model, row)

    return row, score, prediction


def calculate_binary_metrics(results):
    tp = sum(1 for row in results if row["expected"] == 1 and row["prediction"] == 1)
    tn = sum(1 for row in results if row["expected"] == 0 and row["prediction"] == 0)
    fp = sum(1 for row in results if row["expected"] == 0 and row["prediction"] == 1)
    fn = sum(1 for row in results if row["expected"] == 1 and row["prediction"] == 0)

    accuracy = (tp + tn) / len(results) if results else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def make_stratified_folds(labels, k=5, seed=0):
    if k < 2:
        raise ValueError("k must be >= 2")

    labels = np.array(labels, dtype=int)
    positive_indices = np.where(labels == 1)[0]
    negative_indices = np.where(labels == 0)[0]

    if k > len(positive_indices) or k > len(negative_indices):
        raise ValueError("k cannot be larger than the smallest class size")

    rng = np.random.default_rng(seed)
    rng.shuffle(positive_indices)
    rng.shuffle(negative_indices)

    folds = [[] for _ in range(k)]

    for i, idx in enumerate(positive_indices):
        folds[i % k].append(idx)

    for i, idx in enumerate(negative_indices):
        folds[i % k].append(idx)

    return [np.array(sorted(fold), dtype=int) for fold in folds]


def evaluate_kfold(csv_path="cheating_dataset.csv", k=5, seed=0):
    from src.model.model import FEATURE_COLS as MODEL_FEATURE_COLS
    from src.model.model import Model
    from src.model.model import prepare_training_frame

    df = pd.read_csv(csv_path)
    df = prepare_training_frame(df)
    labels = df["is_cheater"].astype(int).values
    folds = make_stratified_folds(labels, k=k, seed=seed)
    all_results = []
    fold_rows = []

    for fold_number, test_indices in enumerate(folds, start=1):
        train_indices = np.setdiff1d(np.arange(len(df)), test_indices)
        train_df = df.iloc[train_indices]
        test_df = df.iloc[test_indices]

        model = Model().train_df(
            train_df,
            seed=seed + fold_number,
            verbose=False,
        )

        fold_results = []
        for _, row in test_df.iterrows():
            x = [row[col] for col in MODEL_FEATURE_COLS]
            score = model.predict_score(x)
            prediction = model.predict(x)
            result = {
                "handle": row.get("handle", ""),
                "expected": int(row["is_cheater"]),
                "prediction": prediction,
                "score": score,
                "correct": int(prediction == int(row["is_cheater"])),
                "fold": fold_number,
            }
            fold_results.append(result)
            all_results.append(result)

        fold_metrics = calculate_binary_metrics(fold_results)
        fold_rows.append({
            "fold": fold_number,
            "size": len(fold_results),
            **fold_metrics,
        })

    metrics = calculate_binary_metrics(all_results)

    fold_df = pd.DataFrame(fold_rows)
    result_df = pd.DataFrame(all_results)

    print(fold_df[["fold", "size", "accuracy", "precision", "recall", "f1", "tp", "fp", "tn", "fn"]].to_string(index=False))
    print()
    print(result_df[["fold", "handle", "expected", "prediction", "score", "correct"]].to_string(index=False))
    print()
    print(f"kfold: {k}, seed: {seed}")
    print(
        "oof accuracy: {accuracy:.4f}, precision: {precision:.4f}, recall: {recall:.4f}, f1: {f1:.4f} "
        "(tp={tp}, fp={fp}, tn={tn}, fn={fn})".format(**metrics)
    )


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
    metrics = calculate_binary_metrics(results)

    print(df.to_string(index=False))
    print(
        "accuracy: {accuracy:.4f}, precision: {precision:.4f}, recall: {recall:.4f}, f1: {f1:.4f} "
        "(tp={tp}, fp={fp}, tn={tn}, fn={fn})".format(**metrics)
    )


def main():
    parser = argparse.ArgumentParser(description="Predict whether Codeforces handle looks like a cheater.")
    parser.add_argument("handle", nargs="?", help="Codeforces handle")
    parser.add_argument("--test", action="store_true", help="Evaluate handles from cheaters/trusted lists")
    parser.add_argument("--kfold", type=int, metavar="K", help="Run stratified K-fold evaluation on the CSV dataset")
    parser.add_argument("--csv", default="cheating_dataset.csv", help="Dataset CSV path")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    args = parser.parse_args()

    if args.kfold is not None:
        evaluate_kfold(csv_path=args.csv, k=args.kfold, seed=args.seed)
        return

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
