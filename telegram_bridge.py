# telegram_bridge.py - Multi-Format Signal Parser with Global Counter
# Python 3.11+.  pip install telethon
import asyncio, json, time, re, os, sys
from pathlib import Path
from telethon import TelegramClient, events

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
        # final fallback: default search up the tree
        load_dotenv(override=False)

load_env()

# ====== USER CONFIG ======
TELEGRAM_API_ID       = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH     = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE        = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_SESSION_NAME = os.getenv("SESSION_NAME", "tg_bridge_session")

# WATCH_CHATS: support JSON list or a ;/,-separated string
import json
wc_json = os.getenv("WATCH_CHATS_JSON", "").strip()
if wc_json:
    WATCH_CHATS = json.loads(wc_json)
else:
    raw = os.getenv("WATCH_CHATS", "Saved Messages")
    WATCH_CHATS = [s.strip() for s in raw.replace(",", ";").split(";") if s.strip()]

# Path to your MT5 Data Folder -> MQL5\Files (exact!):
MT5_FILES_DIR = os.getenv("MT5_FILES_DIR", str(Path.home() / "MQL5" / "Files"))
SIGNAL_FILE   = Path(MT5_FILES_DIR) / "telegram_signals.jsonl"
COUNTER_FILE  = Path(MT5_FILES_DIR) / "signal_counter.txt"

# Remember which original Telegram messages we've already opened for (per chat)
SEEN_OPEN = set()  # tuples of (source, original_event_id)

# ====== GLOBAL COUNTER MANAGEMENT ======
GLOBAL_COUNTER = 0

def load_counter():
    """Load the global counter from file"""
    global GLOBAL_COUNTER
    try:
        if COUNTER_FILE.exists():
            with open(COUNTER_FILE, 'r') as f:
                GLOBAL_COUNTER = int(f.read().strip())
                print(f"[COUNTER] Loaded counter: {GLOBAL_COUNTER}")
        else:
            GLOBAL_COUNTER = 0
            print(f"[COUNTER] Starting fresh counter: {GLOBAL_COUNTER}")
    except Exception as e:
        print(f"[COUNTER] Error loading counter: {e}, starting from 0")
        GLOBAL_COUNTER = 0

def save_counter():
    """Save the global counter to file"""
    try:
        with open(COUNTER_FILE, 'w') as f:
            f.write(str(GLOBAL_COUNTER))
    except Exception as e:
        print(f"[COUNTER] Error saving counter: {e}")

def get_next_id():
    """Get next global ID and save counter"""
    global GLOBAL_COUNTER
    GLOBAL_COUNTER += 1
    save_counter()
    return GLOBAL_COUNTER

# ====== OIL-SPECIFIC SETTINGS ======
OIL_SMALL_LOTS = 0.01     # forced lot when "SMALL LOTS" appears for oil symbols

# ====== SYMBOL ALIASES ======
ALIASES = {
    # Metals
    "XAUSD": "XAUUSD", "XAU": "XAUUSD", "GOLD": "XAUUSD",
    "XAG": "XAGUSD", "SILVER": "XAGUSD",
    
    # Indices - FIXED for your broker
    "NAS100": "NAS100", "US100": "NAS100", "USTEC": "NAS100",
    "US30": "DJ30", "DJ30": "DJ30", "DOW": "DJ30",
    "SPX500": "SPX500", "SP500": "SPX500", "US500": "SPX500",
    "GER40": "DE40", "DAX": "DE40", "DAX40": "DE40",
    "UK100": "UK100", "FTSE100": "UK100",
    "JP225": "JP225", "NIKKEI": "JP225",
    
    # Oil (WTI/Brent)
    "USOIL": "XTIUSD", "WTI": "XTIUSD", "OIL": "XTIUSD", "XTIUSD": "XTIUSD",
    "USOUSD": "XTIUSD",
    "BRENT": "XBRUSD", "UKOIL": "XBRUSD", "XBRUSD": "XBRUSD",
}
OIL_BASE_SYMBOLS = {"XTIUSD", "XBRUSD"}

def normalize_symbol(s: str) -> str:
    s = s.strip().upper()
    return ALIASES.get(s, s)

# ====== REGEX PATTERNS - MULTIPLE FORMATS (FIXED: Support comma and dot decimals) ======
# Symbol: allow optional leading '#'
SYM_RE = re.compile(
    r'(?:#)?\b('
    r'[A-Z]{6}'
    r'|[A-Z]{2,5}\d{2,3}'
    r'|XAU|XAUSD|GOLD|SILVER|XAG'
    r'|USOIL|USOUSD|WTI|OIL|XTIUSD|UKOIL|BRENT|XBRUSD'
    r'|SPX500|SP500|US500|USTEC|US30|DJ30'
    r')\b', re.I
)

SIDE_RE = re.compile(r'\b(BUY|SELL)\b', re.I)
# FIXED: Support both comma and dot decimals
ENTRY_LINE_RE = re.compile(r'^\s*(?:ENTER|ENTRY)\b.*?(-?\d+(?:[.,]\d+)?)\b', re.I)

# Multiple SL patterns for different formats (FIXED: Support comma and dot decimals)
SL_PATTERNS = [
    # "Stoploss @ 1.96800" / "Stop loss @ 1.96800" / "STOPLOSS @ 116,580"
    re.compile(r'\b(?:STOP\s*LOSS|STOPLOSS)\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    # "SL @ 1.96800" / "SL 1.96800" / "SL @ 116,580"
    re.compile(r'\bSL\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    # Line starting with "SL"
    re.compile(r'^\s*SL\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

# Multiple TP patterns for different formats (FIXED: Support comma and dot decimals)
TP_PATTERNS = [
    # "TP @ 1.95300" / "TP1 @ 1.95300" / "TP @ 120,500"
    re.compile(r'\bTP\d*\s*@\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    # "TP 1.95300" / "TP1 1.95300" / "TP 120,500"
    re.compile(r'\bTP\d*\s+(-?\d+(?:[.,]\d+)?)\b', re.I),
    # Line starting with "TP"
    re.compile(r'^\s*TP\d*\s*@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

# --- TP move variations (very tolerant) ---
# Handles:
#  - "Move TP4 to 3399", "TP4 moved to 3399", "TP 4 -> 3399", "TP4 now 3399"
#  - "Original TP4 3382 Hit ... TP4 moved to 3399 for now"
#  - "TP moved to 3399", "Move TP to 3399"  (no index -> default TP1)
TP_MOVE_PATTERNS = [
    # e.g., "Move TP4 to 3399", "Set TP3 to 1,234.5", "Raise TP2 -> 3401"
    re.compile(r'\b(?:move|set|raise|adjust|shift)\s*tp\s*(\d{1,2})\s*(?:to|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    # e.g., "TP4 moved to 3399", "TP 4 now 3399", "TP4 now at 3399"
    re.compile(r'\btp\s*(\d{1,2})\s*(?:moved\s*to|now\s*(?:at|to)?|=|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    # e.g., "Original TP4 3382 Hit ... TP4 moved to 3399"
    re.compile(r'\boriginal\s*tp\s*(\d{1,2})\b.*?\btp\s*\1\s*(?:moved\s*to|now\s*(?:at|to)?|=|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I | re.S),
    # e.g., "TP moved to 3399" (no index); default to TP1
    re.compile(r'\btp\s*(?:moved\s*to|now\s*(?:at|to)?|=|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    # e.g., "Move TP to 3399" (no index); default to TP1
    re.compile(r'\b(?:move|set|raise|adjust|shift)\s*tp\s*(?:to|->)\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]

def parse_tp_moves(text: str):
    """
    Return dict {'symbol': str|'' , 'moves': [{'slot': int, 'to': float}, ...]} if we see any TP move,
    else None. If symbol not present in message, return '' so caller can fill from chat context.
    """
    t = text.strip()
    moves = []
    for pat in TP_MOVE_PATTERNS:
        for m in pat.finditer(t):
            # price is always the last capturing group in the pattern
            price_str = m.group(m.lastindex)
            to_val = convert_decimal(price_str)
            if to_val is None:
                continue

            # If a TP index is present (group 1 is digits), use it; otherwise default to TP1
            slot = 1
            if m.lastindex >= 1:
                g1 = m.group(1)
                if g1 and re.fullmatch(r'\d{1,2}', g1):
                    slot = int(g1)

            moves.append({"slot": slot, "to": to_val})

    if not moves:
        return None

    # try to detect a symbol in the same message; leave empty to fill from recent chat context
    ms = SYM_RE.search(t)
    sym = normalize_symbol(ms.group(1)) if ms else ""
    return {"symbol": sym, "moves": moves}

BE_HINT_RE = re.compile(r'\b(?:SL\s*entry\s*at\s*TP\s*1|(?:move|set)\s*SL\s*(?:to\s*)?entry\s*at\s*TP\s*1)\b', re.I)

# Risk controls
RISK_PCT_RE = re.compile(r'\brisk\s*(\d+(?:[.,]\d+)?)\s*%?\b', re.I)  # FIXED: Support comma decimals
HALF_RISK_RE = re.compile(r'\bHALF\s*RISK\b', re.I)
DOUBLE_RISK_RE = re.compile(r'\bDOUBLE\s*RISK\b', re.I)
QUARTER_RISK_RE = re.compile(r'\b(QUARTER|1/4)\s*RISK\b', re.I)
SMALL_LOTS_RE = re.compile(r'\b(SMALL\s*LOTS|USE\s*SMALL\s*LOTS)\b', re.I)

# Corrections / updates (FIXED: Support comma decimals)
CORR_SL_TYP0_RE = re.compile(r'\b(?:typo|correct|correction).*\bSL\b.*?(?:was\s*)?(-?\d+(?:[.,]\d+)?).*(?:not|now)\s*(-?\d+(?:[.,]\d+)?)', re.I)
CORR_SL_TO_RE = re.compile(r'\b(edit(?:ing)?|update(?:d)?)\b.*\bSL\b.*\bto\b\s*(-?\d+(?:[.,]\d+)?)', re.I)
UPDATED_PREFIX_RE = re.compile(r'^\s*updated\b', re.I)
SYMBOL_HINT_RE = re.compile(r'\b(gold|xauusd|xau|nas100|us100|ustec|dj30|us30|dow|spx500|sp500|us500|de40|dax|ger40|gbpjpy|xbrusd|xtiusd|usoil|wti|ukoil|brent)\b', re.I)

# Close commands
CLOSE_ANY_RE = re.compile(r'\b(close|close\s+all|close\s+at\s+market|close\s+now)\b', re.I)
CLOSE_WITH_SYM_RE = re.compile(r'\bclose\b.*?\b([A-Z]{3,6}|[A-Z]{2,5}\d{2,3}|xau|gold|us30|dj30|nas100|spx500|de40|xbrusd|xtiusd|usoil|wti|ukoil|brent)\b', re.I)

# Header patterns for pending orders (FIXED: Support comma decimals)
HEADER_PENDING_FULL_RE = re.compile(
    r'^\s*(?:#)?\s*(?P<sym>[A-Z]{3,6}|[A-Z]{2,5}\d{2,3})\s+'
    r'(?P<side>BUY|SELL)\s+'
    r'(?P<ptype>LIMIT|STOP)\s*@?\s*'
    r'(?P<price>-?\d+(?:[.,]\d+)?)\b',
    re.I | re.M
)

# Header patterns for inline prices (FIXED: Support comma decimals)
HEADER_INLINE_PRICE_RE = re.compile(
    r'^\s*(?:#)?\s*(?P<sym>[A-Z]{3,6}|[A-Z]{2,5}\d{2,3})\s+'
    r'(?P<side>BUY|SELL)\s+@?\s*'
    r'(?P<price>-?\d+(?:[.,]\d+)?)\b',
    re.I | re.M
)

# ====== STATE ======
RECENT_SYMBOL_BY_CHAT = {}  # {chat_title: "XAUUSD"}

# Track the last OPEN id per (chat title, symbol) so CLOSE can carry the exact oid
LAST_OPEN_OID = {}  # key: (title, symbol) -> int

# (optional) avoid double-writing same OPEN for same Telegram message
SEEN_OPEN = set()   # tuples of (title, event_id)

def convert_decimal(price_str: str) -> float:
    """Convert price string with comma or dot decimal to float"""
    try:
        # Convert comma decimal to dot decimal, then to float
        return float(price_str.replace(',', '.'))
    except:
        return None

def try_extract_sl(line: str) -> float:
    """Try multiple SL patterns to extract stop loss"""
    for pattern in SL_PATTERNS:
        match = pattern.search(line)
        if match:
            result = convert_decimal(match.group(1))
            if result is not None:
                return result
    return None

def try_extract_tp(line: str) -> float:
    """Try multiple TP patterns to extract take profit"""
    for pattern in TP_PATTERNS:
        match = pattern.search(line)
        if match:
            result = convert_decimal(match.group(1))
            if result is not None:
                return result
    return None

# ====== PARSERS ======
def parse_block_style(text: str):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None

    side = None
    symbol = None
    entry = None
    sl = None
    tps = []
    be_on_tp = 1 if BE_HINT_RE.search(text) else 0

    print(f"[DEBUG] Parsing signal with {len(lines)} lines:")

    # 1) HEADER FIRST: BUY LIMIT/STOP with price (pending)
    m = HEADER_PENDING_FULL_RE.search(text)
    if m:
        symbol = normalize_symbol(m.group('sym'))
        side   = m.group('side').upper()
        entry = convert_decimal(m.group('price'))
        print(f"[DEBUG] HEADER match (LIMIT/STOP): sym={symbol} side={side} entry={entry}")
    else:
        # 2) HEADER: BUY <price> (treat as pending too)
        m2 = HEADER_INLINE_PRICE_RE.search(text)
        if m2:
            symbol = normalize_symbol(m2.group('sym'))
            side   = m2.group('side').upper()
            entry = convert_decimal(m2.group('price'))
            print(f"[DEBUG] HEADER match (inline price): sym={symbol} side={side} entry={entry}")

    # 3) If still missing side/symbol, fall back to generic scan
    for i, ln in enumerate(lines):
        print(f"[DEBUG]   Line {i+1}: '{ln}'")
        if side is None:
            md = SIDE_RE.search(ln)
            if md:
                side = md.group(1).upper()
                print(f"[DEBUG] Found side (fallback): {side}")
        if symbol is None:
            ms = SYM_RE.search(ln)
            if ms:
                symbol = normalize_symbol(ms.group(1))
                print(f"[DEBUG] Found symbol (fallback): {symbol}")

    # 4) ENTRY via "ENTER/ENTRY ..." (only if not set by header)
    if entry is None:
        for ln in lines:
            m = ENTRY_LINE_RE.search(ln)
            if m:
                entry = convert_decimal(m.group(1))
                if entry is not None:
                    print(f"[DEBUG] Found entry via ENTRY line: {entry}")
                    break

    # 5) SL / TPs
    for ln in lines:
        low = ln.lower()

        # SL lines (ignore 'SL entry...' hints)
        if any(w in low for w in ['sl', 'stop', 'stoploss']):
            if 'entry' in low:
                continue
            v = try_extract_sl(ln)
            if v is not None and sl is None:
                sl = v
                print(f"[DEBUG] Found SL: {sl}")
                continue

        # TP lines
        if 'tp' in low:
            v = try_extract_tp(ln)
            if v is not None:
                tps.append(v)
                print(f"[DEBUG] Found TP: {v}")
                continue

    print("[DEBUG] Final parsing result:")
    print(f"[DEBUG]   Side: {side}")
    print(f"[DEBUG]   Symbol: {symbol}")
    print(f"[DEBUG]   Entry: {entry}")
    print(f"[DEBUG]   SL: {sl}")
    print(f"[DEBUG]   TPs: {tps}")

    if not side or not symbol:
        print(f"[DEBUG] Missing required fields - side: {side}, symbol: {symbol}")
        return None

    # Risk / lots overrides
    risk_percent = None
    m = RISK_PCT_RE.search(text)
    if m:
        risk_percent = convert_decimal(m.group(1))
    elif HALF_RISK_RE.search(text):      risk_percent = 0.5
    elif DOUBLE_RISK_RE.search(text):    risk_percent = 2.0
    elif QUARTER_RISK_RE.search(text):   risk_percent = 0.25

    lots_override = None
    if SMALL_LOTS_RE.search(text) and normalize_symbol(symbol) in OIL_BASE_SYMBOLS:
        lots_override = OIL_SMALL_LOTS

    return {
        "side": side,
        "symbol": symbol,
        "entry": entry,        # if present -> EA places pending
        "sl": sl,
        "tps": tps,
        "be_on_tp": be_on_tp,
        "risk_percent": risk_percent,
        "lots": lots_override
    }

def parse_correction(text: str):
    """Return {'symbol', 'new_sl', 'new_tps'} if it's a correction/edit; else None."""
    t = text.strip()
    low = t.lower()
    is_update_like = bool(UPDATED_PREFIX_RE.search(t)) or "typo" in low or "edit" in low or "updated" in low or "correction" in low
    if not is_update_like:
        return None

    sym = None
    ms = SYMBOL_HINT_RE.search(t)
    if ms:
        sym = normalize_symbol(ms.group(1))

    new_sl = None
    m = CORR_SL_TYP0_RE.search(t)
    if m:
        new_sl = convert_decimal(m.group(2))
    else:
        m = CORR_SL_TO_RE.search(t)
        if m:
            new_sl = convert_decimal(m.group(2))

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
    """Return symbol (or None) if it's a close command; else None."""
    if not CLOSE_ANY_RE.search(text):  # fast precheck
        return None
    # With symbol explicitly
    m = CLOSE_WITH_SYM_RE.search(text)
    if m:
        return normalize_symbol(m.group(1))
    # No symbol → let EA close for the most-recent symbol per chat (we'll fill it in handler)
    return ""  # sentinel = 'close last' for that chat

# ====== RUNNER ======
async def main():
    # Load the global counter at startup
    load_counter()
    
    SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(TELEGRAM_SESSION_NAME, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start()

    watch_titles = {str(x).strip().lower() for x in WATCH_CHATS}
    want_saved   = any(x in ("me", "saved messages", "self") for x in watch_titles)
    me           = await client.get_me()
    my_id        = me.id

    print("=== TELEGRAM BRIDGE WITH COMMA/DOT DECIMAL SUPPORT ===")
    print("Bridge running. Watching:", ", ".join(WATCH_CHATS))
    print("Writing to:", SIGNAL_FILE)
    print(f"Global counter loaded: {GLOBAL_COUNTER}")
    print("Supports both comma (116,580) and dot (116.580) decimals")
    print("==================================================")

    @client.on(events.NewMessage)
    async def handler(event):
        # Filter allowed chats
        title = ""
        is_ok = False
        if event.is_private and event.chat_id == my_id and want_saved:
            title = "Saved Messages"
            is_ok = True
        else:
            chat = await event.get_chat()
            title = (getattr(chat, "title", None) or getattr(chat, "username", None) or "").strip()
            if title.lower() in watch_titles:
                is_ok = True
        if not is_ok:
            return

        txt = event.raw_text or ""
        print(f"\n[NEW MESSAGE] From: {title}")
        print(f"[RAW TEXT] {repr(txt)}")

        # CLOSE?
        close_sym = parse_close(txt)
        if close_sym is not None:
            sym = close_sym if close_sym else RECENT_SYMBOL_BY_CHAT.get(title)
            if not sym:
                print("[CLOSE] No symbol found, skipping")
                return
            
            oid = LAST_OPEN_OID.get((title, sym), 0)
            global_id = get_next_id()
            rec = {
                "action": "CLOSE",
                "id": str(global_id),
                "t": int(time.time()),
                "source": title,
                "symbol": sym,
                "oid": str(oid),  
                "original_event_id": str(event.id)
            }
            with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=True) + "\n")
            print(f"[SAVED] CLOSE for {sym} from {title} (global_id={global_id})")
            return
        
        # MODIFY_TP?  (move one or more TP slots)
        tp_mod = parse_tp_moves(txt)
        if tp_mod:
            sym = tp_mod.get("symbol") or RECENT_SYMBOL_BY_CHAT.get(title)
            if not sym:
                print("[MODIFY_TP] No symbol found, skipping")
                return

            for mv in (tp_mod.get("moves") or []):
                tp_slot = int(mv.get("slot") or 1)
                tp_to   = mv.get("to")
                global_id = get_next_id()
                rec = {
                    "action": "MODIFY_TP",
                    "id": str(global_id),
                    "t": int(time.time()),
                    "source": title,
                    "symbol": sym,
                    "tp_slot": tp_slot,
                    "tp_to": tp_to,
                    "original_event_id": str(event.id)
                }
                with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=True) + "\n")
                print(f"[SAVED] MODIFY_TP for {sym}: TP{tp_slot} -> {tp_to} (global_id={global_id})")
            return

        # MODIFY?
        corr = parse_correction(txt)
        if corr:
            sym = corr["symbol"] or RECENT_SYMBOL_BY_CHAT.get(title)
            if not sym:
                print("[MODIFY] No symbol found, skipping")
                return
            
            global_id = get_next_id()
            rec = {
                "action": "MODIFY",
                "id": str(global_id),
                "t": int(time.time()),
                "source": title,
                "symbol": sym,
                "new_sl": corr["new_sl"],
                "new_tps_csv": ",".join(str(x) for x in corr["new_tps"]) if corr["new_tps"] else "",
                "original_event_id": str(event.id)
            }
            with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=True) + "\n")
            print(f"[SAVED] MODIFY for {sym}: SL->{corr['new_sl']} TPs->{rec['new_tps_csv']} (global_id={global_id})")
            return

        if (title, int(event.id)) in SEEN_OPEN:
            print("[DEDUP] OPEN already processed for this message, skipping")
            return
        
        # OPEN?
        parsed = parse_block_style(txt)
        if not parsed:
            print("[PARSE] No valid signal found")
            return

        sym = parsed["symbol"]
        RECENT_SYMBOL_BY_CHAT[title] = sym  # remember for CLOSE/MODIFY without symbol

        # Default 1% unless message says HALF/DOUBLE/etc.
        risk = 1.0 if parsed["risk_percent"] is None else parsed["risk_percent"]

        global_id = get_next_id()
        rec = {
            "action": "OPEN",
            "id": str(global_id),
            "t": int(time.time()),
            "source": title,
            "raw": txt.strip(),
            "side": parsed["side"],
            "symbol": sym,
            "entry": parsed["entry"],
            "sl": parsed["sl"],
            "tp": None,
            "risk_percent": risk,
            "lots": parsed["lots"],
            "tps_csv": ",".join(str(x) for x in parsed["tps"]) if parsed["tps"] else "",
            "be_on_tp": int(parsed["be_on_tp"] or 0),
            "original_event_id": str(event.id)
        }
        
        # Log the record before saving
        print(f"[RECORD] Global ID: {global_id}")
        print(f"[RECORD] {json.dumps(rec, indent=2)}")

        LAST_OPEN_OID[(title, sym)] = global_id
        SEEN_OPEN.add((title, int(event.id)))  # optional de-dupe
        
        with open(SIGNAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")
        print(f"[SAVED] OPEN: {rec['symbol']} {rec['side']} risk={risk} lots={rec['lots']} SL={rec['sl']} TPs={rec['tps_csv']} from {title} (global_id={global_id})")

    # Treat edits like new messages
    @client.on(events.MessageEdited)
    async def edited(event):
        print("[EDIT] Message edited, processing as new...")
        await handler(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())