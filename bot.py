"""Antalos Mech Royale bot (oval-pilot): an original mechfight/1 controller.

Design notes (all learned from our own experiments during the event):
- Arm first: rush the nearest laser/lightning; laser + lightning is the strongest loadout.
- Fight facing the threat (rear hits do 1.5x), lead gun shots, charge/release the laser on target,
  fire lightning inside its cone; boost-strafe while fighting.
- Retreat to cover and heal when hurt or outnumbered; reach the next zone circle early.
- Free-for-all detection: if other mechs die early without us, it is a free-for-all; then avoid fights we
  did not start until few mechs remain (practice house bots only die to us, so practice stays aggressive).
Standard library only; mechfight.py is the official starter-kit wrapper.
"""
import math
import os
import random
import sys
import time

import mechfight as mf
from world import World, PathSearch

TAU = 2 * math.pi
UPGRADES = ["plating", "armor", "nanites", "laser_damage", "laser_charge", "lightning_efficiency", "gun_rate",
            "gun_damage", "capacitor", "reactor", "servos", "jets", "gyros", "lightning_range", "gun_mag",
            "gun_velocity", "sensors", "lightning_chain", "laser_pierce", "mortar_reload", "mortar_velocity",
            "mortar_splash"]
UPGRADES_KILL = ["laser_damage", "laser_charge", "plating", "armor", "lightning_efficiency", "gun_rate", "gun_damage",
                 "nanites", "capacitor", "reactor", "lightning_range", "servos", "jets", "gyros", "gun_mag", "gun_velocity",
                 "sensors", "lightning_chain", "laser_pierce", "mortar_reload", "mortar_velocity", "mortar_splash"]
WANT = ("laser", "lightning")
THREAT_SOUNDS = {"gun", "laser", "laser_charge", "lightning", "mortar", "explosion", "step", "boost", "jet"}


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def knob(name, default):
    try:
        return float(os.environ.get("AB_" + name, default))
    except ValueError:
        return default


class Bot:
    name = "antalos"

    def __init__(self, hello):
        self.cfg = hello["config"]
        self.slot = hello.get("slot", -1)
        self.rng = random.Random(hello.get("seed", 0))
        self.w = World(hello.get("map", {}).get("dir", "/arena"))
        self.reach = self.cfg["loot"]["pickup_radius"]
        self.attackers = {}        # id -> last time it hit us
        self.hurt_t, self.hurt_bearing = -99.0, None
        self.kills = 0
        self.ffa = False
        self.picks = {}            # id -> (kind, pos) remembered weapon pickups
        self.crates = {}           # id -> pos
        self.sound = None          # (t, bearing)
        self.path, self.path_goal, self.search, self.search_goal = None, None, None, None
        self.path_i = 0
        self.strafe, self.strafe_until = 1, 0.0
        self.retreat = False
        self.cover, self.cover_t = None, -99.0
        self.stuck_t, self.climb_until = 0.0, -1.0
        self.detour, self.detour_until = None, -1.0
        self.scan = None
        self.home, self.home_t = None, -99.0
        self.foe_near_t = -99.0
        self.focus_id, self.focus_t = None, -99.0
        self.peek, self.peek_t = None, -99.0
        self.t0 = 0.0
        self.mode = "start"

    # ------------------------------------------------------------------ helpers
    def _late(self, ms):
        return (time.perf_counter() - self.t0) * 1000.0 > ms

    @staticmethod
    def _slot(me, kind):
        for i, w in enumerate(me["weapons"]):
            if w and w["kind"] == kind:
                return i, w
        return None, None

    def _pick_upgrade(self, offer):
        best, rank = 0, 1e9
        order = UPGRADES_KILL if (not self.ffa and knob("UPG_KILL", 0) > 0) else UPGRADES
        for i, ch in enumerate(offer["choices"]):
            r = order.index(ch.get("id")) if ch.get("id") in order else 99
            if r < rank:
                best, rank = i, r
        return best

    def _zone(self, obs, pos):
        z, t = obs["zone"], obs["t"]
        c, r = z["center"], z["radius"]
        if z["shrink_start"] <= t and z["shrink_end"] > z["shrink_start"]:
            f = min(1.0, (t - z["shrink_start"]) / (z["shrink_end"] - z["shrink_start"]))
            c = [c[0] + (z["next_center"][0] - c[0]) * f, c[1] + (z["next_center"][1] - c[1]) * f]
            r = r + (z["next_radius"] - r) * f
        nc, nr = z["next_center"], z["next_radius"]
        speed = obs["self"]["stats"].get("walk_speed", 11.7)
        margin = min(25.0, nr * 0.3)
        need = max(0.0, math.dist(pos[:2], nc) - (nr - margin))
        left = (z["shrink_start"] - t) if t < z["shrink_start"] else (z["shrink_end"] - t)
        outside = not obs["self"]["in_zone"] or math.dist(pos[:2], c) > r - 6
        go = outside or (need > 0 and need / speed + 15 > left)
        return {"c": c, "r": r, "nc": nc, "nr": nr, "go": go, "outside": outside, "need": need}

    def _inside_soon(self, zs, p):
        return math.dist(p[:2], zs["nc"]) < max(zs["nr"] - 10, 5) or (not zs["go"] and math.dist(p[:2], zs["c"]) < zs["r"] - 25)

    # ------------------------------------------------------------------ movement
    def _route(self, goal, pos, t):
        """Point to walk towards: the goal or the next waypoint of an A* route around buildings."""
        w = self.w
        if not w.ok or goal is None:
            return goal
        x, y = pos[0], pos[1]
        if pos[2] > w.ground(x, y) + 3 or math.hypot(goal[0] - x, goal[1] - y) < 8 or w.straight_ok(x, y, goal[0], goal[1]):
            self.path = self.search = None
            return goal
        gk = w.ncell(goal[0], goal[1])
        if self.path is not None and self.path_goal is not None and math.dist(w.ncenter(gk), w.ncenter(self.path_goal)) < 16:
            return self._follow(pos)
        if self.search is None or self.search_goal is None or math.dist(w.ncenter(gk), w.ncenter(self.search_goal)) >= 16:
            s, e = w.nearest_free(w.ncell(x, y)), w.nearest_free(gk)
            if s is None or e is None:
                return goal
            self.search, self.search_goal, self.path = PathSearch(w, s, e), gk, None
        if not self._late(25):
            self.search.step(2500)
        if self.search.done:
            self.path, self.path_goal, self.path_i = self.search.path, self.search_goal, 0
            self.search = None
            if self.path:
                return self._follow(pos)
        return goal

    def _follow(self, pos):
        p, x, y = self.path, pos[0], pos[1]
        best, bd = self.path_i, 1e18
        for k in range(max(0, self.path_i - 2), min(len(p), self.path_i + 12)):
            d = (p[k][0] - x) ** 2 + (p[k][1] - y) ** 2
            if d < bd:
                best, bd = k, d
        if bd > 30 ** 2:
            self.path = None
            return p[min(best + 1, len(p) - 1)]
        self.path_i = best
        tgt = p[min(best + 1, len(p) - 1)]
        for k in range(best + 2, min(len(p), best + 10)):
            if self.w.straight_ok(x, y, p[k][0], p[k][1]):
                tgt = p[k]
        return tgt

    def _steer(self, pos, dx, dy, t):
        """Pick a walkable heading close to (dx, dy)."""
        if t < self.detour_until and self.detour:
            dx, dy = self.detour
        if not self.w.ok:
            return dx, dy
        base = math.atan2(dy, dx)
        for off in (0, 0.4, -0.4, 0.8, -0.8, 1.3, -1.3, 1.9, -1.9):
            a = base + off
            ok = True
            for d in (3.0, 6.0):
                if self.w.blocked(pos[0] + math.cos(a) * d, pos[1] + math.sin(a) * d, pos[2]):
                    ok = False
                    break
            if ok:
                return math.cos(a), math.sin(a)
        return dx, dy

    def _cover_point(self, pos, threats, zs):
        """Nearby walkable spot whose head height cannot be seen from the threats' eyes."""
        w = self.w
        if not w.ok or not threats:
            return None
        eyes = [(e["pos"][0], e["pos"][1], e["pos"][2] + 8) for e in threats[:3]]
        away = math.atan2(sum(pos[1] - e["pos"][1] for e in threats[:3]), sum(pos[0] - e["pos"][0] for e in threats[:3]))
        best, bs = None, 1e18
        for k in range(16):
            a = k * TAU / 16
            for d in (10, 18, 28, 40, 55):
                px, py = pos[0] + math.cos(a) * d, pos[1] + math.sin(a) * d
                kk = w.ncell(px, py)
                if not w.free[kk]:
                    continue
                if math.dist((px, py), zs["c"]) > zs["r"] - 8:
                    continue
                head = (px, py, w.ground(px, py) + 7)
                seen = sum(1 for e in eyes if w.los(e, head, 3.0))
                sc = seen * 100 + d - 15 * math.cos(wrap(a - away))
                if sc < bs:
                    best, bs = (px, py), sc
                if self._late(30):
                    return best
        return best

    def _crate_goal(self, pos, zs):
        cands = [(math.dist(p[:2], pos[:2]), p) for p in self.crates.values() if p[2] < pos[2] + 8 and self._inside_soon(zs, p)]
        cands = [c for c in cands if 15 < c[0] < 260]
        return min(cands, key=lambda c: c[0])[1][:2] if cands else None

    def _home(self, obs, pos, zs, foes, t):
        """Free-for-all resting spot: inside the next circle, few open sight lines, away from known mechs."""
        if self.home is not None and t - self.home_t < 10 and math.dist(self.home, zs["nc"]) < zs["nr"] * 0.8:
            return self.home
        w = self.w
        if not w.ok:
            return zs["nc"]
        self.home_t = t
        best, bc = None, 1e18
        for k in range(14):
            a = self.rng.random() * TAU
            r = math.sqrt(self.rng.random()) * zs["nr"] * 0.6
            px, py = zs["nc"][0] + math.cos(a) * r, zs["nc"][1] + math.sin(a) * r
            kk = w.ncell(px, py)
            if not w.free[kk] or math.dist((px, py), zs["c"]) > zs["r"] - 15:
                continue
            head = (px, py, w.ground(px, py) + 8)
            open_dirs = 0
            for j in range(8):
                b = j * TAU / 8
                far = (px + math.cos(b) * 50, py + math.sin(b) * 50, head[2])
                if w.los(head, far, 4.0):
                    open_dirs += 1
            crowd = sum(1 for m in foes if math.dist(m["pos"][:2], (px, py)) < 120)
            cost = open_dirs * 12 + crowd * 40 + 0.2 * math.dist((px, py), pos[:2])
            if cost < bc:
                best, bc = (px, py), cost
            if self._late(28):
                break
        if best is not None:
            self.home = best
        return self.home or zs["nc"]

    # ------------------------------------------------------------------ dodge
    def _dodge(self, obs, me, foes):
        x, y, z = me["pos"]
        vx = vy = 0.0
        hit = False
        for m in foes:
            if not m.get("charging"):
                continue
            bear = math.atan2(y - m["pos"][1], x - m["pos"][0])
            if abs(wrap(m["aim"][0] - bear)) < 0.12 and math.dist(m["pos"][:2], (x, y)) < 285:
                vx += -math.sin(bear) * self.strafe
                vy += math.cos(bear) * self.strafe
                hit = True
        for p in obs["projectiles"]:
            if p.get("kind") != "gun":
                continue
            px, py, pz = p["pos"]
            qx, qy, qz = p["vel"]
            sp2 = qx * qx + qy * qy + qz * qz
            if sp2 < 1:
                continue
            rx, ry, rz = px - x, py - y, pz - (z + 4.5)
            tc = -(rx * qx + ry * qy + rz * qz) / sp2
            if 0.02 < tc < 0.5:
                mx, my, mz = rx + qx * tc, ry + qy * tc, rz + qz * tc
                if mx * mx + my * my + mz * mz < 3.6 ** 2:
                    h = math.hypot(qx, qy) or 1.0
                    side = 1.0 if (-qy * (x - px) + qx * (y - py)) >= 0 else -1.0
                    vx += -qy / h * side * 0.6
                    vy += qx / h * side * 0.6
                    hit = True
        if not hit or math.hypot(vx, vy) < 1e-6:
            return None
        n = math.hypot(vx, vy)
        return vx / n, vy / n

    # ------------------------------------------------------------------ main
    def act(self, obs):
        self.t0 = time.perf_counter()
        t = obs["t"]
        me = obs["self"]
        pos = me["pos"]
        x, y, z = pos
        st = me["stats"]
        hp = me["hp"] / max(1.0, me["max_hp"])
        energy = me["energy"]
        act = {"tick": obs["tick"]}
        muzzle = (x, y, z + st.get("muzzle_height", 7))
        eye = (x, y, z + st.get("eye_height", 8))

        for e in obs["events"]:
            ty = e["type"]
            if ty == "damaged" and e.get("by") is not None:
                self.attackers[e["by"]] = t
                self.hurt_t, self.hurt_bearing = t, e.get("bearing")
            elif ty == "kill":
                self.kills += 1
            elif ty in ("took", "take_failed"):
                self.picks.pop(e.get("id"), None)
        for s in obs["sounds"]:
            if s["kind"] in THREAT_SOUNDS and s["dist"] != "far":
                self.sound = (t, s["bearing"])
        if 16 - obs["alive"] - self.kills >= 1 and t < 100:
            self.ffa = True  # practice house bots only die to us; free-for-all mechs die early on their own
        if obs["offer"]:
            act["pick"] = self._pick_upgrade(obs["offer"])

        for p in obs["pickups"]:
            self.picks[p["id"]] = (p["kind"], p["pos"])
        for c in obs["crates"]:
            self.crates[c["id"]] = c["pos"]
        if self.w.ok and obs["tick"] % 10 == 0:
            seen_c = {c["id"] for c in obs["crates"]}
            for cid in [c for c, p in self.crates.items() if c not in seen_c and math.dist(p[:2], (x, y)) < 30]:
                self.crates.pop(cid, None)
            seen_p = {p["id"] for p in obs["pickups"]}
            for pid in [i for i, (k, p) in self.picks.items() if i not in seen_p and math.dist(p[:2], (x, y)) < 30]:
                self.picks.pop(pid, None)

        zs = self._zone(obs, pos)
        gi, gun = self._slot(me, "gun")
        li, laser = self._slot(me, "laser")
        zi, light = self._slot(me, "lightning")
        armed = laser is not None or light is not None

        # ---------------------------------------------------------- enemies & target
        foes = []
        for m in obs["mechs"]:
            if m["kind"] != "mech" or m["id"] == me["id"]:
                continue
            d = math.dist(m["pos"][:2], (x, y))
            sc = 1 + 0.05 * m.get("cubes", 0)
            ctr = (m["pos"][0], m["pos"][1], m["pos"][2] + 4.5 * sc)
            m = dict(m, d=d, ctr=ctr, rad=2.5 * sc)
            m["shoot"] = d < 285 and not (d > 120 and self._late(15)) and self.w.los(muzzle, ctr)
            foes.append(m)
        threats = [m for m in foes if m["shoot"] and m["d"] < 240]
        if any(m["d"] < knob("CALM_R", 150) for m in foes):
            self.foe_near_t = t
        calm = t - self.foe_near_t > knob("CALM_S", 4)
        target, best = None, 1e18
        for m in threats:
            s = m["d"] + 0.15 * m["hp"]
            if m["hp"] < 0.3 * m["max_hp"]:
                s -= 120
            if t - self.attackers.get(m["id"], -99) < 4:
                s -= 80
            if m["id"] == self.focus_id and t - self.focus_t < 3 and (self.ffa or knob("STICK_PRACTICE", 0) > 0):
                s -= knob("STICK", 100)  # focus fire helps in a free-for-all; in practice it cost points
            if s < best:
                target, best = m, s
        if target is not None and self.ffa and obs["alive"] > 2:
            m = target
            aimed_at_us = m.get("charging") and abs(wrap(m["aim"][0] - math.atan2(y - m["pos"][1], x - m["pos"][0]))) < 0.25
            if not (t - self.attackers.get(m["id"], -99) < 4 or m["d"] < knob("ENGAGE", 55)
                    or (m["hp"] < 0.3 * m["max_hp"] and m["d"] < 120 and hp > 0.5)
                    or (aimed_at_us and m["d"] < 120)):
                target = None  # free-for-all: let others fight; only answer who is on us

        if target is not None:
            self.focus_id, self.focus_t = target["id"], t
        if self.retreat and target is not None and t - self.attackers.get(target["id"], -99) > 4 and target["hp"] > 0.25 * target["max_hp"]:
            target = None  # healing: only shoot back at whoever is on us

        # NPC drones / crates to farm for cubes when calm
        farm = None
        if target is None and hp > knob("FARM_HP", 0.5) and not threats and (calm or not self.ffa):
            cands = []
            for n in obs["mechs"]:
                if n["kind"] == "npc":
                    d = math.dist(n["pos"][:2], (x, y))
                    if d < 200:
                        cands.append((d + 25, (n["pos"][0], n["pos"][1], n["pos"][2] + 1.75), n.get("vel", [0, 0, 0]), 1.8))
            for c in obs["crates"]:
                d = math.dist(c["pos"][:2], (x, y))
                if d < 150 and c["pos"][2] < z + 6:
                    cands.append((d, (c["pos"][0], c["pos"][1], c["pos"][2] + 1.2), [0, 0, 0], 1.4))
            cands.sort(key=lambda c: c[0])
            for c in cands[:3]:
                if self.w.los(muzzle, c[1]) and self._inside_soon(zs, c[1]):
                    farm = c
                    break

        # ---------------------------------------------------------- aim & fire
        fire = [False, False]
        aim_yaw, aim_pitch = me["aim"][0], 0.0
        cy, cp = me["aim"]
        aimed = None
        if target is not None:
            aimed = (target["ctr"], target.get("vel", [0, 0, 0]), target["d"], target["rad"])
        elif farm is not None:
            aimed = (farm[1], farm[2], math.dist(farm[1][:2], (x, y)), farm[3])
        if aimed is not None:
            ctr, vel, d, rad = aimed
            spd = gun["stats"]["speed"] if gun else 252.0
            px, py, pz = ctr
            for _ in range(3):
                tt = math.dist(muzzle, (px, py, pz)) / spd + 0.05
                px, py, pz = ctr[0] + vel[0] * tt, ctr[1] + vel[1] * tt, ctr[2] + max(-6, min(6, vel[2] * tt))
            g_yaw = math.atan2(py - muzzle[1], px - muzzle[0])
            g_pitch = math.atan2(pz - muzzle[2], math.hypot(px - muzzle[0], py - muzzle[1]))
            l_yaw = math.atan2(ctr[1] + vel[1] * 0.1 - muzzle[1], ctr[0] + vel[0] * 0.1 - muzzle[0])
            l_pitch = math.atan2(ctr[2] - muzzle[2], math.hypot(ctr[0] - muzzle[0], ctr[1] - muzzle[1]))
            tol = math.atan2(rad * knob("TOL", 1.0), max(d, 1.0)) + 0.006
            tolp = math.atan2(2.5, max(d, 1.0)) + 0.004
            aim_yaw, aim_pitch = g_yaw, g_pitch
            if laser is not None and d < laser["stats"].get("range", 280) - 5:
                full = laser["stats"].get("charge", 0.75)
                ch = laser.get("charge", 0) or 0
                if ch > 0:
                    aim_yaw, aim_pitch = l_yaw, l_pitch
                    on = abs(wrap(l_yaw - cy)) < tol and abs(l_pitch - cp) < tolp * 1.5
                    lethal = False
                    if target is not None and ch >= laser["stats"].get("min_charge", 0.15):
                        mf_ = laser["stats"].get("min_frac", 0.35)
                        dmg = laser["stats"].get("damage", 315) * (mf_ + (1 - mf_) * min(1.0, ch / full))
                        dmg *= 1 + 0.04 * min(me.get("cubes", 0), 10)
                        back = abs(wrap(target["aim"][0] - math.atan2(y - target["pos"][1], x - target["pos"][0]))) > math.pi / 2
                        if back:
                            dmg *= 1.5
                        lethal = dmg >= target["hp"] + 5
                    if ((ch >= full - 0.02 or lethal) and on) or ch > full + laser["stats"].get("hold_s", 2.0) - 0.3:
                        fire[li] = False  # release: the beam fires now
                    else:
                        fire[li] = True
                elif laser.get("cooldown", 0) <= 0.05:
                    fire[li] = True
            if gun is not None and d < gun["stats"].get("range", 230) - 3 and gun.get("reload", 0) <= 0 and gun.get("ammo", 1) > 0:
                if abs(wrap(g_yaw - cy)) < tol and abs(g_pitch - cp) < tolp:
                    fire[gi] = True
            if light is not None and d < light["stats"].get("range", 45) - 1 and energy > light["stats"].get("energy", 3) + 4:
                if abs(wrap(math.atan2(ctr[1] - y, ctr[0] - x) - cy)) < math.radians(light["stats"].get("cone_deg", 30)) * 0.4:
                    fire[zi] = True
        else:
            look = None
            if self.hurt_bearing is not None and t - self.hurt_t < 3:
                look = self.hurt_bearing
            elif foes:
                f = min(foes, key=lambda m: m["d"])
                look = math.atan2(f["pos"][1] - y, f["pos"][0] - x)
            elif self.sound and t - self.sound[0] < 2.5:
                look = self.sound[1]
            if look is None:
                self.scan = wrap((self.scan if self.scan is not None else cy) + 0.3)
                look = self.scan
            else:
                self.scan = None
            aim_yaw, aim_pitch = look, 0.0
            if gun and gun.get("reload", 0) <= 0 and gun.get("ammo", 12) < gun["stats"].get("mag", 12) * 0.5:
                act["reload"] = True
            if laser and (laser.get("charge", 0) or 0) > 0:
                fire[li] = bool(foes)

        # ---------------------------------------------------------- loot choice
        want = None
        held = [w["kind"] if w else None for w in me["weapons"]]
        for pid, (kind, pp) in self.picks.items():
            if kind not in WANT or kind in held or abs(pp[2] - z) > 25:
                continue
            d = math.dist(pp[:2], (x, y))
            lim = 260 if not armed else 140
            if d > lim or (not self._inside_soon(zs, pp) and d > 30):
                continue
            score = d - (40 if kind == "laser" else 0)
            if want is None or score < want[2]:
                want = (pid, pp, score, d)
        if want and want[3] < self.reach - 0.3 and abs(want[1][2] - z) < 3.8:
            if None in held:
                act["take"] = want[0]
            elif "mortar" in held:
                act["take"], act["drop"] = want[0], held.index("mortar")
            elif gi is not None and not (laser and (laser.get("charge", 0) or 0) > 0):
                act["take"], act["drop"] = want[0], gi
        cube = None
        for c in obs["cubes"]:
            d = math.dist(c["pos"][:2], (x, y))
            if d < 70 and abs(c["pos"][2] - z) < 4 and self._inside_soon(zs, c["pos"]) and (cube is None or d < cube[0]):
                cube = (d, c["pos"])

        # ---------------------------------------------------------- mode
        recent_hurt = t - self.hurt_t < 3
        many = len(threats) >= 3 or (len(threats) >= 2 and hp < 0.6)
        if self.retreat and (hp > knob("RECOVER", 0.85) or (t - self.hurt_t > 12 and hp > 0.7)):
            self.retreat = False
        if (hp < (knob("RETREAT_FFA", 0.5) if self.ffa else knob("RETREAT", 0.4)) and (threats or recent_hurt)) or (many and not (target and target["hp"] < 0.25 * target["max_hp"])):
            self.retreat = True
        goal, boost, mode = None, False, "roam"
        if zs["outside"]:
            mode, goal = "zone", zs["nc"]
            boost = energy > 25
        elif self.retreat and (threats or recent_hurt or self.cover is not None):
            mode = "cover"
            if self.cover is None or t - self.cover_t > 1.0:
                ths = threats or [m for m in foes][:3]
                if not ths and self.hurt_bearing is not None:
                    ths = [{"pos": [x + math.cos(self.hurt_bearing) * 100, y + math.sin(self.hurt_bearing) * 100, z]}]
                self.cover, self.cover_t = self._cover_point(pos, ths, zs), t
            goal = self.cover
            boost = energy > 30 and recent_hurt
        elif zs["go"]:
            mode, goal = "zone", zs["nc"]
            boost = zs["need"] > 60 and energy > 50
        elif target is None and t - self.hurt_t < 2.5 and self.hurt_bearing is not None and knob("HIDE", 1) > 0:
            mode = "hide"
            if self.cover is None or t - self.cover_t > 1.0:
                b = self.hurt_bearing
                ghost = [{"pos": [x + math.cos(b) * 90, y + math.sin(b) * 90, z]}]
                self.cover, self.cover_t = self._cover_point(pos, ghost, zs), t
            goal = self.cover
            boost = energy > 30
        elif not armed and want and (target is None or target["d"] > 45 or want[3] < 20):
            mode, goal = "arm", want[1][:2]
            boost = energy > (20 if t < 60 else 50)
        elif cube and cube[0] < knob("CUBE_FIGHT", 0) and hp > 0.3:
            mode, goal = "cube", cube[1][:2]  # grab dropped cubes even mid-fight when they are close
        elif target is not None:
            mode = "fight"
            d = target["d"]
            pref = 110 if laser else (26 if light else 60)
            if laser and light and d < 55:
                pref = 26
            if target["hp"] < 0.25 * target["max_hp"] and hp > 0.4:
                pref = min(pref, 35)
            if t > self.strafe_until:
                if self.rng.random() < 0.7:
                    self.strafe = -self.strafe
                self.strafe_until = t + 0.6 + self.rng.random() * 0.9
            a = math.atan2(target["pos"][1] - y, target["pos"][0] - x)
            radial = max(-1.0, min(1.0, (d - pref) / 30.0))
            mx = math.cos(a) * radial + math.cos(a + math.pi / 2) * 0.85 * self.strafe
            my = math.sin(a) * radial + math.sin(a + math.pi / 2) * 0.85 * self.strafe
            goal = (x + mx * 20, y + my * 20)
            if knob("PEEK", 1) > 0 and laser is not None and laser.get("cooldown", 0) > 0.6 and d > 50 and (laser.get("charge", 0) or 0) <= 0:
                if self.peek is None or t - self.peek_t > 1.5:
                    self.peek, self.peek_t = self._cover_point(pos, [target], zs), t
                if self.peek is not None and math.dist(self.peek, (x, y)) < 22:
                    goal = self.peek  # duck behind cover while the laser recharges
                    mode = "peek"
            boost = energy > knob("FIGHT_BOOST", 35) and not (laser and (laser.get("charge", 0) or 0) > 0)
        elif cube:
            mode, goal = "cube", cube[1][:2]
        elif want:
            mode, goal = "loot", want[1][:2]
            boost = want[3] > 40 and energy > 60 and not foes
        elif farm is not None:
            mode = "farm"
            fd = math.dist(farm[1][:2], (x, y))
            goal = farm[1][:2] if fd > 35 else None
        elif self.ffa and calm and hp > 0.6 and self.crates and obs["t"] < knob("ECON_T", 260) and self._crate_goal(pos, zs) is not None:
            mode, goal = "econ", self._crate_goal(pos, zs)
            boost = knob("ECON_BOOST", 1) > 0 and energy > 60 and math.dist(goal, (x, y)) > 50
        elif self.ffa:
            mode = "home"
            hp_ = self._home(obs, pos, zs, foes, t)
            if hp_ is not None and math.dist(hp_, (x, y)) > 4:
                goal = hp_
        else:
            mode = "roam"
            nc, nr = zs["nc"], zs["nr"]
            if self.crates and hp > 0.6 and not foes:
                cands = [(math.dist(p[:2], (x, y)), p) for p in self.crates.values()
                         if p[2] < z + 8 and self._inside_soon(zs, p)]
                if cands:
                    d, p = min(cands, key=lambda c: c[0])
                    if d > 20 and d < 260:
                        goal = p[:2]
            if goal is None and math.dist((x, y), nc) > max(nr * 0.5, 15):
                goal = nc
        if goal is not None and mode not in ("zone",) and zs["go"] and math.dist(goal[:2], zs["nc"]) > zs["nr"]:
            goal = zs["nc"]
        self.mode = mode

        # ---------------------------------------------------------- steering
        move = [0.0, 0.0]
        if goal is not None:
            way = self._route(goal, pos, t) if mode != "fight" else goal
            dx, dy = way[0] - x, way[1] - y
            dd = math.hypot(dx, dy)
            if dd > 1.0:
                sx, sy = self._steer(pos, dx / dd, dy / dd, t)
                full = math.hypot(goal[0] - x, goal[1] - y)
                k = 1.0 if full > 4 else max(0.3, full / 4)
                move = [sx * k, sy * k]
        dodge = self._dodge(obs, me, foes)
        if dodge is not None:
            move = [dodge[0] * 0.8 + move[0] * 0.2, dodge[1] * 0.8 + move[1] * 0.2]
            n = math.hypot(*move) or 1.0
            move = [move[0] / n, move[1] / n]
            boost = boost or energy > 25
        # quiet: under 5 m/s a mech makes no sound
        if mode in ("roam", "cube", "farm", "home", "econ") and not boost and dodge is None and (foes or (self.sound and t - self.sound[0] < 8)):
            q = 4.6 / max(1.0, st.get("walk_speed", 11.7))
            n = math.hypot(*move)
            if n > q:
                move = [move[0] / n * q, move[1] / n * q]

        # stuck: jump/jet over or take a detour
        speed = math.hypot(me["vel"][0], me["vel"][1])
        if math.hypot(*move) > 0.3 and speed < 2.0 and me["grounded"]:
            self.stuck_t += 0.1
        else:
            self.stuck_t = max(0.0, self.stuck_t - 0.05)
        jump = False
        if self.stuck_t > 0.7:
            self.stuck_t = 0.0
            self.path = None
            if energy > 35 and self.rng.random() < 0.6:
                self.climb_until = t + 2.0
            else:
                a = math.atan2(move[1], move[0]) + self.rng.choice((-1, 1)) * (1.2 + self.rng.random())
                self.detour, self.detour_until = (math.cos(a), math.sin(a)), t + 1.2
        if t < self.climb_until:
            if me["grounded"]:
                jump = True
            elif energy > 5:
                boost = True
        elif not me["grounded"] and mode != "zone":
            boost = False
        if boost and me["grounded"] and energy < 15:
            boost = False

        act["move"] = move
        act["aim"] = [wrap(aim_yaw), max(-0.69, min(1.29, aim_pitch))]
        act["fire"] = fire
        act["boost"] = bool(boost)
        act["jump"] = jump
        return act


if __name__ == "__main__":
    mf.run(Bot)
