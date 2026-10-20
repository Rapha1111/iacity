"""Social Engine : relations dirigées, confiance, hostilité, réputation, liens."""
from agents import emotions
from agents.memory import add_memory
from simulation.state import clamp, fmt_time

POSITIVE = ["merci", "super", "content", "ravi", "bravo", "ami", "plaisir", "génial", "genial", "bien",
            "sympa", "heureux", "adore", "bonjour", "salut", "volontiers", "d'accord", "excellent", "belle"]
NEGATIVE = ["nul", "déteste", "deteste", "arnaque", "menteur", "voleur", "idiot", "colère", "colere",
            "jamais", "ridicule", "dégoût", "honte", "trahi", "mensonge", "mauvais", "furieux", "tais-toi"]
BOND_TYPES = ("ami", "famille", "couple", "collegue", "allie", "rival", "partenaire")


def text_sentiment(text):
    low = text.lower()
    s = sum(1 for w in POSITIVE if w in low) - sum(1 for w in NEGATIVE if w in low)
    return max(-1.0, min(1.0, s / 2.0))


def rel(agent, other_id):
    r = agent["relationships"].get(other_id)
    if r is None:
        r = {"trust": 0.0, "friendship": 0.0, "rivalry": 0.0, "hostility": 0.0, "types": [],
             "met_tick": None, "last_interaction": None, "interactions": 0, "history": [], "opinion": ""}
        agent["relationships"][other_id] = r
    return r


def meet(sim, a, b, why="rencontre"):
    """Première rencontre : crée la connaissance mutuelle."""
    tick = sim.state["tick"]
    new = False
    for x, y in ((a, b), (b, a)):
        r = rel(x, y["id"])
        if r["met_tick"] is None:
            r["met_tick"] = tick
            r["trust"] = max(r["trust"], 0.2)
            r["history"].append({"tick": tick, "delta": "rencontre", "why": why})
            add_memory(sim, x, "experience", f"J'ai rencontré {y['name']} ({why}).", importance=0.55, about=y["id"])
            new = True
    if new:
        sim.emit("relationship", [a["id"], b["id"]], f"{a['name']} et {b['name']} font connaissance", {"why": why})
    return new


def adjust(sim, a, b, trust=0.0, friendship=0.0, rivalry=0.0, hostility=0.0, why="", log=True):
    """Modifie la vision qu'a ``a`` de ``b``."""
    r = rel(a, b["id"])
    before = (r["trust"], r["friendship"], r["rivalry"], r["hostility"])
    r["trust"] = round(clamp(r["trust"] + trust), 3)
    r["friendship"] = round(clamp(r["friendship"] + friendship), 3)
    r["rivalry"] = round(clamp(r["rivalry"] + rivalry), 3)
    r["hostility"] = round(clamp(r["hostility"] + hostility), 3)
    r["last_interaction"] = sim.state["tick"]
    r["interactions"] += 1
    if r["met_tick"] is None:
        r["met_tick"] = sim.state["tick"]
    after = (r["trust"], r["friendship"], r["rivalry"], r["hostility"])
    if why and max(abs(x - y) for x, y in zip(before, after)) >= 0.04:
        r["history"].append({"tick": sim.state["tick"], "delta": [round(y - x, 3) for x, y in zip(before, after)], "why": why})
        if log:
            sim.emit("relationship", [a["id"], b["id"]], f"{a['name']} → {b['name']} : {why}",
                     {"trust": r["trust"], "friendship": r["friendship"], "hostility": r["hostility"], "why": why})
    return r


def interaction(sim, speaker, listener, tone):
    """Effet d'un échange verbal (tone entre -1 et 1)."""
    if tone > 0:
        adjust(sim, listener, speaker, trust=0.05 * tone, friendship=0.04 * tone, why="échange agréable" if tone > 0.5 else "", log=tone > 0.5)
        emotions.nudge(listener, joy=0.04 * tone, trust=0.02 * tone)
        adjust(sim, speaker, listener, friendship=0.01 * tone, log=False)
    elif tone < 0:
        adjust(sim, listener, speaker, trust=0.05 * tone, hostility=-0.06 * tone, why="propos hostiles")
        emotions.nudge(listener, anger=-0.1 * tone, sadness=-0.03 * tone)
    else:
        adjust(sim, listener, speaker, friendship=0.002, log=False)


def propose_bond(sim, proposer, target, btype):
    if btype not in BOND_TYPES:
        return False, "type de lien inconnu"
    r = rel(target, proposer["id"])
    if any(p["from"] == proposer["id"] and p["type"] == btype for p in target["bond_proposals"]):
        return False, "proposition déjà envoyée"
    target["bond_proposals"].append({"from": proposer["id"], "type": btype, "tick": sim.state["tick"]})
    add_memory(sim, target, "experience", f"{proposer['name']} me propose un lien : {btype}.", importance=0.7, about=proposer["id"])
    target["inbox"].append({"kind": "bond", "from": proposer["id"], "type": btype, "tick": sim.state["tick"]})
    sim.emit("bond", [proposer["id"], target["id"]], f"{proposer['name']} propose « {btype} » à {target['name']}")
    return True, "proposition envoyée"


def answer_bond(sim, agent, from_id, accept):
    props = [p for p in agent["bond_proposals"] if p["from"] == from_id]
    if not props:
        return False, "aucune proposition de cet agent"
    other = sim.state["agents"].get(from_id)
    agent["bond_proposals"] = [p for p in agent["bond_proposals"] if p["from"] != from_id]
    for p in props:
        if accept and other:
            for x, y in ((agent, other), (other, agent)):
                r = rel(x, y["id"])
                if p["type"] not in r["types"]:
                    r["types"].append(p["type"])
                adjust(sim, x, y, trust=0.08, friendship=0.08, why=f"lien accepté : {p['type']}")
            sim.emit("bond", [agent["id"], from_id], f"{agent['name']} accepte « {p['type']} » avec {other['name']}")
            add_memory(sim, agent, "experience", f"J'ai accepté le lien « {p['type']} » avec {other['name']}.", importance=0.8, about=from_id)
            add_memory(sim, other, "experience", f"{agent['name']} a accepté le lien « {p['type']} ».", importance=0.8, about=agent["id"])
        elif other:
            adjust(sim, other, agent, trust=-0.03, why="proposition refusée")
            add_memory(sim, other, "experience", f"{agent['name']} a refusé mon lien « {p['type']} ».", importance=0.6, about=agent["id"])
    return True, "réponse enregistrée"


def recompute_reputation(sim):
    st = sim.state
    for a in st["agents"].values():
        opinions = [o["relationships"][a["id"]]["trust"] for o in st["agents"].values()
                    if o["id"] != a["id"] and a["id"] in o["relationships"] and o["relationships"][a["id"]]["met_tick"] is not None]
        sold = a["stats"]["sold"]
        a["reputation"] = {
            "general": round(sum(opinions) / len(opinions), 3) if opinions else None,
            "opinions": len(opinions),
            "commerce": round(min(1.0, 0.3 + 0.07 * sold), 3) if sold else None,
        }
