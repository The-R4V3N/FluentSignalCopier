<!-- markdownlint-disable MD024 -->
# Changelog

## [0.10.0] - 2025-08-17

### Added

- Centralized logging system (`setup_logging.py`, `logging_config.py`).
- GUI log integration with color-tagged [INFO], [WARN], [ERROR] badges.
- Real-time monitoring dashboard (`monitoring_dashboard.py`) to visualize logs.
- Alert system (`alert_system.py`) for critical errors and notifications.

### Changed

- `fluent_copier.py` now integrates with the global logger.
- Logs now stored with rotation and optional alerting.
- Cleaner error handling, unified log format across modules.

### Removed

- Ad-hoc `print()` debugging → replaced with structured logs.

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
