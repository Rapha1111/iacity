"""Fabrication d'objets et construction de lieux (validées par le moteur)."""
from agents import emotions
from agents.memory import add_memory
from simulation.state import clean_text
from simulation.world import FOOD_KINDS, BUILDABLE_TYPES, PLACE_TYPES, convert_plot
from systems import economy

MAX_INGREDIENTS = 5
BUILD_MATERIALS = {"bois": 3, "metal": 2}


def craft(sim, agent, name, description, category, ingredient_ids, price=None):
    st = sim.state
    name = clean_text(name, 60)
    if not name:
        return False, "nom d'objet manquant"
    if category not in economy.CATEGORIES or category == "ressource":
        return False, f"catégorie invalide ({', '.join(c for c in economy.CATEGORIES if c != 'ressource')})"
    ids = list(dict.fromkeys(ingredient_ids or []))
    if not ids or len(ids) > MAX_INGREDIENTS:
        return False, f"il faut 1 à {MAX_INGREDIENTS} ingrédients de votre inventaire"
    items = []
    for i in ids:
        it = st["items"].get(i)
        if not it or it["owner"] != agent["id"]:
            return False, f"ingrédient {i} non possédé"
        items.append(it)
    food = sum(1 for it in items if it["kind"] in FOOD_KINDS or it["category"] == "nourriture")
    if category == "nourriture" and food == 0:
        return False, "un plat demande au moins un ingrédient comestible (farine, fruit, herbes…)"
    skill = agent["skills"].get("cuisine" if category == "nourriture" else "artisanat", 0.0)
    quality = round(1.0 + min(skill, 4.0) * 0.5, 2)
    cost = int(sum(it["cost"] for it in items) * 1.2) + 1
    effects = {}
    if category == "nourriture":
        effects = {"comfort": int(10 + 9 * food + 3 * quality), "fun": 3}
    elif category == "loisir":
        effects = {"fun": int(12 + 5 * len(items) + 3 * quality)}
    elif category == "outil":
        effects = {"curiosity": 6}
    for it in items:
        economy.destroy_item(sim, it)
    new = economy.create_item(sim, name, description or f"{name}, fabriqué par {agent['name']}", agent["id"], agent["id"],
                              category, "creation", cost, quality, effects)
    if price is not None:
        economy.list_item(sim, agent, new["id"], price)
    agent["busy_until"] = st["tick"] + 4
    agent["current_activity"] = f"fabrique « {new['name']} »"
    agent["stats"]["crafted"] += 1
    agent["skills"]["artisanat"] = round(agent["skills"].get("artisanat", 0) + 0.15, 2)
    if category == "nourriture":
        agent["skills"]["cuisine"] = round(agent["skills"].get("cuisine", 0) + 0.2, 2)
    emotions.nudge(agent, joy=0.12, curiosity=0.05)
    emotions.satisfy(agent, curiosity=8)
    sim.emit("craft", [agent["id"]], f"{agent['name']} fabrique « {new['name']} » ({category}, qualité {quality})",
             {"item": new["id"], "ingredients": [it["name"] for it in items], "cost": cost}, place=agent["place"])
    add_memory(sim, agent, "experience", f"J'ai fabriqué « {new['name']} » avec {', '.join(it['name'] for it in items)}.", importance=0.65)
    return True, f"créé : {new['name']} ({new['id']})"


def build(sim, agent, plot, name, ptype, description=""):
    st = sim.state
    if plot["type"] != "terrain" or plot["owner"] != "city" or plot["built"]:
        return False, "cet emplacement n'est pas disponible"
    if agent["place"] != plot["id"]:
        return False, "rendez-vous d'abord sur le terrain (teleport)"
    if ptype not in BUILDABLE_TYPES:
        return False, f"type de lieu non constructible ({', '.join(BUILDABLE_TYPES)})"
    name = clean_text(name, 50)
    if not name:
        return False, "nom manquant"
    cost = sim.cfg.build_cost + int(plot["price"] or 0)
    if agent["money"] < cost:
        return False, f"coût {cost}, vous avez {agent['money']}"
    used = []
    for kind, qty in BUILD_MATERIALS.items():
        have = [st["items"][i] for i in agent["inventory"] if i in st["items"] and st["items"][i]["kind"] == kind]
        if len(have) < qty:
            return False, f"matériaux manquants : {qty}× {kind} (vous en avez {len(have)})"
        used += have[:qty]
    ok, msg = economy.transfer(sim, agent["id"], "city", cost, "construction")
    if not ok:
        return False, msg
    for it in used:
        economy.destroy_item(sim, it)
    convert_plot(st, plot, ptype, name, agent["id"], clean_text(description, 200), st["tick"])
    emotions.nudge(agent, joy=0.3)
    sim.emit("build", [agent["id"]], f"{agent['name']} construit « {name} » ({ptype})", {"place": plot["id"], "cost": cost, "type": ptype}, place=plot["id"])
    add_memory(sim, agent, "experience", f"J'ai construit {name} ({ptype}) !", importance=0.95)
    from systems import iachat
    iachat.create_post(sim, "city", f"Nouveau lieu à IACity : {name} ({PLACE_TYPES[ptype]['label']}), créé par {agent['name']}.", name="Mairie")
    sim.state["flags"]["map_version"] = sim.state["flags"].get("map_version", 0) + 1
    return True, f"construit : {name} ({plot['id']})"
