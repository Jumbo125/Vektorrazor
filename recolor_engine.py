# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""
Bild-Umfaerber GUI v4.5
---------------------
Ein einfaches Tkinter-Tool zum Umfaerben kompletter Farbbereiche in Bildern.

Neu in v2/v3/v4:
- Basis-Modus: Farben automatisch per Schwellenwert erkennen
- erkannte Farbbereiche automatisch in kontrastreiche, exakte RGB-Farben umwandeln
- Erweiterter Modus: manuelle Farbauswahl wie bisher
- v3: Vorschau mit gedrueckter linker Maustaste verschieben, kurzer Klick pickt Farbe
- v4: Bildvorbereitung vor der Farberkennung: Helligkeit, Kontrast, Tonwert/Gamma
- v4.3: Farbtabelle im Basis-Modus wieder sichtbar, Bedienbereich hoeher
- v4.4: kompletter Basis-Modus vertikal scrollbar, damit die Farbtabelle auf kleineren Bildschirmen erreichbar bleibt
- v4.5: Spezialmodus "Logo-Maske": lokale Kontrastmaske gegen Schatten/Verläufe im Hintergrund

Funktionen:
- Bild laden
- Originalvorschau links, bearbeitete Vorschau rechts
- Zoom mit Mausrad
- Verschieben der Vorschau mit gedrueckter linker, rechter oder mittlerer Maustaste
- Basis-Modus: automatische Farberkennung + exakte Kontrastfarben
- Basis-Modus v4: Bildvorbereitung wirkt vor Farberkennung und Export
- Erweiterter Modus: Farbwert mit linker Maustaste aufnehmen und manuell ersetzen
- Export als PNG

Installation:
    pip install -r requirements.txt

Start:
    python bild_umfaerber_gui_v4_5.py

Hinweis:
Tkinter ist bei Windows-Python normalerweise dabei. Unter Linux ggf. installieren:
    sudo apt install python3-tk
"""

from __future__ import annotations

import math
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image, ImageColor, ImageFilter, ImageTk

RGB = Tuple[int, int, int]

# Exakte Ziel-Farben fuer spaetere technische Weiterverarbeitung / Vektorisierung.
# Die Farben werden im PNG wirklich als diese RGB-Werte geschrieben.
CONTRAST_PALETTE: list[tuple[str, RGB]] = [
    ("Schwarz", (0, 0, 0)),
    ("Blau", (0, 0, 255)),
    ("Rot", (255, 0, 0)),
    ("Gruen", (0, 255, 0)),
    ("Magenta", (255, 0, 255)),
    ("Cyan", (0, 255, 255)),
    ("Gelb", (255, 255, 0)),
    ("Orange", (255, 128, 0)),
    ("Violett", (128, 0, 255)),
    ("Dunkelgruen", (0, 128, 0)),
    ("Braun", (128, 64, 0)),
    ("Grau", (128, 128, 128)),
    ("Dunkelblau", (0, 0, 128)),
    ("Pink", (255, 0, 128)),
    ("Hellgruen", (128, 255, 0)),
    ("Hellblau", (0, 128, 255)),
]


# -----------------------------------------------------------------------------
# Hilfsfunktionen
# -----------------------------------------------------------------------------

def clamp_channel(value: int) -> int:
    return max(0, min(255, int(value)))


def rgb_to_text(rgb: RGB) -> str:
    return f"{rgb[0]},{rgb[1]},{rgb[2]}"


def rgb_to_hex(rgb: RGB) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def parse_rgb(text: str) -> RGB:
    """Akzeptiert z. B. '255,0,0', '255 0 0' oder '#ff0000'."""
    value = (text or "").strip()
    if not value:
        raise ValueError("Leerer Farbwert")

    if value.startswith("#"):
        rgb = ImageColor.getrgb(value)
        if len(rgb) < 3:
            raise ValueError("Ungueltiger HEX-Farbwert")
        return clamp_channel(rgb[0]), clamp_channel(rgb[1]), clamp_channel(rgb[2])

    numbers = re.findall(r"\d+", value)
    if len(numbers) != 3:
        raise ValueError("Bitte RGB als 0,0,0 oder #000000 eingeben")

    rgb = tuple(clamp_channel(int(n)) for n in numbers)
    return rgb  # type: ignore[return-value]


def make_checker_background(size: Tuple[int, int], tile: int = 12) -> Image.Image:
    """Erzeugt einen einfachen Schachbrett-Hintergrund fuer transparente PNGs."""
    width, height = size
    bg = Image.new("RGB", size, (245, 245, 245))
    arr = np.array(bg)
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                arr[y : y + tile, x : x + tile] = (220, 220, 220)
    return Image.fromarray(arr, "RGB")


def image_for_display(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Bild fuer Tkinter anzeigen, transparente Bereiche sichtbar machen."""
    resized = image.resize(size, Image.Resampling.NEAREST)
    if resized.mode != "RGBA":
        return resized.convert("RGB")

    bg = make_checker_background(size).convert("RGBA")
    bg.alpha_composite(resized)
    return bg.convert("RGB")


def mask_for_rgb(base_rgb: np.ndarray, source_rgb: RGB, tolerance: int) -> np.ndarray:
    """Kanalweise RGB-Toleranzmaske: R, G und B muessen im Schwellenwert liegen."""
    src = np.array(source_rgb, dtype=np.int16)
    diff = np.abs(base_rgb.astype(np.int16) - src)
    tol = max(0, min(255, int(tolerance)))
    return (diff[:, :, 0] <= tol) & (diff[:, :, 1] <= tol) & (diff[:, :, 2] <= tol)


def apply_image_preparation(
    image: Image.Image,
    brightness: int = 0,
    contrast: int = 0,
    black_point: int = 0,
    white_point: int = 255,
    gamma: float = 1.0,
) -> Image.Image:
    """
    Erstellt die technische Zwischenstufe fuer die Farberkennung.

    Reihenfolge:
    1. Tonwert/Levels ueber Schwarzpunkt und Weisspunkt
    2. Gamma-Korrektur
    3. Kontrast
    4. Helligkeit

    Alpha bleibt erhalten. Dadurch koennen transparente PNGs sauber exportiert werden.
    """
    rgba = np.array(image.convert("RGBA"), dtype=np.float32)
    rgb = rgba[:, :, :3]

    bp = max(0, min(254, int(black_point)))
    wp = max(1, min(255, int(white_point)))
    if wp <= bp:
        wp = min(255, bp + 1)

    # Tonwertspreizung: alles unter Schwarzpunkt wird 0, alles ueber Weisspunkt wird 255.
    rgb = (rgb - float(bp)) * (255.0 / float(wp - bp))
    rgb = np.clip(rgb, 0, 255)

    # Gamma: < 1 hellt Mitteltöne auf, > 1 dunkelt sie ab.
    try:
        g = float(gamma)
    except Exception:
        g = 1.0
    g = max(0.10, min(5.00, g))
    rgb = 255.0 * np.power(np.clip(rgb / 255.0, 0, 1), g)

    # Kontrast um die Bildmitte. -100 = flach, +100 = deutlich staerker.
    c = max(-100, min(100, int(contrast)))
    contrast_factor = 1.0 + (c / 100.0)
    rgb = (rgb - 127.5) * contrast_factor + 127.5

    # Helligkeit als Offset. -100..+100 entspricht ungefaehr -255..+255.
    b = max(-100, min(100, int(brightness)))
    rgb = rgb + (b * 2.55)

    rgba[:, :, :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


# -----------------------------------------------------------------------------
# Zoom-/Pan-Canvas
# -----------------------------------------------------------------------------

class ZoomImageCanvas(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        picker_callback: Optional[Callable[[RGB, int, int], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.picker_callback = picker_callback
        self.image: Optional[Image.Image] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._pan_start: Optional[Tuple[int, int, float, float]] = None
        self._left_press: Optional[Tuple[int, int, float, float]] = None
        self._left_dragged = False
        self._max_display_pixels = 30_000_000

        ttk.Label(self, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=4, pady=(0, 4))
        self.canvas = tk.Canvas(self, bg="#303030", highlightthickness=1, highlightbackground="#808080")
        self.canvas.pack(fill="both", expand=True)

        # Windows/macOS Mausrad
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        # Linux Mausrad
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)

        # Linke Maustaste:
        # - kurzer Klick = Farbe aufnehmen, falls ein Picker gesetzt ist
        # - gedrueckt halten und ziehen = Bild verschieben
        self.canvas.bind("<ButtonPress-1>", self._start_left_action)
        self.canvas.bind("<B1-Motion>", self._move_left_action)
        self.canvas.bind("<ButtonRelease-1>", self._end_left_action)

        # Alternative Bedienung bleibt erhalten.
        self.canvas.bind("<Button-2>", self._start_pan)
        self.canvas.bind("<B2-Motion>", self._move_pan)
        self.canvas.bind("<Button-3>", self._start_pan)
        self.canvas.bind("<B3-Motion>", self._move_pan)
        self.canvas.bind("<Configure>", lambda _event: self.render())

    def set_image(self, image: Optional[Image.Image], reset_view: bool = True) -> None:
        self.image = image
        if image is None:
            self.canvas.delete("all")
            self.tk_image = None
            return

        if reset_view:
            self.fit_to_canvas()
        else:
            self.render()

    def fit_to_canvas(self) -> None:
        if self.image is None:
            return
        # Wichtig: Wenn das Canvas gerade erst aufgebaut wurde, liefert Tk manchmal noch 1x1 px.
        # Dann waere die Vorschau praktisch unsichtbar. Darum kurz Layout aktualisieren
        # und notfalls mit einer sinnvollen Mindestgroesse rechnen.
        self.update_idletasks()
        cw = max(600, self.canvas.winfo_width())
        ch = max(350, self.canvas.winfo_height())
        iw, ih = self.image.size
        if iw <= 0 or ih <= 0:
            return

        # Kleine Bilder werden nicht kuenstlich vergroessert, grosse passend eingepasst.
        self.zoom = min(1.0, cw / iw, ch / ih)
        self.offset_x = (cw - iw * self.zoom) / 2
        self.offset_y = (ch - ih * self.zoom) / 2
        self.render()

    def _safe_zoom(self, requested_zoom: float) -> float:
        if self.image is None:
            return 1.0
        iw, ih = self.image.size
        requested_zoom = max(0.02, min(32.0, requested_zoom))
        pixels = iw * ih * requested_zoom * requested_zoom
        if pixels > self._max_display_pixels:
            requested_zoom = math.sqrt(self._max_display_pixels / max(1, iw * ih))
        return max(0.02, requested_zoom)

    def render(self) -> None:
        self.canvas.delete("all")
        if self.image is None:
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text="Kein Bild geladen",
                fill="white",
                font=("Segoe UI", 12),
            )
            return

        iw, ih = self.image.size
        self.zoom = self._safe_zoom(self.zoom)
        dw = max(1, int(iw * self.zoom))
        dh = max(1, int(ih * self.zoom))

        display_img = image_for_display(self.image, (dw, dh))
        self.tk_image = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(int(self.offset_x), int(self.offset_y), anchor="nw", image=self.tk_image)

        # kleiner Zoom-Hinweis unten links
        self.canvas.create_rectangle(4, self.canvas.winfo_height() - 26, 96, self.canvas.winfo_height() - 4, fill="#111111", outline="")
        self.canvas.create_text(50, self.canvas.winfo_height() - 15, text=f"Zoom {self.zoom:.2f}x", fill="white")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.image is None:
            return

        old_zoom = self.zoom
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            factor = 1.15
        else:
            factor = 1 / 1.15

        requested_zoom = old_zoom * factor
        new_zoom = self._safe_zoom(requested_zoom)
        if abs(new_zoom - old_zoom) < 0.0001:
            return

        # Zoom um Mausposition herum
        img_x = (event.x - self.offset_x) / old_zoom
        img_y = (event.y - self.offset_y) / old_zoom
        self.zoom = new_zoom
        self.offset_x = event.x - img_x * new_zoom
        self.offset_y = event.y - img_y * new_zoom
        self.render()

    def _pick_pixel_at_canvas_pos(self, canvas_x: int, canvas_y: int) -> None:
        if self.image is None or self.picker_callback is None:
            return
        x = int((canvas_x - self.offset_x) / self.zoom)
        y = int((canvas_y - self.offset_y) / self.zoom)
        if 0 <= x < self.image.width and 0 <= y < self.image.height:
            pixel = self.image.convert("RGBA").getpixel((x, y))
            rgb = (pixel[0], pixel[1], pixel[2])
            self.picker_callback(rgb, x, y)

    def _start_left_action(self, event: tk.Event) -> None:
        self._left_press = (event.x, event.y, self.offset_x, self.offset_y)
        self._left_dragged = False

    def _move_left_action(self, event: tk.Event) -> None:
        if self._left_press is None:
            return
        sx, sy, ox, oy = self._left_press
        dx = event.x - sx
        dy = event.y - sy
        if abs(dx) > 3 or abs(dy) > 3:
            self._left_dragged = True
        self.offset_x = ox + dx
        self.offset_y = oy + dy
        self.render()

    def _end_left_action(self, event: tk.Event) -> None:
        if self._left_press is None:
            return
        sx, sy, _ox, _oy = self._left_press
        moved = abs(event.x - sx) > 3 or abs(event.y - sy) > 3 or self._left_dragged
        self._left_press = None

        # Nur ein echter kurzer Klick nimmt Farbe auf. Ziehen verschiebt nur das Bild.
        if not moved:
            self._pick_pixel_at_canvas_pos(event.x, event.y)

    def _start_pan(self, event: tk.Event) -> None:
        self._pan_start = (event.x, event.y, self.offset_x, self.offset_y)

    def _move_pan(self, event: tk.Event) -> None:
        if self._pan_start is None:
            return
        sx, sy, ox, oy = self._pan_start
        self.offset_x = ox + (event.x - sx)
        self.offset_y = oy + (event.y - sy)
        self.render()


# -----------------------------------------------------------------------------
# Scrollbarer Bereich fuer Farblisten
# -----------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget, height: int = 130) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.inner.bind("<Button-4>", self._on_mousewheel)
        self.inner.bind("<Button-5>", self._on_mousewheel)

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-3, "units")
        elif getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(3, "units")
        elif getattr(event, "delta", 0):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# -----------------------------------------------------------------------------
# Datenstrukturen
# -----------------------------------------------------------------------------

@dataclass
class MappingValues:
    enabled: bool
    source_rgb: RGB
    target_rgb: RGB
    tolerance: int


@dataclass
class DetectedColor:
    source_rgb: RGB
    target_rgb: RGB
    pixels: int
    percent: float
    palette_name: str


# -----------------------------------------------------------------------------
# Basis-Modus-Zeile
# -----------------------------------------------------------------------------

class BasicColorRow:
    def __init__(self, app: "RecolorApp", parent: tk.Widget, index: int, detected: DetectedColor) -> None:
        self.app = app
        self.index = index
        self.detected = detected
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", padx=4, pady=2)

        self.enabled_var = tk.BooleanVar(value=True)
        self.target_var = tk.StringVar(value=rgb_to_text(detected.target_rgb))

        ttk.Label(self.frame, text=f"#{index + 1}", width=4).grid(row=0, column=0, sticky="w")
        self.enabled_check = ttk.Checkbutton(self.frame, text="aktiv", variable=self.enabled_var, command=self.app.schedule_preview)
        self.enabled_check.grid(row=0, column=1, padx=(0, 8), sticky="w")

        ttk.Label(self.frame, text="Erkannt").grid(row=0, column=2, sticky="w")
        self.source_label = ttk.Label(self.frame, text=rgb_to_text(detected.source_rgb), width=13)
        self.source_label.grid(row=0, column=3, padx=(4, 4), sticky="w")
        self.source_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1, bg=rgb_to_hex(detected.source_rgb))
        self.source_swatch.grid(row=0, column=4, padx=(0, 10))

        ttk.Label(self.frame, text="Pixel").grid(row=0, column=5, sticky="w")
        ttk.Label(self.frame, text=f"{detected.pixels:,}".replace(",", "."), width=10).grid(row=0, column=6, padx=(4, 4), sticky="e")
        ttk.Label(self.frame, text=f"{detected.percent:.2f}%", width=8).grid(row=0, column=7, padx=(0, 10), sticky="e")

        ttk.Label(self.frame, text="Neue exakte RGB").grid(row=0, column=8, sticky="w")
        self.target_entry = ttk.Entry(self.frame, textvariable=self.target_var, width=14)
        self.target_entry.grid(row=0, column=9, padx=(4, 4), sticky="w")
        self.target_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.target_swatch.grid(row=0, column=10, padx=(0, 4))
        self.pick_btn = ttk.Button(self.frame, text="wählen", command=self.choose_target_color)
        self.pick_btn.grid(row=0, column=11, padx=(0, 4))
        ttk.Label(self.frame, text=detected.palette_name, width=12).grid(row=0, column=12, padx=(4, 0), sticky="w")

        self.target_var.trace_add("write", self._on_change)
        self.update_swatch()

    def _on_change(self, *_args: object) -> None:
        self.update_swatch()
        self.app.schedule_preview()

    def update_swatch(self) -> None:
        try:
            rgb = parse_rgb(self.target_var.get())
            self.target_swatch.configure(bg=rgb_to_hex(rgb))
        except Exception:
            self.target_swatch.configure(bg="#cccccc")

    def choose_target_color(self) -> None:
        try:
            initial = rgb_to_hex(parse_rgb(self.target_var.get()))
        except Exception:
            initial = "#ffffff"
        color = colorchooser.askcolor(color=initial, title="Neue exakte Farbe wählen")
        if color and color[0]:
            r, g, b = (int(round(v)) for v in color[0])
            self.target_var.set(rgb_to_text((r, g, b)))

    def get_values(self, tolerance: int) -> Optional[MappingValues]:
        if not self.enabled_var.get():
            return None
        target_rgb = parse_rgb(self.target_var.get())
        return MappingValues(True, self.detected.source_rgb, target_rgb, tolerance)

    def destroy(self) -> None:
        self.frame.destroy()


# -----------------------------------------------------------------------------
# Erweiterter Modus - manuelle Farbumsetzungs-Zeile
# -----------------------------------------------------------------------------

class ColorMappingRow:
    def __init__(self, app: "RecolorApp", parent: tk.Widget, index: int, source: str, target: str) -> None:
        self.app = app
        self.index = index
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", padx=4, pady=2)

        self.enabled_var = tk.BooleanVar(value=True)
        self.source_var = tk.StringVar(value=source)
        self.target_var = tk.StringVar(value=target)
        self.tolerance_var = tk.IntVar(value=8)

        self.radio = ttk.Radiobutton(
            self.frame,
            variable=self.app.selected_row_var,
            value=self.index,
            command=self.app.update_status_selection,
        )
        self.radio.grid(row=0, column=0, padx=(0, 4))

        self.index_label = ttk.Label(self.frame, text=f"#{self.index + 1}", width=4)
        self.index_label.grid(row=0, column=1, sticky="w")

        self.enabled_check = ttk.Checkbutton(self.frame, text="aktiv", variable=self.enabled_var)
        self.enabled_check.grid(row=0, column=2, padx=(2, 8), sticky="w")

        ttk.Label(self.frame, text="Aus Bild RGB").grid(row=0, column=3, sticky="w")
        self.source_entry = ttk.Entry(self.frame, textvariable=self.source_var, width=14)
        self.source_entry.grid(row=0, column=4, padx=(4, 4), sticky="w")
        self.source_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.source_swatch.grid(row=0, column=5, padx=(0, 10))

        ttk.Label(self.frame, text="Toleranz").grid(row=0, column=6, sticky="w")
        self.tol_spin = ttk.Spinbox(self.frame, from_=0, to=255, textvariable=self.tolerance_var, width=5)
        self.tol_spin.grid(row=0, column=7, padx=(4, 10), sticky="w")

        ttk.Label(self.frame, text="Neue Farbe").grid(row=0, column=8, sticky="w")
        self.target_entry = ttk.Entry(self.frame, textvariable=self.target_var, width=14)
        self.target_entry.grid(row=0, column=9, padx=(4, 4), sticky="w")
        self.target_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.target_swatch.grid(row=0, column=10, padx=(0, 4))
        self.pick_btn = ttk.Button(self.frame, text="wählen", command=self.choose_target_color)
        self.pick_btn.grid(row=0, column=11, padx=(0, 4))

        for col in range(12):
            self.frame.grid_columnconfigure(col, weight=0)
        self.frame.grid_columnconfigure(12, weight=1)

        for var in (self.enabled_var, self.source_var, self.target_var, self.tolerance_var):
            var.trace_add("write", self._on_change)

        self.update_swatches()

    def _on_change(self, *_args: object) -> None:
        self.update_swatches()
        self.app.schedule_preview()

    def update_index(self, index: int) -> None:
        self.index = index
        self.radio.configure(value=index)
        self.index_label.configure(text=f"#{index + 1}")

    def update_swatches(self) -> None:
        for var, label in ((self.source_var, self.source_swatch), (self.target_var, self.target_swatch)):
            try:
                rgb = parse_rgb(var.get())
                label.configure(bg=rgb_to_hex(rgb))
            except Exception:
                label.configure(bg="#cccccc")

    def choose_target_color(self) -> None:
        try:
            initial = rgb_to_hex(parse_rgb(self.target_var.get()))
        except Exception:
            initial = "#ffffff"
        color = colorchooser.askcolor(color=initial, title="Neue Farbe wählen")
        if color and color[0]:
            r, g, b = (int(round(v)) for v in color[0])
            self.target_var.set(rgb_to_text((r, g, b)))

    def set_source_rgb(self, rgb: RGB) -> None:
        self.source_var.set(rgb_to_text(rgb))

    def get_values(self) -> Optional[MappingValues]:
        if not self.enabled_var.get():
            return None
        source = parse_rgb(self.source_var.get())
        target = parse_rgb(self.target_var.get())
        try:
            tolerance = int(self.tolerance_var.get())
        except Exception:
            tolerance = 0
        tolerance = max(0, min(255, tolerance))
        return MappingValues(True, source, target, tolerance)

    def destroy(self) -> None:
        self.frame.destroy()


# -----------------------------------------------------------------------------
# Haupt-App
# -----------------------------------------------------------------------------

class RecolorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bild einfach umfärben - Basis/Erweitert - PNG Export - v4.5")
        self.geometry("1400x900")
        self.minsize(1100, 760)

        self.original_image: Optional[Image.Image] = None
        self.prepared_image: Optional[Image.Image] = None
        self.edited_image: Optional[Image.Image] = None
        self.current_path: Optional[Path] = None
        self.preview_after_id: Optional[str] = None
        self.preprocess_dirty = False

        self.basic_rows: list[BasicColorRow] = []
        self.advanced_rows: list[ColorMappingRow] = []
        self.selected_row_var = tk.IntVar(value=0)

        self.basic_threshold_var = tk.IntVar(value=10)
        self.basic_min_area_var = tk.IntVar(value=30)
        self.basic_max_colors_var = tk.IntVar(value=12)
        self.basic_alpha_var = tk.IntVar(value=10)

        # Bildvorbereitung im Basis-Modus. Diese Werte wirken VOR Farberkennung und Export.
        self.prep_brightness_var = tk.IntVar(value=0)
        self.prep_contrast_var = tk.IntVar(value=0)
        self.prep_black_var = tk.IntVar(value=0)
        self.prep_white_var = tk.IntVar(value=255)
        self.prep_gamma_var = tk.DoubleVar(value=1.0)

        # v4.5: Spezialmodus fuer graue/gescannte Logos auf unruhigem Hintergrund.
        # Nicht absolute RGB-Farbe, sondern lokaler Kontrast wird erkannt:
        # Pixel ist deutlich dunkler als seine lokale Umgebung -> Logo/Strich.
        self.logo_mask_threshold_var = tk.IntVar(value=18)
        self.logo_mask_blur_var = tk.IntVar(value=31)
        self.logo_mask_clean_var = tk.BooleanVar(value=True)
        self.logo_mask_fg_var = tk.StringVar(value="0,0,0")
        self.logo_mask_bg_var = tk.StringVar(value="255,255,255")
        self.special_result_image: Optional[Image.Image] = None

        self._build_ui()
        self.add_mapping(source="0,0,0", target="255,255,255")

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(99, weight=1)

        ttk.Button(toolbar, text="Bild laden", command=self.load_image).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(toolbar, text="Vorschau aktualisieren", command=self.update_preview).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(toolbar, text="Zoom zurücksetzen", command=self.reset_zoom).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(toolbar, text="Export als PNG", command=self.export_png).grid(row=0, column=3, padx=(0, 12))

        self.info_label = ttk.Label(
            toolbar,
            text="Basis: Bild laden -> Farben erkennen -> PNG mit exakten RGB-Kontrastfarben exportieren.",
        )
        self.info_label.grid(row=0, column=4, sticky="w")

        preview_frame = ttk.Frame(self, padding=(8, 4, 8, 4))
        preview_frame.grid(row=1, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.columnconfigure(1, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.original_canvas = ZoomImageCanvas(preview_frame, "Originalbild", self.on_pick_color)
        self.original_canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.edited_canvas = ZoomImageCanvas(preview_frame, "Bearbeitete Vorschau")
        self.edited_canvas.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # Der Bedienbereich bekommt eine feste, groessere Hoehe.
        # v4.2 war hier zu niedrig: Die Farbtabelle war zwar vorhanden, lag aber unterhalb des sichtbaren Bereichs.
        bottom = ttk.Frame(self, padding=(8, 4, 8, 8), height=430)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.grid_propagate(False)
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(bottom)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self.on_mode_changed())

        self.basic_tab = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        self.advanced_tab = ttk.Frame(self.notebook, padding=(8, 8, 8, 8))
        self.notebook.add(self.basic_tab, text="Basis-Modus")
        self.notebook.add(self.advanced_tab, text="Erweiterter Modus")

        self._build_basic_tab()
        self._build_advanced_tab()

    def _build_basic_tab(self) -> None:
        """
        Basis-Modus bewusst zweigeteilt und komplett scrollbar:
        links  = Bildvorbereitung (Helligkeit/Kontrast/Tonwert)
        rechts = automatische Farberkennung (Schwellenwert/Max. Farben usw.)
        unten  = erkannte Farbbereiche mit exakten Ziel-RGB-Werten

        Wichtig ab v4.4:
        Der ganze Basis-Tab liegt in einem vertikalen Scrollbereich. Dadurch ist die
        Farbtabelle auch erreichbar, wenn der untere UI-Bereich auf dem Bildschirm
        zu klein ist.
        """
        self.basic_tab.columnconfigure(0, weight=1)
        self.basic_tab.rowconfigure(0, weight=1)

        self.basic_tab_scroll = ScrollableFrame(self.basic_tab, height=360)
        self.basic_tab_scroll.grid(row=0, column=0, sticky="nsew")
        content = self.basic_tab_scroll.inner

        content.columnconfigure(0, weight=1, uniform="basic_top")
        content.columnconfigure(1, weight=1, uniform="basic_top")
        content.rowconfigure(2, weight=1)

        # LINKS: Bildvorbereitung
        prep = ttk.LabelFrame(content, text="1) Bildvorbereitung", padding=(8, 6, 8, 6))
        prep.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        prep.columnconfigure(1, weight=1)

        self._add_preprocess_scale(prep, row=0, label="Helligkeit", variable=self.prep_brightness_var, from_=-100, to=100, resolution=1)
        self._add_preprocess_scale(prep, row=1, label="Kontrast", variable=self.prep_contrast_var, from_=-100, to=100, resolution=1)
        self._add_preprocess_scale(prep, row=2, label="Schwarzpunkt", variable=self.prep_black_var, from_=0, to=254, resolution=1)
        self._add_preprocess_scale(prep, row=3, label="Weißpunkt", variable=self.prep_white_var, from_=1, to=255, resolution=1)
        self._add_preprocess_scale(prep, row=4, label="Gamma/Tonwert", variable=self.prep_gamma_var, from_=0.30, to=3.00, resolution=0.05)

        prep_buttons = ttk.Frame(prep)
        prep_buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(prep_buttons, text="Zurücksetzen", command=self.reset_preprocessing).pack(side="left", padx=(0, 6))
        ttk.Button(prep_buttons, text="Vorbereitung anzeigen", command=self.update_preview).pack(side="left", padx=(0, 6))
        ttk.Button(prep_buttons, text="Vorbereitung + Farben neu erkennen", command=self.detect_basic_colors).pack(side="left")

        prep_hint = ttk.Label(
            prep,
            text="Diese Werte wirken vor der Farberkennung. Damit kannst du schwache Logos zuerst klarer machen.",
            foreground="#555555",
            wraplength=520,
            justify="left",
        )
        prep_hint.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # RECHTS: automatische Farberkennung
        controls = ttk.LabelFrame(content, text="2) Automatische Farberkennung", padding=(8, 6, 8, 6))
        controls.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Schwellenwert", width=18).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Spinbox(controls, from_=0, to=255, textvariable=self.basic_threshold_var, width=8, command=self.schedule_preview).grid(row=0, column=1, sticky="w", padx=(4, 0), pady=2)
        ttk.Label(controls, text="ähnliche Farben zusammenfassen", foreground="#555555").grid(row=0, column=2, sticky="w", padx=(8, 0), pady=2)

        ttk.Label(controls, text="Mindestfläche/Px", width=18).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Spinbox(controls, from_=1, to=999999, textvariable=self.basic_min_area_var, width=8).grid(row=1, column=1, sticky="w", padx=(4, 0), pady=2)
        ttk.Label(controls, text="kleine Störungen ignorieren", foreground="#555555").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=2)

        ttk.Label(controls, text="Max. Farben", width=18).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Spinbox(controls, from_=1, to=64, textvariable=self.basic_max_colors_var, width=8).grid(row=2, column=1, sticky="w", padx=(4, 0), pady=2)
        ttk.Label(controls, text="wie viele Farbbereiche behalten", foreground="#555555").grid(row=2, column=2, sticky="w", padx=(8, 0), pady=2)

        ttk.Label(controls, text="Alpha ab", width=18).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Spinbox(controls, from_=0, to=255, textvariable=self.basic_alpha_var, width=8).grid(row=3, column=1, sticky="w", padx=(4, 0), pady=2)
        ttk.Label(controls, text="transparente Pixel ignorieren", foreground="#555555").grid(row=3, column=2, sticky="w", padx=(8, 0), pady=2)

        control_buttons = ttk.Frame(controls)
        control_buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(control_buttons, text="Farben erkennen + Kontrastfarben setzen", command=self.detect_basic_colors).pack(side="left", padx=(0, 8))
        ttk.Button(control_buttons, text="Kontrastfarben neu zuweisen", command=self.reassign_basic_targets).pack(side="left", padx=(0, 8))
        ttk.Button(control_buttons, text="↓ Farbtabelle anzeigen", command=self.scroll_basic_to_table).pack(side="left")

        controls_hint = ttk.Label(
            controls,
            text="Für CAD/Vektor später wichtig: Zielwerte werden als exakte RGB-Werte ins PNG geschrieben. Die Farbtabelle liegt unten im Basis-Tab.",
            foreground="#555555",
            wraplength=520,
            justify="left",
        )
        controls_hint.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Spezialhilfe fuer genau solche Bilder wie graue Logos auf nicht ganz sauberem Hintergrund.
        # RGB-Picker erwischt dort oft Schatten/Verläufe, weil dieselben Grauwerte auch im Hintergrund vorkommen.
        mask_box = ttk.LabelFrame(controls, text="Problemfall: graues Logo / Schatten / Verlauf", padding=(6, 6, 6, 6))
        mask_box.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        mask_box.columnconfigure(1, weight=1)

        ttk.Label(mask_box, text="Logo-Schwelle", width=18).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Spinbox(mask_box, from_=1, to=100, textvariable=self.logo_mask_threshold_var, width=8).grid(row=0, column=1, sticky="w", padx=(4, 0), pady=2)
        ttk.Label(mask_box, text="höher = weniger wird schwarz", foreground="#555555").grid(row=0, column=2, sticky="w", padx=(8, 0), pady=2)

        ttk.Label(mask_box, text="Hintergrund-Radius", width=18).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Spinbox(mask_box, from_=5, to=151, increment=2, textvariable=self.logo_mask_blur_var, width=8).grid(row=1, column=1, sticky="w", padx=(4, 0), pady=2)
        ttk.Label(mask_box, text="größer = langsame Schatten/Verläufe werden ignoriert", foreground="#555555").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=2)

        ttk.Label(mask_box, text="Logo RGB", width=18).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(mask_box, textvariable=self.logo_mask_fg_var, width=14).grid(row=2, column=1, sticky="w", padx=(4, 0), pady=2)
        ttk.Label(mask_box, text="Hintergrund RGB", width=18).grid(row=2, column=2, sticky="e", padx=(8, 0), pady=2)
        ttk.Entry(mask_box, textvariable=self.logo_mask_bg_var, width=14).grid(row=2, column=3, sticky="w", padx=(4, 0), pady=2)

        ttk.Checkbutton(mask_box, text="kleine Pixelstörungen glätten", variable=self.logo_mask_clean_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(mask_box, text="Logo-Maske erzeugen", command=self.create_logo_mask_preview).grid(row=3, column=2, sticky="w", padx=(8, 0), pady=(4, 0))
        ttk.Label(mask_box, text="Ergebnis: exaktes Schwarz/Weiß-PNG für spätere Vektorisierung", foreground="#555555").grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

        self.basic_status_label = ttk.Label(
            content,
            text="Noch keine Farben erkannt. Lade ein Bild und klicke auf 'Farben erkennen'. Farbtabelle ist unten erreichbar.",
        )
        self.basic_status_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

        rows_frame = ttk.LabelFrame(content, text="3) Erkannte Farbbereiche und Ziel-RGB", padding=(4, 4, 4, 4))
        rows_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        rows_frame.columnconfigure(0, weight=1)
        rows_frame.rowconfigure(0, weight=1)

        self.basic_rows_scroll = ScrollableFrame(rows_frame, height=220)
        self.basic_rows_scroll.grid(row=0, column=0, sticky="nsew")
        self.basic_rows_container = self.basic_rows_scroll.inner

    def scroll_basic_to_table(self) -> None:
        """Springt im Basis-Modus zur Farbtabelle nach unten."""
        try:
            self.basic_tab.update_idletasks()
            self.basic_tab_scroll.canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _add_preprocess_scale(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        variable: tk.Variable,
        from_: float,
        to: float,
        resolution: float,
    ) -> None:
        ttk.Label(parent, text=label, width=15).grid(row=row, column=0, sticky="w", pady=1)
        scale = tk.Scale(
            parent,
            from_=from_,
            to=to,
            resolution=resolution,
            orient="horizontal",
            variable=variable,
            length=240,
            showvalue=True,
            command=lambda _value: self.on_preprocess_changed(),
        )
        scale.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=1)

    def _build_advanced_tab(self) -> None:
        self.advanced_tab.columnconfigure(0, weight=1)
        self.advanced_tab.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.advanced_tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(controls, text="+ Farbauswahl", command=self.add_mapping).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="- selektierte löschen", command=self.remove_selected_mapping).pack(side="left", padx=(0, 12))

        self.status_label = ttk.Label(
            controls,
            text="Selektierte Zeile: #1 | Kurzer Klick ins Originalbild übernimmt die Farbe; gedrückt ziehen verschiebt in diese Zeile.",
        )
        self.status_label.pack(side="left")

        self.advanced_rows_scroll = ScrollableFrame(self.advanced_tab, height=200)
        self.advanced_rows_scroll.grid(row=1, column=0, sticky="nsew")
        self.rows_container = self.advanced_rows_scroll.inner

    # ------------------------------------------------------------------ Modus
    def current_mode(self) -> str:
        try:
            selected = self.notebook.index(self.notebook.select())
        except Exception:
            selected = 0
        return "basic" if selected == 0 else "advanced"

    def on_mode_changed(self) -> None:
        if self.current_mode() == "basic":
            self.info_label.configure(text="Basis: Bildvorbereitung -> Farberkennung -> exakte RGB-Kontrastfarben. Linksklick zeigt nur die Pixel-Farbe an.")
        else:
            self.info_label.configure(text="Erweitert: Linksklick ins Originalbild übernimmt die Farbe in die selektierte Zeile. Mausrad = Zoom, linke Maustaste gedrueckt halten = verschieben, kurzer Klick = Farbe aufnehmen.")
        self.update_preview()

    # ------------------------------------------------------------------ Bild
    def load_image(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Bild laden",
            filetypes=[
                ("Bilddateien", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                ("PNG", "*.png"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            img = Image.open(file_path).convert("RGBA")
        except Exception as exc:
            messagebox.showerror("Fehler beim Laden", f"Bild konnte nicht geladen werden:\n{exc}")
            return

        self.current_path = Path(file_path)
        self.original_image = img
        self.prepared_image = self.get_prepared_image(force=True)
        self.edited_image = self.prepared_image.copy() if self.prepared_image else img.copy()
        self.preprocess_dirty = False
        self.update_idletasks()
        self.original_canvas.set_image(self.original_image, reset_view=True)
        self.edited_canvas.set_image(self.edited_image, reset_view=True)
        self.info_label.configure(text=f"Geladen: {self.current_path.name} | Größe: {img.width} x {img.height}px")

        if self.current_mode() == "basic":
            self.detect_basic_colors()
        else:
            self.update_preview()

    def reset_zoom(self) -> None:
        self.original_canvas.fit_to_canvas()
        self.edited_canvas.fit_to_canvas()

    def on_pick_color(self, rgb: RGB, x: int, y: int) -> None:
        if self.current_mode() == "basic":
            self.basic_status_label.configure(text=f"Pixel-Farbe bei x={x}, y={y}: {rgb_to_text(rgb)}. Im Basis-Modus wird automatisch erkannt.")
            return

        if not self.advanced_rows:
            self.add_mapping()
        index = self.selected_row_var.get()
        if index < 0 or index >= len(self.advanced_rows):
            index = 0
            self.selected_row_var.set(0)
        self.advanced_rows[index].set_source_rgb(rgb)
        self.status_label.configure(text=f"Farbe übernommen: {rgb_to_text(rgb)} bei Pixel x={x}, y={y} -> Zeile #{index + 1}")
        self.schedule_preview()

    # ------------------------------------------------------------------ Bildvorbereitung
    def reset_preprocessing(self) -> None:
        self.prep_brightness_var.set(0)
        self.prep_contrast_var.set(0)
        self.prep_black_var.set(0)
        self.prep_white_var.set(255)
        self.prep_gamma_var.set(1.0)
        self.on_preprocess_changed()

    def on_preprocess_changed(self) -> None:
        self.special_result_image = None
        if self.original_image is None:
            return
        self.prepared_image = self.get_prepared_image(force=True)
        self.preprocess_dirty = True
        if self.current_mode() == "basic":
            self.basic_status_label.configure(
                text="Bildvorbereitung geändert. Für neue Farbbereiche bitte 'Vorbereitung + Farben neu erkennen' klicken."
            )
        self.schedule_preview()

    def get_prepared_image(self, force: bool = False) -> Optional[Image.Image]:
        if self.original_image is None:
            return None
        if self.prepared_image is not None and not force:
            return self.prepared_image

        try:
            brightness = int(self.prep_brightness_var.get())
            contrast = int(self.prep_contrast_var.get())
            black_point = int(self.prep_black_var.get())
            white_point = int(self.prep_white_var.get())
            gamma = float(self.prep_gamma_var.get())
        except Exception:
            brightness, contrast, black_point, white_point, gamma = 0, 0, 0, 255, 1.0

        self.prepared_image = apply_image_preparation(
            self.original_image,
            brightness=brightness,
            contrast=contrast,
            black_point=black_point,
            white_point=white_point,
            gamma=gamma,
        )
        return self.prepared_image

    def get_processing_base_image(self) -> Optional[Image.Image]:
        """Basis-Modus nutzt die vorbereitete Zwischenstufe, Erweitert bleibt wie bisher beim Original."""
        if self.original_image is None:
            return None
        if self.current_mode() == "basic":
            return self.get_prepared_image(force=False)
        return self.original_image

    # ------------------------------------------------------------------ Basis-Erkennung
    def get_basic_threshold(self) -> int:
        try:
            return max(0, min(255, int(self.basic_threshold_var.get())))
        except Exception:
            return 10

    def detect_basic_colors(self) -> None:
        self.special_result_image = None
        if self.original_image is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein Bild laden.")
            return

        try:
            threshold = self.get_basic_threshold()
            min_area = max(1, int(self.basic_min_area_var.get()))
            max_colors = max(1, min(64, int(self.basic_max_colors_var.get())))
            alpha_min = max(0, min(255, int(self.basic_alpha_var.get())))
            base_image = self.get_prepared_image(force=True)
            if base_image is None:
                return
            detected = self.detect_colors_by_threshold(
                base_image,
                threshold=threshold,
                min_area=min_area,
                max_colors=max_colors,
                alpha_min=alpha_min,
            )
        except Exception as exc:
            messagebox.showerror("Fehler", f"Farben konnten nicht erkannt werden:\n{exc}")
            return

        self.clear_basic_rows()
        for index, item in enumerate(detected):
            self.basic_rows.append(BasicColorRow(self, self.basic_rows_container, index, item))

        self.preprocess_dirty = False

        if detected:
            self.basic_status_label.configure(
                text=f"{len(detected)} Farbbereich(e) erkannt. Farbtabelle unten / per Scrollbar erreichbar. Schwellenwert: {threshold}"
            )
        else:
            self.basic_status_label.configure(text="Keine Farbbereiche erkannt. Schwellenwert/Mindestfläche prüfen.")

        self.update_preview()

    def clear_basic_rows(self) -> None:
        for row in self.basic_rows:
            row.destroy()
        self.basic_rows.clear()

    def reassign_basic_targets(self) -> None:
        if not self.basic_rows:
            return
        for index, row in enumerate(self.basic_rows):
            name, rgb = CONTRAST_PALETTE[index % len(CONTRAST_PALETTE)]
            row.detected.palette_name = name
            row.target_var.set(rgb_to_text(rgb))
        self.basic_status_label.configure(text="Kontrastfarben neu zugewiesen. Die Zielwerte bleiben exakte RGB-Werte.")
        self.schedule_preview()

    @staticmethod
    def detect_colors_by_threshold(
        image: Image.Image,
        threshold: int,
        min_area: int,
        max_colors: int,
        alpha_min: int,
    ) -> list[DetectedColor]:
        """
        Erkennt Farbbereiche durch Gruppierung aehnlicher RGB-Werte.

        Vorgehen:
        1. transparente Pixel ignorieren
        2. haeufige RGB-Werte suchen
        3. aehnliche Farben nach Schwellenwert zusammenfassen
        4. reale Flaeche je Gruppe im Originalbild zaehlen
        5. groesste Gruppen behalten und exakte Kontrastfarben vergeben
        """
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        rgb_full = rgba[:, :, :3]
        alpha = rgba[:, :, 3]
        valid_mask = alpha >= alpha_min
        total_valid = int(valid_mask.sum())
        if total_valid <= 0:
            return []

        pixels = rgb_full[valid_mask]

        # Bei sehr grossen Bildern nur jeden n-ten Pixel fuer die Farb-Kandidaten nehmen.
        # Die echte Pixelanzahl wird danach trotzdem ueber das ganze Bild gezaehlt.
        max_sample_pixels = 1_500_000
        if pixels.shape[0] > max_sample_pixels:
            step = int(math.ceil(pixels.shape[0] / max_sample_pixels))
            sample = pixels[::step]
        else:
            sample = pixels

        unique, counts = np.unique(sample, axis=0, return_counts=True)
        order = np.argsort(counts)[::-1]

        reps: list[RGB] = []
        approx_counts: list[int] = []

        # Mehr Kandidaten sammeln als spaeter angezeigt werden, damit nach Mindestflaeche noch genug bleiben.
        max_reps_to_build = max_colors * 4
        for idx in order:
            color_arr = unique[idx].astype(np.int16)
            count = int(counts[idx])

            assigned = False
            for rep_index, rep in enumerate(reps):
                rep_arr = np.array(rep, dtype=np.int16)
                if np.all(np.abs(color_arr - rep_arr) <= threshold):
                    approx_counts[rep_index] += count
                    assigned = True
                    break

            if not assigned:
                reps.append((int(color_arr[0]), int(color_arr[1]), int(color_arr[2])))
                approx_counts.append(count)
                if len(reps) >= max_reps_to_build:
                    break

        found: list[tuple[RGB, int]] = []
        rgb_int = rgb_full.astype(np.int16)
        for rep in reps:
            mask = mask_for_rgb(rgb_int, rep, threshold) & valid_mask
            real_count = int(mask.sum())
            if real_count >= min_area:
                found.append((rep, real_count))

        found.sort(key=lambda item: item[1], reverse=True)
        found = found[:max_colors]

        detected: list[DetectedColor] = []
        for index, (rep, count) in enumerate(found):
            palette_name, target = CONTRAST_PALETTE[index % len(CONTRAST_PALETTE)]
            percent = (count / total_valid) * 100.0
            detected.append(
                DetectedColor(
                    source_rgb=rep,
                    target_rgb=target,
                    pixels=count,
                    percent=percent,
                    palette_name=palette_name,
                )
            )
        return detected

    # ------------------------------------------------------------------ Spezial: Logo-Maske ueber lokalen Kontrast
    def create_logo_mask_preview(self) -> None:
        """
        Erzeugt ein exaktes 2-Farben-Ergebnis fuer schwierige Logos.

        Problem: Bei gescannten/hellgrauen Logos gibt es dieselben Grauwerte oft auch
        im Schatten oder Hintergrund. Eine reine RGB-Toleranz kann das nicht unterscheiden.

        Loesung hier: Es wird nicht "dieser RGB-Wert" gesucht, sondern: 
        Ist ein Pixel deutlich dunkler als seine lokale Umgebung? Dann gehoert es
        vermutlich zum Logo/Strich. Langsame Verlaeufe und Schatten werden dadurch
        eher ignoriert.
        """
        if self.original_image is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein Bild laden.")
            return

        try:
            fg_rgb = parse_rgb(self.logo_mask_fg_var.get())
            bg_rgb = parse_rgb(self.logo_mask_bg_var.get())
            threshold = max(1, min(100, int(self.logo_mask_threshold_var.get())))
            blur_radius = max(3, min(151, int(self.logo_mask_blur_var.get())))
            # GaussianBlur arbeitet auch mit geraden Werten, fuer Bedienlogik sind ungerade Werte aber angenehmer.
            if blur_radius % 2 == 0:
                blur_radius += 1
            base_image = self.get_prepared_image(force=True)
            if base_image is None:
                return
            self.special_result_image = self.build_logo_mask_image(
                base_image,
                threshold=threshold,
                blur_radius=blur_radius,
                foreground=fg_rgb,
                background=bg_rgb,
                clean=bool(self.logo_mask_clean_var.get()),
            )
        except Exception as exc:
            messagebox.showerror("Fehler", f"Logo-Maske konnte nicht erzeugt werden:\n{exc}")
            return

        self.edited_image = self.special_result_image.copy()
        reset = self.edited_canvas.image is None or self.edited_canvas.image.size != self.edited_image.size
        self.edited_canvas.set_image(self.edited_image, reset_view=reset)
        self.basic_status_label.configure(
            text=f"Logo-Maske aktiv: lokaler Kontrast, Schwelle {threshold}, Radius {blur_radius}. Export schreibt exakte RGB-Werte."
        )

    @staticmethod
    def build_logo_mask_image(
        image: Image.Image,
        threshold: int,
        blur_radius: int,
        foreground: RGB,
        background: RGB,
        clean: bool = True,
    ) -> Image.Image:
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        rgb = rgba[:, :, :3].astype(np.float32)
        alpha = rgba[:, :, 3]

        # Luminanz nach gaengiger Gewichtung: dunkle Striche werden besser getrennt als per RGB-Kanal.
        gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(np.uint8)
        gray_img = Image.fromarray(gray, "L")

        # Lokale Hintergrund-Schaetzung. Breite Schatten/Verlaeufe verschwinden dadurch weitgehend.
        bg_img = gray_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        bg = np.array(bg_img, dtype=np.int16)
        g = gray.astype(np.int16)

        # Positiv, wenn Pixel dunkler ist als lokale Umgebung.
        diff = bg - g
        mask = (diff >= int(threshold)) & (alpha > 0)

        if clean:
            # Schnell und ohne OpenCV: kleine Einzelpixel reduzieren.
            mask_img = Image.fromarray((mask.astype(np.uint8) * 255), "L")
            mask_img = mask_img.filter(ImageFilter.MedianFilter(size=3))
            # Opening: sehr kleine weisse Stoerungen entfernen, ohne die Kontur zu stark aufzublasen.
            mask_img = mask_img.filter(ImageFilter.MinFilter(size=3)).filter(ImageFilter.MaxFilter(size=3))
            mask = np.array(mask_img, dtype=np.uint8) >= 128

        h, w = gray.shape
        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[:, :, 0:3] = np.array(background, dtype=np.uint8)
        out[:, :, 3] = 255
        out[mask, 0:3] = np.array(foreground, dtype=np.uint8)
        return Image.fromarray(out, "RGBA")

    # ------------------------------------------------------------------ Erweiterter Modus
    def add_mapping(self, source: str = "0,0,0", target: str = "255,255,255") -> None:
        index = len(self.advanced_rows)
        row = ColorMappingRow(self, self.rows_container, index, source, target)
        self.advanced_rows.append(row)
        self.selected_row_var.set(index)
        self.update_status_selection()
        self.schedule_preview()

    def remove_selected_mapping(self) -> None:
        if not self.advanced_rows:
            return
        index = self.selected_row_var.get()
        if index < 0 or index >= len(self.advanced_rows):
            index = len(self.advanced_rows) - 1

        self.advanced_rows[index].destroy()
        del self.advanced_rows[index]

        for i, row in enumerate(self.advanced_rows):
            row.update_index(i)

        if not self.advanced_rows:
            self.add_mapping()
        else:
            self.selected_row_var.set(min(index, len(self.advanced_rows) - 1))
            self.update_status_selection()
            self.schedule_preview()

    def update_status_selection(self) -> None:
        self.status_label.configure(text=f"Selektierte Zeile: #{self.selected_row_var.get() + 1} | Kurzer Klick ins Originalbild übernimmt die Farbe; gedrückt ziehen verschiebt.")

    # ------------------------------------------------------------------ Vorschau / Export
    def schedule_preview(self) -> None:
        if self.preview_after_id is not None:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
        self.preview_after_id = self.after(250, self.update_preview)

    def collect_basic_mappings(self) -> list[MappingValues]:
        mappings: list[MappingValues] = []
        errors: list[str] = []
        threshold = self.get_basic_threshold()
        for i, row in enumerate(self.basic_rows, start=1):
            try:
                values = row.get_values(threshold)
                if values is not None:
                    mappings.append(values)
            except Exception as exc:
                errors.append(f"Basis #{i}: {exc}")

        if errors:
            self.basic_status_label.configure(text="Ungültige Eingabe: " + " | ".join(errors[:2]))
        return mappings

    def collect_advanced_mappings(self) -> list[MappingValues]:
        mappings: list[MappingValues] = []
        errors: list[str] = []
        for i, row in enumerate(self.advanced_rows, start=1):
            try:
                values = row.get_values()
                if values is not None:
                    mappings.append(values)
            except Exception as exc:
                errors.append(f"Zeile #{i}: {exc}")

        if errors:
            self.status_label.configure(text="Ungültige Eingabe: " + " | ".join(errors[:2]))
        return mappings

    def collect_active_mappings(self) -> list[MappingValues]:
        if self.current_mode() == "basic":
            return self.collect_basic_mappings()
        return self.collect_advanced_mappings()

    def update_preview(self) -> None:
        self.preview_after_id = None
        if self.original_image is None:
            return

        # Wenn der Spezialmodus "Logo-Maske" aktiv ist, darf die normale RGB-Ersetzung
        # die Maske nicht sofort wieder ueberschreiben.
        if self.current_mode() == "basic" and self.special_result_image is not None:
            self.edited_image = self.special_result_image.copy()
            reset = self.edited_canvas.image is None or self.edited_canvas.image.size != self.edited_image.size
            self.edited_canvas.set_image(self.edited_image, reset_view=reset)
            return

        mappings = self.collect_active_mappings()
        base_image = self.get_processing_base_image()
        if base_image is None:
            return
        try:
            # Im Basis-Modus ist base_image die vorbereitete Zwischenstufe.
            # Wenn noch keine Farben erkannt wurden, sieht man rechts diese Vorbereitung.
            self.edited_image = self.apply_mappings(base_image, mappings) if mappings else base_image.copy()
        except Exception as exc:
            messagebox.showerror("Fehler", f"Vorschau konnte nicht erstellt werden:\n{exc}")
            return

        reset = self.edited_canvas.image is None or self.edited_canvas.image.size != self.edited_image.size
        self.edited_canvas.set_image(self.edited_image, reset_view=reset)

        if self.current_mode() == "basic":
            if self.preprocess_dirty and self.basic_rows:
                self.basic_status_label.configure(
                    text="Bildvorbereitung geändert. Die rechte Vorschau nutzt alte Farbbereiche. Für saubere Erkennung bitte neu erkennen."
                )
            elif mappings:
                self.basic_status_label.configure(text=f"{len(mappings)} erkannte Farbbereiche werden mit exakten RGB-Werten ersetzt.")
            elif self.original_image is not None:
                self.basic_status_label.configure(text="Keine Basis-Farben aktiv. Rechts siehst du die vorbereitete Zwischenstufe. Dann 'Farben erkennen' klicken.")
        else:
            if mappings:
                self.status_label.configure(text=f"{len(mappings)} aktive manuelle Farbumsetzung(en) angewendet")
            else:
                self.status_label.configure(text="Keine aktive manuelle Farbumsetzung")

    @staticmethod
    def apply_mappings(image: Image.Image, mappings: list[MappingValues]) -> Image.Image:
        base = np.array(image.convert("RGBA"), dtype=np.uint8)
        result = base.copy()
        base_rgb = base[:, :, :3].astype(np.int16)

        for mapping in mappings:
            dst = np.array(mapping.target_rgb, dtype=np.uint8)
            mask = mask_for_rgb(base_rgb, mapping.source_rgb, mapping.tolerance)
            result[mask, 0:3] = dst
            # Alpha bleibt unveraendert, damit transparente PNGs sauber bleiben.

        return Image.fromarray(result, "RGBA")

    def export_png(self) -> None:
        if self.original_image is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein Bild laden.")
            return

        # Sicherstellen, dass die aktuellen Eingaben wirklich in der Exportdatei sind.
        if self.current_mode() == "basic" and self.special_result_image is not None:
            self.edited_image = self.special_result_image.copy()
            mappings = []
            base_image = None
        else:
            mappings = self.collect_active_mappings()
            base_image = self.get_processing_base_image()
        if self.edited_image is None:
            if base_image is None:
                return
            try:
                self.edited_image = self.apply_mappings(base_image, mappings) if mappings else base_image.copy()
            except Exception as exc:
                messagebox.showerror("Fehler", f"Export konnte nicht vorbereitet werden:\n{exc}")
                return
        elif base_image is not None:
            try:
                self.edited_image = self.apply_mappings(base_image, mappings) if mappings else base_image.copy()
            except Exception as exc:
                messagebox.showerror("Fehler", f"Export konnte nicht vorbereitet werden:\n{exc}")
                return

        if self.current_mode() == "basic" and self.special_result_image is not None:
            suffix = "logo_maske"
        else:
            suffix = "basis_umgefaerbt" if self.current_mode() == "basic" else "manuell_umgefaerbt"
        initial_name = f"{suffix}.png"
        if self.current_path:
            initial_name = f"{self.current_path.stem}_{suffix}.png"

        out_path = filedialog.asksaveasfilename(
            title="Als PNG exportieren",
            defaultextension=".png",
            initialfile=initial_name,
            filetypes=[("PNG-Datei", "*.png")],
        )
        if not out_path:
            return

        try:
            self.edited_image.save(out_path, format="PNG")
        except Exception as exc:
            messagebox.showerror("Exportfehler", f"PNG konnte nicht gespeichert werden:\n{exc}")
            return

        messagebox.showinfo("Export fertig", f"PNG gespeichert:\n{out_path}")


if __name__ == "__main__":
    app = RecolorApp()
    app.mainloop()

