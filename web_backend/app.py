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
    Aggregate recent signals by source/channel.
    Scans the last ~2MB (or 'limit' rows after slicing) for speed.
    """
    rows = []
    if SIGNALS.exists():
        try:
            with SIGNALS.open("rb") as f:
                f.seek(0, os.SEEK_END)
                sz = f.tell()
                f.seek(max(0, sz - 2 * 1024 * 1024))  # last ~2MB
                data = f.read().decode("utf-8", "ignore").splitlines()
            # keep only the last 'limit' JSON lines
            for ln in data[-limit:]:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
        except Exception:
            pass

    agg = defaultdict(lambda: {
        "channel": "",
        "opens": 0,
        "closes": 0,
        "conf_sum": 0.0,
        "conf_n": 0,
        "wins": 0,
        "closed_n": 0,
        "last_ts": 0,
    })

    for r in rows:
        src = str(r.get("source") or "—")
        a = (r.get("action") or "").upper()
        t = int(r.get("t") or 0)

        g = agg[src]
        g["channel"] = src

        # avg confidence
        conf = r.get("confidence")
        if isinstance(conf, (int, float)):
            g["conf_sum"] += float(conf)
            g["conf_n"] += 1

        # last ts
        if t and t > g["last_ts"]:
            g["last_ts"] = t

        if a == "OPEN":
            g["opens"] += 1
            continue

        if a != "CLOSE":
            continue

        g["closes"] += 1
        g["closed_n"] += 1

        # --- WIN detection (robust) ---
        profit = r.get("profit", None)
        win = None

        # 1) numeric profit (supports strings-as-numbers)
        if profit is not None:
            try:
                p = float(profit)
                # allow tiny rounding noise
                if p > 1e-8:
                    win = True
                elif p < -1e-8:
                    win = False
                else:
                    win = False  # treat pure 0 as non-win (breakeven)
            except Exception:
                pass

        # 2) explicit outcome if present
        if win is None:
            outcome = str(r.get("outcome") or "").upper()
            if outcome == "WIN":
                win = True
            elif outcome in ("LOSS", "LOSE"):
                win = False

        # 3) reason heuristic (just in case)
        if win is None:
            reason = str(r.get("reason") or "").upper()
            if "TP" in reason or "TAKE" in reason:
                win = True
            elif "SL" in reason or "STOP" in reason:
                win = False

        if win:
            g["wins"] += 1

    out = []
    for src, g in agg.items():
        avg_conf = (g["conf_sum"] / g["conf_n"]) if g["conf_n"] else None
        win_rate = (g["wins"] / g["closed_n"] * 100.0) if g["closed_n"] else None
        # use avg_conf as "signal score" to match desktop
        signal_score = avg_conf
        last_signal_iso = datetime.fromtimestamp(g["last_ts"]).isoformat(sep=" ") if g["last_ts"] else None

        out.append({
            "channel": src,
            "signal_score": signal_score,   # %
            "win_rate": win_rate,           # %
            "opens": g["opens"],
            "closes": g["closes"],
            "avg_confidence": avg_conf,     # %
            "last_signal": last_signal_iso,
        })

    # sort by last signal desc
    out.sort(key=lambda r: (r["last_signal"] is None, r["last_signal"]), reverse=True)
    return JSONResponse(out)

@app.get("/")
def root():
    return {"status": "ok", "message": "Fluent Signal Copier API"}
