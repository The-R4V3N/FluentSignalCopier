# fluent_copier_new_gui.py
# Modern Windows GUI (PySide6 + QFluentWidgets) for Telegram -> MT5 file-drop copier
# Build Example:
#    poetry run pyinstaller --clean --noconfirm --onefile --noconsole `
#  --name FluentSignalCopier `
#  --icon .\app.ico `
#  --add-data "app.ico;." `
#  --collect-all PySide6 `
#  --collect-all qfluentwidgets `
#  .\fluent_copier_new_gui.py

import os, re, sys, json, time, asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable
from html import escape

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QCoreApplication, QThread
from PySide6.QtGui import QTextCursor, QIcon, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QSlider, QLabel,
    QFileDialog, QMessageBox, QTabWidget, QSpacerItem, QSizePolicy,
    QDialog, QListWidget, QFrame, QHeaderView, QListWidgetItem, QCheckBox
)
from qfluentwidgets import (
    LineEdit, PushButton, PrimaryPushButton, TextEdit, SubtitleLabel, BodyLabel,
    CaptionLabel, InfoBar, InfoBarPosition, FluentIcon, setTheme, Theme, InfoBadge
)

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

# Optional sound beeps (Windows)
try:
    import winsound
    def _beep_ok():   winsound.MessageBeep(winsound.MB_ICONASTERISK)
    def _beep_warn(): winsound.MessageBeep(winsound.MB_ICONHAND)
except Exception:
    def _beep_ok():   pass
    def _beep_warn(): pass

# =====================================================================
# Configuration
# =====================================================================

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "R4V3N" / "Fluent_signals_copier"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONF_PATH = APP_DIR / "config.json"

@dataclass
class AppConfig:
    api_id: int = 0
    api_hash: str = ""
    phone: str = ""
    mt5_files_dir: str = ""
    watch_chats: List[str] = None
    session_name: str = "tg_bridge_session"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @staticmethod
    def from_json(s: str) -> "AppConfig":
        d = json.loads(s)
        return AppConfig(
            api_id=int(d.get("api_id", 0) or 0),
            api_hash=d.get("api_hash", ""),
            phone=d.get("phone", ""),
            mt5_files_dir=d.get("mt5_files_dir", ""),
            watch_chats=d.get("watch_chats") or ["Saved Messages"],
            session_name=d.get("session_name", "tg_bridge_session"),
        )

def load_config() -> AppConfig:
    if CONF_PATH.exists():
        try:
            return AppConfig.from_json(CONF_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return AppConfig()

def save_config(cfg: AppConfig):
    CONF_PATH.write_text(cfg.to_json(), encoding="utf-8")

# =====================================================================
# Parsing Utilities
# =====================================================================

def strip_ansi(s: str) -> str:
    """Remove ANSI color codes from any incoming log line."""
    return re.sub(r'\x1b\[[0-9;]*m', '', s or '')

def _normalize_spaces(s: str) -> str:
    """Normalize weird Unicode spaces/characters that appear in some channels."""
    if not s:
        return s
    # NBSP, narrow NBSP, figure space, BOM → normal space
    s = s.replace('\u00A0', ' ').replace('\u202F', ' ').replace('\u2007', ' ').replace('\ufeff', ' ')
    # Fullwidth at-sign → normal
    s = s.replace('＠', '@')
    return s

def _num(s: str) -> Optional[float]:
    """
    Robust numeric parser:
    - tolerates thousands separators ',' or ' ' or NBSP
    - handles decimals with '.' or ','
    - tolerates apostrophe thousands (e.g. 1'234.56)
    """
    if s is None:
        return None
    x = s.strip()
    # Remove spaces and NBSP variants used as thousands separators
    x = x.replace(' ', '').replace('\u00A0', '').replace('\u202F', '').replace('\u2007', '')
    # Remove common thousands apostrophes
    x = x.replace("'", "").replace("'", "")
    # If both ',' and '.' present -> assume ',' are thousands -> drop commas
    if ',' in x and '.' in x:
        x2 = x.replace(',', '')
    else:
        # If only ',' present and looks like thousands grouping -> drop commas
        if ',' in x:
            parts = x.split(',')
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                x2 = ''.join(parts)
            else:
                # treat comma as decimal separator
                x2 = x.replace(',', '.')
        else:
            x2 = x
    try:
        return float(x2)
    except Exception:
        return None

def _sanitize_price(v: Optional[float]) -> Optional[float]:
    """Sanitize price values."""
    if v is None:
        return None
    return abs(v)  # Prices are never negative

# =====================================================================
# Signal Parsing
# =====================================================================

# Symbol normalization
ALIASES = {
    "XAUSD": "XAUUSD", "XAU": "XAUUSD", "GOLD": "XAUUSD",
    "XAG": "XAGUSD", "SILVER": "XAGUSD",
    "NAS100": "NAS100", "US100": "NAS100", "USTEC": "NAS100",
    "US30": "DJ30", "DJ30": "DJ30", "DOW": "DJ30",
    "SPX500": "SPX500", "SP500": "SPX500", "US500": "SPX500",
    "GER40": "DE40", "DAX": "DE40", "DAX40": "DE40",
    "UK100": "UK100", "FTSE100": "UK100",
    "JP225": "JP225", "NIKKEI": "JP225",
    "USOIL": "XTIUSD", "WTI": "XTIUSD", "OIL": "XTIUSD", "XTIUSD": "XTIUSD",
    "BRENT": "XBRUSD", "UKOIL": "XBRUSD", "XBRUSD": "XBRUSD",
}

def normalize_symbol(s: str) -> str:
    s = (s or "").strip().upper()
    return ALIASES.get(s, s)

# Regex patterns for parsing
SYM_RE = re.compile(
    r'(?:#)?\b([A-Z]{6}|[A-Z]{2,5}\d{2,3}|XAU|XAUSD|GOLD|SILVER|XAG|USOIL|WTI|OIL|XTIUSD|UKOIL|BRENT|XBRUSD|SPX500|SP500|US500|USTEC|US30|DJ30)\b',
    re.I
)
SIDE_RE = re.compile(r'\b(BUY|SELL)\b', re.I)
ENTRY_RE = re.compile(r'^\s*(?:ENTER|ENTRY)\b.*?(-?\d+(?:[.,]\d+)?)\b', re.I)

SL_RES = [
    re.compile(r'\b(?:STOP\s*LOSS|STOPLOSS)\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\bSL\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

TP_RES = [
    re.compile(r'\bTP\d*\s*@\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\bTP\d*\s*(?:at|=|->)?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'^\s*TP\d*\s*@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

# Order type patterns
HEADER_PENDING_FULL_RE = re.compile(
    r'^\s*(?:#)?\s*(?P<sym>[A-Z]{3,6}|[A-Z]{2,5}\d{2,3})\s+'
    r'(?P<side>BUY|SELL)\s+(?P<ptype>LIMIT|STOP)\b.*?@?\s*(?P<price>-?\d+(?:[.,]\d+)?)\b',
    re.I | re.M
)

HEADER_INLINE_PRICE_RE = re.compile(
    r'^\s*(?:#)?\s*(?P<sym>[A-Z]{3,6}|[A-Z]{2,5}\d{2,3})\s+'
    r'(?P<side>BUY|SELL)\s+@?\s*(?P<price>-?\d+(?:[.,]\d+)?)\b',
    re.I | re.M
)

NOW_MARKET_RE = re.compile(r'\b(BUY|SELL)\s+(?:NOW|AT\s+MARKET|@\s*MARKET)\b', re.I)
PENDING_PAIR_RE = re.compile(r'\b(BUY|SELL)\s+(LIMIT|STOP)\b', re.I)
BE_HINT_RE = re.compile(r'\bSL\s*entry\s*at\s*TP\s*1\b', re.I)
RISK_PCT_RE = re.compile(r'\brisk\s*(\d+(?:[.,]\d+)?)\s*%?\b', re.I)
CLOSE_ANY_RE = re.compile(
    r'\b(?:close(?!\s+to)\b|close\s+all|close\s+at\s+market|close\s+now|flatten|exit\s+now|liquidate)\b',
    re.I
)

# TP move patterns
TP_MOVE_PATTERNS = [
    re.compile(r'\b(?:move|set|raise|adjust|shift)\s*tp\s*(\d{1,2})\s*(?:to|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\btp\s*(\d{1,2})\s*(?:moved\s*to|now\s*(?:at|to)?|=|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

def _try_sl(line: str) -> Optional[float]:
    for r in SL_RES:
        m = r.search(line)
        if m:
            v = _num(m.group(1))
            if v is not None:
                return _sanitize_price(v)
    return None

def _try_tp(line: str) -> Optional[float]:
    for r in TP_RES:
        m = r.search(line)
        if m:
            v = _num(m.group(1))
            if v is not None:
                return _sanitize_price(v)
    return None

def _find_tp_moves(text: str) -> List[Dict[str, Any]]:
    """Return list of {'slot': int, 'to': float} for any TP move variants found."""
    out: List[Dict[str, Any]] = []
    for pat in TP_MOVE_PATTERNS:
        for m in pat.finditer(text):
            price_str = m.group(m.lastindex)
            to_val = _num(price_str)
            if to_val is None:
                continue
            slot = 1
            if m.lastindex and m.lastindex >= 1:
                g1 = m.group(1)
                if g1 and re.fullmatch(r'\d{1,2}', g1):
                    slot = int(g1)
            out.append({"slot": slot, "to": to_val})
    return out

def parse_message(text: str) -> Optional[Dict[str, Any]]:
    """Parse a message into a signal dictionary."""
    t = _normalize_spaces(text).strip()
    low = t.lower()

    # Check for CLOSE
    if CLOSE_ANY_RE.search(t):
        ms = SYM_RE.search(t)
        sym = normalize_symbol(ms.group(1)) if ms else ""
        return {"kind": "CLOSE", "symbol": sym}

    # Check for MODIFY_TP
    tp_moves = _find_tp_moves(t)
    if tp_moves:
        ms = SYM_RE.search(t)
        sym = normalize_symbol(ms.group(1)) if ms else ""
        return {"kind": "MODIFY_TP", "symbol": sym, "tp_moves": tp_moves}

    # Check for MODIFY
    if any(k in low for k in ["updated", "update", "edit", "typo", "correction"]):
        new_sl = None
        tps = []
        ms = SYM_RE.search(t)
        sym = normalize_symbol(ms.group(1)) if ms else ""
        for line in t.splitlines():
            line = _normalize_spaces(line)
            s = line.strip().lower()
            if "sl" in s and "entry" not in s:
                v = _try_sl(line)
                if v is not None:
                    new_sl = v
            if "tp" in s:
                v = _try_tp(line)
                if v is not None:
                    tps.append(v)
        if new_sl is None and not tps:
            return None
        return {"kind": "MODIFY", "symbol": sym, "new_sl": new_sl, "new_tps": tps}

    # Parse OPEN signal
    side = None
    symbol = None
    entry = None
    sl = None
    tps = []
    order_type = "MARKET"
    be_on_tp = 1 if BE_HINT_RE.search(t) else 0

    # Check header patterns
    m = HEADER_PENDING_FULL_RE.search(t)
    if m:
        symbol = normalize_symbol(m.group('sym'))
        side = m.group('side').upper()
        entry = _num(m.group('price'))
        ptype = m.group('ptype').upper()
        order_type = "LIMIT" if ptype == "LIMIT" else "STOP"
    else:
        m2 = HEADER_INLINE_PRICE_RE.search(t)
        if m2:
            symbol = normalize_symbol(m2.group('sym'))
            side = m2.group('side').upper()
            entry = _num(m2.group('price'))

        # Check for order type overrides
        if PENDING_PAIR_RE.search(t):
            pm = PENDING_PAIR_RE.search(t)
            pside, ptyp = pm.group(1).upper(), pm.group(2).upper()
            side = side or pside
            order_type = "LIMIT" if ptyp == "LIMIT" else "STOP"
        elif NOW_MARKET_RE.search(t):
            order_type = "MARKET"

    # Line by line parsing
    lines = [_normalize_spaces(l).strip() for l in t.splitlines() if l.strip()]
    for ln in lines:
        if side is None:
            ms = SIDE_RE.search(ln)
            if ms:
                side = ms.group(1).upper()
        if symbol is None:
            mm = SYM_RE.search(ln)
            if mm:
                symbol = normalize_symbol(mm.group(1))
        if entry is None:
            me = ENTRY_RE.search(ln)
            if me:
                entry = _num(me.group(1))

    for ln in lines:
        lo = ln.lower()
        if "sl" in lo and "entry" not in lo:
            v = _try_sl(ln)
            if v is not None and sl is None:
                sl = v
        if "tp" in lo:
            v = _try_tp(ln)
            if v is not None:
                tps.append(v)

    if not (side and symbol):
        return None

    # Risk parsing
    risk = None
    m = RISK_PCT_RE.search(t)
    if m:
        risk = _num(m.group(1))

    # For MARKET orders, entry is reference only
    entry_ref = entry
    if order_type == "MARKET":
        entry = None

    return {
        "kind": "OPEN",
        "side": side,
        "symbol": symbol,
        "order_type": order_type,
        "entry": entry,
        "entry_ref": entry_ref,
        "sl": sl,
        "tps": tps,
        "be_on_tp": be_on_tp,
        "risk": risk,
    }

# =====================================================================
# MT5 Path Detection
# =====================================================================

def find_mt5_files_candidates() -> List[Path]:
    """Find likely MT5 MQL5\\Files directories, newest first."""
    cands: List[Path] = []

    for env in ("APPDATA", "LOCALAPPDATA"):
        base = Path(os.getenv(env, "")) / "MetaQuotes" / "Terminal"
        if base.exists():
            cands += [d / "MQL5" / "Files" for d in base.glob("*")]
            cands.append(base / "Common" / "Files")

    for pf in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = Path(os.getenv(pf, ""))
        if base.exists():
            cands.append(base / "MetaTrader 5" / "MQL5" / "Files")
            cands += list(base.glob("MetaTrader*/*/MQL5/Files"))

    cands.append(Path.home() / "MQL5" / "Files")

    # Remove duplicates and non-existent paths
    seen = set()
    unique = []
    for p in cands:
        try:
            rp = p.resolve()
            if rp not in seen and rp.exists():
                seen.add(rp)
                unique.append(rp)
        except Exception:
            continue

    # Sort by modification time (newest first)
    try:
        unique.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        pass
    
    return unique

def resource_path(name):
    """Get resource path for bundled files."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name

# =====================================================================
# Chat Picker Dialog
# =====================================================================

class ChatPickerDialog(QDialog):
    def __init__(self, chats: List[dict], parent=None, watch_set: set = None):
        super().__init__(parent)
        self.setWindowTitle("Pick chats to watch")
        self.resize(700, 560)
        self.setModal(True)

        self.watch_set = watch_set or set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Search + toggle row
        sr = QHBoxLayout()
        self.search = LineEdit(self)
        self.search.setPlaceholderText("Search title, @handle, or id…")
        self.onlyWatched = QCheckBox("Show only watched", self)
        self.onlyWatched.setChecked(True)  # default to only tracked
        sr.addWidget(self.search, 1)
        sr.addWidget(self.onlyWatched)
        layout.addLayout(sr)

        # Chat list
        self.list = QListWidget(self)
        self.list.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.list, 1)

        # Buttons
        btns = QHBoxLayout()
        ok_btn = PrimaryPushButton("Add selected", self)
        cancel_btn = PushButton("Cancel", self)
        btns.addStretch(1)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())

        # Populate list
        self._all_items: List[QListWidgetItem] = []
        for c in chats:
            title = c.get("title") or ""
            user = c.get("username") or ""
            ident = str(c.get("id", ""))

            label = title or (f"@{user}" if user else ident)
            sub = f"@{user}" if user else ident
            text = f"{label}    —    {sub}"

            item = QListWidgetItem(text)
            # canonical keys we’ll match against
            keys = {
                label.lower(),
                sub.lower(),
                ident.lower(),
                (f"@{user}".lower() if user else ""),
            }
            item.setData(Qt.UserRole, {"raw": c, "keys": {k for k in keys if k}})
            self.list.addItem(item)
            self._all_items.append(item)

        # Filtering logic
        def apply_filters():
            q = (self.search.text() or "").strip().lower()
            only = self.onlyWatched.isChecked()

            for item in self._all_items:
                data = item.data(Qt.UserRole)
                chat_data = data["raw"]

                # Build all possible identifiers for this chat
                title = (chat_data.get("title") or "").lower()
                username = (chat_data.get("username") or "").lower()
                chat_id = str(chat_data.get("id", "")).lower()

                # Create all possible searchable strings
                identifiers = set()
                if title: identifiers.add(title)
                if username: 
                    identifiers.add(username)
                    identifiers.add(f"@{username}")
                if chat_id: identifiers.add(chat_id)

                # Check if matches search query
                text_match = not q or any(q in ident for ident in identifiers)

                # Check if in watch list (case-insensitive comparison)
                in_watch_list = False
                if self.watch_set:
                    for watched in self.watch_set:
                        watched_lower = watched.lower()
                        # Check against all identifiers
                        if (watched_lower in identifiers or 
                            any(watched_lower == ident for ident in identifiers)):
                            in_watch_list = True
                            break
        
            # Show item if: matches text AND (not filtering or is in watch list)
            show_item = text_match and (not only or in_watch_list)
            item.setHidden(not show_item)

        self.search.textChanged.connect(apply_filters)
        self.onlyWatched.toggled.connect(apply_filters)
        apply_filters()  # initial

    def selected_entries(self) -> List[str]:
        out = []
        for item in self.list.selectedItems():
            c = item.data(Qt.UserRole)["raw"]
            if c.get("username"):
                out.append(f"@{c['username']}")
            elif c.get("title"):
                out.append(c["title"])
            else:
                out.append(str(c.get("id", "")))
        # de-dup
        seen = set()
        unique = []
        for s in out:
            if s and s.lower() not in seen:
                seen.add(s.lower())
                unique.append(s)
        return unique

# =====================================================================
# Copier Thread
# =====================================================================

class CopierThread(QThread):
    logLine = Signal(str)
    notify = Signal(str, str)
    authCodeNeeded = Signal()
    authPwdNeeded = Signal()
    runningState = Signal(bool)
    dialogsReady = Signal(list)
    signalProcessed = Signal(dict)

    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.client: Optional[TelegramClient] = None
        self._stop_flag = False
        self._paused = False
        self._code: Optional[str] = None
        self._password: Optional[str] = None
        self._hb_task = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._dialogs_cache: list = []
        self.quality_threshold = 60

        self.signal_file: Optional[Path] = None
        self.counter_file: Optional[Path] = None
        self.heartbeat_file: Optional[Path] = None
        self.global_counter = 0

        # Per-chat memory
        self.recent_symbol_by_chat: Dict[str, str] = {}
        self.last_open_oid: Dict[tuple, int] = {}
        self._recent_seen: Dict[str, float] = {}

    def set_quality_threshold(self, v: int):
        self.quality_threshold = max(0, min(100, int(v)))

    def set_auth_code(self, code: str):
        self._code = code

    def set_auth_password(self, pwd: str):
        self._password = pwd

    def set_paused(self, v: bool):
        self._paused = bool(v)

    def is_paused(self) -> bool:
        return self._paused

    def _choose_mt5_files(self) -> Path:
        p = Path(self.cfg.mt5_files_dir) if self.cfg.mt5_files_dir else None
        if p and p.exists():
            return p
        cands = find_mt5_files_candidates()
        if cands:
            return cands[0]
        return Path.home() / "MQL5" / "Files"

    def _load_counter(self):
        try:
            if self.counter_file.exists():
                self.global_counter = int(self.counter_file.read_text().strip())
                self.logLine.emit(f"[COUNTER] Loaded: {self.global_counter}")
            else:
                self.global_counter = 0
                self.logLine.emit("[COUNTER] Starting at 0")
        except Exception as e:
            self.global_counter = 0
            self.logLine.emit(f"[COUNTER] Load error: {e} -> 0")

    def _next_id(self) -> int:
        self.global_counter += 1
        try:
            self.counter_file.write_text(str(self.global_counter))
        except Exception as e:
            self.logLine.emit(f"[COUNTER] Save error: {e}")
        return self.global_counter

    def _confidence(self, p: dict) -> int:
        """Calculate confidence score for a parsed signal."""
        if not p:
            return 0
        k = p.get("kind")
        if k == "CLOSE":
            return 100
        if k in ("MODIFY_TP", "MODIFY"):
            return 90
        
        # OPEN signals
        score = 0
        score += 40 if p.get("side") and p.get("symbol") else 0
        if p.get("sl"):
            score += 20
        tps = p.get("tps") or []
        score += min(3, len(tps)) * 10
        if isinstance(p.get("entry"), (int, float)):
            score += 5
        if p.get("be_on_tp"):
            score += 5
        return min(100, score)

    def _dedupe_key(self, chat_id: int, msg_id: int, txt: str) -> str:
        import hashlib
        h = hashlib.sha1((txt.strip()[:400]).encode("utf-8", "ignore")).hexdigest()[:12]
        return f"{chat_id}:{msg_id}:{h}"

    def _dedupe_check(self, key: str, window=3.0) -> bool:
        now = time.time()
        # Purge old entries
        if self._recent_seen:
            for k, exp in list(self._recent_seen.items()):
                if exp < now:
                    self._recent_seen.pop(k, None)
        if key in self._recent_seen:
            return True
        self._recent_seen[key] = now + window
        return False

    def run(self):
        try:
            if sys.platform.startswith("win"):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._main(loop))
        except Exception as e:
            self.logLine.emit(f"[ERROR] {e}")
        finally:
            # cancel any stragglers (e.g., if window closed fast)
            if self._loop:
                try:
                    pending = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
                    for t in pending:
                        t.cancel()
                    if pending:
                        self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    try:
                        self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                    except Exception:
                        pass
                except Exception:
                    pass
                finally:
                    self._loop.close()
                    self._loop = None
            self.runningState.emit(False)

    @Slot()
    def getDialogs(self):
        """Get dialogs for chat picker."""
        if not self.client or not self._loop or not self._loop.is_running():
            self.notify.emit("Not connected", "Start and sign in first.")
            return

        if self._dialogs_cache:
            self.dialogsReady.emit(self._dialogs_cache)
            return

        try:
            asyncio.run_coroutine_threadsafe(self._async_emit_dialogs(300), self._loop)
        except Exception as e:
            self.notify.emit("Fetch failed", str(e))

    async def _async_emit_dialogs(self, limit: int = 1000):
        """Async method to fetch and emit dialogs."""
        try:
            dialogs = await self.client.get_dialogs(limit=limit)
            out = []
            for d in dialogs:
                e = d.entity
                title = (getattr(e, "title", None)
                        or (" ".join(x for x in [getattr(e, "first_name", None), 
                                                 getattr(e, "last_name", None)] if x)) or "").strip()
                username = getattr(e, "username", "") or ""
                out.append({"id": str(d.id), "title": title, "username": username})
            self._dialogs_cache = out
            self.dialogsReady.emit(out)
        except Exception as ex:
            self.notify.emit("Fetch failed", str(ex))

    async def _main(self, loop):
        """Main async loop."""
        self.runningState.emit(True)

        # Setup files
        mt5_dir = self._choose_mt5_files()
        mt5_dir.mkdir(parents=True, exist_ok=True)
        self.signal_file = mt5_dir / "Fluent_signals.jsonl"
        self.counter_file = mt5_dir / "signal_counter.txt"
        self.heartbeat_file = mt5_dir / "fluent_heartbeat.txt"
        self._load_counter()

        self.logLine.emit(f"[INFO] MT5 Files: {mt5_dir}")
        self.logLine.emit(f"[INFO] Writing: {self.signal_file}")

        api_id = int(self.cfg.api_id)
        api_hash = self.cfg.api_hash.strip()
        phone = self.cfg.phone.strip()
        
        if not api_id or not api_hash:
            self.notify.emit("Missing credentials", "Enter API ID and API Hash.")
            return

        session_path = str(APP_DIR / (self.cfg.session_name or "tg_bridge_session"))
        self.client = TelegramClient(session_path, api_id, api_hash)

        # Main connection loop with backoff
        backoff = 1.0
        while not self._stop_flag:
            try:
                await self.client.connect()
                
                # Authentication
                if not await self.client.is_user_authorized():
                    if not phone:
                        self.notify.emit("Phone needed", "Enter your phone number for first login.")
                        return
                    
                    result = await self.client.send_code_request(phone)
                    self.logLine.emit("[AUTH] Code sent.")
                    self.authCodeNeeded.emit()
                    
                    # Wait for code
                    while self._code is None and not self._stop_flag:
                        await asyncio.sleep(0.1)
                    if self._stop_flag:
                        break
                    
                    try:
                        await self.client.sign_in(phone=phone, code=self._code, 
                                                 phone_code_hash=result.phone_code_hash)
                    except SessionPasswordNeededError:
                        self.authPwdNeeded.emit()
                        while self._password is None and not self._stop_flag:
                            await asyncio.sleep(0.1)
                        if self._stop_flag:
                            break
                        await self.client.sign_in(password=self._password)

                me = await self.client.get_me()
                self.logLine.emit(f"[AUTH] Signed in as @{getattr(me,'username', None)} (id={me.id})")

                # Prefetch dialogs
                self.logLine.emit("[SCAN] Prefetching chats…")
                self._loop.create_task(self._prefetch_dialogs())

                # Setup watched chats
                watch = [w.strip() for w in (self.cfg.watch_chats or []) if str(w).strip()]
                watch_set = {w.lower() for w in watch}
                want_saved = any(x in ("me","saved messages","self") for x in watch_set)

                # Message handler
                @self.client.on(events.NewMessage)
                async def on_new_message(event):
                    if self._stop_flag:
                        return
                    if self._paused:
                        self.logLine.emit("[RUN] Intake paused; message ignored")
                        return

                    chat_id = event.chat_id
                    msg_id = event.id

                    # Update heartbeat
                    try:
                        self.heartbeat_file.write_text(str(int(time.time())), encoding="utf-8")
                    except Exception:
                        pass

                    # Dedupe check
                    key = self._dedupe_key(chat_id, msg_id, event.raw_text or "")
                    if self._dedupe_check(key):
                        self.logLine.emit("[WARN] Duplicate/rapid replay suppressed")
                        _beep_warn()
                        return

                    # Check if it's from a watched chat
                    title = ""
                    ok = False
                    
                    # Check Saved Messages
                    if event.is_private and want_saved:
                        me2 = await self.client.get_me()
                        if event.chat_id == me2.id:
                            title = "Saved Messages"
                            ok = True

                    # Check other chats
                    if not ok:
                        chat = await event.get_chat()
                        cands = set()
                        title = getattr(chat, "title", None) or ""
                        if title:
                            cands.add(title.strip().lower())

                        username = getattr(chat, "username", None)
                        if username:
                            u = username.strip()
                            cands.add(u.lower())
                            cands.add(('@' + u).lower())

                        cands.add(str(event.chat_id))

                        first = getattr(chat, "first_name", None)
                        last = getattr(chat, "last_name", None)
                        name_combo = " ".join(n for n in [first, last] if n)
                        if name_combo:
                            cands.add(name_combo.strip().lower())

                        ok = bool(watch_set & cands)
                        if not ok:
                            return

                    source_key = f"id:{chat_id}" if chat_id is not None else f"name:{(title or '').lower()}"

                    txt = event.raw_text or ""
                    self.logLine.emit(f"[NEW] {title}: {repr(txt[:180])}...")

                    # Parse message
                    p = parse_message(txt)
                    if not p:
                        self.logLine.emit("[PARSE] No valid signal.")
                        return

                    # Check confidence
                    conf = self._confidence(p)
                    threshold = self.quality_threshold
                    if p.get("kind") == "OPEN" and conf < threshold:
                        self.logLine.emit(f"[WARN] Signal skipped (confidence {conf} < {threshold})")
                        return

                    # Handle different signal types
                    if p["kind"] == "CLOSE":
                        sym = p["symbol"] or self.recent_symbol_by_chat.get(source_key)
                        if not sym:
                            self.logLine.emit("[CLOSE] No symbol context.")
                            return
                        oid = self.last_open_oid.get((source_key, sym), 0)
                        gid = self._next_id()
                        rec = {
                            "action": "CLOSE",
                            "id": str(msg_id),
                            "source_id": str(chat_id),
                            "t": int(time.time()),
                            "source": title,
                            "symbol": sym,
                            "oid": str(oid),
                            "gid": str(gid),
                            "original_event_id": str(event.id),
                            "confidence": conf
                        }
                        await self._write_signal(rec)
                        self.logLine.emit(f"[WRITE] CLOSE {sym} (OID={oid})")
                        _beep_ok()
                        return

                    elif p["kind"] == "MODIFY_TP":
                        sym = p.get("symbol") or self.recent_symbol_by_chat.get(source_key)
                        if not sym:
                            self.logLine.emit("[MODIFY_TP] No symbol context.")
                            return

                        moves = p.get("tp_moves") or []
                        if not moves:
                            self.logLine.emit("[MODIFY_TP] No moves parsed.")
                            return

                        for mv in moves:
                            tp_slot = int(mv.get("slot") or 1)
                            tp_to = mv.get("to")
                            gid = self._next_id()
                            rec = {
                                "action": "MODIFY_TP",
                                "id": str(msg_id),
                                "source_id": str(chat_id),
                                "t": int(time.time()),
                                "source": title,
                                "symbol": sym,
                                "tp_slot": tp_slot,
                                "tp_to": tp_to,
                                "gid": str(gid),
                                "original_event_id": str(event.id),
                                "confidence": conf
                            }
                            await self._write_signal(rec)
                            self.logLine.emit(f"[WRITE] MODIFY_TP {sym} TP{tp_slot} -> {tp_to}")
                        _beep_ok()
                        return

                    elif p["kind"] == "MODIFY":
                        sym = p["symbol"] or self.recent_symbol_by_chat.get(source_key)
                        if not sym:
                            self.logLine.emit("[MODIFY] No symbol context.")
                            return
                        gid = self._next_id()
                        rec = {
                            "action": "MODIFY",
                            "id": str(msg_id),
                            "source_id": str(chat_id),
                            "t": int(time.time()),
                            "source": title,
                            "symbol": sym,
                            "new_sl": p.get("new_sl"),
                            "new_tps_csv": ",".join(str(x) for x in (p.get("new_tps") or [])) or "",
                            "gid": str(gid),
                            "original_event_id": str(event.id),
                            "confidence": conf
                        }
                        await self._write_signal(rec)
                        self.logLine.emit(f"[WRITE] MODIFY {sym} SL->{p.get('new_sl')} TPs->{rec['new_tps_csv']}")
                        _beep_ok()
                        return

                    elif p["kind"] == "OPEN":
                        sym = p["symbol"]
                        self.recent_symbol_by_chat[source_key] = sym
                        gid = self._next_id()

                        tps_list = p.get("tps") or []
                        tp_first = tps_list[0] if tps_list else None
                        tps_csv = ",".join(str(x) for x in tps_list) if tps_list else ""

                        rec = {
                            "action": "OPEN",
                            "id": str(msg_id),
                            "source_id": str(chat_id),
                            "t": int(time.time()),
                            "source": title,
                            "raw": (txt.strip()[:1000]),
                            "side": p["side"],
                            "symbol": sym,
                            "order_type": p.get("order_type") or "MARKET",
                            "entry": p.get("entry"),
                            "entry_ref": p.get("entry_ref"),
                            "sl": p.get("sl"),
                            "tp": tp_first,
                            "tps": tps_list,
                            "tps_csv": tps_csv,
                            "risk_percent": (1.0 if p.get("risk") is None else p["risk"]),
                            "lots": None,
                            "be_on_tp": int(p.get("be_on_tp") or 0),
                            "gid": str(gid),
                            "original_event_id": str(event.id),
                            "confidence": conf,
                        }
                        await self._write_signal(rec)
                        self.last_open_oid[(source_key, sym)] = msg_id
                        self.logLine.emit(
                            f"[WRITE] OPEN {sym} {p['side']} [{p.get('order_type','MARKET')}] "
                            f"SL={p.get('sl')} TP={tp_first} TPs={tps_csv} (conf={conf})"
                        )
                        _beep_ok()

                # Edit handler
                @self.client.on(events.MessageEdited)
                async def on_edit(event):
                    chat_id = event.chat_id
                    msg_id = event.id
                    key = self._dedupe_key(chat_id, msg_id, event.raw_text or "") + ":edit"
                    if self._dedupe_check(key):
                        self.logLine.emit("[INFO] Duplicate/rapid replay (edit) suppressed")
                        return
                    await on_new_message(event)

                # Heartbeat writer
                async def _hb_writer():
                    try:
                        while not self._stop_flag and self.client and self.client.is_connected():
                            try:
                                self.heartbeat_file.write_text(str(int(time.time())), encoding="utf-8")
                            except Exception:
                                pass
                            await asyncio.sleep(5)
                    except asyncio.CancelledError:
                        return  # exit quietly

                    self._hb_task = loop.create_task(_hb_writer())

                loop.create_task(_hb_writer())
                self.logLine.emit("[RUN] Connected & listening…")
                backoff = 1.0
                await self.client.run_until_disconnected()

            except Exception as e:
                self.logLine.emit(f"[ERROR] {e}")
                _beep_warn()
            finally:
                try:
                    if self.client and self.client.is_connected():
                        await self.client.disconnect()
                        # ensure heartbeat task is gone
                        if self._hb_task:
                            try:
                                self._hb_task.cancel()
                                await asyncio.gather(self._hb_task, return_exceptions=True)
                            except Exception:
                                pass
                            finally:
                                self._hb_task = None
                        
                except Exception:
                    pass
                self.logLine.emit("[STOPPED]")

            if self._stop_flag:
                break
            
            self.logLine.emit(f"[WARN] Reconnecting in {int(backoff)}s…")
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 2.0)

    async def _write_signal(self, record: dict):
        """Write signal to file and notify UI."""
        with self.signal_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

        # Emit the signal data directly instead of making UI read from file
        self.signalProcessed.emit(record)

    async def _prefetch_dialogs(self, limit: int = 400):
        """Prefetch dialogs for quick access."""
        try:
            dialogs = await self.client.get_dialogs(limit=limit)
            out = []
            for d in dialogs:
                e = d.entity
                title = (getattr(e, "title", None)
                        or (" ".join(x for x in [getattr(e, "first_name", None), 
                                                 getattr(e, "last_name", None)] if x)) or "").strip()
                username = getattr(e, "username", "") or ""
                out.append({"id": str(d.id), "title": title, "username": username})
            self._dialogs_cache = out
            self.logLine.emit(f"[SCAN] Cached {len(out)} chats.")
        except Exception as ex:
            self.logLine.emit(f"[SCAN] Prefetch failed: {ex}")

    def stop(self):
        """Stop the thread and its asyncio tasks."""
        self._stop_flag = True
        try:
            if self._loop and self._loop.is_running():
                async def _shutdown():
                    # cancel heartbeat
                    try:
                        if self._hb_task and not self._hb_task.done():
                            self._hb_task.cancel()
                            await asyncio.gather(self._hb_task, return_exceptions=True)
                    except Exception:
                        pass
                    # disconnect telegram client
                    try:
                        if self.client and self.client.is_connected():
                            await self.client.disconnect()
                    except Exception:
                        pass
                asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
        except Exception as e:
            self.logLine.emit(f"[STOP] scheduling error: {e}")

class StatCard(QFrame):
    """Simple KPI card with title, value and optional status dot."""
    def __init__(self, title: str, value: str = "—", show_dot: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("StatCard")

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)

        self.titleLabel = CaptionLabel(title, self)

        self.dot = QLabel(self)
        self.dot.setFixedSize(10, 10)
        self.dot.setVisible(show_dot)
        self._dot_color = QColor(156, 163, 175)  # gray
        self._apply_dot_color()

        top.addWidget(self.titleLabel)
        top.addStretch(1)
        if show_dot:
            top.addWidget(self.dot)

        self.valueLabel = BodyLabel(value, self)
        self.valueLabel.setStyleSheet("font-size: 20px; font-weight: 600;")

        v.addLayout(top)
        v.addWidget(self.valueLabel)

    def setValue(self, text: str):
        self.valueLabel.setText(text)

    def setDotColor(self, color: QColor):
        self._dot_color = color
        self._apply_dot_color()

    def _apply_dot_color(self):
        c = self._dot_color
        self.dot.setStyleSheet(
            f"border-radius:5px; background: rgb({c.red()},{c.green()},{c.blue()});"
        )

class DashboardPage(QWidget):
    # Signals
    startRequested = Signal()
    stopRequested = Signal()
    pauseToggle = Signal()
    emergRequested = Signal()
    pickChats = Signal()
    qualityChanged = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.signal_count = 0
        self.channel_count = 0
        self.last_heartbeat = 0
        self._setup_ui()
        
        # Heartbeat checker timer
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._check_heartbeat)
        self.heartbeat_timer.start(1000)  # Check every second
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # --- Top: status badges + actions
        top = QHBoxLayout()
        layout.addLayout(top)

        # Left: status cards
        statusLayout = QVBoxLayout()
        
        # Status cards grid
        cardsLayout = QGridLayout()
        cardsLayout.setHorizontalSpacing(12)
        cardsLayout.setVerticalSpacing(10)
        
        # Helper function to create cards with badges
        def _makeCardWithBadge(title: str, initial_value: str = "Off", badge_type: str = "attension"):
            card = QWidget()
            card.setFixedHeight(80)
            card.setStyleSheet("""
                QWidget {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 8px;
                    padding: 8px;
                }
            """)
            
            cardLayout = QVBoxLayout(card)
            cardLayout.setContentsMargins(12, 8, 12, 8)
            cardLayout.setSpacing(4)
            
            # Title
            titleLabel = BodyLabel(title)
            titleLabel.setStyleSheet("color: #888; font-size: 12px;")
            cardLayout.addWidget(titleLabel)
            
            # Badge container
            badgeContainer = QWidget()
            badgeLayout = QHBoxLayout(badgeContainer)
            badgeLayout.setContentsMargins(0, 0, 0, 0)
            badgeLayout.setSpacing(0)
            
            if badge_type == "attension":
                badge = InfoBadge.attension(initial_value, badgeContainer)
            elif badge_type == "success":
                badge = InfoBadge.success(initial_value, badgeContainer)
            else:
                badge = InfoBadge.info(initial_value, badgeContainer)
            
            badge.setStyleSheet("font-size: 14px; font-weight: bold;")
            badgeLayout.addWidget(badge)
            badgeLayout.addStretch()
            
            cardLayout.addWidget(badgeContainer)
            cardLayout.addStretch()
            
            return card, badge
        
        # System Status Card
        self.systemCard, self.statusBadge = _makeCardWithBadge("System Status", "Off", "attension")
        
        # Signals Count Card  
        self.signalsCard, self.signalsBadge = _makeCardWithBadge("Signals Processed", "0", "info")
        
        # Channels Count Card
        self.channelsCard, self.channelsBadge = _makeCardWithBadge("Active Channels", "0", "info")
        
        # Heartbeat Card
        self.heartbeatCard, self.heartbeatBadge = _makeCardWithBadge("EA Heartbeat", "—", "attension")
        
        cardsLayout.addWidget(self.systemCard, 0, 0)
        cardsLayout.addWidget(self.signalsCard, 0, 1)
        cardsLayout.addWidget(self.channelsCard, 1, 0)
        cardsLayout.addWidget(self.heartbeatCard, 1, 1)
        
        # Slider under badges
        sliderLay = QHBoxLayout()
        self.qualityLabel = QLabel("Signal Quality ≥ 60", self)
        self.qualitySlider = QSlider(Qt.Horizontal, self)
        self.qualitySlider.setRange(0, 100)
        self.qualitySlider.setValue(50)
        self.qualitySlider.setTickInterval(10)
        self.qualitySlider.setTickPosition(QSlider.TicksBelow)
        sliderLay.addWidget(self.qualityLabel)
        sliderLay.addWidget(self.qualitySlider, 1)

        statusLayout.addLayout(cardsLayout)
        statusLayout.addLayout(sliderLay)
        top.addLayout(statusLayout, 1)

        # Right: big actions
        actWrap = QWidget(self)
        act = QVBoxLayout(actWrap)
        act.setSpacing(10)

        self.startBtn = PrimaryPushButton("START", self)
        self.stopBtn  = PushButton("STOP", self); self.stopBtn.setEnabled(False)
        self.pauseBtn = PushButton(FluentIcon.PAUSE, "Pause", self); self.pauseBtn.setEnabled(False)
        self.emergBtn = PrimaryPushButton("EMERGENCY STOP", self); self.emergBtn.setEnabled(False)
        for b in (self.startBtn, self.stopBtn, self.pauseBtn, self.emergBtn):
            b.setMinimumHeight(44)
            act.addWidget(b)

        self.pickBtn = PushButton(FluentIcon.PEOPLE, "Pick chats…", self); self.pickBtn.setEnabled(False)
        act.addWidget(self.pickBtn)
        act.addStretch(1)

        actWrap.setFixedWidth(280)
        top.addWidget(actWrap)
        
        # Inline auth box
        self.authBox = QWidget(self)
        authLay = QHBoxLayout(self.authBox)
        authLay.setContentsMargins(0, 0, 0, 0)
        authLay.setSpacing(8)
        self.authPrompt = SubtitleLabel("Enter the code you received:", self.authBox)
        self.authEdit = LineEdit(self.authBox)
        self.authEdit.setPlaceholderText("e.g. 12345")
        self.authSubmit = PrimaryPushButton("Submit", self.authBox)
        self.authCancel = PushButton("Cancel", self.authBox)
        authLay.addWidget(self.authPrompt)
        authLay.addWidget(self.authEdit, 1)
        authLay.addWidget(self.authSubmit)
        authLay.addWidget(self.authCancel)
        self.authBox.setVisible(False)
        layout.addWidget(self.authBox)
        
        # --- Recent Signals Table
        layout.addWidget(SubtitleLabel("Recent Signals"))
        self.signalsTable = QTableWidget(self)
        self.signalsTable.setColumnCount(6)
        self.signalsTable.setHorizontalHeaderLabels(["Time", "Action", "Symbol", "Side", "Entry/Price", "Details"])
        self.signalsTable.setMaximumHeight(150)
        self.signalsTable.setMinimumHeight(120)
        self.signalsTable.setAlternatingRowColors(True)
        self.signalsTable.horizontalHeader().setStretchLastSection(True)
        self.signalsTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.signalsTable.verticalHeader().setVisible(False)
        header = self.signalsTable.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Time
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Action
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Symbol
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Side
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Entry/Price
        header.setSectionResizeMode(5, QHeaderView.Stretch)           # Details fills the rest
        layout.addWidget(self.signalsTable)

        # --- Log
        layout.addWidget(SubtitleLabel("Log"))
        self.log = TextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(200)
        self.log.setAcceptRichText(True)
        self.log.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log.customContextMenuRequested.connect(lambda p: self._logMenu(p))
        layout.addWidget(self.log, 1)
        
        # Connect signals
        self._connect_signals()
        
    def _connect_signals(self):
        self.startBtn.clicked.connect(self.startRequested.emit)
        self.stopBtn.clicked.connect(self.stopRequested.emit)
        self.pauseBtn.clicked.connect(self.pauseToggle.emit)
        self.emergBtn.clicked.connect(self.emergRequested.emit)
        self.pickBtn.clicked.connect(self.pickChats.emit)
        
        self.qualitySlider.valueChanged.connect(
            lambda v: self.qualityLabel.setText(f"Signal Quality ≥ {v}")
        )
        self.qualitySlider.valueChanged.connect(self.qualityChanged.emit)
        
        self.authSubmit.clicked.connect(self._submitAuth)
        self.authCancel.clicked.connect(self._cancelAuth)
        
    def _logMenu(self, pos):
        menu = self.log.createStandardContextMenu()
        menu.addSeparator()
        act = menu.addAction("Clear log")
        act.triggered.connect(self.log.clear)
        menu.exec(self.log.mapToGlobal(pos))
            
    def _submitAuth(self):
        if self.parent_window:
            self.parent_window._submitAuth()
            
    def _cancelAuth(self):
        if self.parent_window:
            self.parent_window._cancelAuth()

    def _check_heartbeat(self):
        """Check heartbeat and update indicator"""
        if not self.parent_window or not self.parent_window.thread:
            self.heartbeatBadge.setText("—")
            self.heartbeatBadge.setColor(QColor(128, 128, 128))  # Gray
            return
            
        try:
            if hasattr(self.parent_window.thread, 'heartbeat_file') and self.parent_window.thread.heartbeat_file:
                if self.parent_window.thread.heartbeat_file.exists():
                    hb_time = int(self.parent_window.thread.heartbeat_file.read_text().strip())
                    current_time = int(time.time())
                    diff = current_time - hb_time
                    
                    if diff > 15:  # More than 15 seconds
                        self.heartbeatBadge.setText("Dead")
                        self.heartbeatBadge.setColor(QColor(239, 68, 68))  # Red
                    else:
                        self.heartbeatBadge.setText("OK")
                        self.heartbeatBadge.setColor(QColor(34, 197, 94))  # Green
                else:
                    self.heartbeatBadge.setText("No file")
                    self.heartbeatBadge.setColor(QColor(251, 146, 60))  # Orange
        except Exception:
            self.heartbeatBadge.setText("Error")
            self.heartbeatBadge.setColor(QColor(239, 68, 68))  # Red
    
    def addSignalToTable(self, signal_data: dict):
        """Add a new signal record to the table"""
        # Keep only last 20 records
        if self.signalsTable.rowCount() >= 20:
            self.signalsTable.removeRow(0)

        row = self.signalsTable.rowCount()
        self.signalsTable.insertRow(row)

        # Format timestamp
        timestamp = signal_data.get('t', int(time.time()))
        time_str = time.strftime('%H:%M:%S', time.localtime(timestamp))

        action = signal_data.get('action', '')
        symbol = signal_data.get('symbol', '')
        side = signal_data.get('side', '')

        # Format entry/price based on action
        entry_price = ""
        details = ""

        if action == "OPEN":
            order_type = signal_data.get('order_type', 'MARKET')
            entry = signal_data.get('entry')
            entry_ref = signal_data.get('entry_ref')

            if order_type == "MARKET":
                entry_price = f"MARKET ({entry_ref})" if entry_ref else "MARKET"
            else:
                entry_price = f"{order_type} @ {entry}" if entry else f"{order_type}"

            sl = signal_data.get('sl')
            tps = signal_data.get('tps', [])  # Get all TPs as list

            details_parts = []
            if sl:
                details_parts.append(f"SL: {sl}")
            if tps:
                # Show all TPs in format: TP1: 203.0, TP2: 204.0, TP3: 205.0
                tp_details = []
                for i, tp_value in enumerate(tps, 1):
                    tp_details.append(f"TP{i}: {tp_value}")
                details_parts.append(", ".join(tp_details))
            details = " | ".join(details_parts)

        elif action == "CLOSE":
            entry_price = "Market Close"
            details = f"OID: {signal_data.get('oid', '')}"

        elif action == "MODIFY":
            new_sl = signal_data.get('new_sl')
            new_tps = signal_data.get('new_tps_csv', '')
            details_parts = []
            if new_sl:
                details_parts.append(f"New SL: {new_sl}")
            if new_tps:
                details_parts.append(f"New TPs: {new_tps}")
            details = " | ".join(details_parts)

        elif action == "MODIFY_TP":
            tp_slot = signal_data.get('tp_slot', 1)
            tp_to = signal_data.get('tp_to')
            details = f"TP{tp_slot} → {tp_to}"

        elif action == "EMERGENCY_CLOSE_ALL":
            entry_price = "EMERGENCY"
            details = "Close all positions"
            side = ""

        # Set table items
        self.signalsTable.setItem(row, 0, QTableWidgetItem(time_str))
        self.signalsTable.setItem(row, 1, QTableWidgetItem(action))
        self.signalsTable.setItem(row, 2, QTableWidgetItem(symbol))
        self.signalsTable.setItem(row, 3, QTableWidgetItem(side))
        self.signalsTable.setItem(row, 4, QTableWidgetItem(entry_price))
        self.signalsTable.setItem(row, 5, QTableWidgetItem(details))
    
        # Color coding by action
        action_colors = {
            "OPEN": QColor(34, 197, 94, 50),      # Green
            "CLOSE": QColor(239, 68, 68, 50),     # RedaddSignalToTable
            "MODIFY": QColor(59, 130, 246, 50),   # Blue
            "MODIFY_TP": QColor(147, 51, 234, 50), # Purple
            "EMERGENCY_CLOSE_ALL": QColor(220, 38, 127, 50)  # Pink
        }

        color = action_colors.get(action, QColor(156, 163, 175, 50))
        for col in range(6):
            item = self.signalsTable.item(row, col)
            if item:
                item.setBackground(color)

        # Scroll to bottom
        self.signalsTable.scrollToBottom()

        # Update signals count
        self.signal_count += 1
        self.signalsBadge.setText(str(self.signal_count))

    # convenience helpers used by MainWindow
    def setRunning(self, running: bool) -> None:
        is_running = bool(running)             # keep the original meaning clear

        self.startBtn.setEnabled(not is_running)
        self.stopBtn.setEnabled(is_running)
        self.pauseBtn.setEnabled(is_running)
        self.emergBtn.setEnabled(is_running)
        self.pickBtn.setEnabled(is_running)
        
        # Update status badge
        if is_running:
            self.statusBadge.setText("On")
            self.statusBadge.setColor(QColor(34, 197, 94))  # Green
        else:
            self.statusBadge.setText("Off")
            self.statusBadge.setColor(QColor(156, 163, 175))  # Gray
            
    def updateChannelCount(self, count: int):
        """Update the channels count badge"""
        self.channel_count = count
        self.channelsBadge.setText(str(count))

class StatCard(QFrame):
    """Small card with a title, big value, and optional status dot."""
    def __init__(self, title: str, value: str = "—", show_dot: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumWidth(220)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.titleLbl = BodyLabel(title, self)
        self.dot = QLabel("●", self) if show_dot else None
        if self.dot:
            self.dot.setFixedWidth(10)
            self.dot.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.setDotColor(QColor(156, 163, 175))  # gray (off)
            head.addWidget(self.titleLbl)
            head.addWidget(self.dot)
            head.addStretch(1)
        else:
            head.addWidget(self.titleLbl)
            head.addStretch(1)
        lay.addLayout(head)

        self.valueLbl = QLabel(value, self)
        self.valueLbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.valueLbl.setStyleSheet("font-size: 24px; font-weight: 700;")
        lay.addWidget(self.valueLbl)

        # subtle border + rounding (follows dark/light theme nicely)
        self.setStyleSheet("""
            QFrame#statCard {
                background-color: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }
        """)

    def setValue(self, text: str):
        self.valueLbl.setText(text)

    def setDotColor(self, color: QColor):
        if not self.dot:
            return
        # use text color for the dot glyph
        self.dot.setStyleSheet(f"color: rgba({color.red()},{color.green()},{color.blue()},255); font-size: 12px;")

    def setOK(self, ok: bool, text_ok="OK", text_off="—"):
        self.setValue(text_ok if ok else text_off)
        self.setDotColor(QColor(34, 197, 94) if ok else QColor(239, 68, 68))


class DashboardPage(QWidget):
    # Signals
    startRequested = Signal()
    stopRequested = Signal()
    pauseToggle = Signal()
    emergRequested = Signal()
    pickChats = Signal()
    qualityChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.signal_count = 0
        self.channel_count = 0
        self._setup_ui()

        # Heartbeat checker timer
        self.last_heartbeat = 0
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._check_heartbeat)
        self.heartbeat_timer.start(1000)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ===== Top: stat cards + actions =====
        top = QHBoxLayout()
        top.setSpacing(12)
        root.addLayout(top)

        # Cards area
        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)

        self.cardSystem   = StatCard("System", "Off", show_dot=False)
        self.cardSignals  = StatCard("Signals", "0")
        self.cardChannels = StatCard("Channels", "0")
        self.cardHB       = StatCard("EA Heartbeat", "—", show_dot=True)

        cards.addWidget(self.cardSystem,   0, 0)
        cards.addWidget(self.cardSignals,  0, 1)
        cards.addWidget(self.cardChannels, 0, 2)
        cards.addWidget(self.cardHB,       0, 3)

        left = QVBoxLayout()
        left.addLayout(cards)

        # Quality slider under the cards
        sliderRow = QHBoxLayout()
        self.qualityLabel = QLabel("Signal Quality ≥ 60", self)
        self.qualitySlider = QSlider(Qt.Horizontal, self)
        self.qualitySlider.setRange(0, 100)
        self.qualitySlider.setValue(60)
        self.qualitySlider.setTickInterval(10)
        self.qualitySlider.setTickPosition(QSlider.TicksBelow)
        sliderRow.addWidget(self.qualityLabel)
        sliderRow.addWidget(self.qualitySlider, 1)
        left.addLayout(sliderRow)

        top.addLayout(left, 1)

        # Actions column
        actions = QVBoxLayout()
        actions.setSpacing(10)
        self.startBtn = PrimaryPushButton("START", self)
        self.stopBtn  = PushButton("STOP", self); self.stopBtn.setEnabled(False)
        self.pauseBtn = PushButton(FluentIcon.PAUSE, "Pause", self); self.pauseBtn.setEnabled(False)
        self.emergBtn = PrimaryPushButton("EMERGENCY STOP", self); self.emergBtn.setEnabled(False)
        for b in (self.startBtn, self.stopBtn, self.pauseBtn, self.emergBtn):
            b.setMinimumHeight(44)
            actions.addWidget(b)

        self.pickBtn = PushButton(FluentIcon.PEOPLE, "Pick chats…", self)
        self.pickBtn.setEnabled(False)
        actions.addWidget(self.pickBtn)
        actions.addStretch(1)
        top.addLayout(actions)

        # Inline auth box
        self.authBox = QWidget(self)
        authLay = QHBoxLayout(self.authBox)
        authLay.setContentsMargins(0, 0, 0, 0); authLay.setSpacing(8)
        self.authPrompt = SubtitleLabel("Enter the code you received:", self.authBox)
        self.authEdit = LineEdit(self.authBox); self.authEdit.setPlaceholderText("e.g. 12345")
        self.authSubmit = PrimaryPushButton("Submit", self.authBox)
        self.authCancel = PushButton("Cancel", self.authBox)
        authLay.addWidget(self.authPrompt); authLay.addWidget(self.authEdit, 1)
        authLay.addWidget(self.authSubmit); authLay.addWidget(self.authCancel)
        self.authBox.setVisible(False)
        root.addWidget(self.authBox)

        # ===== Recent Signals =====
        root.addWidget(SubtitleLabel("Recent Signals"))
        self.signalsTable = QTableWidget(self)
        self.signalsTable.setColumnCount(6)
        self.signalsTable.setHorizontalHeaderLabels(["Time", "Action", "Symbol", "Side", "Entry/Price", "Details"])
        self.signalsTable.setMaximumHeight(150)
        self.signalsTable.setMinimumHeight(120)
        self.signalsTable.setAlternatingRowColors(True)
        self.signalsTable.horizontalHeader().setStretchLastSection(True)
        self.signalsTable.verticalHeader().setVisible(False)
        self.signalsTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        root.addWidget(self.signalsTable)

        # ===== Log =====
        root.addWidget(SubtitleLabel("Log"))
        self.log = TextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(200)
        self.log.setAcceptRichText(True)
        self.log.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log.customContextMenuRequested.connect(lambda p: self._logMenu(p))
        root.addWidget(self.log, 1)

        # Wire up signals
        self._connect_signals()

    # ---------- wiring ----------
    def _connect_signals(self):
        self.startBtn.clicked.connect(self.startRequested.emit)
        self.stopBtn.clicked.connect(self.stopRequested.emit)
        self.pauseBtn.clicked.connect(self.pauseToggle.emit)
        self.emergBtn.clicked.connect(self.emergRequested.emit)
        self.pickBtn.clicked.connect(self.pickChats.emit)

        self.qualitySlider.valueChanged.connect(
            lambda v: self.qualityLabel.setText(f"Signal Quality ≥ {v}")
        )
        self.qualitySlider.valueChanged.connect(self.qualityChanged.emit)

        self.authSubmit.clicked.connect(self._submitAuth)
        self.authCancel.clicked.connect(self._cancelAuth)

    def _logMenu(self, pos):
        menu = self.log.createStandardContextMenu()
        menu.addSeparator()
        act = menu.addAction("Clear log")
        act.triggered.connect(self.log.clear)
        menu.exec(self.log.mapToGlobal(pos))

    # ---------- auth passthrough ----------
    def _submitAuth(self):
        if self.parent_window:
            self.parent_window._submitAuth()

    def _cancelAuth(self):
        if self.parent_window:
            self.parent_window._cancelAuth()

    # ---------- heartbeat ----------
    def _check_heartbeat(self):
        """Check EA heartbeat file and color the dot."""
        if not self.parent_window or not self.parent_window.thread:
            self.cardHB.setValue("—")
            self.cardHB.setDotColor(QColor(128, 128, 128))  # gray
            return
        try:
            th = self.parent_window.thread
            if hasattr(th, "heartbeat_file") and th.heartbeat_file and th.heartbeat_file.exists():
                hb_time = int(th.heartbeat_file.read_text().strip() or "0")
                diff = int(time.time()) - hb_time
                if diff > 15:
                    self.cardHB.setValue("Dead")
                    self.cardHB.setDotColor(QColor(239, 68, 68))  # red
                else:
                    self.cardHB.setValue("OK")
                    self.cardHB.setDotColor(QColor(34, 197, 94))  # green
            else:
                self.cardHB.setValue("No file")
                self.cardHB.setDotColor(QColor(251, 146, 60))  # orange
        except Exception:
            self.cardHB.setValue("Error")
            self.cardHB.setDotColor(QColor(239, 68, 68))

    # ---------- signals table ----------
    def addSignalToTable(self, signal_data: dict):
        # keep only last 20 rows
        if self.signalsTable.rowCount() >= 20:
            self.signalsTable.removeRow(0)

        row = self.signalsTable.rowCount()
        self.signalsTable.insertRow(row)

        ts = signal_data.get("t", int(time.time()))
        time_str = time.strftime("%H:%M:%S", time.localtime(ts))
        action  = signal_data.get("action", "")
        symbol  = signal_data.get("symbol", "")
        side    = signal_data.get("side", "")

        entry_price = ""
        details = ""

        if action == "OPEN":
            order_type = signal_data.get('order_type', 'MARKET')
            entry = signal_data.get('entry')
            entry_ref = signal_data.get('entry_ref')

            if order_type == "MARKET":
                entry_price = f"MARKET ({entry_ref})" if entry_ref else "MARKET"
        else:
            entry_price = f"{order_type} @ {entry}" if entry else f"{order_type}"
            
        sl = signal_data.get('sl')
        tps = signal_data.get('tps', [])  # Get all TPs as list
        
        details_parts = []
        if sl:
            details_parts.append(f"SL: {sl}")
        if tps:
            # Show all TPs in format: TP1: 203.0, TP2: 204.0, TP3: 205.0
            tp_details = []
            for i, tp_value in enumerate(tps, 1):
                tp_details.append(f"TP{i}: {tp_value}")
            details_parts.append(", ".join(tp_details))
            details = " | ".join(details_parts)

        elif action == "CLOSE":
            entry_price = "Market Close"
            details = f"OID: {signal_data.get('oid', '')}"

        elif action == "MODIFY":
            new_sl = signal_data.get("new_sl")
            new_tps = signal_data.get("new_tps_csv", "")
            parts = []
            if new_sl: parts.append(f"New SL: {new_sl}")
            if new_tps: parts.append(f"New TPs: {new_tps}")
            details = " | ".join(parts)

        elif action == "MODIFY_TP":
            tp_slot = signal_data.get("tp_slot", 1)
            tp_to = signal_data.get("tp_to")
            details = f"TP{tp_slot} → {tp_to}"

        elif action == "EMERGENCY_CLOSE_ALL":
            entry_price = "EMERGENCY"
            details = "Close all positions"
            side = ""

        self.signalsTable.setItem(row, 0, QTableWidgetItem(time_str))
        self.signalsTable.setItem(row, 1, QTableWidgetItem(action))
        self.signalsTable.setItem(row, 2, QTableWidgetItem(symbol))
        self.signalsTable.setItem(row, 3, QTableWidgetItem(side))
        self.signalsTable.setItem(row, 4, QTableWidgetItem(entry_price))
        self.signalsTable.setItem(row, 5, QTableWidgetItem(details))

        # row tint
        action_colors = {
            "OPEN": QColor(34, 197, 94, 50),
            "CLOSE": QColor(239, 68, 68, 50),
            "MODIFY": QColor(59, 130, 246, 50),
            "MODIFY_TP": QColor(147, 51, 234, 50),
            "EMERGENCY_CLOSE_ALL": QColor(220, 38, 127, 50)
        }
        bg = action_colors.get(action, QColor(156, 163, 175, 50))
        for c in range(6):
            it = self.signalsTable.item(row, c)
            if it:
                it.setBackground(bg)

        self.signalsTable.scrollToBottom()

        # update signals card
        self.signal_count += 1
        self.cardSignals.setValue(str(self.signal_count))

    # ---------- helpers for MainWindow ----------
    def setRunning(self, running: bool) -> None:
        self.startBtn.setEnabled(not running)
        self.stopBtn.setEnabled(running)
        self.pauseBtn.setEnabled(running)
        self.emergBtn.setEnabled(running)
        self.pickBtn.setEnabled(running)

        if running:
            self.cardSystem.setValue("On")
        else:
            self.cardSystem.setValue("Off")

    def updateChannelCount(self, count: int):
        self.channel_count = count
        self.cardChannels.setValue(str(count))

class SettingsPage(QWidget):
    # Signals
    saved = Signal(object)  # AppConfig object
    
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.parent_window = parent
        self._setup_ui()
        
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # --- Connections
        conBox = QGroupBox("Connections", self)
        conLay = QVBoxLayout(conBox)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.apiId = LineEdit(self)
        self.apiId.setPlaceholderText("API ID")
        self.apiId.setText(str(self.cfg.api_id or ""))
        self.apiHash = LineEdit(self)
        self.apiHash.setPlaceholderText("API Hash")
        self.apiHash.setText(self.cfg.api_hash)
        self.phone = LineEdit(self)
        self.phone.setPlaceholderText("Phone (+46...)")
        self.phone.setText(self.cfg.phone)

        grid.addWidget(BodyLabel("Telegram API ID"), 0, 0)
        grid.addWidget(self.apiId, 0, 1)
        grid.addWidget(BodyLabel("Telegram API Hash"), 1, 0)
        grid.addWidget(self.apiHash, 1, 1)
        grid.addWidget(BodyLabel("Phone"), 2, 0)
        grid.addWidget(self.phone, 2, 1)

        conLay.addLayout(grid)
        root.addWidget(conBox)

        # --- MT5 Folder
        mt5Box = QGroupBox(r"MT5  •  MQL5\Files directory", self)
        mt5Lay = QHBoxLayout(mt5Box)
        self.mt5Dir = LineEdit(self)
        self.mt5Dir.setPlaceholderText(r"C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\...\MQL5\Files")
        self.mt5Dir.setText(self.cfg.mt5_files_dir)
        self.browseBtn = PushButton(FluentIcon.FOLDER, "Browse…", self)
        self.autodBtn = PushButton(FluentIcon.SEARCH, "Auto‑detect", self)
        mt5Lay.addWidget(self.mt5Dir, 1)
        mt5Lay.addWidget(self.browseBtn)
        mt5Lay.addWidget(self.autodBtn)
        root.addWidget(mt5Box)

        # --- Sources
        srcBox = QGroupBox("Sources (Telegram chats to watch)", self)
        srcLay = QVBoxLayout(srcBox)
        self.chats = TextEdit(self)
        self.chats.setFixedHeight(110)
        self.chats.setText("\n".join(self.cfg.watch_chats or ["Saved Messages"]))
        srcLay.addWidget(self.chats)
        srcLay.addWidget(QWidget(), 0, Qt.AlignRight)  # spacer
        root.addWidget(srcBox)

        # --- Save
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.saveBtn = PrimaryPushButton(FluentIcon.SAVE, "Save settings", self)
        footer.addWidget(self.saveBtn)
        root.addLayout(footer)
        root.addSpacerItem(QSpacerItem(0, 6, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Auto-detect MT5 folder on startup
        self._auto_detect_mt5_on_startup()
        
        # Connect signals
        self.browseBtn.clicked.connect(self._onBrowse)
        self.autodBtn.clicked.connect(self._onAutoDetect)
        self.saveBtn.clicked.connect(self._onSave)
        
    def _auto_detect_mt5_on_startup(self):
        try:
            cur = Path(self.mt5Dir.text().strip()) if self.mt5Dir.text().strip() else None
            if not cur or not cur.exists():
                cands = find_mt5_files_candidates()
                if cands:
                    self.mt5Dir.setText(str(cands[0]))
                    if self.parent_window:
                        self.parent_window.toast("Detected MT5 folder", str(cands[0]), success=True)
        except Exception:
            pass
            
    def _onBrowse(self):
        d = QFileDialog.getExistingDirectory(self, "Select MT5 MQL5\\Files folder", self.mt5Dir.text() or "")
        if d:
            self.mt5Dir.setText(d)
            
    def _onAutoDetect(self):
        try:
            cands = find_mt5_files_candidates()
            if cands:
                self.mt5Dir.setText(str(cands[0]))
                InfoBar.success("Detected", str(cands[0]), parent=self, position=InfoBarPosition.TOP)
                if self.parent_window and len(cands) > 1:
                    self.parent_window._appendLog("[INFO] Other candidates:")
                    for p in cands[1:]:
                        self.parent_window._appendLog(f"  - {p}")
            else:
                InfoBar.info("Not found", "No MT5 MQL5\\Files folder detected.", parent=self)
        except Exception as e:
            QMessageBox.critical(self, "Auto-detect failed", str(e))
            
    def _onSave(self):
        try:
            cfg = AppConfig(
                api_id=int(self.apiId.text().strip() or "0"),
                api_hash=self.apiHash.text().strip(),
                phone=self.phone.text().strip(),
                mt5_files_dir=self.mt5Dir.text().strip(),
                watch_chats=[x.strip() for x in self.chats.toPlainText().splitlines() if x.strip()],
                session_name="tg_bridge_session",
            )
            save_config(cfg)
            self.cfg = cfg
            self.saved.emit(cfg)
            InfoBar.success("Saved", f"Config written to:\n{CONF_PATH}", parent=self, position=InfoBarPosition.TOP_RIGHT)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        setTheme(Theme.AUTO)
        self.setWindowTitle("Fluent Signal Copier")
        QCoreApplication.setOrganizationName("R4V3N")
        QCoreApplication.setOrganizationDomain("r4v3n.dev")
        self.setMinimumSize(1200, 750)
        self.resize(1320, 860)

        # Icon
        ico_path = resource_path("app.ico")
        if ico_path.exists():
            ico = QIcon(str(ico_path))
            self.setWindowIcon(ico)
            QApplication.instance().setWindowIcon(ico)

        self.cfg = load_config()
        self.thread: Optional[CopierThread] = None

        # Tabs
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs)

        # Pages
        self.dashboard = DashboardPage(self)
        self.settings  = SettingsPage(self.cfg, self)

        self.tabs.addTab(self.dashboard, "Home")
        self.tabs.addTab(self.settings, "Settings")

        # now that pages exist, we can update tracked count
        self._update_tracked_count()

        self._connect_page_signals()

        # UI timer
        self.uiTimer = QTimer(self)
        self.uiTimer.setInterval(2000)
        self.uiTimer.timeout.connect(self._tickUi)
        self.uiTimer.start()

    # ------------ helpers for tracked count ------------
    def _watched_list(self) -> List[str]:
        return [x.strip() for x in self.settings.chats.toPlainText().splitlines() if x.strip()]

    def _update_tracked_count(self):
        self.dashboard.updateChannelCount(len(self._watched_list()))

    def _connect_page_signals(self):
        self.settings.saved.connect(self._onSettingsSaved)
        self.dashboard.startRequested.connect(self.start)
        self.dashboard.stopRequested.connect(self.stop)
        self.dashboard.pauseToggle.connect(self.togglePause)
        self.dashboard.emergRequested.connect(self.emergencyStop)
        self.dashboard.pickChats.connect(self.onPickChats)
        self.dashboard.qualityChanged.connect(self._onQualityChanged)

    def _tickUi(self):
        pass
    
    def _read_last_signal_record(self):
        """Return the last non-empty JSON object from the signal JSONL file, or None."""
        try:
            if not self.thread or not getattr(self.thread, "signal_file", None):
                return None
            path = self.thread.signal_file
            if not path.exists() or path.stat().st_size == 0:
                return None

            # Efficient-ish tail: read from end in chunks until we see a newline
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                buf = bytearray()
                block = 1024
                while pos > 0:
                    read = block if pos >= block else pos
                    pos -= read
                    f.seek(pos, os.SEEK_SET)
                    buf[:0] = f.read(read)
                    if b"\n" in buf:
                        break
                # split and take the last non-empty line
                lines = bytes(buf).splitlines()
                for line in reversed(lines):
                    s = line.strip()
                    if s:
                        try:
                            return json.loads(s.decode("utf-8", "ignore"))
                        except Exception:
                            return None
        except Exception:
            return None
        return None

    # --- UI helpers ---------------------------------------------------
    def toast(self, title: str, content: str, success: bool = False):
        (InfoBar.success if success else InfoBar.info)(
            title, content,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.dashboard
        )

    def _appendLog(self, line: str):
        """Rich log + side-effects for dashboard (signals table & counters)."""
        colors = {
            "ERROR":   "#EF4444",
            "WARN":    "#F59E0B",
            "INFO":    "#3B82F6",
            "NEW":     "#7C3AED",
            "WRITE":   "#10B981",
            "PARSE":   "#F97316",
            "AUTH":    "#06B6D6",
            "RUN":     "#6366F1",
            "SCAN":    "#14B8A6",
            "STOPPED": "#6B7280",
            "COUNTER": "#84CC16",
        }

        aliases = {"WARNING": "WARN", "ERR": "ERROR"}
        msg = strip_ansi(line or "")
        tag = "INFO"

        m = re.match(r'^\[([A-Za-z]+)]\s*(.*)$', msg.strip())
        if m:
            tag = aliases.get(m.group(1).upper(), m.group(1).upper())
            msg = m.group(2)
        else:
            low = msg.lower()
            if "error" in low:
                tag = "ERROR"
            elif "warn" in low:
                tag = "WARN"
                # ---- UI side-effects -------------------------------------------------
                # When SCAN logs "...Cached N chats...", update Channels card with TRACKED count only
        if tag == "SCAN":
            try:
                # More robust pattern matching
                patterns = [
                    r'Cached\s+(\d+)\s+chats',
                    r'Prefetched\s+(\d+)\s+chats', 
                    r'Found\s+(\d+)\s+chats'
                ]
                for pattern in patterns:
                    mm = re.search(pattern, msg, re.IGNORECASE)
                    if mm:
                        # Update with the actual number of TRACKED channels, not total
                        tracked_count = len(self._watched_list())
                        self.dashboard.updateChannelCount(tracked_count)
                        break
            except Exception:
                pass
                # ---- Pretty HTML log -------------------------------------------------
        color = colors.get(tag, "#6B7280")
        badge = (
            f'<span style="background-color:{color};'
            f' color:white; border-radius:8px; padding:1px 8px;'
            f' font-weight:600; font-family:Segoe UI, system-ui, -apple-system;">{escape(tag)}</span>'
        )
        safe_msg = escape(msg).replace("\n", "<br>")
        html = f'<div style="margin:2px 0;">{badge}&nbsp;&nbsp;<span style="white-space:pre-wrap;">{safe_msg}</span></div>'
        self.dashboard.log.append(html)
        self.dashboard.log.moveCursor(QTextCursor.End)
        
    # --- Auth UI ------------------------------------------------------
    def _showAuthBox(self, mode: str):
        if not hasattr(self, "dashboard"):
            return
        if mode == "code":
            self.dashboard.authPrompt.setText("Enter the code you received:")
            self.dashboard.authEdit.setPlaceholderText("Telegram code (e.g. 12345)")
            self.dashboard.authEdit.setEchoMode(self.dashboard.authEdit.EchoMode.Normal)
            self._authMode = "code"
        else:
            self.dashboard.authPrompt.setText("Enter your Telegram 2FA password:")
            self.dashboard.authEdit.setPlaceholderText("Password")
            self.dashboard.authEdit.setEchoMode(self.dashboard.authEdit.EchoMode.Password)
            self._authMode = "password"
        self.dashboard.authEdit.clear()
        self.dashboard.authBox.setVisible(True)
        self.dashboard.authEdit.setFocus()

    def _hideAuthBox(self):
        if not hasattr(self, "dashboard"):
            return
        # idempotent: safe to call even if already hidden
        try:
            self.dashboard.authBox.setVisible(False)
            self.dashboard.authEdit.clear()
        except Exception:
            pass
        
    def closeEvent(self, event):
        try:
            self.stop()
            if self.thread:
                self.thread.wait(3000)  # wait up to 3s to finish
        except Exception:
            pass
        event.accept()

    # --- Event handlers ----------------------------------------------
    def _onSettingsSaved(self, cfg):
        self.cfg = cfg
        self._update_tracked_count()

    def _onQualityChanged(self, v: int):
        if self.thread:
            self.thread.set_quality_threshold(v)

    @Slot(bool)
    def _onRunningState(self, running: bool):
        self.dashboard.setRunning(running)

    # --- Main actions -------------------------------------------------
    def start(self):
        # Save settings before starting
        self.settings._onSave()
        self.cfg = load_config()
        self._update_tracked_count()

        if not self.cfg.api_id or not self.cfg.api_hash:
            QMessageBox.warning(self, "Missing", "Enter API ID and API Hash in Settings.")
            self.tabs.setCurrentWidget(self.settings)
            return

        self.thread = CopierThread(self.cfg, self)
        self.thread.logLine.connect(self._appendLog)
        self.thread.notify.connect(lambda t, m: self.toast(t, m))
        self.thread.authCodeNeeded.connect(self._onAuthCodeNeeded)
        self.thread.authPwdNeeded.connect(self._onAuthPwdNeeded)
        self.thread.runningState.connect(self._onRunningState)
        self.thread.dialogsReady.connect(self.onDialogsReady)
        self.thread.signalProcessed.connect(self._add_to_table)

        self.thread.set_quality_threshold(self.dashboard.qualitySlider.value())
        self.thread.start()
        self._onRunningState(True)

    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None
        self._hideAuthBox()
        self._onRunningState(False)

    @Slot()
    def _onAuthCodeNeeded(self):
        self._showAuthBox("code")

    @Slot()
    def _onAuthPwdNeeded(self):
        self._showAuthBox("password")

    def onPickChats(self):
        if not self.thread:
            self.toast("Start first", "Sign in, then pick chats.")
            return
        self.toast("Loading…", "Fetching chats (first time only).")
        self.thread.getDialogs()

    @Slot(list)
    def onDialogsReady(self, chats: List[dict]):
        if not chats:
            self.toast("No chats found", "Are you logged in to the right account?")
            return

        # Build a case-insensitive watch set from Settings
        current = [x.strip() for x in self.settings.chats.toPlainText().splitlines() if x.strip()]
        watch_set = {s.lower() for s in current}

        dlg = ChatPickerDialog(chats, self, watch_set=watch_set)
        if dlg.exec():
            picks = dlg.selected_entries()
            if not picks:
                return
            merged = current[:]
            seen = {x.lower() for x in current}
            for p in picks:
                if p.lower() not in seen:
                    merged.append(p)
                    seen.add(p.lower())

            self.settings.chats.setText("\n".join(merged))
            self._update_tracked_count()
            self.toast("Added", f"Added {len(picks)} chat(s).", success=True)

    def togglePause(self):
        if not self.thread:
            return

        paused = not self.thread.is_paused()
        self.thread.set_paused(paused)

        # no log lines anymore
        self.toast("Intake", "Paused" if paused else "Resumed", success=True)
        self.dashboard.pauseBtn.setText("Resume" if paused else "Pause")

    def _add_to_table(self, record: dict):
        """Compat shim for Dashboard methods."""
        if hasattr(self.dashboard, "addSignalToTable"):
            self.dashboard.addSignalToTable(record)
        elif hasattr(self.dashboard, "add_signal_to_table"):
            self.dashboard.add_signal_to_table(record)

    def emergencyStop(self):
        if not self.thread or not self.thread.signal_file:
            self.toast("Not running", "Start first")
            return
        gid = self.thread._next_id()  # use the same counter file
        rec = {
            "action": "EMERGENCY_CLOSE_ALL",
            "id": str(gid),
            "t": int(time.time()),
            "source": "GUI",
            "source_id": "",
            "confirm": "YES"
        }
        with self.thread.signal_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._appendLog("[WRITE] EMERGENCY_CLOSE_ALL dispatched")
        self.toast("Emergency STOP", "Close-all signal sent.", success=True)

        # Add to signals table (compat)
        self._add_to_table(rec)

# =====================================================================
# App Entry Point
# =====================================================================
if __name__ == "__main__":
    import multiprocessing, os, sys
    multiprocessing.freeze_support()
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())