# FluentSignalCopier

A production-ready bridge that reads trading signals from **Telegram** and executes them in **MetaTrader 5** via an Expert Advisor (EA).

## 🎯 Why This Project?

- **Real-world signal parsing**: Handles messy, human-written signals (e.g., "BUY LIMIT 3347", "SL @ 3341", comma/dot decimals, emojis)
- **Smart order types**: Distinguishes between pending orders (`BUY LIMIT`, `BUY STOP`) vs market entries
- **Multi-TP management**: Splits positions for multiple take-profit levels
- **Risk-aware**: Per-instrument lot caps, dollar risk limits, and percentage-based sizing
- **Selective closing**: Close-by-OID ensures only related trades are closed, preserving swing trades
- **Broker compatibility**: Symbol mapping (aliases like `US30 → DJ30`) and prefix/suffix support

- **GUI and CLI**: User-friendly interface for configuration and monitoring, plus a command-line option for automation

![FluentSignalCopier GUI](https://github.com/The-R4V3N/FluentSignalCopier/blob/master/image.png)

## 🏗️ Architecture

``` yml
Telegram → Python Bridge → MT5 Files → Expert Advisor → Trades
           (Parse & Filter)  (JSON)     (Execute)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- MetaTrader 5
- Telegram API credentials ([get them here](https://my.telegram.org))

### Installation

1. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Build GUI Application (Optional):**

## Install build dependencies

py -3.12 -m pip install pyside6 "PySide6-Fluent-Widgets>=1.8" telethon pyinstaller

```bash
py -3.12 -m PyInstaller --clean --noconsole --onefile ^
    --name FluentSignalCopier ^
    --icon .\app.ico ^
    --add-data "app.ico;." ^
    --collect-all qfluentwidgets --collect-all PySide6 ^
    .\fluent_copier.py
    - Get API ID and Hash from [my.telegram.org](https://my.telegram.org)
    - Configure in `.env` or GUI
```

1. **Set up Telegram API:**

    - Get API ID and Hash from my.telegram.org
    - Configure in .env or GUI

2. **Install MT5 Expert Advisor:**

    - Copy FluentSignalCopier.mq5 to MQL5/Experts/
    - Compile in MetaEditor
    - Attach to any chart with AutoTrading enabled

## Basic Usage

### Option 1: GUI (Recommended)

```bash
python fluent_copier.py
```

#### Option 2: Command Line

```bash
python telegram_bridge.py
```

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

### Configuration

#### Python Bridge (.env or GUI)

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

## 🔧 Advanced Features

### Close-by-OID System

- Bridge tracks last OPEN per (chat, symbol)
- CLOSE commands target specific trade groups
- Preserves unrelated swing trades

### Multi-TP Management

- Automatically splits positions for multiple TPs
- Optional break-even at TP1
- Configurable position limits

### Risk Controls

- Dollar risk caps per trade
- Per-instrument lot limits (Oil, Indices, FX, Crypto)
- Account balance percentage limits

## 📊 Monitoring

The system provides comprehensive logging:

- **Python Bridge**: Real-time message parsing and filtering
- **MT5 EA**: Trade execution and position management
- **Global Variables**: Per-channel state tracking

## ⚠️ Safety & Disclaimer

**This system places real trades.**

- Test on demo accounts first
- You are responsible for risk management
- No warranty provided
- Ensure compliance with your broker's policies

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| FileOpen failed | Check MT5 file path and permissions |
| No trades placed | Enable AutoTrading, check symbol names |
| Symbol not found | Add to Market Watch, check prefix/suffix |
| Multiple opens for one message | Enable deduplication |
| Wrong trades closed | Verify close-by-OID is enabled |

## 🔄 File Structure

``` yml
FluentSignalCopier/
├── telegram_bridge.py      # Command-line bridge
├── fluent_copier.py        # GUI application  
├── requirements.txt        # Python dependencies
├── mt5/
│   └── FluentSignalCopier.mq5  # Expert Advisor
└── README.md
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

## 🤝 Contributing

Contributions welcome! Please:

- Follow MISRA C guidelines for MT5 code
- Include Doxygen documentation
- Test on demo accounts
- Submit pull requests with clear descriptions

## 📜 License

MIT License - see LICENSE file for details.

## 🙏 Credits

- [Telethon](https://github.com/LonamiWebs/Telethon) for Telegram integration
- MetaQuotes for MT5/MQL5 platform
- Community contributors
- Inspiration from real-world trading practices
