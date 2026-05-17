const fs = require("fs");
const path = require("path");

const APP_DIR = path.resolve(__dirname, "..");
const COMMON_DIR = path.join(APP_DIR, "common");
const DIST_DIR = path.join(APP_DIR, "dist");

const TARGETS = [
  {
    name: "chrome",
    manifest: path.join(APP_DIR, "chrome", "manifest.json"),
    output: path.join(DIST_DIR, "chrome"),
  },
  {
    name: "firefox",
    manifest: path.join(APP_DIR, "firefox", "manifest.json"),
    output: path.join(DIST_DIR, "firefox"),
  },
];

/**
 * Описание:
 * Сбрасывает права на файл или папку перед удалением на Windows.
 *
 * Параметры:
 * - targetPath: путь к файлу или папке.
 *
 * Возвращает:
 * - void.
 */
function normalizePermissions(targetPath) {
  if (!fs.existsSync(targetPath)) {
    return;
  }

  const stats = fs.statSync(targetPath);

  if (stats.isDirectory()) {
    fs.readdirSync(targetPath).forEach((entry) => {
      normalizePermissions(path.join(targetPath, entry));
    });
  }

  fs.chmodSync(targetPath, 0o777);
}

/**
 * Описание:
 * Создает папку сборки, если она еще не существует.
 *
 * Параметры:
 * - directory: путь к папке сборки.
 *
 * Возвращает:
 * - void.
 */
function cleanDirectory(directory) {
  fs.mkdirSync(directory, { recursive: true });
}

/**
 * Описание:
 * Проверяет, совпадает ли содержимое двух файлов.
 *
 * Параметры:
 * - source: путь к исходному файлу.
 * - target: путь к целевому файлу.
 *
 * Возвращает:
 * - boolean: true, если оба файла существуют и совпадают.
 */
function filesAreEqual(source, target) {
  if (!fs.existsSync(target)) {
    return false;
  }

  return fs.readFileSync(source).equals(fs.readFileSync(target));
}

/**
 * Описание:
 * Копирует файл в целевую папку без лишнего удаления.
 *
 * Параметры:
 * - source: путь к исходному файлу.
 * - target: путь к целевому файлу.
 *
 * Возвращает:
 * - void.
 */
function copyFile(source, target) {
  if (filesAreEqual(source, target)) {
    return;
  }

  fs.mkdirSync(path.dirname(target), { recursive: true });
  normalizePermissions(target);
  fs.copyFileSync(source, target);
}

/**
 * Описание:
 * Копирует файл или папку в целевую директорию.
 *
 * Параметры:
 * - source: путь к исходному файлу или папке.
 * - target: путь, куда нужно скопировать данные.
 *
 * Возвращает:
 * - void.
 */
function copyPath(source, target) {
  const stats = fs.statSync(source);

  if (stats.isDirectory()) {
    fs.mkdirSync(target, { recursive: true });
    fs.readdirSync(source).forEach((entry) => {
      copyPath(path.join(source, entry), path.join(target, entry));
    });
    return;
  }

  copyFile(source, target);
}

/**
 * Описание:
 * Собирает одну browser-specific версию extension.
 *
 * Параметры:
 * - target: объект с именем браузера, manifest и output папкой.
 *
 * Возвращает:
 * - void.
 */
function buildTarget(target) {
  cleanDirectory(target.output);
  copyPath(COMMON_DIR, target.output);
  copyPath(target.manifest, path.join(target.output, "manifest.json"));
  console.log(`Built ${target.name}: ${target.output}`);
}

TARGETS.forEach(buildTarget);
