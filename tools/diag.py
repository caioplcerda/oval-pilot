"""Per-match diagnostics on the local sim: how and when the bot dies, stuck time, damage sources.

    uv run python tools/diag.py --matches 24 [--botfile other_bot.py] [--start 0]
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
ap.add_argument("--matches", type=int, default=24)
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--kit", default="..")
ap.add_argument("--botfile", default="")
ap.add_argument("--quiet", action="store_true")
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
tot = collections.Counter()
deaths = []
for k in range(args.matches):
    seed = 1 + args.start + k
    s = sim.Sim(cfg, w, seed, B.Bot)
    st = collections.Counter()
    od, oa = s.damage, s.bot.act

    def dm(t, by, amt, ev, od=od, s=s, st=st):
        if by is s.me:
            st["dmg_out"] += amt
        if t is s.me:
            st["dmg_in_bots"] += amt
        od(t, by, amt, ev)

    def act(o, oa=oa, s=s, st=st):
        a = oa(o)
        st["m_" + getattr(s.bot, "mode", "?")] += 1
        sp = math.hypot(o["self"]["vel"][0], o["self"]["vel"][1])
        if math.hypot(*a.get("move", [0, 0])) > 0.5 and sp < 1.5 and o["self"]["grounded"]:
            st["stuck_ticks"] += 1
        if not o["self"]["in_zone"]:
            st["outside_zone_ticks"] += 1
        return a

    s.damage, s.bot.act = dm, act
    r = s.run()
    cause = "survived" if s.me.alive else ("zone" if (s.t - s.me.last_dmg) > 0 and st["dmg_in_bots"] < 1 else "bots")
    # classify: zone if hp loss dominated by zone ticks right before death
    if not s.me.alive:
        cause = "zone" if st["outside_zone_ticks"] > 5 and s.zone_now()[1] < 400 and math.dist(s.me.pos[:2], s.zone_now()[0]) > s.zone_now()[1] else "bots"
    deaths.append((r["points"], round(r["t"]), cause))
    tot.update(st)
    tot["pts"] += r["points"]
    if not args.quiet:
        print(seed, r["points"], round(r["t"]), cause, {k2: round(v) for k2, v in st.items()})
n = args.matches
print("MEAN pts %.2f" % (tot["pts"] / n))
early = sum(1 for p, t, c in deaths if t < 60)
print("died <60s: %d/%d  <120s: %d  survived-to-end: %d  by zone: %d" % (
    early, n, sum(1 for p, t, c in deaths if t < 120), sum(1 for p, t, c in deaths if c == "survived"),
    sum(1 for p, t, c in deaths if c == "zone")))
tick_total = sum(v for k2, v in tot.items() if k2.startswith("m_")) or 1
print("mode share:", {k2[2:]: round(v / tick_total, 3) for k2, v in tot.items() if k2.startswith("m_")})
print("stuck share %.3f  outside-zone share %.3f" % (tot["stuck_ticks"] / tick_total, tot["outside_zone_ticks"] / tick_total))
print("dmg out/in per match: %.0f / %.0f" % (tot["dmg_out"] / n, tot["dmg_in_bots"] / n))
