import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass, field
import math
import random
import time


@dataclass
class Track:
    track_id: str
    iff: str
    alt: float
    hdg: float
    spd: float
    nctr: str
    x_km: float
    y_km: float
    vector_len: float = 18.0
    damaged: bool = False
    damage_age: float = 0.0
    descent_rate: float = 18.0
    ecm: bool = False
    ecm_strength: float = 0.0
    ecm_phase: float = field(default_factory=lambda: random.random() * 360.0)
    evading: bool = False
    evasion_timer: float = 0.0
    evasion_cooldown: float = 0.0
    evasion_phase: float = field(default_factory=lambda: random.random() * math.tau)
    evasion_turn_dir: int = field(default_factory=lambda: random.choice([-1, 1]))
    lock_pressure: float = 0.0


@dataclass
class Missile:
    missile_id: str
    target_id: str
    x_km: float
    y_km: float
    hdg: float
    launch_mode: str = "PPI 360"
    spd: float = 1400.0
    max_spd: float = 4300.0
    accel: float = 700.0
    burn_time: float = 7.5
    drag: float = 70.0
    max_turn_rate: float = 62.0
    nav_constant: float = 4.0
    seeker_limit: float = 65.0
    proximity_radius: float = 3.8
    age: float = 0.0
    max_age: float = 38.0
    last_los: float | None = None
    guidance_lost: bool = False
    lost_time: float = 0.0
    closest_approach: float = 9999.0
    miss_reason: str = ""
    trail: list = field(default_factory=list)


class RadarSim:
    def __init__(self, root):
        self.root = root
        self.root.title("Cold War CRT Radar Simulator - Enhanced FCS / PN Missiles / Evasion")
        self.root.geometry("1200x780")

        self.canvas_w = 820
        self.canvas_h = 740
        self.cx = self.canvas_w / 2
        self.cy = self.canvas_h / 2
        self.radius = 300

        self.range_steps_km = [50, 100, 150, 250, 400]
        self.max_range_km = 250
        self.sweep_angle = 0.0
        # Unbounded sweep phase prevents sector modes from snapping when the 360° sweep wraps.
        self.sweep_phase = 0.0
        self.sweep_speed_deg = 85.0
        self.running = True
        self.speed_scale = 35.0
        self.theme = "green"
        self.track_font_size = 8
        self.grid_font_size = 10
        self.major_font_size = 12
        self.last_time = time.time()
        self.tracks = []
        self.missiles = []
        self.locked_track_id = None
        self.last_lock_flash = 0.0
        self.lock_reacquire_delay = 0.0
        self.missile_counter = 0
        self.missile_ammo = 8
        self.max_missile_ammo = 8
        self.missile_cooldown = 0.0
        self.missile_reload_cooldown = 0.0
        # 1980s-ish guided missile model for video/simulation purposes.
        # Uses boosted flight, seeker limits, and proportional-navigation style lead pursuit.
        self.missile_launch_speed_kmh = 1400.0
        self.missile_max_speed_kmh = 4300.0
        self.missile_accel_kmh_s = 700.0
        self.missile_burn_time_s = 7.5
        self.missile_drag_kmh_s = 70.0
        self.missile_max_turn_rate_deg = 62.0
        self.missile_nav_constant = 4.0
        self.missile_seeker_limit_deg = 65.0
        self.missile_proximity_radius_km = 3.8
        self.missile_trail_points = 64
        self.kills = 0
        self.misses = 0
        self.shots_fired = 0

        self.mode_var = tk.StringVar(value="PPI 360")
        self.fcs_state_var = tk.StringVar(value="STANDBY")
        self.fcs_master_arm = tk.BooleanVar(value=False)
        self.show_track_labels = tk.BooleanVar(value=True)
        self.show_readable_scale = tk.BooleanVar(value=True)
        self.show_lead_cue = tk.BooleanVar(value=True)
        self.global_ecm = tk.BooleanVar(value=False)
        self.ecm_mode_var = tk.StringVar(value="SPOT")
        self.ecm_strength_var = tk.DoubleVar(value=0.55)
        self.target_ai_evasion = tk.BooleanVar(value=True)
        self.lock_breaks_enabled = tk.BooleanVar(value=True)

        self.colors = {
            "green": {
                "bg": "#020702",
                "grid": "#0b5f2a",
                "dim": "#063817",
                "bright": "#39ff88",
                "text": "#7dffb1",
                "scanline": "#031206",
                "warn": "#b6ff5f",
            },
            "amber": {
                "bg": "#080502",
                "grid": "#704b00",
                "dim": "#3d2900",
                "bright": "#ffbf3d",
                "text": "#ffd27a",
                "scanline": "#160e00",
                "warn": "#fff0a0",
            },
        }

        self.build_ui()
        self.root.bind("<Return>", self.lock_nearest_track_event)
        self.root.bind_all("<KeyPress-space>", self.fire_missile_key_event, add="+")
        self.root.bind("g", lambda event=None: self.set_theme("green"))
        self.root.bind("a", lambda event=None: self.set_theme("amber"))
        self.add_demo_tracks()
        self.animate()

    # ---------------------------- UI ----------------------------
    def build_ui(self):
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(main, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Button-1>", self.select_track_with_mouse)

        panel_shell = ttk.Frame(main, width=350)
        panel_shell.pack(side="right", fill="y", padx=10, pady=10)
        panel_shell.pack_propagate(False)

        panel_canvas = tk.Canvas(panel_shell, highlightthickness=0, borderwidth=0, width=326)
        self.panel_canvas = panel_canvas
        panel_scroll = ttk.Scrollbar(panel_shell, orient="vertical", command=panel_canvas.yview)
        panel = ttk.Frame(panel_canvas)
        panel_window = panel_canvas.create_window((0, 0), window=panel, anchor="nw")
        panel_canvas.configure(yscrollcommand=panel_scroll.set)

        def _update_scroll_region(event=None):
            panel_canvas.configure(scrollregion=panel_canvas.bbox("all"))

        def _fit_panel_width(event):
            panel_canvas.itemconfigure(panel_window, width=event.width)

        def _on_mousewheel(event):
            # Smooth-enough wheel scrolling that still works when the pointer is over
            # buttons, sliders, entries, or labels inside the menu.
            bbox = panel_canvas.bbox("all")
            if not bbox:
                return
            content_h = bbox[3] - bbox[1]
            if content_h <= max(1, panel_canvas.winfo_height()):
                return

            delta = getattr(event, "delta", 0)
            if delta:
                steps = -1 if delta > 0 else 1
                # Trackpads sometimes send small deltas; mouse wheels often send 120.
                if abs(delta) >= 240:
                    steps *= max(1, int(abs(delta) / 120))
            else:
                steps = 1 if getattr(event, "num", None) == 5 else -1
            panel_canvas.yview_scroll(steps * 3, "units")
            return "break"

        def _bind_wheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel, add="+")
            widget.bind("<Button-4>", _on_mousewheel, add="+")
            widget.bind("<Button-5>", _on_mousewheel, add="+")
            for child in widget.winfo_children():
                _bind_wheel_recursive(child)

        panel.bind("<Configure>", _update_scroll_region)
        panel_canvas.bind("<Configure>", _fit_panel_width)
        panel_canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
        panel_canvas.bind("<Button-4>", _on_mousewheel, add="+")
        panel_canvas.bind("<Button-5>", _on_mousewheel, add="+")
        panel_canvas.pack(side="left", fill="both", expand=True)
        panel_scroll.pack(side="right", fill="y")

        ttk.Label(panel, text="Radar Mode").pack(anchor="w")
        modes = [
            "PPI 360",
            "RWS",
            "TWS",
            "SECTOR 120",
            "B-SCOPE",
            "E-SCOPE",
            "STT LOCK",
            "FCS",
            "ECM MONITOR",
            "ACM BORESIGHT",
            "RAW CRT",
        ]
        ttk.Combobox(
            panel,
            textvariable=self.mode_var,
            values=modes,
            state="readonly",
            width=22,
        ).pack(anchor="w", pady=(0, 6))

        theme_frame = ttk.LabelFrame(panel, text="CRT Theme")
        theme_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(theme_frame, text="Green CRT   [G]", command=lambda: self.set_theme("green")).pack(side="left", expand=True, fill="x", padx=6, pady=6)
        ttk.Button(theme_frame, text="Amber CRT   [A]", command=lambda: self.set_theme("amber")).pack(side="left", expand=True, fill="x", padx=6, pady=6)

        fcs_frame = ttk.LabelFrame(panel, text="FCS / Lock Control")
        fcs_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(fcs_frame, text="Master Arm", variable=self.fcs_master_arm).pack(anchor="w", padx=6, pady=2)
        ttk.Checkbutton(fcs_frame, text="Lead cue", variable=self.show_lead_cue).pack(anchor="w", padx=6, pady=2)
        ttk.Button(fcs_frame, text="Lock Nearest", command=self.lock_nearest_track).pack(fill="x", padx=6, pady=2)
        ttk.Button(fcs_frame, text="Lock Next", command=self.lock_next_track).pack(fill="x", padx=6, pady=2)
        ttk.Button(fcs_frame, text="Fire Missile", command=self.fire_missile).pack(fill="x", padx=6, pady=2)
        ttk.Button(fcs_frame, text="Reload Missiles", command=self.reload_missiles).pack(fill="x", padx=6, pady=2)
        ttk.Button(fcs_frame, text="Clear Lock", command=self.clear_lock).pack(fill="x", padx=6, pady=(2, 6))

        ecm_frame = ttk.LabelFrame(panel, text="ECM / Countermeasures")
        ecm_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(ecm_frame, text="Global ECM noise", variable=self.global_ecm).pack(anchor="w", padx=6, pady=2)
        ttk.Label(ecm_frame, text="ECM type").pack(anchor="w", padx=6)
        ttk.Combobox(
            ecm_frame,
            textvariable=self.ecm_mode_var,
            values=["SPOT", "BARRAGE", "CHAFF"],
            state="readonly",
            width=14,
        ).pack(anchor="w", padx=6, pady=(0, 4))
        ttk.Label(ecm_frame, text="ECM strength").pack(anchor="w", padx=6)
        ttk.Scale(ecm_frame, from_=0.0, to=1.0, variable=self.ecm_strength_var, orient="horizontal").pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(ecm_frame, text="ECM on Locked Track", command=self.ecm_on_locked_track).pack(fill="x", padx=6, pady=2)
        ttk.Button(ecm_frame, text="ECM on All Tracks", command=self.ecm_on_all_tracks).pack(fill="x", padx=6, pady=2)
        ttk.Button(ecm_frame, text="Clear ECM", command=self.clear_ecm).pack(fill="x", padx=6, pady=(2, 6))

        defense_frame = ttk.LabelFrame(panel, text="Target AI / Evasion")
        defense_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(defense_frame, text="Targets evade locks/missiles", variable=self.target_ai_evasion).pack(anchor="w", padx=6, pady=2)
        ttk.Checkbutton(defense_frame, text="Allow radar lock breaks", variable=self.lock_breaks_enabled).pack(anchor="w", padx=6, pady=(2, 6))

        ttk.Label(panel, text="Track Setup").pack(anchor="w", pady=(0, 8))
        self.entries = {}

        fields = [
            ("iff", "IFF", "UNKNOWN"),
            ("alt", "ALT", "120"),
            ("hdg", "HDG", "275"),
            ("spd", "SPD", "420"),
            ("nctr", "NCTR", "MiG-29"),
            ("range", "Range km", "155"),
            ("bearing", "Bearing deg", "060"),
        ]

        form = ttk.Frame(panel)
        form.pack(fill="x")
        ttk.Label(form, text="TRACK").pack(anchor="w")
        ttk.Label(form, text="AUTO / random unique ID", foreground="#666666").pack(anchor="w", pady=(0, 5))
        for key, label, default in fields:
            ttk.Label(form, text=label).pack(anchor="w")
            e = ttk.Entry(form, width=24)
            e.insert(0, default)
            e.pack(anchor="w", pady=(0, 5))
            self.entries[key] = e

        ttk.Button(panel, text="Add Track", command=self.add_track_from_ui).pack(fill="x", pady=3)
        ttk.Button(panel, text="Add Demo Tracks", command=self.add_demo_tracks).pack(fill="x", pady=3)
        ttk.Button(panel, text="Clear Tracks", command=self.clear_tracks).pack(fill="x", pady=3)
        ttk.Button(panel, text="Pause / Resume", command=self.toggle_running).pack(fill="x", pady=3)

        ttk.Separator(panel).pack(fill="x", pady=10)

        range_frame = ttk.LabelFrame(panel, text="Readable Display")
        range_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(range_frame, text="Large range / angle labels", variable=self.show_readable_scale).pack(anchor="w", padx=6, pady=2)
        ttk.Checkbutton(range_frame, text="Track labels", variable=self.show_track_labels).pack(anchor="w", padx=6, pady=2)
        ttk.Button(range_frame, text="Range -", command=lambda: self.change_range(-1)).pack(side="left", expand=True, fill="x", padx=6, pady=6)
        ttk.Button(range_frame, text="Range +", command=lambda: self.change_range(1)).pack(side="left", expand=True, fill="x", padx=6, pady=6)

        ttk.Label(panel, text="Track Label Size").pack(anchor="w")
        ttk.Button(panel, text="Smaller", command=lambda: self.change_track_font(-1)).pack(fill="x", pady=2)
        ttk.Button(panel, text="Bigger", command=lambda: self.change_track_font(1)).pack(fill="x", pady=2)

        ttk.Separator(panel).pack(fill="x", pady=10)

        notes = (
            "Bearing convention:\n"
            "000° = North    090° = East\n"
            "180° = South    270° = West\n\n"
            "RWS = range-while-search\n"
            "TWS = track-while-scan\n"
            "STT = single target track\n"
            "FCS = fire-control solution\n"
            "ACM = close boresight lock\n"
            "Click a contact to lock it\n"
            "Enter = lock nearest\n"
            "A/G = amber/green CRT\n"
            "Missiles use PN lead pursuit\n"
            "Targets can evade / break locks\n"
            "Track numbers are auto-random"
        )
        ttk.Label(panel, text=notes, justify="left").pack(anchor="w")

        _bind_wheel_recursive(panel_shell)
        panel_canvas.bind("<Prior>", lambda event: (panel_canvas.yview_scroll(-1, "pages"), "break"))
        panel_canvas.bind("<Next>", lambda event: (panel_canvas.yview_scroll(1, "pages"), "break"))
        panel_canvas.bind("<Home>", lambda event: (panel_canvas.yview_moveto(0), "break"))
        panel_canvas.bind("<End>", lambda event: (panel_canvas.yview_moveto(1), "break"))

    # ---------------------------- State ----------------------------
    def on_canvas_resize(self, event):
        self.canvas_w = max(420, event.width)
        self.canvas_h = max(320, event.height)
        self.cx = self.canvas_w / 2
        self.cy = self.canvas_h / 2
        self.radius = min(self.canvas_w, self.canvas_h) * 0.405

    def change_track_font(self, delta):
        self.track_font_size = max(6, min(14, self.track_font_size + delta))

    def change_range(self, delta):
        idx = self.range_steps_km.index(self.max_range_km)
        idx = max(0, min(len(self.range_steps_km) - 1, idx + delta))
        self.max_range_km = self.range_steps_km[idx]

    def set_theme(self, theme):
        self.theme = theme

    def clear_tracks(self):
        self.tracks.clear()
        self.missiles.clear()
        self.locked_track_id = None
        self.lock_reacquire_delay = 0.0

    def reload_missiles(self):
        self.missile_ammo = self.max_missile_ammo
        self.missile_reload_cooldown = 1.5
        self.fcs_state_var.set("RELOADED")

    def toggle_running(self):
        self.running = not self.running

    def ecm_on_locked_track(self):
        target = self.get_locked_track()
        if not target:
            self.fcs_state_var.set("NO LOCK")
            return
        target.ecm = True
        target.ecm_strength = max(0.15, min(1.0, float(self.ecm_strength_var.get())))
        self.fcs_state_var.set("ECM")

    def ecm_on_all_tracks(self):
        strength = max(0.15, min(1.0, float(self.ecm_strength_var.get())))
        for t in self.tracks:
            if not t.damaged:
                t.ecm = True
                t.ecm_strength = strength
        self.fcs_state_var.set("ECM ALL")

    def clear_ecm(self):
        self.global_ecm.set(False)
        for t in self.tracks:
            t.ecm = False
            t.ecm_strength = 0.0
        self.fcs_state_var.set("ECM OFF")

    def generate_track_id(self):
        used = {t.track_id for t in self.tracks}
        for _ in range(200):
            candidate = f"{random.randint(1, 999):03d}"
            if candidate not in used:
                return candidate
        # Fallback if the scope is extremely full.
        n = 1
        while f"{n:03d}" in used:
            n += 1
        return f"{n:03d}"

    def make_track(self, iff, alt, hdg, spd, nctr, x_km, y_km):
        return Track(self.generate_track_id(), iff, alt, hdg, spd, nctr, x_km, y_km)

    def add_demo_tracks(self):
        self.tracks.extend([
            self.make_track("UNKNOWN", 120, 275, 420, "MiG-29", 115, 85),
            self.make_track("HOSTILE?", 80, 245, 510, "Su-22", 170, -40),
            self.make_track("FRIENDLY", 210, 90, 460, "F-4F", -130, -70),
            self.make_track("UNKNOWN", 60, 315, 380, "An-26", 40, 170),
        ])

    def add_track_from_ui(self):
        try:
            track_id = self.generate_track_id()
            iff = self.entries["iff"].get().strip() or "UNKNOWN"
            alt = int(float(self.entries["alt"].get()))
            hdg = float(self.entries["hdg"].get()) % 360
            spd = float(self.entries["spd"].get())
            nctr = self.entries["nctr"].get().strip() or "UNKNOWN"

            rng = float(self.entries["range"].get())
            brg = math.radians(float(self.entries["bearing"].get()) % 360)

            x_km = math.sin(brg) * rng
            y_km = math.cos(brg) * rng

            self.tracks.append(Track(track_id, iff, alt, hdg, spd, nctr, x_km, y_km))
            self.fcs_state_var.set(f"TRK {track_id}")
        except ValueError:
            print("Invalid track input.")

    def update_tracks(self, dt):
        survivors = []
        for t in self.tracks:
            if t.damaged:
                t.damage_age += dt
                t.alt = max(0.0, float(t.alt) - t.descent_rate * dt)
                t.spd = max(120.0, float(t.spd) - 22.0 * dt)
                # A hit track keeps moving while descending, but no longer wraps back onto the scope.
                drift_scale = 0.45
            else:
                drift_scale = 1.0
                self.apply_defensive_ai(t, dt)

            distance_km = (float(t.spd) / 3600.0) * dt * self.speed_scale * drift_scale
            rad = math.radians(t.hdg)

            t.x_km += math.sin(rad) * distance_km
            t.y_km += math.cos(rad) * distance_km

            if t.damaged and t.alt <= 0.0:
                if self.locked_track_id == t.track_id:
                    self.locked_track_id = None
                    self.fcs_state_var.set("STANDBY")
                continue

            dist = math.hypot(t.x_km, t.y_km)
            if not t.damaged and dist > self.max_range_km * 1.08:
                t.x_km *= -0.85
                t.y_km *= -0.85

            survivors.append(t)

        self.tracks = survivors

    def threat_level_for_track(self, t):
        if t.damaged or not self.target_ai_evasion.get():
            return 0.0
        threat = 0.0
        if self.locked_track_id == t.track_id:
            threat = max(threat, 0.55)
        for m in self.missiles:
            if m.target_id == t.track_id and not m.guidance_lost:
                d = math.hypot(m.x_km - t.x_km, m.y_km - t.y_km)
                # A nearby missile forces harder maneuvering than a simple radar lock.
                threat = max(threat, 1.0 if d < 45 else 0.75)
        return threat

    def apply_defensive_ai(self, t, dt):
        threat = self.threat_level_for_track(t)
        t.evasion_cooldown = max(0.0, t.evasion_cooldown - dt)

        if threat > 0.0:
            t.lock_pressure = min(1.0, t.lock_pressure + dt * (0.18 + 0.30 * threat))
            if not t.evading and t.evasion_cooldown <= 0.0:
                t.evading = True
                t.evasion_timer = random.uniform(3.2, 7.0)
                t.evasion_turn_dir = random.choice([-1, 1])
                t.evasion_phase = random.random() * math.tau
        else:
            t.lock_pressure = max(0.0, t.lock_pressure - dt * 0.22)

        if t.evading:
            t.evasion_timer -= dt
            # Jinking heading change. It is stylized for the CRT display, not a flight sim.
            wiggle = math.sin(time.time() * 3.2 + t.evasion_phase)
            turn_rate = t.evasion_turn_dir * (20.0 + 26.0 * threat) + wiggle * 18.0
            t.hdg = (t.hdg + turn_rate * dt) % 360

            # Speed changes and altitude notches make locks less stable and visibly alive.
            if threat >= 0.75:
                t.spd = max(240.0, min(760.0, t.spd + random.uniform(-28.0, 18.0) * dt))
                t.alt = max(20.0, t.alt - random.uniform(3.0, 9.0) * dt)
            else:
                t.spd = max(220.0, min(740.0, t.spd + random.uniform(-12.0, 12.0) * dt))

            if t.evasion_timer <= 0.0:
                t.evading = False
                t.evasion_cooldown = random.uniform(1.0, 3.5)

        self.try_break_lock(t, dt, threat)

    def try_break_lock(self, t, dt, threat):
        if not self.lock_breaks_enabled.get():
            return
        if self.locked_track_id != t.track_id or threat <= 0.0 or t.damaged:
            return

        ecm = self.ecm_strength_for_track(t)
        mode = self.mode_var.get()
        mode_factor = 1.0
        if mode in ("STT LOCK", "FCS"):
            mode_factor = 0.62
        elif mode in ("ACM BORESIGHT", "SECTOR 120", "RWS", "B-SCOPE"):
            mode_factor = 1.25

        # Low altitude, ECM, and hard maneuvering increase the chance of a momentary lost lock.
        low_alt_bonus = 0.025 if t.alt < 60 else 0.0
        probability_per_second = mode_factor * (0.010 + 0.030 * float(t.evading) + 0.065 * ecm + low_alt_bonus + 0.018 * t.lock_pressure)

        if random.random() < probability_per_second * dt:
            self.locked_track_id = None
            self.lock_reacquire_delay = random.uniform(1.4, 3.2)
            self.fcs_state_var.set("LOCK LOST")

    def find_track_by_id(self, track_id):
        for t in self.tracks:
            if t.track_id == track_id:
                return t
        return None

    def update_missiles(self, dt):
        self.missile_cooldown = max(0.0, self.missile_cooldown - dt)
        self.missile_reload_cooldown = max(0.0, self.missile_reload_cooldown - dt)

        survivors = []
        for m in self.missiles:
            m.age += dt
            prev_x, prev_y = m.x_km, m.y_km
            m.trail.append((m.x_km, m.y_km))
            if len(m.trail) > self.missile_trail_points:
                m.trail = m.trail[-self.missile_trail_points:]

            # Boost-sustain behavior: fast burn first, then slow decay. This makes
            # the weapon visibly accelerate instead of moving as a constant-speed dot.
            if m.age <= m.burn_time:
                m.spd = min(m.max_spd, m.spd + m.accel * dt)
            else:
                m.spd = max(850.0, m.spd - m.drag * dt)

            target = self.find_track_by_id(m.target_id)
            # 1980s radar-guided feel: the missile needs continued radar support.
            radar_support = bool(target and self.locked_track_id == m.target_id)
            target_in_launch_view = bool(target and radar_support and self.track_is_visible_for_mode(target, m.launch_mode))
            jam = self.ecm_strength_for_track(target) if target else 0.0
            defense = max(jam, 0.28 if (target and getattr(target, "evading", False)) else 0.0)

            if target_in_launch_view:
                apparent_x, apparent_y = self.apparent_target_position(target, m.age, jam)
                rx = apparent_x - m.x_km
                ry = apparent_y - m.y_km
                rng = max(0.001, math.hypot(rx, ry))
                los = math.degrees(math.atan2(rx, ry)) % 360
                seeker_error = self.signed_angle(los, m.hdg)
                seeker_limit = max(18.0, m.seeker_limit * (1.0 - 0.38 * defense))

                # Simple ECM: strong jamming can make the seeker blink or chase a false
                # echo for a moment. The missile may reacquire if geometry improves.
                jam_blink = jam > 0.0 and random.random() < jam * dt * (0.10 if self.ecm_mode_var.get() == "SPOT" else 0.22)
                if jam_blink:
                    m.guidance_lost = True
                    m.lost_time += dt

                if (not jam_blink) and abs(seeker_error) <= seeker_limit and not (m.guidance_lost and m.lost_time > 0.55):
                    m.guidance_lost = False
                    m.lost_time = 0.0
                    if m.last_los is None:
                        m.last_los = los

                    los_rate = self.signed_angle(los, m.last_los) / max(dt, 0.001)
                    m.last_los = los

                    mvx, mvy = self.velocity_vector_display(m.hdg, m.spd)
                    tvx, tvy = self.target_velocity_display(target)
                    rvx = tvx - mvx
                    rvy = tvy - mvy
                    closing = -((rx * rvx + ry * rvy) / rng)
                    missile_speed_display = max(0.001, math.hypot(mvx, mvy))

                    # Proportional navigation gives the curved, leading intercept path.
                    pn_rate = m.nav_constant * max(0.25, closing / missile_speed_display) * los_rate

                    lead = self.intercept_solution(m.x_km, m.y_km, target, max(m.spd, m.max_spd * 0.82))
                    lead_error = self.signed_angle(lead["bearing"], m.hdg)
                    if defense > 0.0:
                        lead_error += random.uniform(-28.0, 28.0) * defense
                    lead_rate = lead_error / 0.85

                    commanded_rate = 0.72 * pn_rate + 0.92 * lead_rate
                    speed_factor = 0.45 + 0.55 * min(1.0, m.spd / max(1.0, m.max_spd))
                    turn_limit = m.max_turn_rate * speed_factor * (1.0 - 0.22 * defense)
                    turn_rate = max(-turn_limit, min(turn_limit, commanded_rate))
                    m.hdg = (m.hdg + turn_rate * dt) % 360
                else:
                    m.guidance_lost = True
                    m.lost_time += dt
            else:
                m.guidance_lost = True
                m.lost_time += dt

            rad = math.radians(m.hdg)
            distance_km = (m.spd / 3600.0) * dt * self.speed_scale
            m.x_km += math.sin(rad) * distance_km
            m.y_km += math.cos(rad) * distance_km

            if target and not target.damaged:
                actual_distance = math.hypot(target.x_km - m.x_km, target.y_km - m.y_km)
                m.closest_approach = min(m.closest_approach, actual_distance)

                # ECM reduces the effective proximity fuse and can turn a near-hit into a miss.
                effective_prox = max(1.0, m.proximity_radius * (1.0 - 0.45 * defense))
                if target_in_launch_view and not m.guidance_lost:
                    miss_distance = self.segment_point_distance(prev_x, prev_y, m.x_km, m.y_km, target.x_km, target.y_km)
                    if min(miss_distance, actual_distance) <= effective_prox:
                        self.damage_track(target)
                        continue

                # Overshoot: if the missile passed the target and closest approach was outside
                # the fuze radius, count it as a clean miss and let it disappear quietly.
                if m.age > 2.0 and m.closest_approach < 18.0:
                    if actual_distance > m.closest_approach + max(4.0, m.proximity_radius * 1.6) and m.closest_approach > effective_prox:
                        self.register_miss(m, "MISS")
                        continue

            if m.lost_time > (2.4 if self.ecm_mode_var.get() != "CHAFF" else 1.7):
                self.register_miss(m, "LOST")
                continue

            if m.age > m.max_age or math.hypot(m.x_km, m.y_km) > self.max_range_km * 1.45:
                if target and not target.damaged:
                    self.register_miss(m, "MISS")
                continue

            survivors.append(m)

        self.missiles = survivors

    def damage_track(self, target):
        if not target.damaged:
            target.damaged = True
            target.damage_age = 0.0
            target.descent_rate = max(10.0, min(28.0, float(target.alt) / 7.0))
            self.kills += 1
        self.fcs_state_var.set("HIT")

    # ---------------------------- Math helpers ----------------------------
    def signed_angle(self, angle, center=0):
        return (angle - center + 180) % 360 - 180

    def angle_difference(self, a, b):
        return abs((a - b + 180) % 360 - 180)

    def bearing_of_track(self, t):
        return math.degrees(math.atan2(t.x_km, t.y_km)) % 360

    def range_of_track(self, t):
        return math.hypot(t.x_km, t.y_km)

    def km_to_px_ppi(self, x_km, y_km):
        scale = self.radius / self.max_range_km
        x = self.cx + x_km * scale
        y = self.cy - y_km * scale
        return x, y

    def px_in_ppi(self, x, y):
        return math.hypot(x - self.cx, y - self.cy) <= self.radius

    def get_sector_sweep_bearing(self, width=120):
        """Smooth bidirectional sector sweep centered on 000°.

        Uses an unbounded sweep phase, not the wrapped 360° display angle.
        That avoids the visible jump that happened after the first global loop.
        Cosine easing slows the beam gently at the left/right edges.
        """
        half = width / 2
        cycle = max(1.0, width * 2.0)
        p = (self.sweep_phase % cycle) / cycle

        if p < 0.5:
            u = p * 2.0
            eased = 0.5 - 0.5 * math.cos(math.pi * u)
            offset = -half + eased * width
        else:
            u = (p - 0.5) * 2.0
            eased = 0.5 - 0.5 * math.cos(math.pi * u)
            offset = half - eased * width

        return offset % 360

    def track_velocity_kmh(self, t):
        rad = math.radians(t.hdg)
        return math.sin(rad) * t.spd, math.cos(rad) * t.spd

    def closure_rate(self, t):
        rng = max(0.1, self.range_of_track(t))
        vx, vy = self.track_velocity_kmh(t)
        radial_away = (vx * t.x_km + vy * t.y_km) / rng
        return -radial_away

    def aspect_text(self, t):
        brg = self.bearing_of_track(t)
        target_tail = (t.hdg + 180) % 360
        aspect = self.angle_difference(brg, target_tail)
        if aspect < 35:
            return "HOT"
        if aspect > 145:
            return "COLD"
        return "FLANK"

    def velocity_vector_display(self, hdg, spd_kmh):
        """Return velocity in displayed km per real second.

        Track and missile motion in this simulator is time-compressed by
        self.speed_scale, so the same scaled units are used for intercept math.
        """
        rad = math.radians(hdg)
        speed = (float(spd_kmh) / 3600.0) * self.speed_scale
        return math.sin(rad) * speed, math.cos(rad) * speed

    def target_velocity_display(self, t):
        return self.velocity_vector_display(t.hdg, t.spd)

    def segment_point_distance(self, ax, ay, bx, by, px, py):
        abx = bx - ax
        aby = by - ay
        apx = px - ax
        apy = py - ay
        denom = abx * abx + aby * aby
        if denom <= 1e-9:
            return math.hypot(px - ax, py - ay)
        u = max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
        cx = ax + abx * u
        cy = ay + aby * u
        return math.hypot(px - cx, py - cy)

    def intercept_solution(self, shooter_x, shooter_y, target, missile_speed_kmh=None):
        """Predict the target intercept point for a constant-speed first guess."""
        missile_speed_kmh = missile_speed_kmh or self.missile_max_speed_kmh
        vm = max(0.001, (float(missile_speed_kmh) / 3600.0) * self.speed_scale)
        tvx, tvy = self.target_velocity_display(target)
        rx = target.x_km - shooter_x
        ry = target.y_km - shooter_y

        a = tvx * tvx + tvy * tvy - vm * vm
        b = 2.0 * (rx * tvx + ry * tvy)
        c = rx * rx + ry * ry
        t_hit = None

        if abs(a) < 1e-9:
            if abs(b) > 1e-9:
                candidate = -c / b
                if candidate > 0:
                    t_hit = candidate
        else:
            disc = b * b - 4.0 * a * c
            if disc >= 0:
                root = math.sqrt(disc)
                candidates = [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]
                positives = [v for v in candidates if v > 0]
                if positives:
                    t_hit = min(positives)

        if t_hit is None:
            t_hit = math.sqrt(c) / vm

        t_hit = max(0.2, min(60.0, t_hit))
        lead_x = target.x_km + tvx * t_hit
        lead_y = target.y_km + tvy * t_hit
        lead_brg = math.degrees(math.atan2(lead_x - shooter_x, lead_y - shooter_y)) % 360
        lead_rng = math.hypot(lead_x - shooter_x, lead_y - shooter_y)
        return {
            "lead_seconds": t_hit,
            "lead_x": lead_x,
            "lead_y": lead_y,
            "bearing": lead_brg,
            "range": lead_rng,
        }

    def fcs_solution(self, t):
        rng = self.range_of_track(t)
        closure = self.closure_rate(t)
        brg = self.bearing_of_track(t)
        lead = self.intercept_solution(0.0, 0.0, t, self.missile_max_speed_kmh * 0.88)
        return {
            "range": rng,
            "bearing": brg,
            "closure": closure,
            "aspect": self.aspect_text(t),
            "lead_seconds": lead["lead_seconds"],
            "lead_x": lead["lead_x"],
            "lead_y": lead["lead_y"],
            "lead_bearing": lead["bearing"],
            "lead_range": lead["range"],
        }

    # ---------------------------- ECM / miss helpers ----------------------------
    def ecm_strength_for_track(self, t):
        if t.damaged:
            return 0.0
        strength = 0.0
        if self.global_ecm.get():
            # Global ECM makes the whole scope dirtier, but individual jammers are stronger.
            strength = max(strength, float(self.ecm_strength_var.get()) * 0.55)
        if getattr(t, "ecm", False):
            strength = max(strength, float(getattr(t, "ecm_strength", 0.0)))
        return max(0.0, min(1.0, strength))

    def apparent_target_position(self, t, missile_age=0.0, strength=None):
        """Return a noisy/false target position for stylized 1980s ECM visuals.

        This is intentionally arcade-like: it gives jamming, chaff and range-gate
        errors without modelling a real radar or seeker.
        """
        strength = self.ecm_strength_for_track(t) if strength is None else strength
        if strength <= 0.0:
            return t.x_km, t.y_km

        brg = self.bearing_of_track(t)
        rng = self.range_of_track(t)
        mode = self.ecm_mode_var.get()
        phase = math.radians(getattr(t, "ecm_phase", 0.0) + missile_age * (95 if mode != "CHAFF" else 45))

        if mode == "BARRAGE":
            bearing_error = math.sin(phase * 1.7) * 4.0 * strength + random.uniform(-3.0, 3.0) * strength
            range_error = math.sin(phase * 0.9) * 14.0 * strength + random.uniform(-6.0, 6.0) * strength
        elif mode == "CHAFF":
            bearing_error = math.sin(phase) * 10.0 * strength + random.uniform(-7.0, 7.0) * strength
            range_error = 20.0 * strength + math.sin(phase * 0.6) * 18.0 * strength
        else:  # SPOT
            bearing_error = math.sin(phase * 2.2) * 2.5 * strength + random.uniform(-1.5, 1.5) * strength
            range_error = math.sin(phase) * 8.0 * strength + random.uniform(-4.0, 4.0) * strength

        fake_brg = math.radians((brg + bearing_error) % 360)
        fake_rng = max(0.1, rng + range_error)
        return math.sin(fake_brg) * fake_rng, math.cos(fake_brg) * fake_rng

    def ecm_jitter_px(self, t):
        strength = self.ecm_strength_for_track(t)
        if strength <= 0.0:
            return 0.0, 0.0
        mode = self.ecm_mode_var.get()
        mult = 1.8 if mode == "BARRAGE" else 2.6 if mode == "CHAFF" else 1.0
        phase = math.radians(getattr(t, "ecm_phase", 0.0) + time.time() * 85.0)
        jx = (math.sin(phase * 1.7) * 8.0 + random.uniform(-5.0, 5.0)) * strength * mult
        jy = (math.cos(phase * 1.3) * 5.0 + random.uniform(-4.0, 4.0)) * strength * mult
        return jx, jy

    def register_miss(self, missile, reason="MISS"):
        self.misses += 1
        self.fcs_state_var.set(reason)

    # ---------------------------- Lock/FCS helpers ----------------------------
    def get_locked_track(self):
        if not self.locked_track_id:
            return None
        for t in self.tracks:
            if t.track_id == self.locked_track_id:
                return t
        self.locked_track_id = None
        return None

    def track_is_visible_for_mode(self, t, mode=None):
        mode = mode or self.mode_var.get()
        rng = self.range_of_track(t)
        if rng > self.max_range_km:
            return False
        brg = self.bearing_of_track(t)
        if mode in ("SECTOR 120", "RWS"):
            return abs(self.signed_angle(brg, 0)) <= 60
        if mode == "ACM BORESIGHT":
            return abs(self.signed_angle(brg, 0)) <= 18 and rng <= min(self.max_range_km, 90)
        if mode == "B-SCOPE":
            return abs(self.signed_angle(brg, 0)) <= 70
        return True

    def screen_pos_for_track(self, t, mode=None):
        mode = mode or self.mode_var.get()
        if mode == "B-SCOPE":
            p = self.bscope_coord(t.x_km, t.y_km)
            if not p:
                return None
            return p[0], p[1]
        if mode == "E-SCOPE":
            rng = self.range_of_track(t)
            if rng > self.max_range_km:
                return None
            left, top, right, bottom = self.escope_bounds()
            max_alt = max(300.0, max([float(tr.alt) for tr in self.tracks], default=300.0))
            x = left + rng / self.max_range_km * (right - left)
            y = bottom - min(float(t.alt), max_alt) / max_alt * (bottom - top)
            return x, y
        x, y = self.km_to_px_ppi(t.x_km, t.y_km)
        if not self.px_in_ppi(x, y):
            return None
        return x, y

    def select_track_with_mouse(self, event):
        mode = self.mode_var.get()
        candidates = []
        for t in self.tracks:
            if not self.track_is_visible_for_mode(t, mode):
                continue
            pos = self.screen_pos_for_track(t, mode)
            if not pos:
                continue
            x, y = pos
            d = math.hypot(event.x - x, event.y - y)
            candidates.append((d, t))

        if not candidates:
            return

        distance_px, target = min(candidates, key=lambda item: item[0])
        if distance_px <= 30:
            self.locked_track_id = target.track_id
            self.fcs_state_var.set("LOCK")

    def lock_nearest_track(self):
        candidates = [t for t in self.tracks if self.track_is_visible_for_mode(t)]
        if not candidates:
            self.locked_track_id = None
            self.fcs_state_var.set("NO TRACK")
            return
        target = min(candidates, key=self.range_of_track)
        self.locked_track_id = target.track_id
        self.fcs_state_var.set("LOCK")

    def lock_nearest_track_event(self, event=None):
        self.lock_nearest_track()

    def lock_next_track(self):
        candidates = sorted([t for t in self.tracks if self.track_is_visible_for_mode(t)], key=lambda tr: tr.track_id)
        if not candidates:
            self.locked_track_id = None
            self.fcs_state_var.set("NO TRACK")
            return
        if self.locked_track_id not in [t.track_id for t in candidates]:
            self.locked_track_id = candidates[0].track_id
        else:
            idx = [t.track_id for t in candidates].index(self.locked_track_id)
            self.locked_track_id = candidates[(idx + 1) % len(candidates)].track_id
        self.fcs_state_var.set("LOCK")

    def fire_missile_key_event(self, event=None):
        """Keyboard shortcut for firing without showing any on-screen hint.

        Ignore spaces typed into text-entry widgets so editing track fields does
        not accidentally launch a missile.
        """
        widget_class = event.widget.winfo_class() if event and event.widget else ""
        if widget_class in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
            return None
        self.fire_missile(event)
        return "break"

    def fire_missile(self, event=None):
        target = self.get_locked_track()
        if not self.fcs_master_arm.get():
            self.fcs_state_var.set("SAFE")
            return
        if not target:
            self.fcs_state_var.set("NO LOCK")
            return
        if target.damaged:
            self.fcs_state_var.set("DAMAGED")
            return
        if not self.track_is_visible_for_mode(target):
            self.locked_track_id = None
            self.fcs_state_var.set("OUT OF VIEW")
            return
        if self.missile_ammo <= 0:
            self.fcs_state_var.set("NO MSL")
            return
        if self.missile_cooldown > 0.0:
            self.fcs_state_var.set("WAIT")
            return

        sol = self.fcs_solution(target)
        # Simple arcade launch envelope: within displayed radar range and not too close.
        if sol["range"] > min(self.max_range_km, 220) or sol["range"] < 6:
            self.fcs_state_var.set("NO SHOT")
            return

        self.missile_counter += 1
        missile = Missile(
            missile_id=f"M{self.missile_counter:02d}",
            target_id=target.track_id,
            x_km=0.0,
            y_km=0.0,
            hdg=sol["lead_bearing"],
            launch_mode=self.mode_var.get(),
            spd=self.missile_launch_speed_kmh,
            max_spd=self.missile_max_speed_kmh,
            accel=self.missile_accel_kmh_s,
            burn_time=self.missile_burn_time_s,
            drag=self.missile_drag_kmh_s,
            max_turn_rate=self.missile_max_turn_rate_deg,
            nav_constant=self.missile_nav_constant,
            seeker_limit=self.missile_seeker_limit_deg,
            proximity_radius=self.missile_proximity_radius_km,
        )
        missile.last_los = self.bearing_of_track(target)
        missile.trail.append((missile.x_km, missile.y_km))
        self.missiles.append(missile)
        self.missile_ammo -= 1
        self.shots_fired += 1
        self.missile_cooldown = 0.85
        self.fcs_state_var.set("MISSILE")

    def clear_lock(self):
        self.locked_track_id = None
        self.lock_reacquire_delay = 0.0
        self.fcs_state_var.set("STANDBY")

    def auto_acquire_for_mode(self):
        mode = self.mode_var.get()
        lock_required = mode in ("STT LOCK", "FCS", "ACM BORESIGHT")
        locked = self.get_locked_track()

        # Never carry a lock into a mode where that track is outside the visible radar volume.
        # This fixes sector/ACM modes being able to fire at off-screen contacts.
        if locked and not self.track_is_visible_for_mode(locked, mode):
            self.locked_track_id = None
            locked = None
            self.fcs_state_var.set("OUT OF VIEW")

        if lock_required and not locked:
            if self.lock_reacquire_delay <= 0.0:
                self.lock_nearest_track()
            else:
                self.fcs_state_var.set("LOCK LOST")
        elif not lock_required and self.fcs_state_var.get() in ("NO TRACK", "OUT OF VIEW"):
            self.fcs_state_var.set("STANDBY")

    # ---------------------------- Drawing helpers ----------------------------
    def draw_background(self):
        col = self.colors[self.theme]
        bg = col["bg"] if random.random() > 0.05 else "#000000"
        self.canvas.configure(bg=bg)

    def crt_text(self, x, y, text, fill=None, font=None, anchor="center", bg=True, pad=3, justify="center"):
        col = self.colors[self.theme]
        fill = fill or col["text"]
        font = font or ("Consolas", self.grid_font_size, "bold")
        item = self.canvas.create_text(x, y, text=text, fill=fill, font=font, anchor=anchor, justify=justify)
        if bg:
            bbox = self.canvas.bbox(item)
            if bbox:
                rect = self.canvas.create_rectangle(
                    bbox[0] - pad,
                    bbox[1] - pad,
                    bbox[2] + pad,
                    bbox[3] + pad,
                    fill=col["bg"],
                    outline=col["dim"],
                )
                self.canvas.tag_lower(rect, item)
        return item

    def draw_bearing_label(self, deg, radius_offset=24, compact=False):
        col = self.colors[self.theme]
        rad = math.radians(deg)
        tx = self.cx + math.sin(rad) * (self.radius + radius_offset)
        ty = self.cy - math.cos(rad) * (self.radius + radius_offset)

        cardinal = {0: "N", 90: "E", 180: "S", 270: "W"}.get(deg)
        if cardinal:
            text = f"{deg:03d}° {cardinal}"
            font = ("Consolas", self.major_font_size, "bold")
            fill = col["bright"]
        else:
            text = f"{deg:03d}°" if not compact else f"{deg:03d}"
            font = ("Consolas", self.grid_font_size, "bold")
            fill = col["text"]

        self.crt_text(tx, ty, text, fill=fill, font=font, bg=self.show_readable_scale.get(), pad=2)

    def draw_range_label(self, x, y, r_km, anchor="w"):
        col = self.colors[self.theme]
        label = f"{int(r_km):03d} km"
        self.crt_text(
            x,
            y,
            label,
            fill=col["text"],
            font=("Consolas", self.grid_font_size, "bold"),
            anchor=anchor,
            bg=self.show_readable_scale.get(),
            pad=2,
        )

    def range_rings(self):
        if self.max_range_km <= 50:
            return [10, 20, 30, 40, 50]
        if self.max_range_km <= 100:
            return [20, 40, 60, 80, 100]
        if self.max_range_km <= 150:
            return [30, 60, 90, 120, 150]
        if self.max_range_km <= 250:
            return [50, 100, 150, 200, 250]
        return [80, 160, 240, 320, 400]

    def draw_tick_ring(self):
        col = self.colors[self.theme]
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            outer = self.radius
            inner = self.radius - (13 if deg % 30 == 0 else 7)
            x1 = self.cx + math.sin(rad) * inner
            y1 = self.cy - math.cos(rad) * inner
            x2 = self.cx + math.sin(rad) * outer
            y2 = self.cy - math.cos(rad) * outer
            self.canvas.create_line(x1, y1, x2, y2, fill=col["grid"], width=2 if deg % 30 == 0 else 1)

    # ---------------------------- PPI/Sector Modes ----------------------------
    def draw_ppi_grid(self, sector=False, sector_width=120, title=None):
        col = self.colors[self.theme]

        if not sector:
            self.canvas.create_oval(
                self.cx - self.radius, self.cy - self.radius,
                self.cx + self.radius, self.cy + self.radius,
                outline=col["grid"], width=2,
            )
            self.draw_tick_ring()

            for r_km in self.range_rings():
                r = self.radius * r_km / self.max_range_km
                self.canvas.create_oval(
                    self.cx - r, self.cy - r,
                    self.cx + r, self.cy + r,
                    outline=col["dim"], width=1,
                )
                self.draw_range_label(self.cx + 10, self.cy - r + 12, r_km, anchor="w")

            for deg in range(0, 360, 30):
                rad = math.radians(deg)
                x = self.cx + math.sin(rad) * self.radius
                y = self.cy - math.cos(rad) * self.radius
                self.canvas.create_line(self.cx, self.cy, x, y, fill=col["dim"])
                self.draw_bearing_label(deg, radius_offset=30)

            self.canvas.create_line(self.cx - self.radius, self.cy, self.cx + self.radius, self.cy, fill=col["dim"], width=1)
            self.canvas.create_line(self.cx, self.cy - self.radius, self.cx, self.cy + self.radius, fill=col["dim"], width=1)
        else:
            # Tk arcs use canvas coordinates; 90° is north and positive angle is counterclockwise.
            start_canvas_angle = 90 - sector_width / 2
            extent = sector_width
            half = sector_width / 2

            for r_km in self.range_rings():
                r = self.radius * r_km / self.max_range_km
                self.canvas.create_arc(
                    self.cx - r, self.cy - r,
                    self.cx + r, self.cy + r,
                    start=start_canvas_angle,
                    extent=extent,
                    style="arc",
                    outline=col["dim"],
                    width=1,
                )
                rx = self.cx + math.sin(math.radians(half)) * r + 8
                ry = self.cy - math.cos(math.radians(half)) * r
                self.draw_range_label(rx, ry, r_km, anchor="w")

            step = 30 if sector_width >= 90 else 10
            brgs = list(range(int(-half), int(half) + 1, step))
            if 0 not in brgs:
                brgs.append(0)
            for brg in sorted(set(brgs)):
                b = brg % 360
                rad = math.radians(b)
                x = self.cx + math.sin(rad) * self.radius
                y = self.cy - math.cos(rad) * self.radius
                self.canvas.create_line(self.cx, self.cy, x, y, fill=col["dim"], width=2 if brg == 0 else 1)
                self.draw_bearing_label(b, radius_offset=28, compact=True)

            self.canvas.create_arc(
                self.cx - self.radius, self.cy - self.radius,
                self.cx + self.radius, self.cy + self.radius,
                start=start_canvas_angle,
                extent=extent,
                style="arc",
                outline=col["grid"],
                width=2,
            )

            for brg in (-half, half):
                rad = math.radians(brg % 360)
                x = self.cx + math.sin(rad) * self.radius
                y = self.cy - math.cos(rad) * self.radius
                self.canvas.create_line(self.cx, self.cy, x, y, fill=col["grid"], width=2)

        if title:
            self.crt_text(
                self.cx,
                max(24, self.cy - self.radius - 58),
                title,
                fill=col["bright"],
                font=("Consolas", 13, "bold"),
                bg=True,
            )

    def draw_ppi_sweep(self, sector=False, sector_width=120):
        col = self.colors[self.theme]
        base_angle = self.get_sector_sweep_bearing(sector_width) if sector else self.sweep_angle

        for i in range(14):
            angle = base_angle - i * 2.6
            if sector and abs(self.signed_angle(angle, 0)) > sector_width / 2 + 1:
                continue

            rad = math.radians(angle)
            x = self.cx + math.sin(rad) * self.radius
            y = self.cy - math.cos(rad) * self.radius

            color = col["bright"] if i == 0 else col["grid"] if i < 5 else col["dim"]
            width = 3 if i == 0 else 1
            self.canvas.create_line(self.cx, self.cy, x, y, fill=color, width=width)

    def draw_track_label(self, x, y, t, color, compact=False):
        if compact:
            sol = self.fcs_solution(t)
            state = " DMG" if t.damaged else " EVADE" if getattr(t, "evading", False) else " ECM" if self.ecm_strength_for_track(t) > 0 else ""
            label = f"{t.track_id}{state}  {int(sol['bearing']):03d}°/{int(sol['range']):03d}km  {t.iff}"
        else:
            sol = self.fcs_solution(t)
            label = (
                f"TRK {t.track_id}{'  DMG' if t.damaged else '  EVADE' if getattr(t, 'evading', False) else '  ECM' if self.ecm_strength_for_track(t) > 0 else ''}\n"
                f"IFF {t.iff}\n"
                f"BRG {int(sol['bearing']):03d}° RNG {int(sol['range']):03d} km\n"
                f"ALT {int(t.alt):03d}  HDG {int(t.hdg):03d}°\n"
                f"SPD {int(t.spd):03d}  NCTR {t.nctr}"
            )

        self.crt_text(
            x + 11,
            y - 10,
            label,
            fill=color,
            font=("Consolas", self.track_font_size, "bold"),
            anchor="nw",
            bg=True,
            pad=2,
            justify="left",
        )

    def draw_target_symbol(self, x, y, r, fill, locked=False):
        if locked:
            s = max(12, r + 9)
            self.canvas.create_line(x - s, y - s, x - s / 2, y - s, fill=fill, width=2)
            self.canvas.create_line(x - s, y - s, x - s, y - s / 2, fill=fill, width=2)
            self.canvas.create_line(x + s, y - s, x + s / 2, y - s, fill=fill, width=2)
            self.canvas.create_line(x + s, y - s, x + s, y - s / 2, fill=fill, width=2)
            self.canvas.create_line(x - s, y + s, x - s / 2, y + s, fill=fill, width=2)
            self.canvas.create_line(x - s, y + s, x - s, y + s / 2, fill=fill, width=2)
            self.canvas.create_line(x + s, y + s, x + s / 2, y + s, fill=fill, width=2)
            self.canvas.create_line(x + s, y + s, x + s, y + s / 2, fill=fill, width=2)
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline="")

    def draw_ecm_echo(self, x, y, t, fill):
        strength = self.ecm_strength_for_track(t)
        if strength <= 0.0:
            return
        col = self.colors[self.theme]
        mode = self.ecm_mode_var.get()
        vx = x - self.cx
        vy = y - self.cy
        length = max(1.0, math.hypot(vx, vy))
        ux, uy = vx / length, vy / length
        ghost_count = 2 + int(strength * (5 if mode == "CHAFF" else 3))
        for i in range(ghost_count):
            if mode == "CHAFF":
                offset = (i + 1) * (9 + 10 * strength) + random.uniform(-6, 6)
            elif mode == "BARRAGE":
                offset = random.uniform(-22, 42) * strength
            else:
                offset = (i + 1) * 12 * strength
            gx = x + ux * offset + random.uniform(-5, 5) * strength
            gy = y + uy * offset + random.uniform(-5, 5) * strength
            self.canvas.create_oval(gx - 2, gy - 2, gx + 2, gy + 2, outline=col["dim"], width=1)
        if strength >= 0.35:
            self.crt_text(x + 13, y + 13, f"ECM {mode[:3]}", fill=col["warn"], font=("Consolas", 8, "bold"), anchor="nw", bg=True)

    def draw_ppi_tracks(self, sector=False, raw=False, sector_width=120, labels=True, only_locked=False, dim_others=False):
        col = self.colors[self.theme]
        active_sweep = self.get_sector_sweep_bearing(sector_width) if sector else self.sweep_angle
        locked = self.get_locked_track()

        for t in self.tracks:
            brg = self.bearing_of_track(t)
            if sector and abs(self.signed_angle(brg, 0)) > sector_width / 2:
                continue
            if only_locked and locked is not t:
                continue

            x, y = self.km_to_px_ppi(t.x_km, t.y_km)
            if not self.px_in_ppi(x, y):
                continue
            if self.ecm_strength_for_track(t) > 0.0:
                jx, jy = self.ecm_jitter_px(t)
                x += jx
                y += jy

            sweep_dist = self.angle_difference(active_sweep, brg)
            is_locked = locked is t
            if t.damaged:
                fill = col["warn"]
                r = 5
            elif is_locked:
                fill = col["bright"]
                r = 6
            elif dim_others:
                fill = col["dim"]
                r = 3
            elif sweep_dist < 5:
                fill = col["bright"]
                r = 5
            elif sweep_dist < 18:
                fill = col["text"]
                r = 4
            else:
                fill = col["grid"]
                r = 3

            self.draw_target_symbol(x, y, r, fill, locked=is_locked)
            self.draw_ecm_echo(x, y, t, fill)

            hrad = math.radians(t.hdg)
            vx = x + math.sin(hrad) * t.vector_len
            vy = y - math.cos(hrad) * t.vector_len
            self.canvas.create_line(x, y, vx, vy, fill=fill, width=2 if is_locked else 1)

            if t.damaged:
                self.canvas.create_line(x - 7, y + 9, x, y + 18, x + 7, y + 9, fill=col["warn"], width=2)
            elif getattr(t, "evading", False):
                self.canvas.create_arc(x - 13, y - 13, x + 13, y + 13, start=35, extent=95, outline=col["warn"], width=1)
                self.canvas.create_arc(x - 15, y - 15, x + 15, y + 15, start=210, extent=80, outline=col["warn"], width=1)
            if labels and not raw and self.show_track_labels.get() and (not dim_others or is_locked or t.damaged):
                self.draw_track_label(x, y, t, col["warn"] if t.damaged else col["bright"] if is_locked else col["text"], compact=False)

    def draw_ppi_mode(self, sector=False, raw=False, sector_width=120, title=None, labels=True, dim_others=False):
        self.draw_ppi_grid(sector=sector, sector_width=sector_width, title=title)
        self.draw_ppi_sweep(sector=sector, sector_width=sector_width)
        self.draw_ppi_tracks(sector=sector, raw=raw, sector_width=sector_width, labels=labels, dim_others=dim_others)

    # ---------------------------- B-Scope ----------------------------
    def bscope_bounds(self):
        left = self.canvas_w * 0.08
        right = self.canvas_w * 0.92
        top = self.canvas_h * 0.13
        bottom = self.canvas_h * 0.86
        return left, top, right, bottom

    def draw_bscope_grid(self):
        col = self.colors[self.theme]
        left, top, right, bottom = self.bscope_bounds()
        self.canvas.create_rectangle(left, top, right, bottom, outline=col["grid"], width=2)

        for i in range(1, 6):
            y = bottom - i * (bottom - top) / 6
            self.canvas.create_line(left, y, right, y, fill=col["dim"])
            rng = int(i * self.max_range_km / 6)
            self.draw_range_label(left + 12, y - 10, rng, anchor="w")

        for brg in [-60, -30, 0, 30, 60]:
            x = left + (brg + 70) / 140 * (right - left)
            self.canvas.create_line(x, top, x, bottom, fill=col["dim"], width=2 if brg == 0 else 1)
            label = f"{brg:+03d}°"
            self.crt_text(x, bottom + 22, label, fill=col["text"], font=("Consolas", self.grid_font_size, "bold"), bg=True)

        self.crt_text(
            (left + right) / 2,
            top - 24,
            "B-SCOPE / BEARING-RANGE DISPLAY",
            fill=col["bright"],
            font=("Consolas", 13, "bold"),
            bg=True,
        )
        self.crt_text(left - 4, bottom + 22, "LEFT", fill=col["dim"], font=("Consolas", 9, "bold"), anchor="e", bg=False)
        self.crt_text(right + 4, bottom + 22, "RIGHT", fill=col["dim"], font=("Consolas", 9, "bold"), anchor="w", bg=False)

    def bscope_coord(self, x_km, y_km, sector_width=140):
        left, top, right, bottom = self.bscope_bounds()
        rng = math.hypot(x_km, y_km)
        if rng > self.max_range_km:
            return None
        brg = math.degrees(math.atan2(x_km, y_km)) % 360
        rel = self.signed_angle(brg, 0)
        half = sector_width / 2
        if abs(rel) > half:
            return None
        x = left + (rel + half) / sector_width * (right - left)
        y = bottom - rng / self.max_range_km * (bottom - top)
        return x, y, rel, rng

    def draw_bscope_sweep(self):
        col = self.colors[self.theme]
        left, top, right, bottom = self.bscope_bounds()
        sweep_bearing = self.get_sector_sweep_bearing(140)
        rel = self.signed_angle(sweep_bearing, 0)
        x = left + (rel + 70) / 140 * (right - left)
        self.canvas.create_line(x, top, x, bottom, fill=col["bright"], width=2)
        for i in range(1, 5):
            dx = i * 8
            self.canvas.create_line(x - dx, top, x - dx, bottom, fill=col["dim"], width=1)

    def draw_bscope_tracks(self):
        col = self.colors[self.theme]
        locked = self.get_locked_track()
        for t in self.tracks:
            p = self.bscope_coord(t.x_km, t.y_km)
            if not p:
                continue
            x, y, rel, rng = p
            is_locked = locked is t
            fill = col["warn"] if t.damaged else col["bright"] if is_locked else col["text"]
            r = 5 if is_locked or t.damaged else 4
            self.draw_target_symbol(x, y, r, fill, locked=is_locked)
            if self.ecm_strength_for_track(t) > 0.0:
                self.crt_text(x + 12, y + 13, "ECM", fill=col["warn"], font=("Consolas", 8, "bold"), anchor="nw", bg=True)

            hrad = math.radians(t.hdg)
            future_x = t.x_km + math.sin(hrad) * 20
            future_y = t.y_km + math.cos(hrad) * 20
            fp = self.bscope_coord(future_x, future_y)
            if fp:
                fx, fy, _, _ = fp
                self.canvas.create_line(x, y, fx, fy, fill=fill, width=1)
            if self.show_track_labels.get():
                self.draw_track_label(x, y, t, col["warn"] if t.damaged else col["bright"] if is_locked else col["text"], compact=False)

    def draw_bscope_mode(self):
        self.draw_bscope_grid()
        self.draw_bscope_sweep()
        self.draw_bscope_tracks()

    # ---------------------------- E-Scope ----------------------------
    def escope_bounds(self):
        left = self.canvas_w * 0.09
        right = self.canvas_w * 0.91
        top = self.canvas_h * 0.12
        bottom = self.canvas_h * 0.86
        return left, top, right, bottom

    def draw_escope_mode(self):
        col = self.colors[self.theme]
        left, top, right, bottom = self.escope_bounds()
        max_alt = max(300.0, max([float(t.alt) for t in self.tracks], default=300.0))

        self.canvas.create_rectangle(left, top, right, bottom, outline=col["grid"], width=2)
        self.crt_text((left + right) / 2, top - 24, "E-SCOPE / RANGE-ALTITUDE", fill=col["bright"], font=("Consolas", 13, "bold"), bg=True)

        for r_km in self.range_rings():
            x = left + r_km / self.max_range_km * (right - left)
            self.canvas.create_line(x, top, x, bottom, fill=col["dim"])
            self.draw_range_label(x, bottom + 20, r_km, anchor="center")

        for i in range(0, 6):
            alt = int(i * max_alt / 5)
            y = bottom - i / 5 * (bottom - top)
            self.canvas.create_line(left, y, right, y, fill=col["dim"])
            self.crt_text(left - 10, y, f"ALT {alt:03d}", fill=col["text"], font=("Consolas", self.grid_font_size, "bold"), anchor="e", bg=True)

        locked = self.get_locked_track()
        for t in self.tracks:
            rng = self.range_of_track(t)
            if rng > self.max_range_km:
                continue
            x = left + rng / self.max_range_km * (right - left)
            y = bottom - min(float(t.alt), max_alt) / max_alt * (bottom - top)
            fill = col["warn"] if t.damaged else col["bright"] if locked is t else col["text"]
            self.draw_target_symbol(x, y, 5, fill, locked=locked is t)
            if self.ecm_strength_for_track(t) > 0.0:
                self.crt_text(x + 11, y + 10, "ECM", fill=col["warn"], font=("Consolas", 8, "bold"), anchor="nw", bg=True)
            if self.show_track_labels.get():
                self.draw_track_label(x, y, t, fill, compact=True)

    # ---------------------------- TWS/RWS/FCS Modes ----------------------------
    def draw_tws_track_file(self):
        col = self.colors[self.theme]
        tracks = sorted([t for t in self.tracks if self.range_of_track(t) <= self.max_range_km], key=self.range_of_track)
        left = 18
        top = self.canvas_h - 160
        width = min(520, self.canvas_w - 36)
        row_h = 22
        height = 34 + row_h * min(5, len(tracks))
        self.canvas.create_rectangle(left, top, left + width, top + height, outline=col["grid"], fill=col["bg"], width=2)
        self.crt_text(left + 10, top + 10, "TWS TRACK FILE   ID     BRG    RNG    IFF       ASPECT", fill=col["bright"], font=("Consolas", 10, "bold"), anchor="nw", bg=False)
        for i, t in enumerate(tracks[:5]):
            sol = self.fcs_solution(t)
            locked_mark = "*" if self.get_locked_track() is t else " "
            row = f"{locked_mark}{i + 1:02d}  {t.track_id:>4}   {int(sol['bearing']):03d}°  {int(sol['range']):03d}km  {t.iff:<8}  {sol['aspect']}"
            self.crt_text(left + 12, top + 34 + i * row_h, row, fill=col["text"], font=("Consolas", 10, "bold"), anchor="nw", bg=False)

    def draw_rws_mode(self):
        self.draw_ppi_grid(sector=True, sector_width=120, title="RWS / RANGE-WHILE-SEARCH")
        self.draw_ppi_sweep(sector=True, sector_width=120)
        self.draw_ppi_tracks(sector=True, sector_width=120, labels=False)
        col = self.colors[self.theme]
        self.crt_text(self.cx, self.canvas_h - 46, "SEARCH VOLUME 120°   RAW CONTACTS ONLY", fill=col["text"], font=("Consolas", 11, "bold"), bg=True)

    def draw_tws_mode(self):
        self.draw_ppi_grid(sector=False, title="TWS / TRACK-WHILE-SCAN")
        self.draw_ppi_sweep(sector=False)
        self.draw_ppi_tracks(sector=False, labels=True)
        self.draw_tws_track_file()

    def draw_lock_mode(self, title="STT LOCK"):
        self.draw_ppi_grid(sector=False, title=title)
        self.draw_ppi_sweep(sector=False)
        self.draw_ppi_tracks(sector=False, labels=True, dim_others=True)
        self.draw_fcs_overlay(full_panel=(title == "FCS / FIRE CONTROL"))

    def draw_acm_mode(self):
        col = self.colors[self.theme]
        self.draw_ppi_grid(sector=True, sector_width=36, title="ACM BORESIGHT")
        self.draw_ppi_sweep(sector=True, sector_width=36)
        self.draw_ppi_tracks(sector=True, sector_width=36, labels=True, dim_others=True)
        s = 46
        # Lowered the ACM boresight reticle so it no longer crowds the top title/angle labels.
        acm_y = self.cy - self.radius + 176
        self.canvas.create_rectangle(self.cx - s, acm_y - 42, self.cx + s, acm_y + 42, outline=col["bright"], width=2)
        self.canvas.create_line(self.cx, acm_y - 62, self.cx, acm_y + 62, fill=col["bright"], width=2)
        self.canvas.create_line(self.cx - 60, acm_y, self.cx + 60, acm_y, fill=col["bright"], width=2)
        self.crt_text(self.cx, self.canvas_h - 48, "AUTO-ACQUIRE: ±18° / 90 km", fill=col["text"], font=("Consolas", 11, "bold"), bg=True)
        self.draw_fcs_overlay(full_panel=False)

    def draw_fcs_overlay(self, full_panel=False):
        col = self.colors[self.theme]
        target = self.get_locked_track()
        master = "ARM" if self.fcs_master_arm.get() else "SAFE"

        if not target:
            self.crt_text(self.cx, self.cy, f"FCS {master} / NO LOCK", fill=col["warn"], font=("Consolas", 16, "bold"), bg=True)
            return

        sol = self.fcs_solution(target)
        tx, ty = self.km_to_px_ppi(target.x_km, target.y_km)
        self.canvas.create_line(self.cx, self.cy, tx, ty, fill=col["dim"], width=2)

        if self.show_lead_cue.get() and sol["lead_range"] <= self.max_range_km:
            lx, ly = self.km_to_px_ppi(sol["lead_x"], sol["lead_y"])
            self.canvas.create_oval(lx - 7, ly - 7, lx + 7, ly + 7, outline=col["warn"], width=2)
            self.canvas.create_line(tx, ty, lx, ly, fill=col["warn"], width=1)
            self.crt_text(lx + 12, ly + 10, "LEAD", fill=col["warn"], font=("Consolas", 9, "bold"), anchor="nw", bg=True)

        ready = (
            self.fcs_master_arm.get()
            and self.missile_ammo > 0
            and self.missile_cooldown <= 0.0
            and 6 <= sol["range"] <= min(self.max_range_km, 220)
        )
        cue = "SHOOT" if ready else "HOLD"
        cue_fill = col["warn"] if ready else col["text"]

        box_x = self.canvas_w - 270 if full_panel else 18
        box_y = 110 if full_panel else self.canvas_h - 166
        box_w = 248
        box_h = 202
        self.canvas.create_rectangle(box_x, box_y, box_x + box_w, box_y + box_h, outline=col["grid"], fill=col["bg"], width=2)
        ecm_strength = self.ecm_strength_for_track(target)
        ecm_text = "OFF" if ecm_strength <= 0.0 else f"{self.ecm_mode_var.get()} {int(ecm_strength * 100):02d}%"
        lines = [
            f"FCS {master}  {cue}",
            f"LOCK TRK {target.track_id}  {target.iff}",
            f"BRG {int(sol['bearing']):03d}°   RNG {sol['range']:06.1f} km",
            f"HDG {int(target.hdg):03d}°   SPD {int(target.spd):03d}",
            f"ALT {int(target.alt):03d}    ASP {sol['aspect']}",
            f"CLOS {sol['closure']:+06.1f}  LEAD {sol['lead_seconds']:04.1f}s",
            f"MSL {self.missile_ammo:02d}/{self.max_missile_ammo:02d}  CD {self.missile_cooldown:03.1f}s",
            f"GUIDE PN-{self.missile_nav_constant:.1f}  MAX {int(self.missile_max_speed_kmh)}",
            f"ECM {ecm_text}",
            f"EVAS {'ON' if getattr(target, 'evading', False) else 'OFF'}  LP {int(getattr(target, 'lock_pressure', 0.0) * 100):02d}%",
            f"NCTR {target.nctr}",
        ]
        for i, line in enumerate(lines):
            fill = cue_fill if i == 0 else col["text"]
            self.crt_text(box_x + 10, box_y + 10 + i * 16, line, fill=fill, font=("Consolas", 10, "bold"), anchor="nw", bg=False)

        fire_hint = "READY" if ready else self.fcs_state_var.get()
        self.crt_text(
            self.cx,
            self.cy + self.radius + 34,
            f"STEER {int(sol['lead_bearing']):03d}°  TARGET {int(sol['bearing']):03d}°   {fire_hint}",
            fill=col["bright"] if ready else col["text"],
            font=("Consolas", 12, "bold"),
            bg=True,
        )

    def draw_ecm_monitor_mode(self):
        col = self.colors[self.theme]
        self.draw_ppi_grid(sector=False, title="ECM MONITOR / JAM ANALYSIS")
        self.draw_ppi_sweep(sector=False)
        self.draw_ppi_tracks(sector=False, labels=True, dim_others=False)

        ecm_tracks = [t for t in self.tracks if self.ecm_strength_for_track(t) > 0.0 and self.range_of_track(t) <= self.max_range_km]
        box_x = 18
        box_y = self.canvas_h - 190
        box_w = min(560, self.canvas_w - 36)
        box_h = 160
        self.canvas.create_rectangle(box_x, box_y, box_x + box_w, box_y + box_h, outline=col["grid"], fill=col["bg"], width=2)
        self.crt_text(box_x + 10, box_y + 10, "ECM TRACKS      ID     TYPE     STR   BRG    RNG", fill=col["bright"], font=("Consolas", 10, "bold"), anchor="nw", bg=False)

        if not ecm_tracks:
            self.crt_text(box_x + 12, box_y + 42, "NO ACTIVE JAMMERS / GLOBAL NOISE OFF", fill=col["text"], font=("Consolas", 10, "bold"), anchor="nw", bg=False)
        else:
            for i, t in enumerate(sorted(ecm_tracks, key=self.range_of_track)[:6]):
                strength = self.ecm_strength_for_track(t)
                brg = int(self.bearing_of_track(t))
                rng = int(self.range_of_track(t))
                bar = "#" * max(1, int(strength * 10))
                row = f"{i + 1:02d}             {t.track_id:>4}   {self.ecm_mode_var.get():<7}  {int(strength*100):02d}%   {brg:03d}°   {rng:03d}km  {bar}"
                self.crt_text(box_x + 12, box_y + 40 + i * 18, row, fill=col["text"], font=("Consolas", 10, "bold"), anchor="nw", bg=False)

        if self.global_ecm.get():
            self.crt_text(self.cx, self.canvas_h - 36, f"GLOBAL ECM NOISE ACTIVE / {self.ecm_mode_var.get()} / {int(float(self.ecm_strength_var.get()) * 100):02d}%", fill=col["warn"], font=("Consolas", 11, "bold"), bg=True)

    # ---------------------------- Missile / effects drawing ----------------------------
    def draw_missiles_ppi(self):
        col = self.colors[self.theme]
        for m in self.missiles:
            trail_points = []
            for px_km, py_km in m.trail:
                px, py = self.km_to_px_ppi(px_km, py_km)
                if self.px_in_ppi(px, py):
                    trail_points.append((px, py))
            for i in range(1, len(trail_points)):
                self.canvas.create_line(
                    trail_points[i - 1][0], trail_points[i - 1][1],
                    trail_points[i][0], trail_points[i][1],
                    fill=col["dim"], width=1,
                )

            x, y = self.km_to_px_ppi(m.x_km, m.y_km)
            if not self.px_in_ppi(x, y):
                continue
            rad = math.radians(m.hdg)
            nose_x = x + math.sin(rad) * 10
            nose_y = y - math.cos(rad) * 10
            tail_x = x - math.sin(rad) * 7
            tail_y = y + math.cos(rad) * 7
            missile_fill = col["dim"] if m.guidance_lost else col["warn"]
            self.canvas.create_line(tail_x, tail_y, nose_x, nose_y, fill=missile_fill, width=3)
            self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, outline=col["bright" if not m.guidance_lost else "dim"], width=1)
            label = m.missile_id if not m.guidance_lost else f"{m.missile_id} LOST"
            self.crt_text(x + 9, y + 6, label, fill=missile_fill, font=("Consolas", 8, "bold"), anchor="nw", bg=True)

    def draw_missiles_bscope(self):
        col = self.colors[self.theme]
        for m in self.missiles:
            p = self.bscope_coord(m.x_km, m.y_km)
            if not p:
                continue
            x, y, _, _ = p
            missile_fill = col["dim"] if m.guidance_lost else col["warn"]
            self.canvas.create_rectangle(x - 4, y - 4, x + 4, y + 4, outline=missile_fill, width=2)
            self.crt_text(x + 8, y + 6, m.missile_id, fill=missile_fill, font=("Consolas", 8, "bold"), anchor="nw", bg=True)

    def draw_missiles_escope(self):
        col = self.colors[self.theme]
        left, top, right, bottom = self.escope_bounds()
        for m in self.missiles:
            rng = math.hypot(m.x_km, m.y_km)
            if rng > self.max_range_km:
                continue
            x = left + rng / self.max_range_km * (right - left)
            # Missiles are shown as a low-altitude weapon trace on E-scope.
            y = bottom - 0.08 * (bottom - top)
            missile_fill = col["dim"] if m.guidance_lost else col["warn"]
            self.canvas.create_rectangle(x - 4, y - 4, x + 4, y + 4, outline=missile_fill, width=2)
            self.crt_text(x + 8, y, m.missile_id, fill=missile_fill, font=("Consolas", 8, "bold"), anchor="w", bg=True)

    def draw_weapon_overlays(self, mode):
        if mode in ("B-SCOPE",):
            self.draw_missiles_bscope()
        elif mode in ("E-SCOPE",):
            self.draw_missiles_escope()
        else:
            self.draw_missiles_ppi()

    # ---------------------------- Global overlays ----------------------------
    def draw_scanlines(self):
        col = self.colors[self.theme]
        for y in range(0, int(self.canvas_h), 4):
            self.canvas.create_line(0, y, self.canvas_w, y, fill=col["scanline"])

    def draw_noise(self):
        col = self.colors[self.theme]
        area = self.canvas_w * self.canvas_h
        count = max(40, min(180, int(area / 4500)))
        if self.global_ecm.get():
            count = int(count * (1.0 + 1.8 * float(self.ecm_strength_var.get())))
        for _ in range(count):
            x = random.randint(0, max(1, int(self.canvas_w) - 1))
            y = random.randint(0, max(1, int(self.canvas_h) - 1))
            color = col["dim"] if random.random() < 0.88 else col["grid"]
            self.canvas.create_rectangle(x, y, x + 1, y + 1, fill=color, outline="")

    def draw_status_text(self):
        col = self.colors[self.theme]
        flicker = random.choice(["", ".", "", ""])
        mode = self.mode_var.get()
        locked = self.get_locked_track()
        lock_text = locked.track_id if locked else "----"
        arm_text = "ARM" if self.fcs_master_arm.get() else "SAFE"
        if mode in ("SECTOR 120", "RWS"):
            sweep_readout = int(self.get_sector_sweep_bearing(120))
        elif mode == "B-SCOPE":
            sweep_readout = int(self.get_sector_sweep_bearing(140))
        elif mode == "ACM BORESIGHT":
            sweep_readout = int(self.get_sector_sweep_bearing(36))
        else:
            sweep_readout = int(self.sweep_angle)
        text = (
            f"{mode} MODE{flicker}\n"
            f"RANGE {self.max_range_km:03d} KM\n"
            f"SWEEP {sweep_readout:03d}°\n"
            f"TRACKS {len(self.tracks):02d}  EVAD {sum(1 for t in self.tracks if getattr(t, 'evading', False)):02d}\n"
            f"LOCK {lock_text}\n"
            f"FCS {arm_text}  {self.fcs_state_var.get()}\n"
            f"MSL {self.missile_ammo:02d}  AIR {len(self.missiles):02d}\n"
            f"HIT {self.kills:02d} MISS {self.misses:02d}/{self.shots_fired:02d}\n"
            f"ECM {'ON' if (self.global_ecm.get() or any(self.ecm_strength_for_track(t) > 0 for t in self.tracks)) else 'OFF'}\n"
            f"TIME {time.strftime('%H:%M:%S')}"
        )
        self.crt_text(18, 18, text, fill=col["text"], font=("Consolas", 11, "bold"), anchor="nw", bg=True, pad=4, justify="left")

    def draw_range_ladder(self):
        if not self.show_readable_scale.get():
            return
        col = self.colors[self.theme]
        x = self.canvas_w - 74
        top = self.cy - self.radius
        bottom = self.cy + self.radius
        self.canvas.create_line(x, top, x, bottom, fill=col["grid"], width=2)
        for r_km in self.range_rings():
            y = bottom - r_km / self.max_range_km * (bottom - top)
            self.canvas.create_line(x - 10, y, x + 10, y, fill=col["grid"], width=2)
            self.crt_text(x - 14, y, f"{int(r_km):03d}", fill=col["text"], font=("Consolas", 9, "bold"), anchor="e", bg=True)
        self.crt_text(x, top - 18, "KM", fill=col["bright"], font=("Consolas", 10, "bold"), bg=True)

    def draw_vignette(self):
        col = self.colors[self.theme]
        t = max(8, int(min(self.canvas_w, self.canvas_h) * 0.018))
        self.canvas.create_rectangle(0, 0, self.canvas_w, t, fill=col["bg"], outline="")
        self.canvas.create_rectangle(0, self.canvas_h - t, self.canvas_w, self.canvas_h, fill=col["bg"], outline="")
        self.canvas.create_rectangle(0, 0, t, self.canvas_h, fill=col["bg"], outline="")
        self.canvas.create_rectangle(self.canvas_w - t, 0, self.canvas_w, self.canvas_h, fill=col["bg"], outline="")

    # ---------------------------- Main loop ----------------------------
    def animate(self):
        now = time.time()
        dt = now - self.last_time
        self.last_time = now

        self.lock_reacquire_delay = max(0.0, self.lock_reacquire_delay - dt)

        if self.running:
            self.sweep_phase += self.sweep_speed_deg * dt
            self.sweep_angle = self.sweep_phase % 360
            self.update_tracks(dt)
            self.update_missiles(dt)

        self.auto_acquire_for_mode()

        self.draw_background()
        self.canvas.delete("all")

        # Draw CRT texture behind the symbology so labels remain readable.
        self.draw_noise()
        self.draw_scanlines()

        mode = self.mode_var.get()
        if mode == "PPI 360":
            self.draw_ppi_mode(sector=False, raw=False, title="PPI 360")
        elif mode == "RWS":
            self.draw_rws_mode()
        elif mode == "TWS":
            self.draw_tws_mode()
        elif mode == "SECTOR 120":
            self.draw_ppi_mode(sector=True, raw=False, sector_width=120, title="SECTOR 120")
        elif mode == "B-SCOPE":
            self.draw_bscope_mode()
        elif mode == "E-SCOPE":
            self.draw_escope_mode()
        elif mode == "STT LOCK":
            self.draw_lock_mode(title="STT LOCK")
        elif mode == "FCS":
            self.draw_lock_mode(title="FCS / FIRE CONTROL")
        elif mode == "ECM MONITOR":
            self.draw_ecm_monitor_mode()
        elif mode == "ACM BORESIGHT":
            self.draw_acm_mode()
        elif mode == "RAW CRT":
            self.draw_ppi_mode(sector=False, raw=True, title="RAW CRT", labels=False)

        self.draw_weapon_overlays(mode)
        self.draw_range_ladder()
        self.draw_status_text()
        self.draw_vignette()
        self.root.after(33, self.animate)


if __name__ == "__main__":
    root = tk.Tk()
    app = RadarSim(root)
    root.mainloop()
