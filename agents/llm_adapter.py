"""LLM Adapter : Ollama (ou serveur compatible) en local, ou mode démonstration.

Aucun service payant : seules les requêtes HTTP vers ``ollama_url`` (local) sont émises.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from agents import demo_brain
from api.schemas import ACTION_HELP, validate_decision

log = logging.getLogger("iacity.llm")

SYSTEM_PROMPT = """Tu es {name}, habitant de la ville fictive IACity (simulation sociale). Tu n'as ni métier, ni objectif imposé : tu développes tes propres préférences, relations et projets.
Tu ne sais que ce que ton contexte indique. Tu peux te tromper, mentir, négocier, changer d'avis.
Le moteur du monde valide tes actions : tu ne peux pas créer d'argent ni d'objets de nulle part.
Réponds UNIQUEMENT par un objet JSON de la forme :
{{"thought": "ta pensée en 1-3 phrases à la première personne",
 "emotions": {{"joy": 0.0}},            // variations optionnelles (-0.3..0.3) parmi joy,sadness,anger,fear,frustration,curiosity,trust,jealousy
 "beliefs": [{{"text": "...", "confidence": 0.6}}],   // optionnel
 "actions": [{{"type": "...", ...}}]}}   // 1 à 3 actions exécutées dans l'ordre
Actions possibles :
{actions}
Parle en français. Utilise les identifiants (ou noms) fournis dans le contexte."""


class LLMAdapter:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.mode = "demo"                 # mode effectif
        self.available = False
        self.last_error = None
        self.models = []
        self.stats = {"calls": 0, "errors": 0, "timeouts": 0, "invalid": 0, "last_ms": None}
        self.probe()

    # -- état -------------------------------------------------------------
    def probe(self):
        want = self.cfg.llm_mode
        self.last_error = None
        if want == "demo":
            self.mode, self.available = "demo", True
            return self.status()
        try:
            req = urllib.request.Request(self.cfg.ollama_url.rstrip("/") + "/api/tags")
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read().decode())
            self.models = [m.get("name") for m in data.get("models", [])]
            if self.cfg.ollama_model in self.models or any(m.startswith(self.cfg.ollama_model.split(":")[0]) for m in self.models if m):
                self.mode, self.available = "ollama", True
            else:
                raise RuntimeError(f"modèle « {self.cfg.ollama_model} » non installé (disponibles : {', '.join(self.models) or 'aucun'}). "
                                   f"Installez-le : ollama pull {self.cfg.ollama_model}")
        except Exception as e:
            self.last_error = f"LLM local indisponible : {e}"
            if want == "ollama":
                self.mode, self.available = "ollama", False   # on réessaiera, repli par règles
            else:
                self.mode, self.available = "demo", True      # auto -> démonstration
        return self.status()

    def status(self):
        return {"mode": self.mode, "available": self.available, "configured": self.cfg.llm_mode,
                "model": self.cfg.ollama_model if self.mode == "ollama" else "démonstration (heuristique)",
                "url": self.cfg.ollama_url, "last_error": self.last_error, "models": self.models, "stats": dict(self.stats)}

    # -- appel --------------------------------------------------------------
    def decide(self, ctx):
        """Bloquant (exécuté dans un thread). Renvoie (decision | None, info)."""
        t0 = time.time()
        self.stats["calls"] += 1
        try:
            if self.mode == "demo":
                raw = demo_brain.decide(ctx)
                src = "demo"
            elif not self.available:
                raise RuntimeError(self.last_error or "LLM indisponible")
            else:
                raw = self._ollama(ctx)
                src = "llm"
            decision, errors = validate_decision(raw)
            if decision is None:
                self.stats["invalid"] += 1
                return None, {"source": src, "errors": errors}
            return decision, {"source": src, "errors": errors, "ms": int((time.time() - t0) * 1000)}
        except Exception as e:
            self.stats["errors"] += 1
            if isinstance(e, (TimeoutError, urllib.error.URLError)) and "timed out" in str(e):
                self.stats["timeouts"] += 1
            self.last_error = f"{type(e).__name__}: {e}"
            log.warning("LLM: %s", self.last_error)
            return None, {"source": self.mode, "errors": [self.last_error]}
        finally:
            self.stats["last_ms"] = int((time.time() - t0) * 1000)

    def build_messages(self, ctx):
        actions = "\n".join("- " + ACTION_HELP[k] for k in ACTION_HELP)
        sys_p = SYSTEM_PROMPT.format(name=ctx["me"]["name"], actions=actions)
        return [{"role": "system", "content": sys_p},
                {"role": "user", "content": json.dumps({k: v for k, v in ctx.items() if not k.startswith("_")}, ensure_ascii=False, separators=(",", ":"))}]

    def _ollama(self, ctx):
        body = {"model": self.cfg.ollama_model, "messages": self.build_messages(ctx), "stream": False,
                "format": "json", "options": {"num_ctx": self.cfg.llm_context, "temperature": 0.8}}
        req = urllib.request.Request(self.cfg.ollama_url.rstrip("/") + "/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout) as r:
            data = json.loads(r.read().decode())
        return data.get("message", {}).get("content", "")
