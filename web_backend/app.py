# backend/app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
import asyncio, json, time, os, sys
from collections import defaultdict
from datetime import datetime


# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # safe fallback: .env support optional
    pass

app = FastAPI(title="Fluent Web Backend")

# Resolve MT5 paths
MT5_FILES_DIR = os.getenv("MT5_FILES_DIR")
if not MT5_FILES_DIR:
    # optional fallback: user’s home
    MT5_FILES_DIR = str(Path.home() / "MQL5" / "Files")

SIGNALS = Path(MT5_FILES_DIR) / "Fluent_signals.jsonl"
HEARTBEAT = Path(MT5_FILES_DIR) / "fluent_heartbeat.txt"

# simple in-memory state (persist if you want later)
STATE = {"running": False, "paused": False, "quality": 60}

class PauseReq(BaseModel):
    paused: bool

class QualityReq(BaseModel):
    threshold: int

# CORS (adjust for your frontend port if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _uniq_paths(paths):
    seen=set(); out=[]
    for p in paths:
        try:
            rp = p.resolve()
            if rp not in seen and rp.exists():
                seen.add(rp); out.append(rp)
        except Exception:
            pass
    return out

def _auto_detect_mt5_files() -> Path | None:
    """Best-effort scan for a likely MQL5\\Files folder (Windows)."""
    cands = []
    for env in ("APPDATA","LOCALAPPDATA"):
        base = Path(os.getenv(env,"")) / "MetaQuotes" / "Terminal"
        if base.exists():
            cands += [d / "MQL5" / "Files" for d in base.glob("*")]
            cands.append(base / "Common" / "Files")
    for pf in ("PROGRAMFILES","PROGRAMFILES(X86)"):
        base = Path(os.getenv(pf,""))
        if base.exists():
            cands.append(base / "MetaTrader 5" / "MQL5" / "Files")
            cands += list(base.glob("MetaTrader*/*/MQL5/Files"))
    cands.append(Path.home() / "MQL5" / "Files")
    cands = _uniq_paths(cands)
    try:
        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        pass
    return cands[0] if cands else None

# Resolve paths (env -> auto-detect -> home fallback)
MT5_FILES_DIR = os.getenv("MT5_FILES_DIR")
if MT5_FILES_DIR:
    base = Path(MT5_FILES_DIR)
else:
    base = _auto_detect_mt5_files() or (Path.home() / "MQL5" / "Files")

SIGNALS   = (base / "Fluent_signals.jsonl").resolve()
HEARTBEAT = (base / "fluent_heartbeat.txt").resolve()

def _tail_jsonl(path, limit):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return []
    out = []
    for line in lines[-max(1, min(limit, 20000)):]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out

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
    for k in ("profit", "p", "pnl", "profit_usd", "net_profit"):
        if k in rec:
            n = _num(rec.get(k))
            if n is not None:
                return n
    return None

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
    # Windows-safe (avoid %-m etc.)
    try:
        return datetime.fromtimestamp(ts).strftime("%m/%d/%Y, %I:%M:%S %p")
    except Exception:
        return None


def _heartbeat_status() -> str:
    try:
        ts = int((HEARTBEAT.read_text(encoding="utf-8") or "0").strip())
        age = time.time() - ts
        if age < 15:  return "ok"
        if age < 60:  return "stale"
        return "dead"
    except Exception:
        return "dead"

@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.0", "py": sys.version.split()[0]}

@app.get("/api/paths")
def paths():
    return {
        "mt5_files_dir": str(base),
        "signals": str(SIGNALS),
        "heartbeat": str(HEARTBEAT),
        "heartbeat_status": _heartbeat_status(),
        "signals_exists": SIGNALS.exists(),
        "heartbeat_exists": HEARTBEAT.exists(),
        "env_MT5_FILES_DIR": os.getenv("MT5_FILES_DIR") or "",
    }

@app.get("/api/metrics")
def metrics():
    hb = _heartbeat_status()
    opens = closes = mods = modtp = emerg = 0
    try:
        if SIGNALS.exists():
            # Tail last ~1000 lines quickly
            with SIGNALS.open("rb") as f:
                f.seek(0, os.SEEK_END)
                sz = f.tell()
                f.seek(max(0, sz - 512*1024))  # last 512KB
                data = f.read().decode("utf-8","ignore").splitlines()[-1000:]
            for ln in data:
                try:
                    a = json.loads(ln).get("action","")
                except Exception:
                    continue
                if a == "OPEN": opens += 1
                elif a == "CLOSE": closes += 1
                elif a == "MODIFY": mods += 1
                elif a == "MODIFY_TP": modtp += 1
                elif a == "EMERGENCY_CLOSE_ALL": emerg += 1
    except Exception:
        pass

    return {
        "heartbeat": hb,
        "counts": {"open": opens, "close": closes, "modify": mods, "modify_tp": modtp, "emergency": emerg},
        "state": STATE,
    }

@app.get("/api/signals")
def signals(limit: int = 200):
    rows = []
    if SIGNALS.exists():
        try:
            with SIGNALS.open("rb") as f:
                f.seek(0, os.SEEK_END)
                sz = f.tell()
                f.seek(max(0, sz - 1024*1024))  # last 1MB
                data = f.read().decode("utf-8","ignore").splitlines()
            for ln in data[-limit:]:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
        except Exception:
            pass
    return JSONResponse(rows)

@app.post("/api/emergency-close-all")
def emergency_close_all():
    gid = int(time.time() * 1000)
    rec = {"action":"EMERGENCY_CLOSE_ALL","id":str(gid),"t":int(time.time()),"source":"WEB","confirm":"YES"}
    SIGNALS.parent.mkdir(parents=True, exist_ok=True)
    with SIGNALS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n"); f.flush(); os.fsync(f.fileno())
    return {"ok": True, "gid": gid}

@app.websocket("/ws")
async def ws_events(ws: WebSocket):
    await ws.accept()
    # Tail with rotation/creation handling
    last_size = SIGNALS.stat().st_size if SIGNALS.exists() else 0
    try:
        while True:
            await asyncio.sleep(0.8)
            if not SIGNALS.exists():
                last_size = 0
                continue
            size = SIGNALS.stat().st_size
            # If file shrank (rotation/truncate), reset pointer
            if size < last_size:
                last_size = 0
            if size > last_size:
                with SIGNALS.open("rb") as f:
                    f.seek(last_size)
                    chunk = f.read(size - last_size).decode("utf-8","ignore")
                last_size = size
                for ln in chunk.splitlines():
                    ln = ln.strip()
                    if ln:
                        await ws.send_text(ln)
    except WebSocketDisconnect:
        return
    
@app.get("/api/state")
def get_state():
    # reflect heartbeat too (nice for UI)
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

@app.get("/api/channel-performance")
def channel_performance(limit: int = 5000):
    """
    Minimal robust aggregation:
    - JOIN CLOSE->OPEN via gid/oid/id to pick channel from OPEN
    - Filter internal sources
    - Win% from profit>0
    """
    # Resolve your actual path here if different
    signals_path = str(SIGNALS) if "SIGNALS" in globals() else "Fluent_signals.jsonl"
    rows = _tail_jsonl(signals_path, max(100, min(limit, 20000)))

    # Index OPENs by join key
    opens_by_key = {}
    for r in rows:
        if str(r.get("action") or "").upper() != "OPEN":
            continue
        k = _join_key(r)
        if k:
            opens_by_key[k] = r

    # Aggregate
    agg = {}  # channel -> counters
    for r in rows:
        a = str(r.get("action") or "").upper()
        src = (r.get("source") or "").strip()

        # Resolve canonical channel
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
            # confidence
            conf = r.get("confidence")
            if isinstance(conf, (int, float)):
                slot["confSum"] += float(conf)
                slot["confN"] += 1
            # score
            score = r.get("signal_score")
            if not isinstance(score, (int, float)):
                score = r.get("score")
            if isinstance(score, (int, float)):
                slot["scoreSum"] += float(score)
                slot["scoreN"] += 1

        elif a == "CLOSE":
            slot["closes"] += 1
            slot["totalClosed"] += 1
            p = _profit(r)
            if p is not None and p > 0:
                slot["wins"] += 1

        t = _ts(r)
        if t is not None and t > (slot["lastT"] or 0):
            slot["lastT"] = t

    # Build rows
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

    # Sort by win% desc, then closes desc
    out.sort(key=lambda r: ((r["win_rate"] if isinstance(r["win_rate"], (int, float)) else -1.0), r["closes"]), reverse=True)
    return JSONResponse(out)

@app.get("/")
def root():
    return {"status": "ok", "message": "Fluent Signal Copier API"}
