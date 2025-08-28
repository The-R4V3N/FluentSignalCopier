# persistence.py — minimal, robust history store (Python 3.10+)
from __future__ import annotations
import sqlite3, json, os, time, platform
from dataclasses import dataclass
from pathlib import Path

def _default_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        # align with your GUI’s default layout
        base = Path(os.getenv("APPDATA", str(Path.home())))
        return base / "R4V3N" / "Fluent_signals_copier"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "FluentSignalCopier"
    else:
        return Path.home() / ".local" / "share" / "FluentSignalCopier"

# allow override via env variable
DATA_DIR = Path(os.getenv("FSC_DATA_DIR", str(_default_data_dir())))
DB_PATH  = DATA_DIR / "history.sqlite3"

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS signals (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ms         INTEGER NOT NULL,
  channel       TEXT    NOT NULL,
  message_id    TEXT,
  symbol        TEXT,
  side          TEXT,
  raw_text      TEXT NOT NULL,
  sl            REAL,
  entry         REAL,
  tps_json      TEXT,
  status        TEXT NOT NULL DEFAULT 'NEW'
);

CREATE TABLE IF NOT EXISTS executions (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id     INTEGER NOT NULL,
  ts_ms         INTEGER NOT NULL,
  action        TEXT NOT NULL,
  price         REAL,
  volume        REAL,
  order_id      TEXT,
  note          TEXT,
  FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS results (
  signal_id     INTEGER PRIMARY KEY,
  closed_ts_ms  INTEGER,
  realized_pnl  REAL,
  rr            REAL,
  duration_s    INTEGER,
  outcome       TEXT,
  FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
);

CREATE VIEW IF NOT EXISTS v_channel_stats AS
SELECT
  s.channel,
  COUNT(*) AS signals_total,
  SUM(CASE WHEN r.outcome='WIN' THEN 1 ELSE 0 END)  AS wins,
  SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
  AVG(r.realized_pnl) AS avg_pnl,
  SUM(r.realized_pnl) AS total_pnl
FROM signals s
LEFT JOIN results r ON r.signal_id = s.id
GROUP BY s.channel;
"""

@dataclass
class NewSignal:
    ts_ms: int
    channel: str
    raw_text: str
    symbol: str | None = None
    side: str | None = None
    sl: float | None = None
    entry: float | None = None
    tps: list[float] | None = None
    message_id: str | None = None

class HistoryStore:
    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        # ✅ make sure the folder exists before connecting
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # a small timeout avoids “database is locked” on quick restarts
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=5.0)
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def add_signal(self, sig: NewSignal) -> int:
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO signals(ts_ms,channel,message_id,symbol,side,raw_text,sl,entry,tps_json)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (sig.ts_ms, sig.channel, sig.message_id, sig.symbol, sig.side, sig.raw_text,
             sig.sl, sig.entry, json.dumps(sig.tps or []))
        )
        self._conn.commit()
        return cur.lastrowid

    def mark_event(self, signal_id: int, action: str, price=None, volume=None, order_id=None, note=None, ts_ms=None):
        ts_ms = ts_ms or int(time.time() * 1000)
        self._conn.execute(
            "INSERT INTO executions(signal_id,ts_ms,action,price,volume,order_id,note) VALUES(?,?,?,?,?,?,?)",
            (signal_id, ts_ms, action, price, volume, order_id, note)
        )
        # progress status heuristics
        if action == "OPEN":
            self._conn.execute("UPDATE signals SET status='OPENED' WHERE id=?", (signal_id,))
        elif action in ("TP_HIT", "SL_HIT", "MANUAL_CLOSE"):
            # later finalized by close_result(), but mark as PARTIAL if TP_HIT
            if action == "TP_HIT":
                self._conn.execute("UPDATE signals SET status='PARTIAL' WHERE id=?", (signal_id,))
        self._conn.commit()

    def close_result(self, signal_id: int, realized_pnl: float, outcome: str, rr: float | None = None, ts_ms: int | None = None):
        ts_ms = ts_ms or int(time.time() * 1000)
        # fetch open time to compute duration
        cur = self._conn.execute("SELECT ts_ms FROM signals WHERE id=?", (signal_id,))
        row = cur.fetchone()
        start = row[0] if row else ts_ms
        duration_s = max(0, (ts_ms - start) // 1000)
        self._conn.execute("""
            INSERT INTO results(signal_id,closed_ts_ms,realized_pnl,rr,duration_s,outcome)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(signal_id) DO UPDATE SET
              closed_ts_ms=excluded.closed_ts_ms,
              realized_pnl=excluded.realized_pnl,
              rr=excluded.rr,
              duration_s=excluded.duration_s,
              outcome=excluded.outcome
        """, (signal_id, ts_ms, realized_pnl, rr, duration_s, outcome))
        self._conn.execute("UPDATE signals SET status='CLOSED' WHERE id=?", (signal_id,))
        self._conn.commit()

    # Queries for your GUI
    def recent_signals(self, limit=200):
        q = """SELECT id, ts_ms, channel, symbol, side, sl, entry, tps_json, status FROM signals
               ORDER BY ts_ms DESC LIMIT ?"""
        return [self._row_to_dict(r) for r in self._conn.execute(q, (limit,))]

    def channel_stats(self):
        return [dict(channel=ch, signals_total=tot, wins=w, losses=l, avg_pnl=avg, total_pnl=totp)
                for ch, tot, w, l, avg, totp in self._conn.execute("SELECT channel,signals_total,wins,losses,avg_pnl,total_pnl FROM v_channel_stats")]

    def history_for_channel(self, channel: str, limit=500):
        q = """SELECT s.id, s.ts_ms, s.symbol, s.side, s.sl, s.entry, s.tps_json, s.status,
                      r.realized_pnl, r.outcome
               FROM signals s LEFT JOIN results r ON r.signal_id = s.id
               WHERE s.channel=? ORDER BY s.ts_ms DESC LIMIT ?"""
        rows = self._conn.execute(q, (channel, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(id=r[0], ts_ms=r[1], symbol=r[2], side=r[3], sl=r[4], entry=r[5],
                     tps=json.loads(r[6] or "[]"), status=r[7], realized_pnl=r[8], outcome=r[9])
            out.append(d)
        return out

    def _row_to_dict(self, r):
        return dict(id=r[0], ts_ms=r[1], channel=r[2], symbol=r[3], side=r[4],
                    sl=r[5], entry=r[6], tps=json.loads(r[7] or "[]"), status=r[8])
