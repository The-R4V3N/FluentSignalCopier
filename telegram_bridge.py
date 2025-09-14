# Licensed under the Fluent Signal Copier Limited Use License v1.0
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

# telegram_bridge.py — Telegram → MT5 bridge (robust parser + global counter)
# Python 3.11+.  pip install telethon python-dotenv
import asyncio, json, time, re, os, sys
from pathlib import Path
from turtle import title
from telethon import TelegramClient, events
from persistence import HistoryStore, NewSignal

# =====================================================================
# Helpers (normalization, numbers, env)
# =====================================================================

try:
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit("Install python-dotenv: pip install python-dotenv")

def load_env():
    """Load .env from common locations (cwd, script dir, exe dir when frozen)."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    if getattr(sys, "frozen", False):  # if bundled via PyInstaller
        candidates.insert(0, Path(sys.executable).resolve().parent / ".env")

    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)
            print(f"[.env] loaded: {p}")
            break
    else:
        load_dotenv(override=False)

def normalize_spaces(s: str) -> str:
    """Normalize weird Unicode spaces and fullwidth symbols commonly seen in TG posts."""
    if not s:
        return s
    return (
        s.replace('\u00A0', ' ')  # NBSP
         .replace('\u202F', ' ')  # narrow NBSP
         .replace('\u2007', ' ')  # figure space
         .replace('\ufeff', ' ')  # BOM
         .replace('＠', '@')      # fullwidth '@'
    )

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

def num(s: str):
    """
    Robust numeric parser:
    - Tolerates thousands separators (',' or ' ' or NBSP) and apostrophes.
    - Handles decimal separator '.' or ','.
    """
    if s is None:
        return None
    x = s.strip()
    x = (x.replace(' ', '')
          .replace('\u00A0', '')
          .replace('\u202F', '')
          .replace('\u2007', '')
          .replace("’", "")
          .replace("'", ""))
    if ',' in x and '.' in x:
        # assume commas are thousands
        x2 = x.replace(',', '')
    else:
        if ',' in x:
            parts = x.split(',')
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                x2 = ''.join(parts)          # thousands commas
            else:
                x2 = x.replace(',', '.')     # decimal comma
        else:
            x2 = x
    try:
        return float(x2)
    except Exception:
        return None

load_env()

# =====================================================================
# Config & State
# =====================================================================

TELEGRAM_API_ID       = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH     = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE        = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_SESSION_NAME = os.getenv("SESSION_NAME", "tg_bridge_session")

# WATCH_CHATS: support JSON or comma/semicolon list
wc_json = os.getenv("WATCH_CHATS_JSON", "").strip()
if wc_json:
    WATCH_CHATS = json.loads(wc_json)
else:
    raw = os.getenv("WATCH_CHATS", "Saved Messages")
    WATCH_CHATS = [s.strip() for s in raw.replace(",", ";").split(";") if s.strip()]

# MT5 file drop
MT5_FILES_DIR = os.getenv("MT5_FILES_DIR", str(Path.home() / "MQL5" / "Files"))
SIGNAL_FILE   = Path(MT5_FILES_DIR) / "telegram_signals.jsonl"
COUNTER_FILE  = Path(MT5_FILES_DIR) / "signal_counter.txt"

# Per-chat context
RECENT_SYMBOL_BY_CHAT: dict[str, str] = {}
LAST_OPEN_OID: dict[tuple[str, str], int] = {}
SEEN_OPEN: set[tuple[str, int]] = set()
# === Persistence (SQLite) ===
store = HistoryStore()  # one shared connection (WAL), safe for concurrent reads
# Track the latest signal_id per (channel, symbol) so we can attach edits/close
LAST_OPEN_SIGID: dict[tuple[str, str], int] = {}

# Global counter
GLOBAL_COUNTER = 0

def load_counter():
    global GLOBAL_COUNTER
    try:
        if COUNTER_FILE.exists():
            GLOBAL_COUNTER = int(COUNTER_FILE.read_text().strip())
            print(f"[COUNTER] Loaded: {GLOBAL_COUNTER}")
        else:
            GLOBAL_COUNTER = 0
            print("[COUNTER] Start at 0")
    except Exception as e:
        GLOBAL_COUNTER = 0
        print(f"[COUNTER] Load error: {e} -> 0")

def save_counter():
    try:
        COUNTER_FILE.write_text(str(GLOBAL_COUNTER))
    except Exception as e:
        print(f"[COUNTER] Save error: {e}")

def get_next_id():
    global GLOBAL_COUNTER
    GLOBAL_COUNTER += 1
    save_counter()
    return GLOBAL_COUNTER

# =====================================================================
# Aliases & Regex
# =====================================================================

ALIASES = {
    # Metals
    "XAUSD": "XAUUSD", "XAU": "XAUUSD", "GOLD": "XAUUSD",
    "XAG": "XAGUSD", "SILVER": "XAGUSD",

    # Indices
    "NAS100": "NAS100", "US100": "NAS100", "USTEC": "NAS100",
    "US30": "DJ30", "DJ30": "DJ30", "DOW": "DJ30",
    "SPX500": "SPX500", "SP500": "SPX500", "US500": "SPX500",
    "GER40": "DE40", "DAX": "DE40", "DAX40": "DE40",
    "UK100": "UK100", "FTSE100": "UK100",
    "JP225": "JP225", "NIKKEI": "JP225",

    # Oil
    "USOIL": "XTIUSD", "USOUSD": "XTIUSD", "WTI": "XTIUSD", "OIL": "XTIUSD", "XTIUSD": "XTIUSD",
    "BRENT": "XBRUSD", "UKOIL": "XBRUSD", "XBRUSD": "XBRUSD",
}
OIL_BASE_SYMBOLS = {"XTIUSD", "XBRUSD"}
OIL_SMALL_LOTS = 0.01

def normalize_symbol(s: str) -> str:
    return ALIASES.get((s or "").strip().upper(), (s or "").strip().upper())

SYM_RE = re.compile(
    r'(?:#)?\b([A-Z]{6}|[A-Z]{2,5}\d{2,3}|XAU|XAUSD|GOLD|SILVER|XAG|USOIL|USOUSD|WTI|OIL|XTIUSD|UKOIL|BRENT|XBRUSD|SPX500|SP500|US500|USTEC|US30|DJ30)\b',
    re.I
)
SIDE_RE = re.compile(r'\b(BUY|SELL)\b', re.I)
ENTRY_LINE_RE = re.compile(r'^\s*(?:ENTER|ENTRY)\b.*?(-?\d+(?:[.,]\d+)?)\b', re.I)

# SL / TP patterns (line-oriented)
SL_PATTERNS = [
    re.compile(r'\b(?:STOP\s*LOSS|STOPLOSS)\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\bSL\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'^\s*SL\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]
SL_RE = re.compile(
    r'(?im)^\s*(?:SL|S/L|STOP\s*LOSS|STOPLOSS)\s*(?:@|:)?\s*([+\-]?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*$'
)
TP_PATTERNS = [
    # "TP @ 198.600", "TP@198.600"  (accept full decimals; no bare TPn without price)
    re.compile(r'\bTP\d*\s*@\s*(-?\d+(?:[.,]\d+)?)\b', re.I),

    # "TP1 198.600", "TP 198.600", "TP1 = 198.600", "TP1 -> 198.600"
    re.compile(r'\bTP\d*\s*(?:at|=|->)?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),

    # line starts with TP… followed by a price
    re.compile(r'^\s*TP\d*\s*@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

# Very tolerant whole-text SL fallback (handles NBSP / commas)
SL_FALLBACK = re.compile(r'\b(?:stop\s*loss|stoploss|sl)\b[^0-9-]{0,30}([0-9][\d.,]*)', re.I | re.S)

# Break-even hint
BE_HINT_RE = re.compile(r'\bSL\s*entry\s*at\s*TP\s*1\b', re.I)

# Risk controls
RISK_PCT_RE      = re.compile(r'\brisk\s*(\d+(?:[.,]\d+)?)\s*%?\b', re.I)
HALF_RISK_RE     = re.compile(r'\bHALF\s*RISK\b', re.I)
DOUBLE_RISK_RE   = re.compile(r'\bDOUBLE\s*RISK\b', re.I)
QUARTER_RISK_RE  = re.compile(r'\b(?:QUARTER|1/4)\s*RISK\b', re.I)
SMALL_LOTS_RE    = re.compile(r'\b(SMALL\s*LOTS|USE\s*SMALL\s*LOTS)\b', re.I)

# Close phrases (expanded)
CLOSE_ANY_RE = re.compile(
    r'\b(?:close(?!\s+to)\b|close\s+all|close\s+at\s+market|close\s+now|flatten|exit\s+now|liquidate)\b',
    re.I
)
CLOSE_WITH_SYM_RE  = re.compile(r'\bclose\b.*?\b([A-Z]{3,6}|[A-Z]{2,5}\d{2,3}|xau|gold|us30|dj30|nas100|spx500|de40|xbrusd|xtiusd|usoil|wti|ukoil|brent)\b', re.I)

# Pending & inline header patterns
HEADER_PENDING_FULL_RE = re.compile(
    r'^\s*(?:#)?\s*(?P<sym>[A-Z]{3,6}|[A-Z]{2,5}\d{2,3})\s+(?P<side>BUY|SELL)\s+(?P<ptype>LIMIT|STOP)\s*@?\s*(?P<price>-?\d+(?:[.,]\d+)?)\b',
    re.I | re.M
)
HEADER_INLINE_PRICE_RE = re.compile(
    r'^\s*(?:#)?\s*(?P<sym>[A-Z]{3,6}|[A-Z]{2,5}\d{2,3})\s+(?P<side>BUY|SELL)\s+@?\s*(?P<price>-?\d+(?:[.,]\d+)?)\b',
    re.I | re.M
)

# TP move variants
TP_MOVE_PATTERNS = [
    re.compile(r'\b(?:move|set|raise|adjust|shift)\s*tp\s*(\d{1,2})\s*(?:to|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\btp\s*(\d{1,2})\s*(?:moved\s*to|now\s*(?:at|to)?|=|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\boriginal\s*tp\s*(\d{1,2})\b.*?\btp\s*\1\s*(?:moved\s*to|now\s*(?:at|to)?|=|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I | re.S),
    re.compile(r'\btp\s*(?:moved\s*to|now\s*(?:at|to)?|=|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\b(?:move|set|raise|adjust|shift)\s*tp\s*(?:to|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

UPDATED_PREFIX_RE = re.compile(r'^\s*updated\b', re.I)
CORR_SL_TYP0_RE   = re.compile(r'\b(?:typo|correct|correction).*\bSL\b.*?(?:was\s*)?(-?\d+(?:[.,]\d+)?).*(?:not|now)\s*(-?\d+(?:[.,]\d+)?)', re.I)
CORR_SL_TO_RE     = re.compile(r'\b(edit(?:ing)?|update(?:d)?)\b.*\bSL\b.*\bto\b\s*(-?\d+(?:[.,]\d+)?)', re.I)
SYMBOL_HINT_RE    = re.compile(r'\b(gold|xauusd|xau|nas100|us100|ustec|dj30|us30|dow|spx500|sp500|us500|de40|dax|ger40|gbpjpy|xbrusd|xtiusd|usoil|wti|ukoil|brent)\b', re.I)

# Skip signals explicitly marked risky (matches "Risky" and "Verry Risky"/"Very Risky")
RISKY_RE = re.compile(r'\b(?:ver+y\s+)?risky\b', re.I)

# Execution / intent cues
NOW_MARKET_RE   = re.compile(r'\b(?:BUY\s+NOW|SELL\s+NOW|AT\s+MARKET|@\s*MARKET)\b', re.I)
PENDING_PAIR_RE = re.compile(r'\b(BUY|SELL)\s+(LIMIT|STOP)\b', re.I)


# =====================================================================
# Parsing helpers
# =====================================================================

def parse_tp_moves(text: str):
    t = normalize_spaces(text).strip()
    moves = []
    for pat in TP_MOVE_PATTERNS:
        for m in pat.finditer(t):
            price_str = m.group(m.lastindex)
            to_val = num(price_str)
            if to_val is None:
                continue
            slot = 1
            if m.lastindex >= 1:
                g1 = m.group(1)
                if g1 and re.fullmatch(r'\d{1,2}', g1):
                    slot = int(g1)
            moves.append({"slot": slot, "to": to_val})
    if not moves:
        return None
    ms = SYM_RE.search(t)
    sym = normalize_symbol(ms.group(1)) if ms else ""
    return {"symbol": sym, "moves": moves}

def _sanitize_price(v):
    if v is None:
        return None
    # Negative prices are almost never intended in FX/CFD signals;
    # many channels write "SL- 95.34" with a hyphen as a separator.
    return abs(v)

def try_extract_sl(line: str):
    line = normalize_spaces(line)
    for pat in SL_PATTERNS:
        m = pat.search(line)
        if m:
            v = num(m.group(1))
            if v is not None:
                return _sanitize_price(v)
    return None

def try_extract_tp(line: str):
    line = normalize_spaces(line)
    for pat in TP_PATTERNS:
        m = pat.search(line)
        if m:
            v = num(m.group(1))
            if v is not None:
                return _sanitize_price(v)
    return None

def parse_correction(text: str):
    t = normalize_spaces(text).strip()
    low = t.lower()
    is_update_like = bool(UPDATED_PREFIX_RE.search(t)) or any(w in low for w in ("typo","edit","updated","correction"))
    if not is_update_like:
        return None

    sym = None
    ms = SYMBOL_HINT_RE.search(t)
    if ms:
        sym = normalize_symbol(ms.group(1))

    new_sl = None
    m = CORR_SL_TYP0_RE.search(t)
    if m:
        new_sl = num(m.group(2))
    else:
        m = CORR_SL_TO_RE.search(t)
        if m:
            new_sl = num(m.group(1))

    new_tps = []
    pb = parse_block_style(t)
    if pb:
        if pb.get("sl") is not None: new_sl = pb["sl"]
        if pb.get("tps"): new_tps = pb["tps"]
        if not sym and pb.get("symbol"): sym = pb["symbol"]

    if new_sl is not None or new_tps:
        return {"symbol": sym, "new_sl": new_sl, "new_tps": new_tps}
    return None

def parse_close(text: str):
    t = normalize_spaces(text)
    if not CLOSE_ANY_RE.search(t):
        return None
    m = CLOSE_WITH_SYM_RE.search(t)
    if m:
        return normalize_symbol(m.group(1))
    return ""  # sentinel -> use last symbol in this chat

# =====================================================================
# Block parser
# =====================================================================

def parse_block_style(text: str):
    t = normalize_spaces(text)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    if not lines:
        return None

    side = None
    symbol = None
    entry = None
    sl = None
    tps = []
    be_on_tp = 1 if BE_HINT_RE.search(t) else 0

    # NEW: default to MARKET unless we see LIMIT/STOP explicitly
    order_type = "MARKET"

    # 1) Header with LIMIT/STOP and price
    m = HEADER_PENDING_FULL_RE.search(t)
    if m:
        symbol = normalize_symbol(m.group('sym'))
        side   = m.group('side').upper()
        entry  = num(m.group('price'))
        ptype  = (m.group('ptype') or "").upper()
        if ptype in ("LIMIT", "STOP"):
            order_type = ptype  # LIMIT or STOP
    else:
        # 2) Header with inline price (BUY @ price) – does NOT imply pending
        m2 = HEADER_INLINE_PRICE_RE.search(t)
        if m2:
            symbol = normalize_symbol(m2.group('sym'))
            side   = m2.group('side').upper()
            entry  = num(m2.group('price'))

    # 3) Fallback scan for side/symbol
    for ln in lines:
        if side is None:
            md = SIDE_RE.search(ln)
            if md:
                side = md.group(1).upper()
        if symbol is None:
            ms = SYM_RE.search(ln)
            if ms:
                symbol = normalize_symbol(ms.group(1))

    # 4) Entry via "ENTER/ENTRY ..."
    if entry is None:
        for ln in lines:
            m = ENTRY_LINE_RE.search(ln)
            if m:
                entry = num(m.group(1))
                if entry is not None:
                    break
                
    # 5) --- Risky filter ---
    if RISKY_RE.search(t):
        print("[SKIP] Risky signal ignored")
        return None

    # 6) SL & TPs (unchanged)
    for ln in lines:
        low = ln.lower()
        if any(w in low for w in ('sl','stop','stoploss')):
            if 'entry' in low:
                continue
            v = try_extract_sl(ln)
            if v is not None and sl is None:
                sl = v
                continue
        if 'tp' in low:
            v = try_extract_tp(ln)
            if v is not None:
                tps.append(v)
                continue

    if sl is None:
        m = SL_FALLBACK.search(t)
        if m:
            v = num(m.group(1))
            if v is not None:
                sl = v

    if not side or not symbol:
        return None

    # 7)--- Global cues override / confirm order_type
    pm = PENDING_PAIR_RE.search(t)
    if pm:
        # any “… LIMIT/STOP” anywhere → pending
        order_type = pm.group(2).upper()  # LIMIT or STOP
        # side can be filled from this too if missing
        if side is None:
            side = pm.group(1).upper()
    elif NOW_MARKET_RE.search(t):
        order_type = "MARKET"

    # 8) # --- Risk & lots overrides ---
    risk_percent = None
    m = RISK_PCT_RE.search(t)
    if m:
        risk_percent = num(m.group(1))               # "risk 0.75" or "risk 75%"
        # If author writes "risk 75%", you can convert to 0.75 if you prefer:
        # if risk_percent and risk_percent > 2: risk_percent = risk_percent / 100.0
    elif HALF_RISK_RE.search(t):     risk_percent = 0.5
    elif DOUBLE_RISK_RE.search(t):   risk_percent = 2.0
    elif QUARTER_RISK_RE.search(t):  risk_percent = 0.25

    lots_override = None
    if SMALL_LOTS_RE.search(t) and normalize_symbol(symbol) in OIL_BASE_SYMBOLS:
        lots_override = OIL_SMALL_LOTS

    # IMPORTANT: if MARKET, do not let 'entry' accidentally cause a pending.
    entry_ref = entry
    if order_type == "MARKET":
        entry = None

    return {
        "side": side,
        "symbol": symbol,
        "entry": entry,             # None for MARKET
        "entry_ref": entry_ref,     # keep reference for logs
        "sl": sl,
        "tps": tps,
        "be_on_tp": be_on_tp,
        "risk_percent": risk_percent,
        "lots": lots_override,
        "order_type": order_type    # MARKET | LIMIT | STOP
    }

# =====================================================================
# Runner
# =====================================================================

async def main():
    load_counter()
    SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(TELEGRAM_SESSION_NAME, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start()

    watch_titles = {str(x).strip().lower() for x in WATCH_CHATS}
    want_saved   = any(x in ("me","saved messages","self") for x in watch_titles)
    me           = await client.get_me()
    my_id        = me.id

    print("=== TELEGRAM BRIDGE (robust decimals + SL fallback) ===")
    print("Watching:", ", ".join(WATCH_CHATS))
    print("Writing to:", SIGNAL_FILE)
    print(f"Global counter: {GLOBAL_COUNTER}")
    print("=======================================================")

    @client.on(events.NewMessage)
    async def handler(event):
        # Filter chats
        title = ""
        is_ok = False
        if event.is_private and event.chat_id == my_id and want_saved:
            title = "Saved Messages"; is_ok = True
        else:
            chat = await event.get_chat()
            title = (getattr(chat, "title", None) or getattr(chat, "username", None) or "").strip()
            if title.lower() in watch_titles:
                is_ok = True
        if not is_ok:
            return

        raw = event.raw_text or ""
        txt = normalize_spaces(raw)
        print(f"\n[NEW] {title}")
        print(f"[RAW] {repr(txt)}")

        # CLOSE?
        close_sym = parse_close(txt)
        if close_sym is not None:
            sym = close_sym if close_sym else RECENT_SYMBOL_BY_CHAT.get(title)
            if not sym:
                print("[CLOSE] No symbol context; skip")
                return
            oid = LAST_OPEN_OID.get((title, sym), 0)
            gid = get_next_id()
            rec = {
                "action": "CLOSE",
                "id": str(gid),
                "t": int(time.time()),
                "source": title,
                "symbol": sym,
                "oid": str(oid),
                "original_event_id": str(event.id)
            }
            with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=True) + "\n")
            print(f"[SAVED] CLOSE {sym} (oid={oid}, gid={gid})")

            # Persist close intent against the last open signal for this channel/symbol
            sig_id = LAST_OPEN_SIGID.get((title, sym))
            if sig_id:
                store.mark_event(sig_id, "MANUAL_CLOSE", note="Close via Telegram", ts_ms=int(time.time()*1000))
            return

        # MODIFY_TP?
        tp_mod = parse_tp_moves(txt)
        if tp_mod:
            sym = tp_mod.get("symbol") or RECENT_SYMBOL_BY_CHAT.get(title)
            if not sym:
                print("[MODIFY_TP] No symbol context; skip")
                return
            for mv in (tp_mod.get("moves") or []):
                tp_slot = int(mv.get("slot") or 1)
                tp_to   = mv.get("to")
                gid = get_next_id()
                rec = {
                    "action": "MODIFY_TP",
                    "id": str(gid),
                    "t": int(time.time()),
                    "source": title,
                    "symbol": sym,
                    "tp_slot": tp_slot,
                    "tp_to": tp_to,
                    "original_event_id": str(event.id)
                }
                with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=True) + "\n")
                print(f"[SAVED] MODIFY_TP {sym} TP{tp_slot}->{tp_to} (gid={gid})")

                # Persist TP adjustment
                sig_id = LAST_OPEN_SIGID.get((title, sym))
                if sig_id:
                    store.mark_event(sig_id, "MODIFY", price=tp_to, note=f"TP{tp_slot} -> {tp_to}", ts_ms=int(time.time()*1000))
            return

        # MODIFY?
        corr = parse_correction(txt)
        if corr:
            sym = corr["symbol"] or RECENT_SYMBOL_BY_CHAT.get(title)
            if not sym:
                print("[MODIFY] No symbol context; skip")
                return
            gid = get_next_id()
            rec = {
                "action": "MODIFY",
                "id": str(gid),
                "t": int(time.time()),
                "source": title,
                "symbol": sym,
                "new_sl": corr["new_sl"],
                "new_tps_csv": ",".join(str(x) for x in (corr["new_tps"] or [])) if corr["new_tps"] else "",
                "original_event_id": str(event.id)
            }
            with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=True) + "\n")
            print(f"[SAVED] MODIFY {sym} SL->{corr['new_sl']} TPs->{rec['new_tps_csv']} (gid={gid})")

            # Persist SL/TP corrections
            sig_id = LAST_OPEN_SIGID.get((title, sym))
            if sig_id:
                note_bits = []
                if corr["new_sl"] is not None: note_bits.append(f"SL -> {corr['new_sl']}")
                if corr["new_tps"]:           note_bits.append(f"TPs -> {','.join(map(str, corr['new_tps']))}")
                store.mark_event(sig_id, "MODIFY", note="; ".join(note_bits), ts_ms=int(time.time()*1000))
            return

        # Dedupe OPEN per (title, message id)
        if (title, int(event.id)) in SEEN_OPEN:
            print("[DEDUP] OPEN already handled")
            return

        # OPEN?
        parsed = parse_block_style(txt)
        if not parsed:
            print("[PARSE] No valid signal")
            return
        
        # Persist the *signal* itself (independent of trade fill)
        sig_id = store.add_signal(NewSignal(
            ts_ms=int(time.time()*1000),
            channel=title,
            message_id=str(event.id),
            symbol=sym,
            side=parsed["side"],
            sl=parsed["sl"],
            entry=parsed.get("entry_ref"),   # keep original header price for reference
            tps=parsed.get("tps") or [],
            raw_text=txt.strip()
        ))
        LAST_OPEN_SIGID[(title, sym)] = sig_id  # remember for subsequent edits/close

        sym = parsed["symbol"]
        RECENT_SYMBOL_BY_CHAT[title] = sym
        risk = 1.0 if parsed["risk_percent"] is None else parsed["risk_percent"]

        gid = get_next_id()
        rec = {
            "action": "OPEN",
            "id": str(gid),
            "t": int(time.time()),
            "source": title,
            "raw": txt.strip(),
            "side": parsed["side"],
            "symbol": sym,
            "entry": parsed["entry"],                      # None for MARKET
            "entry_ref": parsed.get("entry_ref"),          # just reference/logging
            "order_type": parsed.get("order_type", "MARKET"),
            "sl": parsed["sl"],
            "tp": None,
            "risk_percent": risk,
            "lots": parsed["lots"],
            "tps_csv": ",".join(str(x) for x in (parsed["tps"] or [])) if parsed["tps"] else "",
            "be_on_tp": int(parsed["be_on_tp"] or 0),
            "original_event_id": str(event.id)
        }

        print(f"[RECORD] {json.dumps(rec, indent=2)}")
        LAST_OPEN_OID[(title, sym)] = gid
        SEEN_OPEN.add((title, int(event.id)))

        with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")
        print(f"[SAVED] OPEN {sym} {parsed['side']} [{parsed.get('order_type','MARKET')}] SL={parsed['sl']} TPs={rec['tps_csv']} (gid={gid})")

    @client.on(events.MessageEdited)
    async def edited(event):
        print("[EDIT] processing as new…")
        await handler(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
