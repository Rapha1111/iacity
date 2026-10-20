"""Exécuteur d'actions : le moteur est l'autorité finale.

Chaque action proposée (par le LLM, les règles ou l'humain) est validée puis
appliquée via les systèmes. Les refus sont journalisés avec leur raison (§16).
"""
from agents import emotions, goals
from agents.agent import find_agent, find_place, place_of
from agents.memory import add_memory
from api.schemas import validate_action
from simulation.state import clean_text
from simulation.world import place_at, random_spot, walkable, PLACE_TYPES
from systems import communication, crafting, economy, iachat, messaging, relationships


def execute(sim, agent, action, origin="rules"):
    """Valide et applique une action. Renvoie (ok, message)."""
    act, err = validate_action(action)
    if err:
        return _reject(sim, agent, action, err, origin)
    try:
        ok, msg = HANDLERS[act["type"]](sim, agent, act)
    except Exception as e:   # une action défectueuse ne doit jamais corrompre/arrêter la simulation
        sim.logger.exception("action %s", act)
        ok, msg = False, f"erreur interne : {e}"
    if ok:
        sim.emit("action", [agent["id"]], f"{agent['name']} : {act['type']} → {msg}", {"action": act, "origin": origin, "result": msg}, place=agent["place"])
        _learn(sim, agent, act, origin)
        return True, msg
    return _reject(sim, agent, act, msg, origin)


def _reject(sim, agent, act, why, origin):
    atype = act.get("type") if isinstance(act, dict) else "?"
    sim.emit("action_rejected", [agent["id"]], f"{agent['name']} : {atype} refusé — {why}", {"action": act, "reason": why, "origin": origin}, place=agent["place"])
    agent["failures"].append({"tick": sim.state["tick"], "action": atype, "reason": why})
    del agent["failures"][:-6]
    if origin != "rules" or atype in ("build", "craft", "buy", "text"):
        add_memory(sim, agent, "lesson", f"Mon action « {atype} » a échoué : {why}.", importance=0.4)
    emotions.nudge(agent, frustration=0.04)
    agent["plan"] = []
    agent["needs_review"] = True
    return False, why


def _learn(sim, agent, act, origin):
    """Habitudes : une séquence réussie plusieurs fois peut être rejouée sans LLM."""
    if origin in ("llm", "demo") and act["type"] in ("work", "relax", "study", "gather", "rest", "read_feed"):
        r = agent["routines"].setdefault(act["type"], {"count": 0, "tick": 0})
        r["count"] += 1
        r["tick"] = sim.state["tick"]


# -- gestionnaires ---------------------------------------------------------
def h_teleport(sim, a, act):
    st = sim.state
    if "place" in act:
        p = find_place(sim, act["place"])
        if not p:
            return False, f"lieu inconnu : {act['place']}"
        if p["id"] == "p_outdoor":
            return False, "choisissez un lieu précis"
        if p["type"] == "terrain" and False:
            return False, "terrain"
        if p["indoor"] and not economy.place_open(sim, p) and a["place"] != p["id"]:
            return False, f"{p['name']} est fermé (panne)"
        if a["place"] == p["id"]:
            return False, "vous y êtes déjà"
        spot = random_spot(sim, p)
        if not spot:
            return False, "aucune position valide dans ce lieu"
        x, y = spot
    elif "x" in act and "y" in act:
        x, y = act["x"], act["y"]
        if not walkable(st, x, y):
            return False, f"position ({x},{y}) interdite (mur, obstacle ou hors carte)"
        p = place_at(st, x, y)
    else:
        return False, "teleport demande un lieu ou x,y"
    return arrive(sim, a, p, x, y)


def arrive(sim, a, p, x, y):
    old = sim.state["places"].get(a["place"])
    communication.leave_conversations(sim, a, "s'est éloigné")
    a["x"], a["y"], a["place"] = x, y, p["id"]
    a["busy_until"] = max(a["busy_until"], sim.state["tick"] + 1)
    a["current_activity"] = f"arrive à {p['name']}"
    a["known_places"][p["id"]] = sim.state["tick"]
    sim.emit("teleport", [a["id"]], f"{a['name']} se téléporte : {old['name'] if old else '∅'} → {p['name']}",
             {"from": old["id"] if old else None, "to": p["id"], "x": x, "y": y}, place=p["id"])
    messaging.learn_public_numbers(sim, a)
    a["inbox"].append({"kind": "arrival", "place": p["id"], "tick": sim.state["tick"]})
    for o in communication.people_around(sim, a):    # perception locale à l'arrivée
        if relationships.rel(a, o["id"])["met_tick"] is None and communication.audibility(sim, a, o, "normal") > 0.4:
            relationships.meet(sim, a, o, f"croisés à {p['name']}")
    return True, f"arrivé à {p['name']}"


def h_say(sim, a, act):
    target = None
    if act.get("to"):
        target = find_agent(sim, act["to"])
        if not target:
            return False, f"personne ne s'appelle « {act['to']} »"
    claim = None
    c = act.get("claim")
    if isinstance(c, dict) and isinstance(c.get("text"), str):
        claim = {"text": clean_text(c["text"], 200), "about": c.get("about") if isinstance(c.get("about"), str) else None,
                 "truthful": bool(c.get("truthful", True)), "knowledge_id": c.get("knowledge_id"),
                 "rumor": bool(c.get("rumor", False))}
        if not claim["truthful"]:
            sim.emit("lie", [a["id"]], f"{a['name']} ment délibérément : « {claim['text']} »", {"claim": claim["text"]})
    tone = act.get("tone")
    if isinstance(tone, (int, float)):
        tone = max(-1.0, min(1.0, float(tone)))
    ok, msg = communication.speak(sim, a, act["text"], target, act.get("volume", "normal"), claim, tone)
    if ok:
        a["busy_until"] = sim.state["tick"] + 1
        a["current_activity"] = "discute" if target else "parle"
        emotions.satisfy(a, social=5)
        a["skills"]["social"] = round(a["skills"].get("social", 0) + 0.02, 2)
    return ok, msg


def h_leave_conversation(sim, a, act):
    communication.leave_conversations(sim, a)
    return True, "conversation quittée"


def _near(sim, a, ref):
    t = find_agent(sim, ref)
    if not t:
        return None, f"personne ne s'appelle « {ref} »"
    return t, None


def h_give_number(sim, a, act):
    t, e = _near(sim, a, act["to"])
    return (False, e) if e else messaging.give_number(sim, a, t)


def h_share_contact(sim, a, act):
    about, e = _near(sim, a, act["about"])
    if e:
        return False, e
    t, e = _near(sim, a, act["to"])
    return (False, e) if e else messaging.share_contact(sim, a, about, t)


def h_text(sim, a, act):
    ok, msg = messaging.send_dm(sim, a, act["to"], act["text"])
    if ok:
        a["current_activity"] = "écrit un SMS"
        emotions.satisfy(a, social=4)
    return ok, msg


def h_post(sim, a, act):
    post, msg = iachat.create_post(sim, a["id"], act["text"])
    if post:
        a["current_activity"] = "publie sur IACHAT"
        emotions.satisfy(a, social=3, curiosity=1)
        return True, f"publié ({post['id']})"
    return False, msg


def h_reply(sim, a, act):
    post, msg = iachat.create_post(sim, a["id"], act["text"], reply_to=act["post_id"])
    return (True, f"réponse publiée ({post['id']})") if post else (False, msg)


def h_react(sim, a, act):
    return iachat.react(sim, a, act["post_id"], act.get("kind", "like"))


def h_read_feed(sim, a, act):
    posts = iachat.read_feed(sim, a)
    a["last_read"] = [{"id": p["id"], "author_id": p["author"], "author": iachat.author_name(sim, p), "text": p["text"]} for p in posts if p["author"] != "city"][:4]
    a["current_activity"] = "lit IACHAT"
    emotions.satisfy(a, curiosity=8, social=2)
    a["busy_until"] = sim.state["tick"] + 1
    return True, f"{len(posts)} publication(s) lue(s)"


def h_set_profile(sim, a, act):
    if "bio" in act:
        a["profile"]["bio"] = clean_text(act["bio"], 160)
    if "show_number" in act:
        a["profile"]["show_number"] = bool(act["show_number"])
    return True, "profil mis à jour"


def h_work(sim, a, act):
    return economy.work(sim, a)


def h_gather(sim, a, act):
    return economy.gather(sim, a, act.get("kind"))


def h_buy(sim, a, act):
    return economy.buy(sim, a, act["item_id"])


def h_list_item(sim, a, act):
    return economy.list_item(sim, a, act["item_id"], act["price"])


def h_unlist_item(sim, a, act):
    return economy.unlist_item(sim, a, act["item_id"])


def h_give(sim, a, act):
    t, e = _near(sim, a, act["to"])
    return (False, e) if e else economy.give(sim, a, t, act.get("item_id"), act.get("amount"))


def h_craft(sim, a, act):
    price = act.get("price")
    return crafting.craft(sim, a, act["name"], act.get("description", ""), act["category"], [str(i) for i in act["ingredients"]], price)


def h_consume(sim, a, act):
    return economy.consume(sim, a, act["item_id"])


def h_study(sim, a, act):
    return economy.study(sim, a)


def h_relax(sim, a, act):
    return economy.relax(sim, a)


def h_rest(sim, a, act):
    return economy.rest(sim, a)


def h_rent_home(sim, a, act):
    p = find_place(sim, act["place"])
    return (False, "lieu inconnu") if not p else economy.rent_home(sim, a, p)


def h_leave_home(sim, a, act):
    return economy.leave_home(sim, a)


def h_build(sim, a, act):
    plot = find_place(sim, act["plot"])
    if not plot:
        return False, "terrain inconnu"
    return crafting.build(sim, a, plot, act["name"], act["place_type"], act.get("description", ""))


def h_list_place(sim, a, act):
    p = find_place(sim, act["place"])
    return (False, "lieu inconnu") if not p else economy.list_place(sim, a, p, act["price"])


def h_buy_place(sim, a, act):
    p = find_place(sim, act["place"])
    return (False, "lieu inconnu") if not p else economy.buy_place(sim, a, p)


def h_set_wage(sim, a, act):
    p = find_place(sim, act["place"])
    return (False, "lieu inconnu") if not p else economy.set_wage(sim, a, p, act["wage"])


def h_propose_bond(sim, a, act):
    t, e = _near(sim, a, act["to"])
    if e:
        return False, e
    if communication.audibility(sim, a, t, "normal") <= 0:
        return False, "interlocuteur hors de portée"
    return relationships.propose_bond(sim, a, t, act["bond"])


def h_answer_bond(sim, a, act):
    t = find_agent(sim, act["from"])
    return (False, "agent inconnu") if not t else relationships.answer_bond(sim, a, t["id"], act["accept"])


def h_set_goal(sim, a, act):
    kind = act.get("kind", "other")
    g = goals.add_goal(sim, a, clean_text(act["description"], 200), kind, act.get("params") or {}, act.get("priority", 0.5), origin="reflexion")
    sim.emit("goal", [a["id"]], f"{a['name']} se fixe un objectif : {g['description']}", {"goal": g["id"], "kind": g["kind"]})
    add_memory(sim, a, "experience", f"Nouvel objectif : {g['description']}", importance=0.7)
    return True, f"objectif {g['id']}"


def h_drop_goal(sim, a, act):
    g = goals.set_status(sim, a, act["goal_id"], "abandoned")
    if not g:
        return False, "objectif introuvable"
    sim.emit("goal", [a["id"]], f"{a['name']} abandonne : {g['description']}", {"goal": g["id"], "status": "abandoned"})
    return True, "objectif abandonné"


def h_wait(sim, a, act):
    a["current_activity"] = "observe"
    a["busy_until"] = sim.state["tick"] + 1
    return True, "attend"


HANDLERS = {k[2:]: v for k, v in globals().items() if k.startswith("h_")}
missing = set(__import__("api.schemas", fromlist=["ACTION_SPECS"]).ACTION_SPECS) - set(HANDLERS)
assert not missing, missing
