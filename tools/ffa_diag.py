"""Death-cause / timing diagnostics for the FFA league sim (all 16 = same spec).

    python tools/ffa_diag.py --matches 20 --spec 'bot:bot.py?sneak'
"""
import argparse, collections, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arena


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=10)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--spec", default="bot:bot.py?sneak")
    a = ap.parse_args()
    cfg = arena.load_cfg(".")
    fac = arena.make_factory(a.spec, ".")
    world = next(iter(arena._MODS.values()))._shared[0]
    rows = []
    orig = arena.League._die
    def die(self, t, by):
        if not isinstance(t, arena.Prop) and t.alive:
            kind = "zone" if by is None else ("npc" if isinstance(by, arena.Prop) else "mech")
            self._diag.append({"t": round(self.t, 1), "cause": kind, "cubes": t.cubes, "alive_before": sum(m.alive for m in self.mechs)})
        return orig(self, t, by)
    arena.League._die = die
    for k in range(a.matches):
        seed = 1 + a.start + k
        sim = arena.League(cfg, world, seed, [("x", fac)] * 16, econ=True)
        sim._diag = []
        res = sim.run(480)
        surv = [m for m in sim.mechs if m.alive]
        rows.append({"deaths": sim._diag, "end_t": round(sim.t, 1), "survivors": len(surv),
                     "winner_cubes": max((r["stats"]["cubes"] for r in res if r["place"] == 1), default=0)})
    for r in rows:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
