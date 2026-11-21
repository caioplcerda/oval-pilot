"""Adapter so tools/sim.py can play the hybrid controller: --botfile tools/hybrid_simbot.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bot as _b  # noqa: E402
import hybrid as _h  # noqa: E402

World = _b.World
ARENA = os.path.join(ROOT, "arena")


class Bot(_h.Hybrid):
    def __init__(self, hello):
        h = dict(hello)
        h["map"] = {"dir": ARENA, "files": ["v2/world.json", "v2/terrain.i16"]}
        super().__init__(h)

    def __del__(self):
        self._stop()
