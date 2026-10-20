"""Messaging Engine : carnet de contacts, numéros de téléphone, messages privés."""
from agents.agent import find_agent, place_of
from agents.memory import add_memory
from simulation.state import next_id, clean_text
from systems import communication, relationships


def add_contact(sim, owner, other, provenance):
    """Ajoute/Met à jour un contact. Jamais deviné : appelé uniquement par des règles explicites."""
    if other["id"] == owner["id"]:
        return False
    new = other["id"] not in owner["contacts"]
    if new:
        owner["contacts"][other["id"]] = {"number": other["number"], "name": other["name"],
                                           "provenance": provenance, "tick": sim.state["tick"]}
        add_memory(sim, owner, "info", f"J'ai le numéro de {other['name']} : {other['number']} ({provenance}).", importance=0.5, about=other["id"])
        sim.emit("contact", [owner["id"], other["id"]], f"{owner['name']} obtient le numéro de {other['name']} ({provenance})", {"provenance": provenance})
    return new


def resolve_contact(owner, ref):
    """Résout une référence (id, nom ou numéro) uniquement parmi les contacts connus."""
    if not isinstance(ref, str):
        return None
    low = ref.strip().lower()
    for cid, c in owner["contacts"].items():
        if low in (cid.lower(), c["number"].lower(), c["name"].lower()):
            return cid
    return None


def give_number(sim, giver, target):
    if communication.audibility(sim, giver, target, "normal") <= 0.0:
        return False, f"{target['name']} est hors de portée"
    if giver["id"] in target["contacts"]:
        return False, f"{target['name']} a déjà ce numéro"
    add_contact(sim, target, giver, f"donné en personne par {giver['name']}")
    add_memory(sim, giver, "experience", f"J'ai donné mon numéro à {target['name']}.", importance=0.45, about=target["id"])
    relationships.adjust(sim, target, giver, trust=0.03, friendship=0.02, log=False)
    return True, "numéro donné"


def share_contact(sim, sharer, about, target):
    if about["id"] not in sharer["contacts"]:
        return False, "vous ne connaissez pas ce numéro"
    if communication.audibility(sim, sharer, target, "normal") <= 0.0:
        return False, f"{target['name']} est hors de portée"
    if about["id"] == target["id"]:
        return False, "c'est son propre numéro"
    if about["id"] in target["contacts"]:
        return False, "déjà connu"
    add_contact(sim, target, about, f"transmis par {sharer['name']}")
    return True, "numéro transmis"


def learn_public_numbers(sim, agent):
    """Règle du monde : le propriétaire d'un commerce affiche son numéro sur la devanture."""
    p = place_of(sim, agent)
    owner = sim.state["agents"].get(p.get("owner"))
    if owner and owner["id"] != agent["id"] and p["indoor"] and PLACE_COMMERCE(p):
        add_contact(sim, agent, owner, f"affiché à {p['name']}")


def PLACE_COMMERCE(p):
    from simulation.world import PLACE_TYPES
    return PLACE_TYPES.get(p["type"], {}).get("commerce", False)


def send_dm(sim, sender, ref, text):
    st = sim.state
    text = clean_text(text, 280)
    if not text:
        return False, "message vide"
    tid = resolve_contact(sender, ref)
    if tid is None:
        return False, "numéro inconnu : vous ne pouvez écrire qu'à une personne dont vous connaissez le numéro"
    target = st["agents"].get(tid)
    if target is None:
        return False, "destinataire introuvable"
    mid = next_id(st, "msg")
    msg = {"id": mid, "from": sender["id"], "to": tid, "text": text, "tick": st["tick"],
           "status": "delivered", "read_tick": None}
    st["messages"].append(msg)
    seq = sim.emit("dm", [sender["id"], tid], f"{sender['name']} → {target['name']} (SMS) : {text}", {"msg": mid, "text": text})
    add_memory(sim, sender, "message", f"J'ai écrit à {target['name']} : « {text} »", importance=0.4, fact_seq=seq, about=tid)
    add_memory(sim, target, "message", f"Message reçu de {sender['name']} : « {text} »", source=sender["id"], importance=0.55, fact_seq=seq, about=sender["id"])
    tone = relationships.text_sentiment(text)
    relationships.interaction(sim, sender, target, tone)
    if sender["id"] not in target["contacts"]:
        pass  # le destinataire voit un numéro inconnu : pas d'ajout automatique
    return True, "message envoyé"


def unread_for(sim, agent):
    return [m for m in sim.state["messages"] if m["to"] == agent["id"] and m["status"] != "read"]


def mark_read(sim, agent):
    out = []
    for m in unread_for(sim, agent):
        m["status"] = "read"
        m["read_tick"] = sim.state["tick"]
        out.append(m)
    return out


def thread(sim, a_id, b_id, offset=0, limit=50):
    msgs = [m for m in sim.state["messages"] if {m["from"], m["to"]} == {a_id, b_id}]
    return msgs[offset:offset + limit]


def messages_of(sim, agent_id):
    return [m for m in sim.state["messages"] if agent_id in (m["from"], m["to"])]
