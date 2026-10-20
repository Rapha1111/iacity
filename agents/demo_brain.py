"""Mode démonstration : « cerveau » heuristique qui imite un LLM local.

Il produit exactement le même format de décision structurée que le LLM
(thought / emotions / beliefs / actions), pour tester l'interface et la
simulation sans modèle installé. Il est déterministe pour un contexte donné.
"""
import random

from agents import templates

RECIPES = {
    "Pain": ("nourriture", ["farine"], "Un pain croustillant fait maison."),
    "Confiture": ("nourriture", ["fruit", "fruit"], "Confiture de fruits du parc."),
    "Tisane": ("nourriture", ["herbes"], "Tisane aux herbes du parc."),
    "Tarte aux fruits": ("nourriture", ["farine", "fruit"], "Une tarte généreuse."),
    "Bougie parfumée": ("objet", ["tissu", "herbes"], "Une bougie à la lavande."),
    "Sac en tissu": ("objet", ["tissu"], "Un sac solide cousu main."),
    "Jouet en bois": ("loisir", ["bois"], "Un petit jouet sculpté."),
}
SOURCES = {"farine": ["epicerie"], "fruit": ["epicerie", "parc"], "herbes": ["epicerie", "parc"],
           "tissu": ["atelier"], "bois": ["atelier", "parc"], "metal": ["atelier"]}
SHOP_NAMES = ["Chez {n}", "La Petite Boutique de {n}", "Le Coin de {n}", "Atelier {n}"]


def decide(ctx):
    rng = random.Random(ctx.get("_seed", 0))
    me = ctx["me"]
    acts, thoughts, emo, beliefs = [], [], {}, []
    pers = me["personality"]
    here = ctx["here"]
    people = {p["id"]: p for p in here["people"]}

    # 1. répondre à ce qui m'est adressé
    to_me = [h for h in ctx["heard"] if h.get("to_me")]
    if to_me:
        h = to_me[-1]
        rel = next((r for r in me["relations"] if r["id"] == h["from_id"]), {"trust": 0.3, "hostility": 0.0})
        if h["from_id"] in people or True:
            line, tone, end = templates.reply_line(rng, h["from"], h["text"], rel["trust"], rel["hostility"], h.get("turns", 0))
            if templates.is_goodbye(h["text"]):
                return {"thought": f"{h['from']} prend congé.", "emotions": {}, "beliefs": [], "actions": [{"type": "leave_conversation"}]}
            say = {"type": "say", "to": h["from_id"], "text": line, "tone": tone}
            if tone > 0.3 and ctx["knowledge"] and rng.random() < 0.35:
                k = rng.choice(ctx["knowledge"])
                say["claim"] = {"text": k["claim"], "knowledge_id": k["id"], "truthful": True, "rumor": True}
            acts.append(say)
            if end:
                acts.append({"type": "leave_conversation"})
            thoughts.append(f"{h['from']} m'a parlé ; je réponds {'sèchement' if tone < 0 else 'aimablement'}.")
            if tone < 0:
                emo["anger"] = 0.1
            if rel["trust"] > 0.3 and not rel.get("has_my_number") and rng.random() < 0.6 and tone >= 0:
                acts.append({"type": "give_number", "to": h["from_id"]})
                thoughts.append("Je lui donne mon numéro.")
            if rel["trust"] > 0.75 and rel.get("friendship", 0) > 0.5 and pers["extraversion"] > 0.45 and "ami" not in rel.get("types", []) and rng.random() < 0.3:
                acts.append({"type": "propose_bond", "to": h["from_id"], "bond": "ami"})
    for m in ctx["messages"]:
        acts.append({"type": "text", "to": m["from_id"], "text": templates.pick(rng, templates.SMS_REPLY, t=m["from"])})
        thoughts.append(f"Message de {m['from']} : je réponds.")
        break
    for b in ctx.get("bond_proposals", []):
        rel = next((r for r in me["relations"] if r["id"] == b["from"]), {"trust": 0.0})
        accept = rel["trust"] > 0.5 and pers["agreeableness"] > 0.35
        acts.append({"type": "answer_bond", "from": b["from"], "accept": accept})
        thoughts.append(f"Proposition « {b['type']} » de {b['from_name']} : {'oui' if accept else 'non'}.")
        break

    # 2. objectifs
    active = me["goals"]
    if not active and len(acts) < 2:
        g, note = new_goal(ctx, rng)
        if g:
            acts.append({"type": "set_goal", **g})
            thoughts.append(note)
            active = [dict(g, id="?", progress=0.0)]
    if active and len(acts) < 3:
        g = active[0]
        steps, note = pursue(ctx, g, rng)
        for s in steps:
            if len(acts) < 3:
                acts.append(s)
        if note:
            thoughts.append(note)

    # 3. vie sociale / IACHAT occasionnelle
    for fp in ctx.get("feed", [])[:1]:
        if len(acts) < 3 and fp["author_id"] != me["id"]:
            sentiment_pos = rng.random() < 0.7
            if rng.random() < 0.5:
                acts.append({"type": "react", "post_id": fp["id"], "kind": "like" if sentiment_pos else "sad"})
            else:
                acts.append({"type": "reply", "post_id": fp["id"], "text": rng.choice([
                    f"Bien vu {fp['author']} !", "Je suis d'accord avec toi.", "Intéressant, dis-m'en plus.", "Pas sûr que ce soit une bonne idée…"])})
            thoughts.append(f"J'ai lu le message de {fp['author']} sur IACHAT.")
    free_people = [p for p in here["people"] if not p["in_conversation"] and p.get("audible", True)]
    if len(acts) < 3 and not to_me and free_people and me["needs"]["social"] > 30 and rng.random() < 0.55:
        p = max(free_people, key=lambda p: (not p["known"]) * 0.3 + p["trust"] + rng.random() * 0.4)
        acts.append({"type": "say", "to": p["id"], "text": templates.pick(rng, templates.GREET if not p["known"] else templates.SMALL, t=p["name"], place=me["place"]["name"])})
        thoughts.append(f"J'engage la conversation avec {p['name']}.")
    if len(acts) < 3 and not to_me:
        if ctx["iachat_unread"] > 2 and rng.random() < 0.4:
            acts.append({"type": "read_feed"})
        elif me["last_post_age"] > 120 and rng.random() < pers["extraversion"] * 0.5:
            options = [f"Belle journée à IACity ! Je suis à {me['place']['name']}.",
                       "Quelqu'un a des idées pour animer la ville ?",
                       "Je cherche des gens sympas pour discuter.",
                       "Les prix sont-ils trop élevés selon vous ?",
                       f"Aujourd'hui je suis à {me['place']['name']}, passez me dire bonjour !"]
            if active:
                options.append(f"Mon projet du moment : {active[0]['description'].lower()}. Des conseils ?")
            sellable = [i for i in me["inventory"] if i.get("price")]
            if sellable:
                options += [f"À vendre : « {sellable[0]['name']} » à {sellable[0]['price']} pièces, fait maison !"] * 3
            acts.append({"type": "post", "text": rng.choice(options)})
    if not acts:
        acts.append({"type": "wait"})
        thoughts.append("Je prends le temps d'observer autour de moi.")
    return {"thought": " ".join(thoughts)[:500], "emotions": emo, "beliefs": beliefs, "actions": acts[:3]}


def new_goal(ctx, rng):
    me, pers = ctx["me"], ctx["me"]["personality"]
    opts = []
    if me["money"] < 160:
        opts.append((3.0, "earn"))
    else:
        opts.append((1.0, "earn"))
    opts.append((1.0 + 2 * pers["openness"] + pers["conscientiousness"], "craft"))
    if me["money"] >= ctx["build"]["cost"] * 0.6 and ctx["free_plots"]:
        opts.append((1.0 + 2 * pers["conscientiousness"], "place"))
    others = [r for r in me["relations"] if r["trust"] < 0.7]
    if others:
        opts.append((0.8 + 2 * pers["extraversion"], "friend"))
    opts.append((0.6 + pers["openness"], "learn"))
    total = sum(w for w, _ in opts)
    r = rng.random() * total
    for w, kind in opts:
        r -= w
        if r <= 0:
            break
    if kind == "earn":
        amount = int(me["money"] + rng.choice([100, 150, 250]))
        return ({"description": f"Gagner de l'argent pour atteindre {amount}", "kind": "earn_money", "params": {"amount": amount}, "priority": 0.7},
                "J'ai besoin d'argent : je vise une somme précise.")
    if kind == "craft":
        name = rng.choice(list(RECIPES))
        return ({"description": f"Fabriquer et vendre : {name}", "kind": "obtain_item", "params": {"name": name}, "priority": 0.6},
                f"Je pourrais fabriquer « {name} » et le vendre aux habitants.")
    if kind == "place":
        sname = rng.choice(SHOP_NAMES).format(n=me["name"])
        return ({"description": f"Ouvrir un commerce « {sname} »", "kind": "create_place", "params": {"name": sname, "type": rng.choice(["boutique", "restaurant", "bar"])}, "priority": 0.8},
                "Je veux posséder mon propre lieu et y vendre mes produits.")
    if kind == "friend":
        r = rng.choice(others)
        return ({"description": f"Devenir proche de {r['name']}", "kind": "improve_relation", "params": {"agent": r["id"], "trust": 0.7}, "priority": 0.5},
                f"J'aimerais mieux connaître {r['name']}.")
    return ({"description": "Apprendre et gagner en savoirs", "kind": "learn_skill", "params": {"skill": "savoirs", "level": 1.0}, "priority": 0.4},
            "J'ai envie d'apprendre de nouvelles choses.")


def best_work_place(ctx):
    cands = [p for p in ctx["places"] if p.get("wage") and p["open"] and p["type"] != "habitation" and p.get("payer_ok", True)]
    if not cands:
        return None
    return max(cands, key=lambda p: p["wage"] + random.Random(len(cands) * 7 + hash(p["id"]) % 5 + ctx.get("_seed", 0)).random() * 8)


def place_by_type(ctx, *types):
    for t in types:
        for p in ctx["places"]:
            if p["type"] == t and p["open"]:
                return p
    return None


def go(ctx, place):
    return [] if not place or ctx["me"]["place"]["id"] == place["id"] else [{"type": "teleport", "place": place["id"]}]


def pursue(ctx, g, rng):
    me = ctx["me"]
    kind, p = g["kind"], g.get("params", {})
    here_type = me["place"]["type"]
    if kind == "earn_money":
        wp = best_work_place(ctx)
        if not wp:
            return [{"type": "wait"}], "Tous les lieux de travail sont fermés."
        return go(ctx, wp) + [{"type": "work"}], f"Je vais travailler à {wp['name']} pour mon objectif."
    if kind == "obtain_item":
        return craft_steps(ctx, p.get("name", "Pain"), rng)
    if kind == "create_place":
        if not ctx["free_plots"]:
            return [{"type": "drop_goal", "goal_id": g["id"]}], "Plus de terrain libre : j'abandonne ce projet."
        need = {"bois": 3, "metal": 2}
        inv = kinds_in_inventory(me)
        missing = [k for k, q in need.items() if len(inv.get(k, [])) < q]
        if missing:
            return acquire(ctx, missing[0], rng)
        if me["money"] < ctx["build"]["cost"] + ctx["free_plots"][0].get("price", 0):
            wp = best_work_place(ctx)
            return (go(ctx, wp) + [{"type": "work"}]) if wp else [{"type": "wait"}], "Il me manque de l'argent pour construire."
        plot = ctx["free_plots"][0]
        return go(ctx, plot) + [{"type": "build", "plot": plot["id"], "name": p.get("name", f"Chez {me['name']}"), "place_type": p.get("type", "boutique"),
                                 "description": f"Créé par {me['name']}"}], "J'ai tout pour construire mon lieu !"
    if kind in ("improve_relation", "meet"):
        tid = p.get("agent")
        people = {x["id"]: x for x in ctx["here"]["people"]}
        tgt = next((r for r in me["relations"] if r["id"] == tid), None)
        name = tgt["name"] if tgt else "lui"
        if tid in people and people[tid].get("audible", True):
            return [{"type": "say", "to": tid, "text": templates.pick(rng, templates.GREET + templates.SMALL, t=name, place=me["place"]["name"])}], f"Je profite de croiser {name}."
        spot = rng.choice([x for x in ctx["places"] if x["type"] in ("plaza", "parc", "bar", "restaurant") and x["open"]] or ctx["places"])
        return go(ctx, spot) or [{"type": "wait"}], f"Je cherche {name} du côté de {spot['name']}."
    if kind == "learn_skill":
        sch = place_by_type(ctx, "ecole")
        if not sch:
            return [{"type": "wait"}], "L'école est fermée."
        return go(ctx, sch) + [{"type": "study"}], "Je vais à l'école."
    return [{"type": "read_feed"}], "Je prends des nouvelles de la ville."


def kinds_in_inventory(me):
    d = {}
    for it in me["inventory"]:
        d.setdefault(it["kind"], []).append(it["id"])
    return d


def acquire(ctx, kind, rng):
    """Se procurer une ressource : acheter ici si possible, sinon aller là où on en trouve."""
    me = ctx["me"]
    for m in ctx["here"]["market"]:
        if m["kind"] == kind and m["price"] <= me["money"]:
            return [{"type": "buy", "item_id": m["item_id"]}], f"J'achète du/de la {kind}."
    here_type = me["place"]["type"]
    if here_type == "parc" and kind in ("bois", "fruit", "herbes"):
        return [{"type": "gather", "kind": kind}], f"Je ramasse du/de la {kind}."
    for t in SOURCES.get(kind, []):
        pl = place_by_type(ctx, t)
        if pl and (t != "parc" or kind in ("bois", "fruit", "herbes")):
            if me["place"]["id"] == pl["id"]:
                if t == "parc":
                    return [{"type": "gather", "kind": kind}], f"Je ramasse du/de la {kind}."
                continue
            first = go(ctx, pl)
            if t == "parc":
                return first + [{"type": "gather", "kind": kind}], f"Je vais chercher du/de la {kind} à {pl['name']}."
            return first, f"Je vais chercher du/de la {kind} à {pl['name']}."
    if me["money"] < 20:
        wp = best_work_place(ctx)
        if wp:
            return go(ctx, wp) + [{"type": "work"}], "Il me faut de l'argent pour acheter des ingrédients."
    return [{"type": "wait"}], f"Je ne trouve pas de {kind}."


def craft_steps(ctx, name, rng):
    me = ctx["me"]
    cat, kinds, desc = RECIPES.get(name, RECIPES["Pain"])
    inv = kinds_in_inventory(me)
    ids, need = [], {}
    for k in kinds:
        need[k] = need.get(k, 0) + 1
    for k, q in need.items():
        have = inv.get(k, [])
        if len(have) < q:
            return acquire(ctx, k, rng)
        ids += have[:q]
    cost = sum(next((it["cost"] for it in me["inventory"] if it["id"] == i), 5) for i in ids)
    price = max(8, int(cost * 2.2))
    steps = [{"type": "craft", "name": name, "description": desc, "category": cat, "ingredients": ids, "price": price}]
    return steps, f"J'ai les ingrédients : je fabrique « {name} »."
