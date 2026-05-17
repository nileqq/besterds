import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs
from urllib.parse import urlparse

from src.model.dataset.test import get_rating_features
from src.model.dataset.test import predict_row
from src.model.model import FEATURE_COLS
from src.model.model import Model


ROOT_DIR = Path(__file__).resolve().parents[3]
DATASET_PATH = ROOT_DIR / "cheating_dataset.csv"

_model = None
_model_lock = Lock()
_prediction_cache = {}
_prediction_cache_lock = Lock()
_handle_locks = {}
_handle_locks_lock = Lock()


def get_model():
    """
    Описание:
      Загружает и обучает текущую Python-модель один раз для всех запросов API.

    Параметры:
      - нет.

    Возвращает:
      - Model: обученная модель, которая используется для predict_score и predict.
    """

    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is None:
            _model = Model().train(csv_path=str(DATASET_PATH), verbose=False)

    return _model


def to_json_value(value):
    """
    Описание:
      Приводит значения numpy/pandas к обычным JSON-типам.

    Параметры:
      - value: значение признака или результата модели.

    Возвращает:
      - object: значение, которое можно безопасно отдать через json.dumps.
    """

    if hasattr(value, "item"):
        return value.item()

    return value


def get_handle_lock(cache_key):
    """
    Описание:
      Возвращает lock для одного handle, чтобы одинаковые запросы не считались параллельно.

    Параметры:
      - cache_key: нормализованный ключ handle.

    Возвращает:
      - Lock: lock, общий для всех запросов этого handle.
    """

    with _handle_locks_lock:
        if cache_key not in _handle_locks:
            _handle_locks[cache_key] = Lock()

        return _handle_locks[cache_key]


def build_prediction(handle):
    """
    Описание:
      Собирает признаки через существующий код и прогоняет их через текущую модель.

    Параметры:
      - handle: Codeforces handle, для которого нужно сделать предсказание.

    Возвращает:
      - dict: handle, score, бинарное prediction и признаки модели.
    """

    normalized_handle = handle.strip()
    cache_key = normalized_handle.lower()

    with _prediction_cache_lock:
        cached = _prediction_cache.get(cache_key)

    if cached is not None:
        return cached

    handle_lock = get_handle_lock(cache_key)

    with handle_lock:
        with _prediction_cache_lock:
            cached = _prediction_cache.get(cache_key)

        if cached is not None:
            return cached

        model = get_model()
        row = get_rating_features(normalized_handle)
        score, prediction = predict_row(model, row)

        result = {
            "handle": normalized_handle,
            "score": float(score),
            "prediction": int(prediction),
            "label": "suspicious" if int(prediction) == 1 else "clean",
            "features": {
                column: to_json_value(row.get(column, 0.0))
                for column in FEATURE_COLS
            },
        }

        with _prediction_cache_lock:
            _prediction_cache[cache_key] = result

    return result


class BesterdsHandler(BaseHTTPRequestHandler):
    """
    Описание:
      HTTP-handler для локального API, к которому обращается browser extension.
    """

    def send_json(self, status, payload):
        """
        Описание:
          Отправляет JSON-ответ с CORS-заголовками для расширения браузера.

        Параметры:
          - status: HTTP-статус ответа.
          - payload: словарь, который нужно вернуть клиенту.

        Возвращает:
          - void.
        """

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def do_OPTIONS(self):
        """
        Описание:
          Отвечает на preflight-запросы браузера.

        Параметры:
          - нет.

        Возвращает:
          - void.
        """

        self.send_json(HTTPStatus.OK, {})

    def do_GET(self):
        """
        Описание:
          Обрабатывает /health и /predict?handle=... запросы.

        Параметры:
          - нет.

        Возвращает:
          - void.
        """

        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True})
            return

        if parsed.path != "/predict":
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Unknown endpoint"})
            return

        handle = parse_qs(parsed.query).get("handle", [""])[0].strip()

        if not handle:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Missing handle"})
            return

        try:
            self.send_json(HTTPStatus.OK, {"ok": True, **build_prediction(handle)})
        except Exception as error:
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "handle": handle,
                    "error": str(error),
                },
            )


def create_server(host, port):
    """
    Описание:
      Создает локальный HTTP-сервер для Besterds extension.

    Параметры:
      - host: адрес, на котором будет слушать сервер.
      - port: порт локального API.

    Возвращает:
      - ThreadingHTTPServer: готовый к запуску сервер.
    """

    return ThreadingHTTPServer((host, port), BesterdsHandler)


def main():
    """
    Описание:
      Запускает локальный backend для расширения.

    Параметры:
      - нет.

    Возвращает:
      - void.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    print(f"Besterds model API: http://{args.host}:{args.port}")
    print(f"Dataset: {DATASET_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
