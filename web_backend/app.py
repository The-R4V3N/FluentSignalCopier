# backend/app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Iterable
import asyncio, json, time, os, sys, re

# --- Optional .env loading ----------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# -----------------------------------------------------------------------------
# FastAPI init + CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="Fluent Web Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Server-side settings persisted for the web UI (Telegram creds, MT5 dir, etc.)
# -----------------------------------------------------------------------------
SETTINGS_JSON = Path(os.getenv("WEB_SETTINGS_JSON") or Path.cwd() / "web_settings.json")

class BridgeSettings(BaseModel):
    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    phone: Optional[str] = None
    mt5_dir: Optional[str] = None
    sources: List[str] = []

def _load_server_settings() -> BridgeSettings:
    if SETTINGS_JSON.exists():
        try:
            return BridgeSettings(**json.loads(SETTINGS_JSON.read_text()))
        except Exception:
            pass
    return BridgeSettings()

SERVER_SETTINGS = _load_server_settings()

# Treat these as internal/system sources when aggregating performance
INTERNAL_SOURCES = {"WEB", "GUI", "EA", "SYSTEM", "LOCAL", "", None}

# -----------------------------------------------------------------------------
# Helpers for locating MT5 MQL5\Files folder
# -----------------------------------------------------------------------------
def _uniq_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set(); out: List[Path] = []
    for p in paths:
        try:
            rp = Path(p).resolve()
            if rp not in seen and rp.exists():
                seen.add(rp); out.append(rp)
        except Exception:
            pass
    return out

def _auto_detect_mt5_files() -> Optional[Path]:
    """Best-effort scan for a likely MQL5\\Files folder (primarily Windows)."""
    cands: List[Path] = []

    # Common Windows user locations
    for env in ("APPDATA", "LOCALAPPDATA"):
        base = Path(os.getenv(env, "")) / "MetaQuotes" / "Terminal"
        if base.exists():
            cands += [d / "MQL5" / "Files" for d in base.glob("*")]
            cands.append(base / "Common" / "Files")

    # Program Files installs
    for pf in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = Path(os.getenv(pf, ""))
        if base.exists():
            cands.append(base / "MetaTrader 5" / "MQL5" / "Files")
            cands += list(base.glob("MetaTrader*/**/MQL5/Files"))

    # Generic fallback
    cands.append(Path.home() / "MQL5" / "Files")

    cands = _uniq_paths(cands)
    try:
        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        pass
    return cands[0] if cands else None

# -----------------------------------------------------------------------------
# Resolve base path for MT5 Files with precedence
# -----------------------------------------------------------------------------
env_mt5 = os.getenv("MT5_FILES_DIR")
if env_mt5 and Path(env_mt5).exists():
    base = Path(env_mt5)
elif SERVER_SETTINGS.mt5_dir and Path(SERVER_SETTINGS.mt5_dir).exists():
    base = Path(SERVER_SETTINGS.mt5_dir)
else:
    base = _auto_detect_mt5_files() or (Path.home() / "MQL5" / "Files")

SIGNALS   = (base / "Fluent_signals.jsonl").resolve()
HEARTBEAT = (base / "Fluent_heartbeat.txt").resolve()

# -----------------------------------------------------------------------------
# Snapshot scanning & selection
# -----------------------------------------------------------------------------
_PATTERNS = [
    "*Fluent_positions*.json*",
    "*position*.json*",
    "*positions*.json*",
    "*snapshot*.json*",
]

def _terminal_root_from_files_dir(files_dir: Path) -> Optional[Path]:
    """
    Given .../MetaQuotes/Terminal/<hash>/MQL5/Files, return .../MetaQuotes/Terminal.
    Works even if files_dir is Common/Files or a custom path.
    """
    try:
        parts = [p.name.lower() for p in files_dir.parts]
        if "terminal" in parts:
            idx = len(parts) - 1 - parts[::-1].index("terminal")
            return Path(*files_dir.parts[:idx+1])
    except Exception:
        pass
    return None

def _candidate_roots(files_dir: Path) -> List[Path]:
    """Return directories to scan: configured Files dir, Common\\Files, and sibling terminals' Files."""
    roots: List[Path] = [files_dir]
    term_root = _terminal_root_from_files_dir(files_dir)
    if term_root:
        common = term_root / "Common" / "Files"
        if common.exists():
            roots.append(common)
        for d in term_root.glob("*/MQL5/Files"):
            try:
                if d.resolve() != files_dir.resolve():
                    roots.append(d)
            except Exception:
                continue
    return _uniq_paths(roots)

def _scan_position_files(files_dir: Path) -> List[Path]:
    """Recursively find plausible snapshot files under candidate roots; newest first."""
    roots = _candidate_roots(files_dir)
    found: List[Path] = []
    for r in roots:
        for pat in _PATTERNS:
            try:
                for p in r.rglob(pat):
                    if p.is_file():
                        found.append(p)
            except Exception:
                continue
    # dedupe
    seen = set(); uniq: List[Path] = []
    for p in found:
        try:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp); uniq.append(rp)
        except Exception:
            continue
    try:
        uniq.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        pass
    return uniq

def _pick_best_snapshot(files_dir: Path) -> Optional[Path]:
    """
    Choose the newest snapshot in the configured Files dir, preferring our known names,
    and fall back to a recursive scan if none are valid.
    """
    # 1) Known filenames in the configured Files dir
    priority = [
        files_dir / "positions_snapshot.json",
        files_dir / "Fluent_positions.json",
        files_dir / "Fluent_position.json",
        files_dir / "positions.json",
    ]

    valid: list[Path] = []
    for cand in priority:
        try:
            if cand.exists() and cand.is_file():
                txt = _read_text_multi(cand)
                if txt.strip():
                    valid.append(cand)
        except Exception:
            continue

    if valid:
        # pick the most recently modified among valid files
        try:
            valid.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            pass
        return valid[0]

    # 2) Fallback: recursive scan across candidate roots (newest first)
    for cand in _scan_position_files(files_dir):
        try:
            txt = _read_text_multi(cand)
            if txt.strip():
                return cand
        except Exception:
            continue
    return None

# -----------------------------------------------------------------------------
# Update base at runtime
# -----------------------------------------------------------------------------
def _set_mt5_dir(new_dir: str) -> bool:
    global base, SIGNALS, HEARTBEAT
    p = Path(new_dir)
    if not p.exists():
        return False
    base = p
    SIGNALS = (base / "Fluent_signals.jsonl").resolve()
    HEARTBEAT = (base / "Fluent_heartbeat.txt").resolve()
    return True

# -----------------------------------------------------------------------------
# Text reading helpers (handle UTF-16/UTF-8/CP1252 etc.)
# -----------------------------------------------------------------------------
_ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252")

def _read_text_multi(path: Path) -> str:
    last_err = None
    for enc in _ENCODINGS:
        try:
            return path.read_text(encoding=enc, errors="strict")
        except Exception as e:
            last_err = e
            continue
    # be permissive fallback (ignore undecodable bytes)
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

# -----------------------------------------------------------------------------
# Misc helpers
# -----------------------------------------------------------------------------
def _tail_jsonl(path, limit):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            sz = f.tell()
            f.seek(max(0, sz - 1024 * 1024))  # last 1MB
            data = f.read().decode("utf-8", "ignore").splitlines()
        return [json.loads(ln) for ln in data[-limit:] if ln.strip()]
    except Exception:
        return []

def _num(x):
    try:
        n = float(x)
        if n != n or n in (float("inf"), float("-inf")):
            return None
        return n
    except Exception:
        return None

def _ts(rec):
    for k in ("t", "ts", "time"):
        n = _num(rec.get(k))
        if n is not None:
            return int(n)
    return None

def _profit(rec):
    n = rec.get("profit_usd")
    return float(n) if n is not None else None

def _join_key(rec):
    for k in ("gid", "oid", "id"):
        v = rec.get(k)
        s = (str(v).strip() if v is not None else "")
        if s:
            return s
    return ""

def _fmt_dt(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).strftime("%m/%d/%Y, %I:%M:%S %p")
    except Exception:
        return None

def _heartbeat_status():
    try:
        if not HEARTBEAT.exists():
            return "dead"
        raw = _read_text_multi(HEARTBEAT)
        # Keep digits only; support ms or s
        digits = re.findall(r"\d+", raw)
        if not digits:
            return "dead"
        ts = int(digits[0])
        # If ts looks like ms, convert
        if ts > 10_000_000_000:  # > ~ 2286-11-20 in seconds
            ts //= 1000
        age = time.time() - ts
        if age < 15:  return "ok"
        if age < 60:  return "stale"
        return "dead"
    except Exception:
        return "dead"

# ---------------------------------------------------------------------------
# JSON parsing helpers for positions files
# ---------------------------------------------------------------------------
def _parse_positions_json(text: str) -> List[dict]:
    """
    Accept either:
      - a top-level list of positions: [ {...}, {...} ]
      - or an object with an array field: { "positions": [ ... ] } / { "data": [...] } / { "items": [...] }
    Return a list (possibly empty).
    """
    try:
        if not text or not text.strip():
            return []
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("positions", "data", "items"):
                val = data.get(key)
                if isinstance(val, list):
                    return val
    except Exception:
        pass
    return []

# ---------------------------------------------------------------------------
# Positions & PnL helpers (use selector each time)
# ---------------------------------------------------------------------------
def _load_open_positions_count() -> int:
    """Count entries in the most recent valid snapshot (authoritative MT5 state)."""
    try:
        cand = _pick_best_snapshot(base)
        if not cand or not cand.exists():
            return 0
        text = _read_text_multi(cand)
        lst = _parse_positions_json(text)
        return len(lst)
    except Exception:
        return 0

def _pnl_30d_usd() -> float:
    """Sum profit_usd (or profit) from CLOSE lines within last 30 days."""
    try:
        if not SIGNALS.exists():
            return 0.0
        cutoff = time.time() - 30*24*3600
        total = 0.0
        with SIGNALS.open("rb") as f:
            f.seek(0, os.SEEK_END)
            sz = f.tell()
            f.seek(max(0, sz - 2*1024*1024))  # last 2MB
            data = f.read().decode("utf-8", "ignore").splitlines()
        for ln in data:
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if str(r.get("action") or "").upper() != "CLOSE":
                continue
            ts = _ts(r)
            if ts is not None and ts < cutoff:
                continue
            p = _profit_usd_only(r)
            if p is None:
                continue
            try:
                total += float(p or 0)
            except Exception:
                pass
        return round(total, 2)
    except Exception:
        return 0.0

# -----------------------------------------------------------------------------
# Simple in-memory UI state
# -----------------------------------------------------------------------------
STATE = {"running": False, "paused": False, "quality": 60}

# -----------------------------------------------------------------------------
# API: health / paths / metrics / signals
# -----------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.0", "py": sys.version.split()[0]}

@app.get("/api/paths")
def paths():
    best = _pick_best_snapshot(base)
    return {
        "mt5_files_dir": str(base),
        "signals": str(SIGNALS),
        "heartbeat": str(HEARTBEAT),
        "positions": str(best) if best else "",
        "heartbeat_status": _heartbeat_status(),
        "signals_exists": SIGNALS.exists(),
        "heartbeat_exists": HEARTBEAT.exists(),
        "positions_exists": bool(best and best.exists()),
        "env_MT5_FILES_DIR": os.getenv("MT5_FILES_DIR") or "",
        "saved_settings": _load_server_settings().dict(),
    }

@app.get("/api/metrics")
def metrics():
    hb = _heartbeat_status()
    opens = closes = mods = modtp = emerg = 0
    try:
        if SIGNALS.exists():
            with SIGNALS.open("rb") as f:
                f.seek(0, os.SEEK_END)
                sz = f.tell()
                f.seek(max(0, sz - 512 * 1024))  # last 512KB
                data = f.read().decode("utf-8", "ignore").splitlines()[-1000:]
            for ln in data:
                try:
                    a = json.loads(ln).get("action", "")
                except Exception:
                    continue
                if a == "OPEN": opens += 1
                elif a == "CLOSE": closes += 1
                elif a == "MODIFY": mods += 1
                elif a == "MODIFY_TP": modtp += 1
                elif a == "EMERGENCY_CLOSE_ALL": emerg += 1
    except Exception:
        pass

    open_positions = _load_open_positions_count()
    pnl30 = _pnl_30d_usd()

    counts = {
        "open": opens, "close": closes, "modify": mods, "modify_tp": modtp, "emergency": emerg,
        "open_positions": open_positions
    }

    return {
        "heartbeat": hb,
        "counts": counts,
        "state": STATE,
        "open_positions": open_positions,
        "pnl_30d": pnl30,
        "pnl": pnl30,     # compat alias
        "pnl30": pnl30,   # compat alias
    }

@app.get("/api/signals")
def signals(limit: int = 200):
    return JSONResponse(_tail_jsonl(str(SIGNALS), limit))

# ---------------------------------------------------------------------------
# API: current open positions (from EA snapshot)
# ---------------------------------------------------------------------------
@app.get("/api/positions")
def api_positions():
    try:
        cand = _pick_best_snapshot(base)
        if not cand or not cand.exists():
            return JSONResponse([])
        text = _read_text_multi(cand)
        lst = _parse_positions_json(text)
        return JSONResponse(lst)
    except Exception:
        return JSONResponse([])

# -----------------------------------------------------------------------------
# API: emergency close
# -----------------------------------------------------------------------------
@app.post("/api/emergency-close-all")
def emergency_close_all():
    gid = int(time.time() * 1000)
    rec = {"action": "EMERGENCY_CLOSE_ALL", "id": str(gid), "t": int(time.time()), "source": "WEB", "confirm": "YES"}
    SIGNALS.parent.mkdir(parents=True, exist_ok=True)
    with SIGNALS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n"); f.flush(); os.fsync(f.fileno())
    return {"ok": True, "gid": gid}

# -----------------------------------------------------------------------------
# Websocket: stream new JSONL lines (auto-handles rotation & path changes)
# -----------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_events(ws: WebSocket):
    await ws.accept()
    last_size = SIGNALS.stat().st_size if SIGNALS.exists() else 0
    last_path = str(SIGNALS)
    try:
        while True:
            await asyncio.sleep(0.8)

            # if path changed at runtime (mt5_dir switched), reset
            if str(SIGNALS) != last_path:
                last_path = str(SIGNALS)
                last_size = SIGNALS.stat().st_size if SIGNALS.exists() else 0

            if not SIGNALS.exists():
                last_size = 0
                continue

            size = SIGNALS.stat().st_size
            if size < last_size:
                last_size = 0  # rotation/truncate
            if size > last_size:
                with SIGNALS.open("rb") as f:
                    f.seek(last_size)
                    chunk = f.read(size - last_size).decode("utf-8", "ignore")
                last_size = size
                for ln in chunk.splitlines():
                    ln = ln.strip()
                    if ln:
                        await ws.send_text(ln)
    except WebSocketDisconnect:
        return

# -----------------------------------------------------------------------------
# API: basic state controls
# -----------------------------------------------------------------------------
class PauseReq(BaseModel):
    paused: bool

class QualityReq(BaseModel):
    threshold: int

@app.get("/api/state")
def get_state():
    return {
        "running": STATE["running"],
        "paused": STATE["paused"],
        "quality": STATE["quality"],
        "heartbeat": _heartbeat_status(),
    }

@app.post("/api/start")
def start():
    STATE["running"] = True
    return {"ok": True, **STATE}

@app.post("/api/stop")
def stop():
    STATE["running"] = False
    return {"ok": True, **STATE}

@app.post("/api/pause")
def pause(req: PauseReq):
    STATE["paused"] = bool(req.paused)
    return {"ok": True, **STATE}

@app.post("/api/set-quality")
def set_quality(req: QualityReq):
    q = max(0, min(100, int(req.threshold)))
    STATE["quality"] = q
    return {"ok": True, **STATE}

# -----------------------------------------------------------------------------
# API: Channel performance aggregation
# -----------------------------------------------------------------------------
@app.get("/api/channel-performance")
def channel_performance(limit: int = 5000):
    """
    Minimal robust aggregation:
    - JOIN CLOSE->OPEN via gid/oid/id to pick channel from OPEN
    - Filter internal sources
    - Win% from profit>0
    """
    rows = _tail_jsonl(str(SIGNALS), max(100, min(limit, 20000)))

    # Index OPENs by join key
    opens_by_key = {}
    for r in rows:
        if str(r.get("action") or "").upper() != "OPEN":
            continue
        k = _join_key(r)
        if k:
            opens_by_key[k] = r

    # Aggregate
    agg = {}
    for r in rows:
        a = str(r.get("action") or "").upper()
        src = (r.get("source") or "").strip()

        # Resolve canonical channel (map CLOSE back to its OPEN if needed)
        if a == "CLOSE":
            if not src or src in INTERNAL_SOURCES:
                k = _join_key(r)
                if k and k in opens_by_key:
                    src = (opens_by_key[k].get("source") or "").strip()

        # Drop internal/unknown
        if not src or src in INTERNAL_SOURCES:
            continue

        slot = agg.get(src)
        if not slot:
            slot = agg[src] = {
                "opens": 0,
                "closes": 0,
                "wins": 0,
                "totalClosed": 0,
                "confSum": 0.0,
                "confN": 0,
                "scoreSum": 0.0,
                "scoreN": 0,
                "lastT": 0,
            }

        if a == "OPEN":
            slot["opens"] += 1
            conf = r.get("confidence")
            if isinstance(conf, (int, float)):
                slot["confSum"] += float(conf); slot["confN"] += 1
            score = r.get("signal_score")
            if not isinstance(score, (int, float)):
                score = r.get("score")
            if isinstance(score, (int, float)):
                slot["scoreSum"] += float(score); slot["scoreN"] += 1

        elif a == "CLOSE":
            slot["closes"] += 1
            slot["totalClosed"] += 1
            p = _profit(r)
            if p is not None and p > 0:
                slot["wins"] += 1

        t = _ts(r)
        if t is not None and t > (slot["lastT"] or 0):
            slot["lastT"] = t

    out = []
    for channel, s in agg.items():
        total = s["totalClosed"]
        win_rate = (s["wins"] / total * 100.0) if total > 0 else None
        avg_conf = (s["confSum"] / s["confN"]) if s["confN"] > 0 else None
        explicit_score = (s["scoreSum"] / s["scoreN"]) if s["scoreN"] > 0 else None
        signal_score = explicit_score if explicit_score is not None else avg_conf

        out.append({
            "channel": channel,
            "signal_score": round(signal_score, 1) if isinstance(signal_score, (int, float)) else None,
            "win_rate": round(win_rate, 1) if isinstance(win_rate, (int, float)) else None,
            "opens": int(s["opens"]),
            "closes": int(s["closes"]),
            "avg_confidence": round(avg_conf, 1) if isinstance(avg_conf, (int, float)) else None,
            "last_signal": _fmt_dt(s["lastT"]) or None,
        })

    out.sort(key=lambda r: ((r["win_rate"] if isinstance(r["win_rate"], (int, float)) else -1.0), r["closes"]), reverse=True)
    return JSONResponse(out)

# -----------------------------------------------------------------------------
# API: Web settings (GET/POST) + MT5 auto-detect
# -----------------------------------------------------------------------------
@app.get("/api/settings")
def get_settings():
    s = _load_server_settings()
    return {
        "api_id": s.api_id or "",
        "api_hash": s.api_hash or "",
        "phone": s.phone or "",
        "mt5_dir": s.mt5_dir or str(base),
        "sources": s.sources or [],
    }

@app.post("/api/settings")
def save_settings(s: BridgeSettings):
    current = _load_server_settings()

    # if mt5_dir provided and different, try to apply live
    if s.mt5_dir and s.mt5_dir != current.mt5_dir:
        _set_mt5_dir(s.mt5_dir)

    SETTINGS_JSON.write_text(json.dumps({
        "api_id": s.api_id if s.api_id is not None else current.api_id,
        "api_hash": s.api_hash if s.api_hash is not None else current.api_hash,
        "phone": s.phone if s.phone is not None else current.phone,
        "mt5_dir": s.mt5_dir if s.mt5_dir is not None else (current.mt5_dir or str(base)),
        "sources": s.sources if s.sources else (current.sources or []),
    }, indent=2))

    return {"ok": True, "mt5_dir": str(base)}

@app.get("/api/mt5/auto_detect")
def auto_detect_mt5_dir():
    env = os.getenv("MT5_FILES_DIR")
    if env and Path(env).exists():
        return {"ok": True, "mt5_dir": str(Path(env))}
    cand = _auto_detect_mt5_files()
    if cand:
        return {"ok": True, "mt5_dir": str(cand)}
    return {"ok": False, "mt5_dir": None}

# -----------------------------------------------------------------------------
# Static SPA (serve built React dashboard from /app)
# -----------------------------------------------------------------------------
DIST = Path(__file__).parent / "dist"     # put your built frontend here

if DIST.exists():
    # serve hashed assets (JS/CSS) under /assets
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/app")
    def serve_app_index():
        """Single-page app entry (kept at /app so / stays API JSON)."""
        return FileResponse(DIST / "index.html")

# -----------------------------------------------------------------------------
# Root
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "Fluent Signal Copier API"}
