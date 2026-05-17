const BACKEND_BASE_URL = "http://127.0.0.1:8765";
const CACHE_VERSION = "model-v1";
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;

const memoryCache = new Map();
const pendingRequests = new Map();

/**
 * Описание:
 * Приводит handle к единому виду для ключа cache.
 *
 * Параметры:
 * - handle: Codeforces handle из standings.
 *
 * Возвращает:
 * - string: нормализованный handle.
 */
function normalizeHandle(handle) {
  return String(handle || "").trim().toLowerCase();
}

/**
 * Описание:
 * Создает ключ cache для конкретной версии модели и handle.
 *
 * Параметры:
 * - handle: Codeforces handle из standings.
 *
 * Возвращает:
 * - string: ключ для chrome.storage.local.
 */
function getCacheKey(handle) {
  return `besterds:${CACHE_VERSION}:${normalizeHandle(handle)}`;
}

/**
 * Описание:
 * Читает значение из chrome.storage.local.
 *
 * Параметры:
 * - key: ключ cache.
 *
 * Возвращает:
 * - Promise<object | null>: сохраненное значение или null.
 */
function storageGet(key) {
  return new Promise((resolve) => {
    chrome.storage.local.get(key, (stored) => {
      resolve(stored[key] || null);
    });
  });
}

/**
 * Описание:
 * Записывает значение в chrome.storage.local.
 *
 * Параметры:
 * - key: ключ cache.
 * - value: значение, которое нужно сохранить.
 *
 * Возвращает:
 * - Promise<void>: завершение записи.
 */
function storageSet(key, value) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [key]: value }, resolve);
  });
}

/**
 * Описание:
 * Проверяет, можно ли использовать сохраненный prediction.
 *
 * Параметры:
 * - cached: объект из cache.
 *
 * Возвращает:
 * - boolean: true, если cache еще актуален.
 */
function isFreshCache(cached) {
  return Boolean(cached && Date.now() - cached.savedAt < CACHE_TTL_MS);
}

/**
 * Описание:
 * Читает prediction из memory cache или chrome.storage.local.
 *
 * Параметры:
 * - handle: Codeforces handle из standings.
 *
 * Возвращает:
 * - Promise<object | null>: prediction из cache или null.
 */
async function readCachedPrediction(handle) {
  const key = getCacheKey(handle);
  const memoryValue = memoryCache.get(key);

  if (isFreshCache(memoryValue)) {
    return { ...memoryValue.payload, cache: "memory" };
  }

  const storedValue = await storageGet(key);

  if (isFreshCache(storedValue)) {
    memoryCache.set(key, storedValue);
    return { ...storedValue.payload, cache: "storage" };
  }

  return null;
}

/**
 * Описание:
 * Сохраняет успешный prediction в memory cache и chrome.storage.local.
 *
 * Параметры:
 * - handle: Codeforces handle из standings.
 * - payload: ответ backend.
 *
 * Возвращает:
 * - Promise<void>: завершение записи cache.
 */
async function writeCachedPrediction(handle, payload) {
  if (!payload || !payload.ok) {
    return;
  }

  const key = getCacheKey(handle);
  const value = {
    savedAt: Date.now(),
    payload,
  };

  memoryCache.set(key, value);
  await storageSet(key, value);
}

/**
 * Описание:
 * Запрашивает предсказание у локального Python backend.
 *
 * Параметры:
 * - handle: Codeforces handle из standings.
 *
 * Возвращает:
 * - Promise<object>: JSON-ответ backend с prediction, score или error.
 */
async function fetchPrediction(handle) {
  const url = new URL("/predict", BACKEND_BASE_URL);
  url.searchParams.set("handle", handle);

  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok || !payload.ok) {
    return {
      ok: false,
      handle,
      error: payload.error || `Model API error ${response.status}`,
    };
  }

  return { ...payload, cache: "backend" };
}

/**
 * Описание:
 * Возвращает prediction из cache или запускает один общий request для handle.
 *
 * Параметры:
 * - handle: Codeforces handle из standings.
 *
 * Возвращает:
 * - Promise<object>: prediction из cache или backend.
 */
async function getPrediction(handle) {
  const key = getCacheKey(handle);
  const cached = await readCachedPrediction(handle);

  if (cached) {
    return cached;
  }

  if (pendingRequests.has(key)) {
    return pendingRequests.get(key);
  }

  const request = fetchPrediction(handle)
    .then(async (payload) => {
      await writeCachedPrediction(handle, payload);
      return payload;
    })
    .finally(() => {
      pendingRequests.delete(key);
    });

  pendingRequests.set(key, request);
  return request;
}

/**
 * Описание:
 * Обрабатывает сообщения от content script и проксирует запросы к backend.
 *
 * Параметры:
 * - message: сообщение от content script.
 * - sender: информация о вкладке-отправителе.
 * - sendResponse: callback для ответа content script.
 *
 * Возвращает:
 * - boolean | void: true, если ответ будет отправлен асинхронно.
 */
function handleMessage(message, sender, sendResponse) {
  if (!message || message.type !== "besterdsPredict") {
    return undefined;
  }

  getPrediction(message.handle)
    .then(sendResponse)
    .catch((error) => {
      sendResponse({
        ok: false,
        handle: message.handle,
        error: error.message,
      });
    });

  return true;
}

chrome.runtime.onMessage.addListener(handleMessage);
