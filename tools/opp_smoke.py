"""Smoke-test external bots inside the league sim: python tools/opp_smoke.py <opps_dir> <name> ..."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import arena

base, names = sys.argv[1], sys.argv[2:]
cfg = arena.load_cfg(".")
ours = arena.make_factory("bot:bot.py?sneak", ".")
world = next(iter(arena._MODS.values()))._shared[0]
for name in names:
    d = os.path.join(base, name)
    m = re.search(r'(?:ENTRYPOINT|CMD)\s*\[(.*)\]', open(os.path.join(d, "Dockerfile")).read())
    parts = [x.strip().strip('"') for x in m.group(1).split(",")]
    entry = [x for x in parts if x.endswith(".py")]
    if not entry:
        print(name, "SKIP no .py entry"); continue
    rel = re.sub(r"^/(bot|app)/", "", entry[0])
    spec = "proc:%s:%s" % (os.path.abspath(d), rel)
    try:
        sim = arena.League(cfg, world, 1, [("opp", arena.make_factory(spec, "."))] + [("ours", ours)] * 15, econ=True)
        pb = sim.bots[0]
        res = sim.run(90)
        r = [x for x in res if x["label"] == "opp"][0]
        print(name, "OK" if getattr(pb, "ok", 0) > 0.9 * max(1, getattr(pb, "n", 0)) else "BAD",
              "answers %d/%d alive_s %s" % (getattr(pb, "ok", 0), getattr(pb, "n", 0), r["alive_s"]), "SPEC", spec, flush=True)
    except Exception as e:
        print(name, "ERR", repr(e)[:120], flush=True)
    finally:
        arena.close_procs()
