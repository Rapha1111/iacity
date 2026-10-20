"""Objectifs émergents : création, suivi vérifiable, abandon."""
from simulation.state import next_id

GOAL_KINDS = ("earn_money", "obtain_item", "meet", "create_place", "improve_relation", "learn_skill", "other")


def add_goal(sim, agent, description, kind="other", params=None, priority=0.5, origin="reflexion"):
    st = sim.state
    if kind not in GOAL_KINDS:
        kind = "other"
    for g in agent["goals"]:
        if g["status"] == "active" and g["description"] == description:
            return g
    g = {"id": next_id(st, "goal"), "description": description[:200], "kind": kind,
         "params": params or {}, "status": "active", "priority": max(0.0, min(1.0, float(priority))),
         "origin": origin, "progress": 0.0, "created": st["tick"], "updated": st["tick"]}
    if kind == "earn_money":
        g["params"].setdefault("start", agent["money"])
    agent["goals"].append(g)
    active = [x for x in agent["goals"] if x["status"] == "active"]
    if len(active) > 5:   # on garde les 5 plus prioritaires
        worst = min(active, key=lambda x: x["priority"])
        worst["status"] = "abandoned"
    return g


def active_goals(agent):
    return sorted([g for g in agent["goals"] if g["status"] == "active"], key=lambda g: -g["priority"])


def set_status(sim, agent, goal_id, status, why=""):
    for g in agent["goals"]:
        if g["id"] == goal_id and g["status"] == "active":
            g["status"] = status
            g["updated"] = sim.state["tick"]
            return g
    return None


def update_progress(sim, agent):
    """Vérifie automatiquement les objectifs mesurables. Renvoie la liste des objectifs accomplis."""
    done = []
    st = sim.state
    for g in agent["goals"]:
        if g["status"] != "active":
            continue
        p, k = g["params"], g["kind"]
        prog = g["progress"]
        if k == "earn_money":
            target = float(p.get("amount", 0) or 0)
            start = float(p.get("start", 0))
            if target > start:
                prog = (agent["money"] - start) / (target - start)
        elif k == "obtain_item":
            want = str(p.get("name") or p.get("kind") or "").lower()
            if want:
                prog = 1.0 if any(want in (st["items"][i]["name"] + " " + st["items"][i]["kind"]).lower()
                                  for i in agent["inventory"] if i in st["items"]) else 0.0
        elif k == "meet":
            tgt = p.get("agent")
            prog = 1.0 if tgt in agent["relationships"] and agent["relationships"][tgt].get("met_tick") is not None else 0.0
        elif k == "create_place":
            prog = 1.0 if any(pl["created_by"] == agent["id"] for pl in st["places"].values()) else prog
        elif k == "improve_relation":
            tgt, target = p.get("agent"), float(p.get("trust", 0.7))
            r = agent["relationships"].get(tgt)
            if r:
                prog = r["trust"] / max(0.01, target)
        elif k == "learn_skill":
            prog = agent["skills"].get(p.get("skill", ""), 0.0) / max(0.1, float(p.get("level", 1.0)))
        g["progress"] = round(max(0.0, min(1.0, prog)), 3)
        if g["progress"] >= 1.0 and k != "other":
            g["status"] = "done"
            g["updated"] = st["tick"]
            done.append(g)
    return done
