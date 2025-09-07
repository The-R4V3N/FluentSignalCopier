# backend/app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Iterable, Dict, Any
import asyncio, json, time, os, sys, re
import shutil
import subprocess

# --- Version helpers ----------------------------------------------------------

def _compute_version() -> dict:
    """
    Compute version info dynamically on each call.

    Safety net:
    - If APP_VERSION is set, use that (and APP_COMMIT if provided), skipping git.
    - Otherwise, read from the local git repo (tags + short commit).
    """
    # ---- env override (CI / packaged builds) ----
    env_ver = os.getenv("APP_VERSION")
    env_commit = os.getenv("APP_COMMIT")

    if env_ver:
        return {
            "app": "Fluent Web Backend",
            "version": env_ver,
            "git_commit": env_commit or "unknown",
            "dirty": False,
            "py": sys.version.split()[0],
            "built_at": datetime.utcnow().isoformat() + "Z",
        }

    # ---- git-based fallback ----
    def _run(cmd: list[str]) -> str | None:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
            return out or None
        except Exception:
            return None

    tag = _run(["git", "describe", "--tags", "--abbrev=0"])
    commit = _run(["git", "rev-parse", "--short", "HEAD"])
    dirty = bool(_run(["git", "status", "--porcelain"]))

    return {
        "app": "Fluent Web Backend",
        "version": tag or "0.0.0",
        "git_commit": commit or "unknown",
        "dirty": dirty,
        "py": sys.version.split()[0],
        "built_at": datetime.utcnow().isoformat() + "Z",
    }

# NOTE: removed the global VERSION = _compute_version()


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

# If you need cookies/credentials, list explicit origins via env.
# Example: CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
_origins_env = os.getenv("CORS_ORIGINS")
if _origins_env:
    origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Safe local defaults without credentials
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
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
    for enc in _ENCODINGS:
        try:
            return path.read_text(encoding=enc, errors="strict")
        except Exception:
            continue
    # be permissive fallback (ignore undecodable bytes)
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

# --- Channels aggregation -----------------------------------------------------
from dataclasses import dataclass, asdict

@dataclass
class ChanAgg:
    opens: int = 0
    closes: int = 0
    wins: int = 0
    last_signal_ts: int | None = None
    last_signal_iso: str | None = None
    last_action: str | None = None
    last_symbol: str | None = None
    avg_conf_sum: float = 0.0
    avg_conf_n: int = 0

def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except Exception:
                # ignore malformed jsonl rows
                continue

def _safe_int(v, default=None):
    try:
        if isinstance(v, (int, float)):
            return int(v)
        return int(str(v))
    except Exception:
        return default

def _safe_float(v, default=None):
    try:
        return float(v)
    except Exception:
        try:
            return float(str(v).replace(',', '.'))
        except Exception:
            return default

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

def read_last_jsonl(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    # Efficient-ish tail read
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            block = 4096
            data = b""
            while len(rows) < limit and f.tell() > 0:
                seek = max(0, f.tell() - block)
                f.seek(seek)
                chunk = f.read(min(block, f.tell()))
                f.seek(seek)
                data = chunk + data
                if seek == 0:
                    break
            # split lines and parse JSON
            for line in data.splitlines()[::-1]:  # newest last in file -> iterate from end
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8", errors="ignore"))
                    rows.append(obj)
                except Exception:
                    continue
                if len(rows) >= limit:
                    break
    except Exception:
        return []
    return rows

# -----------------------------------------------------------------------------
# JSON parsing helpers for positions files
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Positions & PnL helpers (use selector each time)
# -----------------------------------------------------------------------------
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
            f.seek(max(0, f.tell() - 2*1024*1024))  # last 2MB
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
            p = _profit(r)
            if p is None:
                continue
            try:
                total += float(p or 0)
            except Exception:
                pass
        return round(total, 2)
    except Exception:
        return 0.0

def _profit_usd_or_any(rec):
    """
    Return a numeric profit from a CLOSE record, or None.
    Preference: profit_usd, then net_profit, pnl, profit.
    """
    for k in ("profit_usd", "net_profit", "pnl", "profit"):
        v = rec.get(k)
        try:
            n = float(v)
            if n == n and n not in (float("inf"), float("-inf")):
                return n
        except Exception:
            continue
    return None

def _win_rate_30d() -> float | None:
    """
    Win% over the last 30 days from CLOSE lines that have a numeric profit.
    Returns a float in [0..100], or None if no qualifying closes exist.
    """
    try:
        if not SIGNALS.exists():
            return None
        cutoff = time.time() - 30 * 24 * 3600
        wins = 0
        total = 0
        with SIGNALS.open("rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 2 * 1024 * 1024))  # last 2MB
            data = f.read().decode("utf-8", "ignore").splitlines()

        for ln in data:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if str(r.get("action") or "").upper() != "CLOSE":
                continue
            ts = _ts(r)
            if ts is None or ts < cutoff:
                continue
            p = _profit_usd_or_any(r)
            if p is None:
                continue  # only count closes with numeric profit
            total += 1
            if p > 0:
                wins += 1

        if total == 0:
            return None
        return round((wins / total) * 100, 1)
    except Exception:
        return None

# -----------------------------------------------------------------------------
# Simple in-memory UI state
# -----------------------------------------------------------------------------
STATE = {"running": False, "paused": False, "quality": 60}

# -----------------------------------------------------------------------------
# API: health / paths / metrics / signals
# -----------------------------------------------------------------------------
@app.get("/api/health")
def health():
    v = _compute_version()
    payload = {
        "ok": True,
        "heartbeat": _heartbeat_status(),
        "app": v.get("app"),
        "version": v.get("version"),
        "git_commit": v.get("git_commit"),
        "py": v.get("py"),
        "built_at": v.get("built_at"),
        # intentionally omitting 'dirty' from /api/health response
    }
    return payload

@app.get("/api/version")
def api_version():
    return _compute_version()

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
                f.seek(max(0, f.tell() - 512 * 1024))  # last 512KB
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
    win30 = _win_rate_30d()

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
        "pnl": pnl30,           # compat alias
        "pnl30": pnl30,         # compat alias
        "win_rate_30d": win30,
        "winrate": win30,       # optional alias for convenience
    }

@app.get("/api/signals")
def signals(limit: int = 200):
    return JSONResponse(_tail_jsonl(str(SIGNALS), limit))

# -----------------------------------------------------------------------------
# API: current open positions (from EA snapshot)
# -----------------------------------------------------------------------------
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
# API: clear signal history (single source of truth)
# -----------------------------------------------------------------------------
@app.post("/api/signals/clear")
def api_signals_clear(backup: bool = True):
    """
    Clear the signals history on disk.
    Optional ?backup=false to skip creating a .bak copy before truncation.
    """
    try:
        made_backup = False
        if SIGNALS.exists():
            if backup:
                ts = int(time.time())
                bak = SIGNALS.with_name(f"{SIGNALS.stem}.{ts}.bak{SIGNALS.suffix}")
                shutil.copy2(SIGNALS, bak)
                made_backup = True
            # Truncate file
            SIGNALS.write_text("", encoding="utf-8")
        return {"ok": True, "cleared": True, "backup": made_backup}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# Back-compat / friendly alias; delegates to the same logic
@app.post("/api/history/clear")
def clear_history(backup: bool = True):
    return api_signals_clear(backup=backup)

# -----------------------------------------------------------------------------
# Websocket: stream new JSONL lines (auto-handles rotation & path changes)
# -----------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_events(ws: WebSocket):
    await ws.accept()
    try:
        last_path = str(SIGNALS)
        try:
            last_size = SIGNALS.stat().st_size if SIGNALS.exists() else 0
        except FileNotFoundError:
            last_size = 0

        while True:
            await asyncio.sleep(0.8)

            # if path changed at runtime (mt5_dir switched), reset
            if str(SIGNALS) != last_path:
                last_path = str(SIGNALS)
                try:
                    last_size = SIGNALS.stat().st_size if SIGNALS.exists() else 0
                except FileNotFoundError:
                    last_size = 0
                continue

            if not SIGNALS.exists():
                last_size = 0
                continue

            # Safe stat (file may rotate)
            try:
                size = SIGNALS.stat().st_size
            except FileNotFoundError:
                last_size = 0
                continue

            if size < last_size:
                # rotation/truncate
                last_size = 0

            if size > last_size:
                try:
                    with SIGNALS.open("rb") as f:
                        f.seek(last_size)
                        chunk = f.read(size - last_size).decode("utf-8", "ignore")
                except FileNotFoundError:
                    last_size = 0
                    continue

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
    - Win% from profit>0 (any profit field)
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
            p = _profit_usd_or_any(r)
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

@app.get("/api/channels")
def api_channels(limit: int = 100):
    """
    Aggregate real channel stats from Fluent_signals.jsonl.
    Returns: { channels: [{channel, opens, closes, win_rate, avg_confidence, last_signal, last_action, last_symbol}], updated_at }
    """
    if "SIGNALS" not in globals():
        return JSONResponse({"channels": [], "updated_at": datetime.utcnow().isoformat()+"Z"})

    aggs: dict[str, ChanAgg] = {}

    for rec in _iter_jsonl(SIGNALS):
        # expected fields commonly present in your pipeline
        action = (rec.get("action") or "").upper()  # "OPEN", "CLOSE", ...
        source = (rec.get("source") or "").strip()  # channel name
        if not source:
            # Some CLOSE lines historically missed source; skip those
            continue

        ts = _safe_int(rec.get("t")) or _safe_int(rec.get("time"))
        sym = rec.get("symbol")
        conf = _safe_float(rec.get("confidence"))

        agg = aggs.setdefault(source, ChanAgg())

        if action == "OPEN":
            agg.opens += 1
            if conf is not None:
                agg.avg_conf_sum += conf
                agg.avg_conf_n += 1

        elif action == "CLOSE":
            agg.closes += 1
            profit = _safe_float(rec.get("profit"))
            if profit is not None and profit > 0:
                agg.wins += 1

        # track last seen info
        if ts is not None and (agg.last_signal_ts is None or ts > agg.last_signal_ts):
            agg.last_signal_ts = ts
            try:
                agg.last_signal_iso = datetime.utcfromtimestamp(ts).isoformat() + "Z"
            except Exception:
                agg.last_signal_iso = None
            agg.last_action = action
            agg.last_symbol = sym

    rows = []
    for ch, a in aggs.items():
        win_rate = None
        if a.closes > 0:
            win_rate = round(100.0 * a.wins / a.closes, 2)

        avg_conf = None
        if a.avg_conf_n > 0:
            avg_conf = round(a.avg_conf_sum / a.avg_conf_n, 2)

        rows.append({
            "channel": ch,
            "opens": a.opens,
            "closes": a.closes,
            "win_rate": win_rate,
            "avg_confidence": avg_conf,
            "last_signal": a.last_signal_iso,
            "last_action": a.last_action,
            "last_symbol": a.last_symbol,
        })

    # sort by most recent activity, then by closes desc
    rows.sort(key=lambda r: (r["last_signal"] is None, r["last_signal"]), reverse=True)
    if limit and limit > 0:
        rows = rows[:limit]

    return JSONResponse({
        "channels": rows,
        "updated_at": datetime.utcnow().isoformat() + "Z"
    })

@app.get("/api/history")
def api_history(limit: int = 100):
    """
    Return the last `limit` signals from Fluent_signals.jsonl, newest first.
    Shape matches frontend `Rec` as closely as possible.
    """
    limit = max(1, min(int(limit), 500))  # safety clamp
    raw = read_last_jsonl(SIGNALS, limit)

    # normalize common fields into your RecentSignalsTable Rec shape
    def norm(r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "t": r.get("t") or r.get("time") or r.get("timestamp"),
            "action": r.get("action"),
            "symbol": r.get("symbol"),
            "side": r.get("side"),
            "order_type": r.get("order_type") or r.get("type"),
            "entry": r.get("entry") or r.get("price") or r.get("entry_price"),
            "entry_ref": r.get("entry_ref"),
            "sl": r.get("sl") or r.get("stop_loss") or r.get("stoploss"),
            "tps": (
                r.get("tps")
                or r.get("tp_list")
                or ([r.get("tp")] if isinstance(r.get("tp"), (int, float)) else None)
            ),
            "source": r.get("source") or r.get("channel"),
            "confidence": r.get("confidence"),
            "new_sl": r.get("new_sl"),
            "new_tps_csv": r.get("new_tps_csv"),
            "tp_slot": r.get("tp_slot"),
            "tp_to": r.get("tp_to"),
        }

    items = [norm(x) for x in raw]
    # ensure newest first (some tails already return newest-first; we sort anyway)
    items.sort(key=lambda x: x.get("t") or 0, reverse=True)
    return {"items": items}

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
    
    # Serve index.html for any other path so SPA routes work (e.g., /dashboard)
    @app.get("/{full_path:path}")
    def spa_catch_all(full_path: str):
        return FileResponse(DIST / "index.html")

# -----------------------------------------------------------------------------
# Root
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "Fluent Signal Copier API"}
