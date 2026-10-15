
import json
import math
import os
import random
import sys
import time
import tkinter as tk
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------
W, H = 900, 640
HUD_H = 56
PLAY_TOP, PLAY_BOTTOM = 100, H - 140#!/usr/bin/env python3
"""
AMMO EMULATOR - shooting gallery
================================

The original Ammo Emulator was one trick: hold the trackpad click and the
Mac fires a haptic tick every 150 ms. This keeps that trick as the core
mechanic and wraps a game around it.

    HOLD CLICK   fire (one haptic tick per round, 150 ms apart)
    R            reload (Classic mode)
    P / Esc      pause
    M            back to the menu (from pause / game over)

Modes
    CLASSIC   30-round mag + 120 in reserve. Shoot the gold ammo crates to
              get 6 seconds of infinite ammo and a full mag.
    INFINITE  The original behaviour: unlimited ammo, pure score attack.

Run:     python3 ammo_emulator_game.py
Haptics: pip install pyobjc-framework-Cocoa   (macOS Force Touch trackpad;
         keep a finger resting on the trackpad while you hold the click)
Build:   pip install pyinstaller pyobjc-framework-Cocoa
         pyinstaller --windowed --name "Ammo Emulator" ammo_emulator_game.py
"""
COUNTER_Y = H - 84
GUN_X, GUN_Y = W / 2, H - 80

ROUND_TIME = 60.0
FIRE_INTERVAL = 0.15          # same 150 ms cadence as the original app
MAG_SIZE = 30
START_RESERVE = 120
RELOAD_TIME = 1.1
INF_TIME = 6.0                # seconds of infinite ammo per gold crate
INF_MAX = 12.0
COMBO_WINDOW = 2.5
SPREAD_MAX = 40.0             # px of bullet spread at full bloom
MAX_TARGETS = 7

SCORE_FILE = os.environ.get(
    "AMMO_EMULATOR_SCORES",
    os.path.join(os.path.expanduser("~"), ".ammo_emulator_scores.json"),
)

# Palette
BG_TOP, BG_BOT = "#0b0e1f", "#2a1b4d"
TEXT, DIM = "#e8ecff", "#8a8fb5"
ACCENT, MINT, GOLD = "#ff9f1c", "#7cffb2", "#ffd166"
RED, PURPLE, STEEL, TEAL = "#ff4d5e", "#b388ff", "#8d99ae", "#2ee6a6"
PANEL, PANEL_HI = "#171a33", "#242850"
WHITE = "#f5f5ff"

MONO = "Menlo"
SANS = "Arial"

KINDS = {
    #            radius  speed range   hp  points  spawn weight
    "normal": dict(r=34, speed=(130, 210), hp=1, pts=10, w=55, color=RED),
    "small":  dict(r=20, speed=(270, 350), hp=1, pts=25, w=20, color=PURPLE),
    "heavy":  dict(r=48, speed=(70, 110),  hp=4, pts=50, w=10, color=STEEL),
    "decoy":  dict(r=30, speed=(150, 220), hp=1, pts=-25, w=15, color=TEAL),
    "ammo":   dict(r=28, speed=(160, 190), hp=1, pts=0,  w=0,  color=GOLD),
}

MENU, PLAYING, OVER = "menu", "playing", "over"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def mix(c1, c2, t):
    """Blend hex colour c1 toward c2 by t (0..1)."""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def load_scores():
    try:
        with open(SCORE_FILE) as f:
            data = json.load(f)
        return {"classic": int(data.get("classic", 0)), "infinite": int(data.get("infinite", 0))}
    except Exception:
        return {"classic": 0, "infinite": 0}


def save_scores(scores):
    try:
        with open(SCORE_FILE, "w") as f:
            json.dump(scores, f)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Haptics (the heart of the original app)
# --------------------------------------------------------------------------
class Haptics:
    """Trackpad haptics via AppKit. Silently disables itself off macOS."""

    GENERIC, ALIGNMENT, LEVEL_CHANGE = 0, 1, 2

    def __init__(self):
        self.ok = False
        self._performer = None
        self._when = 0
        self._pattern = {}
        if sys.platform != "darwin":
            return
        try:
            import AppKit
            self._performer = AppKit.NSHapticFeedbackManager.defaultPerformer()
            self._pattern = {
                "generic": getattr(AppKit, "NSHapticFeedbackPatternGeneric", self.GENERIC),
                "align": getattr(AppKit, "NSHapticFeedbackPatternAlignment", self.ALIGNMENT),
                "level": getattr(AppKit, "NSHapticFeedbackPatternLevelChange", self.LEVEL_CHANGE),
            }
            self._when = getattr(AppKit, "NSHapticFeedbackPerformanceTimeNow", 1)
            self.ok = True
        except Exception:
            self.ok = False

    def _go(self, name):
        if not self.ok:
            return
        try:
            self._performer.performFeedbackPattern_performanceTime_(
                self._pattern[name], self._when)
        except Exception:
            self.ok = False

    def fire(self):    self._go("generic")   # every round
    def kill(self):    self._go("level")     # target destroyed
    def empty(self):   self._go("align")     # dry click / friendly hit
    def reload(self):  self._go("align")
    def pickup(self):  self._go("level")


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
@dataclass
class Target:
    kind: str
    x: float
    y0: float
    vx: float
    r: float
    hp: int
    maxhp: int
    amp: float
    freq: float
    phase: float
    age: float = 0.0
    flash: float = 0.0

    @property
    def y(self):
        return self.y0 + self.amp * math.sin(self.age * self.freq + self.phase)


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
class Game:
    def __init__(self, root, haptics=None):
        self.root = root
        self.haptics = haptics if haptics is not None else Haptics()
        self.c = tk.Canvas(root, width=W, height=H, bg=BG_TOP,
                           highlightthickness=0, cursor="arrow")
        self.c.pack()
        self.best = load_scores()

        self.state = MENU
        self.mode = "classic"
        self.paused = False
        self.mx, self.my = W / 2, H / 2 - 40
        self.mouse_down = False
        self.block_fire = False      # ignore a held click until it is released
        self.buttons = []
        self._cursor = "arrow"
        self.clock = 0.0             # animation clock, always running
        self.last = time.perf_counter()
        self.reset_round()

        self._build_background()
        self._bind()
        self.tick()

    # -- setup --------------------------------------------------------------
    def reset_round(self):
        self.time_left = ROUND_TIME
        self.score = 0
        self.mag = MAG_SIZE
        self.reserve = START_RESERVE
        self.reloading = False
        self.reload_t = 0.0
        self.fire_cd = 0.0
        self.inf_t = 0.0
        self.bloom = 0.0
        self.recoil = 0.0
        self.shake = 0.0
        self.flash_t = 0.0
        self.targets = []
        self.spawn_t = 0.2
        self.gold_t = random.uniform(8, 12)
        self.combo = 0
        self.combo_t = 0.0
        self.best_combo = 0
        self.shots = self.hits = self.kills = 0
        self.tracers, self.particles, self.floats = [], [], []
        self.banner, self.banner_t = "", 0.0
        self.new_best = False

    def _bind(self):
        r, c = self.root, self.c
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Motion>", self.on_motion)
        c.bind("<B1-Motion>", self.on_motion)
        r.bind("<KeyPress>", self.on_key)
        r.bind("<FocusOut>", self.on_focus_out)

    def _build_background(self):
        c = self.c
        steps = 64
        for i in range(steps):
            y0, y1 = i * H / steps, (i + 1) * H / steps + 1
            c.create_rectangle(0, y0, W, y1, fill=mix(BG_TOP, BG_BOT, i / (steps - 1)),
                               outline="", tags="bg")
        rnd = random.Random(7)
        for _ in range(70):
            x, y, s = rnd.uniform(0, W), rnd.uniform(0, H * 0.55), rnd.choice((1, 1, 2))
            c.create_oval(x, y, x + s, y + s, fill=mix("#ffffff", BG_TOP, rnd.uniform(.3, .8)),
                          outline="", tags="bg")
        # distant skyline
        pts = [0, COUNTER_Y]
        x = 0
        while x < W:
            w, h = rnd.randint(40, 90), rnd.randint(40, 150)
            pts += [x, COUNTER_Y - h, x + w, COUNTER_Y - h]
            x += w
        pts += [W, COUNTER_Y]
        c.create_polygon(pts, fill="#14122b", outline="", tags="bg")
        # bunting
        colors = [RED, GOLD, TEAL, PURPLE, ACCENT]
        for i in range(31):
            x = i * W / 30
            y = HUD_H + 10 + 10 * math.sin(i / 30 * math.pi * 4)
            c.create_oval(x - 5, y - 5, x + 5, y + 5, fill=colors[i % 5], outline="", tags="bg")
        # HUD bar + counter
        c.create_rectangle(0, 0, W, HUD_H, fill="#090b18", outline="", tags="bg")
        c.create_line(0, HUD_H, W, HUD_H, fill=PANEL_HI, tags="bg")
        c.create_rectangle(0, COUNTER_Y, W, H, fill="#120f22", outline="", tags="bg")
        c.create_line(0, COUNTER_Y, W, COUNTER_Y, fill=ACCENT, width=3, tags="bg")
        c.tag_lower("bg")

    # -- input --------------------------------------------------------------
    def on_motion(self, e):
        self.mx = min(max(e.x, 0), W)
        self.my = min(max(e.y, 0), H)

    def on_press(self, e):
        self.on_motion(e)
        self.mouse_down = True
        if self.state != PLAYING or self.paused:
            self.block_fire = True
            for x0, y0, x1, y1, action in self.buttons:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    action()
                    break

    def on_release(self, e):
        self.mouse_down = False
        self.block_fire = False

    def on_focus_out(self, e):
        if e.widget is self.root:
            self.mouse_down = False
            if self.state == PLAYING:
                self.paused = True

    def on_key(self, e):
        k = e.keysym.lower()
        if self.state == MENU:
            if k in ("1", "return", "space"):
                self.start("classic")
            elif k == "2":
                self.start("infinite")
        elif self.state == PLAYING:
            if k in ("p", "escape"):
                self.paused = not self.paused
                self.block_fire = self.mouse_down
            elif k == "r" and not self.paused:
                self.start_reload()
            elif k == "m" and self.paused:
                self.to_menu()
            elif k in ("return", "space") and self.paused:
                self.paused = False
                self.block_fire = self.mouse_down
        elif self.state == OVER:
            if k in ("return", "space"):
                self.start(self.mode)
            elif k in ("escape", "m"):
                self.to_menu()

    def set_cursor(self, name):
        if name != self._cursor:
            self._cursor = name
            self.c.config(cursor=name)

    # -- state changes ------------------------------------------------------
    def start(self, mode):
        self.mode = mode
        self.reset_round()
        self.state = PLAYING
        self.paused = False
        self.block_fire = self.mouse_down

    def to_menu(self):
        self.state = MENU
        self.paused = False

    def resume(self):
        self.paused = False
        self.block_fire = self.mouse_down

    def end_round(self):
        self.state = OVER
        self.new_best = self.score > self.best[self.mode]
        if self.new_best:
            self.best[self.mode] = self.score
            save_scores(self.best)

    # -- weapon -------------------------------------------------------------
    @property
    def infinite_active(self):
        return self.mode == "infinite" or self.inf_t > 0

    @property
    def multiplier(self):
        return min(4, 1 + self.combo // 4)

    @property
    def trigger(self):
        return (self.mouse_down and not self.block_fire
                and self.state == PLAYING and not self.paused)

    def start_reload(self):
        if (self.infinite_active or self.reloading or self.mag >= MAG_SIZE
                or self.reserve <= 0):
            return
        self.reloading = True
        self.reload_t = RELOAD_TIME
        self.haptics.reload()

    def try_fire(self):
        self.fire_cd = FIRE_INTERVAL
        if not self.infinite_active:
            if self.mag <= 0:
                if self.reserve > 0:
                    self.start_reload()
                else:
                    # Completely dry: you can still click a gold crate to grab it,
                    # otherwise the round could never recover.
                    for t in reversed(self.targets):
                        if t.kind == "ammo" and (self.mx - t.x) ** 2 + (self.my - t.y) ** 2 <= (t.r + 6) ** 2:
                            self.kill(t)
                            return
                    self.say("OUT OF AMMO - CLICK A GOLD CRATE")
                    self.haptics.empty()
                return
            self.mag -= 1
        self.shots += 1
        self.bloom = min(1.0, self.bloom + 0.12)
        self.recoil = 1.0
        self.flash_t = 0.05
        self.shake = min(6.0, self.shake + 2.2)
        self.haptics.fire()

        # hitscan with bloom spread
        spread = self.bloom * SPREAD_MAX
        ang, dist = random.uniform(0, math.tau), spread * math.sqrt(random.random())
        px, py = self.mx + math.cos(ang) * dist, self.my + math.sin(ang) * dist
        self.tracers.append([GUN_X + math.cos(self.gun_angle()) * 54,
                             GUN_Y + math.sin(self.gun_angle()) * 54, px, py, 0.07])
        self.resolve_shot(px, py)

        if not self.infinite_active and self.mag == 0 and self.reserve > 0:
            self.start_reload()

    def gun_angle(self):
        a = math.atan2(self.my - GUN_Y, self.mx - GUN_X)
        return max(-math.pi + 0.2, min(-0.2, a))

    def resolve_shot(self, px, py):
        for t in reversed(self.targets):          # front-most first
            rr = t.r + 2
            if (px - t.x) ** 2 + (py - t.y) ** 2 <= rr * rr:
                if t.kind != "decoy":
                    self.hits += 1
                t.hp -= 1
                t.flash = 0.08
                self.burst(px, py, KINDS[t.kind]["color"], 4, 140, 0.3)
                if t.hp <= 0:
                    self.kill(t)
                return True
        self.burst(px, py, DIM, 3, 60, 0.25)
        return False

    def kill(self, t):
        self.targets.remove(t)
        d = KINDS[t.kind]
        self.burst(t.x, t.y, d["color"], 16, 240, 0.6)
        self.shake = min(9.0, self.shake + 3)
        if t.kind == "decoy":
            self.combo = 0
            self.score = max(0, self.score + d["pts"])
            self.pop(t.x, t.y - 10, "%d FRIENDLY!" % d["pts"], RED)
            self.haptics.empty()
        elif t.kind == "ammo":
            self.inf_t = min(INF_MAX, self.inf_t + INF_TIME)
            self.mag, self.reserve = MAG_SIZE, min(self.reserve + 30, 999)
            self.reloading = False
            self.pop(t.x, t.y - 10, "INFINITE AMMO!", GOLD, 20)
            self.haptics.pickup()
            self.root.after(90, self.haptics.pickup)
        else:
            self.kills += 1
            self.combo += 1
            self.combo_t = COMBO_WINDOW
            self.best_combo = max(self.best_combo, self.combo)
            pts = d["pts"] * self.multiplier
            self.score += pts
            label = "+%d" % pts + (" x%d" % self.multiplier if self.multiplier > 1 else "")
            self.pop(t.x, t.y - 10, label, WHITE)
            self.root.after(40, self.haptics.kill)

    # -- effects ------------------------------------------------------------
    def burst(self, x, y, color, n, speed, life):
        for _ in range(n):
            a, s = random.uniform(0, math.tau), random.uniform(.2, 1) * speed
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s,
                                   life, life, color, random.uniform(2, 4)])

    def pop(self, x, y, text, color, size=16):
        self.floats.append([x, y, text, color, 0.9, 0.9, size])

    def say(self, text):
        self.banner, self.banner_t = text, 0.6

    # -- targets ------------------------------------------------------------
    def spawn(self, kind):
        d = KINDS[kind]
        r, side = d["r"], random.choice((-1, 1))
        lo, hi = PLAY_TOP + r + 10, PLAY_BOTTOM - r - 10
        y0 = random.uniform(lo, hi)
        amp = random.uniform(0, 15 if kind == "heavy" else 40)
        amp = max(0.0, min(amp, y0 - lo, hi - y0))
        self.targets.append(Target(
            kind=kind, x=-r - 6 if side == 1 else W + r + 6, y0=y0,
            vx=side * random.uniform(*d["speed"]), r=r, hp=d["hp"], maxhp=d["hp"],
            amp=amp, freq=random.uniform(1.5, 3.5), phase=random.uniform(0, math.tau)))

    def pick_kind(self):
        elapsed = ROUND_TIME - self.time_left
        kinds = [k for k in ("normal", "small", "heavy", "decoy")
                 if not (k == "decoy" and elapsed < 8)]
        return random.choices(kinds, [KINDS[k]["w"] for k in kinds])[0]

    # -- simulation ---------------------------------------------------------
    def update(self, dt):
        self.clock += dt
        if self.paused:
            return
        # cosmetic effects keep running on the game-over screen
        for p in self.particles:
            p[0] += p[2] * dt; p[1] += p[3] * dt; p[3] += 300 * dt; p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for f in self.floats:
            f[1] -= 40 * dt; f[4] -= dt
        self.floats = [f for f in self.floats if f[4] > 0]
        for tr in self.tracers:
            tr[4] -= dt
        self.tracers = [tr for tr in self.tracers if tr[4] > 0]
        self.shake = max(0.0, self.shake - 18 * dt)
        self.recoil = max(0.0, self.recoil - 9 * dt)
        self.flash_t = max(0.0, self.flash_t - dt)
        self.banner_t = max(0.0, self.banner_t - dt)

        if self.state != PLAYING:
            return

        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0
            self.end_round()
            return
        self.inf_t = max(0.0, self.inf_t - dt)
        if self.combo_t > 0:
            self.combo_t -= dt
            if self.combo_t <= 0:
                self.combo = 0

        if self.reloading:
            self.reload_t -= dt
            if self.reload_t <= 0:
                take = min(MAG_SIZE - self.mag, self.reserve)
                self.mag += take
                self.reserve -= take
                self.reloading = False
                self.haptics.reload()

        self.fire_cd -= dt
        trig = self.trigger
        if trig and self.fire_cd <= 0 and not self.reloading:
            self.try_fire()
        self.bloom = max(0.0, self.bloom - (0.2 if trig else 2.5) * dt)

        for t in self.targets:
            t.age += dt
            t.x += t.vx * dt
            t.flash = max(0.0, t.flash - dt)
        self.targets = [t for t in self.targets
                        if not (t.vx > 0 and t.x > W + t.r + 12)
                        and not (t.vx < 0 and t.x < -t.r - 12)]

        self.spawn_t -= dt
        if self.spawn_t <= 0 and len(self.targets) < MAX_TARGETS:
            elapsed = ROUND_TIME - self.time_left
            self.spawn(self.pick_kind())
            self.spawn_t = max(0.35, 0.95 - elapsed * 0.008) * random.uniform(0.7, 1.3)

        if self.mode == "classic":
            self.gold_t -= dt
            low = self.mag + self.reserve < 40
            if low:
                self.gold_t = min(self.gold_t, 3.0)
            if self.gold_t <= 0 and not any(t.kind == "ammo" for t in self.targets):
                self.spawn("ammo")
                self.gold_t = random.uniform(14, 20)

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last, 0.05)
        self.last = now
        try:
            self.update(dt)
            self.draw()
        finally:
            self.root.after(16, self.tick)

    # -- drawing ------------------------------------------------------------
    def txt(self, x, y, s, size=14, color=TEXT, anchor="center", family=MONO,
            tags="dyn", bold=True):
        return self.c.create_text(x, y, text=s, fill=color, anchor=anchor, tags=tags,
                                  font=(family, size, "bold" if bold else "normal"))

    def rrect(self, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.c.create_polygon(pts, smooth=True, tags=kw.pop("tags", "dyn"), **kw)

    def button(self, x0, y0, x1, y1, title, sub, action, hint="", best=None):
        hover = x0 <= self.mx <= x1 and y0 <= self.my <= y1
        self.rrect(x0, y0, x1, y1, 14, fill=PANEL_HI if hover else PANEL,
                   outline=ACCENT if hover else PANEL_HI, width=2)
        self.txt(x0 + 22, y0 + 28 if sub else (y0 + y1) / 2, title, 20,
                 ACCENT if hover else TEXT, "w")
        if sub:
            self.txt(x0 + 22, y0 + 58, sub, 11, DIM, "w", bold=False)
        if hint:
            self.txt(x1 - 20, y0 + 28 if sub else (y0 + y1) / 2, hint, 13, DIM, "e")
        if best is not None:
            self.txt(x1 - 70, y0 + 28 if sub else (y0 + y1) / 2, "BEST %d" % best, 12, GOLD, "e")
        self.buttons.append((x0, y0, x1, y1, action))

    def draw_star(self, x, y, r, rot, **kw):
        pts = []
        for i in range(10):
            rad = r if i % 2 == 0 else r * 0.5
            a = rot + i * math.pi / 5 - math.pi / 2
            pts += [x + math.cos(a) * rad, y + math.sin(a) * rad]
        return self.c.create_polygon(pts, **kw)

    def draw_target(self, kind, x, y, r, age=0.0, flash=0.0, hp=1, maxhp=1, tags=("dyn", "world")):
        c, f = self.c, flash > 0

        def oval(rr, fill, **kw):
            c.create_oval(x - rr, y - rr, x + rr, y + rr, fill=fill, outline=kw.pop("outline", ""),
                          tags=tags, **kw)

        if kind in ("normal", "small"):
            col = KINDS[kind]["color"]
            col = mix(col, "#ffffff", .65) if f else col
            oval(r + 3, "#0c0a18")
            oval(r, col); oval(r * .72, WHITE); oval(r * .46, col); oval(r * .2, WHITE)
        elif kind == "heavy":
            oval(r + 3, "#0c0a18")
            oval(r, mix(STEEL, "#ffffff", .6) if f else STEEL)
            oval(r * .78, "#5c677d"); oval(r * .5, RED); oval(r * .2, WHITE)
            for i in range(maxhp):
                px = x + (i - (maxhp - 1) / 2) * 14
                c.create_oval(px - 4, y - r - 14, px + 4, y - r - 6,
                              fill=RED if i < hp else "#2a2d45", outline="", tags=tags)
        elif kind == "decoy":
            oval(r + 3, "#0c0a18")
            oval(r, mix(TEAL, "#ffffff", .6) if f else TEAL)
            w = max(3, r * .3)
            c.create_line(x - r * .5, y, x + r * .5, y, width=w, fill=WHITE, tags=tags)
            c.create_line(x, y - r * .5, x, y + r * .5, width=w, fill=WHITE, tags=tags)
        elif kind == "ammo":
            pulse = 3 * math.sin(age * 6)
            c.create_oval(x - r - 8 - pulse, y - r - 8 - pulse, x + r + 8 + pulse, y + r + 8 + pulse,
                          outline=mix(GOLD, BG_BOT, .4), width=2, tags=tags)
            self.draw_star(x, y, r, age * 1.5, fill="#fff3c4" if f else GOLD,
                           outline="#b8860b", width=2, tags=tags)
            c.create_text(x, y, text="∞", fill="#5a3b00", tags=tags,
                          font=(SANS, int(r * .75), "bold"))

    def draw_world(self):
        c = self.c
        for t in self.targets:
            self.draw_target(t.kind, t.x, t.y, t.r, t.age, t.flash, t.hp, t.maxhp)
        for x0, y0, x1, y1, life in self.tracers:
            c.create_line(x0, y0, x1, y1, fill=mix("#fff1a8", BG_BOT, 1 - life / 0.07),
                          width=2, tags=("dyn", "world"))
        for x, y, vx, vy, life, total, col, r in self.particles:
            rr = r * life / total
            c.create_oval(x - rr, y - rr, x + rr, y + rr, fill=mix(col, BG_BOT, 1 - life / total),
                          outline="", tags=("dyn", "world"))
        for x, y, text, col, life, total, size in self.floats:
            self.txt(x, y, text, size, mix(col, BG_BOT, 1 - life / total), tags=("dyn", "world"))
        # turret
        ang = self.gun_angle() if self.state == PLAYING else -math.pi / 2
        length = 54 - self.recoil * 9
        tx, ty = GUN_X + math.cos(ang) * length, GUN_Y + math.sin(ang) * length
        tags = ("dyn", "world")
        c.create_line(GUN_X, GUN_Y, tx, ty, width=16, fill="#c9ccff", capstyle="round", tags=tags)
        c.create_line(GUN_X, GUN_Y, tx, ty, width=6, fill="#3a3d63", capstyle="round", tags=tags)
        c.create_oval(GUN_X - 28, GUN_Y - 28, GUN_X + 28, GUN_Y + 28, fill="#2b2d4a",
                      outline=ACCENT, width=3, tags=tags)
        c.create_oval(GUN_X - 9, GUN_Y - 9, GUN_X + 9, GUN_Y + 9, fill=ACCENT, outline="", tags=tags)
        if self.flash_t > 0:
            self.draw_star(tx + math.cos(ang) * 8, ty + math.sin(ang) * 8, 24, ang,
                           fill="#fff1a8", outline="", tags=tags)
        if self.shake > 0:
            c.move("world", random.uniform(-1, 1) * self.shake * .6,
                   random.uniform(-1, 1) * self.shake * .6)

    def draw_crosshair(self):
        c, x, y = self.c, self.mx, self.my
        col = GOLD if self.infinite_active else MINT
        spread = self.bloom * SPREAD_MAX
        gap = 5 + spread
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.create_line(x + dx * gap, y + dy * gap, x + dx * (gap + 10), y + dy * (gap + 10),
                          fill=col, width=2, tags="dyn")
        c.create_oval(x - 1.5, y - 1.5, x + 1.5, y + 1.5, fill=col, outline="", tags="dyn")
        if spread > 3:
            c.create_oval(x - spread, y - spread, x + spread, y + spread, outline=col, tags="dyn")

    def draw_hud(self):
        self.txt(20, 28, "SCORE", 10, DIM, "w")
        self.txt(20 + 52, 28, str(self.score), 24, TEXT, "w")
        t = self.time_left
        low = t <= 10 and int(self.clock * 4) % 2 == 0
        self.txt(W / 2, 22, "%04.1f" % t, 24, RED if low else TEXT)
        frac = t / ROUND_TIME
        self.c.create_rectangle(W / 2 - 80, 42, W / 2 + 80, 48, fill="#1d2040", outline="", tags="dyn")
        self.c.create_rectangle(W / 2 - 80, 42, W / 2 - 80 + 160 * frac, 48,
                                fill=RED if t <= 10 else ACCENT, outline="", tags="dyn")
        if self.combo > 1:
            self.txt(W - 20, 22, "COMBO %d  x%d" % (self.combo, self.multiplier), 16, GOLD, "e")
            w = 120 * max(0, self.combo_t) / COMBO_WINDOW
            self.c.create_rectangle(W - 20 - w, 42, W - 20, 48, fill=GOLD, outline="", tags="dyn")
        else:
            self.txt(W - 20, 28, "BEST %d" % self.best[self.mode], 12, DIM, "e")

        # ammo counter on the bar
        if self.infinite_active:
            pulse = 0.6 + 0.4 * math.sin(self.clock * 8)
            col = mix(BG_BOT, GOLD, pulse)
            self.txt(24, COUNTER_Y + 42, "∞", 34, col, "w", family=SANS)
            label = "INFINITE MODE" if self.mode == "infinite" else "INFINITE AMMO"
            self.txt(70, COUNTER_Y + 30, label, 14, GOLD, "w")
            if self.mode == "classic":
                frac = self.inf_t / INF_MAX
                self.c.create_rectangle(70, COUNTER_Y + 48, 70 + 200, COUNTER_Y + 54,
                                        fill="#2a2210", outline="", tags="dyn")
                self.c.create_rectangle(70, COUNTER_Y + 48, 70 + 200 * frac, COUNTER_Y + 54,
                                        fill=GOLD, outline="", tags="dyn")
        else:
            for i in range(MAG_SIZE):
                x = 24 + i * 12
                full = i < self.mag
                self.rrect(x, COUNTER_Y + 22, x + 7, COUNTER_Y + 52, 3,
                           fill=ACCENT if full else "#2a2440")
            if self.reloading:
                p = 1 - self.reload_t / RELOAD_TIME
                self.c.create_rectangle(24, COUNTER_Y + 10, 24 + 360, COUNTER_Y + 16,
                                        fill="#2a2440", outline="", tags="dyn")
                self.c.create_rectangle(24, COUNTER_Y + 10, 24 + 360 * p, COUNTER_Y + 16,
                                        fill=MINT, outline="", tags="dyn")
            self.txt(W - 24, COUNTER_Y + 30, "RESERVE", 10, DIM, "e")
            self.txt(W - 24, COUNTER_Y + 54, str(self.reserve), 24,
                     RED if self.reserve == 0 else TEXT, "e")
            if self.mag == 0 and self.reserve == 0 and not self.reloading:
                self.txt(GUN_X + 160, COUNTER_Y + 40, "EMPTY", 14, RED)
        if self.banner_t > 0:
            self.txt(W / 2, PLAY_BOTTOM + 30, self.banner, 14, RED)
        if self.mode == "classic" and not self.infinite_active and not self.reloading \
                and self.mag < 8 and self.reserve > 0 and self.state == PLAYING:
            self.txt(GUN_X + 160, COUNTER_Y + 40, "PRESS R", 14, MINT)

    def draw_menu(self):
        self.txt(W / 2 + 3, 113, "AMMO EMULATOR", 54, "#000000", family=SANS)
        self.txt(W / 2, 110, "AMMO EMULATOR", 54, ACCENT, family=SANS)
        self.txt(W / 2, 162, "HOLD CLICK  ·  FEEL EVERY ROUND", 14, DIM)
        self.button(170, 210, 730, 290, "CLASSIC",
                    "30-round mag, 120 in reserve. Shoot gold crates for infinite ammo.",
                    lambda: self.start("classic"), "[1]", self.best["classic"])
        self.button(170, 306, 730, 386, "INFINITE",
                    "The original Ammo Emulator: unlimited ammo, pure score attack.",
                    lambda: self.start("infinite"), "[2]", self.best["infinite"])

        legend = [("normal", "10"), ("small", "25"), ("heavy", "50 (4 hits)"),
                  ("decoy", "-25"), ("ammo", "∞ ammo")]
        x = 100
        for kind, label in legend:
            self.draw_target(kind, x, 450, 22 if kind != "heavy" else 26, self.clock,
                             tags=("dyn",), maxhp=4, hp=4)
            self.txt(x, 492, label, 11, DIM)
            x += 175
        self.txt(W / 2, 535, "R reload    P pause    Esc pause / back    M menu", 12, DIM, bold=False)
        if self.haptics.ok:
            self.txt(W / 2, 580, "TRACKPAD HAPTICS ON - rest a finger on the trackpad as you hold the click",
                     12, MINT)
        else:
            self.txt(W / 2, 580, "HAPTICS OFF - needs macOS + pyobjc-framework-Cocoa", 12, ACCENT)

    def draw_over(self):
        self.rrect(190, 110, 710, 470, 20, fill=PANEL, outline=ACCENT, width=3)
        self.txt(W / 2, 152, "TIME!", 34, ACCENT, family=SANS)
        self.txt(W / 2, 215, str(self.score), 54, WHITE)
        self.txt(W / 2, 264, "NEW BEST!" if self.new_best else "BEST %d" % self.best[self.mode],
                 16, GOLD if self.new_best else DIM)
        acc = 100 * self.hits / self.shots if self.shots else 0
        rows = [("KILLS", str(self.kills)), ("ACCURACY", "%d%%" % acc),
                ("SHOTS", str(self.shots)), ("BEST COMBO", str(self.best_combo))]
        for i, (k, v) in enumerate(rows):
            y = 300 + (i // 2) * 34
            self.txt(240 + (i % 2) * 230, y, k, 12, DIM, "w")
            self.txt(240 + (i % 2) * 230 + 200, y, v, 14, TEXT, "e")
        self.button(230, 390, 440, 440, "PLAY AGAIN", "", lambda: self.start(self.mode))
        self.button(460, 390, 670, 440, "MENU", "", self.to_menu)

    def draw_pause(self):
        self.rrect(250, 190, 650, 400, 20, fill=PANEL, outline=ACCENT, width=3)
        self.txt(W / 2, 235, "PAUSED", 30, ACCENT, family=SANS)
        self.button(280, 270, 620, 320, "RESUME", "", self.resume, "[P]")
        self.button(280, 332, 620, 382, "QUIT TO MENU", "", self.to_menu, "[M]")

    def draw(self):
        self.c.delete("dyn")
        self.buttons = []
        if self.state == MENU:
            self.set_cursor("arrow")
            self.draw_menu()
            return
        if self.state == OVER or self.paused:
            self.set_cursor("arrow")
        self.draw_world()
        self.draw_hud()
        if self.state == PLAYING and not self.paused:
            self.set_cursor("none")
            self.draw_crosshair()
        elif self.state == OVER:
            self.draw_over()
        elif self.paused:
            self.draw_pause()


def main():
    root = tk.Tk()
    root.title("Ammo Emulator")
    root.resizable(False, False)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry("%dx%d+%d+%d" % (W, H, (sw - W) // 2, max(0, (sh - H) // 3)))
    Game(root)
    root.lift()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
