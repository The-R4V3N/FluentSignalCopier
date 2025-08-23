<!-- markdownlint-disable MD024 -->
# Changelog

## [0.11.0] - 2025-08-23

📓 Changelog

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
