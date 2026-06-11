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
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable, Optional, Tuple

import numpy as np
import cv2
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
    # Für Vorschau/Zoom nicht mit NEAREST skalieren, sonst wirkt es stark verpixelt.
    # Beim Vergrößern BICUBIC, beim Verkleinern LANCZOS.
    src_w, src_h = image.size
    dst_w, dst_h = size
    upsample = dst_w >= src_w or dst_h >= src_h
    resample = Image.Resampling.BICUBIC if upsample else Image.Resampling.LANCZOS
    resized = image.resize(size, resample)
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


def _assign_contrast_targets(found: list[tuple[RGB, int]], total_valid: int) -> list["DetectedColor"]:
    detected: list[DetectedColor] = []
    for index, (rep, count) in enumerate(found):
        palette_name, target = CONTRAST_PALETTE[index % len(CONTRAST_PALETTE)]
        percent = (count / max(1, total_valid)) * 100.0
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
        zoom_callback: Optional[Callable[[float], None]] = None,
        view_callback: Optional[Callable[["ZoomImageCanvas"], None]] = None,
        overlay_draw_callback: Optional[Callable[["ZoomImageCanvas"], None]] = None,
        mousewheel_zoom_enabled: bool = True,
        fast_pan: bool = False,
    ) -> None:
        super().__init__(parent)
        self.picker_callback = picker_callback
        self.zoom_callback = zoom_callback
        self.view_callback = view_callback
        self.overlay_draw_callback = overlay_draw_callback
        # Schritt 2 kann sehr große technische Raster- und Vektorvorschauen anzeigen.
        # Dort ist Mausrad-Zoom teuer, weil jeder Tick ein neues PIL/Tk-Bild erzeugt.
        # Für diese Fälle kann der Zoom bewusst über Buttons gesteuert werden.
        self.mousewheel_zoom_enabled = bool(mousewheel_zoom_enabled)
        # Fast-Pan reduziert die Anzahl kompletter Re-Render-Vorgänge während des Ziehens.
        # Dadurch bleibt das Verschieben bei großen Vorschauen deutlich reaktionsfähiger.
        self.fast_pan = bool(fast_pan)
        self.image: Optional[Image.Image] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._pan_start: Optional[Tuple[int, int, float, float]] = None
        self._left_press: Optional[Tuple[int, int, float, float]] = None
        self._left_dragged = False
        self._max_display_pixels = 30_000_000
        self._render_after_id: Optional[str] = None

        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(fill="x", padx=4, pady=(0, 4))
        self.title_label = ttk.Label(self.header_frame, text=title, font=("Segoe UI", 10, "bold"))
        self.title_label.pack(side="left")
        self.canvas = tk.Canvas(self, bg="#303030", highlightthickness=1, highlightbackground="#808080")
        self.canvas.pack(fill="both", expand=True)

        # Windows/macOS/Linux Mausrad.
        # Im normalen Bearbeitungsmodus bleibt Mausrad-Zoom erhalten.
        # In Schritt 2 kann er deaktiviert werden, weil Plus/Minus-Zoom in festen
        # Schritten wesentlich weniger versehentliche teure Re-Renders auslöst.
        wheel_handler = self._on_mousewheel if self.mousewheel_zoom_enabled else self._ignore_mousewheel
        self.canvas.bind("<MouseWheel>", wheel_handler)
        self.canvas.bind("<Button-4>", wheel_handler)
        self.canvas.bind("<Button-5>", wheel_handler)

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
        self._cancel_scheduled_render()
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
        # Auf Linux/Wayland kann das zu falschem Offset fuehren (Bild "unsichtbar").
        # Deshalb nicht auf grosse Fixwerte erzwingen, sondern bei zu kleiner Flaeche kurz spaeter erneut fitten.
        self.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 2 or ch <= 2:
            rw = self.canvas.winfo_reqwidth()
            rh = self.canvas.winfo_reqheight()
            cw = max(240, int(rw) if rw else 0)
            ch = max(180, int(rh) if rh else 0)
        if cw <= 2 or ch <= 2:
            self.after(30, self.fit_to_canvas)
            return
        iw, ih = self.image.size
        if iw <= 0 or ih <= 0:
            return

        # Kleine Bilder werden nicht kuenstlich vergroessert, grosse passend eingepasst.
        self.zoom = min(1.0, cw / iw, ch / ih)
        self.offset_x = (cw - iw * self.zoom) / 2
        self.offset_y = (ch - ih * self.zoom) / 2
        self.render()
        self._notify_zoom_changed()
        self._notify_view_changed()

    def _notify_zoom_changed(self) -> None:
        if self.zoom_callback is None:
            return
        try:
            self.zoom_callback(float(self.zoom))
        except Exception:
            pass

    def _notify_view_changed(self) -> None:
        if self.view_callback is None:
            return
        try:
            self.view_callback(self)
        except Exception:
            pass

    def _cancel_scheduled_render(self) -> None:
        if self._render_after_id:
            try:
                self.after_cancel(self._render_after_id)
            except Exception:
                pass
            self._render_after_id = None

    def schedule_render(self, delay_ms: int = 20) -> None:
        self._cancel_scheduled_render()
        self._render_after_id = self.after(max(1, int(delay_ms)), self.render)

    def set_zoom(self, zoom: float, defer_render: bool = True) -> None:
        if self.image is None:
            return
        old_zoom = max(0.0001, float(self.zoom))
        new_zoom = self._safe_zoom(float(zoom))
        if abs(new_zoom - old_zoom) < 0.0001:
            return

        cx = self.canvas.winfo_width() * 0.5
        cy = self.canvas.winfo_height() * 0.5
        img_x = (cx - self.offset_x) / old_zoom
        img_y = (cy - self.offset_y) / old_zoom
        self.zoom = new_zoom
        self.offset_x = cx - img_x * new_zoom
        self.offset_y = cy - img_y * new_zoom
        if defer_render:
            self.schedule_render()
        else:
            self.render()
        self._notify_zoom_changed()
        self._notify_view_changed()

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
        self._render_after_id = None
        self.canvas.delete("all")
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        canvas_bg = str(self.canvas.cget("bg") or "").strip()
        text_fill = "white"
        if canvas_bg.startswith("#") and len(canvas_bg) == 7:
            try:
                r = int(canvas_bg[1:3], 16)
                g = int(canvas_bg[3:5], 16)
                b = int(canvas_bg[5:7], 16)
                luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                text_fill = "#111111" if luminance > 150 else "#f3f3f3"
            except Exception:
                text_fill = "white"
        if self.image is None:
            self.canvas.create_text(
                cw // 2,
                ch // 2,
                text="Kein Bild geladen",
                fill=text_fill,
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
        if self.overlay_draw_callback is not None:
            try:
                self.overlay_draw_callback(self)
            except Exception:
                pass

        # kleiner Zoom-Hinweis unten links
        self.canvas.create_rectangle(4, ch - 26, 96, ch - 4, fill="#111111", outline="")
        self.canvas.create_text(50, ch - 15, text=f"Zoom {self.zoom * 100:.0f}%", fill="white")

    def _ignore_mousewheel(self, _event: tk.Event) -> str:
        # Bewusst blockiert: In performancelastigen Vorschauen wird Zoom über
        # feste Plus/Minus-Schritte gesteuert. Das verhindert ungewollte Serien
        # von Resize-Operationen durch das Mausrad.
        return "break"

    def _on_mousewheel(self, event: tk.Event) -> str:
        if self.image is None:
            return "break"

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
        self.schedule_render()
        self._notify_zoom_changed()
        self._notify_view_changed()
        return "break"

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
        if self.fast_pan:
            self.schedule_render(35)
        else:
            self.render()
        self._notify_view_changed()

    def _end_left_action(self, event: tk.Event) -> None:
        if self._left_press is None:
            return
        sx, sy, _ox, _oy = self._left_press
        moved = abs(event.x - sx) > 3 or abs(event.y - sy) > 3 or self._left_dragged
        self._left_press = None

        # Nur ein echter kurzer Klick nimmt Farbe auf. Ziehen verschiebt nur das Bild.
        if not moved:
            self._pick_pixel_at_canvas_pos(event.x, event.y)
        elif self.fast_pan:
            # Nach dem Loslassen einmal final rendern, damit die Vorschau exakt
            # am letzten Offset liegt, auch wenn während des Ziehens gedrosselt wurde.
            self.render()
        self._notify_view_changed()

    def _start_pan(self, event: tk.Event) -> None:
        self._pan_start = (event.x, event.y, self.offset_x, self.offset_y)

    def _move_pan(self, event: tk.Event) -> None:
        if self._pan_start is None:
            return
        sx, sy, ox, oy = self._pan_start
        self.offset_x = ox + (event.x - sx)
        self.offset_y = oy + (event.y - sy)
        if self.fast_pan:
            self.schedule_render(35)
        else:
            self.render()
        self._notify_view_changed()


# -----------------------------------------------------------------------------
# Scrollbarer Bereich fuer Farblisten
# -----------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget, height: int = 130, horizontal: bool = False) -> None:
        super().__init__(parent)
        self.horizontal = bool(horizontal)
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.h_scrollbar: Optional[ttk.Scrollbar] = None
        self.inner = ttk.Frame(self.canvas)

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        if self.horizontal:
            self.h_scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
            self.canvas.configure(xscrollcommand=self.h_scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        if self.h_scrollbar is not None:
            self.h_scrollbar.grid(row=1, column=0, sticky="ew")
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
        if self.horizontal:
            try:
                cw = max(1, self.canvas.winfo_width())
                iw = max(1, self.inner.winfo_reqwidth())
                self.canvas.itemconfigure(self.window_id, width=max(cw, iw))
            except Exception:
                pass

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if self.horizontal:
            iw = max(1, self.inner.winfo_reqwidth())
            self.canvas.itemconfigure(self.window_id, width=max(event.width, iw))
        else:
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
    fill_noise: int = 0
    fill_solid: bool = False


@dataclass
class DetectedColor:
    source_rgb: RGB
    target_rgb: RGB
    pixels: int
    percent: float
    palette_name: str


@dataclass
class PhotoScanAnalysis:
    score: int
    background_noise: float
    color_complexity: float
    small_specks: int
    edge_fray: float
    target_mismatch: float = 0.0


@dataclass
class PhotoScanCleanupResult:
    image: Image.Image
    detected: list[DetectedColor]
    analysis: PhotoScanAnalysis
    variant: str = ""
    technical_score: float = 0.0


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
            detected = self.detect_motif_colors_by_threshold(
                base_image,
                threshold=threshold,
                min_area=min_area,
                max_colors=max_colors,
                alpha_min=alpha_min,
                noise_suppression=int(self.basic_noise_var.get()) if hasattr(self, "basic_noise_var") else 45,
            )
            if len(detected) < 2:
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

        return _assign_contrast_targets(found, total_valid)

    @staticmethod
    def detect_motif_colors_by_threshold(
        image: Image.Image,
        threshold: int,
        min_area: int,
        max_colors: int,
        alpha_min: int,
        noise_suppression: int = 45,
    ) -> list[DetectedColor]:
        """
        Erkennt wenige Hauptfarben fuer Logos/Etiketten mit Papierstruktur.

        Anders als die einfache RGB-Haeufigkeit behandelt diese Methode eine
        helle, wenig kontrastreiche Hintergrundebene als Hintergrundrauschen.
        Uebrig bleiben zusammengefasste Motivfarben mit ausreichendem Abstand
        zum Hintergrund. Das ist keine Motiv-Sonderlogik, sondern eine
        generelle Vordergrund-/Hintergrundtrennung.
        """
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        rgb_full = rgba[:, :, :3]
        alpha = rgba[:, :, 3]
        valid_mask = alpha >= alpha_min
        total_valid = int(valid_mask.sum())
        if total_valid <= 0:
            return []
        noise_suppression = max(0, min(100, int(noise_suppression)))

        rgb_float = rgb_full.astype(np.float32)
        valid_pixels = rgb_float[valid_mask]
        gray = 0.299 * rgb_float[:, :, 0] + 0.587 * rgb_float[:, :, 1] + 0.114 * rgb_float[:, :, 2]
        rgb_norm = np.clip(rgb_float / 255.0, 0.0, 1.0)
        sat = np.max(rgb_norm, axis=2) - np.min(rgb_norm, axis=2)
        gray_values = gray[valid_mask]
        sat_values = sat[valid_mask]

        p50 = float(np.percentile(gray_values, 50))
        p75 = float(np.percentile(gray_values, 75))
        p92 = float(np.percentile(gray_values, 92))
        background_luma_floor = max(p50, p75 - 10.0)

        h, w = valid_mask.shape
        border_width = max(2, int(round(min(h, w) * 0.035)))
        border_mask = np.zeros_like(valid_mask, dtype=bool)
        border_mask[:border_width, :] = True
        border_mask[-border_width:, :] = True
        border_mask[:, :border_width] = True
        border_mask[:, -border_width:] = True
        border_candidates = valid_mask & border_mask & (gray >= background_luma_floor)
        if int(border_candidates.sum()) >= max(32, total_valid * 0.002):
            bg_pixels = rgb_float[border_candidates]
        else:
            bg_pixels = valid_pixels[gray_values >= background_luma_floor]
            if bg_pixels.size == 0:
                bg_pixels = valid_pixels
        background_rgb = np.median(bg_pixels, axis=0)
        background_sat = float(np.median(sat[valid_mask & (gray >= background_luma_floor)])) if np.any(valid_mask & (gray >= background_luma_floor)) else float(np.median(sat_values))

        color_distance = np.linalg.norm(rgb_float - background_rgb.reshape(1, 1, 3), axis=2)
        luma_distance = np.abs(gray - float(np.median(gray_values[gray_values >= background_luma_floor])) if np.any(gray_values >= background_luma_floor) else gray - p92)
        noise_bias = noise_suppression / 100.0
        foreground_distance = max(18.0, float(threshold) * (1.55 + noise_bias * 0.35))
        dark_ink_limit = min(p50 - 8.0, p92 - 34.0)
        colored_ink = (sat >= max(0.055, background_sat + 0.035 + noise_bias * 0.025)) & (color_distance >= max(12.0, float(threshold) * (0.85 + noise_bias * 0.20)))
        dark_ink = gray <= dark_ink_limit
        contrast_ink = (color_distance >= foreground_distance) | (luma_distance >= max(18.0, float(threshold) * 1.4))
        motif_mask = valid_mask & (colored_ink | dark_ink | contrast_ink)

        # Hintergrundtextur besteht oft aus winzigen Farbabweichungen. Eine
        # kleine Medianfilterung entfernt Einzelpixel, laesst Linien/Flaechen aber stehen.
        median_size = 3 if noise_suppression < 65 else 5
        mask_img = Image.fromarray((motif_mask.astype(np.uint8) * 255), "L").filter(ImageFilter.MedianFilter(size=median_size))
        motif_mask = np.array(mask_img, dtype=np.uint8) >= 128
        motif_count = int(motif_mask.sum())
        if motif_count < min_area:
            return []

        found: list[tuple[RGB, int]] = []
        motif_gray = gray[motif_mask]
        dark_cluster_limit = min(
            110.0,
            max(42.0, float(np.percentile(motif_gray, 30)) if motif_gray.size else 70.0),
        )
        dark_group_mask = motif_mask & (gray <= dark_cluster_limit)
        dark_group_count = int(dark_group_mask.sum())
        if dark_group_count >= min_area:
            dark_pixels = rgb_float[dark_group_mask]
            dark_rep = tuple(int(max(0, min(255, round(v)))) for v in np.median(dark_pixels, axis=0))
            found.append((dark_rep, dark_group_count))

        color_cluster_mask = motif_mask & ~dark_group_mask
        pixels = rgb_full[color_cluster_mask]
        if pixels.shape[0] <= 0:
            found.sort(key=lambda item: item[1], reverse=True)
            found = found[: max(1, int(max_colors))]
            return _assign_contrast_targets(found, total_valid)

        max_sample_pixels = 1_000_000
        if pixels.shape[0] > max_sample_pixels:
            step = int(math.ceil(pixels.shape[0] / max_sample_pixels))
            sample = pixels[::step]
        else:
            sample = pixels

        unique, counts = np.unique(sample, axis=0, return_counts=True)
        order = np.argsort(counts)[::-1]
        reps: list[np.ndarray] = []
        rep_counts: list[int] = []
        merge_distance = max(26.0, float(threshold) * 2.4)
        max_reps_to_build = max(1, int(max_colors)) * 5
        for idx in order:
            color_arr = unique[idx].astype(np.float32)
            count = int(counts[idx])
            best_index = -1
            best_distance = 10**9
            for rep_index, rep in enumerate(reps):
                dist = float(np.linalg.norm(color_arr - rep))
                if dist < best_distance:
                    best_distance = dist
                    best_index = rep_index
            if best_index >= 0 and best_distance <= merge_distance:
                current_count = rep_counts[best_index]
                new_count = current_count + count
                reps[best_index] = ((reps[best_index] * current_count) + (color_arr * count)) / max(1, new_count)
                rep_counts[best_index] = new_count
            else:
                reps.append(color_arr)
                rep_counts.append(count)
                if len(reps) >= max_reps_to_build:
                    break

        rgb_float_full = rgb_full.astype(np.float32)
        for rep in reps:
            dist = np.linalg.norm(rgb_float_full - rep.reshape(1, 1, 3), axis=2)
            mask = (dist <= merge_distance) & color_cluster_mask
            real_count = int(mask.sum())
            if real_count >= min_area:
                rep_rgb = tuple(int(max(0, min(255, round(v)))) for v in rep)
                found.append((rep_rgb, real_count))

        found.sort(key=lambda item: item[1], reverse=True)
        found = found[: max(1, int(max_colors))]
        return _assign_contrast_targets(found, total_valid)

    @staticmethod
    def analyze_photo_scan_logo_problem(image: Image.Image, target_colors: Optional[list[RGB]] = None) -> PhotoScanAnalysis:
        image = RecolorApp._limited_work_image(image, max_edge=1800)[0]
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3] > 0
        if not np.any(alpha):
            return PhotoScanAnalysis(0, 0.0, 0.0, 0, 0.0, 0.0)

        rgb_float = rgb.astype(np.float32)
        gray = (0.299 * rgb_float[:, :, 0] + 0.587 * rgb_float[:, :, 1] + 0.114 * rgb_float[:, :, 2]).astype(np.uint8)
        valid_gray = gray[alpha]
        bright_limit = max(170, int(np.percentile(valid_gray, 72)))
        bright_bg = alpha & (gray >= bright_limit)
        if int(bright_bg.sum()) < max(64, int(alpha.sum() * 0.08)):
            bright_bg = alpha & (gray >= int(np.percentile(valid_gray, 60)))

        blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
        residual = np.abs(gray.astype(np.int16) - blur.astype(np.int16)).astype(np.float32)
        background_noise = float(np.mean(residual[bright_bg])) if np.any(bright_bg) else 0.0

        sample = rgb[alpha]
        if sample.shape[0] > 250_000:
            step = int(math.ceil(sample.shape[0] / 250_000))
            sample = sample[::step]
        quant = (sample.astype(np.uint16) // 16).astype(np.uint8)
        unique_bins = int(np.unique(quant, axis=0).shape[0])
        color_complexity = float(unique_bins)

        edges = cv2.Canny(gray, 45, 130)
        edge_mask = (edges > 0) & alpha
        labels_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(edge_mask.astype(np.uint8), connectivity=8)
        small_specks = 0
        for label_id in range(1, labels_count):
            area = int(stats[label_id, cv2.CC_STAT_AREA])
            if 1 <= area <= 8:
                small_specks += 1
        edge_area = max(1, int(edge_mask.sum()))
        edge_fray = min(1.0, small_specks / max(25.0, edge_area * 0.030))

        target_mismatch = 0.0
        if target_colors:
            targets = np.array(target_colors, dtype=np.float32)
            if targets.ndim == 2 and targets.shape[0] > 0:
                diff = sample.astype(np.float32)[:, None, :] - targets[None, :, :]
                nearest = np.sqrt(np.sum(diff * diff, axis=2)).min(axis=1)
                target_mismatch = float(np.mean(nearest > 34.0))

        score = 0
        score += 2 if background_noise >= 8.0 else 1 if background_noise >= 4.0 else 0
        score += 2 if color_complexity >= 180 else 1 if color_complexity >= 80 else 0
        score += 2 if small_specks >= 900 else 1 if small_specks >= 250 else 0
        score += 2 if edge_fray >= 0.75 else 1 if edge_fray >= 0.35 else 0
        score += 2 if target_mismatch >= 0.30 else 1 if target_mismatch >= 0.12 else 0
        return PhotoScanAnalysis(
            score=int(score),
            background_noise=background_noise,
            color_complexity=color_complexity,
            small_specks=int(small_specks),
            edge_fray=edge_fray,
            target_mismatch=target_mismatch,
        )

    @staticmethod
    def _limited_work_image(image: Image.Image, max_edge: int = 1800) -> tuple[Image.Image, float]:
        width, height = image.size
        longest = max(width, height)
        if longest <= max_edge or longest <= 0:
            return image, 1.0
        scale = float(max_edge) / float(longest)
        new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        return image.resize(new_size, Image.Resampling.LANCZOS), scale

    @staticmethod
    def _component_filtered_color_accent_mask(
        raw_mask: np.ndarray,
        total_valid: int,
        image_width: int,
        image_height: int,
        *,
        min_area_ratio: float = 0.000008,
        max_area_ratio: float = 0.025,
        max_span_ratio: float = 0.18,
    ) -> np.ndarray:
        """Behaelt kleine/markante Farbakzente, aber keine grossen Hauptflaechen.

        Der Zweck ist nicht, farbige Logos farbig zu lassen, sondern z. B. rote Sterne
        oder gruene Schrift im Schwarz/Weiss-Modus als kontrastierende Aussparung zu
        erhalten. Grosse Farbflaechen wie Baender, Himmel, Wald oder Fluss werden hier
        bewusst nicht als Akzent behandelt.
        """
        if raw_mask.size == 0 or not np.any(raw_mask):
            return np.zeros_like(raw_mask, dtype=bool)
        labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(raw_mask.astype(np.uint8), connectivity=8)
        keep = np.zeros_like(raw_mask, dtype=bool)
        if labels_count <= 1:
            return keep
        min_area = max(3, int(round(float(max(1, total_valid)) * float(min_area_ratio))))
        max_area = max(min_area, int(round(float(max(1, total_valid)) * float(max_area_ratio))))
        max_w = max(2, int(round(float(max(1, image_width)) * float(max_span_ratio))))
        max_h = max(2, int(round(float(max(1, image_height)) * float(max_span_ratio))))
        for label_id in range(1, labels_count):
            area = int(stats[label_id, cv2.CC_STAT_AREA])
            width = int(stats[label_id, cv2.CC_STAT_WIDTH])
            height = int(stats[label_id, cv2.CC_STAT_HEIGHT])
            if area < min_area:
                continue
            # Lange Baender/Grossflaechen nicht als Akzent schuetzen.
            if area > max_area and (width > max_w or height > max_h):
                continue
            if width > max_w or height > max_h:
                continue
            keep[labels == label_id] = True
        return keep

    @staticmethod
    def _apply_local_opposite_to_accent_mask(out_rgba: np.ndarray, accent_mask: np.ndarray, alpha_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """Faerbt Akzent-Komponenten schwarz oder weiss je nach lokaler Umgebung.

        Beispiel: roter Stern im schwarzen Ring -> weisser Stern.
        Gruene Schrift auf schwarzem Ring -> weisse Schrift.
        Farbakzent auf hellem Papier -> schwarze Zeichnung.
        """
        if out_rgba.size == 0 or accent_mask.size == 0 or not np.any(accent_mask):
            return out_rgba
        if alpha_mask is None:
            valid = out_rgba[:, :, 3] > 0
        else:
            valid = alpha_mask.astype(bool)
        labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(accent_mask.astype(np.uint8), connectivity=8)
        if labels_count <= 1:
            return out_rgba
        gray_out = (
            0.299 * out_rgba[:, :, 0].astype(np.float32)
            + 0.587 * out_rgba[:, :, 1].astype(np.float32)
            + 0.114 * out_rgba[:, :, 2].astype(np.float32)
        )
        black_now = valid & np.all(out_rgba[:, :, 0:3] <= 20, axis=2)
        for label_id in range(1, labels_count):
            component = labels == label_id
            if not np.any(component):
                continue
            width = int(stats[label_id, cv2.CC_STAT_WIDTH])
            height = int(stats[label_id, cv2.CC_STAT_HEIGHT])
            # Eher enger Ring: fuer Sterne/Schrift auf schwarzem Band nicht zu viel weisses Umfeld mitnehmen.
            radius = max(2, min(11, int(round(max(width, height) * 0.10)) + 1))
            ksize = radius * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
            dilated = cv2.dilate(component.astype(np.uint8), kernel, iterations=1) > 0
            ring = dilated & ~component & valid
            if int(np.count_nonzero(ring)) < 6:
                ring = ~component & valid
            if np.any(ring):
                black_ratio = float(np.mean(black_now[ring]))
                surrounding = float(np.median(gray_out[ring]))
            else:
                black_ratio = 0.0
                surrounding = 255.0
            # Primär nach echter Schwarz-Nachbarschaft entscheiden, sonst über Helligkeit fallbacken.
            use_white = (black_ratio >= 0.35) or (black_ratio >= 0.20 and surrounding < 150.0) or (surrounding < 110.0)
            target = 255 if use_white else 0
            out_rgba[component, 0:3] = target
            out_rgba[component, 3] = 255
        return out_rgba

    @staticmethod
    def _detect_small_color_accents(
        rgb: np.ndarray,
        gray: np.ndarray,
        sat: np.ndarray,
        lab_distance: np.ndarray,
        alpha: np.ndarray,
        total_valid: int,
        *,
        foreground_distance: float = 24.0,
    ) -> np.ndarray:
        """Findet kleine bunte Akzente unabhaengig davon, ob sie schon Vordergrund sind."""
        if rgb.size == 0:
            return np.zeros(alpha.shape, dtype=bool)
        h, w = alpha.shape
        valid_gray = gray[alpha]
        p96 = float(np.percentile(valid_gray, 96)) if valid_gray.size else 245.0
        raw = (
            alpha
            & (sat >= 0.135)
            & (lab_distance >= max(8.0, float(foreground_distance) * 0.62))
            & (gray.astype(np.float32) <= min(248.0, p96 + 8.0))
        )
        return RecolorApp._component_filtered_color_accent_mask(raw, total_valid, w, h)

    @staticmethod
    def _photo_scan_foreground_mask_from_result(image: Image.Image) -> np.ndarray:
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        alpha = rgba[:, :, 3] > 0
        rgb = rgba[:, :, :3]
        return alpha & np.any(rgb < 245, axis=2)

    @staticmethod
    def _detected_colors_from_mask(mask: np.ndarray, total_valid: int, rgb: RGB = (0, 0, 0), target: RGB = (0, 0, 0)) -> list[DetectedColor]:
        count = int(np.count_nonzero(mask))
        if count <= 0:
            return []
        return [DetectedColor(source_rgb=rgb, target_rgb=target, pixels=count, percent=(count / max(1, total_valid)) * 100.0, palette_name="Schwarz")]


    @staticmethod
    def _rebuild_photo_scan_detected_from_technical_image(
        result: PhotoScanCleanupResult,
    ) -> PhotoScanCleanupResult:
        """Ermittelt die Farbzählung eines technischen Foto-/Scan-Ergebnisses neu.

        Das ist bewusst klein gehalten: Weiß ist Hintergrund, alle anderen
        exakten RGB-Farben gelten als technische Zielfarben. Es wird nur die
        Statistik aktualisiert, nicht das Bild neu berechnet.
        """
        try:
            arr = np.array(result.image.convert("RGBA"), dtype=np.uint8)
            if arr.size == 0:
                return result
            alpha = arr[:, :, 3] > 0
            rgb = arr[:, :, :3]
            total_valid = max(1, int(np.count_nonzero(alpha)))
            non_background = alpha & ~((rgb[:, :, 0] >= 248) & (rgb[:, :, 1] >= 248) & (rgb[:, :, 2] >= 248))
            if not np.any(non_background):
                result.detected = []
                return result
            existing_by_rgb = {tuple(int(v) for v in item.target_rgb): item for item in result.detected}
            colors = np.unique(rgb[non_background].reshape(-1, 3), axis=0)
            updated: list[DetectedColor] = []
            for color in colors:
                target_rgb = tuple(int(v) for v in color.tolist())
                count = int(np.count_nonzero(alpha & np.all(rgb == color.reshape(1, 1, 3), axis=2)))
                if count <= 0:
                    continue
                old = existing_by_rgb.get(target_rgb)
                updated.append(
                    DetectedColor(
                        source_rgb=old.source_rgb if old is not None else target_rgb,
                        target_rgb=target_rgb,
                        pixels=count,
                        percent=(count / total_valid) * 100.0,
                        palette_name=old.palette_name if old is not None else rgb_to_text(target_rgb),
                    )
                )
            updated.sort(key=lambda item: item.pixels, reverse=True)
            result.detected = updated
            return result
        except Exception:
            return result

    @staticmethod
    def _quiet_photo_scan_color_speckles(
        result: PhotoScanCleanupResult,
        min_area: int = 8,
        preserve_thin_lines: bool = True,
    ) -> PhotoScanCleanupResult:
        """Entfernt kleine farbige Einzelinseln aus dem technischen Foto-/Scan-Ergebnis.

        Der Auto-Modus darf feine Linien behalten, soll aber Papierkorn und einzelne
        blaue/rote/grüne Fremdpunkte nicht als eigene technische Zielfarbe ausgeben.
        Deshalb wird jede Ziel-RGB-Maske separat beruhigt: kleine Inseln werden
        entfernt, lange dünne Komponenten bleiben erhalten.
        """
        try:
            min_area = max(1, int(min_area))
            original_size = result.image.size
            longest = max(1, max(original_size))
            max_process_edge = 1200
            if longest > max_process_edge:
                scale = float(max_process_edge) / float(longest)
                small_size = (
                    max(1, int(round(original_size[0] * scale))),
                    max(1, int(round(original_size[1] * scale))),
                )
                small_result = PhotoScanCleanupResult(
                    result.image.resize(small_size, Image.Resampling.NEAREST),
                    list(result.detected),
                    result.analysis,
                    result.variant,
                    result.technical_score,
                )
                small_result = RecolorApp._quiet_photo_scan_color_speckles(
                    small_result,
                    min_area=max(1, int(round(float(min_area) * scale * scale))),
                    preserve_thin_lines=preserve_thin_lines,
                )
                small_total_valid = max(1, int(np.count_nonzero(np.array(small_result.image.convert("RGBA"), dtype=np.uint8)[:, :, 3] > 0)))
                small_result.image = small_result.image.resize(original_size, Image.Resampling.NEAREST)
                inv_area = 1.0 / max(1e-9, scale * scale)
                estimated_total_valid = max(1, int(round(float(small_total_valid) * inv_area)))
                for item in small_result.detected:
                    item.pixels = int(round(float(item.pixels) * inv_area))
                    item.percent = (item.pixels / estimated_total_valid) * 100.0
                small_result.variant = result.variant
                small_result.technical_score = result.technical_score
                return small_result

            image = result.image.convert("RGBA")
            arr = np.array(image, dtype=np.uint8)
            if arr.size == 0:
                return result
            alpha = arr[:, :, 3] > 0
            rgb = arr[:, :, :3]
            h, w = alpha.shape
            non_background = alpha & ~((rgb[:, :, 0] >= 248) & (rgb[:, :, 1] >= 248) & (rgb[:, :, 2] >= 248))
            if not np.any(non_background):
                return result
            colors = np.unique(rgb[non_background].reshape(-1, 3), axis=0)
            cleaned_any = False
            for color in colors:
                mask = alpha & np.all(rgb == color.reshape(1, 1, 3), axis=2)
                if int(np.count_nonzero(mask)) <= 0:
                    continue
                labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
                if labels_count <= 1:
                    continue
                areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                spans = np.maximum(widths, heights)
                mins = np.maximum(1, np.minimum(widths, heights))
                line_like = (
                    bool(preserve_thin_lines)
                    & (areas >= max(2, min_area // 3))
                    & (spans >= max(8, min(h, w) // 170))
                    & ((mins <= max(4, min(h, w) // 120)) | ((spans / mins.astype(np.float32)) >= 2.4))
                )
                keep_criteria = (areas >= min_area) | line_like
                keep = np.zeros(labels_count, dtype=bool)
                keep[1:] = keep_criteria
                clean_mask = keep[labels]
                removed = mask & ~clean_mask
                if np.any(removed):
                    arr[removed, 0:3] = 255
                    cleaned_any = True
            if not cleaned_any:
                return result
            new_image = Image.fromarray(arr, "RGBA")
            total_valid = max(1, int(np.count_nonzero(arr[:, :, 3] > 0)))
            updated_detected: list[DetectedColor] = []
            for item in result.detected:
                target = np.array(item.target_rgb, dtype=np.uint8).reshape(1, 1, 3)
                count = int(np.count_nonzero((arr[:, :, 3] > 0) & np.all(arr[:, :, :3] == target, axis=2)))
                if count <= 0:
                    continue
                updated_detected.append(
                    DetectedColor(
                        source_rgb=item.source_rgb,
                        target_rgb=item.target_rgb,
                        pixels=count,
                        percent=(count / total_valid) * 100.0,
                        palette_name=item.palette_name,
                    )
                )
            result.image = new_image
            result.detected = updated_detected
            return result
        except Exception:
            return result

    @staticmethod
    def _solidify_photo_scan_technical_image(
        result: PhotoScanCleanupResult,
        speckle_area: int = 18,
        hole_area: int = 80,
        preserve_thin_lines: bool = True,
    ) -> PhotoScanCleanupResult:
        """Macht das technische Foto-/Scan-Ergebnis flächiger.

        Performance-Version:
        Kleine Fremdfarb-Inseln und weiße Löcher werden nicht mehr Komponente
        für Komponente mit eigener Nachbarschaftssuche abgearbeitet. Stattdessen
        werden die kleinen Komponenten gesammelt und mit einer vektorisierten
        lokalen Mehrheitsfarbe ersetzt. Das ist bei großen Scans deutlich
        schneller und verhindert lange Hänger bei „Masken werden bereinigt“.
        """
        try:
            speckle_area = max(1, int(speckle_area))
            hole_area = max(speckle_area, int(hole_area))
            original_size = result.image.size
            longest = max(1, max(original_size))

            # Die Bereinigung ist bewusst eine technische Zwischenstufe. Für die
            # Entscheidung, welche Mini-Inseln verschwinden, reicht eine moderate
            # Arbeitsgröße völlig aus. Danach wird wieder mit NEAREST skaliert,
            # damit die exakten Zielfarben erhalten bleiben.
            max_process_edge = 900
            if longest > max_process_edge:
                scale = float(max_process_edge) / float(longest)
                small_size = (
                    max(1, int(round(original_size[0] * scale))),
                    max(1, int(round(original_size[1] * scale))),
                )
                small_result = PhotoScanCleanupResult(
                    result.image.resize(small_size, Image.Resampling.NEAREST),
                    list(result.detected),
                    result.analysis,
                    result.variant,
                    result.technical_score,
                )
                small_result = RecolorApp._solidify_photo_scan_technical_image(
                    small_result,
                    speckle_area=max(1, int(round(float(speckle_area) * scale * scale))),
                    hole_area=max(1, int(round(float(hole_area) * scale * scale))),
                    preserve_thin_lines=preserve_thin_lines,
                )
                small_total_valid = max(
                    1,
                    int(np.count_nonzero(np.array(small_result.image.convert("RGBA"), dtype=np.uint8)[:, :, 3] > 0)),
                )
                small_result.image = small_result.image.resize(original_size, Image.Resampling.NEAREST)
                inv_area = 1.0 / max(1e-9, scale * scale)
                estimated_total_valid = max(1, int(round(float(small_total_valid) * inv_area)))
                for item in small_result.detected:
                    item.pixels = int(round(float(item.pixels) * inv_area))
                    item.percent = (item.pixels / estimated_total_valid) * 100.0
                small_result.variant = result.variant
                small_result.technical_score = result.technical_score
                return small_result

            arr = np.array(result.image.convert("RGBA"), dtype=np.uint8)
            if arr.size == 0:
                return result

            alpha = arr[:, :, 3] > 0
            h, w = alpha.shape
            if h <= 0 or w <= 0:
                return result

            rgb = arr[:, :, :3]
            white_mask = alpha & ((rgb[:, :, 0] >= 248) & (rgb[:, :, 1] >= 248) & (rgb[:, :, 2] >= 248))
            non_white = alpha & ~white_mask
            if not np.any(non_white):
                return result

            colors = np.unique(rgb[non_white].reshape(-1, 3), axis=0)
            if colors.size == 0:
                return result

            # Maximal kleine Komponenten umfaerben. Wenn extrem viele Mikro-Inseln
            # entstehen, ist eine vollstaendige exakte Behandlung nicht sinnvoll;
            # dann arbeitet die globale Mehrheitskorrektur trotzdem sauber und schnell.
            changed = False
            remove_mask = np.zeros((h, w), dtype=bool)

            for color in colors:
                color_mask = alpha & np.all(rgb == color.reshape(1, 1, 3), axis=2)
                if not np.any(color_mask):
                    continue
                labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
                    color_mask.astype(np.uint8), connectivity=8
                )
                if labels_count <= 1:
                    continue

                areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                spans = np.maximum(widths, heights)
                min_sides = np.maximum(1, np.minimum(widths, heights))
                line_like = (
                    bool(preserve_thin_lines)
                    & (areas >= max(2, speckle_area // 4))
                    & (spans >= max(8, min(h, w) // 170))
                    & ((min_sides <= max(4, min(h, w) // 120)) | ((spans / min_sides.astype(np.float32)) >= 2.6))
                )
                small = (areas < speckle_area) & ~line_like
                if not np.any(small):
                    continue
                remove_lookup = np.zeros(labels_count, dtype=bool)
                remove_lookup[1:] = small
                remove_mask |= remove_lookup[labels]

            # Kleine weiße Löcher innerhalb farbiger Flächen sammeln.
            hole_mask = np.zeros((h, w), dtype=bool)
            labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(white_mask.astype(np.uint8), connectivity=8)
            if labels_count > 1:
                areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                lefts = stats[1:, cv2.CC_STAT_LEFT].astype(np.int64)
                tops = stats[1:, cv2.CC_STAT_TOP].astype(np.int64)
                widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                inside = (lefts > 0) & (tops > 0) & ((lefts + widths) < w) & ((tops + heights) < h)
                small_holes = (areas > 0) & (areas <= hole_area) & inside
                if np.any(small_holes):
                    hole_lookup = np.zeros(labels_count, dtype=bool)
                    hole_lookup[1:] = small_holes
                    hole_mask = hole_lookup[labels]

            if not np.any(remove_mask) and not np.any(hole_mask):
                return result

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)).astype(np.uint8)
            palette = [np.array((255, 255, 255), dtype=np.uint8)] + [np.array(c, dtype=np.uint8) for c in colors]

            def _apply_majority(target_mask: np.ndarray, allow_white: bool) -> bool:
                if not np.any(target_mask):
                    return False
                counts: list[np.ndarray] = []
                candidates: list[np.ndarray] = []
                for candidate in palette:
                    is_white = bool(np.all(candidate >= 248))
                    if is_white and not allow_white:
                        continue
                    mask = alpha & np.all(arr[:, :, :3] == candidate.reshape(1, 1, 3), axis=2)
                    if not np.any(mask):
                        continue
                    # Anzahl Nachbarpixel dieser Farbe im 5x5 Umfeld.
                    cnt = cv2.filter2D(mask.astype(np.uint8), cv2.CV_16U, kernel, borderType=cv2.BORDER_CONSTANT)
                    counts.append(cnt)
                    candidates.append(candidate)
                if not counts:
                    return False
                stack = np.stack(counts, axis=0)
                best_idx = np.argmax(stack, axis=0)
                best_count = np.max(stack, axis=0)
                valid = target_mask & (best_count >= 1)
                if not np.any(valid):
                    return False
                for idx, candidate in enumerate(candidates):
                    selected = valid & (best_idx == idx)
                    if np.any(selected):
                        arr[selected, 0:3] = candidate.reshape(1, 3)
                return True

            # Fremdfarbpunkte dürfen weiß werden, wenn sie im Papierbereich liegen.
            changed = _apply_majority(remove_mask, allow_white=True) or changed
            # Weiße Löcher sollen nur mit echter Zielfarbe gefüllt werden, nicht wieder weiß.
            changed = _apply_majority(hole_mask, allow_white=False) or changed

            if not changed:
                return result

            new_image = Image.fromarray(arr, "RGBA")
            total_valid = max(1, int(np.count_nonzero(arr[:, :, 3] > 0)))
            existing_by_rgb = {tuple(item.target_rgb): item for item in result.detected}
            updated_detected: list[DetectedColor] = []
            rgb_now = arr[:, :, :3]
            non_white_now = alpha & ~((rgb_now[:, :, 0] >= 248) & (rgb_now[:, :, 1] >= 248) & (rgb_now[:, :, 2] >= 248))
            if np.any(non_white_now):
                for color in np.unique(rgb_now[non_white_now].reshape(-1, 3), axis=0):
                    target_rgb = tuple(int(v) for v in color.tolist())
                    count = int(np.count_nonzero(alpha & np.all(rgb_now == color.reshape(1, 1, 3), axis=2)))
                    if count <= 0:
                        continue
                    old = existing_by_rgb.get(target_rgb)
                    updated_detected.append(
                        DetectedColor(
                            source_rgb=old.source_rgb if old is not None else target_rgb,
                            target_rgb=target_rgb,
                            pixels=count,
                            percent=(count / total_valid) * 100.0,
                            palette_name=old.palette_name if old is not None else rgb_to_text(target_rgb),
                        )
                    )
            result.image = new_image
            result.detected = updated_detected
            return result
        except Exception:
            return result

    @staticmethod
    def _score_photo_scan_result(original: Image.Image, result: PhotoScanCleanupResult, variant: str = "balanced") -> float:
        try:
            work_original, _scale = RecolorApp._limited_work_image(original.convert("RGBA"), max_edge=900)
            work_result = result.image.convert("RGBA")
            if work_result.size != work_original.size:
                work_result = work_result.resize(work_original.size, Image.Resampling.NEAREST)
            rgba = np.array(work_original, dtype=np.uint8)
            rgb = rgba[:, :, :3]
            alpha = rgba[:, :, 3] > 0
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            foreground = RecolorApp._photo_scan_foreground_mask_from_result(work_result) & alpha
            total = max(1, int(np.count_nonzero(alpha)))
            fg_pixels = int(np.count_nonzero(foreground))
            coverage = fg_pixels / float(total)
            if fg_pixels <= 0:
                return -9999.0

            cand_u8 = foreground.astype(np.uint8) * 255
            orig_edges = cv2.Canny(gray, 45, 135) > 0
            cand_edges = cv2.Canny(cand_u8, 45, 135) > 0
            edge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            orig_edges_wide = cv2.dilate(orig_edges.astype(np.uint8), edge_kernel, iterations=1) > 0
            edge_match = float(np.count_nonzero(cand_edges & orig_edges_wide)) / float(max(1, np.count_nonzero(cand_edges)))

            label_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(foreground.astype(np.uint8), connectivity=8)
            areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64) if label_count > 1 else np.array([], dtype=np.int64)
            small = int(np.count_nonzero((areas > 0) & (areas <= max(2, total * 0.000015))))
            tiny_ratio = small / max(1.0, float(label_count - 1))
            largest_ratio = float(areas.max()) / float(max(1, fg_pixels)) if areas.size else 0.0
            component_density = (label_count - 1) / max(1.0, fg_pixels / 1000.0)

            out_rgb = np.array(work_result.convert("RGB"), dtype=np.uint8)
            non_bg = out_rgb[foreground]
            unique_colors = np.unique(non_bg.reshape(-1, 3), axis=0).shape[0] if non_bg.size else 0
            color_penalty = max(0, int(unique_colors) - (1 if variant == "bw" else 4)) * 0.9

            if variant == "clean":
                target_low, target_high = 0.010, 0.42
                density_weight, detail_weight = 1.2, 0.7
            elif variant == "detail":
                target_low, target_high = 0.004, 0.62
                density_weight, detail_weight = 0.65, 1.25
            elif variant == "color":
                target_low, target_high = 0.008, 0.58
                density_weight, detail_weight = 0.9, 1.0
            elif variant == "bw":
                target_low, target_high = 0.004, 0.55
                density_weight, detail_weight = 0.8, 1.15
            else:
                target_low, target_high = 0.008, 0.52
                density_weight, detail_weight = 1.0, 1.0

            coverage_penalty = 0.0
            if coverage < target_low:
                coverage_penalty += (target_low - coverage) * 240.0
            if coverage > target_high:
                coverage_penalty += (coverage - target_high) * 60.0

            score = 0.0
            score += edge_match * 36.0 * detail_weight
            score += min(18.0, largest_ratio * 18.0)
            score -= tiny_ratio * 22.0 * density_weight
            score -= min(18.0, component_density * 0.18) * density_weight
            score -= coverage_penalty
            score -= color_penalty
            score -= max(0.0, result.analysis.background_noise - 12.0) * 0.15
            return float(score)
        except Exception:
            return -9999.0

    @staticmethod
    def build_photo_scan_black_white_image(
        image: Image.Image,
        min_area: int = 4,
        noise_suppression: int = 62,
        foreground_distance: int = 24,
        weak_contrast: int = 70,
        protect_background: bool = True,
        protect_thin_lines: bool = True,
        close_lines: bool = True,
        fill_small_holes: bool = False,
        preserve_color_accents: bool = False,
        max_work_edge: int = 1500,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> PhotoScanCleanupResult:
        def progress(value: float, key: str) -> None:
            if progress_callback is not None:
                progress_callback(float(value), key)

        def check_cancel() -> None:
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("cancelled")

        original_size = image.size
        progress(8, "progress.prepare_image")
        work_image, work_scale = RecolorApp._limited_work_image(image, max_edge=max_work_edge)
        rgba = np.array(work_image.convert("RGBA"), dtype=np.uint8)
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3] > 0
        h, w = alpha.shape
        total_valid = int(np.count_nonzero(alpha))
        analysis = RecolorApp.analyze_photo_scan_logo_problem(work_image)
        if total_valid <= 0:
            out = np.zeros((h, w, 4), dtype=np.uint8)
            return PhotoScanCleanupResult(Image.fromarray(out, "RGBA"), [], analysis, "bw", 0.0)

        progress(22, "progress.photo_scan_background")
        check_cancel()
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1].astype(np.float32) / 255.0
        valid_gray = gray[alpha]
        p50 = float(np.percentile(valid_gray, 50))
        p82 = float(np.percentile(valid_gray, 82))
        bright_bg = alpha & (gray >= max(160, int(p82 - 6))) & (sat <= 0.45)
        if int(np.count_nonzero(bright_bg)) < max(64, total_valid * 0.03):
            bright_bg = alpha & (gray >= int(p50))
        bg_rgb = np.median(rgb[bright_bg].astype(np.float32), axis=0) if np.any(bright_bg) else np.median(rgb[alpha].astype(np.float32), axis=0)
        bg_lab = cv2.cvtColor(np.uint8([[bg_rgb]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
        lab_distance = np.linalg.norm(lab - bg_lab.reshape(1, 1, 3), axis=2)

        progress(40, "progress.photo_scan_main_masks")
        check_cancel()
        clahe = cv2.createCLAHE(clipLimit=2.0 + max(0, weak_contrast) / 70.0, tileGridSize=(8, 8))
        gray_clahe = clahe.apply(gray)
        block = max(15, int(round(min(h, w) / 22.0)) | 1)
        block = min(block, 101)
        local_inv = cv2.adaptiveThreshold(gray_clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 7)
        local_bg = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), max(2.0, min(h, w) * 0.012))
        local_dark = local_bg - gray.astype(np.float32)
        _thr, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        weak_factor = max(0.0, min(1.0, weak_contrast / 100.0))
        noise_factor = max(0.0, min(1.0, noise_suppression / 100.0))
        color_term = lab_distance >= max(4.0, foreground_distance * (0.68 + noise_factor * 0.20))
        dark_term = local_dark >= max(2.0, 10.0 - weak_factor * 7.0)
        foreground = alpha & (((local_inv > 0) & (dark_term | color_term)) | ((otsu_inv > 0) & (gray < p82 - 8)))
        foreground |= alpha & color_term & (sat >= 0.08)

        if protect_background:
            background_like = alpha & (lab_distance < max(3.0, foreground_distance * 0.55)) & (gray >= max(135, p50 - 5)) & (sat <= 0.36)
            foreground &= ~background_like

        # Allgemeine Schutzregel für kleine Farbakzente:
        # kleine, inhaltlich wichtige Elemente sollen nicht durch eine rein
        # globale Schwarzfärbung unsichtbar werden. Stattdessen werden sie als
        # eigene Komponenten gemerkt und erst beim Rendern lokal kontrastierend
        # schwarz oder weiß gesetzt.
        # Farbakzente (z. B. rote Sterne/gruene Schrift) werden im S/W-Modus
        # NICHT mehr einfach zum schwarzen Vordergrund addiert. Sonst sind sie auf
        # einem schwarzen Ring zwar erkannt, werden aber schwarz und verschwinden.
        # Stattdessen merken wir die Komponenten separat und faerben sie beim Rendern
        # lokal gegensaetzlich: dunkle Umgebung -> weiss, helle Umgebung -> schwarz.
        accent_preserve_mask = np.zeros_like(foreground, dtype=bool)
        if preserve_color_accents:
            accent_preserve_mask = RecolorApp._detect_small_color_accents(
                rgb,
                gray,
                sat,
                lab_distance,
                alpha,
                total_valid,
                foreground_distance=float(foreground_distance),
            )

        progress(56, "progress.photo_scan_detail_masks")
        check_cancel()
        if protect_thin_lines:
            edges = cv2.Canny(gray_clahe, 32, 120) > 0
            edge_dark = edges & alpha & ((local_dark >= max(1.5, 6.0 - weak_factor * 4.0)) | color_term)
            foreground |= edge_dark

        progress(70, "progress.photo_scan_cleanup")
        check_cancel()
        mask_u8 = (foreground.astype(np.uint8) * 255)
        if close_lines:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, k, iterations=1)
        if fill_small_holes:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, k, iterations=1)
        if noise_suppression >= 55:
            k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            opened = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, k, iterations=1)
            if protect_thin_lines:
                mask_u8 = np.maximum(opened, (foreground.astype(np.uint8) * 255))
            else:
                mask_u8 = opened

        labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats((mask_u8 >= 128).astype(np.uint8), connectivity=8)
        cleaned = np.zeros((h, w), dtype=bool)
        min_area = max(1, int(min_area))
        if labels_count > 1:
            areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
            widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
            heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
            spans = np.maximum(widths, heights)
            mins = np.maximum(1, np.minimum(widths, heights))
            long_thin = protect_thin_lines & (spans >= max(7, min(h, w) // 180)) & (
                (mins <= max(4, min(h, w) // 110)) | ((spans / mins.astype(np.float32)) >= 2.2)
            )
            criteria = (areas >= min_area) | long_thin
            keep = np.zeros(labels_count, dtype=bool)
            keep[1:] = criteria
            cleaned = keep[labels]

        if preserve_color_accents and np.any(accent_preserve_mask):
            # Akzentpixel aus dem schwarzen Grund entfernen, damit sie als weisse
            # Aussparung sichtbar werden koennen, wenn die Umgebung dunkel ist.
            cleaned = cleaned & ~accent_preserve_mask

        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[:, :, 0:3] = 255
        out[:, :, 3] = rgba[:, :, 3]
        out[cleaned, 0:3] = 0
        if preserve_color_accents and np.any(accent_preserve_mask):
            out = RecolorApp._apply_local_opposite_to_accent_mask(out, accent_preserve_mask, alpha)
        result_image = Image.fromarray(out, "RGBA")
        black_mask_for_stats = alpha & np.all(out[:, :, 0:3] <= 12, axis=2)
        detected = RecolorApp._detected_colors_from_mask(black_mask_for_stats, total_valid, (0, 0, 0), (0, 0, 0))
        if result_image.size != original_size:
            result_image = result_image.resize(original_size, Image.Resampling.NEAREST)
            if work_scale > 0:
                inv_area = 1.0 / max(1e-9, work_scale * work_scale)
                estimated_total_valid = max(1, int(round(float(total_valid) * inv_area)))
                for item in detected:
                    item.pixels = int(round(float(item.pixels) * inv_area))
                    item.percent = (item.pixels / estimated_total_valid) * 100.0
        result = PhotoScanCleanupResult(result_image, detected, analysis, "bw", 0.0)
        result.technical_score = RecolorApp._score_photo_scan_result(image, result, "bw")
        progress(100, "progress.render_preview")
        return result

    @staticmethod
    def build_photo_scan_faded_print_image(
        image: Image.Image,
        min_area: int = 3,
        noise_suppression: int = 54,
        weak_contrast: int = 92,
        close_lines: bool = True,
        max_work_edge: int = 1300,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> PhotoScanCleanupResult:
        """Spezialmodus fuer sehr schwachen/verblassten Druck.

        Anders als die normale Farbreduktion sucht dieser Weg keine stabilen
        Motivfarben. Er schaetzt den Papier-/Lichtverlauf, zieht ihn ab,
        verstaerkt lokale Druckspuren und erzeugt daraus eine Schwarz/Weiss-
        Maske. Geeignet fuer schwache Stempel, alte Etiketten und Papierfotos,
        bei denen Motivfarbe und Hintergrund fast gleich sind.
        """
        def progress(value: float, key: str) -> None:
            if progress_callback is not None:
                progress_callback(float(value), key)

        def check_cancel() -> None:
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("cancelled")

        original_size = image.size
        progress(8, "progress.prepare_image")
        work_image, work_scale = RecolorApp._limited_work_image(image, max_edge=max_work_edge)
        rgba = np.array(work_image.convert("RGBA"), dtype=np.uint8)
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3] > 0
        h, w = alpha.shape
        total_valid = int(np.count_nonzero(alpha))
        analysis = RecolorApp.analyze_photo_scan_logo_problem(work_image)
        if total_valid <= 0:
            out = np.zeros((h, w, 4), dtype=np.uint8)
            return PhotoScanCleanupResult(Image.fromarray(out, "RGBA"), [], analysis, "faded", 0.0)

        progress(20, "progress.photo_scan_faded_background")
        check_cancel()
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gray_f = gray.astype(np.float32)
        longest = max(h, w)
        # Großer Weichzeichner: Papierfarbe, Schatten und Scanner-Vignette schaetzen.
        sigma_large = max(12.0, float(longest) * 0.045)
        background = cv2.GaussianBlur(gray_f, (0, 0), sigmaX=sigma_large, sigmaY=sigma_large)
        residual_dark = background - gray_f
        residual_abs = np.abs(gray_f - background)

        progress(38, "progress.photo_scan_faded_contrast")
        check_cancel()
        # Lokaler Kontrast auf dem abgezogenen Signal, nicht auf der Rohfarbe.
        norm = residual_dark.copy()
        norm[~alpha] = 0.0
        p_high = float(np.percentile(norm[alpha], 99.2)) if np.any(alpha) else 1.0
        norm = np.clip(norm * (255.0 / max(1.0, p_high)), 0, 255).astype(np.uint8)
        clip = 2.0 + max(0, min(100, int(weak_contrast))) / 28.0
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
        contrast = clahe.apply(norm)

        progress(56, "progress.photo_scan_faded_threshold")
        check_cancel()
        weak_factor = max(0.0, min(1.0, float(weak_contrast) / 100.0))
        noise_factor = max(0.0, min(1.0, float(noise_suppression) / 100.0))
        valid_res = residual_dark[alpha]
        # Bei sehr schwachem Druck niedrigere Schwelle, aber mit zusätzlicher
        # Kontrastbedingung, damit Papierkorn nicht komplett schwarz wird.
        res_thr = max(1.2, float(np.percentile(valid_res, 82.0 - weak_factor * 18.0))) if valid_res.size else 3.0
        contrast_thr = int(max(9, 34 - weak_factor * 20 + noise_factor * 5))
        block = max(21, int(round(min(h, w) / 16.0)) | 1)
        block = min(block, 151)
        local = cv2.adaptiveThreshold(contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, -2)
        mask = alpha & (residual_dark >= res_thr) & ((contrast >= contrast_thr) | (local > 0))

        # Gedruckte schwache Linien koennen auch nur als Kante sichtbar sein.
        edges = cv2.Canny(contrast, 18, 70) > 0
        mask |= alpha & edges & (residual_abs >= max(1.0, res_thr * 0.55)) & (contrast >= max(7, contrast_thr - 8))

        progress(74, "progress.photo_scan_cleanup")
        check_cancel()
        mask_u8 = (mask.astype(np.uint8) * 255)
        if close_lines:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, k, iterations=1)

        # Bei hohem Rauschen keine grossen Flaechen aggressiv öffnen, sonst gehen
        # schwache Buchstaben verloren. Nur Einzelkorn etwas beruhigen.
        if noise_suppression >= 55:
            k2 = np.ones((2, 2), dtype=np.uint8)
            opened = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, k2, iterations=1)
            mask_u8 = np.maximum(opened, (edges.astype(np.uint8) * 255) & mask_u8)

        labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats((mask_u8 >= 128).astype(np.uint8), connectivity=8)
        cleaned = np.zeros((h, w), dtype=bool)
        min_area = max(1, int(min_area))
        if labels_count > 1:
            areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
            widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
            heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
            spans = np.maximum(widths, heights)
            mins = np.maximum(1, np.minimum(widths, heights))
            long_thin = (spans >= max(6, min(h, w) // 200)) & (
                (mins <= max(4, min(h, w) // 120)) | ((spans / mins.astype(np.float32)) >= 2.0)
            )
            keep = np.zeros(labels_count, dtype=bool)
            keep[1:] = (areas >= min_area) | long_thin
            cleaned = keep[labels]

        progress(90, "progress.render_preview")
        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[:, :, 0:3] = 255
        out[:, :, 3] = rgba[:, :, 3]
        out[cleaned, 0:3] = 0
        result_image = Image.fromarray(out, "RGBA")
        detected = RecolorApp._detected_colors_from_mask(cleaned, total_valid, (0, 0, 0), (0, 0, 0))
        if result_image.size != original_size:
            result_image = result_image.resize(original_size, Image.Resampling.NEAREST)
            if work_scale > 0:
                inv_area = 1.0 / max(1e-9, work_scale * work_scale)
                estimated_total_valid = max(1, int(round(float(total_valid) * inv_area)))
                for item in detected:
                    item.pixels = int(round(float(item.pixels) * inv_area))
                    item.percent = (item.pixels / estimated_total_valid) * 100.0
        result = PhotoScanCleanupResult(result_image, detected, analysis, "faded", 0.0)
        result.technical_score = RecolorApp._score_photo_scan_result(image, result, "faded")
        progress(100, "progress.render_preview")
        return result

    @staticmethod
    def build_photo_scan_auto_image(
        image: Image.Image,
        preference: str = "auto",
        max_colors: int = 3,
        min_area: int = 6,
        preserve_color_accents: bool = False,
        max_work_edge: int = 1050,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> PhotoScanCleanupResult:
        def progress(value: float, key: str) -> None:
            if progress_callback is not None:
                progress_callback(float(value), key)

        def check_cancel() -> None:
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("cancelled")

        max_work_edge = max(480, min(820, int(max_work_edge)))
        analysis = RecolorApp.analyze_photo_scan_logo_problem(image)
        preference = (preference or "auto").strip().lower()
        base_min = max(1, int(min_area))
        requested_colors = max(1, min(8, int(max_colors)))
        bw_likely = analysis.color_complexity < 80 or requested_colors <= 2
        candidates: list[tuple[str, dict[str, object]]] = []
        if preference == "auto":
            # Der Auto-Modus darf nicht minutenlang auf 1/5 stehen bleiben.
            # Deshalb werden nur robuste Universal-Kandidaten getestet;
            # "Detail" bleibt als eigener manueller Modus verfuegbar.
            clean_params = dict(max_colors=max(2, min(3, requested_colors)), min_area=max(base_min * 2, 8), noise_suppression=88, foreground_distance=38, weak_contrast=12, protect_background=True, object_mask_first=True, despeckle=True, despeckle_min_area=max(base_min * 2, 8), protect_thin_lines=True, close_lines=True, fill_small_holes=True, preserve_color_accents=preserve_color_accents)
            balanced_params = dict(max_colors=max(3, requested_colors), min_area=max(base_min * 2, 8), noise_suppression=74, foreground_distance=30, weak_contrast=34, protect_background=True, object_mask_first=True, despeckle=True, despeckle_min_area=max(base_min * 2, 10), protect_thin_lines=True, close_lines=True, fill_small_holes=True, preserve_color_accents=preserve_color_accents)
            color_params = dict(max_colors=max(4, requested_colors + 1), min_area=max(2, base_min), noise_suppression=55, foreground_distance=24, weak_contrast=45, protect_background=True, object_mask_first=False, despeckle=True, despeckle_min_area=max(base_min, 3), protect_thin_lines=True, close_lines=True, fill_small_holes=False, preserve_color_accents=preserve_color_accents)
            if bw_likely or requested_colors <= 2:
                candidates.extend([("bw", {}), ("clean", clean_params)])
            else:
                # Schnellere Auto-Suche: robuste Hauptkandidaten testen.
                # Der farbige Spezialfall bleibt als eigener manueller Modus verfuegbar.
                candidates.extend([("clean", clean_params), ("balanced", balanced_params), ("bw", {})])
        else:
            lookup = {
                "clean": dict(max_colors=max(2, min(3, requested_colors)), min_area=max(base_min * 2, 8), noise_suppression=88, foreground_distance=38, weak_contrast=12, protect_background=True, object_mask_first=True, despeckle=True, despeckle_min_area=max(base_min * 2, 8), protect_thin_lines=True, close_lines=True, fill_small_holes=True, preserve_color_accents=preserve_color_accents),
                "detail": dict(max_colors=max(4, requested_colors), min_area=max(1, base_min // 2), noise_suppression=42, foreground_distance=18, weak_contrast=78, protect_background=True, object_mask_first=True, despeckle=False, despeckle_min_area=0, protect_thin_lines=True, close_lines=True, fill_small_holes=False, preserve_color_accents=preserve_color_accents),
                "color": dict(max_colors=max(4, requested_colors + 1), min_area=max(2, base_min), noise_suppression=55, foreground_distance=24, weak_contrast=45, protect_background=True, object_mask_first=False, despeckle=True, despeckle_min_area=max(base_min, 3), protect_thin_lines=True, close_lines=True, fill_small_holes=False, preserve_color_accents=preserve_color_accents),
                "bw": {},
            }
            candidates.append((preference if preference in lookup else "balanced", lookup.get(preference, dict(max_colors=max(3, requested_colors), min_area=base_min, noise_suppression=68, foreground_distance=28, weak_contrast=40, protect_background=True, object_mask_first=True, despeckle=True, despeckle_min_area=base_min, protect_thin_lines=True, close_lines=True, fill_small_holes=True, preserve_color_accents=preserve_color_accents))))

        results: list[PhotoScanCleanupResult] = []
        total = max(1, len(candidates))
        for index, (variant, params) in enumerate(candidates, start=1):
            check_cancel()
            start_progress = 8.0 + ((index - 1) / total) * 84.0
            span_progress = 84.0 / total

            def candidate_progress(inner_value: float, inner_key: str, *, _index: int = index, _variant: str = variant) -> None:
                value = start_progress + (max(0.0, min(100.0, float(inner_value))) / 100.0) * span_progress
                progress(value, f"progress.photo_scan_auto_candidate_step|{_index}|{total}|{_variant}|{inner_key}")

            progress(start_progress, f"progress.photo_scan_auto_candidate|{index}|{total}|{variant}")
            if variant == "bw":
                result = RecolorApp.build_photo_scan_black_white_image(
                    image,
                    min_area=max(1, base_min // 2),
                    noise_suppression=64,
                    foreground_distance=24,
                    weak_contrast=72,
                    protect_background=True,
                    protect_thin_lines=True,
                    close_lines=True,
                    fill_small_holes=False,
                    preserve_color_accents=preserve_color_accents,
                    max_work_edge=max_work_edge,
                    progress_callback=candidate_progress,
                    cancel_callback=cancel_callback,
                )
            else:
                result = RecolorApp.build_photo_scan_cleanup_image(
                    image,
                    **params,
                    max_work_edge=max_work_edge,
                    progress_callback=candidate_progress,
                    cancel_callback=cancel_callback,
                )
                result.variant = variant
            if variant != "bw":
                check_cancel()
                candidate_progress(94, "progress.photo_scan_cleanup")
                quiet_area = max(base_min, 6) if variant == "detail" else max(base_min * 2, 10)
                result = RecolorApp._quiet_photo_scan_color_speckles(
                    result,
                    min_area=quiet_area,
                    preserve_thin_lines=True,
                )
                check_cancel()
                solid_area = max(quiet_area * (2 if variant == "detail" else 3), 18)
                result = RecolorApp._solidify_photo_scan_technical_image(
                    result,
                    speckle_area=solid_area,
                    hole_area=max(solid_area * 5, 90),
                    preserve_thin_lines=True,
                )
            result.technical_score = RecolorApp._score_photo_scan_result(image, result, variant)
            results.append(result)

        if not results:
            return RecolorApp.build_photo_scan_cleanup_image(image, max_colors=max_colors, min_area=min_area, max_work_edge=max_work_edge)
        # Bei Badge-/Logo-Bildern mit kleinen Farbakzenten soll S/W nicht
        # wieder knapp vom Farbumfaerben verdraengt werden. Sonst werden rote
        # Sterne/gruene Schrift zwar erkannt, aber als normale Farbe/Schwarz
        # unbrauchbar dargestellt.
        color_best = max((r for r in results if r.variant != "bw"), key=lambda r: r.technical_score, default=None)
        bw_best = max((r for r in results if r.variant == "bw"), key=lambda r: r.technical_score, default=None)
        best = max(results, key=lambda r: r.technical_score)
        if (bw_likely or preserve_color_accents) and bw_best is not None and color_best is not None:
            bw_margin = 14.0 if preserve_color_accents else 5.0
            if bw_best.technical_score >= color_best.technical_score - bw_margin:
                best = bw_best
        elif best.variant == "bw" and color_best is not None and best.technical_score < color_best.technical_score + 7.5:
            best = color_best
        progress(100, "progress.render_preview")
        return best

    @staticmethod
    def build_photo_scan_cleanup_image(
        image: Image.Image,
        max_colors: int = 3,
        min_area: int = 10,
        noise_suppression: int = 70,
        foreground_distance: int = 30,
        weak_contrast: int = 0,
        protect_background: bool = False,
        object_mask_first: bool = False,
        despeckle: bool = False,
        despeckle_min_area: int = 0,
        protect_thin_lines: bool = True,
        close_lines: bool = True,
        fill_small_holes: bool = False,
        preserve_color_accents: bool = False,
        max_work_edge: int = 1500,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> PhotoScanCleanupResult:
        # Sicherheitsnetz gegen echte Endlosschleifen. Einzelne Schritte dürfen bei
        # großen Scans aber länger dauern, ohne fälschlich als Abbruch zu wirken.
        step_timeout_s = 60.0
        total_started = time.perf_counter()
        step_started = total_started
        current_step = "start"

        def progress(value: float, key: str) -> None:
            if progress_callback is not None:
                progress_callback(float(value), key)

        def check_cancel() -> None:
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("cancelled")

        def begin_step(value: float, key: str, debug_name: str) -> None:
            nonlocal step_started, current_step
            now = time.perf_counter()
            if current_step != "start":
                print(f"[Vektorrazor FotoScan] {current_step}: {now - step_started:.2f}s", flush=True)
            current_step = debug_name
            step_started = now
            progress(value, key)
            check_cancel()

        def check_step_timeout(detail: str = "") -> None:
            check_cancel()
            elapsed = time.perf_counter() - step_started
            if elapsed > step_timeout_s:
                suffix = f" ({detail})" if detail else ""
                raise TimeoutError(f"Foto-/Scan-Maskenschritt zu langsam: {current_step}{suffix}, {elapsed:.1f}s")

        def remove_isolated_pixels(mask: np.ndarray, min_neighbors: int) -> np.ndarray:
            if not np.any(mask):
                return mask
            kernel = np.ones((3, 3), dtype=np.uint8)
            neighbors = cv2.filter2D(mask.astype(np.uint8), -1, kernel, borderType=cv2.BORDER_CONSTANT)
            return mask & (neighbors >= max(1, min(9, int(min_neighbors))))

        def keep_components_by_stats(
            labels: np.ndarray,
            stats: np.ndarray,
            criteria: np.ndarray,
            label_count: int,
        ) -> np.ndarray:
            keep = np.zeros(label_count, dtype=bool)
            if label_count > 1:
                keep[1:] = criteria
            return keep[labels]

        def despeckle_color_mask(mask_u8: np.ndarray, min_island_area: int) -> tuple[np.ndarray, int, int]:
            if min_island_area <= 0 or not np.any(mask_u8 >= 128):
                return mask_u8, 0, 0
            mask = mask_u8 >= 128
            kernel = np.ones((3, 3), dtype=np.uint8)
            neighbors = cv2.filter2D(mask.astype(np.uint8), -1, kernel, borderType=cv2.BORDER_CONSTANT)
            neighbor_min = 2 if min_island_area < 40 else 3 if min_island_area < 140 else 4
            mask = mask & (neighbors >= neighbor_min)
            labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
            if labels_count <= 1:
                return np.zeros_like(mask_u8), 0, 0
            areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
            widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
            heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
            spans = np.maximum(widths, heights)
            mins = np.maximum(1, np.minimum(widths, heights))
            line_min_area = max(3, min_island_area // 3)
            line_min_span = max(8, min(h, w) // 180)
            line_like = protect_thin_lines & (areas >= line_min_area) & (spans >= line_min_span) & (
                (mins <= max(3, min(h, w) // 180))
                | ((spans / mins.astype(np.float32)) >= 2.4)
            )
            criteria = (areas >= min_island_area) | line_like
            cleaned = keep_components_by_stats(labels, stats, criteria, labels_count)
            removed_components = int((~criteria).sum())
            removed_pixels = int(mask.sum() - cleaned.sum())
            inverse = ~cleaned
            inv_count, inv_labels, inv_stats, _inv_centroids = cv2.connectedComponentsWithStats(inverse.astype(np.uint8), connectivity=8)
            if inv_count > 1:
                inv_areas = inv_stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                touches_border = np.zeros(inv_count, dtype=bool)
                touches_border[np.unique(inv_labels[0, :])] = True
                touches_border[np.unique(inv_labels[-1, :])] = True
                touches_border[np.unique(inv_labels[:, 0])] = True
                touches_border[np.unique(inv_labels[:, -1])] = True
                fill_criteria = (~touches_border[1:]) & (inv_areas <= max(1, min_island_area))
                fill_holes = keep_components_by_stats(inv_labels, inv_stats, fill_criteria, inv_count)
                cleaned = cleaned | fill_holes
                removed_pixels += int(fill_holes.sum())
            return (cleaned.astype(np.uint8) * 255), removed_components, removed_pixels

        original_size = image.size
        # Der farbige Foto-/Scan-Modus ist der teuerste Fall: mehrere Cluster,
        # Hysterese und Komponentenprüfung. Deshalb hier zusätzlich begrenzen,
        # auch wenn der Aufrufer versehentlich einen großen Wert übergibt.
        if int(max_colors) >= 4 or not bool(object_mask_first):
            max_work_edge = min(int(max_work_edge), 920)
        else:
            max_work_edge = min(int(max_work_edge), 1250)
        begin_step(8, "progress.prepare_image", "Bild vorbereiten")
        image, work_scale = RecolorApp._limited_work_image(image, max_edge=max_work_edge)
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3] > 0
        h, w = alpha.shape
        total_valid = int(alpha.sum())
        max_colors = max(1, min(8, int(max_colors)))
        min_area = max(1, int(min_area))
        noise_suppression = max(0, min(100, int(noise_suppression)))
        foreground_distance = max(5, min(80, int(foreground_distance)))
        weak_contrast = max(0, min(100, int(weak_contrast)))
        weak_factor = weak_contrast / 100.0
        despeckle_min_area = max(0, min(500, int(despeckle_min_area)))
        if despeckle and despeckle_min_area <= 0:
            base = (max(1.0, float(min(h, w))) / 650.0) ** 2
            despeckle_min_area = max(1, min(80, int(round(base * (2.5 + (noise_suppression / 100.0) * 4.5)))))
        print(
            "[Vektorrazor FotoScan] "
            f"Original={original_size[0]}x{original_size[1]}, Arbeit={w}x{h}, "
            f"Scale={work_scale:.3f}, Ziel-Farben={max_colors}, "
            f"Entpunkten={despeckle}, Mindestinsel={despeckle_min_area}",
            flush=True,
        )
        analysis = RecolorApp.analyze_photo_scan_logo_problem(image)
        if total_valid <= 0:
            out = np.zeros((h, w, 4), dtype=np.uint8)
            result_image = Image.fromarray(out, "RGBA")
            if result_image.size != original_size:
                result_image = result_image.resize(original_size, Image.Resampling.NEAREST)
            return PhotoScanCleanupResult(result_image, [], analysis)

        rgb_float = rgb.astype(np.float32)
        begin_step(18, "progress.photo_scan_background", "Hintergrundmaske")
        gray = (0.299 * rgb_float[:, :, 0] + 0.587 * rgb_float[:, :, 1] + 0.114 * rgb_float[:, :, 2]).astype(np.uint8)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1].astype(np.float32) / 255.0
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)

        valid_gray = gray[alpha]
        p50 = float(np.percentile(valid_gray, 50))
        p80 = float(np.percentile(valid_gray, 80))
        p92 = float(np.percentile(valid_gray, 92))
        bright_bg = alpha & (gray >= max(165, int(p80 - 4)))
        if int(bright_bg.sum()) < max(64, total_valid * 0.04):
            bright_bg = alpha & (gray >= int(p50))
        bg_rgb = np.median(rgb_float[bright_bg], axis=0) if np.any(bright_bg) else np.median(rgb_float[alpha], axis=0)
        bg_lab = cv2.cvtColor(np.uint8([[bg_rgb]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]

        lab_distance = np.linalg.norm(lab - bg_lab.reshape(1, 1, 3), axis=2)
        luma_distance = np.abs(gray.astype(np.float32) - p92)
        noise_factor = noise_suppression / 100.0
        bg_gray = cv2.GaussianBlur(gray, (0, 0), max(1.0, min(h, w) * 0.010))
        local_dark = bg_gray.astype(np.float32) - gray.astype(np.float32)
        lab_blur = cv2.GaussianBlur(lab, (0, 0), 1.2)
        local_lab_change = np.linalg.norm(lab - lab_blur, axis=2)
        lab_threshold = max(4.0, float(foreground_distance) * (0.75 + noise_factor * 0.35))
        background_locked = np.zeros_like(alpha, dtype=bool)
        if protect_background:
            border = np.zeros_like(alpha, dtype=bool)
            border_px = max(3, min(h, w) // 40)
            border[:border_px, :] = True
            border[-border_px:, :] = True
            border[:, :border_px] = True
            border[:, -border_px:] = True
            border_bg = alpha & border & (gray >= max(150, int(p80 - 8))) & (sat <= 0.30)
            if int(border_bg.sum()) < max(64, total_valid * 0.01):
                border_bg = bright_bg
            edge_bg_rgb = np.median(rgb_float[border_bg], axis=0) if np.any(border_bg) else bg_rgb
            edge_bg_lab = cv2.cvtColor(np.uint8([[edge_bg_rgb]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
            edge_lab_distance = np.linalg.norm(lab - edge_bg_lab.reshape(1, 1, 3), axis=2)
            background_locked = (
                alpha
                & (edge_lab_distance < max(3.0, lab_threshold * 0.78))
                & (gray >= max(135, int(p50 - 4)))
                & (sat <= 0.42)
                & (local_lab_change < 4.2)
            )
        check_step_timeout("Hintergrund")

        begin_step(30, "progress.photo_scan_main_masks", "Hauptmasken")
        main_mask = alpha & (
            (lab_distance >= lab_threshold)
            | (sat >= (0.10 + noise_factor * 0.04))
            | (gray.astype(np.float32) <= min(p50 - 8.0, p92 - 38.0))
            | (luma_distance >= (22.0 + noise_factor * 10.0))
        )
        main_mask &= ~background_locked
        main_mask = remove_isolated_pixels(main_mask, 2 if protect_thin_lines else 3)
        object_candidate = alpha & ~background_locked
        if object_mask_first:
            edges = cv2.Canny(gray, 45, 135) > 0
            edge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges.astype(np.uint8), edge_kernel, iterations=1) >= 128
            secure_object = main_mask
            soft_object = object_candidate & (
                secure_object
                | edges
                | (local_lab_change >= 2.4)
                | (local_dark >= max(3.0, 8.0 - weak_factor * 4.0))
            )
            soft_object = remove_isolated_pixels(soft_object, 2 if protect_thin_lines else 3)
            labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(soft_object.astype(np.uint8), connectivity=8)
            if labels_count > 1:
                touches_secure = np.bincount(
                    labels.ravel(),
                    weights=secure_object.ravel().astype(np.uint8),
                    minlength=labels_count,
                ) > 0
                areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                spans = np.maximum(widths, heights)
                mins = np.maximum(1, np.minimum(widths, heights))
                line_like = (spans >= max(6, min(h, w) // 220)) & (
                    (mins <= max(5, min(h, w) // 100))
                    | ((spans / mins.astype(np.float32)) >= 2.0)
                )
                small_detail = (weak_contrast > 0) & (areas <= max(min_area * 8, int(round(total_valid * 0.004)))) & line_like
                criteria = touches_secure[1:] | small_detail | (areas >= max(min_area * 4, int(round(total_valid * 0.006))))
                object_candidate = keep_components_by_stats(labels, stats, criteria, labels_count)
            else:
                object_candidate = secure_object
            object_candidate |= main_mask
            print(
                "[Vektorrazor FotoScan] "
                f"Objektmaske Komponenten={labels_count - 1}, Pixel={int(object_candidate.sum())}",
                flush=True,
            )
            check_step_timeout("Objektmaske")
        print(
            "[Vektorrazor FotoScan] "
            f"Hintergrundschutz={protect_background}, Hintergrund gesperrt={int(background_locked.sum())}, "
            f"Objektmaske={object_mask_first}, Hauptmaske={int(main_mask.sum())}",
            flush=True,
        )
        check_step_timeout("Hauptmaske")

        begin_step(42, "progress.photo_scan_detail_masks", "Detailmasken")
        weak_line_mask = np.zeros_like(main_mask, dtype=bool)
        if weak_contrast > 0:
            weak_lab_threshold = max(2.5, lab_threshold * (0.72 - weak_factor * 0.36))
            weak_luma_threshold = max(3.0, (18.0 + noise_factor * 6.0) * (1.0 - weak_factor * 0.70))
            weak_sat_threshold = max(0.018, (0.075 + noise_factor * 0.018) * (1.0 - weak_factor * 0.60))
            weak_candidate = object_candidate & ~main_mask & (
                ((lab_distance >= weak_lab_threshold) & ((sat >= weak_sat_threshold) | (local_lab_change >= 1.6 + weak_factor * 2.2)))
                | (local_dark >= weak_luma_threshold)
            )
            weak_candidate &= ~background_locked
            weak_candidate = remove_isolated_pixels(weak_candidate, 2 if protect_thin_lines else 3)
            weak_kernel_size = 3 if weak_contrast < 55 else 5
            weak_kernel_size = max(3, min(5, int(weak_kernel_size)))
            weak_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (weak_kernel_size, weak_kernel_size))
            weak_candidate = cv2.morphologyEx((weak_candidate.astype(np.uint8) * 255), cv2.MORPH_CLOSE, weak_kernel, iterations=1) >= 128
            weak_candidate &= ~background_locked
            check_step_timeout("Detailkandidaten")
            labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(weak_candidate.astype(np.uint8), connectivity=8)
            min_span = max(6, int(round(min(h, w) * 0.010)))
            max_width_for_line = max(4, int(round(min(h, w) * (0.010 + weak_factor * 0.010))))
            max_line_area = max(min_area * 12, int(round(total_valid * (0.003 + weak_factor * 0.010))))
            if labels_count > 1:
                areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                spans = np.maximum(widths, heights)
                mins = np.maximum(1, np.minimum(widths, heights))
                narrow = mins <= max_width_for_line
                elongated = (spans >= min_span) & ((spans / mins.astype(np.float32)) >= (2.2 if protect_thin_lines else 3.2))
                ring_like = (spans >= min_span) & (areas <= max_line_area) & (areas <= (widths * heights) * (0.42 + weak_factor * 0.18))
                criteria = (
                    (protect_thin_lines and (areas >= max(1, min_area // 10)) & (narrow | elongated | ring_like))
                    | ((areas >= max(1, min_area // 4)) & elongated & (areas <= max_line_area))
                )
                weak_line_mask = keep_components_by_stats(labels, stats, criteria, labels_count)
            print(
                "[Vektorrazor FotoScan] "
                f"Detailmaske Komponenten={labels_count - 1}, Kernel={weak_kernel_size}x{weak_kernel_size}, "
                f"behalten={int(weak_line_mask.sum())}",
                flush=True,
            )
            check_step_timeout("Detailkomponenten")

        foreground = (main_mask | weak_line_mask) & object_candidate

        begin_step(52, "progress.photo_scan_cleanup", "Vorreinigung")
        fg_img = cv2.medianBlur((foreground.astype(np.uint8) * 255), 3)
        foreground = fg_img >= 128
        if noise_suppression >= 35:
            labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(foreground.astype(np.uint8), connectivity=8)
            thin_line_min = max(2, int(round(min(h, w) * 0.006)))
            if labels_count > 1:
                areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                spans = np.maximum(widths, heights)
                mins = np.minimum(widths, heights)
                long_thin = protect_thin_lines & (spans >= thin_line_min) & (mins <= max(4, int(round(min(h, w) * 0.010))))
                weak_keep = (weak_contrast > 0) & (spans >= max(4, thin_line_min // 2)) & (areas >= max(1, min_area // 6))
                criteria = (areas >= min_area) | ((areas >= max(2, min_area // 3)) & (spans >= thin_line_min)) | long_thin | weak_keep
                foreground = keep_components_by_stats(labels, stats, criteria, labels_count)
            else:
                foreground = np.zeros_like(foreground)
            print(
                "[Vektorrazor FotoScan] "
                f"Vorreinigung Komponenten={labels_count - 1}, Vordergrund={int(foreground.sum())}",
                flush=True,
            )
            check_step_timeout("Vorreinigung")

        if np.any(weak_line_mask):
            weak_dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            weak_line_mask = cv2.dilate(weak_line_mask.astype(np.uint8), weak_dilate_kernel, iterations=1) >= 128
            foreground = foreground | weak_line_mask

        pixels_lab = lab[foreground]
        if pixels_lab.shape[0] <= 0:
            out = np.zeros((h, w, 4), dtype=np.uint8)
            out[:, :, 0:3] = 255
            out[:, :, 3] = rgba[:, :, 3]
            result_image = Image.fromarray(out, "RGBA")
            if result_image.size != original_size:
                result_image = result_image.resize(original_size, Image.Resampling.NEAREST)
            return PhotoScanCleanupResult(result_image, [], analysis)

        begin_step(62, "progress.photo_scan_cluster", "Farben clustern")
        sample = pixels_lab
        sample_limit = 28_000 if max_colors >= 4 else 42_000
        if sample.shape[0] > sample_limit:
            step = int(math.ceil(sample.shape[0] / float(sample_limit)))
            sample = sample[::step]
        cluster_count = max(1, min(max_colors, int(sample.shape[0])))
        _compactness, _labels_sample, centers = cv2.kmeans(
            sample.astype(np.float32),
            cluster_count,
            None,
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 16, 1.2),
            1,
            cv2.KMEANS_PP_CENTERS,
        )
        centers = centers.astype(np.float32)
        all_dist = np.linalg.norm(lab[:, :, None, :] - centers.reshape(1, 1, cluster_count, 3), axis=3)
        assigned_cluster = np.argmin(all_dist, axis=2)
        print(
            "[Vektorrazor FotoScan] "
            f"Cluster={cluster_count}, Sample={sample.shape[0]}, Distanzmatrix={all_dist.shape}",
            flush=True,
        )
        check_step_timeout("Cluster")

        masks: list[tuple[int, np.ndarray, RGB]] = []
        begin_step(72, "progress.photo_scan_hysteresis", "Hysterese")
        line_close_radius = 1 if weak_contrast < 60 else 2
        line_close_radius = max(1, min(3, int(line_close_radius)))
        line_close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (line_close_radius * 2 + 1, line_close_radius * 2 + 1))
        hole_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        print(
            "[Vektorrazor FotoScan] "
            f"Kernel Linien={line_close_kernel.shape[1]}x{line_close_kernel.shape[0]}, "
            f"Loecher={hole_kernel.shape[1]}x{hole_kernel.shape[0]}",
            flush=True,
        )
        for cluster_index in range(cluster_count):
            progress(72.0 + (float(cluster_index) / max(1.0, float(cluster_count))) * 16.0, "progress.photo_scan_hysteresis")
            check_step_timeout(f"Cluster {cluster_index + 1}/{cluster_count}")
            dist_to_center = all_dist[:, :, cluster_index]
            secure_distance = float(np.percentile(dist_to_center[foreground & (assigned_cluster == cluster_index)], 68)) if np.any(foreground & (assigned_cluster == cluster_index)) else 0.0
            secure_limit = max(4.0, secure_distance)
            weak_limit = secure_limit * (1.45 + weak_factor * 0.85)
            secure_mask = foreground & (assigned_cluster == cluster_index) & (dist_to_center <= secure_limit)
            candidate_mask = foreground & object_candidate & (dist_to_center <= weak_limit)
            candidate_mask &= ~background_locked
            candidate_mask = remove_isolated_pixels(candidate_mask, 2 if protect_thin_lines else 3)
            if not np.any(secure_mask):
                continue
            labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(candidate_mask.astype(np.uint8), connectivity=8)
            if labels_count <= 1:
                continue
            touches_secure = np.bincount(
                labels.ravel(),
                weights=secure_mask.ravel().astype(np.uint8),
                minlength=labels_count,
            ) > 0
            areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
            widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
            heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
            spans = np.maximum(widths, heights)
            mins = np.maximum(1, np.minimum(widths, heights))
            compact_large = (areas >= max(min_area * 8, int(round(total_valid * 0.010)))) & (areas > (widths * heights) * 0.55)
            line_like = (spans >= max(8, min(h, w) // 180)) & (
                (mins <= max(6, min(h, w) // 90))
                | ((spans / mins.astype(np.float32)) >= 2.0)
            )
            criteria = touches_secure[1:] & (
                compact_large | line_like | (areas <= max(min_area * 6, int(round(total_valid * 0.004))))
            )
            mask = secure_mask | keep_components_by_stats(labels, stats, criteria, labels_count)
            progress(72.0 + (float(cluster_index + 1) / max(1.0, float(cluster_count))) * 16.0, "progress.photo_scan_hysteresis")
            print(
                "[Vektorrazor FotoScan] "
                f"Maske {cluster_index + 1}/{cluster_count}: Komponenten={labels_count - 1}, "
                f"beruehren_sicher={int(touches_secure.sum()) - int(touches_secure[0])}, "
                f"Pixel={int(mask.sum())}",
                flush=True,
            )

            mask_u8 = mask.astype(np.uint8) * 255
            if despeckle and despeckle_min_area > 0:
                mask_u8, removed_components, removed_pixels = despeckle_color_mask(mask_u8, despeckle_min_area)
                print(
                    "[Vektorrazor FotoScan] "
                    f"Entpunkten Maske {cluster_index + 1}/{cluster_count}: "
                    f"entfernte Komponenten={removed_components}, korrigierte Pixel={removed_pixels}",
                    flush=True,
                )
            if close_lines:
                line_candidates = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, line_close_kernel, iterations=1)
                add = (line_candidates >= 128) & ~(mask_u8 >= 128)
                if np.any(add):
                    labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(add.astype(np.uint8), connectivity=8)
                    if labels_count > 1:
                        areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                        widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                        heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                        criteria = (areas <= max(24, min_area * 2)) | (np.minimum(widths, heights) <= max(4, line_close_radius * 3))
                        safe_add = keep_components_by_stats(labels, stats, criteria, labels_count)
                    else:
                        safe_add = np.zeros_like(add)
                    mask_u8[safe_add] = 255
            if fill_small_holes:
                filled = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, hole_kernel, iterations=1)
                holes = (filled >= 128) & ~(mask_u8 >= 128)
                if np.any(holes):
                    labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(holes.astype(np.uint8), connectivity=8)
                    if labels_count > 1:
                        areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                        widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                        heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                        criteria = (areas <= max(16, min_area * 3)) & (np.maximum(widths, heights) <= max(10, min(h, w) // 80))
                        safe_holes = keep_components_by_stats(labels, stats, criteria, labels_count)
                    else:
                        safe_holes = np.zeros_like(holes)
                    mask_u8[safe_holes] = 255
            if noise_suppression >= 55 and not protect_thin_lines:
                open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, open_kernel, iterations=1)
            labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats((mask_u8 >= 128).astype(np.uint8), connectivity=8)
            if labels_count > 1:
                areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
                widths = stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
                heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64)
                spans = np.maximum(widths, heights)
                mins = np.minimum(widths, heights)
                long_thin = protect_thin_lines & (spans >= max(8, min(h, w) // 160)) & (mins <= max(5, min(h, w) // 90))
                weak_keep = (weak_contrast > 0) & (spans >= max(6, min(h, w) // 220)) & (areas >= max(1, min_area // 8))
                criteria = (areas >= min_area) | ((areas >= max(2, min_area // 3)) & (spans >= max(8, min(h, w) // 120))) | long_thin | weak_keep
                clean = keep_components_by_stats(labels, stats, criteria, labels_count)
            else:
                clean = np.zeros_like(mask, dtype=bool)
            area = int(clean.sum())
            if area < min_area and not (protect_thin_lines and area >= max(1, min_area // 8)):
                continue
            median_rgb = tuple(int(max(0, min(255, round(v)))) for v in np.median(rgb_float[clean], axis=0))
            masks.append((area, clean, median_rgb))

        masks.sort(key=lambda item: item[0], reverse=True)
        begin_step(88, "progress.render_preview", "Vorschau")
        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[:, :, 0:3] = 255
        out[:, :, 3] = rgba[:, :, 3]
        detected: list[DetectedColor] = []
        occupied = np.zeros((h, w), dtype=bool)
        for index, (area, mask, source_rgb) in enumerate(masks[:max_colors]):
            draw_mask = mask & ~occupied
            area = int(draw_mask.sum())
            if area <= 0:
                continue
            palette_name, target_rgb = CONTRAST_PALETTE[index % len(CONTRAST_PALETTE)]
            out[draw_mask, 0:3] = np.array(target_rgb, dtype=np.uint8)
            occupied[draw_mask] = True
            detected.append(
                DetectedColor(
                    source_rgb=source_rgb,
                    target_rgb=target_rgb,
                    pixels=area,
                    percent=(area / max(1, total_valid)) * 100.0,
                    palette_name=palette_name,
                )
            )

        result_image = Image.fromarray(out, "RGBA")
        result = PhotoScanCleanupResult(result_image, detected, analysis)

        # Wichtig: Diese flächige Nachbereinigung zuerst auf der begrenzten
        # Arbeitsgröße ausführen. Auf dem Originalscan kann sie bei großen Bildern
        # sonst bei „Vorschau wird erstellt“ scheinbar hängen bleiben.
        if despeckle or fill_small_holes or noise_suppression >= 70:
            progress(92, "progress.photo_scan_cleanup")
            solid_area = max(
                int(min_area) * (2 if protect_thin_lines else 3),
                int(despeckle_min_area) if despeckle else 0,
                14,
            )
            result = RecolorApp._solidify_photo_scan_technical_image(
                result,
                speckle_area=solid_area,
                hole_area=max(solid_area * 5, int(min_area) * 8, 80),
                preserve_thin_lines=protect_thin_lines,
            )

        if result.image.size != original_size:
            result.image = result.image.resize(original_size, Image.Resampling.NEAREST)
            if work_scale > 0:
                inv_area = 1.0 / max(1e-9, work_scale * work_scale)
                estimated_total_valid = max(1, int(round(float(total_valid) * inv_area)))
                for item in result.detected:
                    item.pixels = int(round(float(item.pixels) * inv_area))
                    item.percent = (item.pixels / estimated_total_valid) * 100.0
        progress(100, "progress.render_preview")
        print(f"[Vektorrazor FotoScan] Gesamt: {time.perf_counter() - total_started:.2f}s", flush=True)
        return result

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
        preserve_color_accents: bool = False,
        accent: RGB = (128, 64, 0),
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

        if preserve_color_accents:
            valid = alpha > 0
            rgb_norm = np.clip(rgb / 255.0, 0.0, 1.0)
            sat = np.max(rgb_norm, axis=2) - np.min(rgb_norm, axis=2)
            bg_candidates = valid & (gray >= np.percentile(gray[valid], 55) if np.any(valid) else True)
            if np.any(bg_candidates):
                bg_rgb = np.median(rgb[bg_candidates], axis=0)
            else:
                bg_rgb = np.array(background, dtype=np.float32)
            color_distance = np.linalg.norm(rgb - bg_rgb.reshape(1, 1, 3), axis=2)
            raw_accent_mask = (
                valid
                & (sat >= 0.075)
                & (color_distance >= 22.0)
                & (gray <= min(245, int(np.percentile(gray[valid], 96)) if np.any(valid) else 245))
            )
            keep = RecolorApp._component_filtered_color_accent_mask(
                raw_accent_mask,
                int(np.count_nonzero(valid)),
                w,
                h,
                min_area_ratio=0.000006,
                max_area_ratio=0.025,
                max_span_ratio=0.18,
            )
            if np.any(keep):
                out = RecolorApp._apply_local_opposite_to_accent_mask(out, keep, valid)
        return Image.fromarray(out, "RGBA")

    @staticmethod
    def build_logo_direct_black_image(
        image: Image.Image,
        threshold: int,
        foreground: RGB,
        background: RGB,
        clean: bool = False,
        preserve_color_accents: bool = False,
        accent: RGB = (128, 64, 0),
    ) -> Image.Image:
        """Setzt eine dominante Motivfarbe technisch auf Schwarz um.

        Dieser Weg ist für saubere Logos mit einer klaren dunklen Motivfarbe
        gedacht, bei denen die lokale Logo-Maske unnötig aggressiv wäre.
        Im Unterschied zur Logo-Maske wird hier keine lokale Hintergrundschätzung
        mit großem Blur benutzt, sondern ein direkter Farb-/Helligkeitsabstand
        zum geschätzten Hintergrund ausgewertet. So bleiben feine Innenlinien
        oft besser erhalten.
        """
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        rgb = rgba[:, :, :3].astype(np.float32)
        alpha = rgba[:, :, 3] > 0
        if not np.any(alpha):
            return image.convert("RGBA")

        h, w = alpha.shape
        gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

        border = max(1, int(round(min(h, w) * 0.03)))
        border_mask = np.zeros((h, w), dtype=bool)
        border_mask[:border, :] = True
        border_mask[-border:, :] = True
        border_mask[:, :border] = True
        border_mask[:, -border:] = True
        bg_candidates = border_mask & alpha
        if int(np.count_nonzero(bg_candidates)) < max(20, (h * w) // 200):
            bright = gray >= np.percentile(gray[alpha], 65)
            bg_candidates = alpha & bright
        if not np.any(bg_candidates):
            bg_candidates = alpha

        bg_rgb = np.median(rgb[bg_candidates], axis=0)
        bg_gray = float(0.299 * bg_rgb[0] + 0.587 * bg_rgb[1] + 0.114 * bg_rgb[2])
        color_distance = np.linalg.norm(rgb - bg_rgb.reshape(1, 1, 3), axis=2)
        darker = np.maximum(0.0, bg_gray - gray)

        sensitivity = max(1, min(100, int(threshold)))
        tone_threshold = float(np.interp(sensitivity, [1, 100], [5.0, 42.0]))
        color_threshold = float(np.interp(sensitivity, [1, 100], [10.0, 62.0]))

        mask = alpha & (
            ((darker >= tone_threshold) & (color_distance >= color_threshold * 0.55))
            | (darker >= tone_threshold * 1.55)
            | (color_distance >= color_threshold * 1.20)
        )

        if clean:
            mask_img = Image.fromarray((mask.astype(np.uint8) * 255), "L")
            mask_img = mask_img.filter(ImageFilter.MedianFilter(size=3))
            mask = np.array(mask_img, dtype=np.uint8) >= 128

        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[:, :, 0:3] = np.array(background, dtype=np.uint8)
        out[:, :, 3] = 255
        out[mask, 0:3] = np.array(foreground, dtype=np.uint8)

        if preserve_color_accents:
            valid = alpha > 0
            rgb_norm = np.clip(rgb / 255.0, 0.0, 1.0)
            sat = np.max(rgb_norm, axis=2) - np.min(rgb_norm, axis=2)
            color_distance_full = np.linalg.norm(rgb - bg_rgb.reshape(1, 1, 3), axis=2)
            raw_accent_mask = (
                valid
                & (sat >= 0.075)
                & (color_distance_full >= 22.0)
                & (gray <= min(245, int(np.percentile(gray[valid], 96)) if np.any(valid) else 245))
            )
            keep = RecolorApp._component_filtered_color_accent_mask(
                raw_accent_mask,
                int(np.count_nonzero(valid)),
                w,
                h,
                min_area_ratio=0.000006,
                max_area_ratio=0.025,
                max_span_ratio=0.18,
            )
            if np.any(keep):
                out = RecolorApp._apply_local_opposite_to_accent_mask(out, keep, valid)
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

        active_mappings = [mapping for mapping in mappings if getattr(mapping, "enabled", True)]
        if not active_mappings:
            return Image.fromarray(result, "RGBA")

        best_distance = np.full(base_rgb.shape[:2], np.inf, dtype=np.float32)
        best_target = np.zeros_like(result[:, :, 0:3])
        assigned = np.zeros(base_rgb.shape[:2], dtype=bool)
        assigned_labels = np.full(base_rgb.shape[:2], -1, dtype=np.int16)
        label_targets = [np.array(mapping.target_rgb, dtype=np.uint8) for mapping in active_mappings]

        for label_index, mapping in enumerate(active_mappings):
            src = np.array(mapping.source_rgb, dtype=np.int16)
            diff = np.abs(base_rgb - src)
            tol = max(0, min(255, int(mapping.tolerance)))
            mask = (diff[:, :, 0] <= tol) & (diff[:, :, 1] <= tol) & (diff[:, :, 2] <= tol)
            if not np.any(mask):
                continue
            distance = np.sqrt(np.sum(diff.astype(np.float32) * diff.astype(np.float32), axis=2))
            update = mask & (distance < best_distance)
            if not np.any(update):
                continue
            best_distance[update] = distance[update]
            target = label_targets[label_index]
            best_target[update] = target
            assigned_labels[update] = label_index
            assigned[update] = True

        result[assigned, 0:3] = best_target[assigned]

        max_fill_noise = max(0, min(100, max(int(getattr(mapping, "fill_noise", 0) or 0) for mapping in active_mappings)))
        fill_solid = any(bool(getattr(mapping, "fill_solid", False)) for mapping in active_mappings)
        if max_fill_noise > 0 and np.any(assigned):
            if fill_solid:
                radius = 2 if max_fill_noise < 45 else 4 if max_fill_noise < 75 else 6
            else:
                radius = 1 if max_fill_noise < 45 else 2 if max_fill_noise < 75 else 3
            filter_size = radius * 2 + 1
            fill_mask_total = np.zeros_like(assigned)
            for label_index, target in enumerate(label_targets):
                label_mask = assigned_labels == label_index
                if not np.any(label_mask):
                    continue
                mask_img = Image.fromarray((label_mask.astype(np.uint8) * 255), "L")
                closed = mask_img.filter(ImageFilter.MaxFilter(size=filter_size)).filter(ImageFilter.MinFilter(size=filter_size))
                fill_candidates = (np.array(closed, dtype=np.uint8) >= 128) & ~label_mask
                if fill_solid:
                    fill_mask = fill_candidates & ~fill_mask_total
                else:
                    fill_mask = fill_candidates & ~assigned & ~fill_mask_total
                if not np.any(fill_mask):
                    continue
                result[fill_mask, 0:3] = target
                assigned_labels[fill_mask] = label_index
                assigned[fill_mask] = True
                fill_mask_total[fill_mask] = True
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
