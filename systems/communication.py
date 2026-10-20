"""Communication Engine : portée, bruit, obstacles, conversations en personne.

Tout le calcul d'audibilité est centralisé dans :func:`audibility`.
"""
from agents.agent import place_of
from agents.memory import add_memory, add_knowledge, blur
from simulation.state import next_id, clean_text, clamp
from simulation.world import distance
from systems import relationships

VOLUME_RANGE = {"whisper": 0.3, "normal": 1.0, "shout": 2.6}
VOLUMES = tuple(VOLUME_RANGE)


def ambient_noise(sim, place):
    st = sim.state
    n = place["noise"] + 0.02 * sum(1 for a in st["agents"].values() if a["place"] == place["id"])
    for eff in st["effects"]:
        if eff["key"] == "fete" and eff["data"].get("place") == place["id"]:
            n += 0.5
        if eff["key"] == "fete" and not place["indoor"] and eff["data"].get("place") != place["id"]:
            n += 0.05
    return clamp(n, 0.0, 1.0)


def walls_between(sp, lp):
    if sp["id"] == lp["id"]:
        return 0
    return (1 if sp["indoor"] else 0) + (1 if lp["indoor"] else 0)


def audibility(sim, speaker, listener, volume="normal"):
    """Score d'audibilité 0..1 (distance, murs, bruit, volume)."""
    if speaker.get("x") is None or listener.get("x") is None:
        return 0.0
    cfg = sim.cfg
    sp, lp = place_of(sim, speaker), place_of(sim, listener)
    rng = cfg.conversation_range * VOLUME_RANGE.get(volume, 1.0) * (cfg.wall_attenuation ** walls_between(sp, lp))
    d = distance(speaker, listener)
    if rng <= 0 or d >= rng:
        return 0.0
    score = (1.0 - d / rng) * 0.85 + 0.15
    score -= ambient_noise(sim, lp) * cfg.noise_effect * 0.5
    return round(clamp(score), 3)


def visible(sim, a, b):
    """Perception visuelle : même lieu, ou deux extérieurs proches."""
    if a.get("x") is None or b.get("x") is None:
        return False
    pa, pb = place_of(sim, a), place_of(sim, b)
    if pa["id"] == pb["id"]:
        return True
    return (not pa["indoor"]) and (not pb["indoor"]) and distance(a, b) <= 8


def people_around(sim, agent):
    return [o for o in sim.state["agents"].values() if o["id"] != agent["id"] and visible(sim, agent, o)]


# -- conversations --------------------------------------------------------
def open_conversations(sim):
    return [c for c in sim.state["conversations"].values() if c["state"] == "open"]


def _find_or_open(sim, speaker, target):
    st = sim.state
    for c in open_conversations(sim):
        if c["place"] != speaker["place"]:
            continue
        if speaker["id"] in c["participants"] and (target is None or target["id"] in c["participants"]):
            return c
    if target is not None:
        for c in open_conversations(sim):
            if c["place"] == speaker["place"] and target["id"] in c["participants"] and speaker["id"] not in c["participants"]:
                c["participants"].append(speaker["id"])
                return c
    for c in open_conversations(sim):
        if speaker["id"] in c["participants"] and c["place"] == speaker["place"]:
            if target is not None:
                c["participants"].append(target["id"])
            return c
    cid = next_id(st, "conv")
    c = {"id": cid, "place": speaker["place"], "participants": [speaker["id"]] + ([target["id"]] if target else []),
         "state": "open", "opened": st["tick"], "last_tick": st["tick"], "turns": [], "closed_tick": None}
    st["conversations"][cid] = c
    sim.emit("conversation", c["participants"], f"Conversation ouverte ({sim.state['places'][c['place']]['name']})", {"conv": cid})
    return c


def close_conversation(sim, c, why="fin"):
    if c["state"] == "closed":
        return
    c["state"] = "closed"
    c["closed_tick"] = sim.state["tick"]
    sim.emit("conversation_end", c["participants"], f"Conversation terminée ({why}, {len(c['turns'])} répliques)", {"conv": c["id"]})


def leave_conversations(sim, agent, why="part"):
    for c in open_conversations(sim):
        if agent["id"] in c["participants"]:
            c["participants"].remove(agent["id"])
            if len(c["participants"]) < 2:
                close_conversation(sim, c, f"{agent['name']} {why}")


def upkeep(sim):
    st = sim.state
    for c in open_conversations(sim):
        c["participants"] = [p for p in c["participants"] if p in st["agents"] and st["agents"][p]["place"] == c["place"]]
        if len(c["participants"]) < 2:
            close_conversation(sim, c, "participants partis")
        elif st["tick"] - c["last_tick"] > sim.cfg.conversation_idle_ticks:
            close_conversation(sim, c, "silence")
        elif len(c["turns"]) >= sim.cfg.conversation_max_turns:
            close_conversation(sim, c, "longueur max")


def speak(sim, speaker, text, to=None, volume="normal", claim=None, tone=None):
    """Prononce une réplique ; renvoie (ok, message). Les auditeurs sont calculés ici."""
    st = sim.state
    text = clean_text(text, 240)
    if not text:
        return False, "réplique vide"
    if volume not in VOLUME_RANGE:
        volume = "normal"
    target = to if isinstance(to, dict) else None
    if target and target["id"] == speaker["id"]:
        return False, "on ne se parle pas à soi-même"
    if target and audibility(sim, speaker, target, volume) <= 0.0:
        return False, f"{target['name']} est hors de portée"
    conv = _find_or_open(sim, speaker, target)
    if tone is None:
        tone = relationships.text_sentiment(text)
    listeners = {}
    for o in st["agents"].values():
        if o["id"] == speaker["id"]:
            continue
        s = audibility(sim, speaker, o, volume)
        if target and o["id"] == target["id"] and s > 0:
            s = min(1.0, s + 0.25)
        if s >= 0.15:
            listeners[o["id"]] = s
    where = place_of(sim, speaker)
    data = {"conv": conv["id"], "text": text, "to": target["id"] if target else None, "volume": volume,
            "listeners": listeners, "tone": tone}
    if claim:
        data["claim"] = claim
    seq = sim.emit("say", [speaker["id"]] + list(listeners), f"{speaker['name']}" + (f" → {target['name']}" if target else "") + f" ({volume}) : {text}",
                   data, place=where["id"])
    turn = {"seq": seq, "tick": st["tick"], "speaker": speaker["id"], "text": text, "volume": volume,
            "to": target["id"] if target else None, "listeners": list(listeners)}
    conv["turns"].append(turn)
    conv["last_tick"] = st["tick"]
    if speaker["id"] not in conv["participants"]:
        conv["participants"].append(speaker["id"])
    speaker["last_say"] = {"seq": seq, "text": text, "tick": st["tick"], "volume": volume}
    add_memory(sim, speaker, "conversation", f"J'ai dit{' à ' + target['name'] if target else ''} : « {text} »",
               importance=0.35, fact_seq=seq, about=target["id"] if target else None)
    for oid, s in listeners.items():
        o = st["agents"][oid]
        addressed = bool(target and oid == target["id"])
        participant = oid in conv["participants"]
        heard = text if s >= 0.8 else blur(text, s, sim.rng)
        if s >= 0.5 and relationships.rel(o, speaker["id"])["met_tick"] is None:
            relationships.meet(sim, speaker, o, "conversation en personne")
        kind = "conversation" if (addressed or participant) else "overheard"
        add_memory(sim, o, kind, f"{speaker['name']} a dit{' (à ' + target['name'] + ')' if target else ''} : « {heard} »",
                   source=speaker["id"], confidence=s, importance=0.45 if addressed else 0.3, fact_seq=seq, about=speaker["id"])
        if s >= 0.5 or addressed:
            o["inbox"].append({"kind": "speech", "conv": conv["id"], "from": speaker["id"], "text": heard,
                               "clarity": s, "to_me": addressed, "tick": st["tick"], "seq": seq})
            del o["inbox"][:-12]
        if s >= 0.4 and (addressed or participant):
            relationships.interaction(sim, speaker, o, tone)
        if claim and s >= 0.4:
            _receive_claim(sim, speaker, o, claim, s)
    return True, "ok"


def _receive_claim(sim, speaker, listener, claim, clarity):
    """Transmission d'information : provenance conservée, confiance dépendante de la relation."""
    trust = relationships.rel(listener, speaker["id"])["trust"]
    base = claim.get("confidence", 0.8)
    conf = clamp(clarity * (0.35 + 0.65 * trust) * base)
    prior = None
    kid = claim.get("knowledge_id")
    hops, chain = 1, [speaker["id"]]
    for k in speaker["knowledge"]:
        if k["id"] == kid:
            prior = k
    if prior:
        hops, chain = prior["hops"] + 1, prior["chain"] + [speaker["id"]]
        conf = clamp(conf * max(0.3, prior["confidence"]))
    text = claim["text"]
    k = add_knowledge(sim, listener, text, about=claim.get("about"), source=speaker["id"], confidence=conf,
                      hops=hops, chain=chain, kind="rumor" if hops > 1 or claim.get("rumor") else "claim")
    add_memory(sim, listener, "info", f"{speaker['name']} m'a appris : « {text} » (confiance {conf:.2f}).",
               source=speaker["id"], confidence=conf, importance=0.5, about=claim.get("about"))
    sim.emit("info", [speaker["id"], listener["id"]], f"{speaker['name']} transmet une information à {listener['name']}",
             {"claim": text, "confidence": conf, "hops": hops, "truthful": claim.get("truthful", True), "knowledge": k["id"]})
