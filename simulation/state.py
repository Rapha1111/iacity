"""Helpers d'état : identifiants, temps simulé, utilitaires partagés.

L'état complet de la simulation est un dictionnaire JSON-natif : une
sauvegarde est donc simplement sa sérialisation.
"""
import re

SCHEMA_VERSION = 1

ID_PREFIX = {
    "agent": "a", "item": "i", "post": "t", "conv": "c", "msg": "m",
    "goal": "g", "mem": "k", "tx": "x", "place": "p", "know": "n", "belief": "b",
}


def next_id(state, kind):
    n = state["ids"].get(kind, 0) + 1
    state["ids"][kind] = n
    return f"{ID_PREFIX[kind]}{n}"


def minutes_of(sim, tick):
    return tick * sim.cfg.minutes_per_tick


def day_of(sim, tick):
    return minutes_of(sim, tick) // 1440 + 1


def minute_of_day(sim, tick):
    return minutes_of(sim, tick) % 1440


def fmt_time(sim, tick):
    m = minutes_of(sim, tick)
    return f"Jour {m // 1440 + 1} {(m % 1440) // 60:02d}:{m % 60:02d}"


def ticks_per_day(sim):
    return 1440 // sim.cfg.minutes_per_tick


def is_night(sim, tick):
    h = minute_of_day(sim, tick) // 60
    return h >= 22 or h < 6


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def clean_text(s, limit=280):
    """Texte libre venant d'un agent/utilisateur : sans contrôle, borné."""
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def tokens(text):
    return set(w for w in re.findall(r"[a-zàâäçéèêëîïôöùûüÿœ0-9]{4,}", (text or "").lower()))
