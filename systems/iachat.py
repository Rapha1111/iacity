"""IACHAT Engine : réseau social fictif (fil public, réponses, réactions, profils)."""
from agents.memory import add_memory
from simulation.state import next_id, clean_text
from systems import messaging, relationships

REACTIONS = ("like", "love", "laugh", "angry", "sad")


def author_name(sim, post):
    return post.get("author_name") or sim.state["agents"].get(post["author"], {}).get("name", post["author"])


def create_post(sim, author_id, text, reply_to=None, human=False, name=None):
    st = sim.state
    text = clean_text(text, 280)
    if not text:
        return None, "publication vide"
    if reply_to is not None and reply_to not in st["posts"]:
        return None, "publication parente introuvable"
    pid = next_id(st, "post")
    agent = st["agents"].get(author_id)
    post = {"id": pid, "n": len(st["posts"]) + 1, "author": author_id,
            "author_name": name or (agent["name"] if agent else author_id),
            "human": bool(human or (agent and agent["is_human"])), "text": text, "tick": st["tick"],
            "reply_to": reply_to, "reactions": {}}
    st["posts"][pid] = post
    seq = sim.emit("post" if not reply_to else "reply", [author_id], f"IACHAT — {post['author_name']} : {text}",
                   {"post": pid, "reply_to": reply_to, "text": text, "human": post["human"]})
    if agent:
        add_memory(sim, agent, "post", f"J'ai publié sur IACHAT : « {text} »", importance=0.35, fact_seq=seq)
    return post, "ok"


def react(sim, agent, post_id, kind):
    post = sim.state["posts"].get(post_id)
    if not post:
        return False, "publication introuvable"
    if kind not in REACTIONS:
        return False, "réaction inconnue"
    for k, lst in post["reactions"].items():
        if agent["id"] in lst:
            lst.remove(agent["id"])
    post["reactions"].setdefault(kind, []).append(agent["id"])
    sim.emit("reaction", [agent["id"], post["author"]], f"{agent['name']} réagit ({kind}) à un post de {author_name(sim, post)}", {"post": post_id, "kind": kind})
    author = sim.state["agents"].get(post["author"])
    if author and author["id"] != agent["id"]:
        relationships.adjust(sim, author, agent, trust=0.01 if kind in ("like", "love", "laugh") else -0.02, log=False)
    return True, "ok"


def replies(sim, post_id):
    return [p for p in sim.state["posts"].values() if p["reply_to"] == post_id]


def feed(sim, before=None, limit=30, author=None, include_replies=True):
    posts = list(sim.state["posts"].values())
    if author:
        posts = [p for p in posts if p["author"] == author]
    if not include_replies:
        posts = [p for p in posts if not p["reply_to"]]
    if before:
        posts = [p for p in posts if p["n"] < int(before)]
    posts = sorted(posts, key=lambda p: -p["n"])
    return posts[:limit], len(posts) > limit


def read_feed(sim, agent, n=6):
    """Un agent consulte IACHAT : seules les publications lues entrent dans sa mémoire."""
    st = sim.state
    mine = {p["id"] for p in st["posts"].values() if p["author"] == agent["id"]}
    new = [p for p in st["posts"].values() if p["n"] > agent["feed_cursor"] and p["author"] != agent["id"]]
    notif = [p for p in new if p["reply_to"] in mine]
    rest = [p for p in new if p not in notif]
    chosen = (notif + rest[-max(1, n - len(notif)):])[:n]
    if new:
        agent["feed_cursor"] = max(p["n"] for p in new)
    for p in chosen:
        add_memory(sim, agent, "post", f"Sur IACHAT, {author_name(sim, p)} a écrit : « {p['text']} »",
                   source=p["author"], confidence=0.9, importance=0.3, about=p["author"])
        a = st["agents"].get(p["author"])
        if a and a["profile"].get("show_number"):
            messaging.add_contact(sim, agent, a, "profil IACHAT")
    return chosen


def unread_count(sim, agent):
    return sum(1 for p in sim.state["posts"].values() if p["n"] > agent["feed_cursor"] and p["author"] != agent["id"])
