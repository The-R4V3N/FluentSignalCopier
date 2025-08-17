# fluent_copier.py
# Modern Windows GUI (PySide6 + QFluentWidgets) for Telegram -> MT5 file-drop copier
# Build (example):
#   py -3.12 -m pip install pyside6 "PySide6-Fluent-Widgets>=1.8" telethon pyinstaller python-dotenv
#   py -3.12 -m PyInstaller --clean --noconsole --onefile ^
#       --name FluentSignalCopier ^
#       --icon .\app.ico ^
#       --add-data "app.ico;." ^
#       --collect-all qfluentwidgets --collect-all PySide6 ^
#       .\fluent_copier.py

import os, re, sys, json, time, asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable
from html import escape

from PySide6.QtCore import Qt, QThread, Signal, Slot, QCoreApplication, QTimer
from PySide6.QtGui import QTextCursor, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
    QDialog, QListWidget, QListWidgetItem, QAbstractItemView, QSlider, QLabel
)
from qfluentwidgets import (
    LineEdit, PushButton, PrimaryPushButton, TextEdit,
    InfoBar, InfoBarPosition, setTheme, Theme, FluentIcon, SubtitleLabel
)

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

# optional sound beeps (Windows); safe no-ops elsewhere
try:
    import winsound
    def _beep_ok():   winsound.MessageBeep(winsound.MB_ICONASTERISK)
    def _beep_warn(): winsound.MessageBeep(winsound.MB_ICONHAND)
except Exception:
    def _beep_ok():   pass
    def _beep_warn(): pass

# --------- CONFIG ---------
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

# --------- MT5 path auto-detect ---------
def _uniq_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set(); out = []
    for p in paths:
        try:
            rp = p.resolve()
        except Exception:
            continue
        if rp not in seen and rp.exists():
            seen.add(rp); out.append(rp)
    return out

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

    cands = _uniq_paths(cands)
    try:
        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        pass
    return cands

# --------- PARSER (trimmed; same schema) ---------
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
    s = s.strip().upper()
    return ALIASES.get(s, s)

SYM_RE = re.compile(
    r'(?:#)?\b([A-Z]{6}|[A-Z]{2,5}\d{2,3}|XAU|XAUSD|GOLD|SILVER|XAG|USOIL|WTI|OIL|XTIUSD|UKOIL|BRENT|XBRUSD|SPX500|SP500|US500|USTEC|US30|DJ30)\b',
    re.I
)
SIDE_RE  = re.compile(r'\b(BUY|SELL)\b', re.I)
ENTRY_RE = re.compile(r'^\s*(?:ENTER|ENTRY)\b.*?(-?\d+(?:[.,]\d+)?)\b', re.I)
SL_RES = [
    re.compile(r'\b(?:STOP\s*LOSS|STOPLOSS)\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\bSL\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'^\s*SL\b[^0-9-]*?@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]
TP_RES = [
    re.compile(r'\bTP\d*\s*@\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'\bTP\d*\s+(-?\d+(?:[.,]\d+)?)\b', re.I),
    re.compile(r'^\s*TP\d*\s*@?\s*(-?\d+(?:[.,]\d+)?)\b', re.I),
]
BE_HINT_RE = re.compile(r'\bSL\s*entry\s*at\s*TP\s*1\b', re.I)
RISK_PCT_RE = re.compile(r'\brisk\s*(\d+(?:[.,]\d+)?)\s*%?\b', re.I)
HALF_RISK_RE = re.compile(r'\bHALF\s*RISK\b', re.I)
DOUBLE_RISK_RE = re.compile(r'\bDOUBLE\s*RISK\b', re.I)
QUARTER_RISK_RE = re.compile(r'\b(QUARTER|1/4)\s*RISK\b', re.I)
CLOSE_ANY_RE = re.compile(r'\b(close|close\s+all|close\s+at\s+market|close\s+now)\b', re.I)

def _dec(s: str) -> Optional[float]:
    try: return float(s.replace(",", "."))
    except: return None

def _try_sl(line: str):
    for r in SL_RES:
        m=r.search(line)
        if m:
            v=_dec(m.group(1))
            if v is not None: return v
    return None

def _try_tp(line: str):
    for r in TP_RES:
        m=r.search(line)
        if m:
            v=_dec(m.group(1))
            if v is not None: return v
    return None

def parse_message(text: str) -> Optional[Dict[str, Any]]:
    t = text.strip()
    low = t.lower()

    # ---- CLOSE ----
    if CLOSE_ANY_RE.search(t):
        ms = SYM_RE.search(t)
        sym = normalize_symbol(ms.group(1)) if ms else ""
        return {"kind": "CLOSE", "symbol": sym}

    # ---- MODIFY ----
    if any(k in low for k in ["updated","update","edit","typo","correction"]):
        new_sl=None; tps=[]
        for line in t.splitlines():
            s=line.strip().lower()
            if "sl" in s and "entry" not in s:
                v=_try_sl(line)
                if v is not None: new_sl=v
            if "tp" in s:
                v=_try_tp(line)
                if v is not None: tps.append(v)
        return {"kind":"MODIFY","symbol":"","new_sl":new_sl,"new_tps":tps}

    side=None; symbol=None; entry=None; sl=None; tps=[]
    be_on_tp = 1 if BE_HINT_RE.search(t) else 0
    lines=[l.strip() for l in t.splitlines() if l.strip()]
    for ln in lines:
        if side is None:
            ms=SIDE_RE.search(ln)
            if ms: side=ms.group(1).upper()
        if symbol is None:
            mm=SYM_RE.search(ln)
            if mm: symbol=normalize_symbol(mm.group(1))
        if entry is None:
            me=ENTRY_RE.search(ln)
            if me: entry=_dec(me.group(1))
    for ln in lines:
        lo=ln.lower()
        if "sl" in lo and "entry" not in lo:
            v=_try_sl(ln)
            if v is not None and sl is None: sl=v
        if "tp" in lo:
            v=_try_tp(ln)
            if v is not None: tps.append(v)
    if not (side and symbol):
        return None
    risk=None
    m=RISK_PCT_RE.search(t)
    if m: risk=_dec(m.group(1))
    elif HALF_RISK_RE.search(t): risk=0.5
    elif DOUBLE_RISK_RE.search(t): risk=2.0
    elif QUARTER_RISK_RE.search(t): risk=0.25
    return {"kind":"OPEN","side":side,"symbol":symbol,"entry":entry,"sl":sl,"tps":tps,"be_on_tp":be_on_tp,"risk":risk}

# --------- Chat Picker Dialog ---------
class ChatPickerDialog(QDialog):
    def __init__(self, chats: List[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick chats to watch")
        self.resize(680, 520)

        v = QVBoxLayout(self); v.setContentsMargins(16, 16, 16, 16); v.setSpacing(8)

        self.search = LineEdit(self); self.search.setPlaceholderText("Search title, @handle, or id…")
        v.addWidget(self.search)

        self.list = QListWidget(self)
        self.list.setSelectionMode(QAbstractItemView.MultiSelection)
        v.addWidget(self.list, 1)

        btns = QHBoxLayout(); v.addLayout(btns)
        okBtn = PrimaryPushButton("Add selected", self)
        cancelBtn = PushButton("Cancel", self)
        btns.addStretch(1); btns.addWidget(okBtn); btns.addWidget(cancelBtn)
        okBtn.clicked.connect(self.accept); cancelBtn.clicked.connect(self.reject)

        self._all_items: List[QListWidgetItem] = []
        for c in chats:
            title = c.get("title") or ""
            user  = c.get("username") or ""
            ident = c.get("id") or ""
            label = title or (f"@{user}" if user else ident)
            sub   = f"@{user}" if user else ident
            text  = f"{label}    —    {sub}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, c)
            self.list.addItem(it)
            self._all_items.append(it)

        def _apply_filter(s: str):
            q = (s or "").strip().lower()
            for it in self._all_items:
                c = it.data(Qt.UserRole)
                hay = " ".join([c.get("title",""), c.get("username",""), c.get("id","")]).lower()
                it.setHidden(q not in hay)
        self.search.textChanged.connect(_apply_filter)

    def selected_entries(self) -> List[str]:
        out = []
        for it in self.list.selectedItems():
            c = it.data(Qt.UserRole)
            if c.get("username"):
                out.append(f"@{c['username']}")
            elif c.get("title"):
                out.append(c["title"])
            else:
                out.append(c.get("id",""))
        seen=set(); uniq=[]
        for s in out:
            if s and s not in seen:
                seen.add(s); uniq.append(s)
        return uniq

# --------- Worker (QThread + asyncio) ---------
class CopierThread(QThread):
    logLine = Signal(str)
    notify  = Signal(str, str)
    authCodeNeeded = Signal()
    authPwdNeeded  = Signal()
    runningState   = Signal(bool)
    dialogsReady   = Signal(list)

    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.client: Optional[TelegramClient] = None
        self._stop_flag = False
        self._paused = False
        self._code: Optional[str] = None
        self._password: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._dialogs_cache: list = []
        self.quality_threshold = 50

        self.signal_file: Optional[Path] = None
        self.counter_file: Optional[Path] = None
        self.heartbeat_file: Optional[Path] = None
        self.global_counter = 0

        # Per-chat memory keyed by stable "source_key" (id:<chat_id> or name:<lower_title>)
        self.recent_symbol_by_chat: Dict[str, str] = {}
        self.last_open_oid: Dict[tuple, int] = {}   # (source_key, symbol) -> last OPEN id (Telegram message id)

        # duplicate suppression
        self._recent_seen: Dict[str, float] = {}

    def set_quality_threshold(self, v:int):
        self.quality_threshold = max(0, min(100, int(v)))

    # paths / counter
    def _choose_mt5_files(self) -> Path:
        p = Path(self.cfg.mt5_files_dir) if self.cfg.mt5_files_dir else None
        if p and p.exists(): return p
        cands = find_mt5_files_candidates()
        if cands: return cands[0]
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

    # auth data from UI
    def set_auth_code(self, code: str): self._code = code
    def set_auth_password(self, pwd: str): self._password = pwd

    # pause controls
    def set_paused(self, v: bool): self._paused = bool(v)
    def is_paused(self) -> bool: return self._paused

    # thread start
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
            self.runningState.emit(False)

    @Slot()
    def getDialogs(self):
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
        try:
            dialogs = await self.client.get_dialogs(limit=limit)
            out = []
            for d in dialogs:
                e = d.entity
                title = (getattr(e, "title", None)
                         or (" ".join(x for x in [getattr(e, "first_name", None), getattr(e, "last_name", None)] if x)) or "").strip()
                username = getattr(e, "username", "") or ""
                out.append({"id": str(d.id), "title": title, "username": username})
            self._dialogs_cache = out
            self.dialogsReady.emit(out)
        except Exception as ex:
            self.notify.emit("Fetch failed", str(ex))

    # confidence scoring for parsed signals
    def _confidence(self, p: dict) -> int:
        if not p: return 0
        score = 0
        score += 40 if p.get("side") and p.get("symbol") else 0
        if p.get("sl"): score += 20
        tps = p.get("tps") or []
        score += min(3, len(tps)) * 10          # up to +30
        if isinstance(p.get("entry"), (int,float)): score += 5
        if p.get("be_on_tp"): score += 5
        return min(100, score)

    def _dedupe_key(self, chat_id: int, msg_id: int, txt: str) -> str:
        import hashlib
        h = hashlib.sha1((txt.strip()[:400]).encode("utf-8", "ignore")).hexdigest()[:12]
        return f"{chat_id}:{msg_id}:{h}"

    def _dedupe_check(self, key: str, window=8.0) -> bool:
        now = time.time()
        # purge old
        if self._recent_seen:
            for k, exp in list(self._recent_seen.items()):
                if exp < now:
                    self._recent_seen.pop(k, None)
        if key in self._recent_seen:
            return True
        self._recent_seen[key] = now + window
        return False

    async def _main(self, loop):
        self.runningState.emit(True)

        mt5_dir = self._choose_mt5_files()
        mt5_dir.mkdir(parents=True, exist_ok=True)
        self.signal_file = mt5_dir / "Fluent_signals.jsonl"
        self.counter_file = mt5_dir / "signal_counter.txt"
        self.heartbeat_file = mt5_dir / "fluent_heartbeat.txt"
        self._load_counter()

        self.logLine.emit(f"[INFO] MT5 Files: {mt5_dir}")
        self.logLine.emit(f"[INFO] Writing: {self.signal_file}")

        api_id  = int(self.cfg.api_id)
        api_hash= self.cfg.api_hash.strip()
        phone   = self.cfg.phone.strip()
        if not api_id or not api_hash:
            self.notify.emit("Missing credentials", "Enter API ID and API Hash.")
            return

        session_path = str(APP_DIR / (self.cfg.session_name or "tg_bridge_session"))
        self.client = TelegramClient(session_path, api_id, api_hash)

        # reconnect loop with exponential backoff
        backoff = 1.0
        while not self._stop_flag:
            try:
                await self.client.connect()
                if not await self.client.is_user_authorized():
                    if not phone:
                        self.notify.emit("Phone needed", "Enter your phone number for first login.")
                        return
                    result = await self.client.send_code_request(phone)
                    self.logLine.emit("[AUTH] Code sent.")
                    self.authCodeNeeded.emit()
                    while self._code is None and not self._stop_flag:
                        await asyncio.sleep(0.1)
                    if self._stop_flag: break
                    try:
                        await self.client.sign_in(phone=phone, code=self._code, phone_code_hash=result.phone_code_hash)
                    except SessionPasswordNeededError:
                        self.authPwdNeeded.emit()
                        while self._password is None and not self._stop_flag:
                            await asyncio.sleep(0.1)
                        if self._stop_flag: break
                        await self.client.sign_in(password=self._password)

                me = await self.client.get_me()
                self.logLine.emit(f"[AUTH] Signed in as @{getattr(me,'username', None)} (id={me.id})")

                # Prefetch dialogs in background for instant picker
                self.logLine.emit("[SCAN] Prefetching chats…")
                self._loop.create_task(self._prefetch_dialogs())

                watch = [w.strip() for w in (self.cfg.watch_chats or []) if str(w).strip()]
                watch_set = {w.lower() for w in watch}
                want_saved = any(x in ("me","saved messages","self") for x in watch_set)

                @self.client.on(events.NewMessage)
                async def on_new_message(event):
                    if self._stop_flag: return
                    if self._paused:
                        self.logLine.emit("[RUN] Intake paused; message ignored")
                        return

                    chat_id = event.chat_id
                    msg_id  = event.id

                    # heartbeat touch (fast)
                    try:
                        self.heartbeat_file.write_text(str(int(time.time())), encoding="utf-8")
                    except Exception:
                        pass

                    # de-dup
                    key = self._dedupe_key(chat_id, msg_id, event.raw_text or "")
                    if self._dedupe_check(key):
                        self.logLine.emit("[WARN] Duplicate/rapid replay suppressed")
                        _beep_warn()
                        return

                    # Saved Messages?
                    title = ""
                    ok = False
                    if event.is_private and want_saved:
                        me2 = await self.client.get_me()
                        if event.chat_id == me2.id:
                            title = "Saved Messages"; ok = True

                    # Other chats
                    if not ok:
                        chat = await event.get_chat()
                        cands = set()
                        title = getattr(chat, "title", None) or ""
                        if title:
                            cands.add(title.strip().lower())

                        username = getattr(chat, "username", None)
                        if username:
                            u = username.strip()
                            cands.add(u.lower()); cands.add(('@' + u).lower())

                        cands.add(str(event.chat_id))  # numeric id

                        first = getattr(chat, "first_name", None)
                        last  = getattr(chat, "last_name", None)
                        name_combo = " ".join(n for n in [first, last] if n)
                        if name_combo:
                            cands.add(name_combo.strip().lower())

                        ok = bool(watch_set & cands)
                        if not ok:
                            return

                    source_key = f"id:{chat_id}" if chat_id is not None else f"name:{(title or '').lower()}"

                    txt = event.raw_text or ""
                    self.logLine.emit(f"[NEW] {title}: {repr(txt[:180])}...")

                    p = parse_message(txt)
                    if not p:
                        self.logLine.emit("[PARSE] No valid signal.")
                        return

                    # confidence gate
                    conf = self._confidence(p)
                    threshold = self.quality_threshold  # numeric value, updated from MainWindow
                    if conf < threshold:
                        self.logLine.emit(f"[WARN] Signal skipped (confidence {conf} < {threshold})")
                        return

                    # ===== CLOSE =====
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
                        with self.signal_file.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(rec, ensure_ascii=True) + "\n"); f.flush(); os.fsync(f.fileno())
                        self.logLine.emit(f"[WRITE] CLOSE {sym} (OID={oid})")
                        _beep_ok()
                        return

                    # ===== MODIFY =====
                    if p["kind"] == "MODIFY":
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
                        with self.signal_file.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(rec, ensure_ascii=True) + "\n"); f.flush(); os.fsync(f.fileno())
                        self.logLine.emit(f"[WRITE] MODIFY {sym} SL->{p.get('new_sl')} TPs->{rec['new_tps_csv']}")
                        _beep_ok()
                        return

                    # ===== OPEN =====
                    sym = p["symbol"]
                    self.recent_symbol_by_chat[source_key] = sym
                    gid = self._next_id()

                    rec = {
                        "action": "OPEN",
                        "id": str(msg_id),
                        "source_id": str(chat_id),
                        "t": int(time.time()),
                        "source": title,
                        "raw": (txt.strip()[:1000]),
                        "side": p["side"], "symbol": sym,
                        "entry": p["entry"], "sl": p["sl"],
                        "tp": None,
                        "risk_percent": (1.0 if p["risk"] is None else p["risk"]),
                        "lots": None,
                        "tps_csv": ",".join(str(x) for x in (p["tps"] or [])) if p["tps"] else "",
                        "be_on_tp": int(p["be_on_tp"] or 0),
                        "gid": str(gid),
                        "original_event_id": str(event.id),
                        "confidence": conf
                    }
                    with self.signal_file.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=True) + "\n"); f.flush(); os.fsync(f.fileno())
                    self.last_open_oid[(source_key, sym)] = msg_id
                    self.logLine.emit(f"[WRITE] OPEN {sym} {p['side']} SL={p['sl']} TPs={rec['tps_csv']} (conf={conf})")
                    _beep_ok()

                @self.client.on(events.MessageEdited)
                async def on_edit(event):
                    await on_new_message(event)

                # heartbeat pinger
                async def _hb_writer():
                    while not self._stop_flag and self.client and self.client.is_connected():
                        try:
                            self.heartbeat_file.write_text(str(int(time.time())), encoding="utf-8")
                        except Exception:
                            pass
                        await asyncio.sleep(5)

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
                except Exception:
                    pass
                self.logLine.emit("[STOPPED]")

            if self._stop_flag: break
            self.logLine.emit(f"[WARN] Reconnecting in {int(backoff)}s…")
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 2.0)

    def stop(self):
        self._stop_flag = True
        try:
            if self._loop and self._loop.is_running():
                async def _shutdown():
                    try:
                        if self.client and self.client.is_connected():
                            await self.client.disconnect()
                    except Exception as e:
                        self.logLine.emit(f"[STOP] disconnect error: {e}")
                asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
        except Exception as e:
            self.logLine.emit(f"[STOP] scheduling error: {e}")

    async def _prefetch_dialogs(self, limit: int = 400):
        try:
            dialogs = await self.client.get_dialogs(limit=limit)
            out = []
            for d in dialogs:
                e = d.entity
                title = (getattr(e, "title", None)
                         or (" ".join(x for x in [getattr(e, "first_name", None), getattr(e, "last_name", None)] if x)) or "").strip()
                username = getattr(e, "username", "") or ""
                out.append({"id": str(d.id), "title": title, "username": username})
            self._dialogs_cache = out
            self.logLine.emit(f"[SCAN] Cached {len(out)} chats.")
        except Exception as ex:
            self.logLine.emit(f"[SCAN] Prefetch failed: {ex}")

# --------- Resource Path Helper ---------
def resource_path(name):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name

# --------- UI ---------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        setTheme(Theme.AUTO)
        self.setWindowTitle("Fluent Signal Copier")
        QCoreApplication.setOrganizationName("R4V3N")
        QCoreApplication.setOrganizationDomain("r4v3n.dev")

        ico_path = resource_path("app.ico")
        if ico_path.exists():
            ico = QIcon(str(ico_path))
            self.setWindowIcon(ico)
            QApplication.instance().setWindowIcon(ico)

        self.cfg = load_config()
        self.thread: Optional[CopierThread] = None

        root = QVBoxLayout(self); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(12)

        # Credentials
        root.addWidget(SubtitleLabel("Telegram Credentials"))
        row1 = QHBoxLayout(); root.addLayout(row1)
        self.apiId = LineEdit(self); self.apiId.setPlaceholderText("API ID"); self.apiId.setText(str(self.cfg.api_id or ""))
        self.apiHash = LineEdit(self); self.apiHash.setPlaceholderText("API Hash"); self.apiHash.setText(self.cfg.api_hash)
        self.phone = LineEdit(self); self.phone.setPlaceholderText("Phone (+46...)"); self.phone.setText(self.cfg.phone)
        row1.addWidget(self.apiId); row1.addWidget(self.apiHash); row1.addWidget(self.phone)

        # MT5 folder row
        root.addWidget(SubtitleLabel(r"MT5 MQL5\Files Folder"))
        row2 = QHBoxLayout(); root.addLayout(row2)
        self.mt5Dir = LineEdit(self); self.mt5Dir.setPlaceholderText(r"C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\...\MQL5\Files")
        self.mt5Dir.setText(self.cfg.mt5_files_dir)
        browse = PushButton(FluentIcon.FOLDER, "Browse…", self)
        autod = PushButton(FluentIcon.SEARCH, "Auto-detect", self)
        pick  = PushButton(FluentIcon.PEOPLE, "Pick from Telegram…", self)
        row2.addWidget(self.mt5Dir); row2.addWidget(browse); row2.addWidget(autod); row2.addWidget(pick)
        browse.clicked.connect(self.onBrowse)
        autod.clicked.connect(self.onAutoDetect)
        pick.clicked.connect(self.onPickChats)
        self.pickBtn = pick; self.pickBtn.setEnabled(False)

        # Prefill once on startup if empty or invalid
        try:
            cur = Path(self.mt5Dir.text().strip()) if self.mt5Dir.text().strip() else None
            if not cur or not cur.exists():
                cands = find_mt5_files_candidates()
                if cands:
                    self.mt5Dir.setText(str(cands[0]))
                    self.toast("Detected MT5 folder", str(cands[0]), success=True)
        except Exception:
            pass

        # Watch chats
        root.addWidget(SubtitleLabel("Watch Chats (one per line)"))
        self.chats = TextEdit(self); self.chats.setFixedHeight(100)
        self.chats.setText("\n".join(self.cfg.watch_chats or ["Saved Messages"]))
        root.addWidget(self.chats)

        # Controls
        row3 = QHBoxLayout(); root.addLayout(row3)
        self.saveBtn  = PushButton(FluentIcon.SAVE, "Save", self)
        self.startBtn = PrimaryPushButton("Start", self)
        self.stopBtn  = PushButton("Stop", self); self.stopBtn.setEnabled(False)

        # NEW: Pause & Emergency
        self.pauseBtn = PushButton(FluentIcon.PAUSE, "Pause intake", self); self.pauseBtn.setEnabled(False)
        self.emergBtn = PrimaryPushButton("EMERGENCY STOP", self); self.emergBtn.setEnabled(False)

        row3.addWidget(self.saveBtn); row3.addWidget(self.startBtn); row3.addWidget(self.stopBtn)
        row3.addWidget(self.pauseBtn); row3.addWidget(self.emergBtn)

        self.saveBtn.clicked.connect(self.saveConfig)
        self.startBtn.clicked.connect(self.start)
        self.stopBtn.clicked.connect(self.stop)
        self.pauseBtn.clicked.connect(self.togglePause)
        self.emergBtn.clicked.connect(self.emergencyStop)

        # --- Signal quality slider
        row4 = QHBoxLayout(); root.addLayout(row4)
        self.qualityLabel = QLabel("Signal Quality ≥ 50", self)
        self.qualitySlider = QSlider(Qt.Horizontal, self)
        self.qualitySlider.setRange(0, 100)
        self.qualitySlider.setValue(50)   # default
        self.qualitySlider.setTickInterval(10)
        self.qualitySlider.setTickPosition(QSlider.TicksBelow)

        row4.addWidget(self.qualityLabel)
        row4.addWidget(self.qualitySlider)

        self.qualitySlider.valueChanged.connect(
            lambda v: self.qualityLabel.setText(f"Signal Quality ≥ {v}")
        )

        # Inline auth box
        self.authBox = QWidget(self)
        authLay = QHBoxLayout(self.authBox)
        authLay.setContentsMargins(0, 0, 0, 0); authLay.setSpacing(8)
        self.authPrompt = SubtitleLabel("Enter the code you received:", self.authBox)
        self.authEdit   = LineEdit(self.authBox)
        self.authEdit.setPlaceholderText("e.g. 12345")
        self.authSubmit = PrimaryPushButton("Submit", self.authBox)
        self.authCancel = PushButton("Cancel", self.authBox)
        authLay.addWidget(self.authPrompt)
        authLay.addWidget(self.authEdit, 1)
        authLay.addWidget(self.authSubmit)
        authLay.addWidget(self.authCancel)
        self.authBox.setVisible(False)
        self.authSubmit.clicked.connect(self._submitAuth)
        self.authCancel.clicked.connect(self._cancelAuth)
        root.addWidget(self.authBox)

        # Log
        root.addWidget(SubtitleLabel("Log"))
        self.log = TextEdit(self); self.log.setReadOnly(True)
        self.log.setMinimumHeight(220)
        self.log.setAcceptRichText(True)
        root.addWidget(self.log)

        # Custom context menu with "Clear log"
        self.log.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log.customContextMenuRequested.connect(self._showLogMenu)

        # small UI poller for future snapshot/heartbeat reads if needed
        self.uiTimer = QTimer(self); self.uiTimer.setInterval(2000); self.uiTimer.start()
        self.uiTimer.timeout.connect(self._tickUi)

    def _tickUi(self):  # reserved for future (e.g., snapshot rendering)
        pass

    # UI helpers
    def toast(self, title: str, content: str, success: bool = False):
        (InfoBar.success if success else InfoBar.info)(title, content, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _appendLog(self, line: str):
        """
        Render log lines with a colored [TAG] badge.
        Examples recognized: [ERROR], [WARN], [INFO], [NEW], [WRITE], [PARSE], [AUTH], [RUN], [SCAN], [STOPPED], [COUNTER]
        Falls back to [INFO] if no tag is present.
        """
        colors = {
            "ERROR":   "#EF4444",  # red
            "WARN":    "#F59E0B",  # amber
            "INFO":    "#3B82F6",  # blue
            "NEW":     "#7C3AED",  # purple
            "WRITE":   "#10B981",  # green
            "PARSE":   "#F97316",  # orange
            "AUTH":    "#06B6D4",  # cyan
            "RUN":     "#6366F1",  # indigo
            "SCAN":    "#14B8A6",  # teal
            "STOPPED": "#6B7280",  # gray
            "COUNTER": "#84CC16",  # lime
        }
        aliases = { "WARNING": "WARN", "ERR": "ERROR" }

        tag = "INFO"; msg = line
        m = re.match(r'^\[([A-Za-z]+)]\s*(.*)$', line.strip())
        if m:
            tag = aliases.get(m.group(1).upper(), m.group(1).upper())
            msg = m.group(2)
        else:
            low = line.lower()
            if "error" in low: tag = "ERROR"
            elif "warn" in low: tag = "WARN"

        color = colors.get(tag, "#6B7280")
        badge = (
            f'<span style="background-color:{color};'
            f' color:white; border-radius:8px; padding:1px 8px;'
            f' font-weight:600; font-family:Segoe UI, system-ui, -apple-system;">{escape(tag)}</span>'
        )
        safe_msg = escape(msg).replace("\n", "<br>")
        html = f'<div style="margin:2px 0;">{badge}&nbsp;&nbsp;<span style="white-space:pre-wrap;">{safe_msg}</span></div>'
        self.log.append(html)
        self.log.moveCursor(QTextCursor.End)

    def _showAuthBox(self, mode: str):
        if mode == "code":
            self.authPrompt.setText("Enter the code you received:")
            self.authEdit.setPlaceholderText("Telegram code (e.g. 12345)")
            self.authEdit.setEchoMode(self.authEdit.EchoMode.Normal)
            self._authMode = "code"
        else:
            self.authPrompt.setText("Enter your Telegram 2FA password:")
            self.authEdit.setPlaceholderText("Password")
            self.authEdit.setEchoMode(self.authEdit.EchoMode.Password)
            self._authMode = "password"
        self.authEdit.clear(); self.authBox.setVisible(True); self.authEdit.setFocus()

    def _hideAuthBox(self): self.authBox.setVisible(False); self.authEdit.clear()

    def _submitAuth(self):
        text = self.authEdit.text().strip()
        if not text:
            self.toast("Missing", "Please enter a value.")
            return
        if not self.thread:
            self._hideAuthBox(); return
        if getattr(self, "_authMode", "code") == "code":
            self.thread.set_auth_code(text)
            self.toast("Code sent", "Signing in…", success=True)
        else:
            self.thread.set_auth_password(text)
            self.toast("Password sent", "Verifying…", success=True)
        self._hideAuthBox()

    def _cancelAuth(self):
        if self.thread: self.thread.stop()
        self._hideAuthBox()

    def _showLogMenu(self, pos):
        menu = self.log.createStandardContextMenu()
        menu.addSeparator()
        clear_act = menu.addAction("Clear log")
        clear_act.triggered.connect(self.clearLog)
        menu.exec(self.log.mapToGlobal(pos))

    def clearLog(self):
        self.log.clear()
        self.toast("Log cleared", "", success=True)

    # Actions
    def onBrowse(self):
        d = QFileDialog.getExistingDirectory(self, "Select MT5 MQL5\\Files folder", self.mt5Dir.text() or "")
        if d:
            self.mt5Dir.setText(d)

    def onAutoDetect(self):
        try:
            cands = find_mt5_files_candidates()
            if not cands:
                self.toast("Not found", "No MT5 MQL5\\Files folders detected. Use Browse…")
                return
            self.mt5Dir.setText(str(cands[0]))
            self.toast("Detected", str(cands[0]), success=True)
            if len(cands) > 1:
                self._appendLog("[INFO] Other candidates:")
                for p in cands[1:]:
                    self._appendLog(f"  - {p}")
        except Exception as e:
            QMessageBox.critical(self, "Auto-detect failed", str(e))

    def saveConfig(self):
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
            self.toast("Saved", f"Config written to:\n{CONF_PATH}", success=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def start(self):
        self.saveConfig()
        if not self.cfg.api_id or not self.cfg.api_hash:
            QMessageBox.warning(self, "Missing", "Enter API ID and API Hash.")
            return
        self.thread = CopierThread(self.cfg, self)
        self.thread.logLine.connect(self._appendLog)
        self.thread.notify.connect(lambda t,m: self.toast(t, m))
        self.thread.authCodeNeeded.connect(self._onAuthCodeNeeded)
        self.thread.authPwdNeeded.connect(self._onAuthPwdNeeded)
        self.thread.runningState.connect(self._onRunningState)
        self.thread.dialogsReady.connect(self.onDialogsReady)
        self.thread.set_quality_threshold(self.qualitySlider.value())
        self.qualitySlider.valueChanged.connect(
            lambda v: self.thread and self.thread.set_quality_threshold(v)
        )
        self.thread.start()
        self._onRunningState(True)

    def stop(self):
        if self.thread:
            self.thread.stop()
        self._hideAuthBox()
        self._onRunningState(False)

    @Slot()
    def _onAuthCodeNeeded(self):
        self._showAuthBox("code")

    @Slot()
    def _onAuthPwdNeeded(self):
        self._showAuthBox("password")

    @Slot(bool)
    def _onRunningState(self, running: bool):
        self.startBtn.setEnabled(not running)
        self.stopBtn.setEnabled(running)
        self.pickBtn.setEnabled(running)
        self.pauseBtn.setEnabled(running)
        self.emergBtn.setEnabled(running)

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
        dlg = ChatPickerDialog(chats, self)
        if dlg.exec():
            picks = dlg.selected_entries()
            if not picks:
                return
            current = [x.strip() for x in self.chats.toPlainText().splitlines() if x.strip()]
            merged = current[:]
            seen = set(x.lower() for x in current)
            for p in picks:
                if p.lower() not in seen:
                    merged.append(p); seen.add(p.lower())
            self.chats.setText("\n".join(merged))
            self.toast("Added", f"Added {len(picks)} chat(s).", success=True)

    # --- NEW: Pause + Emergency
    def togglePause(self):
        if not self.thread: return
        self.thread.set_paused(not self.thread.is_paused())
        now = "PAUSED" if self.thread.is_paused() else "RESUMED"
        self._appendLog(f"[RUN] Intake {now}")
        self.toast("Intake", now, success=True)
        self.pauseBtn.setText("Resume intake" if self.thread.is_paused() else "Pause intake")

    def emergencyStop(self):
        if not self.thread or not self.thread.signal_file:
            self.toast("Not running", "Start first"); return
        gid = self.thread._next_id()  # use the same counter file
        rec = {
            "action":"EMERGENCY_CLOSE_ALL",
            "id": str(gid),
            "t": int(time.time()),
            "source":"GUI",
            "source_id":"",
            "confirm":"YES"
        }
        with self.thread.signal_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n"); f.flush(); os.fsync(f.fileno())
        self._appendLog("[WRITE] EMERGENCY_CLOSE_ALL dispatched")
        self.toast("Emergency STOP", "Close-all signal sent.", success=True)

# --------- entry ---------
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(980, 720)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
