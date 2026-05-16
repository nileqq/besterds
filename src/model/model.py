import numpy as np
import pandas as pd


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


def prepare_training_frame(df):
    df = df.dropna().copy()

    if "max_place_surprise_window_rms" not in df.columns and "expected_place_surprise_rms" in df.columns:
        df["max_place_surprise_window_rms"] = df["expected_place_surprise_rms"]

    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0

    return df


class Model:
    def __init__(self, lr=0.01):
        self.lr = lr
        self.w = None
        self.mean = None
        self.std = None

    def normalize(self, X):
        return (X - self.mean) / self.std

    def df(self, x, y):
        """
        Gradient of log2(1 + exp(-y * <w, x>))
        y must be -1 or +1
        x shape: (n_features,)
        w shape: (n_features, 1)
        """
        x = x.reshape(-1, 1)

        margin = y * float(x.T @ self.w)

        # stable enough for small data
        grad = -(y * x) / ((1 + np.exp(margin)) * np.log(2))

        return grad

    def train(self, csv_path="cheating_dataset.csv", seed=0, epochs=2000, batch_size=5, verbose=True):
        df = pd.read_csv(csv_path)
        return self.train_df(df, seed=seed, epochs=epochs, batch_size=batch_size, verbose=verbose)

    def train_df(self, df, seed=0, epochs=2000, batch_size=5, verbose=True):
        np.random.seed(seed)

        df = prepare_training_frame(df)
        X = df[FEATURE_COLS].values.astype(float)

        y = df["is_cheater"].astype(int).values
        y = np.where(y == 1, 1, -1)

        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0) + 1e-8
        X = self.normalize(X)

        X = np.c_[X, np.ones((X.shape[0], 1))]

        n_samples, n_features = X.shape

        self.w = np.zeros((n_features, 1))
        batch_size = min(batch_size, n_samples)

        for epoch in range(epochs):
            k = np.random.randint(0, n_samples - batch_size + 1)

            grads = []

            for i in range(k, k + batch_size):
                grads.append(self.df(X[i], y[i]))

            grad = np.mean(grads, axis=0)

            self.w -= self.lr * grad

            if verbose and epoch % 100 == 0:
                print(f"epoch={epoch}, loss={self.loss(X, y):.4f}")

        return self

    def loss(self, X, y):
        margins = y.reshape(-1, 1) * (X @ self.w)

        return np.mean(np.log2(1 + np.exp(-margins)))

    def predict_score(self, x):
        x = np.array(x, dtype=float).reshape(1, -1)
        x = self.normalize(x)
        x = np.c_[x, np.ones((x.shape[0], 1))]

        return float(x @ self.w)

    def predict(self, x):
        score = self.predict_score(x)
        return int(score >= 0)
    
    def print_w(self):
        return self.w

if __name__ == "__main__":
    x = Model().train()
    print(x.print_w())
