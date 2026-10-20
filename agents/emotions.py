"""Émotions simulées, personnalité et besoins (mécanismes simulés, pas de conscience)."""
from simulation.state import clamp

EMOTIONS = ["joy", "sadness", "anger", "fear", "frustration", "curiosity", "trust", "jealousy"]
EMOTION_FR = {"joy": "joie", "sadness": "tristesse", "anger": "colère", "fear": "peur",
              "frustration": "frustration", "curiosity": "curiosité", "trust": "confiance", "jealousy": "jalousie"}
BASELINE = {"joy": 0.4, "sadness": 0.1, "anger": 0.05, "fear": 0.05, "frustration": 0.1,
            "curiosity": 0.5, "trust": 0.4, "jealousy": 0.05}
TRAITS = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism", "honesty"]
NEEDS = ["social", "fun", "comfort", "security", "curiosity"]   # 0 = satisfait, 100 = urgent
NEED_FR = {"social": "social", "fun": "loisirs", "comfort": "confort", "security": "sécurité (argent/logement)", "curiosity": "curiosité"}


def initial_emotions():
    return dict(BASELINE)


def initial_personality(rng):
    """Traits faiblement définis, tirés autour de la neutralité."""
    return {t: round(clamp(rng.gauss(0.5, 0.15)), 3) for t in TRAITS}


def initial_needs(rng):
    return {n: round(rng.uniform(15, 45), 1) for n in NEEDS}


def nudge(agent, **deltas):
    e = agent["emotions"]
    for k, v in deltas.items():
        if k in e:
            e[k] = round(clamp(e[k] + v), 3)


def apply_deltas(agent, deltas):
    if isinstance(deltas, dict):
        nudge(agent, **{k: max(-0.5, min(0.5, float(v))) for k, v in deltas.items()
                        if k in EMOTIONS and isinstance(v, (int, float))})


def decay(agent, rate=0.02):
    e = agent["emotions"]
    for k, base in BASELINE.items():
        e[k] = round(e[k] + (base - e[k]) * rate, 3)


def dominant(agent, n=2):
    e = agent["emotions"]
    ranked = sorted(((abs(e[k] - BASELINE[k]), k) for k in EMOTIONS), reverse=True)
    return [k for _, k in ranked[:n]]


def drift_needs(agent, dt=1.0, night=False):
    n = agent["needs"]
    f = 0.4 if night else 1.0
    n["social"] = min(100, n["social"] + 0.09 * dt * f * (0.6 + agent["personality"]["extraversion"]))
    n["fun"] = min(100, n["fun"] + 0.08 * dt * f)
    n["comfort"] = min(100, n["comfort"] + 0.10 * dt * (0.5 if night else 1.0))
    n["curiosity"] = min(100, n["curiosity"] + 0.10 * dt * f * (0.5 + agent["personality"]["openness"]))
    sec = 0.0
    if agent["money"] < 60:
        sec += 0.25
    if not agent.get("home"):
        sec += 0.25
    n["security"] = max(0.0, min(100, n["security"] + (sec - 0.12) * dt))


def satisfy(agent, **amounts):
    for k, v in amounts.items():
        if k in agent["needs"]:
            agent["needs"][k] = max(0.0, min(100.0, agent["needs"][k] - v))


def evolve_personality(agent, trait, delta):
    """Évolution lente de la personnalité selon l'expérience."""
    if trait in agent["personality"]:
        agent["personality"][trait] = round(clamp(agent["personality"][trait] + delta), 3)
