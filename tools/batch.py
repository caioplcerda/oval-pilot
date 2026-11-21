"""Background experiment queue: runs many configs over all cores (match-level tasks), writes results.

    python tools/batch.py exps.json results/<name>     # exps.json: [{"name":..,"mode":"league"|"practice"|"diag", ...}]
league:   {"entries": ["lab=SPEC=N", ...], "matches": 220}
practice: {"flags": "sneak,...", "matches": 440, "botfile": ""}
Writes <out>/<exp>.jsonl (one line per match) and <out>/SUMMARY.txt when all done.
"""
import json, math, os, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
CHUNK = 5


def run_chunk(exp, start, n):
    if exp["mode"] == "league":
        cmd = [PY, "tools/league.py", "--kit", ".", "--econ", "--matches", str(n), "--start", str(start)]
        for e in exp["entries"]:
            cmd += ["--entry", e]
        env = dict(os.environ)
    else:
        cmd = [PY, "tools/sim.py", "--kit", ".", "--matches", str(n), "--start", str(start)]
        if exp.get("botfile"):
            cmd += ["--botfile", exp["botfile"]]
        env = dict(os.environ, MR_FLAGS=exp.get("flags", "sneak"))
    out = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True).stdout
    key = '"means"' if exp["mode"] == "league" else '"place"'
    return exp["name"], [l for l in out.splitlines() if l.startswith("{") and key in l]


def summarize(exp, lines):
    rows = [json.loads(l) for l in lines]
    n = len(rows)
    if not n:
        return "%s: no data" % exp["name"]
    if exp["mode"] == "league":
        labs = list(rows[0]["means"])
        txt = ["%s  (league n=%d)" % (exp["name"], n)]
        for lab in labs:
            v = [r["means"][lab] for r in rows]
            mu = sum(v) / n
            se = math.sqrt(sum((x - mu) ** 2 for x in v) / max(1, n - 1) / n)
            txt.append("   %-12s %.2f (se %.2f)" % (lab, mu, se))
        b = labs[0]
        for lab in labs[1:]:
            d = [r["means"][lab] - r["means"][b] for r in rows]
            mu = sum(d) / n
            se = math.sqrt(sum((x - mu) ** 2 for x in d) / max(1, n - 1) / n)
            txt.append("   %-12s vs %s: %+.2f (se %.2f)%s" % (lab, b, mu, se, "  *" if abs(mu) > 2 * se else ""))
        return "\n".join(txt)
    v = [r["points"] for r in rows]
    mu = sum(v) / n
    se = math.sqrt(sum((x - mu) ** 2 for x in v) / max(1, n - 1) / n)
    return "%s  (practice n=%d flags=%s)  %.2f (se %.2f)" % (exp["name"], n, exp.get("flags"), mu, se)


def main():
    exps = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    tasks = []
    for e in exps:
        n = e.get("matches", 220)
        for s in range(0, n, CHUNK):
            tasks.append((e, e.get("seed0", 0) + s, min(CHUNK, n - s)))
    data = {e["name"]: [] for e in exps}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        futs = [ex.submit(run_chunk, *t) for t in tasks]
        for i, f in enumerate(as_completed(futs)):
            name, lines = f.result()
            data[name] += lines
            with open(os.path.join(out, name + ".jsonl"), "a") as fh:
                fh.write("".join(l + "\n" for l in lines))
            if i % 20 == 0:
                print("%d/%d chunks %.0fs" % (i + 1, len(tasks), time.time() - t0), flush=True)
    summ = "\n".join(summarize(e, data[e["name"]]) for e in exps)
    open(os.path.join(out, "SUMMARY.txt"), "w").write(summ + "\n")
    print(summ)
    print("done in %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
