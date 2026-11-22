"""Static map model for Mech Royale: terrain heights, solid prisms, line of sight and a walk grid.

Written for team Antalos (oval-pilot). Standard library only.
"""
import heapq
import json
import math
import os
from array import array

CELL = 2.0      # solid-prism raster resolution (m)
NAV = 4.0       # walk-grid resolution (m)
MECH_R = 2.5
MECH_H = 9.0


def _point_in_ring(px, py, ring):
    """Even-odd test against a flat [x0, y0, x1, y1, ...] polygon."""
    inside = False
    n = len(ring) // 2
    j = n - 1
    for i in range(n):
        xi, yi = ring[2 * i], ring[2 * i + 1]
        xj, yj = ring[2 * j], ring[2 * j + 1]
        if (yi > py) != (yj > py):
            xc = xi + (py - yi) * (xj - xi) / (yj - yi)
            if px < xc:
                inside = not inside
        j = i
    return inside


class World:
    def __init__(self, map_dir):
        self.ok = False
        try:
            self._load(map_dir)
            self.ok = True
        except Exception:  # missing map: the bot still plays with local steering only
            self.ok = False

    # ------------------------------------------------------------------ loading
    def _load(self, map_dir):
        base = os.path.join(map_dir, "v2")
        with open(os.path.join(base, "world.json")) as f:
            w = json.load(f)
        b = w["bounds"]
        self.x0, self.x1, self.y0, self.y1 = b["minX"], b["maxX"], b["minY"], b["maxY"]
        t = w["terrain"]
        self.tx0, self.ty0, self.tstep = t["minX"], t["minY"], t["step"]
        self.tnx, self.tny = t["nx"], t["ny"]
        scale = t.get("scale", 0.01)
        raw = array("h")
        with open(os.path.join(base, t.get("file", "terrain.i16")), "rb") as f:
            raw.frombytes(f.read())
        if raw.itemsize == 2 and array("h", [1]).tobytes() != b"\x01\x00":
            raw.byteswap()
        self.h = array("f", (v * scale for v in raw))
        # prism raster: lowest base and highest top of any solid covering a cell
        self.cnx = int((self.x1 - self.x0) / CELL) + 1
        self.cny = int((self.y1 - self.y0) / CELL) + 1
        n = self.cnx * self.cny
        self.top = array("f", [-1e9]) * n
        self.base = array("f", [1e9]) * n
        for p in w["prisms"]:
            ring, holes = p["ring"], p.get("holes") or []
            xs, ys = ring[0::2], ring[1::2]
            i0 = max(0, int((min(xs) - self.x0) / CELL))
            i1 = min(self.cnx - 1, int((max(xs) - self.x0) / CELL) + 1)
            j0 = max(0, int((min(ys) - self.y0) / CELL))
            j1 = min(self.cny - 1, int((max(ys) - self.y0) / CELL) + 1)
            for j in range(j0, j1 + 1):
                cy = self.y0 + (j + 0.5) * CELL
                for i in range(i0, i1 + 1):
                    cx = self.x0 + (i + 0.5) * CELL
                    if not _point_in_ring(cx, cy, ring):
                        continue
                    if any(_point_in_ring(cx, cy, hl) for hl in holes):
                        continue
                    c = j * self.cnx + i
                    if p["top"] > self.top[c]:
                        self.top[c] = p["top"]
                    if p["base"] < self.base[c]:
                        self.base[c] = p["base"]
        self._build_nav()

    # ------------------------------------------------------------------ queries
    def ground(self, x, y):
        fx = (x - self.tx0) / self.tstep
        fy = (y - self.ty0) / self.tstep
        i = min(max(int(fx), 0), self.tnx - 2)
        j = min(max(int(fy), 0), self.tny - 2)
        ax, ay = min(max(fx - i, 0.0), 1.0), min(max(fy - j, 0.0), 1.0)
        k = j * self.tnx + i
        h = self.h
        return (h[k] * (1 - ax) + h[k + 1] * ax) * (1 - ay) + (h[k + self.tnx] * (1 - ax) + h[k + self.tnx + 1] * ax) * ay

    def cell(self, x, y):
        i = int((x - self.x0) / CELL)
        j = int((y - self.y0) / CELL)
        if i < 0 or j < 0 or i >= self.cnx or j >= self.cny:
            return -1
        return j * self.cnx + i

    def solid_at(self, x, y, z):
        c = self.cell(x, y)
        if c < 0:
            return True
        return self.base[c] <= z <= self.top[c]

    def surface(self, x, y):
        """Height a mech stands on here (roof or terrain)."""
        g = self.ground(x, y)
        c = self.cell(x, y)
        if c >= 0 and self.base[c] <= g + 1.0:
            return max(g, self.top[c])
        return g

    def los(self, a, b, step=2.0):
        """Straight segment a->b clear of terrain and solids (trees ignored: they never stop shots)."""
        if not self.ok:
            return True
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        n = max(1, int(d / step))
        for k in range(1, n):
            f = k / n
            x, y, z = a[0] + dx * f, a[1] + dy * f, a[2] + dz * f
            if z < self.ground(x, y) - 0.2:
                return False
            c = self.cell(x, y)
            if c < 0 or self.base[c] <= z <= self.top[c]:
                return False
        return True

    def blocked(self, x, y, feet_z):
        """Would a mech with feet at feet_z hit something at (x, y)?"""
        if not self.ok:
            return False
        if x < self.x0 + 4 or x > self.x1 - 4 or y < self.y0 + 4 or y > self.y1 - 4:
            return True
        c = self.cell(x, y)
        if c < 0:
            return True
        if self.top[c] > feet_z + 1.2 and self.base[c] < feet_z + MECH_H:
            return True
        return self.ground(x, y) > feet_z + 1.6

    # ------------------------------------------------------------------ navigation
    def _build_nav(self):
        self.nnx = int((self.x1 - self.x0) / NAV) + 1
        self.nny = int((self.y1 - self.y0) / NAV) + 1
        free = bytearray(self.nnx * self.nny)
        gz = array("f", [0.0]) * (self.nnx * self.nny)
        for j in range(self.nny):
            y = self.y0 + (j + 0.5) * NAV
            for i in range(self.nnx):
                x = self.x0 + (i + 0.5) * NAV
                g = self.ground(x, y)
                k = j * self.nnx + i
                gz[k] = g
                ok = True
                for ox, oy in ((0, 0), (MECH_R, 0), (-MECH_R, 0), (0, MECH_R), (0, -MECH_R)):
                    c = self.cell(x + ox, y + oy)
                    if c < 0 or (self.top[c] > g + 1.2 and self.base[c] < g + MECH_H):
                        ok = False
                        break
                free[k] = 1 if ok else 0
        self.free, self.gz = free, gz

    def ncell(self, x, y):
        i = min(max(int((x - self.x0) / NAV), 0), self.nnx - 1)
        j = min(max(int((y - self.y0) / NAV), 0), self.nny - 1)
        return j * self.nnx + i

    def ncenter(self, k):
        return (self.x0 + (k % self.nnx + 0.5) * NAV, self.y0 + (k // self.nnx + 0.5) * NAV)

    def nearest_free(self, k, rmax=8):
        if self.free[k]:
            return k
        ci, cj = k % self.nnx, k // self.nnx
        for r in range(1, rmax + 1):
            for dj in range(-r, r + 1):
                for di in (-r, r) if abs(dj) != r else range(-r, r + 1):
                    i, j = ci + di, cj + dj
                    if 0 <= i < self.nnx and 0 <= j < self.nny and self.free[j * self.nnx + i]:
                        return j * self.nnx + i
        return None

    def straight_ok(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / (NAV * 0.5)))
        for k in range(n + 1):
            f = k / n
            if not self.free[self.ncell(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)]:
                return False
        return True


class PathSearch:
    """A* over the walk grid that can be advanced a little every decision (time-sliced)."""
    NB = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
          (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))

    def __init__(self, world, start, goal):
        self.w, self.start, self.goal = world, start, goal
        self.g = {start: 0.0}
        self.parent = {start: -1}
        gx, gy = goal % world.nnx, goal // world.nnx
        self.gx, self.gy = gx, gy
        self.open = [(self._h(start), start)]
        self.closed = set()
        self.done = False
        self.path = None

    def _h(self, k):
        nx = self.w.nnx
        return math.hypot(k % nx - self.gx, k // nx - self.gy)

    def step(self, budget):
        w = self.w
        nx, ny = w.nnx, w.nny
        free, gz = w.free, w.gz
        while self.open and budget > 0:
            budget -= 1
            _, k = heapq.heappop(self.open)
            if k in self.closed:
                continue
            if k == self.goal:
                self._finish(k)
                return
            self.closed.add(k)
            i, j = k % nx, k // nx
            gk = self.g[k]
            for di, dj, c in self.NB:
                ii, jj = i + di, j + dj
                if not (0 <= ii < nx and 0 <= jj < ny):
                    continue
                kk = jj * nx + ii
                if not free[kk] or kk in self.closed:
                    continue
                climb = gz[kk] - gz[k]
                if climb > 1.4 * c * NAV * 0.5:  # too steep to walk
                    continue
                ng = gk + c + max(0.0, climb) * 0.3
                if ng < self.g.get(kk, 1e18):
                    self.g[kk] = ng
                    self.parent[kk] = k
                    heapq.heappush(self.open, (ng + self._h(kk), kk))
        if not self.open:
            self.done = True

    def _finish(self, k):
        path = []
        while k != -1:
            path.append(self.w.ncenter(k))
            k = self.parent[k]
        path.reverse()
        self.path = path
        self.done = True
