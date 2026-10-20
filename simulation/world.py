"""World Engine : génération de la ville, tuiles, lieux, positions valides."""
import math

from simulation.state import next_id

WALKABLE = set("grpkldfs")   # herbe, route, place, parc, terrain, porte, sol, trottoir

RAW_KINDS = {  # ressources naturelles/approvisionnées : prix de base
    "bois": 6, "farine": 4, "fruit": 3, "herbes": 3, "tissu": 8, "metal": 12,
}
FOOD_KINDS = {"farine", "fruit", "herbes", "repas"}

PLACE_TYPES = {
    "mairie":     dict(indoor=True, noise=0.15, wage=14, label="Mairie"),
    "police":     dict(indoor=True, noise=0.15, wage=13, label="Police"),
    "hopital":    dict(indoor=True, noise=0.20, wage=15, label="Hôpital"),
    "ecole":      dict(indoor=True, noise=0.25, wage=11, label="École", study=True),
    "epicerie":   dict(indoor=True, noise=0.20, wage=9, label="Épicerie", commerce=True, sells=["farine", "fruit", "herbes"]),
    "atelier":    dict(indoor=True, noise=0.30, wage=10, label="Atelier", commerce=True, sells=["bois", "metal", "tissu"]),
    "restaurant": dict(indoor=True, noise=0.45, wage=9, label="Restaurant", commerce=True, leisure=True, entry=0, sells=["repas"]),
    "bar":        dict(indoor=True, noise=0.60, wage=9, label="Bar", commerce=True, leisure=True, entry=6),
    "bureau":     dict(indoor=True, noise=0.10, wage=12, label="Bureaux"),
    "habitation": dict(indoor=True, noise=0.05, label="Habitation", housing=True),
    "boutique":   dict(indoor=True, noise=0.20, wage=9, label="Boutique", commerce=True),
    "loisirs":    dict(indoor=True, noise=0.50, wage=9, label="Loisirs", commerce=True, leisure=True, entry=8),
    "plaza":      dict(indoor=False, noise=0.30, label="Place", leisure=True, entry=0),
    "parc":       dict(indoor=False, noise=0.10, label="Parc", leisure=True, entry=0, gather=True),
    "rue":        dict(indoor=False, noise=0.20, label="Rue"),
    "terrain":    dict(indoor=False, noise=0.05, label="Terrain à bâtir"),
    "exterieur":  dict(indoor=False, noise=0.15, label="Extérieur"),
}
BUILDABLE_TYPES = ["boutique", "restaurant", "bar", "bureau", "atelier", "habitation", "loisirs", "epicerie"]

NAMES = {
    "mairie": "Mairie d'IACity", "police": "Commissariat", "hopital": "Hôpital Saint-Pixel",
    "ecole": "École des Trois Tuiles", "epicerie": "Épicerie du Coin", "atelier": "Atelier Bricolo",
    "restaurant": "Restaurant Le Bit", "bar": "Bar Le Pixel", "bureau": "Bureaux Octet & Cie",
}
HOUSING = [("Résidence Les Tilleuls", 8), ("Résidence du Parc", 8), ("Maisons de la Rue Haute", 6)]


def new_place(state, ptype, name, rect, owner="city", **extra):
    spec = PLACE_TYPES[ptype]
    pid = next_id(state, "place")
    x, y, w, h = rect
    p = {
        "id": pid, "name": name, "type": ptype, "indoor": spec["indoor"], "rect": [x, y, w, h],
        "door": [x + w // 2, y + h - 1] if spec["indoor"] else None,
        "noise": spec["noise"], "owner": owner, "description": "", "wage": spec.get("wage"),
        "for_sale": False, "price": None, "capacity": 0, "tenants": {},
        "natural": {}, "built": False, "created_by": None, "tick_created": 0,
    }
    p.update(extra)
    state["places"][pid] = p
    return p


def generate_world(cfg, rng, state):
    W, H = cfg.map_w, cfg.map_h
    bw, bh = (W - 4) // 3, (H - 4) // 3
    lw, lh = min(8, (bw - 3) // 2), min(8, bh - 3)
    grid = [["g"] * W for _ in range(H)]
    # routes
    for c in (0, 1):
        x0 = (c + 1) * bw + c * 2
        for y in range(H):
            for x in range(x0, x0 + 2):
                grid[y][x] = "r"
    streets = []
    for r in (0, 1):
        y0 = (r + 1) * bh + r * 2
        for y in range(y0, y0 + 2):
            for x in range(W):
                grid[y][x] = "r"
        streets.append(y0)

    def block(r, c):
        return c * (bw + 2), r * (bh + 2)

    # plaza (bloc central) et parc (bloc sud-est)
    px, py = block(1, 1)
    plaza = new_place(state, "plaza", "Place Centrale", (px, py, bw, bh))
    for y in range(py, py + bh):
        for x in range(px, px + bw):
            grid[y][x] = "p"
    grid[py + bh // 2][px + bw // 2] = "x"  # fontaine
    kx, ky = block(2, 2)
    parc = new_place(state, "parc", "Parc des Pixels", (kx, ky, bw, bh), natural={"bois": 8, "fruit": 8, "herbes": 8})
    for y in range(ky, ky + bh):
        for x in range(kx, kx + bw):
            grid[y][x] = "k"
    for _ in range(bw * bh // 9):
        x, y = rng.randrange(kx + 1, kx + bw - 1), rng.randrange(ky + 1, ky + bh - 1)
        grid[y][x] = "t"
    grid[ky + bh // 2][kx + bw // 2] = "o"  # mare
    grid[ky + bh // 2][kx + bw // 2 + 1] = "o"
    new_place(state, "rue", "Rue Haute", (0, streets[0], W, 2))
    new_place(state, "rue", "Rue Basse", (0, streets[1], W, 2))
    state["places"]["p_outdoor"] = {
        "id": "p_outdoor", "name": "Quartier", "type": "exterieur", "indoor": False,
        "rect": [0, 0, W, H], "door": None, "noise": 0.15, "owner": None, "description": "",
        "wage": None, "for_sale": False, "price": None, "capacity": 0, "tenants": {},
        "natural": {}, "built": False, "created_by": None, "tick_created": 0}

    # lots
    lots = []
    for r in range(3):
        for c in range(3):
            if (r, c) in ((1, 1), (2, 2)):
                continue
            bx, by = block(r, c)
            lots.append((bx + 1, by + 1))
            lots.append((bx + bw - 1 - lw, by + 1))
    kinds = ["mairie", "police", "hopital", "ecole", "epicerie", "atelier", "restaurant", "bar", "bureau",
             "hab0", "hab1", "hab2", "terrain", "terrain"]
    rng.shuffle(kinds)
    tcount = 0
    for (lx, ly), kind in zip(lots, kinds):
        rect = (lx, ly, lw, lh)
        if kind.startswith("hab"):
            name, cap = HOUSING[int(kind[3])]
            p = new_place(state, "habitation", name, rect, capacity=cap)
        elif kind == "terrain":
            tcount += 1
            p = new_place(state, "terrain", f"Terrain à bâtir n°{tcount}", rect, for_sale=True, price=cfg.build_cost // 2)
        else:
            p = new_place(state, kind, NAMES[kind], rect)
        if p["type"] == "terrain":
            for y in range(ly, ly + lh):
                for x in range(lx, lx + lw):
                    grid[y][x] = "l"
        else:
            paint_building(grid, p)
        # trottoir porte -> route
        if p["door"]:
            dx, dy = p["door"]
            y = dy + 1
            while y < H and grid[y][dx] not in "r":
                if grid[y][dx] == "g":
                    grid[y][dx] = "s"
                y += 1
    # arbres décoratifs
    for _ in range(W * H // 40):
        x, y = rng.randrange(W), rng.randrange(H)
        if grid[y][x] == "g":
            grid[y][x] = "t"
    state["map"] = ["".join(row) for row in grid]
    return state


def paint_building(grid, p):
    x, y, w, h = p["rect"]
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            edge = xx in (x, x + w - 1) or yy in (y, y + h - 1)
            grid[yy][xx] = "w" if edge else "f"
    dx, dy = p["door"]
    grid[dy][dx] = "d"


def tile_at(state, x, y):
    rows = state["map"]
    if 0 <= y < len(rows) and 0 <= x < len(rows[0]):
        return rows[y][x]
    return None


def walkable(state, x, y):
    t = tile_at(state, x, y)
    return t is not None and t in WALKABLE


def place_at(state, x, y):
    best, area = None, None
    for p in state["places"].values():
        if p["id"] == "p_outdoor":
            continue
        rx, ry, rw, rh = p["rect"]
        if rx <= x < rx + rw and ry <= y < ry + rh:
            a = rw * rh
            if area is None or a < area:
                best, area = p, a
    return best or state["places"]["p_outdoor"]


def place_tiles(state, p):
    x, y, w, h = p["rect"]
    out = []
    if p["indoor"]:
        rng_x, rng_y = range(x + 1, x + w - 1), range(y + 1, y + h - 1)
    else:
        rng_x, rng_y = range(x, x + w), range(y, y + h)
    for yy in rng_y:
        for xx in rng_x:
            if walkable(state, xx, yy):
                out.append((xx, yy))
    return out


def random_spot(sim, p):
    tiles = place_tiles(sim.state, p)
    if not tiles:
        return None
    occupied = {(a["x"], a["y"]) for a in sim.state["agents"].values() if a.get("x") is not None}
    free = [t for t in tiles if t not in occupied] or tiles
    return sim.rng.choice(free)


def distance(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def free_plots(state):
    return [p for p in state["places"].values() if p["type"] == "terrain" and p["owner"] == "city" and not p["built"]]


def convert_plot(state, plot, ptype, name, owner, description, tick):
    """Transforme un terrain en bâtiment (création de lieu validée par l'économie)."""
    spec = PLACE_TYPES[ptype]
    plot.update(type=ptype, name=name, indoor=True, noise=spec["noise"], wage=spec.get("wage"),
                owner=owner, description=description, built=True, created_by=owner,
                tick_created=tick, for_sale=False, price=None)
    plot["door"] = [plot["rect"][0] + plot["rect"][2] // 2, plot["rect"][1] + plot["rect"][3] - 1]
    if spec.get("housing"):
        plot["capacity"] = 6
    rows = [list(r) for r in state["map"]]
    paint_building(rows, plot)
    state["map"] = ["".join(r) for r in rows]
