"""Configuration centralisée d'IACity (cahier des charges §20).

Chaque paramètre peut être surchargé par une variable d'environnement
``IACITY_<NOM_EN_MAJUSCULES>`` (ex. ``IACITY_NUM_AGENTS=12``).
"""
import os
from dataclasses import dataclass, fields, asdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class Config:
    # Serveur
    host: str = "127.0.0.1"          # local uniquement par défaut (§16)
    port: int = 5000
    allow_remote: bool = False        # exposition réseau = action explicite
    data_dir: str = os.path.join(BASE_DIR, "data")
    log_level: str = "INFO"

    # Simulation
    num_agents: int = 8               # 1..20
    seed: int = 0                     # 0 = graine aléatoire
    speed: float = 1.0
    tick_seconds: float = 1.0         # secondes réelles par cycle à vitesse x1
    minutes_per_tick: int = 5         # minutes simulées par cycle
    map_w: int = 66
    map_h: int = 42
    event_frequency: float = 1.0      # événements aléatoires par jour simulé
    autosave_every_days: float = 1.0  # 0 = désactivé

    # Agents
    perception_every: int = 4         # fréquence de perception (cycles)
    reflection_every: int = 72        # fréquence de réflexion approfondie (cycles)
    llm_min_interval: int = 8         # cycles minimum entre 2 appels LLM d'un agent

    # LLM local
    llm_mode: str = "auto"            # auto | ollama | demo
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    llm_timeout: float = 90.0
    llm_context: int = 4096
    llm_max_concurrent: int = 2
    llm_queue_max: int = 12

    # Communication
    conversation_range: float = 5.0   # portée d'une voix normale (tuiles)
    wall_attenuation: float = 0.35    # facteur de portée par mur traversé
    noise_effect: float = 0.6         # impact du bruit ambiant
    conversation_idle_ticks: int = 14
    conversation_max_turns: int = 40

    # Économie
    start_money: int = 200
    treasury_start: int = 6000
    rent_per_day: int = 40
    wage_scale: float = 1.0
    price_scale: float = 1.0
    build_cost: int = 250

    @classmethod
    def load(cls, **overrides):
        cfg = cls()
        for f in fields(cls):
            env = os.environ.get("IACITY_" + f.name.upper())
            if env is not None:
                setattr(cfg, f.name, _cast(f.type, env))
        for k, v in overrides.items():
            if v is not None and hasattr(cfg, k):
                setattr(cfg, k, v)
        cfg.num_agents = max(1, min(20, int(cfg.num_agents)))
        cfg.map_w = max(54, int(cfg.map_w))
        cfg.map_h = max(36, int(cfg.map_h))
        return cfg

    def to_dict(self):
        return asdict(self)


def _cast(typ, raw):
    t = typ if isinstance(typ, str) else typ.__name__
    if t == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "oui", "on")
    if t == "int":
        return int(raw)
    if t == "float":
        return float(raw)
    return raw
