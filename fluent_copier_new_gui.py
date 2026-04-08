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

# Licensed under the Attribution-NonCommercial-ShareAlike 4.0 International
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

import os, re, sys, json, time, asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable
from html import escape
from persistence import HistoryStore

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
    CaptionLabel, InfoBar, InfoBarPosition, FluentIcon, setTheme, Theme, InfoBadge,
    ComboBox
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

def normalize_price(num_str: str) -> float | None:
    """
    Convert strings like '109,840', '1,234.56', '1.234,56', '3391', '3391,5' to float.
    Assumes:
      - If both '.' and ',' appear, ',' are thousands and '.' is decimal (US style), OR
        '.' are thousands and ',' is decimal (EU style). We detect by final separator block length.
      - If only one of them appears, decide by rightmost group length (<=2 -> decimal).
    """
    s = num_str.strip()
    # Remove weird spaces
    s = s.replace('\u00A0', ' ').replace(' ', '')

    if ',' in s and '.' in s:
        # Decide decimal separator by last occurrence
        last_comma = s.rfind(',')
        last_dot   = s.rfind('.')
        if last_comma > last_dot:
            # comma as decimal, dots as thousands: 1.234,56
            s = s.replace('.', '')
            s = s.replace(',', '.')
        else:
            # dot as decimal, commas as thousands: 1,234.56
            s = s.replace(',', '')
    elif ',' in s:
        # Only comma present -> decide by group length after last comma
        right = s.split(',')[-1]
        if 1 <= len(right) <= 2:
            # comma is decimal
            s = s.replace('.', '')  # any stray dots were thousands
            s = s.replace(',', '.')
        else:
            # comma is thousands
            s = s.replace(',', '')
    elif '.' in s:
        # Only dot present -> decide by group length after last dot
        right = s.split('.')[-1]
        if not (1 <= len(right) <= 2):
            # dot is thousands
            s = s.replace('.', '')

    try:
        return float(s)
    except ValueError:
        return None

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

def _find_tps(text: str) -> list[float]:
    vals = []
    for m in TP_RE.finditer(text):
        v = _num(m.group(1))
        if v is not None:
            vals.append(_sanitize_price(v))
    # unique + ascending order
    return sorted(set(vals))

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

    # Your broker’s dotted crypto symbols:
    "BTCUSD": "BTCUSD", "BTC": "BTCUSD",
    "ETHUSD": "ETHUSD", "ETH": "ETHUSD",
    "SOLUSD": "SOLUSD", "SOL": "SOLUSD",
    "LTCUSD": "LTCUSD", "LTC": "LTCUSD",
    "XRPUSD": "XRPUSD", "XRP": "XRPUSD",
    # add more as needed
}

# Broker-specific forced suffix when signals omit it
BROKER_FORCED_SUFFIX = {
    "XAUUSD": "+",   # make bare XAUUSD become XAUUSD+
    # add more if needed, e.g. "XAGUSD": "m"
}

# Core symbols/aliases we understand before suffixes
CORE_SYM = (
    r'(?:'
    r'[A-Z]{6}'              # EURUSD, XAUUSD, etc.
    r'|[A-Z]{2,5}\d{2,3}'    # GER40, US500, NAS100, etc.
    r'|XAU|XAUSD|GOLD|SILVER|XAG'
    r'|USOIL|WTI|OIL|XTIUSD|UKOIL|BRENT|XBRUSD'
    r'|SPX500|SP500|US500|USTEC|US30|DJ30'
    r')'
)

# Suffix could be ".r", "-ecn", "_pro", "+", or bare trailing letters like "m"
BROKER_SUFFIX = r'(?:[.\-_][A-Za-z0-9]{1,10}|\+|[A-Za-z]{1,7})'

# Use lookarounds, not \b, so trailing '+' / '.' are kept
SYM_TOKEN = rf'(?<!\w)({CORE_SYM}(?:{BROKER_SUFFIX})?)(?=$|\s|[^\w])'
SYM_RE = re.compile(SYM_TOKEN, re.I)

# For splitting inside normalize_symbol
_SPLIT_SYM = re.compile(rf'^({CORE_SYM})({BROKER_SUFFIX})?$', re.I)

# Accept 1) plain numbers  2) numbers with grouped thousands (space, NBSP, narrow NBSP, figure space, comma, apostrophe)
NUM_TOKEN = r"-?\d{1,3}(?:[ \u00A0\u202F\u2007,'’]\d{3})+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?"

SIDE_RE = re.compile(r'\b(BUY|SELL|LONG|SHORT)\b', re.I)
ENTRY_RE = re.compile(r'^\s*(?:ENTER|ENTRY)\b.*?(' + NUM_TOKEN + r')\b', re.I)

# Accepts: SL / S/L / STOPLOSS / STOP LOSS / STOPPLOSS with @, :, =, -, en/em dash
SL_RES = re.compile(
    r'(?im)\b(?:SL|S/L|STOPP?[\s\-]*LOSS)\b\s*(?:@|:|=|-|–|—)?\s*([0-9][0-9\s.,]*)\b'
)

# Accepts: TP, TP1, TP2 … with @, :, ;, =, ->, -, en/em dash; works anywhere in the line
TP_RE = re.compile(
    r'(?im)\bTP\d*\b\s*(?:@|:|;|=|->|-|–|—)?\s*([0-9][0-9\s.,]*)\b'
)

# Order type patterns
HEADER_PENDING_FULL_RE = re.compile(
    rf'^\s*(?:#)?\s*(?P<sym>{CORE_SYM}(?:{BROKER_SUFFIX})?)\s+'
    rf'(?P<side>BUY|SELL)\s+(?P<ptype>LIMIT|STOP)\b.*?@?\s*(?P<price>{NUM_TOKEN})\b',
    re.I | re.M
)

HEADER_LONGSHORT_ENTRY_RE = re.compile(
    rf'^\s*(?:#)?\s*(?P<sym>{CORE_SYM}(?:{BROKER_SUFFIX})?)\s+'
    r'(?P<side>LONG|SHORT)\s+ENTRY\s*\(\s*(?P<ptype>MARKET|LIMIT|STOP)\s*\)\s*'
    r'[:@-]?\s*(?P<price>' + NUM_TOKEN + r')\b',
    re.I | re.M
)

HEADER_INLINE_PRICE_RE = re.compile(
    rf'^\s*(?:#)?\s*(?P<sym>{CORE_SYM}(?:{BROKER_SUFFIX})?)\s+'
    rf'(?P<side>BUY|SELL)\s+@?\s*(?P<price>{NUM_TOKEN})\b',
    re.I | re.M
)

NOW_MARKET_RE = re.compile(r'\b(BUY|SELL|LONG|SHORT)\s+(?:NOW|AT\s+MARKET|@\s*MARKET)\b', re.I)
PENDING_PAIR_RE = re.compile(r'\b(BUY|SELL|LONG|SHORT)\s+(LIMIT|STOP)\b', re.I)
BE_HINT_RE = re.compile(r'\bSL\s*entry\s*at\s*TP\s*1\b', re.I)
RISK_PCT_RE = re.compile(r'\brisk\s*(\d+(?:[.,]\d+)?)\s*%?\b', re.I)
CLOSE_ANY_RE = re.compile(
    r'\b(?:close(?!\s+to)\b|close\s+all|close\s+at\s+market|close\s+now|flatten|exit\s+now|liquidate)\b',
    re.I
)

# TP move patterns
TP_MOVE_PATTERNS = [
    re.compile(r'\b(?:move|set|raise|adjust|shift)\s*tp\s*(\d{1,2})\s*(?:to|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    # OLD (too broad): r'\btp\s*(\d{1,2})\s*(?:moved\s*to|now\s*(?:at|to)?|->)\s*(-?\d+(?:[.,]\d+)?)\b'
    re.compile(r'\btp\s*(\d{1,2})\s*(?:moved\s*to|now\s*(?:at|to)?)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

# add next to RISK_PCT_RE
RISK_PCT_RE = re.compile(r'\brisk\s*(\d+(?:[.,]\d+)?)\s*%?\b', re.I)
RISK_X_RE   = re.compile(r'\b(\d+(?:[.,]\d+)?)\s*x\s*risk\b|\brisk\s*(\d+(?:[.,]\d+)?)\s*x\b', re.I)

_FRACTIONAL_RISK_WORDS = {
    "half": 0.5, "½": 0.5,
    "quarter": 0.25, "¼": 0.25,
    "third": 1/3, "⅓": 1/3,
    "two thirds": 2/3, "⅔": 2/3,
}

def apply_forced_suffix(sym: str) -> str:
    """
    If a symbol matches a base in BROKER_FORCED_SUFFIX and has no broker suffix,
    append the broker's required suffix. If it already has any suffix, leave it.
    """
    s = (sym or "").strip().upper()
    if not s:
        return s

    # treat these as suffix indicators
    suffix_starters = {"+", ".", "-", "_"}

    for base, suff in BROKER_FORCED_SUFFIX.items():
        if s == base:
            return base + suff
        # If something like XAUUSDm or XAUUSD.cash is already there, keep it.
        if s.startswith(base) and len(s) > len(base) and s[len(base)] in suffix_starters:
            return s
    return s

def normalize_symbol(s: str) -> str:
    s = (s or "").strip().upper()
    # first map aliases (GOLD -> XAUUSD, etc.)
    core = ALIASES.get(s, s)
    # then force the broker suffix if the core has none
    return apply_forced_suffix(core)

def _try_sl(text: str) -> Optional[float]:
    m = SL_RES.search(text)
    if not m:
        return None
    v = _num(m.group(1))   # <-- normalization happens here (your point #3)
    return _sanitize_price(v)

def _try_tp(line: str) -> Optional[float]:
    m = TP_RE.search(line)
    if not m:
        return None
    v = _num(m.group(1))
    return _sanitize_price(v) if v is not None else None

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

# def _parse_risk_percent(text: str) -> Optional[float]:
#     """Return a numeric risk value from common phrasings.
#     Interprets bare numbers as % (1 -> 1%), words like 'half risk' as multipliers (0.5)."""
#     t = text or ""
#     # 1) explicit %/number after 'risk'
#     m = RISK_PCT_RE.search(t)
#     if m:
#         v = _num(m.group(1))
#         if v is not None:
#             return float(v)  # treat as percentage value

#     # 2) '0.5x risk' / 'risk 0.5x'
#     m = RISK_X_RE.search(t)
#     if m:
#         v = _num(m.group(1) or m.group(2))
#         if v is not None:
#             return float(v)  # multiplier (0.5, 2, etc.)

#     # 3) worded fractions: 'half risk', 'risk half', 'quarter risk'
#     low = t.lower()
#     for word, val in _FRACTIONAL_RISK_WORDS.items():
#         if re.search(fr'\b{word}\s*risk\b', low) or re.search(fr'\brisk\s*{word}\b', low):
#             return float(val)

#     # 4) simple fractions: '1/2 risk', 'risk 1/3'
#     m = re.search(r'\b(\d+)\s*/\s*(\d+)\s*risk\b|\brisk\s*(\d+)\s*/\s*(\d+)\b', low)
#     if m:
#         a = _num(m.group(1) or m.group(3))
#         b = _num(m.group(2) or m.group(4))
#         if a and b and b != 0:
#             return float(a / b)

#     return None

def _parse_risk_fields(text: str) -> dict[str, Any]:
    """
    Return structured risk fields:
      - risk_percent: float | None (e.g., 1.5 means 1.5%)
      - risk_multiplier: float | None (e.g., 0.5, 2.0)
      - risk_label: str | None ("half", "quarter", "double", "1/3", etc.)
    Rules:
      - "risk 2%" or "risk 2" (ambiguous) → percent
      - "0.5x risk" or "risk 0.5x" → multiplier
      - "half/quarter/double/twice/third/two thirds" → multiplier + label
      - "risk 1/3" or "1/3 risk" → multiplier + label "1/3"
    """
    t = text or ""
    out = {"risk_percent": None, "risk_multiplier": None, "risk_label": None}

    # 1) explicit %/number after 'risk'
    m = RISK_PCT_RE.search(t)
    if m:
        v = _num(m.group(1))
        if v is not None:
            out["risk_percent"] = float(v)
            return out

    # 2) '0.5x risk' / 'risk 0.5x'
    m = RISK_X_RE.search(t)
    if m:
        v = _num(m.group(1) or m.group(2))
        if v is not None:
            out["risk_multiplier"] = float(v)
            return out

    # 3) worded fractions
    low = t.lower()
    WORDS = dict(_FRACTIONAL_RISK_WORDS)
    # add a couple of common synonyms
    WORDS.update({"double": 2.0, "twice": 2.0})
    for word, val in WORDS.items():
        if re.search(fr'\b{word}\s*risk\b', low) or re.search(fr'\brisk\s*{word}\b', low):
            out["risk_multiplier"] = float(val)
            out["risk_label"] = word
            return out

    # 4) simple fractions like 1/3
    m = re.search(r'\b(\d+)\s*/\s*(\d+)\s*risk\b|\brisk\s*(\d+)\s*/\s*(\d+)\b', low)
    if m:
        a = _num(m.group(1) or m.group(3))
        b = _num(m.group(2) or m.group(4))
        if a and b and b != 0:
            val = float(a / b)
            out["risk_multiplier"] = val
            out["risk_label"] = f"{int(a)}/{int(b)}"
            return out

    # 5) No match
    return out

def parse_message(text: str) -> Optional[Dict[str, Any]]:
    """Parse a message into a signal dictionary."""
    t = _normalize_spaces(text).strip()
    low = t.lower()

    # Skip signals marked as risky
    if "risky" in low:   # catches both "Risky" and "Verry Risky"
        return None

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
        # New: "BTCUSD Long Entry (market|limit|stop): 116474"
        mL = HEADER_LONGSHORT_ENTRY_RE.search(t)
        if mL:
            symbol = normalize_symbol(mL.group('sym'))
            side = mL.group('side').upper()          # LONG/SHORT here
            entry = _num(mL.group('price'))
            ptype = (mL.group('ptype') or "").upper()
            order_type = ("LIMIT" if ptype == "LIMIT"
                          else "STOP" if ptype == "STOP"
                          else "MARKET")
        else:
            m2 = HEADER_INLINE_PRICE_RE.search(t)
            if m2:
                symbol = normalize_symbol(m2.group('sym'))
                side = m2.group('side').upper()
                entry = _num(m2.group('price'))
    
        # Check for order type overrides
        pm = PENDING_PAIR_RE.search(t)
        if pm and order_type == "MARKET":
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

    if sl is None:
        sl = _try_sl(t)   # search the whole message once

    # TP: switch to full-text collection
    tps = _find_tps(t)

    if not (side and symbol):
        return None

    # Risk parsing
    # risk = _parse_risk_percent(t) legacy code
    _risk = _parse_risk_fields(t)

    # Normalize LONG/SHORT to BUY/SELL for downstream logic
    if side in ("LONG", "SHORT"):
        side = "BUY" if side == "LONG" else "SELL"

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
    "tp": (tps[0] if tps else None),   # ← add this line
    "be_on_tp": be_on_tp,
   # "risk": risk, legacy code
    "risk_percent": _risk.get("risk_percent"),
    "risk_multiplier": _risk.get("risk_multiplier"),
    "risk_label": _risk.get("risk_label"),
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

        # normalize the incoming watch set once
        def _canon(s: str) -> str:
            return (s or "").strip().lower()

        self.watch_set = { _canon(x) for x in (watch_set or set()) }

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
            q = _canon(self.search.text())
            only = self.onlyWatched.isChecked()

            for item in self._all_items:
                raw = item.data(Qt.UserRole)["raw"]
                title    = _canon(raw.get("title"))
                username = _canon(raw.get("username"))
                chat_id  = _canon(str(raw.get("id", "")))

                # all identifiers we consider for matching
                idents = {i for i in {
                    title,
                    username,
                    f"@{username}" if username else "",
                    chat_id
                } if i}

                # does the row match the text box?
                text_match = (not q) or any(q in ident for ident in idents)

                # is this chat in the watched list?
                in_watch = bool(self.watch_set & idents)

                # final visibility
                item.setHidden(not (text_match and (not only or in_watch)))

        self.search.textChanged.connect(apply_filters)
        self.onlyWatched.toggled.connect(apply_filters)
        apply_filters()  # initial filter on open

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
        self.counter_file = mt5_dir / "Fluent_signal_counter.txt"
        self.heartbeat_file = mt5_dir / "Fluent_heartbeat.txt"
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
                        if "risky" in (txt or "").lower():
                            self.logLine.emit("[SKIP] Risky signal ignored")
                        else:
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
                            "lots": None,
                            "be_on_tp": int(p.get("be_on_tp") or 0),
                            # risk fields will be injected conditionally below
                            "gid": str(gid),
                            "original_event_id": str(event.id),
                            "confidence": conf,
                        }
                        # Inject risk only if explicitly parsed
                        rp = p.get("risk_percent")
                        rm = p.get("risk_multiplier")
                        rl = p.get("risk_label")

                        if rp is not None:
                            rec["risk_percent"] = float(rp)
                        if rm is not None:
                            rec["risk_multiplier"] = float(rm)
                        if rl:
                            rec["risk_label"] = str(rl)

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
                        return

                # schedule once and keep the handle for shutdown
               # self._hb_task = loop.create_task(_hb_writer())

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
    """Small card with a title, big value, and optional status dot."""
    def __init__(self, title: str, value: str = "—", show_dot: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumWidth(180)

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

        # Cards area (left)
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

        # Actions column (right)
        actions = QVBoxLayout()
        actions.setSpacing(10)
        self.startBtn = PrimaryPushButton("START", self)
        self.stopBtn  = PushButton("STOP", self); self.stopBtn.setEnabled(False)
        self.pauseBtn = PushButton(FluentIcon.PAUSE, "Pause", self); self.pauseBtn.setEnabled(False)
        self.emergBtn = PrimaryPushButton("EMERGENCY STOP", self); self.emergBtn.setEnabled(False)
        for b in (self.startBtn, self.stopBtn, self.pauseBtn, self.emergBtn):
            b.setMinimumHeight(34)
            actions.addWidget(b)

        self.pickBtn = PushButton(FluentIcon.PEOPLE, "Pick chats…", self)
        self.pickBtn.setEnabled(False)
        actions.addWidget(self.pickBtn)
        actions.addStretch(1)

        # Wrap actions in a widget to control min width
        actionsWidget = QWidget(self)
        actionsWidget.setLayout(actions)
        actionsWidget.setMinimumWidth(220)
        actionsWidget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        top.addWidget(actionsWidget)

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
                entry_price = f"{order_type} @ {entry}" if entry is not None else order_type

            sl = signal_data.get('sl')
            tps = signal_data.get('tps', []) or []

            parts = []
            if sl is not None:
                parts.append(f"SL: {sl}")
            if tps:
                parts.append(", ".join(f"TP{i}: {v}" for i, v in enumerate(tps, 1)))
            details = " | ".join(parts)

            rp = signal_data.get('risk_percent')
            rm = signal_data.get('risk_multiplier')
            rl = signal_data.get('risk_label')

            if rp is not None:
                parts.append(f"Risk: {rp}%")
            elif rm is not None:
                # Pretty-print known labels when available
                if rl:
                    parts.append(f"Risk: {rl} ({rm}x)")
                else:
                    parts.append(f"Risk: {rm}x")

        elif action == "CLOSE":
            entry_price = "Market Close"
            details = f"OID: {signal_data.get('oid', '')}"

        elif action == "MODIFY":
            new_sl = signal_data.get("new_sl")
            new_tps = signal_data.get("new_tps_csv", "")
            parts = []
            if new_sl is not None:
                parts.append(f"New SL: {new_sl}")
            if new_tps:
                parts.append(f"New TPs: {new_tps}")
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

class HistoryPage(QWidget):
    """Trading History & Channel Performance"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent

        # raw events buffer (bounded)
        self.max_events = 2000
        self.events: list[dict] = []

        # per-channel stats
        self.stats: dict[str, dict] = {}  # channel -> metrics dict

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # --- Channel selector (filter) + period selector ---
        row = QHBoxLayout()
        row.addWidget(SubtitleLabel("Trading History"))
        row.addStretch(1)
        row.addWidget(BodyLabel("Filter by channel:"))
        self.channelFilter = LineEdit(self)
        self.channelFilter.setPlaceholderText("Type to filter (leave empty for all)")
        row.addWidget(self.channelFilter, 0)
        row.addWidget(BodyLabel("Period:"))
        self.periodCombo = ComboBox(self)
        self.periodCombo.addItems(["All Time", "30 Days", "7 Days", "Today"])
        self.periodCombo.setCurrentIndex(0)
        row.addWidget(self.periodCombo)
        root.addLayout(row)

        # --- PnL total label ---
        pnl_row = QHBoxLayout()
        pnl_row.addWidget(BodyLabel("Total P&L:"))
        self.pnlLabel = BodyLabel("$0.00")
        pnl_row.addWidget(self.pnlLabel)
        pnl_row.addStretch(1)
        root.addLayout(pnl_row)

        # --- Channel performance table ---
        root.addWidget(SubtitleLabel("Channel Performance"))
        self.summaryTable = QTableWidget(self)
        self.summaryTable.setColumnCount(7)
        self.summaryTable.setHorizontalHeaderLabels(
            ["Channel", "Signal Score", "Win %", "Opens", "Closes", "Avg Conf", "Last Signal"]
        )
        self.summaryTable.verticalHeader().setVisible(False)
        self.summaryTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.summaryTable.horizontalHeader().setStretchLastSection(True)
        self.summaryTable.setSortingEnabled(True)
        root.addWidget(self.summaryTable)

        # --- History table ---
        root.addWidget(SubtitleLabel("Recent Signals / Trades"))
        self.historyTable = QTableWidget(self)
        self.historyTable.setColumnCount(8)
        self.historyTable.setHorizontalHeaderLabels(
            ["Time", "Channel", "Action", "Symbol", "Side", "Price", "Details", "Profit"]
        )
        self.historyTable.verticalHeader().setVisible(False)
        self.historyTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.historyTable.horizontalHeader().setStretchLastSection(True)
        self.historyTable.setAlternatingRowColors(True)
        root.addWidget(self.historyTable, 1)
        self.refreshBtn = PushButton("Refresh from DB", self)
        row.addWidget(self.refreshBtn)

        # wire filter and period selector
        self.channelFilter.textChanged.connect(self._refresh_tables)
        self.periodCombo.currentIndexChanged.connect(self._on_period_changed)

    # ---------- public API ----------
    def _since_ms_for_period(self) -> int | None:
        """Convert current period combo selection to a UTC epoch ms cutoff."""
        text = self.periodCombo.currentText()
        if text == "All Time":
            return None
        now = int(time.time() * 1000)
        if text == "Today":
            t = time.localtime()
            midnight = time.mktime(time.struct_time(
                (t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, t.tm_isdst)
            ))
            return int(midnight * 1000)
        elif text == "7 Days":
            return now - 7 * 86400 * 1000
        elif text == "30 Days":
            return now - 30 * 86400 * 1000
        return None

    def _on_period_changed(self):
        if hasattr(self, "_current_store") and self._current_store is not None:
            self.hydrate_from_store(self._current_store)

    def hydrate_from_store(self, store: HistoryStore, limit: int = 600):
        """Fill Channel Performance + Recent Signals from the persistent DB."""
        self._current_store = store
        since_ms = self._since_ms_for_period()
        try:
            # 1) Channel performance (period-filtered)
            self.stats.clear()
            self.summaryTable.setRowCount(0)
            for row in store.channel_stats_since(since_ms):
                ch = row.get("channel") or ""
                wins = int(row.get("wins") or 0)
                losses = int(row.get("losses") or 0)
                total = int(row.get("signals_total") or 0)
                known = wins + losses
                win_rate = (wins / known * 100.0) if known else None

                # Populate self.stats so _refresh_summary can display Win % correctly
                # after filter changes or live events trigger a table rebuild.
                st = self.stats.setdefault(ch, {
                    "opens": 0, "closes": 0, "mods": 0,
                    "win": 0, "loss": 0, "draw": 0,
                    "conf_sum": 0.0, "conf_n": 0,
                    "last_ts": 0,
                })
                st["win"] = wins
                st["loss"] = losses
                st["opens"] = total

                r = self.summaryTable.rowCount()
                self.summaryTable.insertRow(r)
                vals = [
                    ch,
                    f"{(win_rate if win_rate is not None else 0.0):.1f}%" if known >= 3 else "—",  # “Signal score” proxy
                    f"{win_rate:.1f}%" if win_rate is not None else "—",
                    str(total),
                    "—",          # closes count (optional unless you persist closes in DB->results)
                    "—",          # avg confidence (GUI-only metric)
                    "—",          # last signal time (optional: add a view for last ts if you want)
                ]
                for c, v in enumerate(vals):
                    self.summaryTable.setItem(r, c, QTableWidgetItem(v))

            # Update PnL total label
            pnl = store.total_pnl(since_ms)
            self.pnlLabel.setText(f"${pnl:,.2f}")

            # 2) Recent signals
            self.historyTable.setRowCount(0)
            recent = store.recent_signals(limit=limit)
            for s in reversed(recent):  # oldest first so the table builds up chronologically
                rec = {
                    "t": int((s.get("ts_ms") or 0) / 1000),
                    "source": s.get("channel", ""),
                    "action": s.get("status", "NEW").upper(),  # DB status -> action-ish
                    "symbol": s.get("symbol", ""),
                    "side": s.get("side", "") or "",
                    "entry": s.get("entry", None),
                    "tps": s.get("tps", []),
                    "sl": s.get("sl", None),
                    "order_type": "MARKET" if s.get("entry") in (None, "") else "LIMIT",  # best-effort
                }
                # Reuse existing row builder
                self._append_history_row(self._coerce_db_to_ui(rec))
            self.summaryTable.sortItems(1, Qt.DescendingOrder)
        except Exception:
            pass

    def _coerce_db_to_ui(self, rec: dict) -> dict:
        """Map DB-like signal dict to the UI’s expected keys so _append_history_row works."""
        out = {
            "t": rec.get("t", int(time.time())),
            "source": rec.get("source", ""),
            "action": rec.get("action", "OPEN"),
            "symbol": rec.get("symbol", ""),
            "side": rec.get("side", ""),
            "order_type": rec.get("order_type", "MARKET"),
            "entry": rec.get("entry"),
            "entry_ref": rec.get("entry_ref"),
            "sl": rec.get("sl"),
            "tps": rec.get("tps") or [],
            "new_sl": rec.get("new_sl"),
            "new_tps_csv": rec.get("new_tps_csv", ""),
        }
        return out

    def ingest_existing_file(self, path: Path, max_lines: int = 1200):
        """Load recent JSONL records from file at startup."""
        if not path or not path.exists():
            return
        try:
            # Read tail quickly
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                chunk = min(size, 512 * 1024)
                f.seek(size - chunk)
                data = f.read().decode("utf-8", "ignore")
            lines = [ln.strip() for ln in data.splitlines() if ln.strip()][-max_lines:]
            for ln in lines:
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                self.on_signal(rec, update_ui=False)
            self._refresh_tables()
        except Exception:
            pass

    def on_signal(self, rec: dict, update_ui: bool = True):
        """Feed a single new signal/trade record."""
        # keep bounded buffer
        self.events.append(rec)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

        ch = rec.get("source", "") or ""
        act = rec.get("action", "")
        conf = float(rec.get("confidence", 0) or 0)
        ts = int(rec.get("t", time.time()))
        sym = rec.get("symbol") or ""
        side = rec.get("side") or ""
        profit = rec.get("profit")  # may be provided by EA on CLOSE; optional

        # init channel bucket
        st = self.stats.setdefault(ch, {
            "opens": 0, "closes": 0, "mods": 0,
            "win": 0, "loss": 0, "draw": 0,
            "conf_sum": 0.0, "conf_n": 0,
            "last_ts": 0
        })

        if act == "OPEN":
            st["opens"] += 1
            st["conf_sum"] += conf
            st["conf_n"] += 1
        elif act == "CLOSE":
            st["closes"] += 1
            # If EA writes profit into the record we can compute win/loss
            if isinstance(profit, (int, float)):
                if profit > 0:
                    st["win"] += 1
                elif profit < 0:
                    st["loss"] += 1
                else:
                    st["draw"] += 1
        elif act in ("MODIFY", "MODIFY_TP"):
            st["mods"] += 1

        st["last_ts"] = max(st["last_ts"], ts)

        # append to history table immediately if desired
        if update_ui:
            self._append_history_row(rec)
            self._refresh_summary()

    # ---------- UI population ----------
    def _append_history_row(self, rec: dict):
        if not self._passes_filter(rec):
            return
        row = self.historyTable.rowCount()
        self.historyTable.insertRow(row)

        ts = int(rec.get("t", time.time()))
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        ch = rec.get("source", "")
        act = rec.get("action", "")
        sym = rec.get("symbol", "")
        side = rec.get("side", "")
        price = ""
        details = ""
        profit = rec.get("profit", "")

        if act == "OPEN":
            ot = rec.get("order_type", "MARKET")
            entry = rec.get("entry")
            ref = rec.get("entry_ref")
            if ot == "MARKET":
                price = f"MARKET{f' ({ref})' if ref else ''}"
            else:
                price = f"{ot} @ {entry if entry is not None else ''}"
            parts = []
            if rec.get("sl") is not None: parts.append(f"SL {rec['sl']}")
            tps = rec.get("tps") or []
            if tps: parts.append(", ".join(f"TP{i+1} {v}" for i, v in enumerate(tps)))
            details = " | ".join(parts)
        elif act == "CLOSE":
            price = "Market Close"
            details = f"OID: {rec.get('oid','')}"
        elif act == "MODIFY":
            ns = rec.get("new_sl")
            nt = rec.get("new_tps_csv", "")
            details = " | ".join(x for x in [f"New SL {ns}" if ns is not None else "", f"TPs {nt}" if nt else ""] if x)
        elif act == "MODIFY_TP":
            details = f"TP{rec.get('tp_slot',1)} → {rec.get('tp_to')}"

        for c, val in enumerate([time_str, ch, act, sym, side, price, details, str(profit) if profit not in (None, "") else ""]):
            self.historyTable.setItem(row, c, QTableWidgetItem(val))

        # optional row tint by action
        tint = {
            "OPEN": QColor(34, 197, 94, 40),
            "CLOSE": QColor(239, 68, 68, 40),
            "MODIFY": QColor(59, 130, 246, 40),
            "MODIFY_TP": QColor(147, 51, 234, 40),
            "EMERGENCY_CLOSE_ALL": QColor(220, 38, 127, 40),
        }.get(act)
        if tint:
            for c in range(self.historyTable.columnCount()):
                it = self.historyTable.item(row, c)
                if it: it.setBackground(tint)

        # cap rows
        while self.historyTable.rowCount() > 400:
            self.historyTable.removeRow(0)
        self.historyTable.scrollToBottom()

    def _refresh_summary(self):
        # rebuild summary from self.stats (fast; small)
        self.summaryTable.setRowCount(0)
        filt = (self.channelFilter.text() or "").strip().lower()

        for ch, s in self.stats.items():
            if filt and filt not in ch.lower():
                continue

            opens = s["opens"]; closes = s["closes"]
            wins, losses, draws = s["win"], s["loss"], s["draw"]
            conf_avg = (s["conf_sum"] / s["conf_n"]) if s["conf_n"] else 0.0

            # Win rate if we have profit outcomes
            known = wins + losses
            win_rate = (wins / known * 100.0) if known else None

            # Signal Score
            if known >= 3:
                score = win_rate
            else:
                score = conf_avg  # proxy until we have outcomes

            last_ts = s["last_ts"]
            last_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_ts)) if last_ts else "—"

            row = self.summaryTable.rowCount()
            self.summaryTable.insertRow(row)
            vals = [
                ch,
                f"{score:.1f}%" if score is not None else "—",
                f"{win_rate:.1f}%" if win_rate is not None else "—",
                str(opens),
                str(closes),
                f"{conf_avg:.1f}",
                last_str
            ]
            for c, v in enumerate(vals):
                self.summaryTable.setItem(row, c, QTableWidgetItem(v))

        self.summaryTable.sortItems(1, Qt.DescendingOrder)

    def _refresh_tables(self):
        # rebuild both tables according to filter
        self.summaryTable.setRowCount(0)
        self.historyTable.setRowCount(0)
        self._refresh_summary()
        for rec in self.events[-600:]:
            self._append_history_row(rec)

    def _passes_filter(self, rec: dict) -> bool:
        f = (self.channelFilter.text() or "").strip().lower()
        if not f:
            return True
        return f in (rec.get("source", "") or "").lower()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        setTheme(Theme.AUTO)
        self.setWindowTitle("Fluent Signal Copier")
        QCoreApplication.setOrganizationName("R4V3N")
        QCoreApplication.setOrganizationDomain("r4v3n.dev")
        self.setMinimumSize(960, 600) # Main Window size
        self.resize(1000, 650)
        self.store = HistoryStore()   # durable history / channel stats
        self._last_seen_ea_key = None

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
        self.history   = HistoryPage(self)
        self.settings  = SettingsPage(self.cfg, self)

        self.tabs.addTab(self.dashboard, "Home")
        self.tabs.addTab(self.history, "History")
        self.tabs.addTab(self.settings, "Settings")

        # Fill History tab from persistent store at boot
        self.history.hydrate_from_store(self.store, limit=600)

        # Connection between pages
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
        # Only when thread has created/selected the file location
        path = None
        if self.thread and getattr(self.thread, "signal_file", None):
            path = self.thread.signal_file
        else:
            # best-effort guess (same default as EA/GUI)
            path = Path((self.settings.mt5Dir.text() or "").strip()) / "Fluent_signals.jsonl"
        if not path or not path.exists():
            return

        rec = self._read_last_signal_record()
        if not rec:
            return

        # Only ingest EA-emitted results (avoid duplicating our own OPEN/MODIFY writes)
        src = (rec.get("source") or "").upper()
        if src != "EA":
            return

        # Deduplicate by a compact tuple key
        key = (rec.get("action"), rec.get("t"), rec.get("symbol"),
               rec.get("oid"), rec.get("gid"), rec.get("profit"))
        if key == self._last_seen_ea_key:
            return
        self._last_seen_ea_key = key

        # Feed both tables
        try:
            self.history.on_signal(rec, update_ui=True)
            if hasattr(self.dashboard, "addSignalToTable"):
                self.dashboard.addSignalToTable(rec)
        except Exception:
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

        msg = strip_ansi(line or "").strip()
        tag = "INFO"
        m = re.match(r'^\[([A-Za-z]+)]\s*(.*)$', msg)
        if m:
            tag = aliases.get(m.group(1).upper(), m.group(1).upper())
            msg = m.group(2)

        # side-effect: keep the tracked count in sync on SCAN lines
        if tag == "SCAN":
            try:
                self.dashboard.updateChannelCount(len(self._watched_list()))
            except Exception:
                pass

        color = colors.get(tag, "#6B7280")
        badge = (
            f'<span style="background-color:{color}; color:white; border-radius:8px;'
            f' padding:1px 8px; font-weight:600; font-family:Segoe UI, system-ui;">{escape(tag)}</span>'
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

      # --- Auth actions from Dashboard ---------------------------------
    def _submitAuth(self):
        """Called by DashboardPage when the user hits Submit in the auth box."""
        try:
            if not self.thread:
                self.toast("Not running", "Start first.")
                return

            text = (self.dashboard.authEdit.text() or "").strip()
            if not text:
                self.toast("Missing", "Enter the code or password.")
                return

            mode = getattr(self, "_authMode", "code")
            if mode == "code":
                self.thread.set_auth_code(text)
                self._appendLog("[AUTH] Code submitted")
            else:
                self.thread.set_auth_password(text)
                self._appendLog("[AUTH] Password submitted")

            self._hideAuthBox()
        except Exception as e:
            self._appendLog(f"[ERROR] auth submit: {e}")

    def _cancelAuth(self):
        """Hide the auth box without submitting anything."""
        self._appendLog("[AUTH] Input canceled")
        self._hideAuthBox()
        
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
        self.thread.signalProcessed.connect(self.history.on_signal)

        # If there is already a signals file, load recent history so the tab isn’t empty
        if getattr(self.thread, "signal_file", None):
            self.history.ingest_existing_file(self.thread.signal_file)

        self.thread.set_quality_threshold(self.dashboard.qualitySlider.value())
        self.thread.start()

        # Refresh History tab from DB right after starting (in case bridge already persisted new signals)
        self.history.hydrate_from_store(self.store, limit=600)

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