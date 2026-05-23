const BACKEND_BASE_URL = "http://127.0.0.1:8765";
const CACHE_VERSION = "model-v1";
const CACHE_STORAGE_KEY = `besterds:${CACHE_VERSION}:predictionDict`;
const BACKEND_REQUEST_DELAY_MS = 2000;
const FAILED_CACHE_TTL_MS = 10 * 60 * 1000;

const memoryCache = new Map();
const pendingRequests = new Map();
let cacheLoaded = false;
let cacheLoadPromise = null;
let cacheSaveQueue = Promise.resolve();
let nextBackendRequestAt = 0;
let backendRequestQueue = Promise.resolve();

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
 * Ждет указанное количество миллисекунд.
 *
 * Параметры:
 * - delayMs: время ожидания в миллисекундах.
 *
 * Возвращает:
 * - Promise<void>: завершение ожидания.
 */
function sleep(delayMs) {
  return new Promise((resolve) => {
    setTimeout(resolve, delayMs);
  });
}

/**
 * Описание:
 * Ограничивает частоту запросов к локальному backend.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - Promise<void>: момент, когда можно отправлять следующий request.
 */
async function waitBackendRequestSlot() {
  const waitMs = Math.max(0, nextBackendRequestAt - Date.now());

  if (waitMs > 0) {
    await sleep(waitMs);
  }
}

/**
 * Описание:
 * Запускает backend request через общую очередь.
 *
 * Параметры:
 * - request: функция, которая отправляет один backend request.
 *
 * Возвращает:
 * - Promise<object>: результат backend request.
 */
function runBackendRequest(request) {
  const queuedRequest = backendRequestQueue.then(async () => {
    await waitBackendRequestSlot();

    try {
      return await request();
    } finally {
      nextBackendRequestAt = Date.now() + BACKEND_REQUEST_DELAY_MS;
    }
  });

  backendRequestQueue = queuedRequest.catch(() => {});

  return queuedRequest;
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
  return normalizeHandle(handle);
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
  if (!cached || !cached.payload) {
    return false;
  }

  if (cached.payload.ok) {
    return true;
  }

  return Date.now() - Number(cached.savedAt || 0) < FAILED_CACHE_TTL_MS;
}

function normalizeCacheEntry(entry) {
  if (!isFreshCache(entry)) {
    return null;
  }

  return {
    savedAt: Number(entry.savedAt) || Date.now(),
    payload: entry.payload,
  };
}

async function loadPredictionDict() {
  if (cacheLoaded) {
    return;
  }

  if (!cacheLoadPromise) {
    cacheLoadPromise = storageGet(CACHE_STORAGE_KEY)
      .then((stored) => {
        const users = stored?.version === CACHE_VERSION ? stored.users : null;

        if (users && typeof users === "object") {
          Object.entries(users).forEach(([handle, entry]) => {
            const key = normalizeHandle(handle);
            const normalizedEntry = normalizeCacheEntry(entry);

            if (key && normalizedEntry) {
              memoryCache.set(key, normalizedEntry);
            }
          });
        }

        cacheLoaded = true;
      })
      .catch(() => {
        cacheLoaded = true;
      });
  }

  await cacheLoadPromise;
}

function buildPredictionDictSnapshot() {
  const users = {};

  memoryCache.forEach((entry, handle) => {
    users[handle] = entry;
  });

  return {
    version: CACHE_VERSION,
    savedAt: Date.now(),
    users,
  };
}

function savePredictionDict() {
  cacheSaveQueue = cacheSaveQueue
    .then(() => storageSet(CACHE_STORAGE_KEY, buildPredictionDictSnapshot()))
    .catch(() => {});

  return cacheSaveQueue;
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
  await loadPredictionDict();

  const cached = memoryCache.get(getCacheKey(handle));

  if (isFreshCache(cached)) {
    return {
      ...cached.payload,
      cache: cached.payload.ok ? "dict" : "error-dict",
    };
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
  if (!payload) {
    return;
  }

  await loadPredictionDict();

  const key = getCacheKey(handle);

  if (!key) {
    return;
  }

  const value = {
    savedAt: Date.now(),
    payload,
  };

  memoryCache.set(key, value);
  await savePredictionDict();
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

  return runBackendRequest(async () => {
    const response = await fetch(url);
    const payload = await response.json().catch(() => ({}));

    if (!response.ok || !payload.ok) {
      return {
        ok: false,
        handle,
        error: payload.error || `Model API error ${response.status}`,
      };
    }

    return { ...payload, cache: payload.cache || "backend" };
  });
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
    .catch(async (error) => {
      const payload = {
        ok: false,
        handle,
        error: error.message,
      };

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
