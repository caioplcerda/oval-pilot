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
        cmd += exp.get("simargs", [])
        env = dict(os.environ, MR_FLAGS=exp.get("flags", "sneak"))
    out = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True).stdout
    key = '"means"' if exp["mode"] == "league" else '"place"'
    return exp["name"], [l for l in out.splitlines() if l.startswith("{") and key in l]


def decided(lines, exp):
    """Early stop: every variant is clearly better/worse (|d| >= k*se) or clearly flat (se < flat_se, |d| < flat_d)."""
    rows = [json.loads(l)["means"] for l in lines]
    n = len(rows)
    if n < exp["min_n"]:
        return False
    labs = list(rows[0])
    base = labs[0]
    k, flat_se, flat_d = exp.get("stop_k", 2.5), exp.get("flat_se", 0.10), exp.get("flat_d", 0.15)
    for lab in labs[1:]:
        if exp.get("compare") and lab not in exp["compare"]:
            continue
        d = [r[lab] - r[base] for r in rows]
        mu = sum(d) / n
        se = math.sqrt(sum((x - mu) ** 2 for x in d) / max(1, n - 1) / n)
        if not (abs(mu) >= k * se or (se < flat_se and abs(mu) < flat_d)):
            return False
    return True


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
    byname = {e["name"]: e for e in exps}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(os.environ.get("BATCH_WORKERS", os.cpu_count()))) as ex:
        futs = []
        owner = {}
        for t in tasks:
            fu = ex.submit(run_chunk, *t)
            futs.append(fu)
            owner[fu] = t[0]["name"]
        stopped = set()
        for i, f in enumerate(as_completed(futs)):
            if f.cancelled():
                continue
            name, lines = f.result()
            data[name] += lines
            e = byname[name]
            if name not in stopped and e["mode"] == "league" and e.get("min_n") and decided(data[name], e):
                stopped.add(name)
                n_cancel = sum(1 for fu in futs if owner[fu] == name and fu.cancel())
                print("early stop %s at n=%d (%d chunks cancelled)" % (name, len(data[name]), n_cancel), flush=True)
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
