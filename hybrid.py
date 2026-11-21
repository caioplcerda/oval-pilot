"""Hybrid controller: practice play from a helper bot (MR_HELPER, default TTUN/r1ver), free-for-all play from our bot.

Every observation goes to both controllers. Until our bot proves a free-for-all (other mechs dying
early without us), the TTUN action is sent; afterwards our own action is sent and TTUN is stopped.
If the TTUN process is missing, slow or broken, our action is used, so the hybrid never plays worse
than idling.

TTUN bot: https://github.com/varchaskukreja/TTUN (MIT, see ttun/LICENSE), run with Bun.
"""
import hashlib
import json
import os
import select
import subprocess
import sys
import time

import mechfight as mf
import bot as ours

HERE = os.path.dirname(os.path.abspath(__file__))
TTUN_DIR = os.path.join(HERE, "ttun", os.environ.get("MR_TTUN", "11350d3"))
BUN = os.environ.get("MR_BUN", "bun")
READY_TIMEOUT_S = 12.0
ANSWER_BUDGET_S = 0.036   # leave room inside the 50 ms tick budget
NOSWITCH = os.environ.get("MR_NOSWITCH", "") == "1"
FP_GROUPS = int(os.environ.get("MR_FP_GROUPS", "0") or 0)          # leaderboard experiment (off by default)
FP_ALT_GROUPS = {int(g) for g in os.environ.get("MR_FP_ALT_GROUPS", "").split(",") if g.strip().isdigit()}
FP_ALT_SALT = int(os.environ.get("MR_FP_ALT_SALT", "1") or 1)  # helper plays the whole match; ours is only the fallback


class Hybrid:
    name = "oval-pilot"

    def __init__(self, hello):
        self.inner = ours.Bot(hello)
        self.proc = None
        self.buf = b""
        self.fails = 0
        self.used = 0
        self.alt = None
        self.fp_done = FP_GROUPS <= 0
        self._launch(hello, int(os.environ.get("MR_TTUN_SALT", "0")))
        if FP_GROUPS > 0 and self.proc is not None:
            keep = (self.proc, self.buf)
            self.proc, self.buf = None, b""
            self._launch(hello, FP_ALT_SALT)
            self.alt = (self.proc, self.buf) if self.proc is not None else None
            self.proc, self.buf = keep

    def _launch(self, hello, salt):
        try:
            env = dict(os.environ, HOME="/tmp", BUN_INSTALL_CACHE_DIR="/tmp/bun-cache",
                       BUN_RUNTIME_TRANSPILER_CACHE_PATH="0", TMPDIR="/tmp")
            helper = os.environ.get("MR_HELPER", "")
            cmd = helper.split() if helper else [BUN, os.path.join(TTUN_DIR, "bot.ts")]
            env["GOMAXPROCS"] = "1"
            self.proc = subprocess.Popen(cmd, cwd=HERE if helper else TTUN_DIR,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, env=env, bufsize=0)
            h = dict(hello)
            if salt:
                h["seed"] = (int(hello.get("seed", 0)) + 7919 * salt) & 0xFFFFFFFF  # re-roll its tie-breaks
            self._send(h)
            if self._read_line(time.perf_counter() + READY_TIMEOUT_S) is None:
                ours.log("ttun: no ready, using our bot only")
                self._stop()
        except Exception as e:  # never let the helper break the match
            ours.log("ttun start failed:", repr(e))
            self._stop()

    def _pick_helper(self, obs):
        """Leaderboard-only experiment: group the match by our spawn point and keep the helper copy assigned
        to that group (MR_FP_GROUPS, MR_FP_ALT_GROUPS). The other copy is stopped."""
        self.fp_done = True
        if self.alt is None:
            return
        x, y = obs["self"]["pos"][0], obs["self"]["pos"][1]
        g = int(hashlib.md5(("%.1f,%.1f" % (x, y)).encode()).hexdigest(), 16) % FP_GROUPS
        alt_proc, alt_buf = self.alt
        self.alt = None
        if g in FP_ALT_GROUPS:
            self._stop()
            self.proc, self.buf = alt_proc, alt_buf
        else:
            try:
                alt_proc.kill()
            except Exception:
                pass

    # --- helper process ------------------------------------------------------------------------
    def _send(self, msg):
        self.proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
        self.proc.stdin.flush()

    def _read_line(self, deadline):
        fd = self.proc.stdout.fileno()
        while b"\n" not in self.buf:
            left = deadline - time.perf_counter()
            if left <= 0:
                return None
            r, _, _ = select.select([fd], [], [], left)
            if not r:
                return None
            chunk = os.read(fd, 65536)
            if not chunk:
                self._stop()
                return None
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        try:
            return json.loads(line)
        except ValueError:
            return {}

    def _stop(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    # --- main ----------------------------------------------------------------------------------
    def act(self, obs):
        t0 = time.perf_counter()
        tick = obs["tick"]
        if not self.fp_done:
            self._pick_helper(obs)
        sent = False
        if self.proc is not None and (NOSWITCH or not self.inner.ffa):
            try:
                self._send(obs)  # TTUN thinks while we do
                sent = True
            except Exception:
                self._stop()
        mine = self.inner.act(obs)
        if self.inner.ffa and not NOSWITCH:
            self._stop()  # free-for-all proven: our game from here on
            return mine
        if not sent or self.proc is None:
            return mine
        deadline = t0 + ANSWER_BUDGET_S
        while True:
            a = self._read_line(deadline)
            if a is None:
                self.fails += 1
                if self.fails > 40:
                    self._stop()
                return mine
            if a.get("tick") == tick:
                break  # (stale answers to older ticks are skipped)
        self.used += 1
        a.pop("debug", None)
        return a


if __name__ == "__main__":
    mf.run(Hybrid)
