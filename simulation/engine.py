"""Simulation Engine : horloge simulée, cycles, orchestration, thread de simulation."""
import json
import logging
import os
import random
import threading
import time
import uuid

from agents.agent import new_agent
from agents.decision_engine import DecisionEngine
from agents.llm_adapter import LLMAdapter
from agents import emotions
from agents.memory import decay_memories
from simulation import events, integrity, world
from simulation.state import SCHEMA_VERSION, fmt_time, ticks_per_day, is_night
from systems import communication, economy, relationships
from systems.event_log import EventLog


class Simulation:
    def __init__(self, cfg):
        self.cfg = cfg
        self.logger = logging.getLogger("iacity")
        self.lock = threading.RLock()
        self.rng = random.Random()
        self.state = None
        self.log = EventLog(os.path.join(cfg.data_dir, "session.db"))
        self.llm = LLMAdapter(cfg)
        self.decisions = DecisionEngine(self)
        self.paused = False
        self.speed = max(0.05, float(cfg.speed))
        self.version = 0
        self.integrity_errors = []
        self.saves = None          # défini par save_manager
        self._stop = threading.Event()
        self._thread = None
        self.new_world(cfg.num_agents, cfg.seed or None)

    # -- journal -----------------------------------------------------------------
    def emit(self, etype, actors=(), summary="", data=None, place=None):
        tick = self.state["tick"] if self.state else 0
        return self.log.append(tick, fmt_time(self, tick), etype, list(actors), summary, data, place)

    # -- création ------------------------------------------------------------------
    def new_world(self, num_agents=None, seed=None, human=None):
        with self.lock:
            self.decisions.reset()
            self.log.open_fresh()
            num_agents = max(1, min(20, int(num_agents or self.cfg.num_agents)))
            seed = int(seed) if seed else random.SystemRandom().randrange(1, 2 ** 31)
            self.rng = random.Random(seed)
            self.state = {
                "schema_version": SCHEMA_VERSION, "session_id": uuid.uuid4().hex[:8], "seed": seed,
                "tick": (8 * 60) // self.cfg.minutes_per_tick, "rng": None, "ids": {},
                "agents": {}, "places": {}, "items": {}, "posts": {}, "messages": [], "conversations": {},
                "transactions": [], "treasury": self.cfg.treasury_start, "money_total": self.cfg.treasury_start,
                "effects": [], "flags": {"price_mult": 1.0, "rent_mult": 1.0, "wage_mult": 1.0, "map_version": 0},
                "map": [], "human": None,
            }
            world.generate_world(self.cfg, self.rng, self.state)
            homes = [p for p in self.state["places"].values() if p["type"] == "habitation"]
            for i in range(num_agents):
                a = new_agent(self)
                home = [h for h in homes if len(h["tenants"]) < h["capacity"]][0]
                home["tenants"][a["id"]] = self.cfg.rent_per_day
                a["home"] = home["id"]
                x, y = world.random_spot(self, home)
                a["x"], a["y"], a["place"] = x, y, home["id"]
                a["current_activity"] = "se réveille chez soi"
                a["known_places"][home["id"]] = self.state["tick"]
            economy.restock(self)
            for p in self.state["places"].values():     # le parc démarre bien fourni
                for k in p["natural"]:
                    p["natural"][k] = 8
            self.emit("system", [], f"Simulation créée : {num_agents} agents, graine {seed}", {"num_agents": num_agents, "seed": seed})
            self.integrity_errors = []
            self.version += 1
            self.log.flush()
            if human:
                self.spawn_human(human)
            return self.state["session_id"]

    def spawn_human(self, name):
        from agents.agent import new_agent as mk
        from simulation.state import clean_text
        with self.lock:
            st = self.state
            if st["human"] and st["human"] in st["agents"]:
                return st["agents"][st["human"]]
            name = clean_text(name, 24) or "Visiteur"
            a = mk(self, name=name, is_human=True)
            plaza = [p for p in st["places"].values() if p["type"] == "plaza"][0]
            a["x"], a["y"] = world.random_spot(self, plaza)
            a["place"] = plaza["id"]
            a["current_activity"] = "visite la ville"
            a["needs"] = {k: 0 for k in a["needs"]}
            st["human"] = a["id"]
            self.emit("system", [a["id"]], f"Le personnage humain « {a['name']} » arrive sur la place", {})
            self.version += 1
            return a

    # -- cycle ------------------------------------------------------------------------
    def tick(self):
        with self.lock:
            st, cfg = self.state, self.cfg
            st["tick"] += 1
            tick = st["tick"]
            tpd = ticks_per_day(self)
            events.process(self)
            if tick % tpd == 0:
                economy.pay_rents(self)
            if tick % max(1, tpd // 24) == 0:
                economy.restock(self)
            night = is_night(self, tick)
            for a in st["agents"].values():
                if not a["is_human"]:
                    emotions.drift_needs(a, 1.0, night)
                    emotions.decay(a)
            self.decisions.drain()
            agents = list(st["agents"].values())
            for idx, a in enumerate(agents):
                if a["is_human"]:
                    continue
                urgent = any(i["kind"] == "speech" and i["to_me"] for i in a["inbox"])
                if urgent or (tick + idx) % cfg.perception_every == 0:
                    try:
                        self.decisions.step_agent(a)
                    except Exception:
                        self.logger.exception("décision de %s", a["id"])
                        self.emit("system", [a["id"]], f"Erreur interne lors de la décision de {a['name']}", {})
            communication.upkeep(self)
            if tick % 12 == 0:
                relationships.recompute_reputation(self)
            if tick % 24 == 0:
                for a in agents:
                    decay_memories(self, a)
            if tick % 100 == 0:
                self.integrity_errors = integrity.check(st)
                if self.integrity_errors:
                    self.emit("system", [], f"Intégrité : {len(self.integrity_errors)} anomalie(s)", {"errors": self.integrity_errors[:10]})
            if self.saves and cfg.autosave_every_days > 0 and tick % max(1, int(tpd * cfg.autosave_every_days)) == 0:
                self.saves.autosave()
            self.log.flush()
            self.version += 1

    def step(self, n=1):
        for _ in range(max(0, min(int(n), 500))):
            self.tick()

    # -- contrôle ---------------------------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="iacity-sim", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.decisions.shutdown()
        with self.lock:
            self.log.close()

    def pause(self):
        with self.lock:
            if not self.paused:
                self.paused = True
                self.emit("system", [], "Simulation en pause", {})
                self.version += 1

    def resume(self):
        with self.lock:
            if self.paused:
                self.paused = False
                self.emit("system", [], "Simulation reprise", {})
                self.version += 1

    def set_speed(self, speed):
        self.speed = max(0.1, min(60.0, float(speed)))
        self.version += 1

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            if not self.paused:
                try:
                    self.tick()
                except Exception:
                    self.logger.exception("erreur dans le cycle")
                    time.sleep(0.5)
            interval = self.cfg.tick_seconds / self.speed
            self._stop.wait(max(0.005, interval - (time.time() - t0)))

    # -- snapshots -------------------------------------------------------------------------
    def export_state(self):
        with self.lock:
            v, internal, gauss = self.rng.getstate()
            self.state["rng"] = [v, list(internal), gauss]
            return json.loads(json.dumps(self.state))

    def import_state(self, state):
        with self.lock:
            self.decisions.reset()
            self.state = state
            v, internal, gauss = state["rng"]
            self.rng.setstate((v, tuple(internal), gauss))
            self.integrity_errors = integrity.check(state)
            self.version += 1
