"""Flask API : accès contrôlé à l'état et commandes de l'interface."""
import re
import urllib.parse

from flask import Blueprint, Response, jsonify, request, current_app, abort

from agents import emotions, goals
from agents.agent import find_agent, inventory_items, place_of
from agents.memory import subjective_text
from api.schemas import validate_new_sim
from simulation import actions, events, integrity
from simulation.save_manager import SaveError, export_log, export_table
from simulation.state import fmt_time, ticks_per_day, day_of
from systems import communication, economy, iachat, messaging, relationships

bp = Blueprint("api", __name__, url_prefix="/api")

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def sim():
    return current_app.config["SIM"]


def err(msg, code=400):
    return jsonify({"error": msg}), code


def int_arg(name, default, lo=0, hi=10 ** 9):
    try:
        v = int(request.args.get(name, default))
    except (TypeError, ValueError):
        abort(400, f"paramètre {name} invalide")
    return max(lo, min(hi, v))


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.errorhandler(400)
def _bad(e):
    return err(getattr(e, "description", "requête invalide"), 400)


@bp.errorhandler(404)
def _nf(e):
    return err("introuvable", 404)


@bp.errorhandler(Exception)
def _boom(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return err(e.description, e.code)
    current_app.logger.exception("API")
    return err("erreur interne du serveur", 500)


# -- sécurité : API locale uniquement ---------------------------------------------------
@bp.before_request
def guard():
    cfg = sim().cfg
    if not cfg.allow_remote:
        host = (request.host or "").rsplit(":", 1)[0] if not request.host.startswith("[") else request.host.split("]")[0] + "]"
        if host not in LOCAL_HOSTS:
            abort(403, "accès refusé : l'API n'est accessible qu'en local")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-IACity") != "1":
        abort(403, "en-tête X-IACity manquant")


# -- état léger ----------------------------------------------------------------------------
@bp.get("/state")
def state():
    s = sim()
    with s.lock:
        st = s.state
        agents = []
        for a in st["agents"].values():
            goal = next(iter(goals.active_goals(a)), None)
            agents.append({"id": a["id"], "name": a["name"], "x": a["x"], "y": a["y"], "place": a["place"], "hue": a["hue"],
                           "human": a["is_human"], "activity": a["current_activity"], "money": a["money"],
                           "say": a["last_say"], "mood": emotions.dominant(a, 1)[0],
                           "goal": goal["description"] if goal else None})
        places = [{"id": p["id"], "name": p["name"], "type": p["type"], "rect": p["rect"], "indoor": p["indoor"], "door": p["door"],
                   "owner": p["owner"], "owner_name": "Ville" if p["owner"] == "city" else (st["agents"][p["owner"]]["name"] if p["owner"] in st["agents"] else None),
                   "for_sale": p["for_sale"], "price": p["price"], "built": p["built"], "tenants": len(p["tenants"]), "capacity": p["capacity"],
                   "wage": p["wage"]} for p in st["places"].values() if p["id"] != "p_outdoor"]
        return jsonify({
            "version": s.version, "session_id": st["session_id"], "tick": st["tick"], "time": fmt_time(s, st["tick"]), "day": day_of(s, st["tick"]),
            "paused": s.paused, "speed": s.speed, "llm": s.llm.status(), "llm_pending": len(s.decisions.pending),
            "agents": agents, "places": places, "map_version": st["flags"].get("map_version", 0),
            "effects": [{"key": e["key"], "until": e["until"]} for e in st["effects"]], "human": st["human"],
            "treasury": st["treasury"], "posts": len(st["posts"]), "events": s.log.last_seq(),
            "integrity_errors": len(s.integrity_errors), "map_size": [len(st["map"][0]), len(st["map"])],
            "flags": st["flags"], "open_conversations": len(communication.open_conversations(s)),
        })


@bp.get("/map")
def map_():
    s = sim()
    with s.lock:
        return jsonify({"rows": s.state["map"], "version": s.state["flags"].get("map_version", 0)})


@bp.get("/config")
def config():
    return jsonify({"config": sim().cfg.to_dict(), "scenarios": events.SCENARIOS})


# -- contrôle ------------------------------------------------------------------------------
@bp.post("/sim/new")
def sim_new():
    data, errors = validate_new_sim(body())
    if errors:
        return err("; ".join(errors))
    s = sim()
    s.new_world(data["num_agents"], data["seed"], data["human"] or None)
    if body().get("start", True):
        s.paused = False
    else:
        s.paused = True
    return jsonify({"ok": True, "session_id": s.state["session_id"]})


@bp.post("/sim/pause")
def sim_pause():
    sim().pause()
    return jsonify({"ok": True, "paused": True})


@bp.post("/sim/resume")
def sim_resume():
    sim().resume()
    return jsonify({"ok": True, "paused": False})


@bp.post("/sim/speed")
def sim_speed():
    try:
        v = float(body().get("speed"))
    except (TypeError, ValueError):
        return err("vitesse invalide")
    if not 0.1 <= v <= 60:
        return err("vitesse hors limites (0,1 à 60)")
    sim().set_speed(v)
    return jsonify({"ok": True, "speed": sim().speed})


@bp.post("/sim/step")
def sim_step():
    s = sim()
    if not s.paused:
        return err("le pas à pas n'est possible qu'en pause")
    n = body().get("n", 1)
    if not isinstance(n, int) or not 1 <= n <= 500:
        return err("n doit être entre 1 et 500")
    s.step(n)
    return jsonify({"ok": True, "tick": s.state["tick"]})


@bp.get("/integrity")
def integrity_():
    s = sim()
    with s.lock:
        s.integrity_errors = integrity.check(s.state)
        return jsonify({"ok": not s.integrity_errors, "errors": s.integrity_errors})


@bp.get("/llm")
def llm_status():
    return jsonify(sim().llm.status())


@bp.post("/llm/config")
def llm_config():
    s = sim()
    b = body()
    cfg = s.cfg
    if b.get("mode") in ("auto", "ollama", "demo"):
        cfg.llm_mode = b["mode"]
    if isinstance(b.get("model"), str) and re.fullmatch(r"[\w.\-:/]{1,80}", b["model"]):
        cfg.ollama_model = b["model"]
    if isinstance(b.get("url"), str):
        u = urllib.parse.urlparse(b["url"])
        if u.scheme not in ("http", "https") or (u.hostname not in ("127.0.0.1", "localhost", "::1") and not cfg.allow_remote):
            return err("l'adresse du LLM doit être locale (127.0.0.1 / localhost)")
        cfg.ollama_url = b["url"]
    return jsonify(s.llm.probe())


@bp.post("/llm/probe")
def llm_probe():
    return jsonify(sim().llm.probe())


# -- agents ------------------------------------------------------------------------------------
def get_agent(aid):
    a = sim().state["agents"].get(aid)
    if not a:
        abort(404)
    return a


def names(s):
    return {i: a["name"] for i, a in s.state["agents"].items()}


@bp.get("/agents")
def agents_list():
    s = sim()
    with s.lock:
        return jsonify([{"id": a["id"], "name": a["name"], "human": a["is_human"], "money": a["money"], "activity": a["current_activity"]}
                        for a in s.state["agents"].values()])


@bp.get("/agents/<aid>")
def agent_overview(aid):
    s = sim()
    with s.lock:
        a = get_agent(aid)
        st = s.state
        pl = place_of(s, a)
        return jsonify({
            "id": a["id"], "name": a["name"], "human": a["is_human"], "money": a["money"], "number": a["number"],
            "place": {"id": pl["id"], "name": pl["name"], "type": pl["type"]}, "x": a["x"], "y": a["y"],
            "home": st["places"][a["home"]]["name"] if a["home"] in st["places"] else None,
            "activity": a["current_activity"], "busy_until": a["busy_until"], "tick": st["tick"],
            "needs": a["needs"], "emotions": a["emotions"], "personality": a["personality"], "skills": a["skills"],
            "values": a["values"], "beliefs": a["beliefs"], "reputation": a["reputation"], "profile": a["profile"],
            "inventory": [{"id": i["id"], "name": i["name"], "category": i["category"], "price": i["price"] if i["listed"] else None,
                           "quality": i["quality"], "description": i["description"]} for i in inventory_items(s, a)],
            "contacts": [{"id": cid, **c} for cid, c in a["contacts"].items()],
            "plan": a["plan"], "routines": a["routines"], "stats": a["stats"], "thinking": aid in s.decisions.pending,
            "counts": {"memories": len(a["memory"]), "knowledge": len(a["knowledge"]), "goals": len(a["goals"]), "relationships": len(a["relationships"])},
            "last_say": a["last_say"], "bond_proposals": a["bond_proposals"],
        })


def page_args():
    return int_arg("page", 1, 1, 10 ** 6), int_arg("per_page", 25, 1, 100)


@bp.get("/agents/<aid>/log")
def agent_log(aid):
    """Pensées, historique d'actions et événements d'un agent (paginé par curseur)."""
    s = sim()
    get_agent(aid)
    kind = request.args.get("kind", "all")
    types = {"thoughts": ["thought", "llm_error", "llm_warning"],
             "history": ["action", "action_rejected", "teleport", "say", "transaction", "work", "craft", "build", "post", "reply", "dm", "goal",
                         "relationship", "gift", "contact", "study", "leisure", "gather", "housing", "rent", "bond", "lie", "info"]}.get(kind)
    rows, more = s.log.query(limit=int_arg("limit", 30, 1, 300), actor=aid, types=types, q=request.args.get("q") or None,
                             before=request.args.get("before") or None)
    return jsonify({"rows": rows, "has_more": more, "total": s.log.count(actor=aid, types=types)})


@bp.get("/agents/<aid>/memory")
def agent_memory(aid):
    s = sim()
    with s.lock:
        a = get_agent(aid)
        q = (request.args.get("q") or "").lower()
        kind = request.args.get("kind")
        mem = [m for m in reversed(a["memory"]) if (not kind or m["kind"] == kind) and (not q or q in m["content"].lower())]
        page, per = page_args()
        total = len(mem)
        sl = mem[(page - 1) * per: page * per]
        return jsonify({"rows": [dict(m, recalled=subjective_text(s, m)) for m in sl], "total": total, "page": page, "per_page": per})


@bp.get("/agents/<aid>/knowledge")
def agent_knowledge(aid):
    s = sim()
    with s.lock:
        a = get_agent(aid)
        nm = names(s)
        rows = [dict(k, source_name=nm.get(k["source"], k["source"]), chain_names=[nm.get(c, c) for c in k["chain"]]) for k in reversed(a["knowledge"])]
        page, per = page_args()
        return jsonify({"rows": rows[(page - 1) * per: page * per], "total": len(rows)})


@bp.get("/agents/<aid>/relationships")
def agent_relationships(aid):
    s = sim()
    with s.lock:
        a = get_agent(aid)
        nm = names(s)
        rows = []
        for oid, r in a["relationships"].items():
            if oid in nm:
                rows.append(dict(r, id=oid, name=nm[oid], history=r["history"][-15:], has_number=oid in a["contacts"],
                                 they_have_my_number=aid in s.state["agents"][oid]["contacts"]))
        rows.sort(key=lambda r: -(r["trust"] + r["friendship"] + r["hostility"]))
        return jsonify({"rows": rows, "total": len(rows)})


@bp.get("/agents/<aid>/goals")
def agent_goals(aid):
    with sim().lock:
        a = get_agent(aid)
        return jsonify({"rows": sorted(a["goals"], key=lambda g: (g["status"] != "active", -g["updated"])), "total": len(a["goals"])})


@bp.get("/agents/<aid>/messages")
def agent_messages(aid):
    s = sim()
    with s.lock:
        a = get_agent(aid)
        nm = names(s)
        threads = {}
        for m in messaging.messages_of(s, aid):
            other = m["to"] if m["from"] == aid else m["from"]
            t = threads.setdefault(other, {"with": other, "name": nm.get(other, other), "count": 0, "last": None})
            t["count"] += 1
            t["last"] = m
        other = request.args.get("with")
        msgs = []
        if other:
            msgs = [dict(m, from_name=nm.get(m["from"]), to_name=nm.get(m["to"])) for m in messaging.thread(s, aid, other, 0, 200)]
        return jsonify({"threads": sorted(threads.values(), key=lambda t: -t["last"]["tick"]), "messages": msgs})


@bp.get("/agents/<aid>/conversations")
def agent_conversations(aid):
    s = sim()
    with s.lock:
        get_agent(aid)
        convs = [c for c in s.state["conversations"].values() if aid in c["participants"] or any(aid in t["listeners"] for t in c["turns"])]
        convs.sort(key=lambda c: -c["last_tick"])
        return jsonify({"rows": [conv_view(s, c, aid) for c in convs[:int_arg("limit", 10, 1, 50)]]})


def conv_view(s, c, viewer=None):
    nm = names(s)
    return {"id": c["id"], "state": c["state"], "place": s.state["places"][c["place"]]["name"], "opened": c["opened"], "last_tick": c["last_tick"],
            "participants": [{"id": p, "name": nm.get(p, p)} for p in c["participants"]],
            "turns": [{"seq": t["seq"], "tick": t["tick"], "time": fmt_time(s, t["tick"]), "speaker": nm.get(t["speaker"], t["speaker"]),
                       "text": t["text"], "volume": t["volume"], "overheard": bool(viewer and viewer not in c["participants"] and viewer in t["listeners"])}
                      for t in c["turns"][-60:]], "total_turns": len(c["turns"])}


@bp.get("/conversations")
def conversations():
    s = sim()
    with s.lock:
        convs = list(s.state["conversations"].values())
        if request.args.get("state") in ("open", "closed"):
            convs = [c for c in convs if c["state"] == request.args["state"]]
        convs.sort(key=lambda c: -c["last_tick"])
        page, per = page_args()
        return jsonify({"rows": [conv_view(s, c) for c in convs[(page - 1) * per: page * per]], "total": len(convs)})


# -- journal global ----------------------------------------------------------------------------
@bp.get("/log")
def log_():
    s = sim()
    types = [t for t in (request.args.get("types") or "").split(",") if re.fullmatch(r"[a-z_]{1,30}", t)] or None
    rows, more = s.log.query(limit=int_arg("limit", 50, 1, 500), types=types, actor=request.args.get("actor") or None,
                             q=request.args.get("q") or None, before=request.args.get("before") or None,
                             after=request.args.get("after") or None)
    return jsonify({"rows": rows, "has_more": more, "last_seq": s.log.last_seq()})


# -- IACHAT -------------------------------------------------------------------------------------
def post_view(s, p):
    nm = names(s)
    return {"id": p["id"], "n": p["n"], "author": p["author"], "author_name": p["author_name"], "human": p["human"], "text": p["text"],
            "tick": p["tick"], "time": fmt_time(s, p["tick"]), "reply_to": p["reply_to"],
            "reactions": {k: len(v) for k, v in p["reactions"].items()},
            "reactors": {k: [nm.get(x, x) for x in v] for k, v in p["reactions"].items()},
            "replies": sum(1 for q in s.state["posts"].values() if q["reply_to"] == p["id"])}


@bp.get("/iachat/feed")
def iachat_feed():
    s = sim()
    with s.lock:
        posts, more = iachat.feed(s, before=request.args.get("before") or None, limit=int_arg("limit", 30, 1, 100),
                                  author=request.args.get("author") or None, include_replies=request.args.get("replies") != "0")
        return jsonify({"rows": [post_view(s, p) for p in posts], "has_more": more, "total": len(s.state["posts"])})


@bp.get("/iachat/post/<pid>")
def iachat_post(pid):
    s = sim()
    with s.lock:
        p = s.state["posts"].get(pid)
        if not p:
            abort(404)
        return jsonify({"post": post_view(s, p), "replies": [post_view(s, r) for r in iachat.replies(s, pid)]})


@bp.post("/iachat/post")
def iachat_publish():
    s = sim()
    b = body()
    text = b.get("text")
    if not isinstance(text, str) or not text.strip():
        return err("texte requis")
    with s.lock:
        hid = s.state["human"]
        name = b.get("name") if isinstance(b.get("name"), str) and b["name"].strip() else None
        post, msg = iachat.create_post(s, hid or "human", text, reply_to=b.get("reply_to") if isinstance(b.get("reply_to"), str) else None,
                                       human=True, name=(s.state["agents"][hid]["name"] if hid else (name or "Humain")))
        if not post:
            return err(msg)
        s.version += 1
        return jsonify({"ok": True, "post": post_view(s, post)})


@bp.post("/iachat/react")
def iachat_react():
    s = sim()
    b = body()
    with s.lock:
        hid = s.state["human"]
        if not hid:
            return err("créez d'abord votre personnage pour réagir")
        ok, msg = iachat.react(s, s.state["agents"][hid], b.get("post_id"), b.get("kind", "like"))
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


# -- événements -----------------------------------------------------------------------------------
@bp.post("/events/trigger")
def events_trigger():
    s = sim()
    b = body()
    params = b.get("params") if isinstance(b.get("params"), dict) else {}
    with s.lock:
        ok, desc = events.trigger(s, b.get("key"), params)
        s.version += 1
    return (jsonify({"ok": True, "description": desc}) if ok else err(desc))


# -- personnage humain -----------------------------------------------------------------------------
@bp.post("/human/spawn")
def human_spawn():
    name = body().get("name")
    if not isinstance(name, str) or not name.strip():
        return err("nom requis")
    a = sim().spawn_human(name)
    return jsonify({"ok": True, "id": a["id"], "name": a["name"]})


@bp.get("/human")
def human_view():
    """Ce que perçoit le personnage : uniquement ce qu'il a vu/entendu dans le monde."""
    s = sim()
    with s.lock:
        hid = s.state["human"]
        if not hid:
            return jsonify({"spawned": False})
        a = s.state["agents"][hid]
        nm = names(s)
        pl = place_of(s, a)
        around = communication.people_around(s, a)
        heard = [dict(m, recalled=m["content"]) for m in reversed(a["memory"]) if m["kind"] in ("conversation", "overheard", "info", "experience", "message")][:40]
        msgs = [dict(m, from_name=nm.get(m["from"]), to_name=nm.get(m["to"])) for m in messaging.messages_of(s, hid)][-40:]
        return jsonify({
            "spawned": True, "id": hid, "name": a["name"], "money": a["money"], "number": a["number"],
            "place": {"id": pl["id"], "name": pl["name"], "type": pl["type"]},
            "people": [{"id": o["id"], "name": o["name"], "known": relationships.rel(a, o["id"])["met_tick"] is not None, "doing": o["current_activity"],
                        "audible": communication.audibility(s, a, o, "normal")} for o in around],
            "memory": heard, "messages": msgs, "contacts": [{"id": cid, **c} for cid, c in a["contacts"].items()],
            "inventory": [{"id": i["id"], "name": i["name"], "price": i["price"] if i["listed"] else None} for i in inventory_items(s, a)],
            "market": [{"item_id": it["id"], "name": it["name"], "price": price, "seller": "Ville" if sl == "city" else nm.get(sl)}
                       for it, sl, price in economy.stock_here(s, pl)],
            "places": [{"id": p["id"], "name": p["name"], "type": p["type"]} for p in s.state["places"].values() if p["id"] != "p_outdoor"],
        })


@bp.post("/human/action")
def human_action():
    s = sim()
    with s.lock:
        hid = s.state["human"]
        if not hid:
            return err("créez d'abord votre personnage")
        a = s.state["agents"][hid]
        act = body()
        if act.get("type") in ("set_goal", "drop_goal", "wait"):
            return err("action non disponible pour le personnage humain")
        ok, msg = actions.execute(s, a, act, origin="human")
        a["plan"] = []
        s.version += 1
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


# -- sauvegardes / export -----------------------------------------------------------------------------
@bp.get("/saves")
def saves_list():
    return jsonify(sim().saves.list())


@bp.post("/saves")
def saves_create():
    name = body().get("name")
    return jsonify(sim().saves.save(name[:60] if isinstance(name, str) else ""))


@bp.post("/saves/<sid>/restore")
def saves_restore(sid):
    try:
        return jsonify(sim().saves.restore(sid))
    except SaveError as e:
        return err(str(e))


@bp.get("/saves/<sid>/download")
def saves_download(sid):
    try:
        data = sim().saves.raw(sid)
    except (SaveError, OSError):
        return err("sauvegarde introuvable", 404)
    return Response(data, mimetype="application/json", headers={"Content-Disposition": f"attachment; filename=iacity-{sid}.json"})


@bp.post("/saves/import")
def saves_import():
    f = request.files.get("file")
    raw = f.read() if f else request.get_data()
    try:
        return jsonify(sim().saves.import_bytes(raw.decode("utf-8")))
    except (SaveError, UnicodeDecodeError) as e:
        return err(str(e))


@bp.get("/export")
def export_():
    fmt = request.args.get("format", "jsonl")
    if fmt not in ("jsonl", "json", "csv"):
        return err("format inconnu (jsonl, json, csv)")
    tf = request.args.get("tick_from")
    tt = request.args.get("tick_to")
    types = [t for t in (request.args.get("types") or "").split(",") if re.fullmatch(r"[a-z_]{1,30}", t)] or None
    try:
        tf = int(tf) if tf not in (None, "") else None
        tt = int(tt) if tt not in (None, "") else None
    except ValueError:
        return err("intervalle invalide")
    mime = {"jsonl": "application/x-ndjson", "json": "application/json", "csv": "text/csv"}[fmt]
    return Response(export_log(sim(), fmt, tf, tt, types), mimetype=mime,
                    headers={"Content-Disposition": f"attachment; filename=iacity-journal.{fmt}"})


@bp.get("/export/table/<name>")
def export_tbl(name):
    s = sim()
    with s.lock:
        try:
            data = export_table(s, name)
        except ValueError:
            return err("table inconnue (agents, transactions, posts, messages, items)", 404)
    return Response(data, mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=iacity-{name}.csv"})
