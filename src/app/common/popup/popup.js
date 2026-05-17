const STORAGE_KEYS = {
  enabled: "besterdsEnabled",
  mode: "besterdsMode",
};

const BACKEND_BASE_URL = "http://127.0.0.1:8765";

const DEFAULT_SETTINGS = {
  enabled: true,
  mode: "hide",
};

const enabledInput = document.querySelector("#enabledInput");
const hideModeButton = document.querySelector("#hideModeButton");
const highlightModeButton = document.querySelector("#highlightModeButton");
const saveButton = document.querySelector("#saveButton");
const statusText = document.querySelector("#statusText");
const backendStatusText = document.querySelector("#backendStatusText");

let currentMode = DEFAULT_SETTINGS.mode;

/**
 * Описание:
 * Загружает настройки popup из chrome.storage.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - Promise<object>: настройки расширения.
 */
function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(Object.values(STORAGE_KEYS), (stored) => {
      resolve({
        enabled: stored[STORAGE_KEYS.enabled] ?? DEFAULT_SETTINGS.enabled,
        mode: stored[STORAGE_KEYS.mode] ?? DEFAULT_SETTINGS.mode,
      });
    });
  });
}

/**
 * Описание:
 * Сохраняет настройки popup в chrome.storage.
 *
 * Параметры:
 * - settings: объект с настройками расширения.
 *
 * Возвращает:
 * - Promise<void>: завершение сохранения.
 */
function saveSettings(settings) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(
      {
        [STORAGE_KEYS.enabled]: settings.enabled,
        [STORAGE_KEYS.mode]: settings.mode,
      },
      resolve
    );
  });
}

/**
 * Описание:
 * Проверяет, запущен ли локальный Python backend.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - Promise<boolean>: true, если backend отвечает на /health.
 */
async function checkBackend() {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/health`);
    const payload = await response.json();
    return response.ok && payload.ok;
  } catch {
    return false;
  }
}

/**
 * Описание:
 * Рисует активный режим фильтрации в popup.
 *
 * Параметры:
 * - mode: режим фильтрации, hide или highlight.
 *
 * Возвращает:
 * - void.
 */
function renderMode(mode) {
  currentMode = mode;
  hideModeButton.dataset.active = String(mode === "hide");
  highlightModeButton.dataset.active = String(mode === "highlight");
}

/**
 * Описание:
 * Рисует текущие настройки в popup.
 *
 * Параметры:
 * - settings: объект с настройками расширения.
 *
 * Возвращает:
 * - void.
 */
function renderSettings(settings) {
  enabledInput.checked = settings.enabled;
  renderMode(settings.mode);
}

/**
 * Описание:
 * Рисует состояние локального backend.
 *
 * Параметры:
 * - isOnline: true, если backend доступен.
 *
 * Возвращает:
 * - void.
 */
function renderBackendStatus(isOnline) {
  backendStatusText.textContent = isOnline
    ? "Model API is online"
    : "Start: python -m src.app.backend.server";
  backendStatusText.dataset.online = String(isOnline);
}

/**
 * Описание:
 * Показывает короткое сообщение о результате действия.
 *
 * Параметры:
 * - text: сообщение для пользователя.
 *
 * Возвращает:
 * - void.
 */
function showStatus(text) {
  statusText.textContent = text;
  window.setTimeout(() => {
    statusText.textContent = "";
  }, 1600);
}

hideModeButton.addEventListener("click", () => renderMode("hide"));
highlightModeButton.addEventListener("click", () => renderMode("highlight"));

saveButton.addEventListener("click", async () => {
  await saveSettings({
    enabled: enabledInput.checked,
    mode: currentMode,
  });

  showStatus("Saved");
});

loadSettings().then(renderSettings);
checkBackend().then(renderBackendStatus);
