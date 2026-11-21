"""Trace one simulated match: who hurts us, from how far, what the bot was doing.

    uv run python tools/trace.py --seed 37 [--botfile other_bot.py] [--every 5]
"""
import argparse
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
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--kit", default="..")
ap.add_argument("--botfile", default="")
ap.add_argument("--every", type=int, default=5, help="print every N decisions")
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
s = sim.Sim(cfg, w, args.seed, B.Bot)
oa = s.bot.act
n = [0]
hurt = {}
od = s.damage


def dm(t, by, amt, ev, od=od):
    if t is s.me:
        hurt[by.id] = hurt.get(by.id, 0) + amt
    od(t, by, amt, ev)


s.damage = dm


def act(o):
    a = oa(o)
    n[0] += 1
    if n[0] % args.every == 0 or hurt:
        me = s.me
        near = sorted((round(math.dist(m.pos[:2], me.pos[:2])), m.id, m.skill, "L" if m.weapons[1] else "g")
                      for m in s.mechs[1:] if m.alive)[:5]
        print("%5.1f hp %4d %-5s w=%s cubes=%d dmg=%s near=%s seen=%d" % (
            o["t"], me.hp, getattr(s.bot, "mode", "?") + str(getattr(s.bot, "dbg", "")), [w_["kind"] if w_ else None for w_ in me.weapons], me.cubes,
            {k: round(v) for k, v in hurt.items()}, near, len(o["mechs"])))
        hurt.clear()
    return a


s.bot.act = act
print(s.run())
