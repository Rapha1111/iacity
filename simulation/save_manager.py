"""Save/Replay Manager : snapshots, restauration, import/export, export des journaux."""
import csv
import io
import json
import os
import re
import time

from simulation import integrity
from simulation.state import SCHEMA_VERSION, fmt_time

MAX_IMPORT_BYTES = 128 * 1024 * 1024
REQUIRED_KEYS = {"schema_version", "session_id", "seed", "tick", "rng", "ids", "agents", "places", "items", "posts",
                 "messages", "conversations", "transactions", "treasury", "money_total", "effects", "flags", "map"}


class SaveError(Exception):
    pass


class SaveManager:
    def __init__(self, sim):
        self.sim = sim
        self.dir = os.path.join(sim.cfg.data_dir, "saves")
        os.makedirs(self.dir, exist_ok=True)
        sim.saves = self
        self.meta = {}      # id -> métadonnées (en mémoire pour la session)

    def _path(self, sid):
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", sid or ""):
            raise SaveError("identifiant de sauvegarde invalide")
        return os.path.join(self.dir, sid + ".json")

    def save(self, name="", auto=False):
        sim = self.sim
        with sim.lock:
            state = sim.export_state()
            seq = sim.log.last_seq()
            sid = f"{state['session_id']}-t{state['tick']}{'-auto' if auto else ''}-{int(time.time()) % 100000}"
            rows = list(sim.log.iter_rows(upto=seq))
            doc = {"format": "iacity-snapshot", "schema_version": SCHEMA_VERSION, "saved_at": time.time(),
                   "name": name or fmt_time(sim, state["tick"]), "log_seq": seq, "state": state, "log": rows}
        with open(self._path(sid), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        info = self._info(sid, doc)
        self.meta[sid] = info
        sim.emit("system", [], f"Sauvegarde « {info['name']} » ({sid})", {"save": sid, "auto": auto})
        if auto:
            self._prune_auto()
        return info

    def autosave(self):
        return self.save("Sauvegarde automatique", auto=True)

    def _prune_auto(self, keep=5):
        autos = sorted((f for f in os.listdir(self.dir) if "-auto-" in f), key=lambda f: os.path.getmtime(os.path.join(self.dir, f)))
        for f in autos[:-keep]:
            try:
                os.remove(os.path.join(self.dir, f))
                self.meta.pop(f[:-5], None)
            except OSError:
                pass

    @staticmethod
    def _info(sid, doc):
        st = doc["state"]
        return {"id": sid, "name": doc["name"], "tick": st["tick"], "session_id": st["session_id"],
                "agents": len(st["agents"]), "saved_at": doc["saved_at"], "log_seq": doc["log_seq"], "auto": "-auto-" in sid}

    def list(self):
        out = []
        for f in sorted(os.listdir(self.dir)):
            if f.endswith(".json"):
                sid = f[:-5]
                if sid not in self.meta:
                    try:
                        with open(os.path.join(self.dir, f), encoding="utf-8") as fh:
                            self.meta[sid] = self._info(sid, json.load(fh))
                    except (OSError, ValueError, KeyError):
                        continue
                out.append(self.meta[sid])
        return sorted(out, key=lambda i: -i["saved_at"])

    def _load(self, sid):
        try:
            with open(self._path(sid), encoding="utf-8") as f:
                return self.parse(f.read())
        except FileNotFoundError:
            raise SaveError("sauvegarde introuvable")

    @staticmethod
    def parse(raw):
        if len(raw) > MAX_IMPORT_BYTES:
            raise SaveError("fichier trop volumineux")
        try:
            doc = json.loads(raw)
        except ValueError:
            raise SaveError("JSON invalide")
        if not isinstance(doc, dict) or doc.get("format") != "iacity-snapshot":
            raise SaveError("ce fichier n'est pas une sauvegarde IACity")
        if doc.get("schema_version") != SCHEMA_VERSION:
            raise SaveError(f"version de schéma incompatible ({doc.get('schema_version')} ≠ {SCHEMA_VERSION})")
        st = doc.get("state")
        if not isinstance(st, dict) or not REQUIRED_KEYS <= set(st):
            raise SaveError("état de sauvegarde incomplet")
        errs = integrity.check(st)
        if errs:
            raise SaveError("sauvegarde incohérente : " + "; ".join(errs[:3]))
        return doc

    def restore(self, sid):
        doc = self._load(sid)
        return self._apply(doc, sid)

    def import_bytes(self, raw):
        doc = self.parse(raw)
        sid = f"import-{doc['state']['session_id']}-t{doc['state']['tick']}-{int(time.time()) % 100000}"
        with open(self._path(sid), "w", encoding="utf-8") as f:
            f.write(raw if isinstance(raw, str) else raw.decode("utf-8"))
        self.meta[sid] = self._info(sid, doc)
        return self._apply(doc, sid)

    def _apply(self, doc, sid):
        sim = self.sim
        with sim.lock:
            st = doc["state"]
            same = st["session_id"] == sim.state["session_id"]
            sim.import_state(st)
            if same:
                sim.log.discard_after(doc["log_seq"])        # événements futurs masqués, jamais supprimés
            else:
                sim.log.replace_with(doc.get("log", []))
            sim.emit("restore", [], f"Restauration de « {doc['name']} » ({sid}) au {fmt_time(sim, st['tick'])}",
                     {"save": sid, "log_seq": doc["log_seq"], "same_session": same})
            sim.log.flush()
        return {"id": sid, "name": doc["name"], "tick": st["tick"]}

    def raw(self, sid):
        with open(self._path(sid), "rb") as f:
            return f.read()


# -- export des journaux -------------------------------------------------------------
def export_log(sim, fmt="jsonl", tick_from=None, tick_to=None, types=None):
    """Générateur de morceaux de texte (JSON, JSONL ou CSV), sans charger tout l'historique."""
    meta = {"schema_version": SCHEMA_VERSION, "session_id": sim.state["session_id"], "generated_at": time.time(),
            "tick_from": tick_from, "tick_to": tick_to, "sim_time_from": fmt_time(sim, tick_from) if tick_from is not None else None,
            "sim_time_to": fmt_time(sim, tick_to if tick_to is not None else sim.state["tick"]), "types": types}
    rows = sim.log.iter_rows(tick_from=tick_from, tick_to=tick_to, types=types)
    if fmt == "jsonl":
        yield json.dumps({"meta": meta}, ensure_ascii=False) + "\n"
        for r in rows:
            r.pop("discarded", None)
            yield json.dumps(r, ensure_ascii=False) + "\n"
    elif fmt == "json":
        yield '{"meta": ' + json.dumps(meta, ensure_ascii=False) + ', "events": ['
        first = True
        for r in rows:
            r.pop("discarded", None)
            yield ("" if first else ",") + json.dumps(r, ensure_ascii=False)
            first = False
        yield "]}"
    elif fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["# schema_version", SCHEMA_VERSION, "session", sim.state["session_id"], "tick_from", tick_from, "tick_to", tick_to])
        w.writerow(["seq", "tick", "sim_time", "type", "actors", "place", "summary"])
        yield buf.getvalue()
        for r in rows:
            buf = io.StringIO()
            csv.writer(buf).writerow([r["seq"], r["tick"], r["sim_time"], r["type"], " ".join(r["actors"]), r["place"], _csv_safe(r["summary"])])
            yield buf.getvalue()
    else:
        raise ValueError("format inconnu")


def _csv_safe(s):
    """Neutralise l'injection de formules dans les tableurs."""
    s = s or ""
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def export_table(sim, name):
    st = sim.state
    tables = {
        "agents": (["id", "name", "money", "place", "home", "number", "activity", "goals_active"],
                   lambda: ([a["id"], a["name"], a["money"], a["place"], a["home"], a["number"], a["current_activity"],
                             sum(1 for g in a["goals"] if g["status"] == "active")] for a in st["agents"].values())),
        "transactions": (["id", "tick", "buyer", "seller", "items", "price", "result"],
                         lambda: ([t["id"], t["tick"], t["buyer"], t["seller"], "|".join(t["item_names"]), t["price"], t["result"]] for t in st["transactions"])),
        "posts": (["id", "tick", "author", "human", "reply_to", "text"],
                  lambda: ([p["id"], p["tick"], p["author_name"], p["human"], p["reply_to"], p["text"]] for p in st["posts"].values())),
        "messages": (["id", "tick", "from", "to", "text", "status"],
                     lambda: ([m["id"], m["tick"], m["from"], m["to"], m["text"], m["status"]] for m in st["messages"])),
        "items": (["id", "name", "creator", "owner", "category", "price", "quality"],
                  lambda: ([i["id"], i["name"], i["creator"], i["owner"], i["category"], i["price"], i["quality"]] for i in st["items"].values())),
    }
    if name not in tables:
        raise ValueError("table inconnue")
    header, gen = tables[name]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# schema_version", SCHEMA_VERSION, "session", st["session_id"], "tick", st["tick"]])
    w.writerow(header)
    for row in gen():
        w.writerow([_csv_safe(c) if isinstance(c, str) else c for c in row])
    return buf.getvalue()
