"""Profile the first minute of many simulated matches: arming time, who deals the damage, causes of early death.

    uv run python tools/early.py --matches 60 [--botfile other_bot.py] [--horizon 60]
"""
import argparse
import collections
import gzip
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import sim  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--matches", type=int, default=60)
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--horizon", type=float, default=60.0)
ap.add_argument("--kit", default="..")
ap.add_argument("--botfile", default="")
args = ap.parse_args()
B = sim.B
if args.botfile:
    spec = importlib.util.spec_from_file_location("botmod_alt", args.botfile)
    B = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(args.botfile)))
    spec.loader.exec_module(B)
    sim.B = B
cfg = json.loads(gzip.open(os.path.join(args.kit, "check", "stream.jsonl.gz"), "rt").readline())["config"]
w = B.World(os.path.join(args.kit, "arena"))
rows = []
for k in range(args.matches):
    s = sim.Sim(cfg, w, 1 + args.start + k, B.Bot)
    by_tier = collections.Counter()
    armed_at = [None]
    first_hit = [None]
    od, oa = s.damage, s.bot.act

    def dm(t, by, amt, ev, od=od, s=s, by_tier=by_tier, first_hit=first_hit):
        if t is s.me:
            by_tier[by.skill] += amt
            if first_hit[0] is None:
                first_hit[0] = s.t
        od(t, by, amt, ev)

    def act(o, oa=oa, s=s, armed_at=armed_at):
        a = oa(o)
        if armed_at[0] is None and any(wp and wp["kind"] != "gun" for wp in s.me.weapons):
            armed_at[0] = s.t
        return a

    s.damage, s.bot.act = dm, act
    r = s.run(max_t=args.horizon)
    rows.append({"alive": s.me.alive, "t": s.t, "armed": armed_at[0], "first_hit": first_hit[0], "by": dict(by_tier),
                 "w": [x["kind"] if x else None for x in s.me.weapons], "kills": r["kills"]})

n = len(rows)
dead = [r for r in rows if not r["alive"]]
print("matches %d  died within %ds: %d (%.0f%%)" % (n, args.horizon, len(dead), 100 * len(dead) / n))
armed_dead = sum(1 for r in dead if r["armed"] is not None)
print("  of the early deaths: armed (laser/lightning/mortar) at death %d, gun-only %d" % (armed_dead, len(dead) - armed_dead))
at = sorted(r["armed"] for r in rows if r["armed"] is not None)
print("armed within horizon: %d/%d, median arming time %s" % (len(at), n, round(at[len(at) // 2], 1) if at else "-"))
fh = sorted(r["first_hit"] for r in rows if r["first_hit"] is not None)
print("first damage taken: median %s s" % (round(fh[len(fh) // 2], 1) if fh else "-"))
tier = collections.Counter()
for r in dead:
    for sk, v in r["by"].items():
        tier[sk] += v
tot = sum(tier.values()) or 1
print("damage on early deaths by attacker noise tier:", {k2: "%.0f%%" % (100 * v / tot) for k2, v in sorted(tier.items())})
print("early-death times:", sorted(round(r["t"]) for r in dead))
print("kills before death (early deaths): mean %.2f" % (sum(r["kills"] for r in dead) / max(1, len(dead))))
