from src.model.get_data import GetData
import numpy as np
import pandas as pd

class EMAFeature:

    def __init__(self, handle: str):
        """
        Initialises EMAFeature class that returns EMA of the contests

        Parameters:
          - handle: handle of the user.

        Notes:
          - self.gd: creates an object of the class GetData to have an access to methods of the class
        """

        self.handle = handle
        self.gd = GetData(handle)

    def calculate_ema(self, values, period=5):
        """
        Calculates EMA - exponent moving average of the user's contests.

        Returns:
          - result: returns EMA for every contest
        """

        values = np.array(values)

        if len(values) == 0:
            return np.array([])
        
        # Formula for EMA: EMA_{t+1} = now * alpha + (1 - alpha) * EMA_t

        alpha = 2 / (period + 1)

        result = np.zeros(len(values))
        result[0] = values[0]

        for i in range(1, len(values)):
            result[i] = values[i] * alpha + (1 - alpha) * result[i - 1]

        return result

    def extract(self, deltas, period=5, skip_first=5):
        """
        Extracts and returns EMA - exponent moving average of the user's contests.
        """

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

        ema = self.calculate_ema(arr, period=period)

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



