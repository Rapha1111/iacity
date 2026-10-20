import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app          # noqa: E402
from config import Config           # noqa: E402

H = {"X-IACity": "1"}


@pytest.fixture
def app():
    cfg = Config.load(data_dir=tempfile.mkdtemp(), num_agents=6, llm_mode="demo", seed=42, event_frequency=0.0)
    app = create_app(cfg, run_thread=False)
    app.config["SIM"].paused = True
    yield app
    app.config["SIM"].stop()


@pytest.fixture
def sim(app):
    return app.config["SIM"]


@pytest.fixture
def client(app):
    return app.test_client()


def two_agents(sim):
    a, b = [x for x in sim.state["agents"].values()][:2]
    return a, b


def put(sim, agent, place_id):
    from simulation.world import random_spot
    p = sim.state["places"][place_id]
    x, y = random_spot(sim, p)
    agent["x"], agent["y"], agent["place"] = x, y, place_id
    return p
