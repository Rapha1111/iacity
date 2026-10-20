"""Événements du monde (manuels ou aléatoires). Chaque événement a un effet explicite."""
from agents import emotions
from agents.agent import find_place
from agents.memory import add_memory
from simulation.state import ticks_per_day
from simulation.world import free_plots, convert_plot, PLACE_TYPES
from systems import economy, iachat

SCENARIOS = {
    "fete": "Fête de quartier : bruit élevé sur la place, les présents se détendent (loisirs/social), annonce sur IACHAT.",
    "panne": "Panne de courant : commerces et lieux de travail fermés pendant 3 h simulées.",
    "ouverture_commerce": "Ouverture d'un commerce municipal sur un terrain libre (sinon réapprovisionnement exceptionnel).",
    "penurie": "Pénurie : stocks vidés, réapprovisionnement bloqué 6 h, prix ×1,8.",
    "incident": "Incident public dans une rue : peur chez les personnes proches, annonce de la mairie.",
    "regle_eco": "Changement de règle économique : loyers et salaires modifiés (paramètres rent_mult / wage_mult).",
    "subvention": "Subvention : la Ville verse 25 à chaque habitant (prélevé sur la trésorerie).",
}


def trigger(sim, key, params=None, by_user=True):
    """Déclenche un scénario. Renvoie (ok, description)."""
    params = params or {}
    if key not in SCENARIOS:
        return False, f"événement inconnu : {key}"
    st = sim.state
    tick = st["tick"]
    tpd = ticks_per_day(sim)
    hour = tpd // 24
    desc = ""
    if key == "fete":
        place = find_place(sim, params.get("place") or "plaza") or [p for p in st["places"].values() if p["type"] == "plaza"][0]
        st["effects"].append({"key": "fete", "until": tick + 2 * hour, "data": {"place": place["id"]}})
        for a in st["agents"].values():
            if a["place"] == place["id"]:
                emotions.satisfy(a, fun=30, social=15)
                emotions.nudge(a, joy=0.3)
                add_memory(sim, a, "event", f"J'ai participé à la fête de quartier à {place['name']}.", importance=0.7)
        iachat.create_post(sim, "city", f"Fête de quartier à {place['name']} ! Venez nombreux.", name="Mairie")
        desc = f"Fête de quartier à {place['name']}"
    elif key == "panne":
        st["effects"].append({"key": "panne", "until": tick + 3 * hour, "data": {}})
        for a in st["agents"].values():
            emotions.nudge(a, frustration=0.1, fear=0.05)
            add_memory(sim, a, "event", "Panne de courant générale : commerces et bureaux fermés.", importance=0.6, confidence=0.9)
        iachat.create_post(sim, "city", "Panne de courant en cours. Les commerces sont fermés temporairement.", name="Mairie")
        desc = "Panne de courant (3 h)"
    elif key == "ouverture_commerce":
        plots = free_plots(st)
        if plots:
            p = plots[0]
            ptype = params.get("type") if params.get("type") in ("epicerie", "atelier", "restaurant", "bar") else "epicerie"
            convert_plot(st, p, ptype, f"{PLACE_TYPES[ptype]['label']} Municipal(e) {p['id']}", "city", "Ouvert par la Ville", tick)
            st["flags"]["map_version"] = st["flags"].get("map_version", 0) + 1
            economy.restock(sim)
            iachat.create_post(sim, "city", f"Nouveau commerce : {p['name']} ouvre ses portes !", name="Mairie")
            desc = f"Ouverture de {p['name']}"
        else:
            economy.restock(sim)
            desc = "Pas de terrain libre : réapprovisionnement exceptionnel"
    elif key == "penurie":
        for it in [i for i in st["items"].values() if i["owner"] == "city"]:
            economy.destroy_item(sim, it)
        st["effects"].append({"key": "penurie", "until": tick + 6 * hour, "data": {}})
        st["flags"]["price_mult"] = 1.8
        iachat.create_post(sim, "city", "Pénurie dans les commerces : les prix augmentent.", name="Mairie")
        desc = "Pénurie (stocks vidés, prix ×1,8)"
    elif key == "incident":
        streets = [p for p in st["places"].values() if p["type"] == "rue"]
        place = sim.rng.choice(streets)
        x, y, w, h = place["rect"]
        cx = sim.rng.randrange(x + 3, x + w - 3)
        for a in st["agents"].values():
            if a["x"] is not None and not st["places"][a["place"]]["indoor"] and abs(a["x"] - cx) < 12 and abs(a["y"] - y) < 8:
                emotions.nudge(a, fear=0.35, anger=0.05)
                add_memory(sim, a, "event", f"J'ai assisté à un incident dans la {place['name']}.", importance=0.85)
        iachat.create_post(sim, "city", f"Incident signalé dans la {place['name']}. La police est sur place.", name="Mairie")
        desc = f"Incident public ({place['name']})"
    elif key == "regle_eco":
        rent = float(params.get("rent_mult", sim.rng.choice([0.7, 1.3, 1.6])))
        wage = float(params.get("wage_mult", sim.rng.choice([0.8, 1.2, 1.4])))
        st["flags"]["rent_mult"] = max(0.1, min(5.0, rent))
        st["flags"]["wage_mult"] = max(0.1, min(5.0, wage))
        iachat.create_post(sim, "city", f"Nouvelle règle économique : loyers ×{st['flags']['rent_mult']}, salaires ×{st['flags']['wage_mult']}.", name="Mairie")
        for a in st["agents"].values():
            add_memory(sim, a, "event", f"La mairie a changé les règles : loyers ×{st['flags']['rent_mult']}, salaires ×{st['flags']['wage_mult']}.", importance=0.6, confidence=0.8)
        desc = f"Règle économique (loyers ×{st['flags']['rent_mult']}, salaires ×{st['flags']['wage_mult']})"
    elif key == "subvention":
        amount = int(params.get("amount", 25))
        for a in st["agents"].values():
            if st["treasury"] >= amount:
                economy.transfer(sim, "city", a["id"], amount, "subvention")
                emotions.nudge(a, joy=0.15)
                add_memory(sim, a, "event", f"J'ai reçu une subvention de {amount}.", importance=0.5)
        iachat.create_post(sim, "city", f"Subvention exceptionnelle de {amount} versée aux habitants.", name="Mairie")
        desc = f"Subvention ({amount} par habitant)"
    for a in st["agents"].values():
        if not a["is_human"]:
            a["inbox"].append({"kind": "event", "key": key, "tick": tick})
    sim.emit("world_event", [], f"Événement{' (utilisateur)' if by_user else ''} : {desc}", {"key": key, "params": params, "by_user": by_user})
    return True, desc


def process(sim):
    st = sim.state
    tick = st["tick"]
    keep = []
    for e in st["effects"]:
        if e["until"] <= tick:
            if e["key"] == "penurie":
                st["flags"]["price_mult"] = 1.0
            sim.emit("world_event", [], f"Fin de l'événement : {e['key']}", {"key": e["key"], "end": True})
        else:
            keep.append(e)
    st["effects"] = keep
    # événements aléatoires (fréquence par jour simulé)
    p = sim.cfg.event_frequency / ticks_per_day(sim)
    if p > 0 and sim.rng.random() < p:
        key = sim.rng.choice(["fete", "panne", "incident", "subvention", "penurie", "ouverture_commerce", "regle_eco"])
        if not any(e["key"] == key for e in st["effects"]):
            trigger(sim, key, by_user=False)
