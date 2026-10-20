"""Moteur de décision hybride : règles rapides + réflexion approfondie via LLM local.

Le LLM propose, le moteur dispose : chaque action passe par ``simulation.actions.execute``.
Les appels au modèle sont asynchrones (pool de threads) ; leurs résultats sont appliqués
dans la boucle de simulation, jamais pendant la pause, et revalidés à l'exécution.
"""
import queue
from concurrent.futures import ThreadPoolExecutor

from agents import emotions, goals, templates
from agents.agent import inventory_items, place_of
from agents.memory import add_belief, add_memory, recall, subjective_text
from simulation import actions
from simulation.state import clean_text, fmt_time, is_night, minute_of_day
from simulation.world import PLACE_TYPES
from systems import communication, economy, iachat, messaging, relationships

PRIORITY_URGENT = 3


class DecisionEngine:
    def __init__(self, sim):
        self.sim = sim
        self.pool = ThreadPoolExecutor(max_workers=max(1, sim.cfg.llm_max_concurrent), thread_name_prefix="iacity-llm")
        self.results = queue.Queue()
        self.pending = {}        # agent_id -> job
        self.epoch = 0
        self.job_seq = 0

    def reset(self):
        self.epoch += 1
        self.pending.clear()
        self.results = queue.Queue()

    def shutdown(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    def step_agent(self, agent):
        sim, st = self.sim, self.sim.state
        tick = st["tick"]
        if agent["is_human"] or agent["id"] in self.pending or agent["place"] is None:
            return
        messaging.learn_public_numbers(sim, agent)
        for g in goals.update_progress(sim, agent):
            sim.emit("goal", [agent["id"]], f"{agent['name']} accomplit son objectif : {g['description']}", {"goal": g["id"], "status": "done"})
            add_memory(sim, agent, "lesson", f"Objectif accompli : {g['description']}", importance=0.85)
            emotions.nudge(agent, joy=0.25)
            agent["needs_review"] = True
        triggers = self._triggers(agent)
        urgent = any(p >= PRIORITY_URGENT for p, _ in triggers)
        if tick < agent["busy_until"] and not urgent:
            return
        if urgent:
            agent["plan"] = []
        if triggers and self._can_call(agent, max(p for p, _ in triggers)):
            self._submit(agent, [r for _, r in triggers])
            return
        if agent["plan"] and tick >= agent["busy_until"]:
            act = agent["plan"].pop(0)
            if actions.execute(sim, agent, act, origin="plan")[0]:
                return
        for act in self.rule_decide(agent):
            actions.execute(sim, agent, act, origin="rules")
        messaging.mark_read(sim, agent)
        self._consume_inbox(agent)

    # -- déclencheurs ------------------------------------------------------
    def _triggers(self, agent):
        sim, st = self.sim, self.sim.state
        tick, cfg = st["tick"], self.sim.cfg
        t = []
        if any(i["kind"] == "speech" and i["to_me"] for i in agent["inbox"]):
            t.append((3, "on_m'a_parlé"))
        if messaging.unread_for(sim, agent):
            t.append((3, "nouveau_message"))
        if agent["bond_proposals"]:
            t.append((3, "proposition_de_lien"))
        if any(i["kind"] == "event" for i in agent["inbox"]):
            t.append((2, "événement_en_ville"))
        if agent.get("last_read"):
            t.append((2, "lu_sur_iachat"))
        if agent.pop("needs_review", False):
            t.append((2, "revue_après_échec_ou_succès"))
        since = tick - agent["last_llm_tick"]
        if not goals.active_goals(agent) and since >= cfg.llm_min_interval * 2:
            t.append((1, "aucun_objectif"))
        elif goals.active_goals(agent) and not agent["plan"] and since >= cfg.llm_min_interval * 2:
            t.append((1, "poursuite_objectif"))
        if since >= cfg.reflection_every:
            t.append((1, "réflexion_périodique"))
        return t

    def _can_call(self, agent, priority):
        cfg, tick = self.sim.cfg, self.sim.state["tick"]
        if len(self.pending) >= cfg.llm_queue_max:
            return False
        if priority >= PRIORITY_URGENT:
            return True
        if len(self.pending) >= cfg.llm_max_concurrent * 2:
            return False
        return tick - agent["last_llm_tick"] >= cfg.llm_min_interval

    # -- appel LLM -----------------------------------------------------------
    def _submit(self, agent, reasons):
        sim = self.sim
        ctx = self.build_context(agent, reasons)
        self.job_seq += 1
        job = {"id": self.job_seq, "epoch": self.epoch, "agent": agent["id"], "ctx": ctx, "reasons": reasons, "tick": sim.state["tick"]}
        agent["last_llm_tick"] = sim.state["tick"]
        messaging.mark_read(sim, agent)
        self._consume_inbox(agent)
        agent["last_read"] = []
        if sim.llm.mode == "demo":
            # le cerveau de démonstration est instantané : appel synchrone, donc déterministe (rejouable)
            decision, info = sim.llm.decide(ctx)
            self.apply(agent, job, decision, info)
            return
        self.pending[agent["id"]] = job
        agent["current_activity"] = "réfléchit…"

        def run():
            decision, info = sim.llm.decide(ctx)
            self.results.put((job, decision, info))
        self.pool.submit(run)

    def drain(self):
        """Applique les résultats LLM arrivés (appelé par la boucle, jamais en pause)."""
        n = 0
        while True:
            try:
                job, decision, info = self.results.get_nowait()
            except queue.Empty:
                return n
            if job["epoch"] != self.epoch:
                continue
            agent = self.sim.state["agents"].get(job["agent"])
            cur = self.pending.get(job["agent"])
            if agent is None or cur is None or cur["id"] != job["id"]:
                continue
            del self.pending[job["agent"]]
            self.apply(agent, job, decision, info)
            n += 1

    def apply(self, agent, job, decision, info):
        sim = self.sim
        origin = info.get("source", "llm")
        if decision is None:
            sim.emit("llm_error", [agent["id"]], f"Décision invalide/indisponible pour {agent['name']} : {'; '.join(info.get('errors', []))[:200]}",
                     {"errors": info.get("errors")})
            for act in self.rule_decide(agent, job["ctx"]):
                actions.execute(sim, agent, act, origin="rules")
            return
        if info.get("errors"):
            sim.emit("llm_warning", [agent["id"]], f"Parties de la réponse ignorées : {'; '.join(info['errors'])[:200]}", {"errors": info["errors"]})
        emotions.apply_deltas(agent, decision["emotions"])
        for b in decision["beliefs"]:
            add_belief(sim, agent, b["text"], b["confidence"])
        for v in decision["values"]:
            if v not in [x["text"] for x in agent["values"]]:
                agent["values"].append({"text": v, "tick": sim.state["tick"]})
        seq = sim.emit("thought", [agent["id"]], decision["thought"] or "(pas de pensée)",
                       {"origin": origin, "reasons": job["reasons"], "actions": decision["actions"], "ms": info.get("ms")}, place=agent["place"])
        if decision["thought"]:
            add_memory(sim, agent, "thought", decision["thought"], importance=0.35, fact_seq=seq)
        acts = decision["actions"]
        if not acts:
            for act in self.rule_decide(agent, job["ctx"]):
                actions.execute(sim, agent, act, origin="rules")
            return
        first, rest = acts[0], acts[1:]
        ok, _ = actions.execute(sim, agent, first, origin=origin)
        if ok:
            agent["plan"] = rest
            for g in goals.active_goals(agent):
                g["updated"] = sim.state["tick"]

    def _consume_inbox(self, agent):
        agent["inbox"] = []

    # -- contexte ----------------------------------------------------------------
    def build_context(self, agent, reasons=()):
        sim, st = self.sim, self.sim.state
        tick = st["tick"]
        here = place_of(sim, agent)
        people = communication.people_around(sim, agent)
        convs = {p for c in communication.open_conversations(sim) if agent["id"] in c["participants"] for p in c["participants"]}
        speech = [i for i in agent["inbox"] if i["kind"] == "speech"][-6:]
        msgs = messaging.unread_for(sim, agent)
        top_needs = sorted(agent["needs"].items(), key=lambda kv: -kv[1])
        relations = []
        for oid, r in sorted(agent["relationships"].items(), key=lambda kv: -(kv[1]["interactions"]))[:12]:
            o = st["agents"].get(oid)
            if o and r["met_tick"] is not None:
                relations.append({"id": oid, "name": o["name"], "trust": r["trust"], "friendship": r["friendship"], "hostility": r["hostility"],
                                  "rivalry": r["rivalry"], "types": r["types"], "has_my_number": agent["id"] in o["contacts"]})
        q = " ".join(i["text"] for i in speech) + " " + " ".join(g["description"] for g in goals.active_goals(agent))
        mem = [subjective_text(sim, m) for m in recall(sim, agent, q, k=8)]
        market = [{"item_id": it["id"], "name": it["name"], "kind": it["kind"], "price": price,
                   "seller": "ville" if seller == "city" else st["agents"][seller]["name"]}
                  for it, seller, price in economy.stock_here(sim, here) if seller != agent["id"]][:14]
        places = []
        for p in st["places"].values():
            if p["id"] == "p_outdoor":
                continue
            spec = PLACE_TYPES.get(p["type"], {})
            payer = p["owner"] or "city"
            payer_ok = economy.balance(sim, payer) > 20 if p.get("wage") else True
            places.append({"id": p["id"], "name": p["name"], "type": p["type"], "wage": p.get("wage") and int(p["wage"] * sim.cfg.wage_scale * st["flags"].get("wage_mult", 1.0)),
                           "open": economy.place_open(sim, p), "leisure": bool(spec.get("leisure")), "entry": spec.get("entry", 0),
                           "sells": spec.get("sells", []), "owner": "ville" if p["owner"] == "city" else (st["agents"][p["owner"]]["name"] if p["owner"] in st["agents"] else None),
                           "for_sale": p["for_sale"], "price": p["price"], "housing_free": (p["capacity"] - len(p["tenants"])) if spec.get("housing") else None,
                           "payer_ok": payer_ok})
        last_post = max([p["tick"] for p in st["posts"].values() if p["author"] == agent["id"]] or [-9999])
        ctx = {
            "time": fmt_time(sim, tick), "reasons": list(reasons),
            "me": {"id": agent["id"], "name": agent["name"], "money": agent["money"], "number": agent["number"],
                   "place": {"id": here["id"], "name": here["name"], "type": here["type"]},
                   "home": st["places"][agent["home"]]["name"] if agent["home"] in st["places"] else None,
                   "needs": {k: round(v) for k, v in agent["needs"].items()}, "urgent_need": top_needs[0][0],
                   "emotions": {k: agent["emotions"][k] for k in emotions.dominant(agent, 3)},
                   "personality": agent["personality"], "skills": agent["skills"],
                   "values": [v["text"] for v in agent["values"][-5:]], "beliefs": [b["text"] for b in agent["beliefs"][-5:]],
                   "goals": [{"id": g["id"], "description": g["description"], "kind": g["kind"], "progress": g["progress"], "params": g["params"]} for g in goals.active_goals(agent)],
                   "inventory": [{"id": it["id"], "name": it["name"], "category": it["category"], "kind": it["kind"], "cost": it["cost"], "price": it["price"] if it["listed"] else None}
                                 for it in inventory_items(sim, agent)][:20],
                   "contacts": [{"name": c["name"], "number": c["number"]} for c in agent["contacts"].values()],
                   "relations": relations, "recent_failures": [f"{f['action']}: {f['reason']}" for f in agent["failures"][-3:]],
                   "last_post_age": tick - last_post, "activity": agent["current_activity"]},
            "here": {"people": [{"id": o["id"], "name": o["name"], "known": relationships.rel(agent, o["id"])["met_tick"] is not None,
                                 "trust": relationships.rel(agent, o["id"])["trust"], "in_conversation": o["id"] in convs, "doing": o["current_activity"],
                                 "audible": communication.audibility(sim, agent, o, "normal") > 0} for o in people],
                     "market": market},
            "heard": [{"from_id": i["from"], "from": st["agents"][i["from"]]["name"], "text": i["text"], "to_me": i["to_me"], "clarity": i["clarity"],
                       "turns": next((len(c["turns"]) for c in st["conversations"].values() if c["id"] == i["conv"]), 0)} for i in speech if i["from"] in st["agents"]],
            "messages": [{"from_id": m["from"], "from": st["agents"][m["from"]]["name"], "text": m["text"]} for m in msgs[-4:]],
            "bond_proposals": [{"from": b["from"], "from_name": st["agents"][b["from"]]["name"], "type": b["type"]} for b in agent["bond_proposals"] if b["from"] in st["agents"]],
            "iachat_unread": iachat.unread_count(sim, agent),
            "feed": list(agent.get("last_read") or []),
            "knowledge": [{"id": k["id"], "claim": k["claim"], "confidence": k["confidence"]} for k in agent["knowledge"][-4:]],
            "places": places,
            "free_plots": [{"id": p["id"], "name": p["name"], "price": p["price"]} for p in st["places"].values() if p["type"] == "terrain" and not p["built"] and p["owner"] == "city"],
            "build": {"cost": sim.cfg.build_cost, "materials": "3 bois + 2 metal", "types": ["boutique", "restaurant", "bar", "bureau", "atelier", "habitation", "loisirs", "epicerie"]},
            "memories": mem,
            "active_events": [e["key"] for e in st["effects"]],
            "_seed": (st["tick"] * 7919 + int(agent["id"][1:]) * 104729 + st["seed"]) & 0xFFFFFFF,
        }
        return ctx

    # -- règles rapides (sans LLM) --------------------------------------------------
    def rule_decide(self, agent, ctx=None):
        sim, st = self.sim, self.sim.state
        rng = sim.rng
        tick = st["tick"]
        ctx = ctx or self.build_context(agent)
        me = ctx["me"]
        here = place_of(sim, agent)
        out = []
        marker = {"origin": "rules"}
        # 1. répondre
        to_me = [h for h in ctx["heard"] if h["to_me"]]
        if to_me:
            h = to_me[-1]
            rel = next((r for r in me["relations"] if r["id"] == h["from_id"]), {"trust": 0.3, "hostility": 0.0})
            if templates.is_goodbye(h["text"]):
                return [{"type": "leave_conversation"}]
            line, tone, end = templates.reply_line(rng, h["from"], h["text"], rel["trust"], rel["hostility"], h.get("turns", 0))
            out.append({"type": "say", "to": h["from_id"], "text": line, "tone": tone})
            if end:
                out.append({"type": "leave_conversation"})
            if tone > 0.3 and rel["trust"] > 0.3 and not rel.get("has_my_number") and rng.random() < 0.5:
                out.append({"type": "give_number", "to": h["from_id"]})
            return out[:2]
        for m in ctx["messages"]:
            return [{"type": "text", "to": m["from_id"], "text": templates.pick(rng, templates.SMS_REPLY, t=m["from"])}]
        for b in ctx["bond_proposals"]:
            rel = next((r for r in me["relations"] if r["id"] == b["from"]), {"trust": 0.0})
            return [{"type": "answer_bond", "from": b["from"], "accept": rel["trust"] > 0.55 and agent["personality"]["agreeableness"] > 0.4}]
        # 2. nuit : rentrer dormir
        if is_night(sim, tick):
            if agent["home"] and agent["place"] != agent["home"]:
                return [{"type": "teleport", "place": agent["home"]}]
            if agent["home"]:
                return [{"type": "rest"}]
        # 3. besoins
        needs = agent["needs"]
        cheapest_meal = None
        sec_urgent = agent["money"] < 80 or not agent["home"]
        order = sorted(needs, key=lambda n: -needs[n] - (30 if n == "security" and sec_urgent else 0))
        for need in order:
            if need != "security" and needs[need] < 45:
                continue
            if need == "security":
                if not agent["home"]:
                    free = [p for p in ctx["places"] if p["housing_free"]]
                    if free and agent["money"] >= sim.cfg.rent_per_day:
                        return [{"type": "rent_home", "place": free[0]["id"]}]
                if agent["money"] < 140 or needs["security"] > 60:
                    jobs = [p for p in ctx["places"] if p["wage"] and p["open"] and p["payer_ok"] and p["type"] != "habitation"]
                    if jobs:
                        if here["id"] in {j["id"] for j in jobs}:
                            return [{"type": "work"}]
                        best = max(jobs, key=lambda p: p["wage"] + rng.random() * 3)
                        return [{"type": "teleport", "place": best["id"]}]
            elif need == "social":
                people = [p for p in ctx["here"]["people"] if p["audible"] and (not p["in_conversation"] or rng.random() < 0.3)]
                if people:
                    p = max(people, key=lambda p: p["trust"] + rng.random() * 0.2)
                    acts = [{"type": "say", "to": p["id"], "text": templates.pick(rng, templates.GREET if not p["known"] else templates.SMALL, t=p["name"], place=here["name"])}]
                    if p["trust"] > 0.3 and rng.random() < 0.4:
                        acts.append({"type": "give_number", "to": p["id"]})
                    return acts
                spots = [p for p in ctx["places"] if p["type"] in ("plaza", "parc", "bar", "restaurant") and p["open"] and p["id"] != here["id"]]
                if spots and rng.random() < 0.7:
                    return [{"type": "teleport", "place": rng.choice(spots)["id"]}]
                return [{"type": "read_feed"}] if ctx["iachat_unread"] else [{"type": "wait"}]
            elif need == "fun":
                if here["id"] in {p["id"] for p in ctx["places"] if p["leisure"] and p["open"] and p["entry"] <= agent["money"]}:
                    return [{"type": "relax"}]
                spots = [p for p in ctx["places"] if p["leisure"] and p["open"] and p["entry"] <= max(0, agent["money"] - 30)]
                if spots:
                    return [{"type": "teleport", "place": rng.choice(spots)["id"]}]
            elif need == "comfort":
                for it in inventory_items(sim, agent):
                    if (it.get("effects") or {}).get("comfort"):
                        return [{"type": "consume", "item_id": it["id"]}]
                meals = [m for m in ctx["here"]["market"] if m["kind"] in ("repas", "fruit") and m["price"] <= agent["money"] - 20]
                if meals:
                    return [{"type": "buy", "item_id": min(meals, key=lambda m: m["price"])["item_id"]}]
                sellers = [p for p in ctx["places"] if p["open"] and ("repas" in p["sells"] or "fruit" in p["sells"])]
                if sellers and agent["money"] > 40:
                    return [{"type": "teleport", "place": rng.choice(sellers)["id"]}]
                if agent["home"] and agent["place"] != agent["home"]:
                    return [{"type": "teleport", "place": agent["home"]}]
                if agent["home"]:
                    return [{"type": "rest"}]
            elif need == "curiosity":
                if ctx["iachat_unread"]:
                    return [{"type": "read_feed"}]
                school = [p for p in ctx["places"] if p["type"] == "ecole" and p["open"]]
                if school:
                    if here["id"] == school[0]["id"]:
                        return [{"type": "study"}]
                    return [{"type": "teleport", "place": school[0]["id"]}]
        # 4. flânerie
        if rng.random() < 0.15:
            spots = [p for p in ctx["places"] if p["open"] and p["id"] != here["id"] and p["type"] not in ("habitation", "terrain")]
            if spots:
                return [{"type": "teleport", "place": rng.choice(spots)["id"]}]
        return [{"type": "wait"}]
