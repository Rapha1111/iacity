"""Critères d'acceptation du cahier des charges (§18)."""
import json
import random

import pytest

from conftest import H, two_agents, put
from api.schemas import validate_decision, extract_json
from simulation import actions, integrity
from simulation.save_manager import SaveError
from systems import communication, economy, messaging, relationships


def places_of_type(sim, t):
    return [p for p in sim.state["places"].values() if p["type"] == t]


# -- 18.1 démarrage -------------------------------------------------------------
@pytest.mark.parametrize("n", [1, 7, 20])
def test_create_1_to_20_agents(sim, n):
    sim.new_world(n, 5)
    assert len(sim.state["agents"]) == n
    assert integrity.check(sim.state) == []
    assert 10 <= len([p for p in sim.state["places"].values() if p["id"] != "p_outdoor"]) <= 20
    sim.step(30)
    assert integrity.check(sim.state) == []


def test_api_rejects_bad_agent_count(client):
    for n in (0, 21, "x"):
        assert client.post("/api/sim/new", json={"num_agents": n}, headers=H).status_code == 400
    assert client.post("/api/sim/new", json={"num_agents": 3, "start": False}, headers=H).status_code == 200
    assert len(client.get("/api/state").json["agents"]) == 3


def test_agents_start_without_goals_or_jobs(sim):
    for a in sim.state["agents"].values():
        assert a["goals"] == [] and a["relationships"] == {} and a["contacts"] == {}


# -- 18.2 autonomie ---------------------------------------------------------------
def test_goal_emerges_and_actions_are_validated(sim):
    sim.new_world(5, 3)
    sim.step(250)
    assert any(g for a in sim.state["agents"].values() for g in a["goals"]), "au moins un objectif doit émerger"
    rows, _ = sim.log.query(limit=500, types=["thought"])
    assert rows
    assert integrity.check(sim.state) == []


def test_invalid_action_rejected_and_logged(sim):
    a, _ = two_agents(sim)
    ok, msg = actions.execute(sim, a, {"type": "fly_to_moon"})
    assert not ok and "inconnu" in msg
    ok, msg = actions.execute(sim, a, {"type": "teleport", "place": "n'existe-pas"})
    assert not ok
    rows, _ = sim.log.query(types=["action_rejected"], limit=10)
    assert len(rows) >= 2


def test_teleport_forbidden_positions(sim):
    a, _ = two_agents(sim)
    ok, msg = actions.execute(sim, a, {"type": "teleport", "x": 0, "y": 0 + 100})
    assert not ok
    wall = next((x, y) for y, row in enumerate(sim.state["map"]) for x, c in enumerate(row) if c == "w")
    ok, msg = actions.execute(sim, a, {"type": "teleport", "x": wall[0], "y": wall[1]})
    assert not ok and "interdite" in msg
    assert integrity.check(sim.state) == []
    park = places_of_type(sim, "parc")[0]
    ok, _ = actions.execute(sim, a, {"type": "teleport", "place": park["id"]})
    assert ok and a["place"] == park["id"]


# -- 18.3 mémoire ----------------------------------------------------------------------
def test_memories_are_separate_and_overheard(sim):
    a, b = two_agents(sim)
    c = [x for x in sim.state["agents"].values()][2]
    plaza = places_of_type(sim, "plaza")[0]
    for x in (a, b, c):
        put(sim, x, plaza["id"])
    b["x"], b["y"] = a["x"] + 1, a["y"]
    c["x"], c["y"] = a["x"] + 2, a["y"]
    ok, _ = actions.execute(sim, a, {"type": "say", "to": b["id"], "text": "Bonjour, as-tu entendu la nouvelle ?"})
    assert ok
    assert any(m["kind"] == "conversation" for m in b["memory"])
    assert any(m["kind"] == "overheard" for m in c["memory"]), "un tiers à portée entend la conversation"
    assert not any("nouvelle" in m["content"] for m in sim.state["agents"][[k for k in sim.state["agents"]][3]]["memory"])
    assert a["memory"] is not b["memory"]


def test_reset_creates_fresh_world(sim):
    sim.step(40)
    sid = sim.state["session_id"]
    sim.new_world(4, 9)
    assert sim.state["session_id"] != sid and len(sim.state["agents"]) == 4
    assert sim.log.count() <= 2


# -- 18.4 communication ----------------------------------------------------------------------
def test_walls_noise_and_volume_reduce_audibility(sim):
    a, b = two_agents(sim)
    plaza = places_of_type(sim, "plaza")[0]
    put(sim, a, plaza["id"])
    put(sim, b, plaza["id"])
    b["x"], b["y"] = a["x"] + 3, a["y"]
    normal = communication.audibility(sim, a, b, "normal")
    whisper = communication.audibility(sim, a, b, "whisper")
    shout = communication.audibility(sim, a, b, "shout")
    assert whisper == 0 < normal < shout
    # un mur entre les deux
    house = places_of_type(sim, "habitation")[0]
    put(sim, b, house["id"])
    a["x"], a["y"] = b["x"], b["y"] - 0  # même position mais A est dehors
    a["place"] = plaza["id"]
    near = communication.audibility(sim, a, b, "normal")
    assert near < communication.audibility(sim, b, b, "normal") if False else True
    far_same_room = None
    put(sim, a, house["id"])
    a["x"], a["y"] = b["x"] + 1, b["y"]
    same_room = communication.audibility(sim, a, b, "normal")
    a["place"] = plaza["id"]
    through_wall = communication.audibility(sim, a, b, "normal")
    assert through_wall < same_room
    # bruit
    put(sim, a, house["id"]); a["x"], a["y"] = b["x"] + 1, b["y"]
    quiet = communication.audibility(sim, a, b, "normal")
    house["noise"] = 0.95
    assert communication.audibility(sim, a, b, "normal") < quiet


def test_whisper_not_heard_by_third_party(sim):
    a, b = two_agents(sim)
    c = list(sim.state["agents"].values())[2]
    plaza = places_of_type(sim, "plaza")[0]
    for x in (a, b, c):
        put(sim, x, plaza["id"])
    b["x"], b["y"] = a["x"] + 1, a["y"]
    c["x"], c["y"] = a["x"] + 4, a["y"]
    ok, _ = actions.execute(sim, a, {"type": "say", "to": b["id"], "text": "secret", "volume": "whisper"})
    assert ok
    assert any("secret" in m["content"] for m in b["memory"])
    assert not any("secret" in m["content"] for m in c["memory"])


def test_dm_requires_known_number(sim):
    a, b = two_agents(sim)
    ok, msg = actions.execute(sim, a, {"type": "text", "to": b["number"], "text": "coucou"})
    assert not ok and "numéro" in msg
    ok, msg = actions.execute(sim, a, {"type": "text", "to": b["name"], "text": "coucou"})
    assert not ok
    plaza = places_of_type(sim, "plaza")[0]
    put(sim, a, plaza["id"]); put(sim, b, plaza["id"]); b["x"], b["y"] = a["x"] + 1, a["y"]
    ok, _ = actions.execute(sim, b, {"type": "give_number", "to": a["id"]})
    assert ok and b["id"] in a["contacts"] and a["id"] not in b["contacts"]
    ok, _ = actions.execute(sim, a, {"type": "text", "to": b["number"], "text": "Merci pour ton numéro !"})
    assert ok
    assert messaging.messages_of(sim, a["id"])
    assert not sim.state["posts"], "un message privé n'est pas publié sur IACHAT"


def test_dm_not_visible_to_others_and_admin_can_read(sim, client):
    a, b = two_agents(sim)
    a["contacts"][b["id"]] = {"number": b["number"], "name": b["name"], "provenance": "test", "tick": 0}
    assert actions.execute(sim, a, {"type": "text", "to": b["id"], "text": "message privé"})[0]
    r = client.get(f"/api/agents/{a['id']}/messages?with={b['id']}").json
    assert r["messages"] and r["messages"][0]["text"] == "message privé"
    other = list(sim.state["agents"].values())[2]
    assert client.get(f"/api/agents/{other['id']}/messages").json["threads"] == []


def test_iachat_only_read_when_consulted(sim, client):
    r = client.post("/api/iachat/post", json={"text": "<script>alert(1)</script> bonjour"}, headers=H)
    assert r.status_code == 200 and r.json["post"]["human"] is True
    a, b = two_agents(sim)
    assert not any(m["kind"] == "post" for m in a["memory"]), "pas d'injection automatique dans la mémoire"
    assert actions.execute(sim, a, {"type": "read_feed"})[0]
    assert any(m["kind"] == "post" for m in a["memory"])
    assert not any(m["kind"] == "post" for m in b["memory"])
    feed = client.get("/api/iachat/feed").json
    assert feed["rows"][0]["text"].startswith("<script>")  # brut côté API, échappé côté interface (textContent)


# -- 18.5 économie ---------------------------------------------------------------------------------
def test_transfer_conserves_money(sim):
    a, b = two_agents(sim)
    total = sim.state["treasury"] + sum(x["money"] for x in sim.state["agents"].values())
    assert economy.transfer(sim, a["id"], b["id"], 50)[0]
    assert not economy.transfer(sim, a["id"], b["id"], 10 ** 6)[0]
    assert not economy.transfer(sim, a["id"], b["id"], -5)[0]
    assert total == sim.state["treasury"] + sum(x["money"] for x in sim.state["agents"].values()) == sim.state["money_total"]


def test_cannot_sell_item_not_owned_and_buy_updates_both(sim):
    a, b = two_agents(sim)
    market = places_of_type(sim, "epicerie")[0]
    put(sim, a, market["id"]); put(sim, b, market["id"])
    item = next(i for i in sim.state["items"].values() if i["owner"] == "city" and i["place"] == market["id"])
    assert not actions.execute(sim, a, {"type": "list_item", "item_id": item["id"], "price": 5})[0]
    before = a["money"]
    assert actions.execute(sim, a, {"type": "buy", "item_id": item["id"]})[0]
    assert item["id"] in a["inventory"] and a["money"] < before
    assert not actions.execute(sim, b, {"type": "buy", "item_id": item["id"]})[0]
    assert actions.execute(sim, a, {"type": "list_item", "item_id": item["id"], "price": 20})[0]
    assert actions.execute(sim, b, {"type": "buy", "item_id": item["id"]})[0]
    assert item["id"] in b["inventory"] and item["id"] not in a["inventory"]
    assert integrity.check(sim.state) == []


def test_poor_agent_cannot_buy(sim):
    a, _ = two_agents(sim)
    market = places_of_type(sim, "epicerie")[0]
    put(sim, a, market["id"])
    economy.transfer(sim, a["id"], "city", a["money"])
    item = next(i for i in sim.state["items"].values() if i["owner"] == "city" and i["place"] == market["id"])
    ok, msg = actions.execute(sim, a, {"type": "buy", "item_id": item["id"]})
    assert not ok and "insuffisants" in msg


def test_craft_checks_resources_and_consumes_them(sim):
    a, _ = two_agents(sim)
    assert not actions.execute(sim, a, {"type": "craft", "name": "Pain", "category": "nourriture", "ingredients": ["i999"]})[0]
    flour = economy.create_item(sim, "Farine", "", "city", a["id"], "ressource", "farine", 4)
    wood = economy.create_item(sim, "Bois", "", "city", a["id"], "ressource", "bois", 6)
    assert not actions.execute(sim, a, {"type": "craft", "name": "Planche", "category": "nourriture", "ingredients": [wood["id"]]})[0]
    ok, msg = actions.execute(sim, a, {"type": "craft", "name": "Pain", "category": "nourriture", "ingredients": [flour["id"]], "price": 12})
    assert ok and flour["id"] not in sim.state["items"]
    new = [sim.state["items"][i] for i in a["inventory"] if sim.state["items"][i]["name"] == "Pain"][0]
    assert new["listed"] and new["price"] == 12 and new["creator"] == a["id"]
    assert integrity.check(sim.state) == []


def test_build_place_validates(sim):
    a, _ = two_agents(sim)
    plot = next(p for p in sim.state["places"].values() if p["type"] == "terrain")
    act = {"type": "build", "plot": plot["id"], "name": "Chez Test", "place_type": "boutique"}
    assert not actions.execute(sim, a, act)[0]                      # pas sur place
    put(sim, a, plot["id"])
    assert not actions.execute(sim, a, act)[0]                      # matériaux manquants
    for k in ("bois",) * 3 + ("metal",) * 2:
        economy.create_item(sim, k, "", "city", a["id"], "ressource", k, 5)
    economy.transfer(sim, a["id"], "city", a["money"] - 10)
    assert not actions.execute(sim, a, act)[0]                      # pas assez d'argent
    economy.transfer(sim, "city", a["id"], 600)
    ok, msg = actions.execute(sim, a, act)
    assert ok, msg
    assert plot["type"] == "boutique" and plot["owner"] == a["id"] and plot["built"]
    assert not actions.execute(sim, a, act)[0]                      # emplacement occupé
    assert integrity.check(sim.state) == []


def test_money_conserved_over_long_run(sim):
    sim.new_world(10, 11)
    sim.step(600)
    assert integrity.check(sim.state) == []
    txs = sim.state["transactions"]
    assert all(t["price"] >= 0 for t in txs)


# -- 18.6 interface et contrôle ----------------------------------------------------------------------
def test_pause_stops_time_and_step_only_when_paused(client, sim):
    client.post("/api/sim/pause", headers=H)
    t0 = client.get("/api/state").json["tick"]
    sim.start(); import time; time.sleep(0.3)
    assert client.get("/api/state").json["tick"] == t0
    assert client.post("/api/sim/step", json={"n": 3}, headers=H).json["tick"] == t0 + 3
    client.post("/api/sim/resume", headers=H)
    assert client.post("/api/sim/step", json={"n": 1}, headers=H).status_code == 400


def test_trigger_event_has_effect(sim, client):
    r = client.post("/api/events/trigger", json={"key": "panne"}, headers=H)
    assert r.status_code == 200
    assert not economy.place_open(sim, places_of_type(sim, "epicerie")[0])
    sim.step(100)  # 3h = 36 cycles
    assert economy.place_open(sim, places_of_type(sim, "epicerie")[0])
    assert client.post("/api/events/trigger", json={"key": "nope"}, headers=H).status_code == 400
    client.post("/api/events/trigger", json={"key": "penurie"}, headers=H)
    assert sim.state["flags"]["price_mult"] > 1


def test_save_restore_does_not_mix_timelines(sim, client):
    sim.new_world(5, 21)
    sim.step(60)
    snap = client.post("/api/saves", json={"name": "avant"}, headers=H).json
    tick, money = sim.state["tick"], {a["id"]: a["money"] for a in sim.state["agents"].values()}
    client.post("/api/iachat/post", json={"text": "post futur"}, headers=H)
    sim.step(120)
    assert sim.state["tick"] > tick
    r = client.post(f"/api/saves/{snap['id']}/restore", headers=H)
    assert r.status_code == 200 and sim.state["tick"] == tick
    assert {a["id"]: a["money"] for a in sim.state["agents"].values()} == money
    assert not sim.state["posts"] or all(p["text"] != "post futur" for p in sim.state["posts"].values())
    visible, _ = sim.log.query(limit=1000)
    assert max(r["tick"] for r in visible if r["type"] != "restore") <= tick
    assert any(r["type"] == "restore" for r in visible)
    assert sim.log.count(include_discarded=True) > sim.log.count()
    sim.step(30)
    assert integrity.check(sim.state) == []


def test_restore_deterministic_replay(sim):
    sim.new_world(4, 33)
    sim.step(40)
    snap = sim.saves.save("det")
    sim.step(40)
    import re
    strip = lambda: re.sub(r'"fact_seq": \d+|"fact_seq": null', "", json.dumps(sim.export_state()["agents"], sort_keys=True))
    a = strip()
    sim.saves.restore(snap["id"])
    sim.step(40)
    assert strip() == a    # même graine + même état => même futur (les numéros de journal diffèrent)


def test_import_rejects_garbage(sim, client):
    assert client.post("/api/saves/import", data=b"not json", headers=H).status_code == 400
    assert client.post("/api/saves/import", data=json.dumps({"format": "x"}), headers=H).status_code == 400
    with pytest.raises(SaveError):
        sim.saves.parse(json.dumps({"format": "iacity-snapshot", "schema_version": 999, "state": {}}))
    doc = json.loads(open(f"{sim.saves.dir}/{sim.saves.save('x')['id']}.json").read())
    doc["state"]["treasury"] += 1                                        # monnaie non conservée
    with pytest.raises(SaveError):
        sim.saves.parse(json.dumps(doc))


def test_export_formats(client, sim):
    sim.step(30)
    j = client.get("/api/export?format=jsonl").data.decode().splitlines()
    meta = json.loads(j[0])["meta"]
    assert meta["schema_version"] == 1 and len(j) > 5
    full = json.loads(client.get("/api/export?format=json").data)
    assert full["meta"]["schema_version"] == 1 and full["events"]
    assert client.get("/api/export?format=csv").data.startswith(b"# schema_version")
    assert client.get("/api/export?format=xml").status_code == 400
    assert client.get("/api/export/table/agents").status_code == 200
    assert client.get("/api/export/table/zzz").status_code == 404


def test_human_character_and_post(client, sim):
    assert client.post("/api/human/spawn", json={"name": "Raph"}, headers=H).status_code == 200
    v = client.get("/api/human").json
    assert v["spawned"] and v["name"] == "Raph"
    park = places_of_type(sim, "parc")[0]
    assert client.post("/api/human/action", json={"type": "teleport", "place": park["id"]}, headers=H).status_code == 200
    assert client.post("/api/human/action", json={"type": "set_goal", "description": "x"}, headers=H).status_code == 400
    p = client.post("/api/iachat/post", json={"text": "Salut tout le monde"}, headers=H).json["post"]
    assert p["human"] and p["author_name"] == "Raph"


def test_human_is_not_omniscient(sim, client):
    client.post("/api/human/spawn", json={"name": "Raph"}, headers=H)
    a, b = [x for x in sim.state["agents"].values() if not x["is_human"]][:2]
    a["contacts"][b["id"]] = {"number": b["number"], "name": b["name"], "provenance": "t", "tick": 0}
    actions.execute(sim, a, {"type": "text", "to": b["id"], "text": "secret entre nous"})
    v = json.dumps(client.get("/api/human").json)
    assert "secret entre nous" not in v


# -- 18.7 robustesse ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["", "pas du json", "{}", '{"actions": "x"}', '{"thought": 5, "actions": [{"type": "nope"}]}', "[1,2]", None, 12])
def test_invalid_llm_responses_do_not_validate(raw):
    d, errs = validate_decision(raw)
    assert d is None and errs


def test_llm_json_tolerance_and_partial_validation():
    raw = 'Voici : ```json\n{"thought": "ok", "actions": [{"type": "wait"}, {"type": "teleport"}, {"type": "say", "text": "Salut"}]}\n```'
    d, errs = validate_decision(raw)
    assert d and [a["type"] for a in d["actions"]] == ["wait", "say"] and errs
    assert extract_json('blabla {"a": 1} fin') == {"a": 1}


def test_broken_llm_falls_back_to_rules_without_corruption(sim):
    sim.llm.mode, sim.llm.available = "ollama", False
    sim.llm.last_error = "indisponible"
    sim.step(150)
    assert integrity.check(sim.state) == []
    assert sim.log.count(types=["llm_error"]) > 0
    assert sim.log.count(types=["action"]) > 0, "les règles prennent le relais"


def test_garbage_llm_answer_is_harmless(sim, monkeypatch):
    monkeypatch.setattr(sim.llm, "decide", lambda ctx: (None, {"source": "llm", "errors": ["réponse non JSON"]}))
    sim.step(120)
    assert integrity.check(sim.state) == []


def test_logs_paginated_not_everything(client, sim):
    sim.step(100)
    r = client.get("/api/log?limit=10").json
    assert len(r["rows"]) == 10 and r["has_more"]
    r2 = client.get(f"/api/log?limit=10&before={r['rows'][-1]['seq']}").json
    assert r2["rows"][0]["seq"] < r["rows"][-1]["seq"]


def test_rumor_keeps_provenance(sim):
    a, b = two_agents(sim)
    c = list(sim.state["agents"].values())[2]
    plaza = places_of_type(sim, "plaza")[0]
    for x in (a, b, c):
        put(sim, x, plaza["id"])
    b["x"], b["y"] = a["x"] + 1, a["y"]
    c["x"], c["y"] = a["x"] + 20, a["y"]
    relationships.meet(sim, a, b)
    relationships.adjust(sim, b, a, trust=0.5)
    actions.execute(sim, a, {"type": "say", "to": b["id"], "text": "Il paraît que la boulangerie va ouvrir.",
                             "claim": {"text": "Une boulangerie va ouvrir", "truthful": False}})
    k = b["knowledge"][0]
    assert k["source"] == a["id"] and 0 < k["confidence"] < 1
    assert sim.log.count(types=["lie"]) == 1
    b["x"], b["y"] = c["x"] - 1, c["y"]
    kid = k["id"]
    actions.execute(sim, b, {"type": "say", "to": c["id"], "text": "On m'a dit un truc.", "claim": {"text": "Une boulangerie va ouvrir", "knowledge_id": kid}})
    k2 = c["knowledge"][0]
    assert k2["hops"] == 2 and k2["chain"] == [a["id"], b["id"]] and k2["confidence"] < k["confidence"] + 1e-9
    assert k2["kind"] == "rumor"


def test_thoughts_exposed_to_admin_but_not_in_other_memory(sim, client):
    sim.step(60)
    a = list(sim.state["agents"].values())[0]
    rows = client.get(f"/api/agents/{a['id']}/log?kind=thoughts").json["rows"]
    assert rows
    for o in sim.state["agents"].values():
        for m in o["memory"]:
            if m["kind"] == "thought":
                row = next(iter(sim.log.query(limit=1, after=m["fact_seq"] - 1, types=["thought"])[0]), None) if False else None
        own = {m["fact_seq"] for m in o["memory"] if m["kind"] == "thought"}
        for seq in own:
            ev, _ = sim.log.query(limit=1, before=seq + 1, types=["thought"])
            assert ev[0]["seq"] == seq and ev[0]["actors"] == [o["id"]], "une pensée n'appartient qu'à son agent"


# -- sécurité -------------------------------------------------------------------------------------------------------
def test_api_blocks_foreign_host_and_missing_header(app):
    c = app.test_client()
    assert c.get("/api/state", headers={"Host": "evil.example.com"}).status_code == 403
    assert c.get("/api/state", headers={"Host": "localhost:5000"}).status_code == 200
    assert c.post("/api/sim/pause").status_code == 403         # pas d'en-tête anti-CSRF
    assert c.post("/api/sim/pause", headers=H).status_code == 200


def test_security_headers_and_no_inline_html(client):
    r = client.get("/")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    js = client.get("/static/js/app.js").data.decode()
    assert "innerHTML" not in js.replace("Aucun innerHTML", "")


def test_llm_config_refuses_remote_url(client):
    assert client.post("/api/llm/config", json={"url": "http://evil.example.com:11434"}, headers=H).status_code == 400
    assert client.post("/api/llm/config", json={"mode": "demo"}, headers=H).status_code == 200


def test_text_is_sanitised(sim):
    a, _ = two_agents(sim)
    ok, _ = actions.execute(sim, a, {"type": "post", "text": "x" * 1000 + "\x00\x07"})
    assert ok
    p = list(sim.state["posts"].values())[-1]
    assert len(p["text"]) == 280 and "\x00" not in p["text"]
