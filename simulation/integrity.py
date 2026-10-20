"""Contrôles d'intégrité de l'état (conservation de la monnaie, références, positions)."""
from simulation.world import walkable


def check(state):
    errs = []
    agents, places, items = state["agents"], state["places"], state["items"]
    total = state["treasury"] + sum(a["money"] for a in agents.values())
    if total != state["money_total"]:
        errs.append(f"monnaie non conservée : {total} ≠ {state['money_total']}")
    if state["treasury"] < 0:
        errs.append("trésorerie négative")
    for a in agents.values():
        if a["money"] < 0:
            errs.append(f"{a['id']}: solde négatif")
        if a["place"] not in places:
            errs.append(f"{a['id']}: lieu inconnu {a['place']}")
        elif a["x"] is not None:
            p = places[a["place"]]
            rx, ry, rw, rh = p["rect"]
            if not (rx <= a["x"] < rx + rw and ry <= a["y"] < ry + rh):
                errs.append(f"{a['id']}: position hors du lieu {p['name']}")
            if not walkable(state, a["x"], a["y"]):
                errs.append(f"{a['id']}: position interdite ({a['x']},{a['y']})")
        for iid in a["inventory"]:
            if iid not in items:
                errs.append(f"{a['id']}: objet fantôme {iid}")
            elif items[iid]["owner"] != a["id"]:
                errs.append(f"{a['id']}: objet {iid} appartient à {items[iid]['owner']}")
        if len(set(a["inventory"])) != len(a["inventory"]):
            errs.append(f"{a['id']}: inventaire en double")
        if a["home"] and (a["home"] not in places or a["id"] not in places[a["home"]]["tenants"]):
            errs.append(f"{a['id']}: logement incohérent")
        for oid in list(a["relationships"]) + list(a["contacts"]):
            if oid not in agents:
                errs.append(f"{a['id']}: référence inconnue {oid}")
    for it in items.values():
        o = it["owner"]
        if o != "city" and o not in agents:
            errs.append(f"objet {it['id']}: propriétaire inconnu {o}")
        elif o in agents and it["id"] not in agents[o]["inventory"]:
            errs.append(f"objet {it['id']}: absent de l'inventaire de {o}")
        if o == "city" and it.get("place") not in places:
            errs.append(f"objet {it['id']}: stock sans lieu")
    for p in places.values():
        if p["owner"] not in (None, "city") and p["owner"] not in agents:
            errs.append(f"lieu {p['id']}: propriétaire inconnu")
        if len(p["tenants"]) > max(p["capacity"], 0) + 0:
            errs.append(f"lieu {p['id']}: surcapacité")
        for t in p["tenants"]:
            if t not in agents or agents[t]["home"] != p["id"]:
                errs.append(f"lieu {p['id']}: locataire incohérent {t}")
    for c in state["conversations"].values():
        for pid in c["participants"]:
            if pid not in agents:
                errs.append(f"conversation {c['id']}: participant inconnu")
    for m in state["messages"]:
        if m["from"] not in agents or m["to"] not in agents:
            errs.append(f"message {m['id']}: agent inconnu")
        elif m["to"] not in [m["to"]] or m["from"] not in agents[m["from"]]["contacts"] and False:
            pass
    for p in state["posts"].values():
        if p["reply_to"] and p["reply_to"] not in state["posts"]:
            errs.append(f"post {p['id']}: parent introuvable")
    return errs
