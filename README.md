# FluentSignalCopier ![Version](https://img.shields.io/badge/version-v0.10.0--beta-orange) ![Status](https://img.shields.io/badge/status-production--ready-green) ![Security Policy](https://img.shields.io/badge/security-policy-blue)

A production-ready bridge that reads trading signals from **Telegram** and executes them in **MetaTrader 5** via an Expert Advisor (EA).

---

## 🎯 Why This Project?

- **Real-world signal parsing**: Handles messy, human-written signals (e.g., "BUY LIMIT 3347", "SL @ 3341", comma/dot decimals, emojis)
- **Smart order types**: Distinguishes between pending orders (`BUY LIMIT`, `BUY STOP`) vs market entries
- **Multi-TP management**: Splits positions for multiple take-profit levels
- **Risk-aware**: Per-instrument lot caps, dollar risk limits, and percentage-based sizing
- **Selective closing**: Close-by-OID ensures only related trades are closed, preserving swing trades
- **Broker compatibility**: Symbol mapping (aliases like `US30 → DJ30`) and prefix/suffix support
- **GUI and CLI**: User-friendly interface for configuration and monitoring, plus a command-line option for automation

![FluentSignalCopier GUI](https://github.com/The-R4V3N/FluentSignalCopier/blob/master/image.png)

## 🆕 Latest Features

- **Centralized Logging**:
  - Unified logging system across GUI, Telegram bridge, and MT5 connector.
  - Structured log output with severity levels ([INFO], [WARN], [ERROR], [CRITICAL]).
  - Logs displayed directly in GUI with color-tagged badges.
  - Automatic log file rotation for production stability.

- **Monitoring Dashboard**:
  - Real-time visualization of logs and system activity.
  - Health checks for bridge ↔ EA connectivity.
  - Hooks for future performance metrics.

- **Alert System**:
  - Sends alerts on CRITICAL events (optional: future email/Slack/Discord hooks).
  - Keeps you aware of failures even if GUI is minimized.

- **Enhanced Production Readiness**:
  - Replaced ad-hoc print() statements with structured logs.
  - Clearer error handling with tracebacks in log files.
  - Easier debugging and audit trails.

## 🏗️ Architecture

```yml
Telegram → Python Bridge → MT5 Files → Expert Advisor → Trades
           (Parse & Filter)  (JSON)     (Execute)
                 │
                 ├── Logging → log files + GUI + dashboard
                 └── Alerts  → notify on CRITICAL events
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.11 or 3.12** (PySide6 does not yet support 3.13+)
- [Poetry](https://python-poetry.org/) for dependency management
- MetaTrader 5
- Telegram API credentials ([get them here](https://my.telegram.org))

### Installation (Development)

1. **Install Poetry** (on Windows recommended via [pipx](https://pypa.github.io/pipx/)):

   ```powershell
   pipx install poetry
    ```

2. **Clone the repo and enter the folder:**

    ```powershell
    git clone https://github.com/The-R4V3N/FluentSignalCopier.git
    cd FluentSignalCopier
    ```

3. **Create a Poetry venv with Python 3.11:**

    ```powershell
    poetry env use C:\Users\<you>\AppData\Local\Programs\Python\Python311\python.exe
    ```

4. **Install dependencies (script mode)::**

  ```powershell
    poetry install --no-root
  ```

5. **Install MT5 Expert Advisor:**

    - Copy FluentSignalCopier.mq5 to MQL5/Experts/
    - Compile in MetaEditor
    - Attach to any chart with AutoTrading enabled

## ▶️ Running

Option 1: GUI (Recommended)

- Run the FluentSignalCopier GUI to connect Telegram → MT5:

``` powershell
    poetry run python fluent_copier.py
```

Option 2: Command-line Bridge (Headless)

``` powershell
    poetry run python telegram_bridge.py
```

Both commands run inside the Poetry-managed virtual environment.

## 🛠️ Troubleshooting

| Issue      | Solution                                                                 |
|------------|--------------------------------------------------------------------------|
| No file/folder found for package fluentsignalcopier | Use poetry install --no-root in script mode |
| Poetry picks Python 3.13 | Force Python 3.11 with poetry env use <path-to-python311.exe> |
| PySide6 install fails | You’re likely on Python 3.13+ — downgrade to 3.11/3.12 |
| No trades placed | Check MT5 EA is attached, AutoTrading enabled, and symbols match |
| Symbol not found | Ensure the symbol is available in MT5 and matches the Telegram signal. Also add to Market Watch, check prefix/suffix |
| Multiple opens for one message | Enable deduplication in the GUI settings |
| Wrong trades closed | Verify close-by-OID is enabled in the GUI settings |

## 📋 Features

### Signal Format Support

The system understands multiple signal formats:

**Market Orders:**

```yml
XAUUSD Buy Now
SL 3341
TP 3362
```

**Pending Orders:**

```yml
#XAUUSD BUY LIMIT 3347
STOPLOSS @ 3320
TP @ 3357
```

**Risk Controls:**

```yml
XAUUSD Buy
RISK 2%
HALF RISK
```

- **Logging & Alerts**
  - Unified logging with rotating log files
  - Real-time log streaming into GUI
  - Severity levels with color-coded display
  - Optional alerts on CRITICAL errors

- **Monitoring Dashboard**:
  - Web-based dashboard (monitoring_dashboard.py)
  - Stream logs visually in charts/tables
  - Detect stale connections instantly

### Configuration

#### Telegram Bridge (.env)

- Rename .env.example to .env.
- Add your Credentials from my.telegram.org into the .env file:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_hash_here
TELEGRAM_PHONE=+1234567890
WATCH_CHATS=["Saved Messages", "Trading Signals"]
MT5_FILES_DIR=C:\Users\You\AppData\Roaming\MetaQuotes\Terminal\...\MQL5\Files
```

#### MT5 EA Parameters

- **Risk Management**: Percentage-based or fixed lots
- **Symbol Mapping**: Handle broker-specific symbol names
- **Position Limits**: Max positions per signal
- **Safety Caps**: Per-instrument lot limits
- **EmergencyCloseAll**: Close all positions if triggered by a signal or GUI
- **EnableModify**: Allow TP/SL modifications on active trades
- **SoundAlerts**: Play sounds on OPEN/CLOSE/EMERGENCY actions
- **ConfidenceThreshold**: Skip signals below a given quality score
- **SourceTagging**: Auto-tag trades with short hash of originating Telegram source

#### Heartbeat & Alerts

- **InpEnableHeartbeat**: Enable GUI heartbeat monitoring  
- **InpHeartbeatTimeout**: Seconds until EA considers the GUI stale  
- **InpHeartbeatPopupAlerts**: Show MT5 popup alerts when stale (default: off)  
- **InpHeartbeatPrintWarnings**: Print stale warnings to Experts tab (default: on)  
- **InpHeartbeatWarnInterval**: Minimum seconds between repeated stale warnings

## 🔧 Advanced Features

### Close-by-OID System

- Bridge tracks last OPEN per (chat, symbol)
- CLOSE commands target specific trade groups
- Preserves unrelated swing trades

### Multi-TP Management

- Automatically splits positions for multiple TPs
- Optional break-even at TP1
- Configurable position limits
- Supports mid-trade TP modifications (MODIFY_TP)

### Risk Controls

- Dollar risk caps per trade
- Per-instrument lot limits (Oil, Indices, FX, Crypto)
- Account balance percentage limits

## 📊 Monitoring

The system provides comprehensive logging:

- **Python Bridge**: Real-time parsing + logs
- **MT5 EA**: Trade execution logs
- **GUI**: Embedded log view + confidence slider
- **Monitoring Dashboard**: Central log stream with visualization
- **Alert System**: CRITICAL alerts dispatched automatically
- **Global Variables**: Per-channel state tracking
- **Heartbeat files**: EA writes heartbeat + position snapshots for GUI health-checks
- **Signal quality filter**: GUI slider skips incomplete or low-confidence signals automatically
  
## 🔄 File Structure

``` yml
FluentSignalCopier/
├── telegram_bridge.py          # Command-line bridge
├── fluent_copier.py            # GUI application  
├── pyproject.toml              # Poetry config
├── mt5/
│   └── FluentSignalCopier.mq5  # Expert Advisor
└── README.md                   # Project documentation
```

## 📄 JSON Schema

The bridge outputs structured data:

```json
{
  "action": "OPEN",
  "id": "15",
  "source": "Trading Channel",
  "symbol": "XAUUSD", 
  "side": "BUY",
  "entry": 3347.0,
  "sl": 3320.0,
  "tps_csv": "3357.0,3370.0,3384.0",
  "risk_percent": 1.0,
  "oid": "33"
}
```

Supports additional actions:

```json
{
  "action": "MODIFY_TP",
  "id": "57",
  "source": "VIP Signals",
  "symbol": "XAUUSD",
  "tp_slot": 4,
  "tp_to": 3399
}
```

## 🤝 Contributing

Contributions welcome! Please:

- See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing, coding standards, and release process.

## 🔐 Security

If you discover a vulnerability or security issue:

- Please **do not open a public issue**.
- Instead, report it privately by following our [SECURITY.md](SECURITY.md) guidelines.

We take security seriously and will respond promptly.

---

## 📜 Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md) to ensure a welcoming community.
By participating, you are expected to uphold this standard.

## ⚠️ Safety & Disclaimer

**This system places real trades.**

- Test on demo accounts first
- You are responsible for risk management
- No warranty provided
- Ensure compliance with your broker's policies

## 📜 License

MIT License - see LICENSE file for details.

## 🙏 Credits

- [Telethon](https://github.com/LonamiWebs/Telethon) for Telegram integration
- MetaQuotes for MT5/MQL5 platform
- Community contributors
- Inspiration from real-world trading practices
