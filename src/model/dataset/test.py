import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.model import get_data as gd
from src.model.model import FEATURE_COLS
from src.model.model import Model
from src.model.model import prepare_training_frame
from src.model.dataset.prepare_data.ema_feature import EMAFeature
from src.model.dataset.prepare_data.skipped_feature import SkippedFeature


FEATURE_DIR = Path(__file__).with_name("prepare_data")
if str(FEATURE_DIR) not in sys.path:
    sys.path.insert(0, str(FEATURE_DIR))


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


def get_rating_features(handle: str, period: int = 5):
    client = gd.GetData(handle)
    contests = client.get_contest_list()

    if len(contests) < 3:
        raise ValueError("Not enough rated contests to make prediction")

    rating_deltas = [
        contest["newRating"] - contest["oldRating"]
        for contest in contests
    ]

    return {
        "handle": handle,
        **EMAFeature().extract(rating_deltas, period=period),
        "max_place_surprise_window_rms": SkippedFeature.get_expected_place(
            contests,
            period=period,
            window_size=5,
        ),
        **SkippedFeature.extract_skipped_contests_features(client, contests),
    }


def load_model():
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
            score, prediction = predict_row(model, row)
            result = {
                "fold": fold_number,
                "handle": row.get("handle", ""),
                "expected": int(row["is_cheater"]),
                "prediction": prediction,
                "score": score,
                "correct": int(prediction == int(row["is_cheater"])),
            }
            fold_results.append(result)
            all_results.append(result)

        fold_rows.append({
            "fold": fold_number,
            "size": len(fold_results),
            **calculate_binary_metrics(fold_results),
        })

    fold_df = pd.DataFrame(fold_rows)
    result_df = pd.DataFrame(all_results)
    metrics = calculate_binary_metrics(all_results)

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
