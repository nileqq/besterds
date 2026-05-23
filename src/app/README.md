# Besterds Extension

Browser extension for Codeforces standings.

## Structure

```text
src/app/
  common/   shared implementation
  chrome/   Chrome manifest
  firefox/  Firefox manifest
  scripts/  build helpers
  dist/     generated loadable extensions
```

## Build

```powershell
node src/app/scripts/build.js
```

## Run model backend

Start this from the repository root before opening standings:

```powershell
python -m src.app.backend.server
```

## Run in Firefox

1. Start the model backend.
2. Run the build command.
3. Open `about:debugging#/runtime/this-firefox`.
4. Click `Load Temporary Add-on`.
5. Select `src/app/dist/firefox/manifest.json`.
6. Open a Codeforces standings page.

## Run in Chrome

1. Start the model backend.
2. Run the build command.
3. Open `chrome://extensions`.
4. Enable `Developer mode`.
5. Click `Load unpacked`.
6. Select `src/app/dist/chrome`.

## What it does

- Adds a Besterds panel above standings.
- Builds a pure leaderboard by asking the local Python model API for each visible handle.
- Shows your real place without suspicious users and `pure #N` ranks for clean rows.
- Supports hide and highlight modes.
- Uses the existing `src.model.model.Model` implementation instead of reimplementing the model in JavaScript.
- Caches predictions in one extension dictionary and in `src/app/backend/prediction_cache.json` so handles are not recomputed after reloads or backend restarts.
