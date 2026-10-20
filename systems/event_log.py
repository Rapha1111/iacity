"""Journal d'événements append-only (SQLite).

Les entrées ne sont jamais supprimées : lors d'une restauration, les
événements postérieurs à la sauvegarde sont marqués ``discarded`` et
masqués par défaut (§15.2).
"""
import json
import os
import sqlite3
import threading
import time

from simulation.state import SCHEMA_VERSION

COLUMNS = ["seq", "tick", "sim_time", "real_ts", "type", "actors", "place", "summary", "data", "discarded"]


class EventLog:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.db = None
        self.open_fresh()

    # -- cycle de vie ---------------------------------------------------
    def open_fresh(self):
        with self.lock:
            if self.db is not None:
                self.db.close()
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(self.path + suffix)
                except OSError:
                    pass
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self.db = sqlite3.connect(self.path, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=OFF")
            self.db.executescript("""
                CREATE TABLE events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER NOT NULL, sim_time TEXT, real_ts REAL,
                    type TEXT NOT NULL, actors TEXT, place TEXT,
                    summary TEXT, data TEXT, discarded INTEGER DEFAULT 0);
                CREATE TABLE event_actors(seq INTEGER, agent_id TEXT);
                CREATE INDEX ix_ev_type ON events(type);
                CREATE INDEX ix_ev_tick ON events(tick);
                CREATE INDEX ix_ea ON event_actors(agent_id, seq);
            """)
            self.db.commit()

    def close(self):
        with self.lock:
            if self.db is not None:
                self.db.commit()
                self.db.close()
                self.db = None

    def flush(self):
        with self.lock:
            self.db.commit()

    # -- écriture -------------------------------------------------------
    def append(self, tick, sim_time, etype, actors=(), summary="", data=None, place=None):
        actors = [a for a in actors if a]
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO events(tick,sim_time,real_ts,type,actors,place,summary,data) VALUES(?,?,?,?,?,?,?,?)",
                (tick, sim_time, time.time(), etype, json.dumps(actors), place, summary,
                 json.dumps(data if data is not None else {}, ensure_ascii=False)))
            seq = cur.lastrowid
            if actors:
                self.db.executemany("INSERT INTO event_actors VALUES(?,?)", [(seq, a) for a in set(actors)])
            return seq

    def discard_after(self, seq):
        with self.lock:
            self.db.execute("UPDATE events SET discarded=1 WHERE seq>?", (seq,))
            self.db.commit()

    def replace_with(self, rows):
        """Remplace le contenu (restauration d'une sauvegarde d'une autre session)."""
        with self.lock:
            self.db.execute("DELETE FROM events")
            self.db.execute("DELETE FROM event_actors")
            for r in rows:
                self.db.execute(
                    "INSERT INTO events(seq,tick,sim_time,real_ts,type,actors,place,summary,data,discarded) VALUES(?,?,?,?,?,?,?,?,?,0)",
                    (r["seq"], r["tick"], r.get("sim_time"), r.get("real_ts"), r["type"],
                     json.dumps(r.get("actors") or []), r.get("place"), r.get("summary"),
                     json.dumps(r.get("data") or {}, ensure_ascii=False)))
                for a in set(r.get("actors") or []):
                    self.db.execute("INSERT INTO event_actors VALUES(?,?)", (r["seq"], a))
            self.db.commit()

    # -- lecture --------------------------------------------------------
    def last_seq(self):
        with self.lock:
            r = self.db.execute("SELECT MAX(seq) m FROM events").fetchone()
            return r["m"] or 0

    @staticmethod
    def _row(r):
        d = dict(r)
        d["actors"] = json.loads(d["actors"] or "[]")
        d["data"] = json.loads(d["data"] or "{}")
        return d

    def _where(self, types=None, actor=None, q=None, before=None, after=None,
               tick_from=None, tick_to=None, include_discarded=False):
        conds, args = [], []
        if not include_discarded:
            conds.append("e.discarded=0")
        if types:
            conds.append("e.type IN (%s)" % ",".join("?" * len(types)))
            args += list(types)
        if actor:
            conds.append("e.seq IN (SELECT seq FROM event_actors WHERE agent_id=?)")
            args.append(actor)
        if q:
            conds.append("(e.summary LIKE ? OR e.data LIKE ?)")
            like = "%" + q.replace("%", "").replace("_", "") + "%"
            args += [like, like]
        if before:
            conds.append("e.seq<?")
            args.append(int(before))
        if after:
            conds.append("e.seq>?")
            args.append(int(after))
        if tick_from is not None:
            conds.append("e.tick>=?")
            args.append(int(tick_from))
        if tick_to is not None:
            conds.append("e.tick<=?")
            args.append(int(tick_to))
        return (" WHERE " + " AND ".join(conds)) if conds else "", args

    def query(self, limit=50, **filters):
        """Page d'événements, du plus récent au plus ancien (curseur ``before``)."""
        limit = max(1, min(int(limit), 1000))
        where, args = self._where(**filters)
        with self.lock:
            rows = self.db.execute(
                f"SELECT * FROM events e{where} ORDER BY e.seq DESC LIMIT ?", args + [limit + 1]).fetchall()
        has_more = len(rows) > limit
        return [self._row(r) for r in rows[:limit]], has_more

    def count(self, **filters):
        where, args = self._where(**filters)
        with self.lock:
            return self.db.execute(f"SELECT COUNT(*) c FROM events e{where}", args).fetchone()["c"]

    def iter_rows(self, chunk=500, upto=None, **filters):
        """Itère par ordre croissant sans tout charger en mémoire."""
        last = 0
        while True:
            where, args = self._where(after=last, **filters)
            if upto is not None:
                where += (" AND" if where else " WHERE") + " e.seq<=?"
                args = args + [upto]
            with self.lock:
                rows = self.db.execute(
                    f"SELECT * FROM events e{where} ORDER BY e.seq ASC LIMIT ?", args + [chunk]).fetchall()
            if not rows:
                return
            for r in rows:
                yield self._row(r)
            last = rows[-1]["seq"]

    def meta(self):
        return {"schema_version": SCHEMA_VERSION}
