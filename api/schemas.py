"""Validation des entrées : décisions du LLM, actions, requêtes de l'API.

Toute réponse du LLM est analysée et validée ici avant d'être confiée au moteur.
"""
import json
import re

MAX_ACTIONS = 3
S, I, N, B, L, D = "str", "int", "num", "bool", "list", "dict"

# type d'action -> {argument: (type, requis)}
ACTION_SPECS = {
    "teleport": {"place": (S, False), "x": (I, False), "y": (I, False)},
    "say": {"text": (S, True), "to": (S, False), "volume": (S, False), "tone": (N, False), "claim": (D, False)},
    "leave_conversation": {},
    "give_number": {"to": (S, True)},
    "share_contact": {"about": (S, True), "to": (S, True)},
    "text": {"to": (S, True), "text": (S, True)},
    "post": {"text": (S, True)},
    "reply": {"post_id": (S, True), "text": (S, True)},
    "react": {"post_id": (S, True), "kind": (S, False)},
    "read_feed": {},
    "set_profile": {"bio": (S, False), "show_number": (B, False)},
    "work": {},
    "gather": {"kind": (S, False)},
    "buy": {"item_id": (S, True)},
    "list_item": {"item_id": (S, True), "price": (I, True)},
    "unlist_item": {"item_id": (S, True)},
    "give": {"to": (S, True), "item_id": (S, False), "amount": (I, False)},
    "craft": {"name": (S, True), "description": (S, False), "category": (S, True), "ingredients": (L, True), "price": (I, False)},
    "consume": {"item_id": (S, True)},
    "study": {},
    "relax": {},
    "rest": {},
    "rent_home": {"place": (S, True)},
    "leave_home": {},
    "build": {"plot": (S, True), "name": (S, True), "place_type": (S, True), "description": (S, False)},
    "list_place": {"place": (S, True), "price": (I, True)},
    "buy_place": {"place": (S, True)},
    "set_wage": {"place": (S, True), "wage": (I, True)},
    "propose_bond": {"to": (S, True), "bond": (S, True)},
    "answer_bond": {"from": (S, True), "accept": (B, True)},
    "set_goal": {"description": (S, True), "kind": (S, False), "params": (D, False), "priority": (N, False)},
    "drop_goal": {"goal_id": (S, True)},
    "wait": {},
}

ACTION_HELP = {
    "teleport": "teleport {place: id ou nom du lieu} (ou x,y) — se déplacer instantanément",
    "say": "say {text, to?: nom/id, volume?: whisper|normal|shout, claim?: {text, about?, truthful?}} — parler (portée limitée)",
    "give_number": "give_number {to} — donner son numéro de téléphone à quelqu'un à portée",
    "share_contact": "share_contact {about, to} — transmettre le numéro d'un contact à quelqu'un à portée",
    "text": "text {to: nom/numéro d'un contact connu, text} — SMS (numéro connu obligatoire)",
    "post": "post {text} — publier sur IACHAT", "reply": "reply {post_id, text}", "react": "react {post_id, kind: like|love|laugh|angry|sad}",
    "read_feed": "read_feed {} — lire les nouveautés d'IACHAT",
    "work": "work {} — travailler dans le lieu actuel contre salaire", "gather": "gather {kind?} — ramasser (parc)",
    "buy": "buy {item_id} — acheter un objet en vente dans le lieu", "list_item": "list_item {item_id, price} — mettre en vente",
    "give": "give {to, item_id? | amount?} — offrir", "craft": "craft {name, description, category: nourriture|loisir|objet|outil|autre, ingredients: [ids d'objets possédés], price?}",
    "consume": "consume {item_id}", "study": "study {} — à l'école", "relax": "relax {} — loisirs (parc, bar, restaurant, place…)",
    "rest": "rest {} — chez soi", "rent_home": "rent_home {place}", "build": "build {plot, name, place_type: boutique|restaurant|bar|bureau|atelier|habitation|loisirs|epicerie, description} — construire sur un terrain libre (argent + 3 bois + 2 métal)",
    "list_place": "list_place {place, price}", "buy_place": "buy_place {place}", "set_wage": "set_wage {place, wage}",
    "propose_bond": "propose_bond {to, bond: ami|famille|couple|collegue|allie|rival|partenaire}", "answer_bond": "answer_bond {from, accept}",
    "set_goal": "set_goal {description, kind: earn_money|obtain_item|meet|create_place|improve_relation|learn_skill|other, params?, priority?}",
    "drop_goal": "drop_goal {goal_id}", "wait": "wait {}",
}


def _check(value, typ):
    if typ == S:
        return isinstance(value, (str, int)) and not isinstance(value, bool)
    if typ == I:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        return isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?", value.strip()) is not None
    if typ == N:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if typ == B:
        return isinstance(value, bool)
    if typ == L:
        return isinstance(value, list)
    if typ == D:
        return isinstance(value, dict)
    return False


def _coerce(value, typ):
    if typ == S:
        return str(value)
    if typ == I:
        return int(float(value))
    return value


def validate_action(raw):
    """Renvoie (action_normalisée | None, erreur | None)."""
    if not isinstance(raw, dict):
        return None, "action non-objet"
    atype = raw.get("type") or raw.get("action")
    spec = ACTION_SPECS.get(atype) if isinstance(atype, str) else None
    if spec is None:
        return None, f"type d'action inconnu : {atype!r}"
    out = {"type": atype}
    for name, (typ, required) in spec.items():
        if name not in raw or raw[name] is None:
            if required:
                return None, f"{atype}: argument « {name} » manquant"
            continue
        if not _check(raw[name], typ):
            return None, f"{atype}: argument « {name} » de mauvais type"
        out[name] = _coerce(raw[name], typ)
    if atype == "teleport" and "place" not in out and not ("x" in out and "y" in out):
        return None, "teleport: indiquez « place » ou « x » et « y »"
    return out, None


def extract_json(text):
    """Extrait un objet JSON d'une réponse de modèle (tolère le texte autour / les balises)."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    cands = [m.group(1)] if m else []
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        cands.append(text[start:end + 1])
    for c in cands:
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except ValueError:
            continue
    return None


def validate_decision(raw):
    """Valide une décision brute. Renvoie (decision, erreurs). decision=None si inutilisable."""
    errors = []
    if isinstance(raw, str):
        raw = extract_json(raw)
    if not isinstance(raw, dict):
        return None, ["réponse non JSON"]
    thought = raw.get("thought")
    thought = thought.strip()[:600] if isinstance(thought, str) else ""
    actions = []
    raw_actions = raw.get("actions")
    if isinstance(raw_actions, dict):
        raw_actions = [raw_actions]
    if not isinstance(raw_actions, list):
        raw_actions = []
        errors.append("« actions » absent ou invalide")
    for a in raw_actions[:MAX_ACTIONS]:
        act, err = validate_action(a)
        if err:
            errors.append(err)
        else:
            actions.append(act)
    emo = raw.get("emotions") if isinstance(raw.get("emotions"), dict) else {}
    beliefs = []
    for b in (raw.get("beliefs") or [])[:3] if isinstance(raw.get("beliefs"), list) else []:
        if isinstance(b, dict) and isinstance(b.get("text"), str):
            conf = b.get("confidence", 0.6)
            beliefs.append({"text": b["text"][:200], "confidence": float(conf) if isinstance(conf, (int, float)) else 0.6})
        elif isinstance(b, str):
            beliefs.append({"text": b[:200], "confidence": 0.6})
    values = [v[:120] for v in (raw.get("values") or [])[:2] if isinstance(v, str)] if isinstance(raw.get("values"), list) else []
    if not thought and not actions:
        return None, errors or ["décision vide"]
    return {"thought": thought, "actions": actions, "emotions": emo, "beliefs": beliefs, "values": values}, errors


def validate_new_sim(payload):
    payload = payload or {}
    errors = []
    n = payload.get("num_agents", None)
    if n is not None:
        try:
            n = int(n)
        except (TypeError, ValueError):
            errors.append("num_agents doit être un entier")
            n = None
        else:
            if not 1 <= n <= 20:
                errors.append("num_agents doit être compris entre 1 et 20")
    seed = payload.get("seed", None)
    if seed not in (None, ""):
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            errors.append("seed doit être un entier")
    else:
        seed = None
    human = payload.get("human")
    if human is not None and not isinstance(human, str):
        errors.append("human doit être un texte")
    return {"num_agents": n, "seed": seed, "human": human}, errors
