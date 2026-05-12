import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
import math
import random
import time


@dataclass
class Track:
    track_id: str
    iff: str
    alt: int
    hdg: float
    spd: float
    nctr: str
    x_km: float
    y_km: float
    vector_len: float = 18.0


class RadarSim:
    def __init__(self, root):
        self.root = root
        self.root.title("Cold War CRT Radar Simulator")
        self.root.geometry("1100x760")

        self.canvas_w = 760
        self.canvas_h = 720
        self.cx = self.canvas_w / 2
        self.cy = self.canvas_h / 2
        self.radius = 300

        self.max_range_km = 250
        self.sweep_angle = 0.0
        self.sweep_speed_deg = 85.0
        self.running = True
        self.speed_scale = 35.0
        self.theme = "green"
        self.track_font_size = 7
        self.last_time = time.time()
        self.tracks = []

        self.mode_var = tk.StringVar(value="PPI 360")

        self.colors = {
            "green": {
                "bg": "#020702",
                "grid": "#0b5f2a",
                "dim": "#063817",
                "bright": "#39ff88",
                "text": "#7dffb1",
                "scanline": "#031206",
            },
            "amber": {
                "bg": "#080502",
                "grid": "#704b00",
                "dim": "#3d2900",
                "bright": "#ffbf3d",
                "text": "#ffd27a",
                "scanline": "#160e00",
            }
        }

        self.build_ui()
        self.add_demo_tracks()
        self.animate()

    def build_ui(self):
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(main, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        panel = ttk.Frame(main, width=270)
        panel.pack(side="right", fill="y", padx=10, pady=10)
        panel.pack_propagate(False)

        ttk.Label(panel, text="Radar Mode").pack(anchor="w")
        modes = ["PPI 360", "SECTOR 120", "B-SCOPE", "RAW CRT"]
        ttk.Combobox(
            panel,
            textvariable=self.mode_var,
            values=modes,
            state="readonly",
            width=18
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(panel, text="Track Setup").pack(anchor="w", pady=(0, 8))
        self.entries = {}

        fields = [
            ("track_id", "TRACK", "041"),
            ("iff", "IFF", "UNKNOWN"),
            ("alt", "ALT", "120"),
            ("hdg", "HDG", "275"),
            ("spd", "SPD", "420"),
            ("nctr", "NCTR", "MiG-29"),
            ("range", "Range km", "155"),
            ("bearing", "Bearing deg", "060"),
        ]

        for key, label, default in fields:
            ttk.Label(panel, text=label).pack(anchor="w")
            e = ttk.Entry(panel, width=20)
            e.insert(0, default)
            e.pack(anchor="w", pady=(0, 5))
            self.entries[key] = e

        ttk.Button(panel, text="Add Track", command=self.add_track_from_ui).pack(fill="x", pady=5)
        ttk.Button(panel, text="Add Demo Tracks", command=self.add_demo_tracks).pack(fill="x", pady=5)
        ttk.Button(panel, text="Clear Tracks", command=self.clear_tracks).pack(fill="x", pady=5)
        ttk.Button(panel, text="Pause / Resume", command=self.toggle_running).pack(fill="x", pady=5)

        ttk.Separator(panel).pack(fill="x", pady=10)

        ttk.Label(panel, text="Theme").pack(anchor="w")
        ttk.Button(panel, text="Green CRT", command=lambda: self.set_theme("green")).pack(fill="x", pady=2)
        ttk.Button(panel, text="Amber CRT", command=lambda: self.set_theme("amber")).pack(fill="x", pady=2)

        ttk.Separator(panel).pack(fill="x", pady=10)

        ttk.Label(panel, text="Track Label Size").pack(anchor="w")
        ttk.Button(panel, text="Smaller", command=lambda: self.change_track_font(-1)).pack(fill="x", pady=2)
        ttk.Button(panel, text="Bigger", command=lambda: self.change_track_font(1)).pack(fill="x", pady=2)

        ttk.Separator(panel).pack(fill="x", pady=10)

        notes = (
            "0° = North\n"
            "90° = East\n"
            "180° = South\n"
            "270° = West\n\n"
            "OBS: crop left canvas.\n"
            "Kdenlive: grain,\n"
            "flicker, blur."
        )
        ttk.Label(panel, text=notes, justify="left").pack(anchor="w")

    def on_canvas_resize(self, event):
        self.canvas_w = max(320, event.width)
        self.canvas_h = max(260, event.height)
        self.cx = self.canvas_w / 2
        self.cy = self.canvas_h / 2
        self.radius = min(self.canvas_w, self.canvas_h) * 0.42

    def change_track_font(self, delta):
        self.track_font_size = max(5, min(12, self.track_font_size + delta))

    def set_theme(self, theme):
        self.theme = theme

    def clear_tracks(self):
        self.tracks.clear()

    def toggle_running(self):
        self.running = not self.running

    def add_demo_tracks(self):
        self.tracks.extend([
            Track("041", "UNKNOWN", 120, 275, 420, "MiG-29", 115, 85),
            Track("114", "HOSTILE?", 80, 245, 510, "Su-22", 170, -40),
            Track("027", "FRIENDLY", 210, 90, 460, "F-4F", -130, -70),
            Track("063", "UNKNOWN", 60, 315, 380, "An-26", 40, 170),
        ])

    def add_track_from_ui(self):
        try:
            track_id = self.entries["track_id"].get().strip() or "000"
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
        except ValueError:
            print("Invalid track input.")

    def update_tracks(self, dt):
        for t in self.tracks:
            distance_km = (t.spd / 3600.0) * dt * self.speed_scale
            rad = math.radians(t.hdg)

            t.x_km += math.sin(rad) * distance_km
            t.y_km += math.cos(rad) * distance_km

            dist = math.hypot(t.x_km, t.y_km)
            if dist > self.max_range_km * 1.05:
                t.x_km *= -0.85
                t.y_km *= -0.85

    def signed_angle(self, angle, center=0):
        return (angle - center + 180) % 360 - 180

    def angle_difference(self, a, b):
        return abs((a - b + 180) % 360 - 180)

    def bearing_of_track(self, t):
        return math.degrees(math.atan2(t.x_km, t.y_km)) % 360

    def km_to_px_ppi(self, x_km, y_km):
        scale = self.radius / self.max_range_km
        x = self.cx + x_km * scale
        y = self.cy - y_km * scale
        return x, y

    def px_in_ppi(self, x, y):
        return math.hypot(x - self.cx, y - self.cy) <= self.radius

    def get_sector_sweep_bearing(self, width=120):
        half = width / 2
        p = self.sweep_angle % (width * 2)
        offset = -half + p if p <= width else half - (p - width)
        return offset % 360

    def draw_background(self):
        col = self.colors[self.theme]
        bg = col["bg"] if random.random() > 0.08 else "#000000"
        self.canvas.configure(bg=bg)

    def draw_ppi_grid(self, sector=False):
        col = self.colors[self.theme]

        if not sector:
            self.canvas.create_oval(
                self.cx - self.radius, self.cy - self.radius,
                self.cx + self.radius, self.cy + self.radius,
                outline=col["grid"], width=2
            )

            for r_km in [50, 100, 150, 200, 250]:
                r = self.radius * r_km / self.max_range_km
                self.canvas.create_oval(
                    self.cx - r, self.cy - r,
                    self.cx + r, self.cy + r,
                    outline=col["dim"], width=1
                )
                self.canvas.create_text(
                    self.cx + 8, self.cy - r + 10,
                    text=f"{r_km}",
                    fill=col["dim"],
                    font=("Consolas", 8)
                )

            for deg in range(0, 360, 30):
                rad = math.radians(deg)
                x = self.cx + math.sin(rad) * self.radius
                y = self.cy - math.cos(rad) * self.radius
                self.canvas.create_line(self.cx, self.cy, x, y, fill=col["dim"])

                tx = self.cx + math.sin(rad) * (self.radius + 14)
                ty = self.cy - math.cos(rad) * (self.radius + 14)
                self.canvas.create_text(
                    tx, ty,
                    text=f"{deg:03d}",
                    fill=col["grid"],
                    font=("Consolas", 8)
                )

            self.canvas.create_line(self.cx - self.radius, self.cy, self.cx + self.radius, self.cy, fill=col["dim"])
            self.canvas.create_line(self.cx, self.cy - self.radius, self.cx, self.cy + self.radius, fill=col["dim"])
            return

        # Sector mode: 120° wedge centered north.
        start_canvas_angle = 30
        extent = 120

        for r_km in [50, 100, 150, 200, 250]:
            r = self.radius * r_km / self.max_range_km
            self.canvas.create_arc(
                self.cx - r, self.cy - r,
                self.cx + r, self.cy + r,
                start=start_canvas_angle,
                extent=extent,
                style="arc",
                outline=col["dim"],
                width=1
            )

        for brg in [-60, -30, 0, 30, 60]:
            b = brg % 360
            rad = math.radians(b)
            x = self.cx + math.sin(rad) * self.radius
            y = self.cy - math.cos(rad) * self.radius
            self.canvas.create_line(self.cx, self.cy, x, y, fill=col["dim"])

            tx = self.cx + math.sin(rad) * (self.radius + 14)
            ty = self.cy - math.cos(rad) * (self.radius + 14)
            self.canvas.create_text(
                tx, ty,
                text=f"{b:03.0f}",
                fill=col["grid"],
                font=("Consolas", 8)
            )

        self.canvas.create_arc(
            self.cx - self.radius, self.cy - self.radius,
            self.cx + self.radius, self.cy + self.radius,
            start=start_canvas_angle,
            extent=extent,
            style="arc",
            outline=col["grid"],
            width=2
        )

    def draw_ppi_sweep(self, sector=False):
        col = self.colors[self.theme]
        base_angle = self.get_sector_sweep_bearing(120) if sector else self.sweep_angle

        for i in range(12):
            angle = base_angle - i * 3.0

            if sector and abs(self.signed_angle(angle, 0)) > 62:
                continue

            rad = math.radians(angle)
            x = self.cx + math.sin(rad) * self.radius
            y = self.cy - math.cos(rad) * self.radius

            color = col["bright"] if i == 0 else col["grid"] if i < 5 else col["dim"]
            width = 3 if i == 0 else 1

            self.canvas.create_line(self.cx, self.cy, x, y, fill=color, width=width)

    def draw_track_label(self, x, y, t, color):
        label = (
            f"TRK {t.track_id}\n"
            f"IFF {t.iff}\n"
            f"ALT {t.alt:03d}\n"
            f"HDG {int(t.hdg):03d}\n"
            f"SPD {int(t.spd):03d}\n"
            f"NCTR {t.nctr}"
        )

        self.canvas.create_text(
            x + 9, y - 8,
            text=label,
            fill=color,
            font=("Consolas", self.track_font_size),
            anchor="nw"
        )

    def draw_ppi_tracks(self, sector=False, raw=False):
        col = self.colors[self.theme]
        active_sweep = self.get_sector_sweep_bearing(120) if sector else self.sweep_angle

        for t in self.tracks:
            brg = self.bearing_of_track(t)

            if sector and abs(self.signed_angle(brg, 0)) > 60:
                continue

            x, y = self.km_to_px_ppi(t.x_km, t.y_km)

            if not self.px_in_ppi(x, y):
                continue

            sweep_dist = self.angle_difference(active_sweep, brg)

            if sweep_dist < 5:
                fill = col["bright"]
                r = 5
            elif sweep_dist < 18:
                fill = col["text"]
                r = 4
            else:
                fill = col["grid"]
                r = 3

            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline="")

            hrad = math.radians(t.hdg)
            vx = x + math.sin(hrad) * t.vector_len
            vy = y - math.cos(hrad) * t.vector_len
            self.canvas.create_line(x, y, vx, vy, fill=fill, width=1)

            if not raw:
                self.draw_track_label(x, y, t, col["text"])

    def bscope_bounds(self):
        left = self.canvas_w * 0.08
        right = self.canvas_w * 0.92
        top = self.canvas_h * 0.12
        bottom = self.canvas_h * 0.88
        return left, top, right, bottom

    def draw_bscope_grid(self):
        col = self.colors[self.theme]
        left, top, right, bottom = self.bscope_bounds()

        self.canvas.create_rectangle(left, top, right, bottom, outline=col["grid"], width=2)

        for i in range(1, 6):
            y = bottom - i * (bottom - top) / 6
            self.canvas.create_line(left, y, right, y, fill=col["dim"])
            rng = int(i * self.max_range_km / 6)
            self.canvas.create_text(left + 8, y - 8, text=f"{rng}", fill=col["dim"], font=("Consolas", 8), anchor="w")

        for brg in [-60, -30, 0, 30, 60]:
            x = left + (brg + 70) / 140 * (right - left)
            self.canvas.create_line(x, top, x, bottom, fill=col["dim"])
            self.canvas.create_text(x, bottom + 14, text=f"{brg:+03d}", fill=col["grid"], font=("Consolas", 8))

        self.canvas.create_text(
            (left + right) / 2, top - 18,
            text="B-SCOPE / BEARING-RANGE DISPLAY",
            fill=col["text"],
            font=("Consolas", 10)
        )

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

        for t in self.tracks:
            p = self.bscope_coord(t.x_km, t.y_km)

            if not p:
                continue

            x, y, rel, rng = p
            r = 4

            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=col["bright"], outline="")

            hrad = math.radians(t.hdg)
            future_x = t.x_km + math.sin(hrad) * 20
            future_y = t.y_km + math.cos(hrad) * 20
            fp = self.bscope_coord(future_x, future_y)

            if fp:
                fx, fy, _, _ = fp
                self.canvas.create_line(x, y, fx, fy, fill=col["text"], width=1)

            self.draw_track_label(x, y, t, col["text"])

    def draw_scanlines(self):
        col = self.colors[self.theme]

        for y in range(0, int(self.canvas_h), 4):
            self.canvas.create_line(0, y, self.canvas_w, y, fill=col["scanline"])

    def draw_noise(self):
        col = self.colors[self.theme]
        area = self.canvas_w * self.canvas_h
        count = max(50, min(230, int(area / 3500)))

        for _ in range(count):
            x = random.randint(0, max(1, int(self.canvas_w) - 1))
            y = random.randint(0, max(1, int(self.canvas_h) - 1))
            color = col["dim"] if random.random() < 0.86 else col["grid"]
            self.canvas.create_rectangle(x, y, x + 1, y + 1, fill=color, outline="")

    def draw_status_text(self):
        col = self.colors[self.theme]
        flicker = random.choice(["", ".", "", ""])
        mode = self.mode_var.get()

        text = (
            f"{mode} MODE{flicker}\n"
            f"RANGE {self.max_range_km} KM\n"
            f"SWEEP {int(self.sweep_angle):03d} DEG\n"
            f"TRACKS {len(self.tracks):02d}\n"
            f"TIME {time.strftime('%H:%M:%S')}"
        )

        self.canvas.create_text(
            18, 18,
            text=text,
            fill=col["text"],
            font=("Consolas", 10),
            anchor="nw"
        )

    def draw_vignette(self):
        col = self.colors[self.theme]
        t = max(8, int(min(self.canvas_w, self.canvas_h) * 0.018))

        self.canvas.create_rectangle(0, 0, self.canvas_w, t, fill=col["bg"], outline="")
        self.canvas.create_rectangle(0, self.canvas_h - t, self.canvas_w, self.canvas_h, fill=col["bg"], outline="")
        self.canvas.create_rectangle(0, 0, t, self.canvas_h, fill=col["bg"], outline="")
        self.canvas.create_rectangle(self.canvas_w - t, 0, self.canvas_w, self.canvas_h, fill=col["bg"], outline="")

    def draw_ppi_mode(self, sector=False, raw=False):
        self.draw_ppi_grid(sector=sector)
        self.draw_ppi_sweep(sector=sector)
        self.draw_ppi_tracks(sector=sector, raw=raw)

    def draw_bscope_mode(self):
        self.draw_bscope_grid()
        self.draw_bscope_sweep()
        self.draw_bscope_tracks()

    def animate(self):
        now = time.time()
        dt = now - self.last_time
        self.last_time = now

        if self.running:
            self.sweep_angle = (self.sweep_angle + self.sweep_speed_deg * dt) % 360
            self.update_tracks(dt)

        self.draw_background()
        self.canvas.delete("all")

        mode = self.mode_var.get()

        if mode == "PPI 360":
            self.draw_ppi_mode(sector=False, raw=False)
        elif mode == "SECTOR 120":
            self.draw_ppi_mode(sector=True, raw=False)
        elif mode == "B-SCOPE":
            self.draw_bscope_mode()
        elif mode == "RAW CRT":
            self.draw_ppi_mode(sector=False, raw=True)

        self.draw_noise()
        self.draw_scanlines()
        self.draw_status_text()
        self.draw_vignette()

        self.root.after(33, self.animate)


if __name__ == "__main__":
    root = tk.Tk()
    app = RadarSim(root)
    root.mainloop()
