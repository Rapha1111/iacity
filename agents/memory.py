"""Memory Engine : souvenirs subjectifs, connaissances avec provenance, oubli doux."""
import re

from simulation.state import next_id, tokens, clamp, fmt_time

MEMORY_KINDS = ("experience", "conversation", "overheard", "message", "post", "info", "lesson", "thought", "event", "transaction")


def add_memory(sim, agent, kind, content, source="self", confidence=1.0, importance=0.5,
               fact_seq=None, about=None, tick=None):
    """Ajoute un souvenir subjectif. ``fact_seq`` relie au fait enregistré dans le journal global."""
    st = sim.state
    tick = st["tick"] if tick is None else tick
    m = {
        "id": next_id(st, "mem"), "tick": tick, "time": fmt_time(sim, tick), "kind": kind,
        "content": content, "original": content, "source": source,
        "confidence": round(clamp(confidence), 3), "importance": round(clamp(importance), 3),
        "fact_seq": fact_seq, "about": about, "distorted": False,
    }
    agent["memory"].append(m)
    return m


def blur(text, confidence, rng):
    """Dégrade un texte selon la confiance : mots manquants (souvenir/écoute partielle)."""
    if confidence >= 0.85:
        return text
    words = text.split()
    keep_p = 0.35 + 0.65 * confidence
    out = [w if (rng.random() < keep_p or len(w) <= 2) else "…" for w in words]
    res = re.sub(r"(…\s*){2,}", "… ", " ".join(out)).strip()
    return res


def recall(sim, agent, query="", k=8, kinds=None):
    """Sélectionne les souvenirs pertinents : récence, importance, proximité lexicale."""
    now = sim.state["tick"]
    q = tokens(query)
    scored = []
    for m in agent["memory"][-400:]:
        if kinds and m["kind"] not in kinds:
            continue
        age = max(0, now - m["tick"])
        rec = 1.0 / (1.0 + age / 120.0)
        rel = len(q & tokens(m["content"])) / (len(q) + 1) if q else 0
        scored.append((rec * 0.5 + m["importance"] * 0.35 + rel * 0.8 + m["confidence"] * 0.1, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:k]]


def subjective_text(sim, m):
    """Texte tel que l'agent s'en souvient : brouillé si la confiance est faible."""
    return blur(m["content"], m["confidence"], sim.rng) if m["confidence"] < 0.6 else m["content"]


def decay_memories(sim, agent, rate=0.0015):
    """Oubli doux : la confiance baisse, aucun souvenir n'est supprimé. Peut déformer un peu."""
    for m in agent["memory"][-300:]:
        if m["kind"] in ("lesson",):
            continue
        m["confidence"] = round(max(0.05, m["confidence"] - rate * (1.1 - m["importance"])), 3)
        if m["confidence"] < 0.4 and not m["distorted"] and sim.rng.random() < 0.02:
            m["content"] = blur(m["content"], m["confidence"], sim.rng)
            m["distorted"] = True


# -- connaissances / rumeurs ----------------------------------------------
def add_knowledge(sim, agent, claim, about=None, source="observed", confidence=1.0, hops=0,
                  chain=None, kind="fact"):
    """Enregistre une information avec sa provenance. Une rumeur n'est pas un fait vérifié."""
    st = sim.state
    for k in agent["knowledge"]:
        if k["claim"] == claim:
            # même information reçue à nouveau : la confiance augmente un peu
            if source != "observed":
                k["confidence"] = round(clamp(max(k["confidence"], confidence) + 0.05), 3)
            return k
    k = {"id": next_id(st, "know"), "claim": claim, "about": about, "source": source,
         "confidence": round(clamp(confidence), 3), "hops": hops, "chain": list(chain or []),
         "kind": kind, "tick": st["tick"]}
    agent["knowledge"].append(k)
    return k


def add_belief(sim, agent, text, confidence=0.6, source="reflexion"):
    st = sim.state
    for b in agent["beliefs"]:
        if b["text"] == text:
            b["confidence"] = round(clamp(confidence), 3)
            return b
    b = {"id": next_id(st, "belief"), "text": text, "confidence": round(clamp(confidence), 3),
         "source": source, "tick": st["tick"]}
    agent["beliefs"].append(b)
    if len(agent["beliefs"]) > 40:
        agent["beliefs"].sort(key=lambda x: x["confidence"])
        agent["beliefs"].pop(0)
    return b
