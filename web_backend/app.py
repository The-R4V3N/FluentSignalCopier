# backend/app.py

# Licensed under the Fluent Signal Copier Limited Use License v1.0
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Iterable, Dict, Any
from glob import glob
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

# -----------------------------------------------------------------------------
# Close with PnL
# -----------------------------------------------------------------------------
def _enrich_closes_with_pnl(rows: list[dict]) -> list[dict]:
    """
    Attach 'pnl' (float) and 'result' ('WIN'|'LOSS'|'BREAKEVEN') to CLOSE rows.

    It tries several common ledgers:
      - Fluent_positions.json
      - positions.json
      - trades.jsonl / Fluent_trades.jsonl  (json-lines)
    And matches by one of: (gid|oid|ticket|order_id) + symbol.
    """
    if not rows:
        return rows

    # Build fast lookups for CLOSE rows we want to enrich
    closes_idx = []
    for i, r in enumerate(rows):
        if str(r.get("action", "")).upper() == "CLOSE":
            closes_idx.append(i)

    if not closes_idx:
        return rows

    def _key(r: dict) -> tuple:
        # Try the most stable identifiers first; fall back to None
        for k in ("gid", "oid", "ticket", "order_id", "id"):
            v = r.get(k)
            if v not in (None, "", 0):
                return (str(v), r.get("symbol", ""))
        # Fallback: time+symbol (weak)
        return (f"{r.get('t','')}", r.get("symbol",""))

    need = {_key(rows[i]) for i in closes_idx}

    # Load possible ledgers
    candidates = [
        "Fluent_positions.json",
        "positions.json",
        "Fluent_trades.jsonl",
        "trades.jsonl",
    ]
    ledgers = []
    for pat in candidates:
        for p in glob(pat):
            ledgers.append(p)

    # Build a map: (id, symbol) -> {pnl: float}
    pnl_map: dict[tuple, dict] = {}
    for path in ledgers:
        try:
            if path.endswith(".jsonl"):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            j = json.loads(line)
                        except Exception:
                            continue
                        if str(j.get("action","")).upper() != "CLOSE":
                            continue
                        k = _key(j)
                        if k in need:
                            pnl = j.get("pnl", j.get("profit", j.get("pl")))
                            if pnl is not None:
                                pnl_map[k] = {
                                    "pnl": float(pnl),
                                }
            else:
                with open(path, "r", encoding="utf-8") as f:
                    j = json.load(f)
                # accept either list or {items:[...]}
                items = j if isinstance(j, list) else j.get("items", [])
                for it in items:
                    if str(it.get("action","")).upper() != "CLOSE":
                        continue
                    k = _key(it)
                    if k in need:
                        pnl = it.get("pnl", it.get("profit", it.get("pl")))
                        if pnl is not None:
                            pnl_map[k] = {
                                "pnl": float(pnl),
                            }
        except Exception:
            # non-fatal; we just skip unreadable ledgers
            continue

    # Apply to rows
    for i in closes_idx:
        r = rows[i]
        k = _key(r)
        extra = pnl_map.get(k)
        if not extra:
            continue
        pnl = extra.get("pnl")
        if pnl is None:
            continue
        r["pnl"] = pnl
        r["result"] = "BREAKEVEN" if abs(pnl) < 1e-6 else ("WIN" if pnl > 0 else "LOSS")

    return rows

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
    
def _heartbeat_info():
    """
    Returns (status, age_seconds, ts_seconds).

    status: "ok" (<15s), "stale" (15–60s), "dead" (missing or >60s)
    age_seconds: None if unknown
    ts_seconds: the raw heartbeat timestamp in seconds (None if unknown)
    """
    try:
        if not HEARTBEAT.exists():
            return "dead", None, None

        raw = _read_text_multi(HEARTBEAT)
        digits = re.findall(r"\d+", raw)
        if not digits:
            return "dead", None, None

        ts = int(digits[0])
        if ts > 10_000_000_000:  # ms → s
            ts //= 1000

        age = max(0, int(time.time() - ts))
        if age < 15:
            status = "ok"
        elif age < 60:
            status = "stale"
        else:
            status = "dead"
        return status, age, ts
    except Exception:
        return "dead", None, None

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
    hb_status, hb_age, hb_ts = _heartbeat_info()
    payload = {
        "ok": True,
        "heartbeat": hb_status,
        "heartbeat_age_seconds": hb_age,
        "heartbeat_ts": hb_ts,
        "app": v.get("app"),
        "version": v.get("version"),
        "git_commit": v.get("git_commit"),
        "py": v.get("py"),
        "built_at": v.get("built_at"),
    }
    return payload

@app.get("/api/heartbeat")
def api_heartbeat():
    status, age, ts = _heartbeat_info()
    return {"status": status, "age_seconds": age, "ts": ts}

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

            # path may change if mt5_dir switches
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

                # Parse all new lines into JSON objects
                batch = []
                for ln in chunk.splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                        batch.append(obj)
                    except Exception:
                        # if a line is malformed, just forward it as-is for visibility
                        await ws.send_text(ln)
                        continue

                if not batch:
                    continue

                # Enrich CLOSE rows with pnl/result
                batch = _enrich_closes_with_pnl(batch)

                # Send as JSON strings (frontend already JSON.parses)
                for obj in batch:
                    await ws.send_text(json.dumps(obj))
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

    # enrich CLOSE lines with pnl/result if we can find them
    raw = _enrich_closes_with_pnl(raw)

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
            "tps": (r.get("tps") or r.get("tp_list")
                    or ([r.get("tp")] if isinstance(r.get("tp"), (int, float)) else None)),
            "source": r.get("source") or r.get("channel"),
            "confidence": r.get("confidence"),
            "new_sl": r.get("new_sl"),
            "new_tps_csv": r.get("new_tps_csv"),
            "tp_slot": r.get("tp_slot"),
            "tp_to": r.get("tp_to"),
            "risk_percent": r.get("risk_percent") or r.get("risk"),

            # pass through enriched fields for CLOSE rows
            "pnl": r.get("pnl") or r.get("profit") or r.get("profit_usd"),
            "result": r.get("result"),  # "WIN" | "LOSS" | "BREAKEVEN"
            
            # (optional) keep join keys if present; helps future correlations
            "gid": r.get("gid"),
            "oid": r.get("oid"),
            "id": r.get("id"),
            "ticket": r.get("ticket"),
            "order_id": r.get("order_id"),
        }

    items = [norm(x) for x in raw]
    items.sort(key=lambda x: x.get("t") or 0, reverse=True)
    return {"items": items}

#------------------------------------------------------------------------------
# EA Settings JSON (read/write)
#------------------------------------------------------------------------------
EA_SETTINGS = (base / "Fluent_ea_settings.json").resolve()

class EaSettings(BaseModel):
    # ===== FILE CONFIGURATION =====
    InpDebug: bool = False
    InpSignalFileName: str = "Fluent_signals.jsonl"
    InpHeartbeatFileName: str = "Fluent_heartbeat.txt"
    InpPositionsFileName: str = "Fluent_positions.json"

    # ===== BRAKE EVEN =====
    InpBE_Enable: bool = True
    InpBE_TriggerTP: int = 1
    InpBE_AutoOnTP1: bool = True
    InpBE_Logging: bool = True
    InpBE_CleanupEveryMin: int = 60
    InpBE_OffsetPoints: int = 0

    # ===== SYMBOL CONFIGURATION =====
    InpSymbolPrefix: str = ""
    InpSymbolSuffix: str = ""
    InpSymbolSuffixVariants: str = ""

    # ===== TRADING PARAMETERS =====
    InpDefaultLots: float = 0.01
    InpRiskPercent: float = 1.0
    InpMagic: int = 20250810
    InpSlippagePoints: int = 50
    InpAllowBuys: bool = True
    InpAllowSells: bool = True
    InpCloseConflicts: bool = False

    # ===== HEARTBEAT CONFIGURATION =====
    InpEnableHeartbeat: bool = True
    HeartbeatSeconds: int = 5
    InpHeartbeatTimeout: int = 60
    InpSnapshotOnlyMagic: bool = False

    # ===== MULTI-POSITION MANAGEMENT =====
    InpMaxPositions: int = 5
    InpSkipBadTPs: bool = True
    InpPositionsToOpen: int = 0
    InpRiskPerLeg: bool = False
    InpUseCustomLots: bool = False
    InpTP1_Lots: float = 0.02
    InpTP2_Lots: float = 0.01
    InpTP3_Lots: float = 0.01
    InpTP4_Lots: float = 0.01
    InpTP5_Lots: float = 0.01

    # ===== SAFETY CAPS =====
    InpMaxLotOverall: float = 0.05
    InpMaxLot_Metal: float = 0.05
    InpMaxLot_Oil: float = 0.05
    InpMaxLot_Index: float = 0.05
    InpMaxLot_FX: float = 0.05
    InpMaxLot_Crypto: float = 0.05
    InpRiskDollarCap: float = 15.0

    # ===== SYSTEM FEATURES =====
    InpWriteSnapshots: bool = True
    InpSoundAlerts: bool = True
    InpSourceTags: bool = True

    # ===== ALERT CONFIGURATION =====
    InpAlertOnOpen: bool = True
    InpAlertOnClose: bool = True
    InpAlertOnEmergency: bool = True
    InpAlertOnModify: bool = False

    # ===== HEARTBEAT WARNING CONTROL =====
    InpHeartbeatPopupAlerts: bool = False
    InpHeartbeatPrintWarnings: bool = True
    InpHeartbeatWarnInterval: int = 300

    # ===== TIME MANAGEMENT =====
    InpTimeFilter: bool = True
    InpStartTimeHHMM: str = "01:00"
    InpEndTimeHHMM: str = "23:59"
    InpTradeMonday: bool = True
    InpTradeTuesday: bool = True
    InpTradeWednesday: bool = True
    InpTradeThursday: bool = True
    InpTradeFriday: bool = True
    InpTradeSaturday: bool = False
    InpTradeSunday: bool = False

    @field_validator("InpStartTimeHHMM", "InpEndTimeHHMM", mode="before")
    def _hhmm(cls, v):
        s = str(v or "")
        parts = s.split(":")
        if len(parts) != 2:
            return "00:00"
        try:
            hh = f"{int(parts[0]) % 24:02d}"
            mm = f"{int(parts[1]) % 60:02d}"
            return f"{hh}:{mm}"
        except Exception:
            return "00:00"

def _load_ea_settings() -> EaSettings:
    try:
        if EA_SETTINGS.exists():
            raw = _read_text_multi(EA_SETTINGS)
            data = json.loads(raw)
            return EaSettings(**data)
    except Exception as e:
        print(f"[EA Settings] Load error: {e}")
    return EaSettings()

def _save_ea_settings(obj: EaSettings) -> None:
    try:
        EA_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        data = obj.model_dump()
        EA_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[EA Settings] Saved to {EA_SETTINGS}")
    except Exception as e:
        print(f"[EA Settings] Save error: {e}")
        raise

@app.get("/api/ea-settings")
def get_ea_settings():
    """Load EA settings from Fluent_ea_settings.json"""
    try:
        settings = _load_ea_settings()
        return JSONResponse(settings.model_dump())
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to load EA settings: {str(e)}"}, 
            status_code=500
        )

@app.post("/api/ea-settings")
def set_ea_settings(settings: EaSettings):
    """Save EA settings to Fluent_ea_settings.json"""
    try:
        # Validate and save
        _save_ea_settings(settings)
        
        # Return success with the saved settings
        return JSONResponse({
            "ok": True, 
            "saved": settings.model_dump(),
            "path": str(EA_SETTINGS)
        })
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": f"Failed to save EA settings: {str(e)}"}, 
            status_code=500
        )
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
