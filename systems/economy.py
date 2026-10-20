"""Economy Engine : monnaie, inventaires, transactions atomiques, travail, logement, lieux."""
import math

from agents import emotions
from agents.agent import place_of, inventory_items
from agents.memory import add_memory
from simulation.state import next_id, clean_text, ticks_per_day, day_of
from simulation.world import PLACE_TYPES, RAW_KINDS, FOOD_KINDS
from systems import relationships

WORK_TICKS = 12
STOCK_TARGET = 6
MEAL_PRICE = 10
CATEGORIES = ("ressource", "nourriture", "loisir", "objet", "outil", "autre")


# -- monnaie ---------------------------------------------------------------
def balance(sim, who):
    return sim.state["treasury"] if who == "city" else sim.state["agents"][who]["money"]


def _set_balance(sim, who, v):
    if who == "city":
        sim.state["treasury"] = v
    else:
        sim.state["agents"][who]["money"] = v


def transfer(sim, src, dst, amount, reason=""):
    """Transfert atomique : ne crée ni ne détruit d'argent. Renvoie (ok, message)."""
    amount = int(amount)
    if amount < 0:
        return False, "montant négatif"
    if src == dst:
        return False, "même compte"
    if src != "city" and src not in sim.state["agents"] or dst != "city" and dst not in sim.state["agents"]:
        return False, "compte inconnu"
    if balance(sim, src) < amount:
        return False, "fonds insuffisants"
    _set_balance(sim, src, balance(sim, src) - amount)
    _set_balance(sim, dst, balance(sim, dst) + amount)
    return True, "ok"


def name_of(sim, who):
    return "la Ville" if who == "city" else sim.state["agents"][who]["name"]


def price_mult(sim):
    return sim.state["flags"].get("price_mult", 1.0)


def place_open(sim, place):
    """Fermé pendant une panne (commerces et lieux de travail)."""
    if any(e["key"] == "panne" for e in sim.state["effects"]):
        return not PLACE_TYPES.get(place["type"], {}).get("wage") and not PLACE_TYPES.get(place["type"], {}).get("commerce")
    return True


# -- objets ----------------------------------------------------------------
def create_item(sim, name, description, creator, owner, category, kind, cost, quality=1.0,
                effects=None, price=None, listed=False, place=None):
    st = sim.state
    iid = next_id(st, "item")
    it = {"id": iid, "name": clean_text(name, 60), "description": clean_text(description, 200),
          "creator": creator, "owner": owner, "category": category, "kind": kind, "cost": int(cost),
          "quality": round(quality, 2), "effects": effects or {}, "price": price, "listed": listed,
          "place": place, "tick": st["tick"], "use_rules": ""}
    st["items"][iid] = it
    if owner != "city" and owner in st["agents"]:
        st["agents"][owner]["inventory"].append(iid)
    return it


def move_item(sim, item, new_owner):
    st = sim.state
    if item["owner"] in st["agents"] and item["id"] in st["agents"][item["owner"]]["inventory"]:
        st["agents"][item["owner"]]["inventory"].remove(item["id"])
    item["owner"] = new_owner
    item["listed"] = False
    item["place"] = None
    if new_owner in st["agents"]:
        st["agents"][new_owner]["inventory"].append(item["id"])


def destroy_item(sim, item):
    st = sim.state
    if item["owner"] in st["agents"] and item["id"] in st["agents"][item["owner"]]["inventory"]:
        st["agents"][item["owner"]]["inventory"].remove(item["id"])
    st["items"].pop(item["id"], None)


def city_price(sim, kind):
    base = MEAL_PRICE if kind == "repas" else RAW_KINDS.get(kind, 6)
    return max(1, int(math.ceil(base * 1.3 * sim.cfg.price_scale * price_mult(sim))))


def restock(sim):
    """Approvisionnement horaire des commerces de la Ville (sauf pénurie)."""
    st = sim.state
    if any(e["key"] == "penurie" for e in st["effects"]):
        return
    for p in st["places"].values():
        spec = PLACE_TYPES.get(p["type"], {})
        if p["owner"] != "city" or not spec.get("sells"):
            continue
        for kind in spec["sells"]:
            have = sum(1 for it in st["items"].values() if it["owner"] == "city" and it["place"] == p["id"] and it["kind"] == kind)
            for _ in range(max(0, STOCK_TARGET - have)):
                if kind == "repas":
                    create_item(sim, "Repas du jour", "Un repas chaud préparé par le restaurant.", "city", "city", "nourriture", "repas",
                                4, 1.0, {"comfort": 35, "fun": 5}, price=None, place=p["id"])
                else:
                    eff = {"comfort": 8} if kind in ("fruit",) else {}
                    create_item(sim, kind.capitalize(), f"{kind.capitalize()} (ressource)", "city", "city", "ressource", kind,
                                RAW_KINDS[kind], 1.0, eff, place=p["id"])
    # régénération naturelle du parc
    for p in st["places"].values():
        for kind in list(p["natural"]):
            p["natural"][kind] = min(10, p["natural"][kind] + 1)


def stock_here(sim, place):
    """Objets achetables dans ce lieu : stock de la Ville + objets listés par les agents présents."""
    st = sim.state
    out = []
    for it in st["items"].values():
        if it["owner"] == "city" and it["place"] == place["id"]:
            out.append((it, "city", city_price(sim, it["kind"])))
        elif it["owner"] in st["agents"] and it["listed"] and it["price"] and st["agents"][it["owner"]]["place"] == place["id"]:
            out.append((it, it["owner"], it["price"]))
    return out


def buy(sim, buyer, item_id, seller_ref=None):
    st = sim.state
    it = st["items"].get(item_id)
    if not it:
        return False, "objet introuvable"
    here = place_of(sim, buyer)
    if not place_open(sim, here):
        return False, "le lieu est fermé (panne)"
    seller = it["owner"]
    if seller == buyer["id"]:
        return False, "vous possédez déjà cet objet"
    if seller == "city":
        if it["place"] != here["id"]:
            return False, "cet objet n'est pas en vente ici"
        price = city_price(sim, it["kind"])
    else:
        s = st["agents"].get(seller)
        if not s or not it["listed"] or not it["price"]:
            return False, "cet objet n'est pas à vendre"
        if s["place"] != here["id"]:
            return False, "le vendeur n'est pas dans le même lieu"
        price = int(it["price"])
    if buyer["money"] < price:
        return False, f"fonds insuffisants ({buyer['money']} < {price})"
    ok, msg = transfer(sim, buyer["id"], seller, price, "achat")
    if not ok:
        return False, msg
    move_item(sim, it, buyer["id"])
    buyer["stats"]["bought"] += 1
    tid = next_id(st, "tx")
    tx = {"id": tid, "tick": st["tick"], "buyer": buyer["id"], "seller": seller, "items": [it["id"]],
          "item_names": [it["name"]], "price": price, "result": "ok", "place": here["id"]}
    st["transactions"].append(tx)
    sim.emit("transaction", [buyer["id"], seller], f"{buyer['name']} achète « {it['name']} » à {name_of(sim, seller)} pour {price}",
             {"tx": tid, "price": price, "item": it["id"]}, place=here["id"])
    add_memory(sim, buyer, "transaction", f"J'ai acheté « {it['name']} » à {name_of(sim, seller)} pour {price}.", importance=0.5, about=None if seller == "city" else seller)
    if seller != "city":
        s = st["agents"][seller]
        s["stats"]["sold"] += 1
        add_memory(sim, s, "transaction", f"J'ai vendu « {it['name']} » à {buyer['name']} pour {price}.", importance=0.6, about=buyer["id"])
        relationships.adjust(sim, s, buyer, trust=0.04, friendship=0.02, why="transaction réussie")
        relationships.adjust(sim, buyer, s, trust=0.04, why="transaction réussie")
        emotions.nudge(s, joy=0.1)
        s["skills"]["commerce"] = round(s["skills"].get("commerce", 0) + 0.1, 2)
    return True, f"acheté pour {price}"


def list_item(sim, agent, item_id, price):
    it = sim.state["items"].get(item_id)
    if not it or it["owner"] != agent["id"]:
        return False, "vous ne possédez pas cet objet"
    try:
        price = int(price)
    except (TypeError, ValueError):
        return False, "prix invalide"
    if price < 1 or price > 100000:
        return False, "prix hors limites"
    it["price"], it["listed"] = price, True
    sim.emit("listing", [agent["id"]], f"{agent['name']} met en vente « {it['name']} » à {price}", {"item": item_id, "price": price}, place=agent["place"])
    return True, "mis en vente"


def unlist_item(sim, agent, item_id):
    it = sim.state["items"].get(item_id)
    if not it or it["owner"] != agent["id"]:
        return False, "vous ne possédez pas cet objet"
    it["listed"] = False
    return True, "retiré de la vente"


def give(sim, giver, target, item_id=None, amount=None):
    from systems import communication
    if communication.audibility(sim, giver, target, "normal") <= 0 and giver["place"] != target["place"]:
        return False, "destinataire hors de portée"
    if item_id:
        it = sim.state["items"].get(item_id)
        if not it or it["owner"] != giver["id"]:
            return False, "vous ne possédez pas cet objet"
        move_item(sim, it, target["id"])
        sim.emit("gift", [giver["id"], target["id"]], f"{giver['name']} offre « {it['name']} » à {target['name']}", {"item": item_id})
        what = f"« {it['name']} »"
    elif amount:
        amount = int(amount)
        if amount <= 0:
            return False, "montant invalide"
        ok, msg = transfer(sim, giver["id"], target["id"], amount, "don")
        if not ok:
            return False, msg
        sim.emit("gift", [giver["id"], target["id"]], f"{giver['name']} donne {amount} à {target['name']}", {"amount": amount})
        what = f"{amount} pièces"
    else:
        return False, "rien à donner"
    add_memory(sim, giver, "experience", f"J'ai donné {what} à {target['name']}.", importance=0.5, about=target["id"])
    add_memory(sim, target, "experience", f"{giver['name']} m'a donné {what}.", importance=0.7, about=giver["id"])
    relationships.adjust(sim, target, giver, trust=0.08, friendship=0.07, why="cadeau")
    emotions.nudge(target, joy=0.15, trust=0.05)
    return True, "donné"


def consume(sim, agent, item_id):
    it = sim.state["items"].get(item_id)
    if not it or it["owner"] != agent["id"]:
        return False, "vous ne possédez pas cet objet"
    eff = it.get("effects") or {}
    if not eff:
        return False, "cet objet ne se consomme pas"
    emotions.satisfy(agent, **{k: v for k, v in eff.items() if k in agent["needs"]})
    if eff:
        emotions.nudge(agent, joy=0.05)
    destroy_item(sim, it)
    sim.emit("consume", [agent["id"]], f"{agent['name']} consomme « {it['name']} »", {"item": item_id, "effects": eff})
    add_memory(sim, agent, "experience", f"J'ai consommé « {it['name']} ».", importance=0.25)
    agent["current_activity"] = f"consomme {it['name']}"
    return True, "consommé"


# -- travail et activités ---------------------------------------------------
def work(sim, agent):
    st = sim.state
    p = place_of(sim, agent)
    spec = PLACE_TYPES.get(p["type"], {})
    if not p.get("wage") or p["type"] in ("habitation",):
        return False, "on ne peut pas travailler ici"
    if not place_open(sim, p):
        return False, "le lieu est fermé (panne)"
    wage = max(1, int(round(p["wage"] * sim.cfg.wage_scale * st["flags"].get("wage_mult", 1.0))))
    payer = p["owner"] if p["owner"] else "city"
    if payer == agent["id"]:
        return False, "vous ne pouvez pas vous payer vous-même"
    ok, msg = transfer(sim, payer, agent["id"], wage, "salaire")
    if not ok:
        return False, f"l'employeur ne peut pas payer ({name_of(sim, payer)})"
    agent["busy_until"] = st["tick"] + WORK_TICKS
    agent["current_activity"] = f"travaille ({p['name']})"
    agent["stats"]["worked"] += 1
    agent["skills"]["travail"] = round(agent["skills"].get("travail", 0) + 0.05, 2)
    emotions.satisfy(agent, security=6, curiosity=-1)
    emotions.nudge(agent, frustration=-0.02)
    sim.emit("work", [agent["id"]] + ([payer] if payer != "city" else []), f"{agent['name']} travaille à {p['name']} (+{wage})", {"wage": wage, "payer": payer}, place=p["id"])
    add_memory(sim, agent, "experience", f"J'ai travaillé à {p['name']} et gagné {wage}.", importance=0.3)
    if payer != "city":
        boss = st["agents"][payer]
        relationships.adjust(sim, agent, boss, trust=0.02, log=False)
        add_memory(sim, boss, "transaction", f"J'ai payé {wage} à {agent['name']} pour son travail à {p['name']}.", importance=0.4, about=agent["id"])
    return True, f"+{wage}"


def gather(sim, agent, kind=None):
    p = place_of(sim, agent)
    if not PLACE_TYPES.get(p["type"], {}).get("gather"):
        return False, "rien à ramasser ici"
    avail = [k for k, n in p["natural"].items() if n > 0]
    if kind and kind in p["natural"]:
        if p["natural"][kind] <= 0:
            return False, f"plus de {kind} pour l'instant"
        avail = [kind]
    elif kind:
        return False, f"{kind} ne pousse pas ici (possible : {', '.join(p['natural'])})"
    if not avail:
        return False, "les ressources sont épuisées, elles repoussent avec le temps"
    k = sim.rng.choice(avail)
    p["natural"][k] -= 1
    eff = {"comfort": 8} if k == "fruit" else {}
    it = create_item(sim, k.capitalize(), f"{k.capitalize()} ramassé(e) au parc", agent["id"], agent["id"], "ressource", k, RAW_KINDS[k], 1.0, eff)
    agent["busy_until"] = sim.state["tick"] + 3
    agent["current_activity"] = f"ramasse du/des {k}"
    emotions.satisfy(agent, curiosity=2)
    sim.emit("gather", [agent["id"]], f"{agent['name']} ramasse : {k}", {"item": it["id"], "kind": k}, place=p["id"])
    add_memory(sim, agent, "experience", f"J'ai ramassé {k} au {p['name']}.", importance=0.2)
    return True, f"obtenu : {k} ({it['id']})"


def study(sim, agent):
    p = place_of(sim, agent)
    if not PLACE_TYPES.get(p["type"], {}).get("study"):
        return False, "on ne peut pas étudier ici (école)"
    if not place_open(sim, p):
        return False, "fermé"
    agent["skills"]["savoirs"] = round(agent["skills"].get("savoirs", 0) + 0.15, 2)
    agent["busy_until"] = sim.state["tick"] + 8
    agent["current_activity"] = "étudie"
    emotions.satisfy(agent, curiosity=18)
    emotions.nudge(agent, curiosity=0.05)
    sim.emit("study", [agent["id"]], f"{agent['name']} étudie à {p['name']}", {"savoirs": agent["skills"]["savoirs"]}, place=p["id"])
    add_memory(sim, agent, "experience", "J'ai étudié et appris des choses.", importance=0.3)
    return True, "ok"


def relax(sim, agent):
    st = sim.state
    p = place_of(sim, agent)
    spec = PLACE_TYPES.get(p["type"], {})
    if not spec.get("leisure"):
        return False, "ce lieu ne se prête pas aux loisirs"
    if not place_open(sim, p):
        return False, "fermé (panne)"
    fee = int(spec.get("entry", 0))
    if fee:
        dst = p["owner"] if p["owner"] else "city"
        if dst == agent["id"]:
            fee = 0
        else:
            ok, msg = transfer(sim, agent["id"], dst, fee, "entrée")
            if not ok:
                return False, f"entrée de {fee} impossible : {msg}"
    others = sum(1 for o in st["agents"].values() if o["id"] != agent["id"] and o["place"] == p["id"])
    emotions.satisfy(agent, fun=22 + min(others, 4) * 3, social=min(others, 4) * 4)
    emotions.nudge(agent, joy=0.08)
    agent["busy_until"] = st["tick"] + 6
    agent["current_activity"] = f"se détend ({p['name']})"
    sim.emit("leisure", [agent["id"]], f"{agent['name']} se détend à {p['name']}", {"fee": fee}, place=p["id"])
    add_memory(sim, agent, "experience", f"Je me suis détendu à {p['name']}.", importance=0.25)
    return True, "ok"


def rest(sim, agent):
    st = sim.state
    p = place_of(sim, agent)
    if agent["home"] != p["id"]:
        return False, "on se repose chez soi"
    wake = st["tick"] + 10
    from simulation.state import is_night, minute_of_day
    if is_night(sim, st["tick"]):
        mins = minute_of_day(sim, st["tick"])
        left = (6 * 60 - mins) % 1440 if mins >= 22 * 60 or mins < 6 * 60 else 0
        wake = st["tick"] + max(6, left // sim.cfg.minutes_per_tick + sim.rng.randrange(0, 6))
    agent["busy_until"] = wake
    agent["current_activity"] = "se repose"
    emotions.satisfy(agent, comfort=30)
    return True, "ok"


# -- logement ----------------------------------------------------------------
def rent_home(sim, agent, place):
    st = sim.state
    if not PLACE_TYPES.get(place["type"], {}).get("housing"):
        return False, "ce lieu n'est pas un logement"
    if len(place["tenants"]) >= place["capacity"]:
        return False, "plus de place"
    if agent["home"] == place["id"]:
        return False, "vous y habitez déjà"
    rent = int(sim.cfg.rent_per_day * st["flags"].get("rent_mult", 1.0))
    if agent["money"] < rent:
        return False, f"loyer d'avance de {rent} insuffisant"
    if agent["home"]:
        leave_home(sim, agent)
    owner = place["owner"] or "city"
    if owner != agent["id"]:
        transfer(sim, agent["id"], owner, rent, "loyer d'entrée")
    place["tenants"][agent["id"]] = sim.cfg.rent_per_day
    agent["home"] = place["id"]
    agent["arrears"] = 0
    sim.emit("housing", [agent["id"]], f"{agent['name']} emménage à {place['name']}", {"rent": rent}, place=place["id"])
    add_memory(sim, agent, "experience", f"J'ai emménagé à {place['name']}.", importance=0.6)
    return True, "emménagé"


def leave_home(sim, agent):
    if not agent["home"]:
        return False, "sans logement"
    p = sim.state["places"].get(agent["home"])
    if p:
        p["tenants"].pop(agent["id"], None)
    agent["home"] = None
    return True, "logement quitté"


def pay_rents(sim):
    st = sim.state
    for p in st["places"].values():
        for tid in list(p["tenants"]):
            a = st["agents"].get(tid)
            if not a:
                p["tenants"].pop(tid, None)
                continue
            rent = int(p["tenants"][tid] * st["flags"].get("rent_mult", 1.0))
            owner = p["owner"] or "city"
            if owner == tid:
                continue
            ok, _ = transfer(sim, tid, owner, rent, "loyer")
            if ok:
                a["arrears"] = 0
                sim.emit("rent", [tid] + ([owner] if owner != "city" else []), f"{a['name']} paie son loyer ({rent})", {"rent": rent}, place=p["id"])
            else:
                a["arrears"] += 1
                emotions.nudge(a, fear=0.1, frustration=0.1)
                add_memory(sim, a, "experience", "Je n'ai pas pu payer mon loyer.", importance=0.8)
                if a["arrears"] >= 3:
                    p["tenants"].pop(tid, None)
                    a["home"] = None
                    sim.emit("eviction", [tid], f"{a['name']} est expulsé de {p['name']}", {}, place=p["id"])
                    add_memory(sim, a, "experience", f"J'ai été expulsé de {p['name']}.", importance=0.95)


# -- lieux ---------------------------------------------------------------------
def list_place(sim, agent, place, price):
    if place["owner"] != agent["id"]:
        return False, "vous ne possédez pas ce lieu"
    try:
        price = int(price)
    except (TypeError, ValueError):
        return False, "prix invalide"
    if price < 1:
        return False, "prix invalide"
    place["for_sale"], place["price"] = True, price
    sim.emit("listing", [agent["id"]], f"{agent['name']} met {place['name']} en vente ({price})", {"place": place["id"], "price": price})
    return True, "mis en vente"


def buy_place(sim, agent, place):
    if not place["for_sale"] or not place["price"]:
        return False, "ce lieu n'est pas à vendre"
    if place["owner"] == agent["id"]:
        return False, "déjà à vous"
    seller = place["owner"] or "city"
    if place["type"] == "terrain":
        return False, "un terrain se développe avec l'action « build »"
    ok, msg = transfer(sim, agent["id"], seller, place["price"], "achat de lieu")
    if not ok:
        return False, msg
    for tid in list(place["tenants"]):
        pass  # les locataires restent, avec le nouveau propriétaire
    place["owner"] = agent["id"]
    place["for_sale"] = False
    sim.emit("transaction", [agent["id"]] + ([seller] if seller != "city" else []),
             f"{agent['name']} achète {place['name']} pour {place['price']}", {"place": place["id"], "price": place["price"]})
    add_memory(sim, agent, "transaction", f"J'ai acheté {place['name']}.", importance=0.9)
    if seller != "city":
        add_memory(sim, sim.state["agents"][seller], "transaction", f"J'ai vendu {place['name']} à {agent['name']}.", importance=0.9, about=agent["id"])
    return True, "acheté"


def set_wage(sim, agent, place, wage):
    if place["owner"] != agent["id"]:
        return False, "vous ne possédez pas ce lieu"
    try:
        wage = int(wage)
    except (TypeError, ValueError):
        return False, "salaire invalide"
    if not 1 <= wage <= 200:
        return False, "salaire hors limites (1-200)"
    if not PLACE_TYPES.get(place["type"], {}).get("wage"):
        return False, "ce lieu n'emploie pas"
    place["wage"] = wage
    return True, "salaire fixé"
