<!-- markdownlint-disable MD024 -->
# Changelog

Changelog — 0.13.0

## Added

- **History Page**
  - New `Clear history` button wired to `/api/signals/clear?backup=true`, with automatic `.bak` safety copy before truncation.
  - Toast notifications for clear success/error.
  - Channel filter + pause/resume feed toggle.
- **Channel Performance**
  - Canonical source attribution: CLOSE signals are mapped back to their original OPEN’s channel when missing/blank.
  - Weighted overall win-rate across all channels (used in Dashboard KPI).
  - Best-by-Win% and Best-by-Score highlights in both table and cards.
- **Settings**
  - Server-backed sources list, Telegram API credentials, MT5 dir persisted in `web_settings.json`.
  - Auto-detect MT5 Files directory button.
  - Theme & signal-color pickers (BUY/SELL/MODIFY).
- **ControlsBar**
  - Mobile sticky action bar with Start/Pause/Stop + quality slider.
  - Desktop variant with enlarged quality range input.
- **Dashboard**
  - Recent signals card now hydrates from `/api/history` on load, then updates live via WebSocket.
  - Deduplication of signals across WS + REST.
  - Added “View full history” link.

### Changed

- **Backend**
  - `/api/health` and `/api/version` now include live git tag + commit hash via `_compute_version()`, without restart.
  - `/api/signals/clear` and `/api/history/clear` unified into a single safe implementation with backup.
  - `/api/channel-performance` and `/api/channels` improved to exclude internal/system sources consistently.
  - Snapshot file resolution more robust: prefers `positions_snapshot.json`, falls back to scan all sibling/common terminals.
- **Frontend**
  - Sidebar now token-based, no hardcoded dark styles.
  - Version + heartbeat pill in top bar uses live `/api/health` every 5s.

### Fixed

- EA: CLOSE record timestamp now uses `TimeGMT()` instead of `TimeCurrent()`.
  `TimeCurrent()` returns broker server time (UTC+2/+3), which caused the
  dashboard to display signal times offset by the broker's timezone (~2–3 hours
  ahead). `TimeGMT()` returns true UTC, matching the Python bridge's
  `time.localtime()` conversion. No bridge update required. ([#37](https://github.com/The-R4V3N/FluentSignalCopier/issues/37))

- Parser (bridge):
  - Safer SL/TP regex: captures full decimals, avoids placeholders (`TP1 / TP2` with no number).
  - SL hyphen sanitization (`SL-95.34` no longer parsed as negative).
  - “Close to entry” no longer mis-classified as CLOSE action.
  - Inline headers (`#XAUUSD BUY LIMIT @ 3402`) now parsed correctly as pending orders.
- Websocket backend:
  - Auto-recovers from file rotation/truncation (`Fluent_signals.jsonl`).
  - Correctly streams only new lines since last offset.

---

Changelog — 0.12.0
Added

- Order‑type routing: EA honors order_type in JSON (MARKET / LIMIT / STOP). Market orders ignore entry value; pendings use it.
- Multi‑TP legs: One signal can open multiple positions (per TP). Each leg gets a compact comment tag.
- Break‑even triggers: _BE_TRG=<price> embedded in the first leg’s comment; EA auto‑moves SL→BE once reached.
- Per‑channel sequencing: Last processed ID tracked via MT5 Global Variables, preventing cross‑chat replays.
- Per‑symbol last OPEN id: Used by CLOSE signals when oid is omitted.
- Heartbeat monitor: EA reads fluent_heartbeat.txt and warns on stale GUI; optional popups/sounds.
- Position snapshots: EA writes positions_snapshot.json periodically for the GUI dashboard.
- Safety caps: Symbol‑class limits (FX/metal/oil/index/crypto) and absolute $ risk cap.
- Sound cues: Configurable alerts for OPEN / CLOSE / EMERGENCY.

New GUI (PySide6 + QFluentWidgets):

- Home dashboard with live heartbeat dot, recent‑signal table, and counters.
- Signal quality slider (confidence gate).
- Chat Picker (fetch dialogs, filter & add).
- Pause intake and Emergency STOP buttons.
- Auto‑detect MT5 MQL5\Files paths.
- Rich, color‑tagged log; inline auth prompts (code/2FA).

Parser upgrades:

- Robust symbol aliases (XAU/GOLD, USOIL/WTI, DE40, SPX500, etc.).
- Detects LIMIT/STOP headers (#XAUUSD BUY LIMIT @ …) and “BUY/SELL NOW”.
- Extracts SL/TP lines in messy formats; collects multi‑TP; BE hint (“SL to entry at TP1”).
- New MODIFY_TP action (TP slot moves).

Changed

- Position comments reworked (compact 31‑char safe): SRC|OID=<id>|GID=<gid> with a 6‑char source tag for quick provenance.
- Risk sizing defaults: use risk_percent if present; otherwise fall back to EA input with dollar hard‑cap.
- Cleaner, defensive file I/O (JSONL line writer; heartbeat write/flush on each event).

Fixed

- Undeclared identifiers / enum issues in EA (e.g., gid name clash & DEAL_REASON_* handling).
- Safer JSON string escaping in EA.
- Duplicate/rapid Telegram events suppressed (GUI de‑dupe window).
- Graceful reconnect & shutdown in GUI (cancels heartbeat task; closes client).

Notes / Compatibility

- JSONL schema is backwards‑compatible for existing OPEN/CLOSE/MODIFY.
- New optional fields the EA understands: order_type, entry (only for LIMIT/STOP), be_on_tp, tps/tps_csv.
- No changes required to your MT5 symbols other than ensuring they’re visible in Market Watch.

## [0.11.0] - 2025-08-23

📓 Changelog

Fluent Copier (new GUI)

UI / UX

- Reduced default button height (setMinimumHeight from 44 → 34) to avoid overlap and make layout more compact.
- Refined default window size and spacing so cards + action buttons don’t collide on smaller screens.
- Inline auth box and Save/Start/Stop buttons aligned consistently across pages.

Log duplication fixed:

- _appendLog no longer appends messages twice; cleaned up duplicate HTML block.
- Added safety so logs show once per event, consistent with [INFO], [COUNTER], [SCAN], etc.

Pause/Resume logs simplified:

- Intake pause/resume now shows only a toast + button state, no duplicate [RUN] log spam.

Heartbeat cleanup:

- On window close, pending tasks are cancelled cleanly (no more “Task was destroyed but pending” warnings).

Chat Picker:

- Implemented correct filtering for “Show only watched” toggle.
- Case-insensitive matching across title, @username, and numeric ID.
- Fixed logic so only tracked channels are displayed when checkbox is on.
- Search filter and toggle now work together reliably.

Dashboard improvements:

- Channels badge now reflects the number of tracked chats (not total cached dialogs).
- Signals table automatically updates with incoming signals (OPEN, CLOSE, MODIFY, MODIFY_TP, EMERGENCY).

Telegram Bridge

- Minor consistency updates in logging for [COUNTER], [SCAN], and [RUN] to match new GUI parsing.

UI Dashboard (fix)

- Unified table update method: addSignalToTable (camelCase).
- Fixed signals counter badge not updating when new trades were received.

CopierThread

- Changed _write_signal to notify the UI through MainWindow._add_to_table instead of accessing the dashboard directly.
- Ensured all signal kinds (OPEN, CLOSE, MODIFY, MODIFY_TP, EMERGENCY_CLOSE_ALL) update both the file and the UI.

MainWindow

- Added _add_to_table() as a compatibility shim (calls dashboard.addSignalToTable).
- Emergency Stop now also updates the signals table via _add_to_table.

Changelog (GUI refresh)
Added

- Tracked-only channel count: “Channels” card now reflects tracked chats (from Settings), not cached dialogs.
- Chat picker seeded with current watch list (tracked chats pre-selected / prioritized).

Changed

- Wider layout: setMinimumSize(1200x750) and default resize(1320x860) for breathing room.
- Dashboard spacing & card grid polish.
- Pause button now toggles text between “Pause” and “Resume”.
- Removed noisy log lines for [RUN] Intake PAUSED/RESUMED (toast + button flip only).

Fixed

- Crash on STOP: restored _hideAuthBox() and auth UI helpers.
- QListWidgetItem NameError in chat picker (imported properly).
- Pending task warning on exit: heartbeat task is tracked/cancelled; loop shutdown is clean; closeEvent waits for thread.
- Duplicated “added chats” toast and text set in onDialogsReady.
- _update_tracked_count defined at class level and called only after pages exist.
- Fixed only the first TP is shown in recent Signals. Now all TP's are shown

## [0.10.0] - 2025-08-17

### Added

- Centralized logging system (`setup_logging.py`, `logging_config.py`).
- GUI log integration with color-tagged [INFO], [WARN], [ERROR] badges.
- Real-time monitoring dashboard (`monitoring_dashboard.py`) to visualize logs.
- Alert system (`alert_system.py`) for critical errors and notifications.
- Added `InpHeartbeatPopupAlerts` to the pyproject.toml.

### 📚 Docs / Dev (no functional change)

- Switched installation & usage docs to **Poetry-only workflow**:
  - Removed legacy `requirements.txt`, `requirements-dev.txt`, and `requirements-logging.txt` in favor of Poetry (`pyproject.toml`).
  - Added `poetry env use` and `poetry install --no-root` instructions.
  - Updated usage examples to `poetry run python …`.
- Cleaned up README:
  - Fixed code block formatting and numbering.
  - Merged duplicate Troubleshooting sections.
  - Moved disclaimer higher up for visibility.
  - Updated file structure to show `pyproject.toml` instead of `requirements.txt`.

---

### Changed

- `fluent_copier.py` now integrates with the global logger.
- Logs now stored with rotation and optional alerting.
- Cleaner error handling, unified log format across modules.

EA (FluentSignalCopier.mq5)

- Added explicit MARKET vs PENDING routing:
- order_type now respected (MARKET, LIMIT, STOP).
- Backward-compatible fallback to legacy behavior (presence of entry decides pending).
- Unified execution: MARKET uses Buy/Sell, PENDING routes via PlacePending.
- Improved debug logging with route info: side, symbol, order type, entry, and decision.
- Minor cleanup of redundant entry handling.

Bridge (telegram_bridge.py / fluent_copier.py)

- Added duplicate/replay suppression to prevent double execution.
- Implemented signal confidence scoring:
- Validates presence of SL/TP, format consistency.
- Marks/filters low-confidence signals.
- Added emergency stop signal forwarding (EMERGENCY_CLOSE_ALL).
- Improved message parsing:
- Unified parsing of LIMIT/STOP/MARKET keywords.
- Normalized symbol/side extraction for robustness.
- Expanded structured JSONL output with order_type and confidence fields.

GUI / Dashboard

- Added Emergency Stop button to send EMERGENCY_CLOSE_ALL.
- Added real-time deduplication status indicator.
- Integrated confidence scoring display in parsed signals list.
- Improved live monitoring panel:
- Shows signals processed, errors, warnings, open positions.
- Heartbeat monitoring with stale warnings.
- Added sound alerts for new signals and emergency events.

### Removed

- Ad-hoc `print()` debugging → replaced with structured logs.

### Fixed

- **telegram_bridge.py / fluent_copier.py**
  - Ensure `"tp"` field is set to the **first take-profit** for backward compatibility.
  - Add structured `"tps"` list alongside legacy `"tps_csv"` string.
  - Prevents cases where signals with multiple TPs had `"tp": null`,
    leading to missing TP in legacy EAs.

- **telegram_bridge.py**
  - Corrected TP parsing regex to capture full decimal values.
  - Previously, values like `198.600` were truncated to `198.0`,
    causing wrong TP levels in MT5 execution.

- **telegram_bridge.py**
  - Prevented false `TP` captures when messages only contain placeholders like `TP1 / TP2 / TP3` without numeric values.
  - Sanitized decorative hyphens (`SL-95.34`) to avoid parsing them as negative prices.
  - Fixed false-positive CLOSE detection on phrases like *"close to entry"* by tightening regex.

- **fluent_copier.py**
  - Synced regex/parsing improvements with bridge logic to ensure consistency between GUI and CLI.
- CLOSE and MODIFY signals no longer skipped by confidence threshold; slider now only applies to OPEN signals.

- **Break-even logic**: ensured that when "SL to entry at TP1" triggers, *all remaining TP-linked positions under the same OID* have their SL moved to entry, instead of only the first.

### Improved

- Duplicate/rapid replay handling:
  - Added clearer logging when duplicate signals are suppressed
    (e.g., channels forwarding their own message or sending quick edits).
  - No functional change—ensures trades aren’t opened twice.

## [0.9.1-beta] - 2025-08-17

### 🚀 Added

- Configurable heartbeat alerts:
  - `InpHeartbeatPopupAlerts` (off by default)
  - `InpHeartbeatPrintWarnings` (on by default)
  - `InpHeartbeatWarnInterval` (throttling, default 300s)
- Optional sound alert on heartbeat stale if popup alerts are enabled.
- Safer handling of malformed/empty heartbeat file content.

### 🛠️ Changed

- Heartbeat stale detection now respects user-defined alert modes instead of always showing intrusive `Alert()` popups.
- Minimum repeat interval enforced (30s) to avoid spam.

### 🐞 Fixed

- Debug print when heartbeat file missing on first run is now gated behind `InpDebug`.

### 📚 Docs / Dev (no functional change)

- Added `requirements-dev.txt` for build/testing extras (`pytest`, `black`, `pandas`, `requests`, `psutil`, `pyinstaller`).
- Updated `README.md` installation section:
  - Clear separation between production vs development installs.
  - Numbered steps corrected (1–5).
  - Polished **Basic Usage** with GUI-first flow.

---

## [0.9.0-beta] - Production milestone

### 🚀 Added

- **MODIFY signal support** (mid-trade TP/SL edits)
- **Emergency Close All** (Magic-scoped kill switch)
- Safer sequencing with per-channel `last_id` (no missed/skipped trades)
- Symbol handling split:  
  • OPEN requires symbol visibility  
  • CLOSE/MODIFY works even if symbol is hidden  
- **Confidence filter** (GUI slider) to auto-skip weak/incomplete signals
- Source-tagged trade comments (short 6-hex hash for traceability)
- Sound alerts for OPEN/CLOSE/EMERGENCY
- EA heartbeat + position snapshot JSON for GUI monitoring
- Deduplication of OPEN signals across edits/noisy repeats
<!-- markdownlint-enable MD024 -->
