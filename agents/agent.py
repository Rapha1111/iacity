"""Agent Engine : création et accès à l'état interne d'un agent."""
from agents import emotions
from simulation.state import next_id

FIRST_NAMES = [
    "Léa", "Hugo", "Camille", "Louis", "Inès", "Jules", "Manon", "Noé", "Zoé", "Théo", "Chloé", "Lucas",
    "Jade", "Adam", "Anna", "Rayan", "Lina", "Tom", "Sarah", "Nina", "Paul", "Alice", "Samir", "Elsa",
    "Yanis", "Maëlle", "Oscar", "Clara", "Malo", "Eva", "Victor", "Lola", "Ravi", "Mia", "Axel",
]


def new_agent(sim, name=None, is_human=False, place=None):
    st = sim.state
    rng = sim.rng
    aid = next_id(st, "agent")
    used = {a["name"] for a in st["agents"].values()}
    if not name:
        pool = [n for n in FIRST_NAMES if n not in used] or [f"Habitant{len(used) + 1}"]
        name = rng.choice(pool)
    numbers = {a["number"] for a in st["agents"].values()}
    num = None
    while num is None or num in numbers:
        num = "555-%04d" % rng.randrange(1000, 9999)
    agent = {
        "id": aid, "name": name, "is_human": is_human, "hue": rng.randrange(360),
        "x": None, "y": None, "place": None,
        "inventory": [], "money": sim.cfg.start_money,
        "needs": emotions.initial_needs(rng), "emotions": emotions.initial_emotions(),
        "personality": emotions.initial_personality(rng),
        "beliefs": [], "values": [], "goals": [], "plan": [], "skills": {},
        "relationships": {}, "contacts": {}, "knowledge": [], "memory": [],
        "current_activity": "arrive en ville", "busy_until": 0, "reputation": {},
        "number": num, "home": None, "profile": {"bio": "", "show_number": False},
        "last_say": None, "inbox": [], "feed_cursor": 0, "routines": {}, "last_llm_tick": -999,
        "failures": [], "bond_proposals": [], "lessons": {}, "stats": {"sold": 0, "bought": 0, "worked": 0, "crafted": 0},
        "arrears": 0, "created": st["tick"], "known_places": {}, "last_read": [],
    }
    st["agents"][aid] = agent
    st["money_total"] += agent["money"]
    return agent


def find_agent(sim, ref, include_self=None):
    """Résout un agent par id, nom exact ou préfixe (insensible à la casse)."""
    if not ref or not isinstance(ref, str):
        return None
    agents = sim.state["agents"]
    if ref in agents:
        return agents[ref]
    low = ref.strip().lower()
    for a in agents.values():
        if a["name"].lower() == low:
            return a
    matches = [a for a in agents.values() if a["name"].lower().startswith(low)]
    return matches[0] if len(matches) == 1 else None


def find_place(sim, ref):
    if not ref or not isinstance(ref, str):
        return None
    places = sim.state["places"]
    if ref in places:
        return places[ref]
    low = ref.strip().lower()
    for p in places.values():
        if p["name"].lower() == low:
            return p
    cands = [p for p in places.values() if low in p["name"].lower() or low == p["type"]]
    return cands[0] if len(cands) >= 1 else None


def place_of(sim, agent):
    return sim.state["places"].get(agent["place"]) or sim.state["places"]["p_outdoor"]


def inventory_items(sim, agent):
    items = sim.state["items"]
    return [items[i] for i in agent["inventory"] if i in items]
