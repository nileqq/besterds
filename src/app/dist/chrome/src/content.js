const STORAGE_KEYS = {
  enabled: "besterdsEnabled",
  mode: "besterdsMode",
};

const DEFAULT_SETTINGS = {
  enabled: true,
  mode: "hide",
};

const predictionCache = new Map();
let applyBesterdsPromise = null;

/**
 * Описание:
 * Отправляет сообщение background script и ждет ответ.
 *
 * Параметры:
 * - message: объект сообщения для background script.
 *
 * Возвращает:
 * - Promise<object>: ответ background script.
 */
function sendRuntimeMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      const error = chrome.runtime.lastError;

      if (error) {
        reject(new Error(error.message));
        return;
      }

      resolve(response);
    });
  });
}

/**
 * Описание:
 * Получает настройки Besterds из chrome.storage и дополняет их значениями по умолчанию.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - Promise<object>: настройки расширения для текущей страницы.
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
 * Приводит handle к единому виду для сравнения.
 *
 * Параметры:
 * - handle: строка с Codeforces handle.
 *
 * Возвращает:
 * - string: нормализованный handle.
 */
function normalizeHandle(handle) {
  return String(handle || "").trim().toLowerCase();
}

/**
 * Описание:
 * Достает handle владельца текущей Codeforces-сессии.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - string | null: handle владельца или null.
 */
function getOwnerHandle() {
  const ownerSelectors = [
    ".userbox a[href*=\"/profile/\"]",
    ".enter-or-register-box a[href*=\"/profile/\"]",
  ];

  for (const selector of ownerSelectors) {
    const link = document.querySelector(selector);
    const handle = link ? getHandleFromHref(link.href) : null;

    if (handle) {
      return handle;
    }
  }

  return new URLSearchParams(window.location.search).get("handle");
}

/**
 * Описание:
 * Запрашивает предсказание для handle у локального Python backend.
 *
 * Параметры:
 * - handle: Codeforces handle из standings.
 *
 * Возвращает:
 * - Promise<object>: ответ модели с score и prediction.
 */
async function fetchPrediction(handle) {
  const normalized = normalizeHandle(handle);

  if (!normalized) {
    throw new Error("Empty handle");
  }

  if (predictionCache.has(normalized)) {
    return predictionCache.get(normalized);
  }

  const request = sendRuntimeMessage({
    type: "besterdsPredict",
    handle,
  })
    .then((payload) => {
      if (!payload || !payload.ok) {
        throw new Error(payload?.error || "Model API error");
      }

      return payload;
    })
    .catch((error) => {
      throw error;
    });

  predictionCache.set(normalized, request);
  return request;
}

/**
 * Описание:
 * Выполняет async-операции с ограничением параллельности.
 *
 * Параметры:
 * - items: элементы, которые нужно обработать.
 * - limit: максимальное число одновременных операций.
 * - mapper: функция обработки одного элемента.
 *
 * Возвращает:
 * - Promise<object[]>: результаты в том же порядке, что и items.
 */
async function mapLimit(items, limit, mapper) {
  const results = new Array(items.length);
  let cursor = 0;

  async function worker() {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await mapper(items[index], index);
    }
  }

  const workers = Array.from(
    { length: Math.min(limit, items.length) },
    () => worker()
  );

  await Promise.all(workers);
  return results;
}

/**
 * Описание:
 * Получает модельные предсказания для всех handles в строке standings.
 *
 * Параметры:
 * - row: HTML-строка standings.
 * - ownerHandle: handle владельца аккаунта, которого нельзя скрывать.
 *
 * Возвращает:
 * - Promise<object>: флаг подозрительности, лучший score и ошибка, если backend недоступен.
 */
async function getRowPrediction(row, ownerHandle) {
  const handles = getRowHandles(row);

  if (!handles.length) {
    return { isSuspicious: false, score: null, error: null };
  }

  const isOwner = isOwnerRow(row, ownerHandle);

  if (isOwner) {
    const settledPredictions = await Promise.allSettled(handles.map(fetchPrediction));
    const predictions = settledPredictions
      .filter((result) => result.status === "fulfilled")
      .map((result) => result.value);

    if (!predictions.length) {
      return { isSuspicious: false, score: null, error: null, isOwner };
    }

    const maxScore = Math.max(...predictions.map((prediction) => prediction.score));
    const cache = [...new Set(predictions.map((prediction) => prediction.cache).filter(Boolean))]
      .join(", ");

    return {
      isSuspicious: false,
      score: maxScore,
      cache,
      error: null,
      isOwner,
    };
  }

  const predictions = await Promise.all(handles.map(fetchPrediction));
  const maxScore = Math.max(...predictions.map((prediction) => prediction.score));
  const isSuspicious = predictions.some((prediction) => prediction.prediction === 1);
  const cache = [...new Set(predictions.map((prediction) => prediction.cache).filter(Boolean))]
    .join(", ");

  return {
    isSuspicious,
    score: maxScore,
    cache,
    error: null,
  };
}

/**
 * Описание:
 * Достает handle из ссылки на профиль Codeforces.
 *
 * Параметры:
 * - href: адрес ссылки из standings.
 *
 * Возвращает:
 * - string | null: handle пользователя или null, если ссылка не является профилем.
 */
function getHandleFromHref(href) {
  try {
    const url = new URL(href, window.location.origin);
    const parts = url.pathname.split("/").filter(Boolean);

    if (parts[0] !== "profile" || !parts[1]) {
      return null;
    }

    return decodeURIComponent(parts[1]);
  } catch {
    return null;
  }
}

/**
 * Описание:
 * Собирает все handles, которые принадлежат строке standings.
 *
 * Параметры:
 * - row: HTML-строка таблицы standings.
 *
 * Возвращает:
 * - string[]: список handles из строки.
 */
function getRowHandles(row) {
  const links = [...row.querySelectorAll('a[href*="/profile/"]')];
  const handles = links
    .map((link) => getHandleFromHref(link.href))
    .filter(Boolean);

  return [...new Set(handles)];
}

/**
 * Описание:
 * Проверяет, принадлежит ли строка standings владельцу аккаунта.
 *
 * Параметры:
 * - row: HTML-строка standings.
 * - ownerHandle: handle владельца аккаунта.
 *
 * Возвращает:
 * - boolean: true, если строка содержит handle владельца.
 */
function isOwnerRow(row, ownerHandle) {
  const normalizedOwner = normalizeHandle(ownerHandle);

  if (!normalizedOwner) {
    return false;
  }

  return getRowHandles(row).some((handle) => normalizeHandle(handle) === normalizedOwner);
}

/**
 * Описание:
 * Проверяет, является ли строка таблицы строкой участника.
 *
 * Параметры:
 * - row: HTML-строка таблицы.
 *
 * Возвращает:
 * - boolean: true, если в строке есть хотя бы один Codeforces handle.
 */
function isStandingsParticipantRow(row) {
  return getRowHandles(row).length > 0;
}

/**
 * Описание:
 * Проверяет, является ли текущая страница страницей standings.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - boolean: true, если Besterds должен работать на текущей странице.
 */
function isStandingsPage() {
  const path = window.location.pathname;

  return (
    /\/contest\/\d+\/standings/.test(path) ||
    /\/gym\/\d+\/standings/.test(path) ||
    /\/group\/[^/]+\/contest\/\d+\/standings/.test(path)
  );
}

/**
 * Описание:
 * Находит таблицы Codeforces standings на текущей странице.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - HTMLTableElement[]: таблицы, в которых есть строки участников.
 */
function findStandingsTables() {
  return [...document.querySelectorAll("table")].filter((table) =>
    [...table.querySelectorAll("tr")].some(isStandingsParticipantRow)
  );
}

/**
 * Описание:
 * Удаляет старые метки Besterds из строки standings перед повторным рендером.
 *
 * Параметры:
 * - row: HTML-строка standings.
 *
 * Возвращает:
 * - void.
 */
function clearBesterdsRowState(row) {
  row.classList.remove("besterds-hidden-row", "besterds-highlight-row");
  row.querySelectorAll(".besterds-pure-rank, .besterds-mark").forEach((node) => {
    node.remove();
  });
}

/**
 * Описание:
 * Возвращает ячейку, рядом с которой можно показать pure rank.
 *
 * Параметры:
 * - row: HTML-строка standings.
 *
 * Возвращает:
 * - HTMLTableCellElement | null: первая ячейка строки или null.
 */
function getRankCell(row) {
  return row.querySelector("td");
}

function getOfficialRankText(row) {
  const rankCell = getRankCell(row);

  if (!rankCell) {
    return "";
  }

  const clone = rankCell.cloneNode(true);
  clone.querySelectorAll(".besterds-pure-rank, .besterds-mark").forEach((node) => {
    node.remove();
  });

  return clone.textContent.trim().replace(/\s+/g, " ");
}

function formatPureRankLabel(officialRank, pureRank) {
  const normalizedOfficialRank = officialRank.replace(/^#/, "");
  const currentRank = String(pureRank);

  if (normalizedOfficialRank && normalizedOfficialRank !== currentRank) {
    return `#${normalizedOfficialRank} -> real #${currentRank}`;
  }

  return `real #${currentRank}`;
}

function formatOwnerPlaceText(owner) {
  if (!owner) {
    return "";
  }

  const officialRank = owner.officialRank.replace(/^#/, "");
  const currentRank = String(owner.pureRank);

  if (officialRank && officialRank !== currentRank) {
    return `your place #${officialRank} -> real #${currentRank}`;
  }

  return `your real place #${currentRank}`;
}

function formatOwnerPanelText(stats) {
  if (stats.owner) {
    const failedBeforeText = stats.owner.failedBefore
      ? `, ${stats.owner.failedBefore} model errors before you`
      : "";

    return ` | ${formatOwnerPlaceText(stats.owner)} (${stats.owner.hiddenBefore} suspicious before you${failedBeforeText})`;
  }

  if (stats.ownerHandle) {
    return " | your row is not visible on this page";
  }

  return "";
}

/**
 * Описание:
 * Добавляет визуальную метку в строку standings.
 *
 * Параметры:
 * - row: HTML-строка standings.
 * - className: CSS-класс метки.
 * - text: текст метки.
 * - title: подсказка при наведении.
 *
 * Возвращает:
 * - HTMLSpanElement | null: созданная метка или null, если нет ячейки ранга.
 */
function appendRowBadge(row, className, text, title = "") {
  const rankCell = getRankCell(row);

  if (!rankCell) {
    return null;
  }

  const badge = document.createElement("span");
  badge.className = className;
  badge.textContent = text;
  if (title) {
    badge.title = title;
  }
  rankCell.appendChild(badge);
  return badge;
}

/**
 * Описание:
 * Форматирует score модели для debug-вывода в standings.
 *
 * Параметры:
 * - score: число, которое вернула модель через predict_score.
 *
 * Возвращает:
 * - string: короткая строка score или пустая строка, если score не число.
 */
function formatScore(score) {
  if (!Number.isFinite(score)) {
    return "";
  }

  return `score ${score.toFixed(2)}`;
}

/**
 * Описание:
 * Рендерит верхнюю панель управления Besterds над таблицей standings.
 *
 * Параметры:
 * - table: таблица standings.
 * - settings: текущие настройки расширения.
 * - stats: статистика фильтрации.
 *
 * Возвращает:
 * - void.
 */
function renderPanel(table, settings, stats) {
  const previousPanel = document.querySelector(".besterds-panel");
  if (previousPanel) {
    previousPanel.remove();
  }

  const panel = document.createElement("div");
  panel.className = "besterds-panel";

  const summary = document.createElement("div");
  const title = document.createElement("strong");
  const errorsText = stats.failed ? ` | model errors ${stats.failed}` : "";
  title.textContent = "Besterds Pure Leaderboard";
  summary.append(
    title,
    document.createTextNode(
      ` | hidden ${stats.hidden} of ${stats.total}${errorsText}${formatOwnerPanelText(stats)}`
    )
  );

  const actions = document.createElement("div");
  actions.className = "besterds-panel-actions";

  const toggleButton = document.createElement("button");
  toggleButton.className = "besterds-button";
  toggleButton.dataset.active = String(settings.enabled);
  toggleButton.textContent = settings.enabled ? "Enabled" : "Disabled";
  toggleButton.addEventListener("click", () => {
    chrome.storage.sync.set({ [STORAGE_KEYS.enabled]: !settings.enabled });
  });

  const modeButton = document.createElement("button");
  modeButton.className = "besterds-button";
  modeButton.dataset.active = "true";
  modeButton.textContent = settings.mode === "hide" ? "Hide mode" : "Highlight mode";
  modeButton.addEventListener("click", () => {
    chrome.storage.sync.set({
      [STORAGE_KEYS.mode]: settings.mode === "hide" ? "highlight" : "hide",
    });
  });

  actions.append(toggleButton, modeButton);
  panel.append(summary, actions);
  table.parentNode.insertBefore(panel, table);
}

/**
 * Описание:
 * Применяет pure leaderboard к одной таблице standings.
 *
 * Параметры:
 * - table: таблица standings.
 * - settings: текущие настройки расширения.
 *
 * Возвращает:
 * - object: статистика обработки таблицы.
 */
async function applyTable(table, settings) {
  const rows = [...table.querySelectorAll("tr")].filter(isStandingsParticipantRow);
  const ownerHandle = getOwnerHandle();
  let pureRank = 1;
  let hidden = 0;
  let failed = 0;
  let owner = null;

  rows.forEach((row) => {
    clearBesterdsRowState(row);
  });

  if (!settings.enabled) {
    return {
      total: rows.length,
      hidden,
      failed,
      owner,
      ownerHandle: null,
    };
  }

  const rowPredictions = await mapLimit(rows, 3, async (row) => {
    try {
      return await getRowPrediction(row, ownerHandle);
    } catch (error) {
      return { isSuspicious: false, score: null, error };
    }
  });

  rows.forEach((row, index) => {
    const prediction = rowPredictions[index];
    const isOwner = Boolean(prediction.isOwner);
    const officialRank = getOfficialRankText(row);

    if (prediction.error) {
      failed += 1;
      const message = prediction.error.message || String(prediction.error);
      appendRowBadge(row, "besterds-mark", "model error", message);
      pureRank += 1;
      return;
    }

    if (prediction.isSuspicious) {
      hidden += 1;
      const score = formatScore(prediction.score);
      appendRowBadge(
        row,
        "besterds-mark",
        `suspicious ${score}`.trim(),
        prediction.cache ? `cache: ${prediction.cache}` : ""
      );

      if (settings.mode === "hide") {
        row.classList.add("besterds-hidden-row");
      } else {
        row.classList.add("besterds-highlight-row");
      }

      return;
    }

    const score = formatScore(prediction.score);
    const rankLabel = formatPureRankLabel(officialRank, pureRank);
    const titleParts = [
      `Real place without suspicious rows: #${pureRank}`,
      officialRank ? `Official Codeforces place: #${officialRank.replace(/^#/, "")}` : "",
      prediction.cache ? `cache: ${prediction.cache}` : "",
    ].filter(Boolean);

    appendRowBadge(
      row,
      isOwner ? "besterds-pure-rank besterds-owner-rank" : "besterds-pure-rank",
      `${isOwner ? formatOwnerPlaceText({ officialRank, pureRank }) : rankLabel} ${score}`.trim(),
      titleParts.join(" | ")
    );

    if (isOwner) {
      owner = {
        officialRank,
        pureRank,
        hiddenBefore: hidden,
        failedBefore: failed,
      };
    }

    pureRank += 1;
  });

  return {
    total: rows.length,
    hidden,
    failed,
    owner,
    ownerHandle,
  };
}

/**
 * Описание:
 * Применяет Besterds ко всем standings-таблицам на странице.
 *
 * Параметры:
 * - нет.
 *
 * Возвращает:
 * - Promise<void>: завершение рендера.
 */
async function runBesterdsPass() {
  if (!isStandingsPage()) {
    return;
  }

  const settings = await loadSettings();
  const tables = findStandingsTables();

  if (!tables.length) {
    return;
  }

  const stats = await applyTable(tables[0], settings);
  renderPanel(tables[0], settings, stats);

  await Promise.all(tables.slice(1).map((table) => applyTable(table, settings)));
}

async function applyBesterds() {
  if (applyBesterdsPromise) {
    return applyBesterdsPromise;
  }

  applyBesterdsPromise = runBesterdsPass().finally(() => {
    applyBesterdsPromise = null;
  });

  return applyBesterdsPromise;
}

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "sync") {
    return;
  }

  if (!changes[STORAGE_KEYS.enabled] && !changes[STORAGE_KEYS.mode]) {
    return;
  }

  applyBesterds();
});

applyBesterds();
