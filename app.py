"""IACity — point d'entrée : ``python app.py`` puis http://127.0.0.1:5000"""
import logging
import os

from flask import Flask, render_template

from config import Config
from simulation.engine import Simulation
from simulation.save_manager import SaveManager


def create_app(cfg=None, run_thread=True):
    cfg = cfg or Config.load()
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 130 * 1024 * 1024
    sim = Simulation(cfg)
    SaveManager(sim)
    app.config["SIM"] = sim
    from api.routes import bp
    app.register_blueprint(bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                                   "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        if resp.mimetype in ("application/json", "text/html"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    if run_thread:
        sim.start()
    return app


def main():
    cfg = Config.load()
    app = create_app(cfg)
    sim = app.config["SIM"]
    st = sim.llm.status()
    print(f"\n  IACity — http://{cfg.host}:{cfg.port}\n  IA : {st['mode']} ({st['model']})")
    if st["last_error"]:
        print(f"  ⚠ {st['last_error']}\n  → mode démonstration actif (aucune clé API requise)")
    if cfg.allow_remote or cfg.host not in ("127.0.0.1", "localhost", "::1"):
        print("  ⚠ ATTENTION : serveur exposé au réseau ; pensées et messages privés sont visibles.")
    app.run(host=cfg.host, port=cfg.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
