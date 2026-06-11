# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""
Workflow-App für PNG-Aufbereitung und Vektorisierung.

Diese Datei bildet die zentrale Schaltstelle des Programms. Hier werden
Benutzeroberfläche, Schrittlogik, automatische Empfehlungen, Bildvorschau,
Zwischenergebnisse und der Übergang zur eigentlichen Vektorisierung
koordiniert.

Hauptaufgaben dieser Datei:
- Aufbau und Verwaltung der zweistufigen Workflow-Oberfläche
- Laden, Zurücksetzen und Vorbereiten von Eingabebildern
- automatische Modus-Empfehlung für Schritt 1
- Steuerung der Spezialmodi wie Logo-Maske und Foto-Scan
- Übergabe des technisch bereinigten Bildes an Schritt 2
- Verwaltung von Statusmeldungen, Busy-Dialogen und Fortschritt

Datei-Struktur:
- main.py               -> Programmeinstieg
- workflow_app.py       -> zentrale Ablaufsteuerung
- recolor_engine.py     -> Bildvorbereitung, Umfärbung, technische S/W-Erzeugung
- vector_engine.py      -> Konturerkennung, Reduktion, SVG/DXF/STL-nahe Ausgaben
- ui_step1.py           -> UI-Bausteine für Schritt 1
- ui_step2.py           -> UI-Bausteine für Schritt 2
- dialogs_scale_export.py -> ausgelagerte Dialoge für Export und Skalierung
- i18n.py               -> Sprachumschaltung und Textauflösung

Wichtige Grundidee:
Schritt 1 soll aus einem oft ungeeigneten PNG eine technisch saubere Grundlage
machen. Erst danach soll Schritt 2 die Konturen vektorisieren. Dadurch bleiben
beide Aufgaben klar getrennt: zuerst Bildbereinigung, danach Geometrie.
"""

from __future__ import annotations


from pathlib import Path
from typing import Optional, Tuple, List, Any
import sys
import math
import json
import threading
import queue
import time

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFilter

import ai_upscale
import recolor_engine as recolor
import vector_engine as vector
import dialogs_scale_export
import ui_step1
import ui_step2
import i18n
from i18n import tr


def resource_path(relative_path: str) -> Path:
    """Pfad funktioniert im Quellordner und in einer PyInstaller-Onefile-EXE."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path


RGB = Tuple[int, int, int]

ACTION_GREEN = "#15803d"
ACTION_GREEN_ACTIVE = "#166534"
ACTION_YELLOW = "#ca8a04"
ACTION_YELLOW_ACTIVE = "#a16207"


class HoverTooltip:
    def __init__(self, widget: tk.Widget, text_key: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text_key = text_key
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        self._hide()
        text = tr(self.text_key, default="")
        if not text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tip,
            text=text,
            justify="left",
            bg="#111827",
            fg="#f9fafb",
            relief="solid",
            bd=1,
            padx=8,
            pady=5,
            wraplength=360,
            font=("Segoe UI", 9),
        )
        label.pack()
        self._tip = tip

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


DXF_COMPATIBILITY_PRESETS = {
    "default": (
        "R2000",
        "Empfohlen für Grafikprogramme: robust, alt genug und für viele Importfilter gut lesbar."
    ),
    "illustrator": (
        "R2007",
        "Illustrator-kompatibler Modus bis AutoCAD 2007. Falls Import scheitert: R2000 wählen."
    ),
    "coreldraw": (
        "R2000",
        "Robuster CorelDRAW-Modus. Corel kann zwar neuere AutoCAD-Versionen, R2000 ist oft stabiler."
    ),
    "coreldraw_modern": (
        "R2007",
        "Für neuere CorelDRAW-Versionen. Bei Importproblemen zurück auf R2000."
    ),
    "autocad": (
        "R2010",
        "Für moderne CAD-Programme. Nicht ideal für Illustrator."
    ),
    "freecad": (
        "R2000",
        "Allgemeiner Austauschmodus für freie CAD/CAM-Programme."
    ),
    "manual": (
        "R2000",
        "DXF-Format rechts selbst wählen."
    ),
}

DXF_COMPATIBILITY_KEYS = list(DXF_COMPATIBILITY_PRESETS.keys())
VECTOR_MODE_KEYS = ["area", "centerline"]
PREVIEW_MODE_KEYS = ["object", "contour", "mask", "cut_risk"]
CLEANUP_MODE_KEYS = ["off", "mm2", "percent"]
INTERNAL_SCALE_KEYS = ["1", "2", "3"]
UI_THEME_KEYS = ["classic", "modern"]
UI_COMPLEXITY_KEYS = ["simple", "expert"]
STARTUP_PRESET_KEYS = ["logo", "organic", "mixed"]
MOTIF_PROFILE_KEYS = STARTUP_PRESET_KEYS


DXF_VERSION_CHOICES = {
    "R2000": "R2000  –  Illustrator/CorelDRAW/LibreCAD/CAM  (empfohlen)",
    "R2004": "R2004  –  ältere AutoCAD/CAD-Systeme",
    "R2007": "R2007  –  Illustrator bis AutoCAD 2007 / CorelDRAW modern",
    "R2010": "R2010  –  AutoCAD/CAD modern  (nicht ideal für Illustrator)",
    "R2013": "R2013  –  neue CAD-Systeme",
    "R2018": "R2018  –  sehr neue CAD-Systeme",
}


def _dxf_choice_for_version(version: str) -> str:
    return DXF_VERSION_CHOICES.get(version, DXF_VERSION_CHOICES["R2000"])


def _dxf_version_from_choice(choice: str) -> str:
    first = (choice or "R2000").strip().split()[0]
    return first if first in DXF_VERSION_CHOICES else "R2000"


def _rgb_to_text(rgb: RGB) -> str:
    return f"{int(rgb[0])},{int(rgb[1])},{int(rgb[2])}"


def _rgb_to_hex(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def _parse_rgb_any(text: str) -> RGB:
    return recolor.parse_rgb(text)


def _flatten_rgba_to_rgb(image: Image.Image, background: RGB = (255, 255, 255)) -> Image.Image:
    rgba = image.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (*background, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def _known_color_name(rgb: RGB) -> str:
    names = {
        (0, 0, 0): "Schwarz",
        (255, 255, 255): "Weiß",
        (0, 0, 255): "Blau",
        (255, 0, 0): "Rot",
        (0, 255, 0): "Grün",
        (255, 0, 255): "Magenta",
        (0, 255, 255): "Cyan",
        (255, 255, 0): "Gelb",
        (255, 128, 0): "Orange",
        (128, 0, 255): "Violett",
        (128, 128, 128): "Grau",
    }
    return names.get(tuple(rgb), f"RGB_{rgb[0]}_{rgb[1]}_{rgb[2]}")


def _row_action_button(parent: tk.Widget, text: str, command, *, bg: str, activebackground: str) -> tk.Button:
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg="white",
        activebackground=activebackground,
        activeforeground="white",
        relief="raised",
        bd=1,
        width=7,
        padx=4,
        pady=2,
        font=("Segoe UI", 8, "bold"),
        cursor="hand2",
    )


class BasicWorkflowRow:
    def __init__(self, app: "WorkflowApp", parent: tk.Widget, index: int, detected: Any) -> None:
        self.app = app
        self.index = index
        self.detected = detected
        self.enabled_var = tk.BooleanVar(value=True)
        self.target_var = tk.StringVar(value=_rgb_to_text(detected.target_rgb))

        self.frame = ttk.Frame(parent)
        self.frame.grid(row=index, column=0, sticky="ew", padx=2, pady=1)
        self.frame.columnconfigure(8, weight=1)

        ttk.Label(self.frame, text=f"#{index + 1}", width=4).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(self.frame, variable=self.enabled_var, command=self.app.schedule_step1_preview).grid(row=0, column=1, padx=(0, 4))
        tk.Label(self.frame, width=3, relief="solid", bd=1, bg=_rgb_to_hex(detected.source_rgb)).grid(row=0, column=2, padx=(0, 4))
        ttk.Label(self.frame, text=_rgb_to_text(detected.source_rgb), width=12).grid(row=0, column=3, sticky="w")
        ttk.Label(self.frame, text=f"{detected.percent:.2f}%", width=8).grid(row=0, column=4, sticky="e", padx=(4, 4))
        ttk.Label(self.frame, text="→").grid(row=0, column=5, padx=2)
        self.target_entry = ttk.Entry(self.frame, textvariable=self.target_var, width=13)
        self.target_entry.grid(row=0, column=6, sticky="w")
        self.target_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.target_swatch.grid(row=0, column=7, padx=(4, 4))
        _row_action_button(self.frame, tr("button.choose"), self.choose_target_color, bg=ACTION_GREEN, activebackground=ACTION_GREEN_ACTIVE).grid(row=0, column=8, sticky="w")

        self.target_var.trace_add("write", lambda *_: self._on_change())
        self.enabled_var.trace_add("write", lambda *_: self.app.schedule_step1_preview())
        self.update_swatch()

    def _on_change(self) -> None:
        self.update_swatch()
        self.app.schedule_step1_preview()

    def update_swatch(self) -> None:
        try:
            self.target_swatch.configure(bg=_rgb_to_hex(_parse_rgb_any(self.target_var.get())))
        except Exception:
            self.target_swatch.configure(bg="#cccccc")

    def choose_target_color(self) -> None:
        try:
            initial = _rgb_to_hex(_parse_rgb_any(self.target_var.get()))
        except Exception:
            initial = "#ffffff"
        color = colorchooser.askcolor(color=initial, title="Ziel-RGB wählen")
        if color and color[0]:
            self.target_var.set(_rgb_to_text(tuple(int(round(v)) for v in color[0])))

    def get_mapping(self, tolerance: int):
        if not self.enabled_var.get():
            return None
        return recolor.MappingValues(
            True,
            self.detected.source_rgb,
            _parse_rgb_any(self.target_var.get()),
            int(tolerance),
            max(0, min(100, int(self.app.basic_noise_var.get()))),
            bool(self.app.basic_fill_solid_var.get()),
        )

    def get_target_rgb(self) -> RGB:
        return _parse_rgb_any(self.target_var.get())

    def destroy(self) -> None:
        self.frame.destroy()


class ManualWorkflowRow:
    def __init__(self, app: "WorkflowApp", parent: tk.Widget, index: int, source="0,0,0", target="255,255,255") -> None:
        self.app = app
        self.index = index
        self.enabled_var = tk.BooleanVar(value=True)
        self.source_var = tk.StringVar(value=source)
        self.tolerance_var = tk.StringVar(value="8")
        self.target_var = tk.StringVar(value=target)

        self.frame = ttk.Frame(parent)
        self.frame.grid(row=index, column=0, sticky="ew", padx=2, pady=1)
        self.frame.columnconfigure(13, weight=1)

        self.radio = ttk.Radiobutton(self.frame, variable=app.selected_manual_row_var, value=index, command=app.update_manual_status)
        self.radio.grid(row=0, column=0, padx=(0, 2))
        ttk.Label(self.frame, text=f"#{index + 1}", width=4).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(self.frame, variable=self.enabled_var, command=app.schedule_step1_preview).grid(row=0, column=2, padx=(0, 4))
        ttk.Entry(self.frame, textvariable=self.source_var, width=13).grid(row=0, column=3, sticky="w")
        self.source_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.source_swatch.grid(row=0, column=4, padx=(4, 4))
        _row_action_button(self.frame, tr("button.choose"), self.choose_source_color, bg=ACTION_YELLOW, activebackground=ACTION_YELLOW_ACTIVE).grid(row=0, column=5, sticky="w", padx=(0, 8))
        ttk.Label(self.frame, text="Tol.").grid(row=0, column=6, sticky="w")
        ttk.Entry(self.frame, textvariable=self.tolerance_var, width=5).grid(row=0, column=7, sticky="w", padx=(2, 8))
        ttk.Label(self.frame, text="→").grid(row=0, column=8, padx=2)
        ttk.Entry(self.frame, textvariable=self.target_var, width=13).grid(row=0, column=9, sticky="w", padx=(4, 0))
        self.target_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.target_swatch.grid(row=0, column=10, padx=(4, 4))
        _row_action_button(self.frame, tr("button.choose"), self.choose_target_color, bg=ACTION_GREEN, activebackground=ACTION_GREEN_ACTIVE).grid(row=0, column=11, sticky="w")

        for var in (self.source_var, self.tolerance_var, self.target_var):
            var.trace_add("write", lambda *_: self._on_change())
        self.update_swatches()

    def _on_change(self) -> None:
        self.update_swatches()
        self.app.schedule_step1_preview()

    def update_index(self, index: int) -> None:
        self.index = index
        self.radio.configure(value=index)
        # Label ist das zweite Child nach Radiobutton; einfacher neu setzen ueber grid slaves ist unnoetig.

    def update_swatches(self) -> None:
        for var, swatch in ((self.source_var, self.source_swatch), (self.target_var, self.target_swatch)):
            try:
                swatch.configure(bg=_rgb_to_hex(_parse_rgb_any(var.get())))
            except Exception:
                swatch.configure(bg="#cccccc")

    def choose_target_color(self) -> None:
        try:
            initial = _rgb_to_hex(_parse_rgb_any(self.target_var.get()))
        except Exception:
            initial = "#ffffff"
        color = colorchooser.askcolor(color=initial, title="Ziel-RGB wählen")
        if color and color[0]:
            self.target_var.set(_rgb_to_text(tuple(int(round(v)) for v in color[0])))

    def choose_source_color(self) -> None:
        try:
            initial = _rgb_to_hex(_parse_rgb_any(self.source_var.get()))
        except Exception:
            initial = "#000000"
        color = colorchooser.askcolor(color=initial, title="Quell-RGB wählen")
        if color and color[0]:
            self.source_var.set(_rgb_to_text(tuple(int(round(v)) for v in color[0])))

    def set_source_rgb(self, rgb: RGB) -> None:
        self.source_var.set(_rgb_to_text(rgb))

    def get_mapping(self):
        if not self.enabled_var.get():
            return None
        tol = max(0, min(255, int(float(self.tolerance_var.get().replace(",", ".")))))
        return recolor.MappingValues(True, _parse_rgb_any(self.source_var.get()), _parse_rgb_any(self.target_var.get()), tol)

    def get_target_rgb(self) -> RGB:
        return _parse_rgb_any(self.target_var.get())

    def destroy(self) -> None:
        self.frame.destroy()


class WorkflowApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        i18n.load_languages()
        self.title(tr("app.title"))
        self._set_window_icon()
        self.geometry("1480x920")
        self.minsize(1180, 760)
        self.after(10, self._force_maximized)
        self.after(300, self._force_maximized)

        self._config_loading = True
        self.user_config_dir = self._program_dir() / "vektorrazor_config"
        self.user_config_file = self.user_config_dir / "settings.json"
        self.scale_export_config_file = self.user_config_dir / "scale_export.json"
        self.user_config = self._load_user_config()

        self._i18n_widgets: list[tuple[tk.Widget, str, str]] = []
        self._i18n_notebook_tabs: list[tuple[ttk.Notebook, tk.Widget, str]] = []
        self._step1_scales: list[tk.Scale] = []
        self.style = ttk.Style(self)
        self.dark_mode_var = tk.BooleanVar(value=False)
        self.ui_theme_key_var = tk.StringVar(value="classic")
        self.ui_theme_display_var = tk.StringVar()
        self.ui_complexity_var = tk.StringVar(value="simple")
        self.ui_complexity_display_var = tk.StringVar()
        self.motif_profile_var = tk.StringVar(value="mixed")
        self.motif_profile_display_var = tk.StringVar()

        self.current_step = 0
        self.original_image: Optional[Image.Image] = None
        self.prepared_image: Optional[Image.Image] = None
        self.edited_image: Optional[Image.Image] = None
        self.special_result_image: Optional[Image.Image] = None
        self.special_result_mode: Optional[str] = None
        self.current_path: Optional[Path] = None
        self.preview_after_id: Optional[str] = None
        self.step2_live_after_id: Optional[str] = None
        self._suspend_live_preview = False

        self.basic_rows: List[BasicWorkflowRow] = []
        self.manual_rows: List[ManualWorkflowRow] = []
        self.vector_rows: List[Any] = []
        self.selected_manual_row_var = tk.IntVar(value=0)

        # Schritt 1 Variablen
        self.input_path_var = tk.StringVar()
        self.prep_brightness_var = tk.IntVar(value=0)
        self.prep_contrast_var = tk.IntVar(value=0)
        self.prep_black_var = tk.IntVar(value=0)
        self.prep_white_var = tk.IntVar(value=255)
        self.prep_gamma_var = tk.DoubleVar(value=1.0)
        self.prep_rotation_var = tk.DoubleVar(value=0.0)
        self.basic_threshold_var = tk.IntVar(value=10)
        self.basic_min_area_var = tk.IntVar(value=30)
        self.basic_max_colors_var = tk.IntVar(value=12)
        self.basic_alpha_var = tk.IntVar(value=10)
        self.basic_noise_var = tk.IntVar(value=45)
        self.basic_fill_solid_var = tk.BooleanVar(value=False)
        self.logo_mask_threshold_var = tk.IntVar(value=10)
        self.logo_mask_blur_var = tk.IntVar(value=50)
        self.logo_mask_clean_var = tk.BooleanVar(value=True)
        self.logo_mask_fg_var = tk.StringVar(value="0,0,0")
        self.logo_mask_bg_var = tk.StringVar(value="255,255,255")
        self.logo_mask_preserve_accents_var = tk.BooleanVar(value=True)
        self.logo_mask_accent_var = tk.StringVar(value="128,64,0")
        self.photo_scan_max_colors_var = tk.IntVar(value=3)
        self.photo_scan_min_area_var = tk.IntVar(value=10)
        self.photo_scan_noise_var = tk.IntVar(value=70)
        self.photo_scan_foreground_distance_var = tk.IntVar(value=30)
        self.photo_scan_weak_contrast_var = tk.IntVar(value=0)
        self.photo_scan_protect_background_var = tk.BooleanVar(value=False)
        self.photo_scan_object_mask_first_var = tk.BooleanVar(value=False)
        self.photo_scan_despeckle_var = tk.BooleanVar(value=False)
        self.photo_scan_despeckle_area_var = tk.IntVar(value=0)
        self.photo_scan_protect_thin_lines_var = tk.BooleanVar(value=True)
        self.photo_scan_close_lines_var = tk.BooleanVar(value=True)
        self.photo_scan_fill_small_holes_var = tk.BooleanVar(value=False)
        self.photo_scan_preserve_accents_var = tk.BooleanVar(value=True)
        self.photo_scan_mode_var = tk.StringVar(value="auto")
        self.photo_scan_status_var = tk.StringVar(value="")
        self.eraser_size_var = tk.IntVar(value=20)
        self.eraser_shape_var = tk.StringVar(value="round")
        self.eraser_color_var = tk.StringVar(value="255,255,255")
        self.eraser_status_var = tk.StringVar(value=tr("step1.eraser_status_idle"))
        self._eraser_last_xy: Optional[Tuple[int, int]] = None
        self.ai_upscale_model_var = tk.StringVar()
        self.ai_upscale_unit_var = tk.StringVar(value="px")
        self.ai_upscale_width_var = tk.StringVar()
        self.ai_upscale_height_var = tk.StringVar()
        self.ai_upscale_keep_aspect_var = tk.BooleanVar(value=True)
        self.ai_upscale_aspect_master_var = tk.StringVar(value="width")
        self.ai_upscale_output_var = tk.StringVar()
        self.ai_upscale_original_size_var = tk.StringVar(value="Originalbildgröße: -")
        self.step1_sync_view_var = tk.BooleanVar(value=False)
        self.step2_sync_view_var = tk.BooleanVar(value=False)
        self._syncing_step1_view = False
        self._syncing_step2_view = False

        # Schritt 2 Variablen
        self.vector_image_rgb: Optional[np.ndarray] = None
        self.vector_source_from_step1 = False
        self.vector_source_name_var = tk.StringVar(value=tr("status.no_intermediate"))
        self.output_path_var = tk.StringVar()
        self.pixel_to_mm_var = tk.StringVar(value="1.0")
        self.target_width_mm_var = tk.StringVar(value="")
        self.target_height_mm_var = tk.StringVar(value="")
        self.cad_tolerance_mm_var = tk.StringVar(value="0.03")
        self.vector_bbox_info_var = tk.StringVar(value="")
        self.dxf_compatibility_var = tk.StringVar(value="default")
        self.dxf_compatibility_display_var = tk.StringVar()
        self.dxf_version_var = tk.StringVar(value=_dxf_choice_for_version("R2000"))
        self.dxf_compatibility_info_var = tk.StringVar(
            value=DXF_COMPATIBILITY_PRESETS["default"][1] + "  Aktuell: DXF R2000"
        )
        self.profile_var = tk.StringVar(value="Standard")
        self.vector_mode_var = tk.StringVar(value="area")
        self.vector_mode_display_var = tk.StringVar()
        self.centerline_merge_px_var = tk.StringVar(value="0")
        self.closed_paths_only_var = tk.BooleanVar(value=False)
        self.fill_closed_shapes_var = tk.BooleanVar(value=False)
        self.group_connected_paths_var = tk.BooleanVar(value=True)
        self.force_color_layers_var = tk.BooleanVar(value=True)
        self.object_layers_dxf_var = tk.BooleanVar(value=False)
        self.preview_mode_var = tk.StringVar(value="object")
        self.preview_mode_display_var = tk.StringVar()
        self.use_bezier_var = tk.BooleanVar(value=False)
        self.unique_cad_lines_var = tk.BooleanVar(value=False)
        self.duplicate_line_tolerance_var = tk.StringVar(value="1,5")
        self.remove_loose_points_var = tk.BooleanVar(value=False)
        self.anchor_neighbor_distance_var = tk.StringVar(value="0.50")
        self.smooth_contours_var = tk.BooleanVar(value=False)
        self.smooth_strength_var = tk.StringVar(value="2")
        self.global_epsilon_var = tk.StringVar(value="0.350")
        self.global_tolerance_var = tk.StringVar(value="12")
        self.preprocess_vector_var = tk.BooleanVar(value=False)
        self.preprocess_blur_var = tk.DoubleVar(value=0.8)
        self.preprocess_edge_var = tk.DoubleVar(value=1.0)
        self.preprocess_noise_var = tk.DoubleVar(value=3.0)
        self.internal_scale_var = tk.StringVar(value="2")
        self.internal_scale_display_var = tk.StringVar()
        self.smart_smoothing_var = tk.BooleanVar(value=False)
        self.smart_corner_angle_var = tk.StringVar(value="45")
        self.smart_line_tolerance_var = tk.StringVar(value="1.0")
        self.smart_curve_strength_var = tk.StringVar(value="2")
        self.hole_scale_var = tk.StringVar(value="1.000")
        self.bridge_tabs_var = tk.BooleanVar(value=False)
        self.bridge_width_mm_var = tk.StringVar(value="1.000")
        self.bridge_width_percent_var = tk.StringVar(value="0.000")
        self.bridge_count_var = tk.StringVar(value="2.000")
        self.live_preview_var = tk.BooleanVar(value=True)
        self.cleanup_mode_var = tk.StringVar(value="off")
        self.cleanup_mode_display_var = tk.StringVar()
        self.min_object_area_mm2_var = tk.StringVar(value="0")
        self.min_object_percent_var = tk.StringVar(value="0,00")
        self.detected_contours: List[Any] = []
        self.last_rules: List[Any] = []
        self.selected_contour_index: Optional[int] = None
        self.selected_contour_indices: set[int] = set()
        self.vector_select_press: Optional[Tuple[int, int, str]] = None
        self.vector_selection_mode_var = tk.BooleanVar(value=False)
        self.show_anchor_points_var = tk.BooleanVar(value=False)
        self.selected_contour_text_var = tk.StringVar(value=tr("status.no_path_selected"))
        self.step2_shared_zoom_var = tk.DoubleVar(value=1.0)
        self.step2_zoom_percent_var = tk.StringVar(value="100")
        self.step2_zoom_preset_var = tk.StringVar(value="100%")
        self._syncing_step2_zoom = False
        self.step2_auto_prompt_pending = True
        self.vector_preview_supersample = 2
        self.vector_diagnostics_var = tk.StringVar(value="")
        self.cad_point_count_var = tk.StringVar(value="")
        self._lineart_recommendation_shown = False
        self._step1_recommendation_shown_for: Optional[str] = None
        self._busy_dialog: Optional[tk.Toplevel] = None
        self._busy_cancel_requested = False
        self._startup_welcome_shown = False
        self._run_step1_auto_after_load = True
        self._perfect_bw_source = False

        self.status_var = tk.StringVar(value=tr("status.ready"))
        self.progress_var = tk.DoubleVar(value=0.0)
        self._busy_progress_var: Optional[tk.DoubleVar] = None
        self._busy_status_var: Optional[tk.StringVar] = None

        self._apply_user_config_to_vars()
        self._build_ui()
        self._bind_live_preview_traces()
        self._bind_user_config_traces()
        self._config_loading = False
        self._save_user_config()
        self.add_manual_row()
        self.load_vector_profile("Standard")
        self.show_step(0)
        self.after(450, self.show_startup_welcome)

    def _program_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def _default_user_config(self) -> dict[str, Any]:
        return {
            "app": {
                "settings_version": 2,
                "language_files_dir": "lang",
            },
            "ui": {
                "language": i18n.FALLBACK_LANGUAGE,
                "dark_mode": False,
                "theme": "classic",
                "complexity": "simple",
                "motif_profile": "mixed",
            },
            "paths": {
                "last_input_dir": "",
                "last_input_path": "",
                "output_dir": "",
                "output_path": "",
            },
            "export": {
                "dxf_compatibility": "default",
                "dxf_version": "R2000",
                "live_preview": True,
            },
        }

    def _merge_config_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        merged = self._default_user_config()
        for section, defaults in merged.items():
            incoming = data.get(section, {}) if isinstance(data, dict) else {}
            if isinstance(defaults, dict) and isinstance(incoming, dict):
                defaults.update({key: value for key, value in incoming.items() if key in defaults})
        return merged

    def _legacy_user_config_files(self) -> list[Path]:
        # Früher wurde die Hauptkonfiguration als config.json gespeichert.
        # Beim ersten Start mit der neuen Version wird sie automatisch übernommen.
        return [self.user_config_dir / "config.json"]

    def _load_json_file(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _load_user_config(self) -> dict[str, Any]:
        try:
            self.user_config_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if self.user_config_file.exists():
            data = self._load_json_file(self.user_config_file)
            if data is not None:
                return self._merge_config_defaults(data)
            return self._default_user_config()

        for legacy_file in self._legacy_user_config_files():
            if not legacy_file.exists():
                continue
            data = self._load_json_file(legacy_file)
            if data is None:
                continue
            config = self._merge_config_defaults(data)
            self._write_user_config(config)
            return config

        config = self._default_user_config()
        self._write_user_config(config)
        return config

    def _default_ai_upscale_models_dir(self) -> Optional[Path]:
        return ai_upscale.AiUpscalePaths(self.user_config_dir).default_model_dir()

    def _default_ai_upscale_model_file(self) -> Optional[Path]:
        return ai_upscale.AiUpscalePaths(self.user_config_dir).default_model_dir()

    def _default_ai_upscale_output_path(self) -> Path:
        return ai_upscale.AiUpscalePaths(self.user_config_dir).default_output_path()

    def _normalize_ai_upscale_model_dir(self, raw_path: str) -> str:
        text = str(raw_path or "").strip()
        if not text:
            return ""
        path = Path(text).expanduser()
        if path.is_file():
            return str(path.parent)
        return str(path)

    def _ensure_ai_upscale_defaults(self) -> None:
        self._update_ai_upscale_original_size_label()
        if not self.ai_upscale_model_var.get().strip():
            default_model = self._default_ai_upscale_model_file()
            if default_model is not None:
                self.ai_upscale_model_var.set(str(default_model))
        else:
            normalized = self._normalize_ai_upscale_model_dir(self.ai_upscale_model_var.get())
            if normalized != self.ai_upscale_model_var.get():
                self.ai_upscale_model_var.set(normalized)
        if not self.ai_upscale_output_var.get().strip():
            self.ai_upscale_output_var.set(str(self._default_ai_upscale_output_path()))
        if self.original_image is not None:
            width_val = str(self.ai_upscale_width_var.get()).strip()
            height_val = str(self.ai_upscale_height_var.get()).strip()
            if not width_val and not height_val:
                base = self.get_prepared_image(force=False)
                if base is not None:
                    self.ai_upscale_width_var.set(str(max(64, base.width * 2)))
                    self.ai_upscale_height_var.set(str(max(64, base.height * 2)))
        self.update_ai_upscale_dimension_edit_state()

    def _update_ai_upscale_original_size_label(self) -> None:
        if self.original_image is None:
            self.ai_upscale_original_size_var.set("Originalbildgröße: -")
            return
        self.ai_upscale_original_size_var.set(
            f"Originalbildgröße: {self.original_image.width} x {self.original_image.height} px"
        )

    def update_ai_upscale_dimension_edit_state(self) -> None:
        width_entry = getattr(self, "ai_upscale_width_entry", None)
        height_entry = getattr(self, "ai_upscale_height_entry", None)
        master_row = getattr(self, "ai_upscale_master_frame", None)
        if width_entry is None or height_entry is None:
            return
        keep_aspect = bool(self.ai_upscale_keep_aspect_var.get())
        master = str(self.ai_upscale_aspect_master_var.get() or "width")
        if master not in {"width", "height"}:
            master = "width"
            self.ai_upscale_aspect_master_var.set(master)
        if master_row is not None:
            if keep_aspect:
                master_row.grid()
            else:
                master_row.grid_remove()
        if keep_aspect:
            width_entry.configure(state="normal" if master == "width" else "disabled")
            height_entry.configure(state="normal" if master == "height" else "disabled")
        else:
            width_entry.configure(state="normal")
            height_entry.configure(state="normal")

    def _run_ai_upscale(self, base: Image.Image, width: int, height: int, progress_callback=None) -> Path:
        return ai_upscale.run_ai_upscale(
            base=base,
            width=width,
            height=height,
            model_dir=Path(self._normalize_ai_upscale_model_dir(self.ai_upscale_model_var.get().strip())),
            output_path=Path(self.ai_upscale_output_var.get().strip() or self._default_ai_upscale_output_path()),
            paths=ai_upscale.AiUpscalePaths(self.user_config_dir),
            progress_callback=progress_callback,
        )

    def _write_json_atomic(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _write_user_config(self, config: dict[str, Any]) -> None:
        try:
            self._write_json_atomic(self.user_config_file, config)
        except Exception:
            pass

    def _default_scale_export_config(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "tolerance_percent": 0.30,
            "target_width_mm": "",
            "target_height_mm": "",
            "keep_proportions": True,
            "show_anchor_points": True,
            "anchor_point_size": 2.50,
            "live_preview": False,
        }

    def _load_scale_export_config(self) -> dict[str, Any]:
        default = self._default_scale_export_config()
        try:
            if not self.scale_export_config_file.exists():
                return default
            data = json.loads(self.scale_export_config_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return default
            merged = dict(default)
            for key in default:
                if key in data:
                    merged[key] = data[key]
            return merged
        except Exception:
            return default

    def _save_scale_export_config(self, config: dict[str, Any]) -> None:
        try:
            merged = self._default_scale_export_config()
            for key in merged:
                if key in config:
                    merged[key] = config[key]
            self._write_json_atomic(self.scale_export_config_file, merged)
        except Exception:
            pass

    def _apply_user_config_to_vars(self) -> None:
        ui_config = self.user_config.get("ui", {})
        export_config = self.user_config.get("export", {})

        language = str(ui_config.get("language", i18n.FALLBACK_LANGUAGE))
        if not i18n.set_language(language):
            i18n.set_language(i18n.FALLBACK_LANGUAGE)
        self.title(tr("app.title"))

        self.dark_mode_var.set(bool(ui_config.get("dark_mode", False)))
        theme_key = str(ui_config.get("theme", "classic"))
        self.ui_theme_key_var.set(theme_key if theme_key in UI_THEME_KEYS else "classic")
        complexity_key = str(ui_config.get("complexity", "simple"))
        self.ui_complexity_var.set(complexity_key if complexity_key in UI_COMPLEXITY_KEYS else "simple")
        motif_key = str(ui_config.get("motif_profile", "mixed"))
        self.motif_profile_var.set(motif_key if motif_key in MOTIF_PROFILE_KEYS else "mixed")

        profile = str(export_config.get("dxf_compatibility", "default"))
        self.dxf_compatibility_var.set(profile if profile in DXF_COMPATIBILITY_KEYS else "default")
        version = str(export_config.get("dxf_version", "R2000"))
        self.dxf_version_var.set(_dxf_choice_for_version(version))
        self.live_preview_var.set(bool(export_config.get("live_preview", True)))
        paths_config = self.user_config.get("paths", {})
        ai_model = str(paths_config.get("ai_upscale_model", ""))
        if ai_model:
            self.ai_upscale_model_var.set(self._normalize_ai_upscale_model_dir(ai_model))
        ai_output = str(paths_config.get("ai_upscale_output", ""))
        if ai_output:
            self.ai_upscale_output_var.set(ai_output)

    def _bind_user_config_traces(self) -> None:
        for var in (
            self.dark_mode_var,
            self.ui_theme_key_var,
            self.ui_complexity_var,
            self.motif_profile_var,
            self.live_preview_var,
            self.dxf_compatibility_var,
            self.dxf_version_var,
            self.output_path_var,
            self.input_path_var,
        ):
            try:
                var.trace_add("write", lambda *_: self._save_user_config())
            except Exception:
                pass

    def _save_user_config(self) -> None:
        if getattr(self, "_config_loading", False):
            return
        config = self._merge_config_defaults(getattr(self, "user_config", {}))
        language = i18n.current_language()
        available_language_codes = {code for code, _name in i18n.available_languages()}
        config["ui"]["language"] = language if language in available_language_codes else i18n.FALLBACK_LANGUAGE
        config["ui"]["dark_mode"] = bool(self.dark_mode_var.get())
        theme_key = self.ui_theme_key_var.get()
        config["ui"]["theme"] = theme_key if theme_key in UI_THEME_KEYS else "classic"
        complexity_key = self.ui_complexity_var.get()
        config["ui"]["complexity"] = complexity_key if complexity_key in UI_COMPLEXITY_KEYS else "simple"
        motif_key = self.motif_profile_var.get()
        config["ui"]["motif_profile"] = motif_key if motif_key in MOTIF_PROFILE_KEYS else "mixed"

        profile = self.dxf_compatibility_var.get()
        config["export"]["dxf_compatibility"] = profile if profile in DXF_COMPATIBILITY_KEYS else "default"
        config["export"]["dxf_version"] = self.get_selected_dxf_version()
        config["export"]["live_preview"] = bool(self.live_preview_var.get())

        input_path = self.input_path_var.get().strip()
        if input_path:
            config["paths"]["last_input_path"] = input_path
            config["paths"]["last_input_dir"] = str(Path(input_path).expanduser().parent)
        output_path = self.output_path_var.get().strip()
        if output_path:
            config["paths"]["output_path"] = output_path
            config["paths"]["output_dir"] = str(Path(output_path).expanduser().parent)
        ai_model_path = self.ai_upscale_model_var.get().strip()
        if ai_model_path:
            config["paths"]["ai_upscale_model"] = self._normalize_ai_upscale_model_dir(ai_model_path)
        ai_output_path = self.ai_upscale_output_var.get().strip()
        if ai_output_path:
            config["paths"]["ai_upscale_output"] = ai_output_path

        self.user_config = config
        self._write_user_config(config)

    def _initial_dir_from_config(self, kind: str) -> Optional[str]:
        paths = self.user_config.get("paths", {})
        keys = ("last_input_dir", "last_input_path") if kind == "input" else ("output_dir", "output_path", "last_input_dir")
        for key in keys:
            raw = str(paths.get(key, "") or "")
            if not raw:
                continue
            path = Path(raw).expanduser()
            candidate = path if path.is_dir() else path.parent
            if candidate.exists():
                return str(candidate)
        return None

    def _remember_input_path(self, path: str) -> None:
        self.input_path_var.set(path)
        self._save_user_config()

    def _register_i18n(self, widget: tk.Widget, option: str, key: str) -> None:
        self._i18n_widgets.append((widget, option, key))
        try:
            widget.configure(**{option: tr(key)})
        except Exception:
            pass

    def _register_notebook_tab(self, notebook: ttk.Notebook, tab: tk.Widget, key: str) -> None:
        self._i18n_notebook_tabs.append((notebook, tab, key))
        try:
            notebook.tab(tab, text=tr(key))
        except Exception:
            pass

    def _add_tooltip(self, widget: tk.Widget, text_key: str) -> None:
        try:
            if getattr(widget, "_vektorrazor_tooltip", False):
                return
            HoverTooltip(widget, text_key)
            setattr(widget, "_vektorrazor_tooltip", True)
            widget.configure(cursor="question_arrow")
        except Exception:
            pass

    def _bind_live_preview_traces(self) -> None:
        # Nur Checkboxen und Comboboxen bekommen trace_add.
        # Numerische Input-Felder und Slider werden über FocusOut/Return/ButtonRelease gebunden.
        checkbox_and_combo_vars: list[tk.Variable] = [
            self.vector_mode_var,
            self.closed_paths_only_var,
            self.fill_closed_shapes_var,
            self.group_connected_paths_var,
            self.force_color_layers_var,
            self.object_layers_dxf_var,
            self.preview_mode_var,
            self.use_bezier_var,
            self.unique_cad_lines_var,
            self.remove_loose_points_var,
            self.smooth_contours_var,
            self.preprocess_vector_var,
            self.internal_scale_var,
            self.smart_smoothing_var,
            self.bridge_tabs_var,
            self.cleanup_mode_var,
        ]
        for var in checkbox_and_combo_vars:
            try:
                var.trace_add("write", self._schedule_live_preview_if_enabled)
            except Exception:
                pass

    def _language_display_to_code(self) -> dict[str, str]:
        return {name: code for code, name in i18n.available_languages()}

    def _compat_label(self, key: str) -> str:
        return tr(f"dxf.compat.{key}")

    def _mode_label(self, key: str) -> str:
        return tr(f"vector_mode.{key}")

    def _preview_label(self, key: str) -> str:
        return tr(f"preview_mode.{key}")

    def _cleanup_label(self, key: str) -> str:
        return tr(f"cleanup.{key}")

    def _internal_scale_label(self, key: str) -> str:
        return tr(f"internal_scale.{key}x")

    def _ui_theme_label(self, key: str) -> str:
        return tr(f"ui.theme.{key}")

    def _ui_complexity_label(self, key: str) -> str:
        return tr(f"ui.mode.{key}")

    def _motif_profile_label(self, key: str) -> str:
        return tr(f"motif_profile.{key}")

    def _step1_mode_label(self, key: str) -> str:
        return tr(f"step1.mode.{key}")

    def _step1_mode_hint(self, key: str) -> str:
        return tr(f"step1.mode_hint.{key}")

    def _refresh_step1_mode_selector(self) -> None:
        if not hasattr(self, "step1_mode_box"):
            return
        keys = list(getattr(self, "step1_mode_keys", ["prep", "basic", "manual", "eraser", "logo", "photo_scan"]))
        labels = [self._step1_mode_label(key) for key in keys]
        self.step1_mode_display_to_key = dict(zip(labels, keys))
        self.step1_mode_box.configure(values=labels)
        key = self.step1_tab_key_var.get() if hasattr(self, "step1_tab_key_var") else "prep"
        if key not in keys:
            key = "prep"
        self.step1_tab_display_var.set(self._step1_mode_label(key))
        self.step1_tab_hint_var.set(self._step1_mode_hint(key))

    def _refresh_combobox_labels(self) -> None:
        if hasattr(self, "language_box"):
            languages = i18n.available_languages()
            self.language_box.configure(values=[name for _code, name in languages])
            current = i18n.current_language()
            for code, name in languages:
                if code == current:
                    self.language_var.set(name)
                    break

        self._refresh_step1_mode_selector()

        if hasattr(self, "compat_box"):
            self.compat_box.configure(values=[self._compat_label(key) for key in DXF_COMPATIBILITY_KEYS])
            self.dxf_compatibility_display_var.set(self._compat_label(self.dxf_compatibility_var.get()))
        if hasattr(self, "vector_mode_box"):
            self.vector_mode_box.configure(values=[self._mode_label(key) for key in VECTOR_MODE_KEYS])
            self.vector_mode_display_var.set(self._mode_label(self.vector_mode_var.get()))
        if hasattr(self, "preview_mode_box"):
            self.preview_mode_box.configure(values=[self._preview_label(key) for key in PREVIEW_MODE_KEYS])
            self.preview_mode_display_var.set(self._preview_label(self.preview_mode_var.get()))
        if hasattr(self, "cleanup_mode_box"):
            self.cleanup_mode_box.configure(values=[self._cleanup_label(key) for key in CLEANUP_MODE_KEYS])
            self.cleanup_mode_display_var.set(self._cleanup_label(self.cleanup_mode_var.get()))
        if hasattr(self, "internal_scale_box"):
            self.internal_scale_box.configure(values=[self._internal_scale_label(key) for key in INTERNAL_SCALE_KEYS])
            self.internal_scale_display_var.set(self._internal_scale_label(self.internal_scale_var.get()))
        if hasattr(self, "ui_theme_box"):
            self.ui_theme_box.configure(values=[self._ui_theme_label(key) for key in UI_THEME_KEYS])
            self.ui_theme_display_var.set(self._ui_theme_label(self.ui_theme_key_var.get()))
        if hasattr(self, "ui_complexity_box"):
            self.ui_complexity_box.configure(values=[self._ui_complexity_label(key) for key in UI_COMPLEXITY_KEYS])
            self.ui_complexity_display_var.set(self._ui_complexity_label(self.ui_complexity_var.get()))
        if hasattr(self, "motif_profile_box"):
            self.motif_profile_box.configure(values=[self._motif_profile_label(key) for key in MOTIF_PROFILE_KEYS])
            self.motif_profile_display_var.set(self._motif_profile_label(self.motif_profile_var.get()))

    def refresh_ui_texts(self) -> None:
        self.title(tr("app.title"))
        for widget, option, key in self._i18n_widgets:
            try:
                widget.configure(**{option: tr(key)})
            except Exception:
                pass
        for notebook, tab, key in self._i18n_notebook_tabs:
            try:
                notebook.tab(tab, text=tr(key))
            except Exception:
                pass
        self._refresh_combobox_labels()
        self.on_dxf_compatibility_changed()
        if hasattr(self, "vector_colors_window"):
            self.vector_colors_window.title(tr("step2.edit_colors"))
        self.show_step(self.current_step)

    def _register_existing_texts(self) -> None:
        text_to_key = {
            "PNG-Logo → CAD-nahe Vektordaten": "app.header",
            "Input-Bild:": "step1.input_image",
            "Bild laden": "step1.load_image",
            "PNG speichern": "step1.save_png",
            "Workflow / Abschluss Schritt 1": "step1.actions",
            "Weiter zur Vektorisierung →": "nav.next_vectorize",
            "Zwischenbild nur aktualisieren": "step1.use_preview_as_base",
            "Für Vektorisierung übernehmen": "step1.use_preview_as_base",
            "Aktuelle Vorschau als neue Grundlage": "step1.use_preview_as_base",
            "Hinweis: 'Weiter zur Vektorisierung' übernimmt das bearbeitete Bild automatisch. Der Aktualisieren-Button ist nur optional.": "step1.update_hint",
            "1) Bildvorbereitung": "step1.prep",
            "Helligkeit": "step1.brightness",
            "Kontrast": "step1.contrast",
            "Schwarzpunkt": "step1.black_point",
            "Weißpunkt": "step1.white_point",
            "Gamma": "step1.gamma",
            "Zurücksetzen": "step1.reset",
            "Vorbereitung + Farben neu erkennen": "step1.prep_detect",
            "2) Automatische Farberkennung": "step1.detect",
            "Schwelle": "step1.threshold",
            "Min. Fläche": "step1.min_area",
            "Max. Farben": "step1.max_colors",
            "Alpha ab": "step1.alpha_from",
            "Farben erkennen": "step1.update_colors",
            "Kontrastfarben neu": "step1.reassign",
            "Tipp: Schritt 1 schreibt exakte RGB-Farben ins Zwischen-PNG. Diese RGB-Werte werden in Schritt 2 automatisch als Layer-Regeln übernommen.": "step1.basic_hint",
            "3) Erkannte Farbbereiche": "step1.detected_ranges",
            "Aktiv  Quelle / Anteil  → Ziel-RGB": "step1.rows_header",
            "+ Farbumsetzung": "step1.add_mapping",
            "- selektierte löschen": "step1.delete_selected",
            "Kurzer Klick ins Originalbild übernimmt Farbe in die selektierte Zeile. Ziehen verschiebt die Vorschau.": "step1.manual_status",
            "Manuelle Farbumsetzungen": "step1.manual_mappings",
            "Für graue Logos, Schatten oder Verläufe: Maske über lokalen Kontrast erzeugen.": "step1.logo_hint",
            "Logo-Schwelle": "step1.logo_threshold",
            "höher = weniger wird schwarz": "step1.logo_threshold_hint",
            "Hintergrund-Radius": "step1.logo_radius",
            "größer = Schatten/Verläufe werden eher ignoriert": "step1.logo_radius_hint",
            "Logo RGB": "step1.logo_rgb",
            "Hintergrund RGB": "step1.background_rgb",
            "kleine Pixelstörungen glätten": "step1.clean_pixels",
            "Logo-Maske erzeugen": "step1.create_mask",
            "Maske entfernen / normale Vorschau": "step1.clear_mask",
            "Zwischenbild:": "step2.source",
            "PNG direkt laden": "step2.load_png",
            "Output:": "step2.output",
            "Speichern als": "step2.save_as",
            "Pixel zu mm:": "step2.pixel_to_mm",
            "Kompatibilität:": "step2.compatibility",
            "DXF-Format:": "step2.dxf_format",
            "Abschluss / Aktionen": "step2.actions",
            "1  Optional: Auto-Werte testen": "step2.auto",
            "2  Erkennen / Vorschau": "step2.detect_preview",
            "3  Export DXF / SVG": "step2.export",
            "Auto-Werte ist optional und rechnet selbst eine Vorschau. Danach Vorschau prüfen oder direkt exportieren.": "step2.actions_hint",
            "Farben / Layer": "step2.colors_layer",
            "Farben / Layer bearbeiten": "step2.edit_colors",
            "Farben aus Bild erkennen": "step2.detect_colors_from_image",
            "Dynamische Farbtabelle": "step2.dynamic_table",
            "+ Farbe": "step2.add_color",
            "Profil:": "step2.profile",
            "Anwenden": "step2.apply",
            "Vektor-Optionen": "step2.options",
            "Vektorart": "step2.vector_type",
            "Linien zusammenführen px": "step2.merge_lines",
            "Nur geschlossene Pfade": "step2.closed_only",
            "SVG-Flächen füllen (Export)": "step2.fill_svg",
            "Zusammenhängende Pfade gruppieren (SVG)": "step2.group_connected_paths",
            "Export-Layer pro Farbe": "step2.force_color_layers",
            "Objekte in Layer erstellen (DXF)": "step2.object_layers_dxf",
            "Bezier für SVG": "step2.bezier_svg",
            "Doppelte Linien entfernen (CAD)": "step2.dedupe",
            "Doppellinien-Toleranz px": "step2.dedupe_tolerance",
            "Vorschau-Modus": "step2.preview_mode",
            "Vorschau-Ansicht": "step2.preview_mode",
            "Lose Ankerpunkte entfernen": "step2.loose_points",
            "Rundungen glätten": "step2.smooth",
            "Punktreduktion / Epsilon px": "step2.global_epsilon",
            "Auf alle Farben anwenden": "step2.apply_all_colors",
            "Epsilon auf alle Farben anwenden": "step2.apply_all_colors",
            "Vorverarbeitung aktiv": "step2.preprocess_enabled",
            "Weichzeichnen / Blur": "step2.preprocess_blur",
            "Kanten beruhigen": "step2.preprocess_edges",
            "Mindeststörung px": "step2.preprocess_noise",
            "Interne Skalierung": "step2.internal_scale",
            "Vorschau aktualisieren": "step2.refresh_preview",
            "Smart CAD Smoothing": "step2.smart_smoothing",
            "Ecken schützen ab Grad": "step2.smart_corner_angle",
            "Ecken schützen °": "step2.smart_corner_angle",
            "Geraden-Toleranz px": "step2.smart_line_tolerance",
            "Gerade Linien Toleranz px": "step2.smart_line_tolerance",
            "Kurven-Glättung": "step2.smart_curve_strength",
            "Lochgröße / Innenlöcher": "step2.hole_scale",
            "Kleine Objekte löschen": "step2.delete_small",
            "% Bildfläche": "step2.percent_area",
            "Pfad-Auswahl": "step2.path_selection",
            "Auswahl-Modus": "step2.selection_mode",
            "Ausgewählte Pfade entfernen": "step2.remove_selected_paths",
            "Auswahl aufheben": "step2.clear_selection",
            "Auswahl-Modus EIN: Klick = Pfad wählen, STRG+Klick = hinzufügen/umschalten, ALT+Klick = direkt entfernen. Auswahl-Modus AUS: Klick/Ziehen verschiebt die Vorschau; nur STRG+Klick wählt temporär.": "step2.selection_help",
            "Original": "canvas.original",
            "Bearbeitet / technische Zwischenstufe": "canvas.edited",
            "Zwischen-PNG": "canvas.step2_original",
            "Vektor-Vorschau": "canvas.vector_preview",
            "wählen": "button.choose",
            "Schließen": "button.close",
            "Tol.": "label.tolerance_short",
        }
        text_to_tooltip = {
            "Helligkeit": "tooltip.step1.brightness",
            "Kontrast": "tooltip.step1.contrast",
            "Schwarzpunkt": "tooltip.step1.black_point",
            "WeiÃŸpunkt": "tooltip.step1.white_point",
            "Weißpunkt": "tooltip.step1.white_point",
            "Gamma": "tooltip.step1.gamma",
            "Rotation °": "tooltip.step1.rotation",
            "Schwelle": "tooltip.step1.threshold",
            "Min. FlÃ¤che": "tooltip.step1.min_area",
            "Min. Fläche": "tooltip.step1.min_area",
            "Max. Farben": "tooltip.step1.max_colors",
            "Alpha ab": "tooltip.step1.alpha_from",
            "Rauschen unterdrÃ¼cken": "tooltip.step1.noise_suppression",
            "Rauschen unterdrücken": "tooltip.step1.noise_suppression",
            "Logo-Schwelle": "tooltip.step1.logo_threshold",
            "Hintergrund-Radius": "tooltip.step1.logo_radius",
            "Ziel-Farben": "tooltip.step1.photo_scan_max_colors",
            "Rauschen bereinigen": "tooltip.step1.photo_scan_noise",
            "Farbabstand zum Hintergrund": "tooltip.step1.photo_scan_foreground_distance",
            "Schwache Farben / schwache Kontraste erkennen": "tooltip.step1.photo_scan_weak_contrast",
            "Schwache / feine Details erkennen": "tooltip.step1.photo_scan_weak_contrast",
            "Punktreduktion / Epsilon px": "tooltip.step2.global_epsilon",
            "Linien zusammenfÃ¼hren px": "tooltip.step2.merge_lines",
            "Linien zusammenführen px": "tooltip.step2.merge_lines",
            "Doppellinien-Toleranz px": "tooltip.step2.dedupe_tolerance",
            "Weichzeichnen / Blur": "tooltip.step2.preprocess_blur",
            "Kanten beruhigen": "tooltip.step2.preprocess_edges",
            "MindeststÃ¶rung px": "tooltip.step2.preprocess_noise",
            "Mindeststörung px": "tooltip.step2.preprocess_noise",
            "Interne Skalierung": "tooltip.step2.internal_scale",
            "Ecken schÃ¼tzen ab Grad": "tooltip.step2.smart_corner_angle",
            "Ecken schÃ¼tzen Â°": "tooltip.step2.smart_corner_angle",
            "Ecken schützen °": "tooltip.step2.smart_corner_angle",
            "Geraden-Toleranz px": "tooltip.step2.smart_line_tolerance",
            "Gerade Linien Toleranz px": "tooltip.step2.smart_line_tolerance",
            "Kurven-GlÃ¤ttung": "tooltip.step2.smart_curve_strength",
            "Kurven-Glättung": "tooltip.step2.smart_curve_strength",
            "LochgrÃ¶ÃŸe / InnenlÃ¶cher": "tooltip.step2.hole_scale",
            "Lochgröße / Innenlöcher": "tooltip.step2.hole_scale",
            "BrÃ¼ckenbreite mm": "tooltip.step2.bridge_width_mm",
            "Brückenbreite mm": "tooltip.step2.bridge_width_mm",
            "BrÃ¼ckenbreite % vom Bild": "tooltip.step2.bridge_width_percent",
            "Brückenbreite % vom Bild": "tooltip.step2.bridge_width_percent",
            "BrÃ¼cken pro Teil": "tooltip.step2.bridge_count",
            "Brücken pro Teil": "tooltip.step2.bridge_count",
            "Kleine Objekte lÃ¶schen": "tooltip.step2.delete_small",
            "Kleine Objekte löschen": "tooltip.step2.delete_small",
            "mmÂ²": "tooltip.step2.delete_small_mm",
            "mm²": "tooltip.step2.delete_small_mm",
            "% BildflÃ¤che": "tooltip.step2.delete_small_percent",
            "% Bildfläche": "tooltip.step2.delete_small_percent",
            "GlÃ¤ttung:": "tooltip.step2.smooth_strength",
            "Rundungen glÃ¤tten": "tooltip.step2.smooth_strength",
            "Rundungen glätten": "tooltip.step2.smooth_strength",
            "Zoom": "tooltip.step2.zoom",
            "Pixel zu mm:": "tooltip.step2.pixel_to_mm",
        }

        def walk(widget: tk.Widget) -> None:
            try:
                text = str(widget.cget("text"))
                key = text_to_key.get(text)
                if key:
                    self._register_i18n(widget, "text", key)
                tooltip_key = text_to_tooltip.get(text)
                if tooltip_key:
                    self._add_tooltip(widget, tooltip_key)
            except Exception:
                pass
            for child in widget.winfo_children():
                walk(child)

        walk(self)
        if hasattr(self, "prep_tab"):
            self._register_notebook_tab(self.step1_notebook, self.prep_tab, "step1.tab_preprocess")
        self._register_notebook_tab(self.step1_notebook, self.basic_tab, "step1.tab_basic")
        self._register_notebook_tab(self.step1_notebook, self.manual_tab, "step1.tab_manual")
        self._register_notebook_tab(self.step1_notebook, self.logo_tab, "step1.tab_logo")
        if hasattr(self, "photo_scan_tab"):
            self._register_notebook_tab(self.step1_notebook, self.photo_scan_tab, "step1.tab_photo_scan")

    def on_language_changed(self, _event: tk.Event | None = None) -> None:
        code = self._language_display_to_code().get(self.language_var.get())
        if not code or not i18n.set_language(code):
            return
        self.refresh_ui_texts()
        self._save_user_config()
        message = i18n.language_status_message() or tr("status.language_changed")
        self.status_var.set(message)

    def _set_window_icon(self) -> None:
        """Fenster-Icon aus assets setzen. PyInstaller packt es per --add-data in die EXE."""
        ico_path = resource_path("assets/vektorrazor.ico")
        png_path = resource_path("assets/vektorrazor_icon.png")

        if ico_path.exists():
            try:
                self.iconbitmap(default=str(ico_path))
                return
            except Exception:
                pass

        if png_path.exists():
            try:
                self._window_icon_photo = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._window_icon_photo)
            except Exception:
                pass

    def _force_maximized(self) -> None:
        # Plattform-robust: Windows (zoomed), Linux/X11 (attributes -zoomed),
        # und als Fallback volle Bildschirm-Geometrie.
        try:
            self.state("zoomed")
            return
        except Exception:
            pass
        try:
            self.attributes("-zoomed", True)
            return
        except Exception:
            pass
        try:
            self.wm_attributes("-zoomed", 1)
            return
        except Exception:
            pass
        try:
            sw = max(1200, int(self.winfo_screenwidth()))
            sh = max(800, int(self.winfo_screenheight()))
            self.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            pass

    # ------------------------------------------------------------------ UI Aufbau
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(10, 8, 10, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)

        ttk.Label(header, text="PNG-Logo → CAD-nahe Vektordaten", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        self.step_label = ttk.Label(header, text="", font=("Segoe UI", 10, "bold"))
        self.step_label.grid(row=0, column=1, padx=(18, 0), sticky="w")
        self.language_var = tk.StringVar()
        self.language_box = ttk.Combobox(header, textvariable=self.language_var, state="readonly", width=20)
        self.language_box.grid(row=0, column=2, sticky="e", padx=(8, 10))
        self.language_box.bind("<<ComboboxSelected>>", self.on_language_changed)
        # Layout-Design-Auswahl entfernt: Vektorrazor nutzt ein einheitliches Layout.
        # Einfach/Experte wird bewusst nicht mehr im Header angezeigt.
        # Die Umschaltung sitzt jetzt direkt links oben in den Vektor-Optionen.
        self.ui_complexity_box = ttk.Combobox(header, textvariable=self.ui_complexity_display_var, state="readonly", width=12)
        self.ui_complexity_box.bind("<<ComboboxSelected>>", lambda _event: self.on_ui_complexity_display_changed())
        self.dark_toggle = ttk.Checkbutton(header, text=tr("ui.dark_mode"), variable=self.dark_mode_var, command=self.apply_ui_theme)
        self.dark_toggle.grid(row=0, column=3, sticky="e", padx=(0, 8))
        # Navigation bewusst als große, farbige Buttons:
        # Man sieht sofort, was der nächste Workflow-Schritt ist.
        self.back_btn = tk.Button(
            header,
            text="← Zurück",
            command=self.back_step,
            bg="#6b7280",
            fg="white",
            activebackground="#4b5563",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=14,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.back_btn.grid(row=0, column=6, padx=(6, 4))
        self.next_btn = tk.Button(
            header,
            text="Weiter →",
            command=self.next_step,
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=16,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.next_btn.grid(row=0, column=7, padx=(4, 0))
        self.back_btn.grid_remove()
        self.next_btn.grid_remove()

        self.content = ttk.Frame(self)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.step1_frame = ttk.Frame(self.content, padding=8)
        self.step2_frame = ttk.Frame(self.content, padding=8)
        for frame in (self.step1_frame, self.step2_frame):
            frame.grid(row=0, column=0, sticky="nsew")

        self._build_step1()
        self._build_step2()

        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Progressbar(footer, variable=self.progress_var, maximum=100).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._register_existing_texts()
        self._refresh_combobox_labels()
        self._register_i18n(self.dark_toggle, "text", "ui.dark_mode")
        language_message = i18n.language_status_message()
        if language_message:
            self.status_var.set(language_message)
        self.apply_ui_theme()
        self.apply_ui_complexity_mode()

    def _build_step1(self) -> None:
        return ui_step1._build_step1(self)

    def _add_scale(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        variable: tk.Variable,
        from_: float,
        to: float,
        resolution: float,
        i18n_key: Optional[str] = None,
        tooltip_key: Optional[str] = None,
    ) -> None:
        return ui_step1._add_scale(self, parent, row, label, variable, from_, to, resolution, i18n_key, tooltip_key)

    def _build_step1_basic_tab(self) -> None:
        return ui_step1._build_step1_basic_tab(self)

    def _build_step1_manual_tab(self) -> None:
        return ui_step1._build_step1_manual_tab(self)

    def _build_step1_eraser_tab(self) -> None:
        return ui_step1._build_step1_eraser_tab(self)

    def _build_step1_logo_tab(self) -> None:
        return ui_step1._build_step1_logo_tab(self)

    def _build_step1_photo_scan_tab(self) -> None:
        return ui_step1._build_step1_photo_scan_tab(self)

    def _build_step1_ai_upscale_tab(self) -> None:
        return ui_step1._build_step1_ai_upscale_tab(self)

    def _build_step2(self) -> None:
        return ui_step2._build_step2(self)

    def _build_vector_colors_modal(self) -> None:
        return ui_step2._build_vector_colors_modal(self)

    def open_vector_colors_modal(self) -> None:
        self.update_vector_color_count()
        self.vector_colors_window.deiconify()
        self.vector_colors_window.lift()
        self.vector_colors_window.focus_set()

    def close_vector_colors_modal(self) -> None:
        self.vector_colors_window.withdraw()

    # ------------------------------------------------------------------ Navigation
    def show_step(self, index: int) -> None:
        previous_step = self.current_step
        self.current_step = max(0, min(1, index))
        if self.current_step == 0:
            self.step1_frame.tkraise()
            self.step_label.configure(text=tr("step1.label"))
            dark = bool(self.dark_mode_var.get())
            self.back_btn.configure(
                text=tr("nav.back"),
                state="disabled",
                bg="#9ca3af",
                fg="#f3f4f6" if dark else "#1f2937",
                disabledforeground="#f3f4f6" if dark else "#1f2937",
                activebackground="#9ca3af",
                activeforeground="#f3f4f6" if dark else "#1f2937",
                cursor="arrow",
            )
            self.next_btn.configure(
                text=tr("nav.next_vectorize"),
                state="normal",
                bg="#2563eb",
                fg="white",
                activebackground="#1d4ed8",
                activeforeground="white",
                cursor="hand2",
            )
        else:
            self.step2_frame.tkraise()
            self.step_label.configure(text=tr("step2.label"))
            self.back_btn.configure(
                text=tr("nav.back_to_step1"),
                state="normal",
                bg="#f97316",
                fg="white",
                activebackground="#ea580c",
                activeforeground="white",
                cursor="hand2",
            )
            self.next_btn.configure(
                text=tr("nav.export"),
                state="normal",
                bg="#15803d",
                fg="white",
                activebackground="#166534",
                activeforeground="white",
                cursor="hand2",
            )
            if previous_step != 1:
                self.on_enter_step2()

    def next_step(self) -> None:
        if self.current_step == 0:
            if self.use_edited_for_vector(show_message=False):
                self.show_step(1)
        else:
            self.export_vector_file()

    def back_step(self) -> None:
        self.show_step(0)

    def show_i18n_info(self, title_key: str, body_key: str) -> None:
        messagebox.showinfo(tr(title_key), tr(body_key))

    def show_startup_welcome(self) -> None:
        if self._startup_welcome_shown:
            return
        self._startup_welcome_shown = True
        choice = tk.StringVar(value="mixed")
        dialog = tk.Toplevel(self)
        dialog.title(tr("msg.welcome_title"))
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        dark = bool(self.dark_mode_var.get())
        bg = "#2b2b2b" if dark else "#ffffff"
        fg = "#f3f4f6" if dark else "#111827"
        muted = "#d1d5db" if dark else "#4b5563"
        select_bg = "#353535" if dark else "#ffffff"
        dialog.configure(bg=bg)

        body = tk.Frame(dialog, bg=bg, padx=20, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=tr("msg.welcome_title"),
            bg=bg,
            fg=fg,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        tk.Label(
            body,
            text=tr("msg.welcome_body"),
            bg=bg,
            fg=muted,
            justify="left",
            wraplength=560,
        ).pack(anchor="w", pady=(0, 14))
        tk.Label(
            body,
            text=tr("startup_preset.choose"),
            bg=bg,
            fg=fg,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        for key in STARTUP_PRESET_KEYS:
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x", anchor="w", pady=4)
            tk.Radiobutton(
                row,
                variable=choice,
                value=key,
                bg=bg,
                fg=fg,
                selectcolor=select_bg,
                activebackground=bg,
                activeforeground=fg,
            ).pack(side="left", anchor="n")
            text_box = tk.Frame(row, bg=bg)
            text_box.pack(side="left", fill="x", expand=True)
            tk.Label(
                text_box,
                text=tr(f"startup_preset.{key}.title"),
                bg=bg,
                fg=fg,
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            ).pack(anchor="w")
            tk.Label(
                text_box,
                text=tr(f"startup_preset.{key}.desc"),
                bg=bg,
                fg=muted,
                justify="left",
                wraplength=500,
                anchor="w",
            ).pack(anchor="w")

        buttons = tk.Frame(body, bg=bg)
        buttons.pack(fill="x", pady=(14, 0))

        def apply_and_close() -> None:
            self.apply_startup_preset(choice.get())
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", apply_and_close)
        tk.Button(
            buttons,
            text=tr("button.apply"),
            command=apply_and_close,
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            padx=14,
            pady=4,
        ).pack(side="right")
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        self.wait_window(dialog)

    def apply_startup_preset(self, preset_key: str) -> None:
        self.apply_motif_profile(preset_key)

    def apply_motif_profile(self, profile_key: str) -> None:
        if profile_key not in MOTIF_PROFILE_KEYS:
            profile_key = "mixed"
        self.motif_profile_var.set(profile_key)
        self.motif_profile_display_var.set(self._motif_profile_label(profile_key))

        if profile_key == "logo":
            self.preprocess_vector_var.set(True)
            self.preprocess_blur_var.set(0.150)
            self.preprocess_edge_var.set(1.000)
            self.preprocess_noise_var.set(2.000)
            self.internal_scale_var.set("2")
            self.global_epsilon_var.set("1.500")
            self.smooth_contours_var.set(False)
            self.smooth_strength_var.set("0.000")
            self.smart_smoothing_var.set(True)
            self.smart_corner_angle_var.set("25.000")
            self.smart_line_tolerance_var.set("2.000")
            self.smart_curve_strength_var.set("1.000")
            self.cleanup_mode_var.set("off")
        elif profile_key == "organic":
            self.preprocess_vector_var.set(True)
            self.preprocess_blur_var.set(0.250)
            self.preprocess_edge_var.set(0.300)
            self.preprocess_noise_var.set(0.500)
            self.internal_scale_var.set("3")
            self.global_epsilon_var.set("0.120")
            self.smooth_contours_var.set(False)
            self.smooth_strength_var.set("0.000")
            self.smart_smoothing_var.set(False)
            self.smart_corner_angle_var.set("35.000")
            self.smart_line_tolerance_var.set("0.600")
            self.smart_curve_strength_var.set("0.000")
            self.cleanup_mode_var.set("off")
        else:
            self.preprocess_vector_var.set(True)
            self.preprocess_blur_var.set(0.250)
            self.preprocess_edge_var.set(0.700)
            self.preprocess_noise_var.set(1.000)
            self.internal_scale_var.set("2")
            self.global_epsilon_var.set("0.300")
            self.smooth_contours_var.set(False)
            self.smooth_strength_var.set("0.000")
            self.smart_smoothing_var.set(True)
            self.smart_corner_angle_var.set("42.000")
            self.smart_line_tolerance_var.set("0.850")
            self.smart_curve_strength_var.set("0.800")
            self.cleanup_mode_var.set("off")

        self.internal_scale_display_var.set(self._internal_scale_label(self.internal_scale_var.get()))
        try:
            self.cleanup_mode_display_var.set(self._cleanup_label(self.cleanup_mode_var.get()))
        except Exception:
            pass
        try:
            self.apply_global_epsilon_to_rows()
        except Exception:
            pass
        self.status_var.set(tr(f"status.startup_preset_{profile_key}"))

    def on_enter_step2(self) -> None:
        if self.vector_image_rgb is None:
            return
        if self.step2_auto_prompt_pending:
            self.step2_auto_prompt_pending = False
            use_auto = messagebox.askyesno(
                tr("msg.auto_expert_prompt_title"),
                tr("msg.auto_expert_prompt"),
                default=messagebox.NO,
                icon=messagebox.QUESTION,
            )
            if use_auto:
                self.auto_tune_expert_values_from_image()
        # Einmal sofort mit aktuellen Einstellungen berechnen.
        self.detect_and_preview_vector()

    def get_selected_dxf_version(self) -> str:
        return _dxf_version_from_choice(self.dxf_version_var.get())

    def on_dxf_compatibility_changed(self) -> None:
        profile = self.dxf_compatibility_var.get()
        version, info = DXF_COMPATIBILITY_PRESETS.get(
            profile,
            DXF_COMPATIBILITY_PRESETS["default"],
        )
        if profile != "manual":
            self.dxf_version_var.set(_dxf_choice_for_version(version))
        self.dxf_compatibility_display_var.set(self._compat_label(profile))
        self.dxf_compatibility_info_var.set(f"{info}  Aktuell: DXF {self.get_selected_dxf_version()}")
        self._save_user_config()

    def on_dxf_compatibility_display_changed(self) -> None:
        selected = self.dxf_compatibility_display_var.get()
        for key in DXF_COMPATIBILITY_KEYS:
            if selected == self._compat_label(key):
                self.dxf_compatibility_var.set(key)
                break
        self.on_dxf_compatibility_changed()

    def on_dxf_version_changed(self) -> None:
        # Wenn der Benutzer das Format selbst ändert, soll sichtbar sein,
        # dass nicht mehr strikt das Programmprofil gilt.
        selected_version = self.get_selected_dxf_version()
        current_profile = self.dxf_compatibility_var.get()
        expected_version = DXF_COMPATIBILITY_PRESETS.get(current_profile, ("", ""))[0]
        if current_profile != "manual" and selected_version != expected_version:
            self.dxf_compatibility_var.set("manual")
            self.dxf_compatibility_display_var.set(self._compat_label("manual"))
        self.dxf_compatibility_info_var.set(
            f"Manuelles DXF-Format gewählt: {selected_version}. "
            "Bei Grafikprogrammen zuerst R2000 probieren."
        )
        self._save_user_config()

    def on_vector_mode_display_changed(self) -> None:
        selected = self.vector_mode_display_var.get()
        for key in VECTOR_MODE_KEYS:
            if selected == self._mode_label(key):
                self.vector_mode_var.set(key)
                break

    def on_preview_mode_display_changed(self) -> None:
        selected = self.preview_mode_display_var.get()
        for key in PREVIEW_MODE_KEYS:
            if selected == self._preview_label(key):
                self.preview_mode_var.set(key)
                break
        self.render_vector_preview()

    def on_cleanup_mode_display_changed(self) -> None:
        selected = self.cleanup_mode_display_var.get()
        for key in CLEANUP_MODE_KEYS:
            if selected == self._cleanup_label(key):
                self.cleanup_mode_var.set(key)
                break

    def on_internal_scale_display_changed(self) -> None:
        selected = self.internal_scale_display_var.get()
        for key in INTERNAL_SCALE_KEYS:
            if selected == self._internal_scale_label(key):
                self.internal_scale_var.set(key)
                break

    def _update_step2_zoom_preset_display(self, zoom: float) -> None:
        try:
            self.step2_zoom_percent_var.set(str(int(round(float(zoom) * 100))))
        except Exception:
            pass
        presets = [0.25, 0.50, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 8.0]
        for preset in presets:
            if abs(float(zoom) - preset) < 0.01:
                self.step2_zoom_preset_var.set(f"{int(round(preset * 100))}%")
                return
        self.step2_zoom_preset_var.set(f"{float(zoom) * 100:.0f}%")

    def set_step2_zoom_percent(self, percent: float) -> None:
        # Zentrale Zoom-Setzung für Schritt 2. Alle Bedienwege landen hier,
        # damit Prozentfeld, interne Zoomvariable und beide Vorschauflächen synchron bleiben.
        try:
            value = float(percent)
        except Exception:
            return
        value = max(25.0, min(800.0, value))
        # Feste 5-Prozent-Schritte vermeiden unnötig viele Zwischen-Renderings.
        value = round(value / 5.0) * 5.0
        zoom = value / 100.0
        self.step2_zoom_percent_var.set(str(int(round(value))))
        self.step2_shared_zoom_var.set(round(zoom, 2))
        self.on_step2_shared_zoom_changed(str(zoom))

    def step2_zoom_step(self, delta_percent: float) -> None:
        # Plus/Minus-Zoom in festen 5-%-Schritten. Das ist absichtlich grober
        # als Mausrad oder Slider und verhindert Render-Stürme bei großen Bildern.
        try:
            current = float(str(self.step2_zoom_percent_var.get()).replace(",", "."))
        except Exception:
            try:
                current = float(self.step2_shared_zoom_var.get()) * 100.0
            except Exception:
                current = 100.0
        self.set_step2_zoom_percent(current + float(delta_percent))

    def on_step2_zoom_spin_changed(self) -> None:
        try:
            percent = float(str(self.step2_zoom_percent_var.get()).replace(",", "."))
        except Exception:
            return
        self.set_step2_zoom_percent(percent)

    def on_step2_zoom_preset_changed(self) -> None:
        text = str(self.step2_zoom_preset_var.get()).strip().replace("%", "")
        try:
            percent = float(text.replace(",", "."))
        except Exception:
            return
        self.set_step2_zoom_percent(percent)

    def on_step2_shared_zoom_changed(self, value: str) -> None:
        if self._syncing_step2_zoom:
            return
        try:
            zoom = float(str(value).replace(",", "."))
        except Exception:
            return
        self._syncing_step2_zoom = True
        try:
            if hasattr(self, "step2_original_canvas"):
                self.step2_original_canvas.set_zoom(zoom)
            if hasattr(self, "step2_vector_canvas"):
                self.step2_vector_canvas.set_zoom(zoom)
            self._update_step2_zoom_preset_display(zoom)
        finally:
            self._syncing_step2_zoom = False

    def on_step2_canvas_zoom_changed(self, zoom: float) -> None:
        if self._syncing_step2_zoom:
            return
        self._syncing_step2_zoom = True
        try:
            rounded_zoom = round(float(zoom), 2)
            self.step2_shared_zoom_var.set(rounded_zoom)
            self._update_step2_zoom_preset_display(rounded_zoom)
            # Beide Vorschauen synchron halten, falls ein Canvas-Zoom extern gesetzt wird.
            if hasattr(self, "step2_original_canvas"):
                self.step2_original_canvas.set_zoom(rounded_zoom)
            if hasattr(self, "step2_vector_canvas"):
                self.step2_vector_canvas.set_zoom(rounded_zoom)
        finally:
            self._syncing_step2_zoom = False

    def on_step2_canvas_view_changed(self, source_canvas) -> None:
        if self._syncing_step2_view or not self.step2_sync_view_var.get():
            return
        try:
            self._syncing_step2_view = True
            target_canvas = self.step2_vector_canvas if source_canvas is self.step2_original_canvas else self.step2_original_canvas
            target_canvas.zoom = float(source_canvas.zoom)
            target_canvas.offset_x = float(source_canvas.offset_x)
            target_canvas.offset_y = float(source_canvas.offset_y)
            target_canvas.render()
        except Exception:
            pass
        finally:
            self._syncing_step2_view = False

    def sync_step2_canvas_views_now(self) -> None:
        if getattr(self, "step2_sync_view_var", None) is not None and self.step2_sync_view_var.get():
            self.on_step2_canvas_view_changed(self.step2_original_canvas)

    def on_ui_theme_display_changed(self) -> None:
        selected = self.ui_theme_display_var.get()
        for key in UI_THEME_KEYS:
            if selected == self._ui_theme_label(key):
                self.ui_theme_key_var.set(key)
                break
        self.apply_ui_theme()
        self._save_user_config()

    def on_ui_complexity_display_changed(self) -> None:
        self._suspend_live_preview = True
        try:
            selected = self.ui_complexity_display_var.get()
            for key in UI_COMPLEXITY_KEYS:
                if selected == self._ui_complexity_label(key):
                    self.ui_complexity_var.set(key)
                    break
            self.apply_ui_complexity_mode()
        finally:
            self._suspend_live_preview = False

    def on_motif_profile_display_changed(self) -> None:
        selected = self.motif_profile_display_var.get()
        selected_key = self.motif_profile_var.get()
        for key in MOTIF_PROFILE_KEYS:
            if selected == self._motif_profile_label(key):
                selected_key = key
                break
        previous_key = self.motif_profile_var.get()
        self.apply_motif_profile(selected_key)
        if self.vector_image_rgb is None or selected_key == previous_key:
            return
        if messagebox.askyesno(
            tr("msg.motif_recalculate_title"),
            tr("msg.motif_recalculate_body"),
            default=messagebox.YES,
            icon=messagebox.QUESTION,
        ):
            self.auto_tune_expert_values_from_image()
            self.detect_and_preview_vector()
        elif self.live_preview_var.get():
            self._schedule_live_preview_if_enabled()

    def set_ui_complexity_mode(self, key: str) -> None:
        if key not in UI_COMPLEXITY_KEYS:
            return
        self._suspend_live_preview = True
        try:
            self.ui_complexity_var.set(key)
            try:
                self.ui_complexity_display_var.set(self._ui_complexity_label(key))
            except Exception:
                pass
            self.apply_ui_complexity_mode()
        finally:
            self._suspend_live_preview = False

    def _refresh_complexity_buttons_style(self) -> None:
        if not hasattr(self, "simple_mode_btn") or not hasattr(self, "expert_mode_btn"):
            return
        dark = bool(self.dark_mode_var.get())
        active_bg = "#2563eb" if not dark else "#3b82f6"
        active_fg = "#ffffff"
        inactive_bg = "#e5e7eb" if not dark else "#374151"
        inactive_fg = "#111827" if not dark else "#f3f4f6"
        hover_active = "#1d4ed8" if not dark else "#60a5fa"
        hover_inactive = "#d1d5db" if not dark else "#4b5563"
        current = self.ui_complexity_var.get()
        for key, button in (("simple", self.simple_mode_btn), ("expert", self.expert_mode_btn)):
            selected = current == key
            button.configure(
                bg=active_bg if selected else inactive_bg,
                fg=active_fg if selected else inactive_fg,
                activebackground=hover_active if selected else hover_inactive,
                activeforeground=active_fg if selected else inactive_fg,
            )
        try:
            base = "#2b2b2b" if dark else "#f2f2f2"
            fg = "#d1d5db" if dark else "#4b5563"
            self.complexity_toggle_frame.configure(bg=base)
            for child in self.complexity_toggle_frame.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=base, fg=fg)
        except Exception:
            pass

    def apply_ui_complexity_mode(self) -> None:
        if not hasattr(self, "vector_options_frame"):
            return
        simple = self.ui_complexity_var.get() == "simple"
        # Einfache Ansicht: nur Kern-Parameter sichtbar, Rest in Expertenmodus.
        for child in self.vector_options_frame.winfo_children():
            info = child.grid_info()
            row = int(info.get("row", 0))
            if row in (17, 18, 30, 31):
                child.grid_remove()
                continue
            if simple:
                if row in (0, 1, 2, 3, 4, 9, 14):
                    child.grid()
                else:
                    child.grid_remove()
            else:
                child.grid()
        self._refresh_anchor_cleanup_controls()
        self._refresh_complexity_buttons_style()

    def _refresh_anchor_cleanup_controls(self) -> None:
        enabled = bool(self.remove_loose_points_var.get())
        state = "normal" if enabled else "disabled"
        for widget_name in ("anchor_distance_label", "anchor_distance_scale", "anchor_distance_spin"):
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            try:
                widget.configure(state=state)
            except Exception:
                pass

    def on_anchor_cleanup_toggle(self) -> None:
        self._refresh_anchor_cleanup_controls()
        self._update_cad_point_count()
        self._schedule_live_preview_if_enabled()

    def _apply_step1_scale_theme(self, base: str, text: str, dark: bool) -> None:
        trough = "#1f2937" if dark else "#d1d5db"
        active = "#374151" if dark else "#e5e7eb"
        for scale in self._step1_scales:
            try:
                scale.configure(
                    bg=base,
                    fg=text,
                    troughcolor=trough,
                    activebackground=active,
                    highlightbackground=base,
                    highlightcolor=base,
                )
            except Exception:
                pass

    def apply_ui_theme(self) -> None:
        dark = bool(self.dark_mode_var.get())
        ui_key = self.ui_theme_key_var.get()
        base = "#2b2b2b" if dark else "#f2f2f2"
        panel = "#353535" if dark else "#ffffff"
        text = "#f3f3f3" if dark else "#202020"
        muted = "#bcbcbc" if dark else "#666666"
        hover_fill = "#454545" if dark else "#e5e7eb"
        active_fill = "#4d4d4d" if dark else "#d1d5db"
        canvas_bg = "#232323" if dark else "#efefef"
        self.configure(bg=base)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self.style.configure(".", background=base, foreground=text)
        self.style.configure("TFrame", background=base)
        self.style.configure("TLabel", background=base, foreground=text)
        source_fg = "#111827" if not dark else "#e5e7eb"
        self.style.configure("Source.TLabel", background=base, foreground=source_fg)
        self.style.configure("TLabelframe", background=base, foreground=text)
        self.style.configure("TLabelframe.Label", background=base, foreground=text)
        self.style.configure("TCheckbutton", background=base, foreground=text)
        self.style.configure("TRadiobutton", background=base, foreground=text)
        self.style.configure("Live.TCheckbutton", background=base, foreground=text, font=("Segoe UI", 9, "bold"))
        # Hover/active fuer Dark/Light konsistent halten (kein hellgraues Standard-Hintergrund-Flackern).
        self.style.map(
            "TCheckbutton",
            background=[("active", base), ("selected", base)],
            foreground=[("active", text), ("selected", text)],
        )
        self.style.map(
            "TRadiobutton",
            background=[("active", base), ("selected", base)],
            foreground=[("active", text), ("selected", text)],
        )
        self.style.map(
            "Live.TCheckbutton",
            background=[("active", base), ("selected", base)],
            foreground=[("active", text), ("selected", text)],
        )
        self.style.configure("TNotebook", background=base)
        self.style.configure("TNotebook.Tab", background=panel, foreground=text, padding=(10, 4))
        self.style.map("TNotebook.Tab", background=[("selected", base)])
        try:
            self.style.layout("Step1Hidden.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
            self.style.layout("Step1Hidden.TNotebook.Tab", [])
            self.style.configure("Step1Hidden.TNotebook", background=base, borderwidth=0, tabmargins=(0, 0, 0, 0), padding=0)
            self.style.configure("Step1Hidden.TNotebook.Tab", padding=0)
        except Exception:
            pass
        self.style.configure("TEntry", fieldbackground=panel, foreground=text)
        self.style.configure("TSpinbox", fieldbackground=panel, foreground=text)
        self.style.configure("TButton", background=panel, foreground=text, padding=(8, 3))
        self.style.map(
            "TButton",
            background=[("active", hover_fill), ("pressed", active_fill)],
            foreground=[("active", text), ("pressed", text)],
        )
        self.style.configure("TCombobox", fieldbackground=panel, foreground=text)
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", panel)],
            foreground=[("readonly", text)],
            selectbackground=[("readonly", "#4c78a8" if dark else "#cfe3ff")],
            selectforeground=[("readonly", text)],
            background=[("readonly", panel)],
        )
        # Dropdown-Liste (Popdown) fuer Tk-Comboboxen besser lesbar machen.
        self.option_add("*TCombobox*Listbox.background", panel)
        self.option_add("*TCombobox*Listbox.foreground", text)
        self.option_add("*TCombobox*Listbox.selectBackground", "#4c78a8" if dark else "#cfe3ff")
        self.option_add("*TCombobox*Listbox.selectForeground", text)
        self.style.configure("Horizontal.TScale", background=base)
        self.style.configure("TProgressbar", background="#2d7ff9" if not dark else "#4ea1ff")
        self._apply_step1_scale_theme(base, text, dark)
        self._refresh_complexity_buttons_style()
        if ui_key == "modern":
            back_bg = "#f97316" if not dark else "#ff8f3f"
            next_bg = "#2563eb" if not dark else "#3b82f6"
            step_bg = "#2563eb" if not dark else "#3b82f6"
            btn_relief = "raised"
            btn_bd = 1
            btn_padx = 14
            btn_pady = 5
            compact_font = ("Segoe UI", 9, "bold")
            frame_pad = (8, 6, 8, 6)
            show_top_toolbar = False
        else:
            # Werkzeug-Optik wie klassische DTP/CAD-Programme: neutral, kompakt, flacher.
            back_bg = "#6f6f6f" if not dark else "#575757"
            next_bg = "#4f6278" if not dark else "#475b73"
            step_bg = "#4f6278" if not dark else "#475b73"
            btn_relief = "flat"
            btn_bd = 1
            btn_padx = 10
            btn_pady = 3
            compact_font = ("Segoe UI", 8, "bold")
            frame_pad = (6, 4, 6, 4)
            show_top_toolbar = False
        self.back_btn.configure(bg=back_bg, activebackground=back_bg, fg="white", activeforeground="white", relief=btn_relief, bd=btn_bd, padx=btn_padx, pady=btn_pady)
        self.next_btn.configure(bg=next_bg, activebackground=next_bg, fg="white", activeforeground="white", relief=btn_relief, bd=btn_bd, padx=btn_padx, pady=btn_pady)
        # Schritt-1-Abschluss bewusst grün halten: die Theme-Logik darf diesen Button
        # nicht wieder blau/grau überschreiben.
        self.step1_next_action_btn.configure(
            bg=ACTION_GREEN,
            activebackground=ACTION_GREEN_ACTIVE,
            fg="white",
            activeforeground="white",
            relief=btn_relief,
            bd=btn_bd,
            # Unten in Schritt 1 soll dieser Button exakt so groß wirken wie die drei Nachbarbuttons.
            # Deshalb hier bewusst NICHT die kompaktere Theme-Padding-Variante verwenden.
            padx=14,
            pady=6,
            font=("Segoe UI", 9, "bold"),
        )
        if hasattr(self, "step2_quick_preview_btn"):
            try:
                self.step2_quick_preview_btn.configure(
                    bg="#15803d",
                    fg="white",
                    activebackground="#166534",
                    activeforeground="white",
                    highlightbackground=base,
                )
            except Exception:
                pass
        if hasattr(self, "detect_action_btn"):
            self.detect_action_btn.configure(activeforeground="white")
        if hasattr(self, "cad_cleanup_action_btn"):
            self.cad_cleanup_action_btn.configure(activeforeground="white")
        if hasattr(self, "export_action_btn"):
            self.export_action_btn.configure(activeforeground="white")
        if hasattr(self, "scale_export_action_btn"):
            self.scale_export_action_btn.configure(activeforeground="white")
        if hasattr(self, "auto_action_btn"):
            self.auto_action_btn.configure(activeforeground="white")
        if hasattr(self, "step2_back_action_btn"):
            self.step2_back_action_btn.configure(
                bg=back_bg,
                activebackground=back_bg,
                fg="white",
                activeforeground="white",
                relief=btn_relief,
                bd=btn_bd,
                padx=btn_padx,
                pady=btn_pady,
                font=compact_font,
            )
        if hasattr(self, "step2_actions_frame"):
            try:
                self.step2_actions_frame.configure(padding=frame_pad)
            except Exception:
                pass
        if hasattr(self, "step2_colors_bar"):
            try:
                self.step2_colors_bar.configure(padding=frame_pad)
            except Exception:
                pass
        if hasattr(self, "step2_workflow_bar"):
            try:
                self.step2_workflow_bar.configure(padding=frame_pad)
            except Exception:
                pass
        if hasattr(self, "step2_top_toolbar"):
            if show_top_toolbar:
                self.step2_top_toolbar.grid()
            else:
                self.step2_top_toolbar.grid_remove()
        # Widgets mit hart kodierten dunklen Textfarben (z.B. "#555") fuer Darkmode nachziehen.
        def _retint(widget: tk.Widget) -> None:
            try:
                if isinstance(widget, ttk.Label):
                    fg = str(widget.cget("foreground") or "").strip().lower()
                    if fg in {"#555", "#555555", "#666", "#666666", "#777", "#777777", "black", "#000", "#000000"}:
                        widget.configure(foreground=muted)
                elif isinstance(widget, tk.Canvas):
                    # Scroll-Canvases im Darkmode nicht hellgrau lassen.
                    widget.configure(bg=base)
                elif isinstance(widget, ttk.Button):
                    fg = str(widget.cget("foreground") or "").strip().lower()
                    if fg in {"", "black", "#000", "#000000"}:
                        widget.configure(foreground=text)
            except Exception:
                pass
            for child in widget.winfo_children():
                _retint(child)
        _retint(self)
        try:
            self.show_step(self.current_step)
        except Exception:
            pass
        for c in (
            getattr(self, "step1_original_canvas", None),
            getattr(self, "step1_edited_canvas", None),
            getattr(self, "step2_original_canvas", None),
            getattr(self, "step2_vector_canvas", None),
        ):
            if c is None:
                continue
            try:
                c.canvas.configure(bg=canvas_bg, highlightbackground=muted)
                c.render()
            except Exception:
                pass

    def apply_global_epsilon_to_rows(self) -> None:
        try:
            value = f"{max(0.0, float(str(self.global_epsilon_var.get()).replace(',', '.'))):.2f}"
        except Exception:
            value = str(self.global_epsilon_var.get()).replace(",", ".")
        for row in self.vector_rows:
            row.epsilon_var.set(value)
        self.status_var.set(tr("status.epsilon_applied_all", value=value))

    def apply_global_tolerance_to_rows(self) -> None:
        text = str(self.global_tolerance_var.get()).replace(",", ".")
        try:
            value = int(round(float(text)))
        except Exception:
            value = 12
        value = max(0, min(255, value))
        for row in self.vector_rows:
            row.tolerance_var.set(str(value))
        self.global_tolerance_var.set(str(value))
        self.status_var.set(tr("status.tolerance_applied_all", value=value))

    def on_global_tolerance_slider_changed(self, value: str) -> None:
        self._set_numeric_var(self.global_tolerance_var, value, 0)
        self.apply_global_tolerance_to_rows()

    def apply_high_detail_mode(self) -> None:
        if not self.vector_rows:
            return

        # Maximale Detailtreue: möglichst wenig Geometrie-Verlust.
        self.closed_paths_only_var.set(False)
        self.remove_loose_points_var.set(False)
        self.anchor_neighbor_distance_var.set("0.50")
        self.preprocess_vector_var.set(True)
        self.preprocess_blur_var.set(0.0)
        self.preprocess_edge_var.set(0.0)
        self.preprocess_noise_var.set(0.0)
        self.internal_scale_var.set("3")
        self.internal_scale_display_var.set(self._internal_scale_label("3"))
        self.smooth_contours_var.set(False)
        self.smart_smoothing_var.set(False)
        self.unique_cad_lines_var.set(False)
        self.cleanup_mode_var.set("off")
        try:
            self.cleanup_mode_display_var.set(self._cleanup_label("off"))
        except Exception:
            pass

        self.global_epsilon_var.set("0.030")
        self.global_tolerance_var.set("200")
        self.hole_scale_var.set("1.000")
        self.bridge_tabs_var.set(False)
        self.bridge_width_mm_var.set("1.000")
        self.bridge_width_percent_var.set("0.000")
        self.bridge_count_var.set("2.000")
        self.min_object_area_mm2_var.set("0")
        self.min_object_percent_var.set("0,00")

        self.apply_global_epsilon_to_rows()
        self.apply_global_tolerance_to_rows()

        for row in self.vector_rows:
            rgb_text = str(row.rgb_var.get()).strip().replace(" ", "")
            row.min_area_var.set("0")
            row.epsilon_var.set("0.030")
            if rgb_text in ("0,0,0", "0;0;0"):
                row.tolerance_var.set("205")
                row.export_var.set(True)
            elif rgb_text in ("255,255,255", "255;255;255"):
                row.tolerance_var.set("140")
            else:
                row.tolerance_var.set("170")

        self.status_var.set(tr("status.high_detail_applied"))
        if self.vector_image_rgb is not None:
            if self.live_preview_var.get():
                self._schedule_live_preview_if_enabled()

    def _set_numeric_var(self, variable: tk.Variable, value: str, decimals: int = 3) -> None:
        try:
            number = float(str(value).replace(",", "."))
        except Exception:
            return
        if decimals <= 0:
            text = str(int(round(number)))
        else:
            text = f"{number:.{decimals}f}".rstrip("0").rstrip(".")
        variable.set(text)

    def show_problem_image_hint(self, reason: str = "") -> None:
        if hasattr(self, "problem_hint_frame"):
            self.problem_hint_frame.grid()
        if reason:
            self.status_var.set(reason)

    def hide_problem_image_hint(self) -> None:
        if hasattr(self, "problem_hint_frame"):
            self.problem_hint_frame.grid_remove()

    def open_manual_colors_from_hint(self) -> None:
        # Wenn keine der automatischen Heuristiken sauber greift, bleibt als
        # sichere Fallback-Empfehlung die manuelle Bearbeitung.
        try:
            self.step1_notebook.select(self.manual_tab)
        except Exception:
            pass
        if not self.manual_rows:
            self.add_manual_row()
        self.update_step1_picker_cursor()
        self.status_var.set(tr("status.problem_hint_manual_opened"))

    def apply_high_tolerance_manual_colors(self) -> None:
        if not self.manual_rows:
            self.add_manual_row()
        for row in self.manual_rows:
            row.tolerance_var.set("180")
        self.open_manual_colors_from_hint()
        self.schedule_step1_preview()
        self.status_var.set(tr("status.problem_hint_high_tolerance"))

    def _format_progress_status(self, value: float, status: str) -> str:
        return tr("status.progress_percent", percent=int(round(max(0.0, min(100.0, value)))), status=status)

    def set_progress(self, value: float, status: Optional[str] = None) -> None:
        value = max(0.0, min(100.0, value))
        self.progress_var.set(value)
        if status is not None:
            text = self._format_progress_status(value, status)
            self.status_var.set(text)
            if self._busy_status_var is not None:
                self._busy_status_var.set(text)
        if self._busy_progress_var is not None:
            self._busy_progress_var.set(value)
        self._resize_busy_dialog_to_content()
        self.update_idletasks()

    def _busy_dialog_geometry(self, requested_height: int) -> tuple[int, int, int, int]:
        """Konstante, breite Fortschrittsfenster-Geometrie ohne abgeschnittenen Text."""
        try:
            screen_width = max(640, int(self.winfo_screenwidth()))
            screen_height = max(480, int(self.winfo_screenheight()))
            app_width = max(640, int(self.winfo_width()))
            width = min(max(620, min(700, app_width - 120)), screen_width - 80)
            height = min(max(105, int(requested_height)), screen_height - 120)
            x = int(self.winfo_rootx() + max(40, (app_width - width) // 2))
            y = int(self.winfo_rooty() + max(60, (int(self.winfo_height()) - height) // 2))
            x = max(20, min(x, screen_width - width - 20))
            y = max(20, min(y, screen_height - height - 40))
            return width, height, x, y
        except Exception:
            return 640, max(120, int(requested_height)), 120, 120

    def _resize_busy_dialog_to_content(self) -> None:
        dialog = getattr(self, "_busy_dialog", None)
        if dialog is None:
            return
        try:
            width = int(getattr(self, "_busy_dialog_width", 640))
            dialog.update_idletasks()
            requested_height = int(dialog.winfo_reqheight()) + 2
            max_height = max(220, int(dialog.winfo_screenheight() * 0.55))
            height = min(max(105, requested_height), max_height)
            # X/Y beibehalten, damit das Fenster nicht springt. Nur Breite/Hoehe werden stabilisiert.
            x = max(20, int(dialog.winfo_x()))
            y = max(20, int(dialog.winfo_y()))
            dialog.geometry(f"{width}x{height}+{x}+{y}")
            dialog.minsize(width, height)
        except Exception:
            pass

    def show_busy_dialog(self, title: str = "Bitte warten", message: str = "Bild wird analysiert...", cancellable: bool = False) -> None:
        """Blockiert kurz die Oberfläche, damit man während Auto-Analyse nicht versehentlich klickt."""
        try:
            self.close_busy_dialog()
        except Exception:
            pass
        self._busy_cancel_requested = False
        self.progress_var.set(0.0)
        self.status_var.set(self._format_progress_status(0.0, message))
        try:
            dialog = tk.Toplevel(self)
            self._busy_dialog = dialog
            dialog.title(title)
            dialog.transient(self)
            dialog.resizable(False, False)
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)
            dialog.columnconfigure(0, weight=1)
            dialog.rowconfigure(0, weight=1)
            self._busy_progress_var = tk.DoubleVar(value=float(self.progress_var.get()))
            self._busy_status_var = tk.StringVar(value=self._format_progress_status(float(self.progress_var.get()), message))
            frame = ttk.Frame(dialog, padding=(18, 12, 18, 12))
            frame.grid(row=0, column=0, sticky="nsew")
            frame.columnconfigure(0, weight=1)
            width, _height, x, y = self._busy_dialog_geometry(130 if not cancellable else 165)
            self._busy_dialog_width = width
            wrap = max(460, width - 76)
            ttk.Label(frame, textvariable=self._busy_status_var, justify="left", wraplength=wrap).grid(row=0, column=0, sticky="ew")
            bar = ttk.Progressbar(frame, mode="determinate", variable=self._busy_progress_var, maximum=100, length=max(420, width - 90))
            bar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
            if cancellable:
                ttk.Button(frame, text=tr("button.cancel"), command=self.request_busy_cancel).grid(row=2, column=0, sticky="e", pady=(10, 0))
            self.update_idletasks()
            dialog.update_idletasks()
            requested_height = int(dialog.winfo_reqheight()) + 2
            width, height, x, y = self._busy_dialog_geometry(requested_height)
            self._busy_dialog_width = width
            dialog.geometry(f"{width}x{height}+{x}+{y}")
            dialog.minsize(width, height)
            dialog.grab_set()
            try:
                dialog.lift()
                dialog.focus_force()
                dialog.attributes("-topmost", True)
                dialog.after(250, lambda: dialog.attributes("-topmost", False))
            except Exception:
                pass
            try:
                self.configure(cursor="watch")
            except Exception:
                pass
            dialog.update_idletasks()
            dialog.update()
        except Exception:
            self._busy_dialog = None
            self._busy_progress_var = None
            self._busy_status_var = None
            self.status_var.set(message)
            self.update_idletasks()

    def request_busy_cancel(self) -> None:
        self._busy_cancel_requested = True
        self.status_var.set(tr("status.analysis_cancel_requested"))

    def _raise_if_cancel_requested(self) -> None:
        if getattr(self, "_busy_cancel_requested", False):
            raise InterruptedError(tr("status.analysis_cancelled"))

    def close_busy_dialog(self) -> None:
        dialog = getattr(self, "_busy_dialog", None)
        self._busy_dialog = None
        self._busy_progress_var = None
        self._busy_status_var = None
        self._busy_cancel_requested = False
        try:
            self.configure(cursor="")
        except Exception:
            pass
        if dialog is None:
            return
        try:
            dialog.grab_release()
        except Exception:
            pass
        try:
            dialog.destroy()
        except Exception:
            pass
        self.update_idletasks()

    def _image_stats_for_step1_recommendation(self) -> Optional[dict[str, float]]:
        if self.original_image is None:
            return None
        original = self.original_image.convert("RGBA")
        image = original
        max_dim = max(image.size)
        analysis_scale = 1.0
        if max_dim > 700:
            analysis_scale = 700.0 / float(max_dim)
            image = image.resize(
                (max(1, int(image.width * analysis_scale)), max(1, int(image.height * analysis_scale))),
                Image.Resampling.LANCZOS,
            )
        rgba = np.array(image, dtype=np.uint8)
        rgb = rgba[:, :, :3].astype(np.float32)
        alpha = rgba[:, :, 3] > 0
        if not np.any(alpha):
            return None
        gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        rgb_norm = np.clip(rgb / 255.0, 0.0, 1.0)
        sat = np.max(rgb_norm, axis=2) - np.min(rgb_norm, axis=2)
        gvals = gray[alpha]
        channel_spread_full = np.max(rgb, axis=2) - np.min(rgb, axis=2)
        channel_spread = channel_spread_full[alpha]
        p5 = float(np.percentile(gvals, 5))
        p95 = float(np.percentile(gvals, 95))
        dyn = p95 - p5
        near_bw = float((channel_spread <= 14).mean())
        near_black = float((gvals <= 45).mean())
        near_white = float((gvals >= 225).mean())
        sat_values = sat[alpha]
        sat_mean = float(sat_values.mean())
        sat_p95 = float(np.percentile(sat_values, 95))
        sat_moderate = float((sat_values >= 0.10).mean())
        sat_strong = float((sat_values >= 0.18).mean())
        sat_clear = float((sat_values >= 0.35).mean())
        alpha_pixels = max(1.0, float(alpha.sum()))
        foreground_luma_limit = max(0.0, min(245.0, p95 - max(10.0, dyn * 0.06)))
        colored_ink_mask = (
            (sat >= 0.075)
            & (gray <= foreground_luma_limit)
            & (channel_spread_full >= 10.0)
            & alpha
        )
        colored_ink_coverage = float(colored_ink_mask.sum()) / alpha_pixels
        colored_component_count = 0
        colored_largest_component = 0.0
        colored_largest_bbox_span = 0.0
        if np.any(colored_ink_mask):
            component_mask = (colored_ink_mask.astype(np.uint8) * 255)
            num_labels, _labels, component_stats, _centroids = vector.cv2.connectedComponentsWithStats(
                component_mask,
                connectivity=8,
            )
            min_component_area = max(8, int(round(alpha_pixels * 0.00015)))
            component_infos: list[tuple[int, float]] = []
            for label_id in range(1, num_labels):
                area = int(component_stats[label_id, vector.cv2.CC_STAT_AREA])
                if area >= min_component_area:
                    width = int(component_stats[label_id, vector.cv2.CC_STAT_WIDTH])
                    height = int(component_stats[label_id, vector.cv2.CC_STAT_HEIGHT])
                    span = max(
                        float(width) / max(1.0, float(gray.shape[1])),
                        float(height) / max(1.0, float(gray.shape[0])),
                    )
                    component_infos.append((area, span))
            colored_component_count = len(component_infos)
            if component_infos:
                largest_area, largest_span = max(component_infos, key=lambda item: item[0])
                colored_largest_component = float(largest_area) / alpha_pixels
                colored_largest_bbox_span = float(largest_span)
        if gray.shape[0] > 1 and gray.shape[1] > 1:
            grad_x = np.abs(np.diff(gray, axis=1))
            grad_y = np.abs(np.diff(gray, axis=0))
            edge_density = float(((grad_x > 14).mean() + (grad_y > 14).mean()) * 0.5)
        else:
            edge_density = 0.0

        gray_img = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8), "L")

        # Dynamische Logo-Masken-Suche:
        # Wir testen reale UI-Radiuswerte, rechnen sie für das verkleinerte
        # Analysebild um und bewerten, wie plausibel die erkannte Maskenfläche ist.
        # Damit ist 10/50 nur ein typischer Startanker, aber kein fixer Zwang.
        ui_blur_candidates = (15, 21, 31, 41, 50, 61, 81, 101, 121)
        threshold_candidates = (5, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 34)
        coarse_radius = max(1.0, 50.0 * analysis_scale)
        coarse_bg = np.array(gray_img.filter(ImageFilter.GaussianBlur(radius=coarse_radius)), dtype=np.int16)
        coarse_diff = coarse_bg - gray.astype(np.int16)
        coarse_coverage = float(((coarse_diff >= 6) & alpha).mean()) * 100.0
        # Zielabdeckung aus dem Bild ableiten. Bei hellgrauen Logos liegt sie oft
        # zwischen 8 und 45 %, bei sehr feinen Logos darunter.
        target_coverage = max(3.0, min(55.0, coarse_coverage))
        if target_coverage < 5.0 and dyn > 25:
            target_coverage = 8.0

        best_blur = 50
        best_threshold = 10
        best_coverage = 0.0
        best_score = 10**9
        best_foreground_edge = 0.0
        for ui_blur in ui_blur_candidates:
            work_radius = max(1.0, float(ui_blur) * analysis_scale)
            bg = np.array(gray_img.filter(ImageFilter.GaussianBlur(radius=work_radius)), dtype=np.int16)
            diff = bg - gray.astype(np.int16)
            for threshold in threshold_candidates:
                mask = (diff >= threshold) & alpha
                coverage = float(mask.mean()) * 100.0
                if coverage < 0.5 or coverage > 75.0:
                    continue
                if gray.shape[0] > 1 and gray.shape[1] > 1 and np.any(mask):
                    mx = np.abs(np.diff(mask.astype(np.uint8), axis=1)).mean()
                    my = np.abs(np.diff(mask.astype(np.uint8), axis=0)).mean()
                    foreground_edge = float((mx + my) * 0.5)
                else:
                    foreground_edge = 0.0
                # Nähe zur aus dem Bild abgeleiteten Zielabdeckung, plus leichter
                # Bias zu moderatem Radius und niedriger Schwelle bei hellgrauen Logos.
                score = (
                    abs(coverage - target_coverage)
                    + abs(float(ui_blur) - 50.0) * 0.025
                    + abs(float(threshold) - 10.0) * 0.12
                    - min(1.5, foreground_edge * 18.0)
                )
                if score < best_score:
                    best_score = score
                    best_blur = int(ui_blur)
                    best_threshold = int(threshold)
                    best_coverage = coverage
                    best_foreground_edge = foreground_edge

        return {
            "p5": p5,
            "p95": p95,
            "dynamic": dyn,
            "near_bw": near_bw,
            "near_black": near_black,
            "near_white": near_white,
            "sat_mean": sat_mean,
            "sat_p95": sat_p95,
            "sat_moderate": sat_moderate,
            "sat_strong": sat_strong,
            "sat_clear": sat_clear,
            "colored_ink_coverage": colored_ink_coverage,
            "colored_component_count": float(colored_component_count),
            "colored_largest_component": colored_largest_component,
            "colored_largest_bbox_span": colored_largest_bbox_span,
            "edge_density": edge_density,
            "mask_blur": float(best_blur),
            "mask_threshold": float(best_threshold),
            "mask_coverage": float(best_coverage),
            "mask_target_coverage": float(target_coverage),
            "mask_score": float(best_score),
            "mask_edge": float(best_foreground_edge),
        }

    def _image_has_small_color_accents(self, stats: Optional[dict[str, float]] = None) -> bool:
        """Erkennt kleine, echte Farbakzente in sonst CAD-typischen Logos."""
        if stats is None:
            stats = self._image_stats_for_step1_recommendation()
        if not stats:
            return False
        coverage = float(stats.get("colored_ink_coverage", 0.0) or 0.0)
        count = int(round(float(stats.get("colored_component_count", 0.0) or 0.0)))
        largest = float(stats.get("colored_largest_component", 0.0) or 0.0)
        largest_span = float(stats.get("colored_largest_bbox_span", 0.0) or 0.0)
        sat_clear = float(stats.get("sat_clear", 0.0) or 0.0)
        return bool(
            sat_clear >= 0.0015
            and coverage >= 0.00015
            and coverage <= 0.065
            and count >= 1
            and largest <= 0.018
            and largest_span <= 0.11
        )

    def recommend_step1_mode_from_image(self, force: bool = False) -> None:
        # Diese Routine entscheidet, welcher Schritt-1-Modus aus Sicht des
        # Programms am sinnvollsten ist. Die Entscheidung basiert nicht nur auf
        # einer einzelnen Kennzahl, sondern auf mehreren Bildmerkmalen wie
        # Schwarz/Weiß-Anteil, echter Farbstruktur, lokaler Kontrastmaske und
        # dem Scan-/Rausch-Eindruck der Vorlage.
        if self.original_image is None:
            return
        current_key = str(self.current_path) if self.current_path else f"image-{id(self.original_image)}"
        if not force and self._step1_recommendation_shown_for == current_key:
            return
        self._step1_recommendation_shown_for = current_key
        stats = self._image_stats_for_step1_recommendation()
        if not stats:
            try:
                self.step1_notebook.select(self.manual_tab)
            except Exception:
                pass
            return

        structured_color = (
            stats.get("colored_component_count", 0.0) >= 1.0
            and stats.get("colored_ink_coverage", 0.0) >= 0.0025
            and (
                stats.get("colored_largest_component", 0.0) >= 0.0015
                or stats.get("colored_largest_bbox_span", 0.0) >= 0.08
            )
        )
        color_like = (
            stats["sat_mean"] >= 0.08
            or stats["sat_p95"] >= 0.12
            or stats.get("sat_moderate", 0.0) >= 0.020
            or stats.get("sat_strong", 0.0) >= 0.025
            or stats.get("sat_clear", 0.0) >= 0.010
            or structured_color
        )
        has_relevant_color = (
            structured_color
            or (
                stats["sat_p95"] >= 0.12
                and (
                    stats.get("sat_moderate", 0.0) >= 0.012
                    or stats.get("sat_strong", 0.0) >= 0.006
                    or stats.get("sat_clear", 0.0) >= 0.003
                )
            )
        )
        mask_like = (
            stats["near_bw"] >= 0.72
            and stats["sat_mean"] <= 0.070
            and not has_relevant_color
            and 18.0 <= stats["dynamic"] <= 155.0
            and stats["near_black"] < 0.10
            and 1.0 <= stats["mask_coverage"] <= 65.0
        )
        bw_lineart_like = (
            stats["near_bw"] >= 0.88
            and not has_relevant_color
            and stats["dynamic"] >= 130.0
            and stats["near_black"] >= 0.01
            and stats["near_white"] >= 0.30
        )
        if bw_lineart_like:
            msg = tr("msg.step1_recommend_existing_bw")
            if messagebox.askyesno(tr("msg.perfect_bw_title"), msg, default=messagebox.YES, icon=messagebox.QUESTION):
                self.use_existing_step1_image_preview()
                self.status_var.set(tr("status.existing_image_used"))
            else:
                try:
                    self.step1_notebook.select(self.manual_tab)
                except Exception:
                    pass
                self.status_var.set(tr("status.existing_image_skipped"))
            return

        try:
            photo_scan_analysis = recolor.RecolorApp.analyze_photo_scan_logo_problem(self.original_image)
        except Exception:
            photo_scan_analysis = None

        small_accents = self._image_has_small_color_accents(stats)
        color_complexity = float(getattr(photo_scan_analysis, "color_complexity", 0.0) or 0.0) if photo_scan_analysis else 0.0
        photo_score = int(getattr(photo_scan_analysis, "score", 0) or 0) if photo_scan_analysis else 0
        badge_bw_structure = (
            stats["near_black"] >= 0.045
            and stats["near_white"] >= 0.18
            and stats["dynamic"] >= 90.0
            and stats.get("edge_density", 0.0) >= 0.018
        )
        flat_technical_color = (
            color_like
            and color_complexity > 0.0
            and color_complexity <= 26.0
            and stats.get("edge_density", 0.0) < 0.070
            and not badge_bw_structure
            and not small_accents
        )
        cad_bw_preferred = (
            color_like
            and self.motif_profile_var.get() in {"logo", "mixed"}
            and not flat_technical_color
            and (
                photo_score >= 2
                or color_complexity >= 42.0
                or badge_bw_structure
                or (stats["near_black"] >= 0.035 and stats["near_white"] >= 0.18 and stats["dynamic"] >= 95.0)
                or small_accents
            )
        )
        # Priorität für die Vektorisierung: so wenig Farben wie möglich.
        # Für Logo/CAD/Mixed-Motive ist ein kontrastreiches Schwarz/Weiß- oder
        # Schwarz/Weiß/Grau-Ergebnis fast immer stabiler als viele technische
        # Zielfarben. Deshalb wird die Farbinformation hier nicht als Grund
        # verwendet, um direkt in den Farben-Umfärben-Modus zu wechseln.
        minimal_color_priority = self.motif_profile_var.get() in {"logo", "mixed"}
        mask_coverage = float(stats.get("mask_coverage", 0.0) or 0.0)
        mask_candidate = (
            0.50 <= mask_coverage <= 88.0
            and stats["dynamic"] >= 35.0
            and (
                stats["near_bw"] >= 0.42
                or badge_bw_structure
                or structured_color
                or color_like
                or stats.get("edge_density", 0.0) >= 0.010
            )
        )
        serious_scan_problem = bool(
            photo_scan_analysis
            and (
                photo_scan_analysis.score >= 7
                or photo_scan_analysis.background_noise >= 10.0
                or photo_scan_analysis.small_specks >= 900
            )
        )
        # Primär: Logo-Maske. Mehrere Farben verhindern die Logo-Maske nicht,
        # weil die spätere Vektorisierung bewusst möglichst wenige Farben nutzen soll.
        logo_mask_preferred = bool(
            minimal_color_priority
            and mask_candidate
            and not serious_scan_problem
        )
        # Sekundär: Foto-Scan S/W. Dieser Modus greift erst, wenn die Logo-Maske
        # nicht ausreichend plausibel ist und echte Scan-/Rauschprobleme vorliegen.
        photo_scan_preferred = bool(
            photo_scan_analysis
            and not logo_mask_preferred
            and (
                photo_scan_analysis.score >= 5
                or photo_scan_analysis.background_noise >= 6.0
                or photo_scan_analysis.small_specks >= 350
                or photo_scan_analysis.edge_fray >= 0.050
                or (
                    photo_scan_analysis.score >= 4
                    and color_like
                    and not badge_bw_structure
                    and not flat_technical_color
                )
            )
        )
        # Tertiär: Farben umfärben. Für Logo/Mixed wird dieser Pfad nur noch als
        # Notlösung verwendet, wenn kein brauchbarer Schwarz/Weiß-Kandidat vorliegt.
        color_recolor_preferred = bool(
            color_like
            and not logo_mask_preferred
            and not photo_scan_preferred
            and (
                not minimal_color_priority
                or not mask_candidate
            )
        )

        if photo_scan_analysis and (
            photo_scan_analysis.score >= 5
            or photo_scan_analysis.background_noise >= 6.0
            or photo_scan_analysis.color_complexity >= 140
            or photo_scan_analysis.small_specks >= 500
        ):
            self.show_problem_image_hint(tr("status.problem_hint_shown"))

        # Vorrang-Regel: saubere, kontrastreiche Logos sollen bevorzugt
        # über die Logo-Maske laufen. Das verhindert, dass flächige Badges mit
        # wenigen klaren Formen unnötig als Foto-Scan interpretiert werden.
        if logo_mask_preferred:
            threshold = int(max(1, min(100, round(stats["mask_threshold"]))))
            blur = int(max(5, min(151, round(stats["mask_blur"]))))
            coverage = stats["mask_coverage"]
            target = stats.get("mask_target_coverage", coverage)
            try:
                self.step1_notebook.select(self.logo_tab)
            except Exception:
                pass
            msg = tr(
                "msg.step1_recommend_mask",
                threshold=threshold,
                blur=blur,
                coverage=coverage,
                target=target,
            )
            apply_logo_mask = messagebox.askyesno(
                tr("msg.step1_recommend_title"),
                f"{msg}\n\nMehrere Farben erkannt, aber für die Vektorisierung wird bewusst die kontrastreiche Logo-Maske bevorzugt.",
                default=messagebox.YES,
                icon=messagebox.QUESTION,
            )
            if apply_logo_mask:
                self.logo_mask_threshold_var.set(threshold)
                self.logo_mask_blur_var.set(blur)
                self.logo_mask_clean_var.set(True)
                self.logo_mask_fg_var.set("0,0,0")
                self.logo_mask_bg_var.set("255,255,255")
                self.logo_mask_preserve_accents_var.set(True)
                self.logo_mask_accent_var.set("128,64,0")
                self.create_logo_mask_preview()
                self.status_var.set(f"Logo-Maske automatisch empfohlen und angewendet (Schwelle {threshold}, Radius {blur}).")
            else:
                self.status_var.set("Automatische Logo-Masken-Empfehlung übersprungen.")
            return

        # Der Foto-Scan-S/W-Pfad bleibt die zweite Wahl und darf nur dann greifen,
        # wenn Logo-Maske nicht passend erscheint und das Bild tatsächlich eine
        # scanartige oder störungsreiche Bereinigung benötigt.
        if photo_scan_preferred:
            max_colors = 2 if self.motif_profile_var.get() == "logo" else 3 if self.motif_profile_var.get() == "mixed" else 4
            min_area = 8 if self.motif_profile_var.get() != "organic" else 5
            noise = 72 if cad_bw_preferred else 78 if photo_scan_analysis.score >= 6 else 65
            try:
                self.step1_notebook.select(self.photo_scan_tab)
            except Exception:
                pass
            msg = tr(
                "msg.step1_recommend_photo_scan_bw",
                score=photo_scan_analysis.score,
                colors=int(photo_scan_analysis.color_complexity),
                noise=photo_scan_analysis.background_noise,
                specks=photo_scan_analysis.small_specks,
                default=tr(
                    "msg.step1_recommend_photo_scan",
                    score=photo_scan_analysis.score,
                    colors=int(photo_scan_analysis.color_complexity),
                    noise=photo_scan_analysis.background_noise,
                    specks=photo_scan_analysis.small_specks,
                ),
            )
            if small_accents:
                msg = f"{msg}\n\n{tr('msg.step1_recommend_preserve_accents')}"
            apply_photo_scan = messagebox.askyesno(
                tr("msg.step1_recommend_title"),
                msg,
                default=messagebox.YES,
                icon=messagebox.QUESTION,
            )
            if apply_photo_scan:
                self.photo_scan_mode_var.set("bw")
                self.photo_scan_max_colors_var.set(max_colors)
                self.photo_scan_min_area_var.set(min_area)
                self.photo_scan_noise_var.set(noise)
                self.photo_scan_foreground_distance_var.set(24)
                self.photo_scan_weak_contrast_var.set(72)
                self.photo_scan_protect_background_var.set(True)
                self.photo_scan_protect_thin_lines_var.set(True)
                self.photo_scan_close_lines_var.set(True)
                self.photo_scan_fill_small_holes_var.set(False)
                if hasattr(self, "photo_scan_preserve_accents_var"):
                    # Bei S/W-Logo/Badge lieber aktiv lassen: farbige Sterne/Schrift
                    # werden danach lokal schwarz/weiss kontrastierend gesetzt.
                    self.photo_scan_preserve_accents_var.set(bool(small_accents or has_relevant_color))
                self.photo_scan_despeckle_var.set(True)
                self.photo_scan_despeckle_area_var.set(max(3, min(60, self._auto_photo_scan_despeckle_area())))
                self.create_photo_scan_cleanup_preview(show_busy=True)
                self.status_var.set(tr("status.step1_recommend_photo_scan_applied", score=photo_scan_analysis.score))
            else:
                try:
                    self.step1_notebook.select(self.manual_tab)
                except Exception:
                    pass
                self.status_var.set(tr("status.step1_recommend_photo_scan_skipped", score=photo_scan_analysis.score))
            return

        if mask_like:
            threshold = int(max(1, min(100, round(stats["mask_threshold"]))))
            blur = int(max(5, min(151, round(stats["mask_blur"]))))
            coverage = stats["mask_coverage"]
            target = stats.get("mask_target_coverage", coverage)
            try:
                self.step1_notebook.select(self.logo_tab)
            except Exception:
                pass
            msg = tr(
                "msg.step1_recommend_mask",
                threshold=threshold,
                blur=blur,
                coverage=coverage,
                target=target,
            )
            if messagebox.askyesno(tr("msg.step1_recommend_title"), msg, default=messagebox.YES, icon=messagebox.QUESTION):
                self.logo_mask_threshold_var.set(threshold)
                self.logo_mask_blur_var.set(blur)
                self.logo_mask_clean_var.set(True)
                self.logo_mask_fg_var.set("0,0,0")
                self.logo_mask_bg_var.set("255,255,255")
                self.logo_mask_preserve_accents_var.set(True)
                self.logo_mask_accent_var.set("128,64,0")
                self.create_logo_mask_preview()
                self.status_var.set(tr("status.step1_recommend_mask_applied", threshold=threshold, blur=blur))
            else:
                self.status_var.set(tr("status.step1_recommend_mask_skipped"))
            return

        # Tertiäre Empfehlung: strukturierte Farbbilder, die weder klare
        # Masken-Kandidaten noch typische Foto-Scan-Fälle sind, werden über
        # den Farben-Umfärben-Modus vorbereitet.
        if color_recolor_preferred:
            try:
                self.step1_notebook.select(self.basic_tab)
            except Exception:
                pass
            if structured_color:
                if self.motif_profile_var.get() == "logo":
                    suggested_colors = 3
                    threshold = 70
                    min_area = 10
                    noise = 70
                    fill_solid = True
                elif self.motif_profile_var.get() == "mixed":
                    suggested_colors = 4
                    threshold = 52
                    min_area = 8
                    noise = 55
                    fill_solid = True
                else:
                    suggested_colors = 6
                    threshold = 34
                    min_area = 5
                    noise = 35
                    fill_solid = False
            else:
                suggested_colors = 8 if stats["sat_p95"] < 0.30 else 12
                threshold = 14 if stats["edge_density"] > 0.08 else 18
                min_area = 5 if stats["edge_density"] > 0.08 else 10
                noise = 45
                fill_solid = False
            msg = tr("msg.step1_recommend_color", threshold=threshold, suggested_colors=suggested_colors, min_area=min_area, noise=noise)
            if messagebox.askyesno(tr("msg.step1_recommend_title"), msg, default=messagebox.YES, icon=messagebox.QUESTION):
                self.basic_threshold_var.set(threshold)
                self.basic_min_area_var.set(min_area)
                self.basic_max_colors_var.set(suggested_colors)
                self.basic_alpha_var.set(10)
                self.basic_noise_var.set(noise)
                self.basic_fill_solid_var.set(fill_solid)
                self.detect_basic_colors(show_busy=True)
                self.status_var.set(tr("status.step1_recommend_color_applied"))
            else:
                self.status_var.set(tr("status.step1_recommend_color_skipped"))
            return

        try:
            self.step1_notebook.select(self.manual_tab)
        except Exception:
            pass
        msg = tr("msg.step1_recommend_manual")
        try:
            messagebox.showinfo(tr("msg.step1_recommend_title"), msg)
        except Exception:
            pass
        self.status_var.set(tr("status.step1_recommend_manual"))


    # ------------------------------------------------------------------ Schritt 1 Logik
    def choose_input_image(self) -> None:
        initial_dir = self._initial_dir_from_config("input")
        path = filedialog.askopenfilename(
            title="Bild laden",
            initialdir=initial_dir,
            filetypes=[("Bilddateien", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"), ("Alle Dateien", "*.*")],
        )
        if path:
            self._remember_input_path(path)
            # Erst laden und analysieren. So kann ein bereits sauberes
            # Schwarz/Weiß-/Lineart-Bild erkannt werden, bevor die allgemeine
            # Auto-Erkennung überhaupt gefragt wird.
            self._run_step1_auto_after_load = True
            self.load_input_image(path)

    def load_input_image(self, path: str) -> None:
        self.show_busy_dialog(tr("msg.busy_load_image_title"), tr("msg.busy_load_image_body"))
        try:
            self.set_progress(10, tr("progress.load_image"))
            try:
                img = Image.open(path).convert("RGBA")
            except Exception as exc:
                messagebox.showerror(tr("msg.load_error"), str(exc))
                return
            self.set_progress(35, tr("progress.prepare_image"))
            self.current_path = Path(path)
            self.original_image = img
            self._update_ai_upscale_original_size_label()
            flat_rgb = np.array(_flatten_rgba_to_rgb(img))
            self._perfect_bw_source = (
                self._is_perfect_black_white_array(flat_rgb)
                or self._is_high_contrast_black_white_array(flat_rgb)
            )
            self.step2_auto_prompt_pending = True
            self.prepared_image = None
            self.edited_image = self.get_prepared_image(force=True)
            self.special_result_image = None
            self.special_result_mode = None
            self.photo_scan_status_var.set("")
            self.clear_basic_rows()
            self.step1_original_canvas.set_image(self.original_image, reset_view=True)
            self.step1_edited_canvas.set_image(self.edited_image, reset_view=True)
            if self._perfect_bw_source:
                self._run_step1_auto_after_load = False
            if not self.output_path_var.get():
                self.output_path_var.set(str(self.current_path.with_suffix(".dxf")))
            self.set_progress(100, tr("status.image_loaded", name=self.current_path.name, width=img.width, height=img.height))
        finally:
            self.close_busy_dialog()

        if self._perfect_bw_source:
            if messagebox.askyesno(tr("msg.perfect_bw_title"), tr("msg.step1_recommend_existing_bw"), default=messagebox.YES, icon=messagebox.QUESTION):
                self.use_existing_step1_image_preview()
                self.status_var.set(tr("status.perfect_bw_ready"))
            else:
                try:
                    self.step1_notebook.select(self.manual_tab)
                except Exception:
                    pass
                self.status_var.set(tr("status.existing_image_skipped"))
        else:
            try:
                self._run_step1_auto_after_load = messagebox.askyesno(
                    tr("msg.step1_auto_prompt_title"),
                    tr("msg.step1_auto_prompt_body"),
                    default=messagebox.YES,
                    icon=messagebox.QUESTION,
                )
            except Exception:
                self._run_step1_auto_after_load = True
            if self._run_step1_auto_after_load:
                # Nach dem Laden ist das Bild sichtbar; die Auto-Analyse läuft nur nach Zustimmung.
                self.after_idle(lambda: self.recommend_step1_mode_from_image(force=False))
            else:
                self.status_var.set(tr("status.step1_auto_skipped"))

    def get_prepared_image(self, force: bool = False) -> Optional[Image.Image]:
        if self.original_image is None:
            return None
        if self.prepared_image is not None and not force:
            return self.prepared_image
        base_image = self.original_image
        try:
            angle = float(self.prep_rotation_var.get())
        except Exception:
            angle = 0.0
        if abs(angle) > 0.001:
            try:
                resample = Image.Resampling.BICUBIC
            except AttributeError:
                resample = Image.BICUBIC
            base_image = base_image.convert("RGBA").rotate(
                -angle,
                expand=True,
                resample=resample,
                fillcolor=(255, 255, 255, 0),
            )
        self.prepared_image = recolor.apply_image_preparation(
            base_image,
            brightness=int(self.prep_brightness_var.get()),
            contrast=int(self.prep_contrast_var.get()),
            black_point=int(self.prep_black_var.get()),
            white_point=int(self.prep_white_var.get()),
            gamma=float(self.prep_gamma_var.get()),
        )
        return self.prepared_image

    def on_preprocess_changed(self) -> None:
        self.special_result_image = None
        self.special_result_mode = None
        self.photo_scan_status_var.set("")
        self.get_prepared_image(force=True)
        self.schedule_step1_preview()

    def reset_preprocessing(self) -> None:
        self.prep_brightness_var.set(0)
        self.prep_contrast_var.set(0)
        self.prep_black_var.set(0)
        self.prep_white_var.set(255)
        self.prep_gamma_var.set(1.0)
        self.prep_rotation_var.set(0.0)
        self.on_preprocess_changed()

    def rotate_step1_image(self, delta_deg: float) -> None:
        try:
            current = float(self.prep_rotation_var.get())
        except Exception:
            current = 0.0
        new_value = current + float(delta_deg)
        while new_value > 180:
            new_value -= 360
        while new_value < -180:
            new_value += 360
        self.prep_rotation_var.set(new_value)
        self.on_preprocess_changed()

    def use_existing_step1_image_preview(self) -> None:
        base = self.get_prepared_image(force=True)
        if base is None:
            return
        self.special_result_image = _flatten_rgba_to_rgb(base)
        self.special_result_mode = "existing"
        self.edited_image = self.special_result_image.copy()
        self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)

    def reset_step2_settings_for_new_workflow(self) -> None:
        self._suspend_live_preview = True
        try:
            if self.step2_live_after_id:
                try:
                    self.after_cancel(self.step2_live_after_id)
                except Exception:
                    pass
                self.step2_live_after_id = None

            self.output_path_var.set("")
            self.pixel_to_mm_var.set("1.0")
            self.target_width_mm_var.set("")
            self.target_height_mm_var.set("")
            self.cad_tolerance_mm_var.set("0.03")
            self.vector_bbox_info_var.set("")
            self.dxf_compatibility_var.set("default")
            self.dxf_version_var.set(_dxf_choice_for_version("R2000"))
            self.on_dxf_compatibility_changed()
            self.profile_var.set("Standard")
            self.vector_mode_var.set("area")
            self.vector_mode_display_var.set(self._mode_label("area"))
            self.centerline_merge_px_var.set("0")
            self.closed_paths_only_var.set(False)
            self.fill_closed_shapes_var.set(False)
            self.group_connected_paths_var.set(True)
            self.force_color_layers_var.set(True)
            self.object_layers_dxf_var.set(False)
            self.preview_mode_var.set("object")
            self.preview_mode_display_var.set(self._preview_label("object"))
            self.use_bezier_var.set(False)
            self.unique_cad_lines_var.set(False)
            self.duplicate_line_tolerance_var.set("1,5")
            self.remove_loose_points_var.set(False)
            self.anchor_neighbor_distance_var.set("0.50")
            self.smooth_contours_var.set(False)
            self.smooth_strength_var.set("2")
            self.global_epsilon_var.set("0.350")
            self.global_tolerance_var.set("12")
            self.preprocess_vector_var.set(False)
            self.preprocess_blur_var.set(0.8)
            self.preprocess_edge_var.set(1.0)
            self.preprocess_noise_var.set(3.0)
            self.internal_scale_var.set("2")
            self.internal_scale_display_var.set(self._internal_scale_label("2"))
            self.smart_smoothing_var.set(False)
            self.smart_corner_angle_var.set("45")
            self.smart_line_tolerance_var.set("1.0")
            self.smart_curve_strength_var.set("2")
            self.hole_scale_var.set("1.000")
            self.bridge_tabs_var.set(False)
            self.bridge_width_mm_var.set("1.000")
            self.bridge_width_percent_var.set("0.000")
            self.bridge_count_var.set("2.000")
            self.live_preview_var.set(True)
            self.cleanup_mode_var.set("off")
            self.cleanup_mode_display_var.set(self._cleanup_label("off"))
            self.min_object_area_mm2_var.set("0")
            self.min_object_percent_var.set("0,00")
            self.ui_complexity_var.set("simple")
            self.ui_complexity_display_var.set(self._ui_complexity_label("simple"))
            self.motif_profile_var.set("mixed")
            self.motif_profile_display_var.set(self._motif_profile_label("mixed"))
            self.vector_selection_mode_var.set(False)
            self.show_anchor_points_var.set(False)
            self.step2_shared_zoom_var.set(1.0)
            self._syncing_step2_zoom = False
            self._step1_transferred_color_rules = False
            self.clear_vector_rows()
            self.load_vector_profile("Standard")
            self.apply_ui_complexity_mode()
        finally:
            self._suspend_live_preview = False

    def reset_workflow_for_new_image(self) -> None:
        if self.preview_after_id:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
            self.preview_after_id = None
        if self.step2_live_after_id:
            try:
                self.after_cancel(self.step2_live_after_id)
            except Exception:
                pass
            self.step2_live_after_id = None

        self.current_path = None
        self.original_image = None
        self._update_ai_upscale_original_size_label()
        self.prepared_image = None
        self.edited_image = None
        self.special_result_image = None
        self.special_result_mode = None
        self.photo_scan_status_var.set("")
        self.hide_problem_image_hint()
        self.vector_image_rgb = None
        self.vector_source_from_step1 = False
        self.detected_contours = []
        self.last_rules = []
        self.selected_contour_index = None
        self.selected_contour_indices.clear()
        self.vector_select_press = None

        self.input_path_var.set("")
        self.vector_source_name_var.set(tr("status.no_intermediate"))
        self.selected_contour_text_var.set(tr("status.no_path_selected"))
        self.vector_diagnostics_var.set("")
        self.vector_color_count_var.set("")
        self.cad_point_count_var.set("")
        self.reset_step2_settings_for_new_workflow()
        self.reset_preprocessing()
        self.basic_threshold_var.set(10)
        self.basic_min_area_var.set(30)
        self.basic_max_colors_var.set(12)
        self.basic_alpha_var.set(10)
        self.basic_noise_var.set(45)
        self.basic_fill_solid_var.set(False)
        self.logo_mask_threshold_var.set(10)
        self.logo_mask_blur_var.set(50)
        self.logo_mask_clean_var.set(True)
        self.logo_mask_fg_var.set("0,0,0")
        self.logo_mask_bg_var.set("255,255,255")
        self.logo_mask_preserve_accents_var.set(True)
        self.logo_mask_accent_var.set("128,64,0")
        self.photo_scan_max_colors_var.set(3)
        self.photo_scan_min_area_var.set(10)
        self.photo_scan_noise_var.set(70)
        self.photo_scan_foreground_distance_var.set(30)
        self.photo_scan_weak_contrast_var.set(0)
        self.photo_scan_protect_background_var.set(False)
        self.photo_scan_object_mask_first_var.set(False)
        self.photo_scan_despeckle_var.set(False)
        self.photo_scan_despeckle_area_var.set(0)
        self.photo_scan_protect_thin_lines_var.set(True)
        self.photo_scan_close_lines_var.set(True)
        self.photo_scan_fill_small_holes_var.set(False)
        self.photo_scan_preserve_accents_var.set(True)
        self.photo_scan_mode_var.set("auto")

        self.clear_basic_rows()
        for row in self.manual_rows:
            row.destroy()
        self.manual_rows.clear()
        self.add_manual_row()
        self.status_var.set(tr("status.workflow_reset"))
        self.set_progress(0, tr("status.workflow_reset"))

        for canvas in (
            self.step1_original_canvas,
            self.step1_edited_canvas,
            self.step2_original_canvas,
            self.step2_vector_canvas,
        ):
            try:
                canvas.set_image(None, reset_view=True)
            except Exception:
                pass

        self._step1_recommendation_shown_for = None
        self._lineart_recommendation_shown = False
        self.step2_auto_prompt_pending = True
        self._startup_welcome_shown = False
        self.show_step(0)
        self.after(200, self.show_startup_welcome)

    def auto_tune_from_input_image(self) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        self._step1_recommendation_shown_for = None
        self.recommend_step1_mode_from_image(force=True)

    def auto_tune_expert_values_from_image(self) -> None:
        source_arr: Optional[np.ndarray] = None
        if self.vector_image_rgb is not None:
            source_arr = self.vector_image_rgb.astype(np.float32)
        elif self.edited_image is not None:
            source_arr = np.array(_flatten_rgba_to_rgb(self.edited_image), dtype=np.float32)
        elif self.original_image is not None:
            source_arr = np.array(_flatten_rgba_to_rgb(self.original_image), dtype=np.float32)
        if source_arr is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return

        h, w = source_arr.shape[:2]
        mega_px = (w * h) / 1_000_000.0
        gray = source_arr.mean(axis=2)
        dyn = float(np.percentile(gray, 95) - np.percentile(gray, 5))
        grad_x = np.abs(np.diff(gray, axis=1))
        grad_y = np.abs(np.diff(gray, axis=0))
        edge_density = float(((grad_x > 16).mean() + (grad_y > 16).mean()) * 0.5)
        rgb_norm = np.clip(source_arr / 255.0, 0.0, 1.0)
        sat = float((np.max(rgb_norm, axis=2) - np.min(rgb_norm, axis=2)).mean())
        near_bw = float((np.max(source_arr, axis=2) - np.min(source_arr, axis=2) < 18).mean())
        antialias_ratio = float(((gray > 8) & (gray < 247)).mean())

        self.preprocess_vector_var.set(False)
        self.smart_smoothing_var.set(False)
        self.closed_paths_only_var.set(False)

        text_logo = near_bw > 0.72 and dyn > 105 and edge_density > 0.035
        organic = sat > 0.22 and edge_density > 0.05 and dyn < 140
        motif_profile = self.motif_profile_var.get()

        if text_logo:
            # Lineart/Logos: keine automatische Weichzeichnung. Feine Striche
            # sollen erst einmal erhalten bleiben; der Benutzer kann im Experten-
            # Modus später bewusst glätten.
            bw_profile = self._find_bw_profile_key()
            if bw_profile:
                self.load_vector_profile(bw_profile)
            blur = 0.0
            epsilon = 0.060
            scale = "3" if mega_px < 3.0 else "2"
            smooth = 0.0
            edge = 0.0
            noise = 0.0
            corner = 34.0
            line_tol = 0.65
            curve = 0.0
            tolerance = max(120, min(210, int(round(120 + antialias_ratio * 140))))
            self.preprocess_vector_var.set(False)
            self.smart_smoothing_var.set(False)
            self._set_preview_mode_key("contour")
        elif organic:
            # Organische/farbige Motive dürfen leicht beruhigt werden, aber nicht
            # so stark, dass feine Innenformen verschwinden.
            blur = 0.25 if mega_px < 2.5 else 0.18
            epsilon = 0.70 if mega_px < 2.5 else 0.90
            scale = "3" if mega_px < 3.0 else "2"
            smooth = 1.0
            edge = 0.6
            noise = 1.0 if mega_px < 2.5 else 1.5
            corner = 44.0
            line_tol = 1.00
            curve = 1.4
            tolerance = max(12, min(45, int(round(14 + sat * 35))))
            self.preprocess_vector_var.set(True)
            self.smart_smoothing_var.set(True)
        else:
            blur = 0.0 if edge_density < 0.09 else 0.20
            epsilon = 0.55 if mega_px < 4.0 else 0.75
            scale = "2" if mega_px < 6.0 else "1"
            smooth = 0.0 if edge_density < 0.09 else 0.8
            edge = 0.0 if blur <= 0 else 0.5
            noise = 0.0 if blur <= 0 else 1.0
            corner = 50.0
            line_tol = 1.15
            curve = 1.0
            tolerance = max(10, min(40, int(round(12 + edge_density * 150))))
            self.preprocess_vector_var.set(blur > 0.0)
            self.smart_smoothing_var.set(smooth > 0.05)

        if motif_profile == "logo":
            if not text_logo:
                blur = min(blur, 0.150)
                epsilon = max(epsilon, 1.500)
                edge = max(edge, 1.000)
                noise = max(noise, 2.000)
                smooth = min(smooth, 0.800)
                corner = min(max(corner, 25.000), 30.000)
                line_tol = max(line_tol, 2.000)
                curve = min(curve, 1.000)
                scale = "2" if mega_px >= 3.0 else scale
                self.preprocess_vector_var.set(True)
                self.smart_smoothing_var.set(True)
        elif motif_profile == "organic":
            blur = min(max(blur, 0.100), 0.250)
            epsilon = min(epsilon, 0.250)
            edge = min(edge, 0.300)
            noise = min(noise, 0.500)
            smooth = 0.0
            corner = min(corner, 38.000)
            line_tol = min(line_tol, 0.700)
            curve = 0.0
            scale = "3" if mega_px < 5.0 else "2"
            self.preprocess_vector_var.set(True)
            self.smart_smoothing_var.set(False)
        else:
            if not text_logo:
                epsilon = min(max(epsilon, 0.300), 0.700)
                edge = min(max(edge, 0.500), 1.000)
                noise = min(max(noise, 0.800), 1.500)
                curve = min(max(curve, 0.600), 1.400)

        self.preprocess_blur_var.set(round(blur, 3))
        self.preprocess_edge_var.set(round(edge, 3))
        self.preprocess_noise_var.set(round(noise, 3))
        self.internal_scale_var.set(scale)
        self.internal_scale_display_var.set(self._internal_scale_label(scale))
        self.global_epsilon_var.set(f"{epsilon:.3f}")
        self.smooth_contours_var.set(smooth > 0.05)
        self.smooth_strength_var.set(f"{smooth:.3f}")
        self.smart_corner_angle_var.set(f"{corner:.3f}")
        self.smart_line_tolerance_var.set(f"{line_tol:.3f}")
        self.smart_curve_strength_var.set(f"{curve:.3f}")
        self.global_tolerance_var.set(str(int(tolerance)))
        self.apply_global_epsilon_to_rows()
        self.apply_global_tolerance_to_rows()
        self.status_var.set(tr("status.auto_expert_done"))

    def schedule_step1_preview(self) -> None:
        if self.preview_after_id:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
        self.preview_after_id = self.after(180, self.update_step1_preview)

    def select_step1_tab(self, key: str) -> None:
        """Select a Step-1 page from the method dropdown."""
        try:
            tab = getattr(self, "step1_tabs_by_key", {}).get(key)
            if tab is None:
                return
            self.step1_notebook.select(tab)
            self.step1_tab_key_var.set(key)
            if hasattr(self, "step1_tab_display_var"):
                self.step1_tab_display_var.set(self._step1_mode_label(key))
            if hasattr(self, "step1_tab_hint_var"):
                self.step1_tab_hint_var.set(self._step1_mode_hint(key))
            if key == "ai_upscale":
                self._ensure_ai_upscale_defaults()
            self.on_step1_mode_changed()
        except Exception:
            pass

    def on_step1_mode_display_changed(self) -> None:
        try:
            label = self.step1_tab_display_var.get()
            key = getattr(self, "step1_mode_display_to_key", {}).get(label)
            if key is None:
                for candidate in getattr(self, "step1_mode_keys", []):
                    if label == self._step1_mode_label(candidate):
                        key = candidate
                        break
            if key:
                self.select_step1_tab(key)
        except Exception:
            pass

    def on_step1_mode_changed(self) -> None:
        try:
            selected_tab = self.nametowidget(self.step1_notebook.select())
            key = getattr(self, "step1_tab_keys_by_widget", {}).get(selected_tab)
            if key:
                self.step1_tab_key_var.set(key)
                if hasattr(self, "step1_tab_display_var"):
                    self.step1_tab_display_var.set(self._step1_mode_label(key))
                if hasattr(self, "step1_tab_hint_var"):
                    self.step1_tab_hint_var.set(self._step1_mode_hint(key))
        except Exception:
            pass
        self.update_step1_picker_cursor()
        self.update_step1_preview()

    def update_step1_picker_cursor(self) -> None:
        try:
            selected_tab = self.nametowidget(self.step1_notebook.select())
            original_cursor = "crosshair" if selected_tab is self.manual_tab else ""
            edited_cursor = "crosshair" if hasattr(self, "eraser_tab") and selected_tab is self.eraser_tab else ""
            self.step1_original_canvas.canvas.configure(cursor=original_cursor)
            if hasattr(self, "step1_edited_canvas"):
                self.step1_edited_canvas.canvas.configure(cursor=edited_cursor)
        except Exception:
            pass

    def on_step1_canvas_view_changed(self, source_canvas) -> None:
        if self._syncing_step1_view or not self.step1_sync_view_var.get():
            return
        try:
            self._syncing_step1_view = True
            target_canvas = self.step1_edited_canvas if source_canvas is self.step1_original_canvas else self.step1_original_canvas
            target_canvas.zoom = float(source_canvas.zoom)
            target_canvas.offset_x = float(source_canvas.offset_x)
            target_canvas.offset_y = float(source_canvas.offset_y)
            target_canvas.render()
        except Exception:
            pass
        finally:
            self._syncing_step1_view = False

    def sync_step1_canvas_views_now(self) -> None:
        if getattr(self, "step1_sync_view_var", None) is not None and self.step1_sync_view_var.get():
            self.on_step1_canvas_view_changed(self.step1_original_canvas)

    def clear_basic_rows(self) -> None:
        for row in self.basic_rows:
            row.destroy()
        self.basic_rows.clear()

    def detect_basic_colors(self, show_busy: bool = True) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        if show_busy:
            self.show_busy_dialog(tr("msg.busy_detect_colors_title"), tr("msg.busy_detect_colors_body"))
        progress_start = 0.0 if show_busy else 65.0
        progress_span = 100.0 if show_busy else 30.0

        def phase(value: float) -> float:
            return progress_start + (progress_span * value / 100.0)

        try:
            try:
                self.set_progress(phase(15), tr("progress.prepare_image"))
                base = self.get_prepared_image(force=True)
                threshold = max(0, min(255, int(self.basic_threshold_var.get())))
                min_area = max(1, int(self.basic_min_area_var.get()))
                max_colors = max(1, min(64, int(self.basic_max_colors_var.get())))
                alpha_min = max(0, min(255, int(self.basic_alpha_var.get())))
                self.set_progress(phase(35), tr("progress.detect_colors"))
                detected = recolor.RecolorApp.detect_motif_colors_by_threshold(
                    base,
                    threshold=threshold,
                    min_area=min_area,
                    max_colors=max_colors,
                    alpha_min=alpha_min,
                    noise_suppression=max(0, min(100, int(self.basic_noise_var.get()))),
                )
                if len(detected) < 2:
                    self.set_progress(phase(55), tr("progress.detect_colors_fallback"))
                    detected = recolor.RecolorApp.detect_colors_by_threshold(
                        base,
                        threshold=threshold,
                        min_area=min_area,
                        max_colors=max_colors,
                        alpha_min=alpha_min,
                    )
            except Exception as exc:
                messagebox.showerror(tr("msg.error"), tr("msg.detect_colors_error", error=exc))
                return
            self.set_progress(phase(75), tr("progress.build_color_table"))
            self.clear_basic_rows()
            for i, item in enumerate(detected):
                self.basic_rows.append(BasicWorkflowRow(self, self.basic_rows_container, i, item))
            self.apply_bw_targets_to_basic_rows_if_suitable(base)
            self.set_progress(phase(90), tr("progress.render_preview"))
            self.update_step1_preview()
            self.set_progress(phase(100), tr("status.detected_color_regions", count=len(detected)))
        finally:
            if show_busy:
                self.close_busy_dialog()

    def apply_bw_targets_to_basic_rows_if_suitable(self, image: Image.Image) -> None:
        """Bei zweifarbigem Lineart Schwarz/Weiß statt Kontrastpalette setzen."""
        if len(self.basic_rows) != 2:
            return
        try:
            rgb_image = _flatten_rgba_to_rgb(image)
            stats = self._bw_stats_from_array(np.array(rgb_image, dtype=np.uint8))
        except Exception:
            return
        if not (
            stats["near_bw"] >= 0.88
            and stats["colored"] <= 0.03
            and stats["dynamic"] >= 80
            and stats["near_black"] >= 0.005
            and stats["near_white"] >= 0.05
        ):
            return
        rows_by_brightness = sorted(
            self.basic_rows,
            key=lambda row: sum(int(v) for v in row.detected.source_rgb) / 3.0,
        )
        rows_by_brightness[0].target_var.set("0,0,0")
        rows_by_brightness[1].target_var.set("255,255,255")

    def reassign_basic_targets(self) -> None:
        for index, row in enumerate(self.basic_rows):
            name, rgb = recolor.CONTRAST_PALETTE[index % len(recolor.CONTRAST_PALETTE)]
            row.detected.palette_name = name
            row.target_var.set(_rgb_to_text(rgb))
        self.update_step1_preview()

    def add_manual_row(self) -> None:
        index = len(self.manual_rows)
        row = ManualWorkflowRow(self, self.manual_rows_container, index)
        self.manual_rows.append(row)
        self.selected_manual_row_var.set(index)
        self.update_manual_status()
        self.schedule_step1_preview()

    def remove_selected_manual_row(self) -> None:
        if not self.manual_rows:
            return
        index = self.selected_manual_row_var.get()
        index = max(0, min(index, len(self.manual_rows) - 1))
        self.manual_rows[index].destroy()
        del self.manual_rows[index]
        saved = [(r.enabled_var.get(), r.source_var.get(), r.tolerance_var.get(), r.target_var.get()) for r in self.manual_rows]
        for r in self.manual_rows:
            r.destroy()
        self.manual_rows.clear()
        for i, data in enumerate(saved):
            row = ManualWorkflowRow(self, self.manual_rows_container, i, data[1], data[3])
            row.enabled_var.set(data[0])
            row.tolerance_var.set(data[2])
            self.manual_rows.append(row)
        if not self.manual_rows:
            self.add_manual_row()
        self.selected_manual_row_var.set(min(index, len(self.manual_rows) - 1))
        self.update_manual_status()
        self.schedule_step1_preview()

    def update_manual_status(self) -> None:
        try:
            self.manual_status_label.configure(text=tr("status.manual_row_selected", row=self.selected_manual_row_var.get() + 1))
        except Exception:
            pass

    def on_pick_color(self, rgb: RGB, x: int, y: int) -> None:
        try:
            selected_tab = self.nametowidget(self.step1_notebook.select())
        except Exception:
            selected_tab = None
        if selected_tab is not self.manual_tab:
            self.status_var.set(tr("status.pixel_color_at", x=x, y=y, rgb=_rgb_to_text(rgb)))
            return
        if not self.manual_rows:
            self.add_manual_row()
        index = max(0, min(self.selected_manual_row_var.get(), len(self.manual_rows) - 1))
        self.manual_rows[index].set_source_rgb(rgb)
        self.status_var.set(tr("status.color_copied_to_row", rgb=_rgb_to_text(rgb), row=index + 1))

    def _is_step1_eraser_mode(self) -> bool:
        try:
            selected_tab = self.nametowidget(self.step1_notebook.select())
            return hasattr(self, "eraser_tab") and selected_tab is self.eraser_tab
        except Exception:
            return False

    def _canvas_to_edited_image_xy(self, event: tk.Event) -> Optional[Tuple[int, int]]:
        canvas = getattr(self, "step1_edited_canvas", None)
        if canvas is None or canvas.image is None:
            return None
        try:
            zoom = max(0.0001, float(canvas.zoom))
            x = int(round((int(event.x) - float(canvas.offset_x)) / zoom))
            y = int(round((int(event.y) - float(canvas.offset_y)) / zoom))
            if 0 <= x < canvas.image.width and 0 <= y < canvas.image.height:
                return x, y
        except Exception:
            return None
        return None

    def _ensure_eraser_work_image(self) -> bool:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return False
        if self.special_result_mode != "eraser" or self.special_result_image is None:
            if self.edited_image is not None:
                base = self.edited_image
            else:
                base = self.get_prepared_image(force=False)
            self.special_result_image = _flatten_rgba_to_rgb(base).copy()
            self.special_result_mode = "eraser"
        if self.special_result_image.mode not in ("RGB", "RGBA"):
            self.special_result_image = self.special_result_image.convert("RGB")
        self.edited_image = self.special_result_image.copy()
        return True

    def _eraser_stamp_bounds(self, x: int, y: int) -> Tuple[int, int, int, int]:
        size = max(1, min(999, int(float(self.eraser_size_var.get()))))
        radius = max(0, size // 2)
        return x - radius, y - radius, x - radius + size - 1, y - radius + size - 1

    def _stamp_eraser_at(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        try:
            rgb = _parse_rgb_any(self.eraser_color_var.get())
        except Exception:
            rgb = (255, 255, 255)
        fill: Any
        if self.special_result_image is not None and self.special_result_image.mode == "RGBA":
            fill = (*rgb, 255)
        else:
            fill = rgb
        bounds = self._eraser_stamp_bounds(int(x), int(y))
        if (self.eraser_shape_var.get() or "round") == "square":
            draw.rectangle(bounds, fill=fill)
        else:
            draw.ellipse(bounds, fill=fill)

    def _paint_eraser_line(self, start: Tuple[int, int], end: Tuple[int, int]) -> None:
        if self.special_result_image is None:
            return
        draw = ImageDraw.Draw(self.special_result_image)
        sx, sy = start
        ex, ey = end
        size = max(1, min(999, int(float(self.eraser_size_var.get()))))
        distance = math.hypot(ex - sx, ey - sy)
        step = max(1.0, size * 0.35)
        count = max(1, int(math.ceil(distance / step)))
        for index in range(count + 1):
            t = index / max(1, count)
            x = int(round(sx + (ex - sx) * t))
            y = int(round(sy + (ey - sy) * t))
            self._stamp_eraser_at(draw, x, y)
        self.edited_image = self.special_result_image.copy()
        self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)

    def on_step1_edited_press(self, event: tk.Event) -> str | None:
        if not self._is_step1_eraser_mode():
            return self.step1_edited_canvas._start_left_action(event)
        if not self._ensure_eraser_work_image():
            return "break"
        xy = self._canvas_to_edited_image_xy(event)
        if xy is None:
            return "break"
        self._eraser_last_xy = xy
        self._paint_eraser_line(xy, xy)
        self.eraser_status_var.set(tr("status.eraser_painted", x=xy[0], y=xy[1]))
        self.status_var.set(self.eraser_status_var.get())
        return "break"

    def on_step1_edited_motion(self, event: tk.Event) -> str | None:
        if not self._is_step1_eraser_mode():
            return self.step1_edited_canvas._move_left_action(event)
        if not self._ensure_eraser_work_image():
            return "break"
        xy = self._canvas_to_edited_image_xy(event)
        if xy is None:
            return "break"
        last = self._eraser_last_xy or xy
        self._paint_eraser_line(last, xy)
        self._eraser_last_xy = xy
        self.eraser_status_var.set(tr("status.eraser_painted", x=xy[0], y=xy[1]))
        self.status_var.set(self.eraser_status_var.get())
        return "break"

    def on_step1_edited_release(self, event: tk.Event) -> str | None:
        if not self._is_step1_eraser_mode():
            return self.step1_edited_canvas._end_left_action(event)
        self._eraser_last_xy = None
        return "break"

    def update_eraser_color_swatch(self) -> None:
        try:
            rgb = _parse_rgb_any(self.eraser_color_var.get())
            color = _rgb_to_hex(rgb)
        except Exception:
            color = "#cccccc"
        try:
            self.eraser_color_swatch.configure(bg=color)
        except Exception:
            pass

    def choose_eraser_color(self) -> None:
        try:
            initial = _rgb_to_hex(_parse_rgb_any(self.eraser_color_var.get()))
        except Exception:
            initial = "#ffffff"
        color = colorchooser.askcolor(color=initial, title=tr("step1.eraser_color_choose"))
        if color and color[0]:
            rgb = tuple(int(round(v)) for v in color[0])
            self.eraser_color_var.set(_rgb_to_text(rgb))

    def choose_ai_upscale_model(self) -> None:
        initial_dir = self._default_ai_upscale_models_dir()
        if initial_dir is None:
            initial_dir = Path(self._initial_dir_from_config("input"))
        path = filedialog.askdirectory(
            title=tr("step1.ai_upscale_choose_model"),
            initialdir=str(initial_dir),
        )
        if path:
            self.ai_upscale_model_var.set(self._normalize_ai_upscale_model_dir(path))

    def choose_ai_upscale_output(self) -> None:
        initial = "upscaled.png"
        if self.current_path:
            initial = f"{self.current_path.stem}_upscaled.png"
        path = filedialog.asksaveasfilename(
            title=tr("step1.ai_upscale_choose_output"),
            defaultextension=".png",
            initialdir=self._initial_dir_from_config("output"),
            initialfile=initial,
            filetypes=[("PNG", "*.png")],
        )
        if path:
            self.ai_upscale_output_var.set(path)

    def choose_ai_scale_model(self) -> None:
        path = filedialog.askopenfilename(
            title=tr("step1.ai_scale_choose_model"),
            initialdir=self._initial_dir_from_config("input"),
            filetypes=[("Model Files", "*.pth *.onnx"), ("All Files", "*.*")],
        )
        if path:
            self.ai_scale_model_var.set(path)

    def choose_ai_scale_output(self) -> None:
        initial = "scaled.png"
        if self.current_path:
            initial = f"{self.current_path.stem}_scaled.png"
        path = filedialog.asksaveasfilename(
            title=tr("step1.ai_scale_choose_output"),
            defaultextension=".png",
            initialdir=self._initial_dir_from_config("output"),
            initialfile=initial,
            filetypes=[("PNG", "*.png")],
        )
        if path:
            self.ai_scale_output_var.set(path)

    def create_ai_scale_preview(self) -> None:
        messagebox.showinfo(
            tr("step1.ai_scale_preview_title"),
            tr("step1.ai_scale_preview_body"),
        )

    def create_ai_upscale_preview(self) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        base = self.get_prepared_image(force=True)
        if base is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        width, height = self._ai_upscale_target_size(base)
        if not self.ai_upscale_output_var.get().strip():
            self.ai_upscale_output_var.set(str(self._default_ai_upscale_output_path()))
        self.show_busy_dialog(tr("step1.ai_upscale_preview_title"), "KI-Skalierung läuft ...")
        self.set_progress(2, "KI-Skalierung vorbereitet")

        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        def worker() -> None:
            try:
                def worker_progress(value: float, status: str) -> None:
                    result_queue.put(("progress", (value, status)))

                out_path = self._run_ai_upscale(base, width, height, progress_callback=worker_progress)
                result_queue.put(("result", out_path))
            except Exception as exc:
                result_queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

        def poll_worker() -> None:
            while True:
                try:
                    kind, payload = result_queue.get_nowait()
                except queue.Empty:
                    self.after(120, poll_worker)
                    return

                if kind == "progress":
                    value, status = payload
                    self.set_progress(float(value), str(status))
                    continue

                self.close_busy_dialog()
                if kind == "error":
                    messagebox.showerror(tr("msg.error"), str(payload))
                    return
                out_path = Path(payload)
                try:
                    with Image.open(out_path) as preview_image:
                        result_image = preview_image.convert("RGBA")
                except Exception as exc:
                    messagebox.showerror(tr("msg.error"), str(exc))
                    return
                self.special_result_image = result_image.copy()
                self.special_result_mode = "ai_upscale"
                self.edited_image = result_image.copy()
                self.step1_edited_canvas.set_image(self.edited_image, reset_view=True)
                self.status_var.set(f"KI-Skalierung gespeichert: {out_path}")
                messagebox.showinfo(
                    tr("step1.ai_upscale_preview_title"),
                    tr("step1.ai_upscale_preview_body")
                )
                return

        self.after(120, poll_worker)

    def _ai_upscale_target_size(self, image: Image.Image) -> tuple[int, int]:
        unit = self.ai_upscale_unit_var.get()
        width_text = str(self.ai_upscale_width_var.get()).strip().replace(",", ".")
        height_text = str(self.ai_upscale_height_var.get()).strip().replace(",", ".")
        keep_aspect = bool(self.ai_upscale_keep_aspect_var.get())
        master = str(self.ai_upscale_aspect_master_var.get() or "width")
        if keep_aspect:
            if master == "width":
                height_text = ""
            else:
                width_text = ""
        width = None
        height = None
        try:
            if unit == "percent":
                factor = float(width_text or height_text or "200") / 100.0
                width = max(1, int(round(image.width * factor)))
                height = max(1, int(round(image.height * factor)))
            else:
                if keep_aspect:
                    aspect = image.width / image.height if image.height else 1.0
                    if master == "height":
                        height = int(round(float(height_text))) if height_text else image.height
                        width = max(1, int(round(height * aspect)))
                    else:
                        width = int(round(float(width_text))) if width_text else image.width
                        height = max(1, int(round(width / aspect)))
                else:
                    width = int(round(float(width_text))) if width_text else image.width
                    height = int(round(float(height_text))) if height_text else image.height
        except Exception:
            width = image.width
            height = image.height
        if keep_aspect and unit == "percent" and width > 0 and height > 0:
            aspect = image.width / image.height if image.height else 1.0
            if width / max(1, height) > aspect:
                width = max(1, int(round(height * aspect)))
            else:
                height = max(1, int(round(width / aspect)))
        return max(1, width), max(1, height)

    def prepare_eraser_from_current_preview(self) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        if self.preview_after_id:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
            self.preview_after_id = None
        # Aktuelle Ansicht als Radier-Grundlage übernehmen. Falls bereits im Radierer
        # gearbeitet wurde, bleibt genau dieser Stand erhalten.
        if self.edited_image is None:
            self.edited_image = self.get_prepared_image(force=False).copy()
        self.special_result_image = _flatten_rgba_to_rgb(self.edited_image).copy()
        self.special_result_mode = "eraser"
        self.edited_image = self.special_result_image.copy()
        self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)
        self.eraser_status_var.set(tr("status.eraser_ready"))
        self.status_var.set(self.eraser_status_var.get())

    def collect_basic_mappings(self) -> List[Any]:
        mappings = []
        tol = max(0, min(255, int(self.basic_threshold_var.get())))
        for row in self.basic_rows:
            try:
                mapping = row.get_mapping(tol)
                if mapping:
                    mappings.append(mapping)
            except Exception as exc:
                self.status_var.set(tr("status.invalid_base_color", error=exc))
        return mappings

    def collect_manual_mappings(self) -> List[Any]:
        mappings = []
        for row in self.manual_rows:
            try:
                mapping = row.get_mapping()
                if mapping:
                    mappings.append(mapping)
            except Exception as exc:
                self.status_var.set(tr("status.invalid_manual_color", error=exc))
        return mappings

    def update_step1_preview(self) -> None:
        self.preview_after_id = None
        if self.original_image is None:
            return
        try:
            selected_tab = self.nametowidget(self.step1_notebook.select())
        except Exception:
            selected_tab = None
        try:
            if hasattr(self, "eraser_tab") and selected_tab is self.eraser_tab:
                if self.special_result_mode == "eraser" and self.special_result_image is not None:
                    self.edited_image = self.special_result_image.copy()
                elif self.edited_image is not None:
                    self.special_result_image = _flatten_rgba_to_rgb(self.edited_image).copy()
                    self.special_result_mode = "eraser"
                    self.edited_image = self.special_result_image.copy()
                else:
                    base = self.get_prepared_image(force=False)
                    self.special_result_image = _flatten_rgba_to_rgb(base).copy()
                    self.special_result_mode = "eraser"
                    self.edited_image = self.special_result_image.copy()
            elif self.special_result_mode == "existing" and self.special_result_image is not None:
                self.edited_image = self.special_result_image.copy()
            elif selected_tab is self.logo_tab and self.special_result_mode == "logo" and self.special_result_image is not None:
                self.edited_image = self.special_result_image.copy()
            elif selected_tab is self.photo_scan_tab and self.special_result_mode == "photo_scan" and self.special_result_image is not None:
                self.edited_image = self.special_result_image.copy()
            elif selected_tab is self.manual_tab:
                mappings = self.collect_manual_mappings()
                self.edited_image = recolor.RecolorApp.apply_mappings(self.original_image, mappings) if mappings else self.original_image.copy()
            elif selected_tab is self.photo_scan_tab:
                base = self.get_prepared_image(force=False)
                self.edited_image = base.copy()
            elif selected_tab is self.ai_upscale_tab and self.special_result_mode == "ai_upscale" and self.special_result_image is not None:
                self.edited_image = self.special_result_image.copy()
            elif selected_tab is self.ai_upscale_tab:
                base = self.get_prepared_image(force=False)
                self.edited_image = base.copy()
            else:
                base = self.get_prepared_image(force=False)
                mappings = self.collect_basic_mappings()
                self.edited_image = recolor.RecolorApp.apply_mappings(base, mappings) if mappings else base.copy()
        except Exception as exc:
            self.status_var.set(tr("status.preview_error", error=exc))
            return
        reset = self.step1_edited_canvas.image is None or self.step1_edited_canvas.image.size != self.edited_image.size
        self.step1_edited_canvas.set_image(self.edited_image, reset_view=reset)

    def create_logo_mask_preview(self) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        try:
            base = self.get_prepared_image(force=True)
            threshold = max(1, min(100, int(self.logo_mask_threshold_var.get())))
            blur_radius = max(3, min(151, int(self.logo_mask_blur_var.get())))
            if blur_radius % 2 == 0:
                blur_radius += 1
            self.special_result_image = recolor.RecolorApp.build_logo_mask_image(
                base,
                threshold=threshold,
                blur_radius=blur_radius,
                foreground=_parse_rgb_any(self.logo_mask_fg_var.get()),
                background=_parse_rgb_any(self.logo_mask_bg_var.get()),
                clean=bool(self.logo_mask_clean_var.get()),
                preserve_color_accents=bool(self.logo_mask_preserve_accents_var.get()),
                accent=_parse_rgb_any(self.logo_mask_accent_var.get()),
            )
            self.special_result_mode = "logo"
            self.edited_image = self.special_result_image.copy()
            self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)
            self.status_var.set(tr("status.logo_mask_created"))
        except Exception as exc:
            messagebox.showerror(tr("msg.error"), tr("msg.logo_mask_error", error=exc))

    def _build_logo_direct_black_image_local(
        self,
        image: Image.Image,
        threshold: int,
        foreground: RGB,
        background: RGB,
        clean: bool = False,
    ) -> Image.Image:
        """Fallback fuer den Button aus ui_step1.py.

        Dieser lokale Weg ist absichtlich in workflow_app.py enthalten, damit der
        Button auch dann funktioniert, wenn recolor_engine.py aus einem aelteren
        Stand stammt. Er setzt saubere, dunkle Motivbereiche direkt auf exaktes
        Schwarz, ohne die lokale Logo-Masken-Bereinigung zu erzwingen.
        """
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
        rgb = rgba[:, :, :3].astype(np.float32)
        alpha = rgba[:, :, 3] > 0
        if not np.any(alpha):
            return image.convert("RGBA")

        height, width = alpha.shape
        gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

        border = max(1, int(round(min(height, width) * 0.03)))
        border_mask = np.zeros((height, width), dtype=bool)
        border_mask[:border, :] = True
        border_mask[-border:, :] = True
        border_mask[:, :border] = True
        border_mask[:, -border:] = True
        bg_candidates = border_mask & alpha
        if int(np.count_nonzero(bg_candidates)) < max(20, (height * width) // 200):
            bg_candidates = alpha & (gray >= np.percentile(gray[alpha], 65))
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

        out = np.zeros((height, width, 4), dtype=np.uint8)
        out[:, :, 0:3] = np.array(background, dtype=np.uint8)
        out[:, :, 3] = 255
        out[mask, 0:3] = np.array(foreground, dtype=np.uint8)
        return Image.fromarray(out, "RGBA")

    def create_logo_direct_black_preview(self) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        try:
            base = self.get_prepared_image(force=True)
            threshold = max(1, min(100, int(self.logo_mask_threshold_var.get())))
            foreground = _parse_rgb_any(self.logo_mask_fg_var.get())
            background = _parse_rgb_any(self.logo_mask_bg_var.get())
            clean = bool(self.logo_mask_clean_var.get())
            builder = getattr(recolor.RecolorApp, "build_logo_direct_black_image", None)
            if callable(builder):
                self.special_result_image = builder(
                    base,
                    threshold=threshold,
                    foreground=foreground,
                    background=background,
                    clean=clean,
                    preserve_color_accents=bool(self.logo_mask_preserve_accents_var.get()),
                    accent=_parse_rgb_any(self.logo_mask_accent_var.get()),
                )
            else:
                self.special_result_image = self._build_logo_direct_black_image_local(
                    base,
                    threshold=threshold,
                    foreground=foreground,
                    background=background,
                    clean=clean,
                )
            self.special_result_mode = "logo"
            self.edited_image = self.special_result_image.copy()
            self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)
            self.status_var.set(tr("status.logo_direct_black_created"))
        except Exception as exc:
            messagebox.showerror(tr("msg.error"), tr("msg.logo_direct_black_error", error=exc))

    def _auto_photo_scan_despeckle_area(self) -> int:
        image = self.original_image or self.edited_image
        if image is None:
            return 4
        width, height = image.size
        longest = max(1, max(width, height))
        scale = min(1.0, 1500.0 / float(longest))
        work_short = max(1.0, min(width, height) * scale)
        base = (work_short / 650.0) ** 2
        noise_factor = max(0.0, min(1.0, float(self.photo_scan_noise_var.get()) / 100.0))
        return max(1, min(80, int(round(base * (2.5 + noise_factor * 4.5)))))

    def on_photo_scan_despeckle_toggle(self) -> None:
        if self.photo_scan_despeckle_var.get() and int(self.photo_scan_despeckle_area_var.get()) <= 0:
            self.photo_scan_despeckle_area_var.set(self._auto_photo_scan_despeckle_area())
        self.schedule_step1_preview()

    def run_photo_scan_auto_best(self) -> None:
        # Auto bewusst ohne erneutes Zuruecksetzen der Feinwerte starten.
        # So koennen Ziel-Farben, Min. Flaeche oder schwache Details angepasst
        # und trotzdem die technische Auto-Bewertung genutzt werden.
        self.photo_scan_mode_var.set("auto")
        self.create_photo_scan_cleanup_preview(show_busy=True)

    def apply_photo_scan_mode_defaults(self) -> None:
        mode = (self.photo_scan_mode_var.get() or "auto").strip().lower()
        base_min = self._auto_photo_scan_despeckle_area()
        presets = {
            "auto": dict(max_colors=3, min_area=max(4, base_min), noise=70, distance=28, weak=35, bg=True, obj=True, despeckle=True, despeckle_area=base_min, thin=True, close=True, holes=True),
            "clean": dict(max_colors=2, min_area=max(8, base_min * 2), noise=88, distance=38, weak=12, bg=True, obj=True, despeckle=True, despeckle_area=max(base_min * 2, 8), thin=True, close=True, holes=True),
            "detail": dict(max_colors=4, min_area=max(1, base_min // 2), noise=42, distance=18, weak=78, bg=True, obj=True, despeckle=False, despeckle_area=0, thin=True, close=True, holes=False),
            # Farbig darf nicht die komplette Papierstruktur als Arbeitsbereich nehmen,
            # sonst wird der Modus bei großen Scans sehr langsam. Die Objektmaske bleibt
            # aktiv, Farben werden aber trotzdem getrennt erhalten.
            "color": dict(max_colors=4, min_area=max(8, base_min * 2), noise=64, distance=28, weak=28, bg=True, obj=True, despeckle=True, despeckle_area=max(base_min * 2, 10), thin=True, close=True, holes=True),
            "bw": dict(max_colors=1, min_area=max(2, base_min // 2), noise=62, distance=24, weak=70, bg=True, obj=True, despeckle=True, despeckle_area=max(1, base_min // 2), thin=True, close=True, holes=False),
            # Verblasster Druck ist ein eigener Low-Contrast-Weg: Hintergrund abziehen,
            # lokale Druckspuren verstärken und als Schwarz/Weiß-Maske ausgeben.
            "faded": dict(max_colors=1, min_area=max(1, base_min // 2), noise=54, distance=16, weak=92, bg=True, obj=True, despeckle=True, despeckle_area=max(1, base_min // 2), thin=True, close=True, holes=False),
        }
        preset = presets.get(mode, presets["auto"])
        self.photo_scan_max_colors_var.set(int(preset["max_colors"]))
        self.photo_scan_min_area_var.set(int(preset["min_area"]))
        self.photo_scan_noise_var.set(int(preset["noise"]))
        self.photo_scan_foreground_distance_var.set(int(preset["distance"]))
        self.photo_scan_weak_contrast_var.set(int(preset["weak"]))
        self.photo_scan_protect_background_var.set(bool(preset["bg"]))
        self.photo_scan_object_mask_first_var.set(bool(preset["obj"]))
        self.photo_scan_despeckle_var.set(bool(preset["despeckle"]))
        self.photo_scan_despeckle_area_var.set(int(preset["despeckle_area"]))
        self.photo_scan_protect_thin_lines_var.set(bool(preset["thin"]))
        self.photo_scan_close_lines_var.set(bool(preset["close"]))
        self.photo_scan_fill_small_holes_var.set(bool(preset["holes"]))
        self.photo_scan_status_var.set(tr(f"status.photo_scan_mode_{mode}", default=""))

    def _current_photo_scan_params(self) -> dict[str, Any]:
        mode = (self.photo_scan_mode_var.get() or "auto").strip().lower()
        if mode not in {"auto", "clean", "detail", "color", "bw", "faded"}:
            mode = "auto"
            self.photo_scan_mode_var.set(mode)
        # Presets werden nur beim Anklicken eines Modus gesetzt.
        # Beim Berechnen selbst duerfen manuell geaenderte Feinwerte nicht
        # wieder ueberschrieben werden.
        return {
            "mode": mode,
            "max_colors": max(1, min(8, int(self.photo_scan_max_colors_var.get()))),
            "min_area": max(1, int(self.photo_scan_min_area_var.get())),
            "noise_suppression": max(0, min(100, int(self.photo_scan_noise_var.get()))),
            "foreground_distance": max(5, min(80, int(self.photo_scan_foreground_distance_var.get()))),
            "weak_contrast": max(0, min(100, int(self.photo_scan_weak_contrast_var.get()))),
            "protect_background": bool(self.photo_scan_protect_background_var.get()),
            "object_mask_first": bool(self.photo_scan_object_mask_first_var.get()),
            "despeckle": bool(self.photo_scan_despeckle_var.get()),
            "despeckle_min_area": max(0, min(500, int(self.photo_scan_despeckle_area_var.get()))),
            "protect_thin_lines": bool(self.photo_scan_protect_thin_lines_var.get()),
            "close_lines": bool(self.photo_scan_close_lines_var.get()),
            "fill_small_holes": bool(self.photo_scan_fill_small_holes_var.get()),
            "preserve_color_accents": bool(self.photo_scan_preserve_accents_var.get()),
        }

    def create_photo_scan_cleanup_preview(self, show_busy: bool = True) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        try:
            base = self.get_prepared_image(force=True)
            params = self._current_photo_scan_params()
            mode = str(params.pop("mode"))
        except Exception as exc:
            messagebox.showerror(tr("msg.error"), tr("msg.photo_scan_error", error=exc))
            return

        if show_busy:
            self.show_busy_dialog(tr("msg.busy_detect_colors_title"), tr("msg.busy_detect_colors_body"), cancellable=True)
        self.set_progress(5, tr("progress.prepare_image"))

        result_queue = queue.Queue()
        cancel_event = threading.Event()
        started_at = time.monotonic()
        # Nur als Sicherheitsnetz gegen echte Endlosschleifen. Normale lange Läufe
        # werden nicht mehr als Benutzer-Abbruch gemeldet.
        timeout_s = 720.0 if mode == "auto" else 360.0

        def worker() -> None:
            try:
                def worker_progress(value: float, key: str) -> None:
                    result_queue.put(("progress", (value, key)))

                if mode == "auto":
                    result = recolor.RecolorApp.build_photo_scan_auto_image(
                        base,
                        preference="auto",
                        max_colors=params["max_colors"],
                        min_area=params["min_area"],
                        preserve_color_accents=params.get("preserve_color_accents", False),
                        max_work_edge=760,
                        progress_callback=worker_progress,
                        cancel_callback=lambda: cancel_event.is_set() or bool(getattr(self, "_busy_cancel_requested", False)),
                    )
                elif mode == "bw":
                    result = recolor.RecolorApp.build_photo_scan_black_white_image(
                        base,
                        min_area=params["min_area"],
                        noise_suppression=params["noise_suppression"],
                        foreground_distance=params["foreground_distance"],
                        weak_contrast=params["weak_contrast"],
                        protect_background=params["protect_background"],
                        protect_thin_lines=params["protect_thin_lines"],
                        close_lines=params["close_lines"],
                        fill_small_holes=params["fill_small_holes"],
                        preserve_color_accents=params["preserve_color_accents"],
                        max_work_edge=1300,
                        progress_callback=worker_progress,
                        cancel_callback=lambda: cancel_event.is_set() or bool(getattr(self, "_busy_cancel_requested", False)),
                    )
                elif mode == "faded":
                    result = recolor.RecolorApp.build_photo_scan_faded_print_image(
                        base,
                        min_area=params["min_area"],
                        noise_suppression=params["noise_suppression"],
                        weak_contrast=params["weak_contrast"],
                        close_lines=params["close_lines"],
                        max_work_edge=1300,
                        progress_callback=worker_progress,
                        cancel_callback=lambda: cancel_event.is_set() or bool(getattr(self, "_busy_cancel_requested", False)),
                    )
                else:
                    # Farbig/Detail sind technisch teurer als Schwarz/Weiß. Begrenzte
                    # Arbeitsgröße verhindert scheinbares Hängen bei großen Scans.
                    if mode == "color":
                        work_edge = 820
                    elif mode == "detail":
                        work_edge = 1050
                    else:
                        work_edge = 1100
                    result = recolor.RecolorApp.build_photo_scan_cleanup_image(
                        base,
                        **params,
                        max_work_edge=work_edge,
                        progress_callback=worker_progress,
                        cancel_callback=lambda: cancel_event.is_set() or bool(getattr(self, "_busy_cancel_requested", False)),
                    )
                    result.variant = mode
                result_queue.put(("result", result))
            except InterruptedError:
                result_queue.put(("cancelled", None))
            except Exception as exc:
                result_queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

        def poll_worker() -> None:
            try:
                while True:
                    kind, payload = result_queue.get_nowait()
                    if kind == "progress":
                        value, key = payload
                        raw_key = str(key)
                        if raw_key.startswith("progress.photo_scan_auto_candidate_step|"):
                            parts = raw_key.split("|", 4)
                            try:
                                inner_key = parts[4] if len(parts) > 4 else ""
                                inner_text = tr(inner_key, default=inner_key)
                                status_text = tr(
                                    "progress.photo_scan_auto_candidate",
                                    index=int(parts[1]),
                                    total=int(parts[2]),
                                    variant=tr(f"step1.photo_scan_mode_{parts[3]}", default=parts[3]),
                                )
                                if inner_text:
                                    status_text = f"{status_text} {inner_text}"
                            except Exception:
                                status_text = raw_key
                        elif raw_key.startswith("progress.photo_scan_auto_candidate|"):
                            parts = raw_key.split("|", 3)
                            try:
                                status_text = tr(
                                    "progress.photo_scan_auto_candidate",
                                    index=int(parts[1]),
                                    total=int(parts[2]),
                                    variant=tr(f"step1.photo_scan_mode_{parts[3]}", default=parts[3]),
                                )
                            except Exception:
                                status_text = raw_key
                        else:
                            status_text = tr(raw_key, default=raw_key)
                        self.set_progress(float(value), status_text)
                    elif kind == "result":
                        result = payload
                        self.set_progress(92, tr("progress.render_preview"))
                        self.special_result_image = result.image
                        self.special_result_mode = "photo_scan"
                        self.edited_image = self.special_result_image.copy()
                        # Bei großen Scans war der letzte Schritt oft nicht die Analyse,
                        # sondern das Rendern der Tk-Vorschau. Deshalb hier bewusst auf
                        # Fit-to-canvas zurücksetzen und die maximale Vorschaufläche
                        # begrenzen, statt mit einem alten Zoomfaktor riesige Bilder zu rendern.
                        try:
                            self.step1_edited_canvas._max_display_pixels = min(
                                int(getattr(self.step1_edited_canvas, "_max_display_pixels", 8_000_000)),
                                8_000_000,
                            )
                        except Exception:
                            pass
                        self.step1_edited_canvas.set_image(self.edited_image, reset_view=True)
                        variant = tr(f"step1.photo_scan_mode_{getattr(result, 'variant', '')}", default=getattr(result, "variant", ""))
                        if not variant:
                            variant = tr(f"step1.photo_scan_mode_{mode}", default=mode)
                        self.photo_scan_status_var.set(
                            tr(
                                "status.photo_scan_done",
                                count=len(result.detected),
                                score=result.analysis.score,
                                noise=result.analysis.background_noise,
                                variant=variant,
                                tech=getattr(result, "technical_score", 0.0),
                            )
                        )
                        self.status_var.set(self.photo_scan_status_var.get())
                        detected_pixels = sum(int(color.pixels) for color in result.detected)
                        total_pixels = max(1, result.image.size[0] * result.image.size[1])
                        detected_ratio = detected_pixels / total_pixels
                        if (
                            result.analysis.score >= 6
                            or result.analysis.small_specks >= 700
                            or result.analysis.color_complexity >= 190
                            or detected_ratio < 0.006
                            or len(result.detected) <= 0
                        ):
                            self.show_problem_image_hint(tr("status.problem_hint_shown"))
                        self.set_progress(100, self.status_var.get())
                        if show_busy:
                            self.close_busy_dialog()
                        return
                    elif kind == "cancelled":
                        self.set_progress(0, tr("status.analysis_cancelled"))
                        if show_busy:
                            self.close_busy_dialog()
                        return
                    elif kind == "error":
                        if show_busy:
                            self.close_busy_dialog()
                        if isinstance(payload, TimeoutError):
                            messagebox.showerror(tr("msg.error"), tr("msg.photo_scan_timeout"))
                        else:
                            messagebox.showerror(tr("msg.error"), tr("msg.photo_scan_error", error=payload))
                        return
            except queue.Empty:
                pass

            if time.monotonic() - started_at > timeout_s:
                cancel_event.set()
                self.set_progress(0, tr("msg.photo_scan_timeout"))
                if show_busy:
                    self.close_busy_dialog()
                messagebox.showerror(tr("msg.error"), tr("msg.photo_scan_timeout"))
                return
            self.after(80, poll_worker)

        self.after(80, poll_worker)

    def clear_logo_mask(self) -> None:
        self.special_result_image = None
        self.special_result_mode = None
        self.photo_scan_status_var.set("")
        self.update_step1_preview()

    def export_intermediate_png(self) -> None:
        self.update_step1_preview()
        if self.edited_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_edit"))
            return
        initial = "workflow_zwischenbild.png"
        if self.current_path:
            initial = f"{self.current_path.stem}_workflow_zwischenbild.png"
        path = filedialog.asksaveasfilename(
            title=tr("msg.export_intermediate_title"),
            defaultextension=".png",
            initialdir=self._initial_dir_from_config("output"),
            initialfile=initial,
            filetypes=[("PNG", "*.png")],
        )
        if not path:
            return
        try:
            self.edited_image.save(path, format="PNG")
            self.output_path_var.set(path)
            self.status_var.set(tr("status.intermediate_saved", path=path))
        except Exception as exc:
            messagebox.showerror(tr("msg.export_error"), str(exc))

    def use_current_preview_as_new_base(self, show_message: bool = False) -> bool:
        """Übernimmt die aktuelle Step-1-Vorschau als neue Arbeitsgrundlage.

        Das ist bewusst etwas anderes als ``use_edited_for_vector``:
        - diese Methode bleibt in Schritt 1
        - das aktuelle bearbeitete Bild wird zum neuen Original
        - Vorbereitungswerte werden neutralisiert, damit sie nicht doppelt wirken
        - danach kann in einem anderen Reiter weitergearbeitet werden
        """
        self.update_step1_preview()
        if self.edited_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_edit"))
            return False

        new_base = _flatten_rgba_to_rgb(self.edited_image).convert("RGBA")
        self.original_image = new_base.copy()
        self.prepared_image = None
        self.special_result_image = None
        self.special_result_mode = None
        self.edited_image = new_base.copy()
        new_base_rgb = np.array(_flatten_rgba_to_rgb(new_base))
        self._perfect_bw_source = (
            self._is_perfect_black_white_array(new_base_rgb)
            or self._is_high_contrast_black_white_array(new_base_rgb)
        )

        # Die Vorschau ist jetzt die neue Quelle. Alle globalen Vorbereitungswerte
        # werden zurückgesetzt, damit Helligkeit/Kontrast/Rotation nicht doppelt
        # auf das bereits erzeugte Zwischenbild angewendet werden.
        try:
            self.prep_brightness_var.set(0)
            self.prep_contrast_var.set(0)
            self.prep_black_var.set(0)
            self.prep_white_var.set(255)
            self.prep_gamma_var.set(1.0)
            self.prep_rotation_var.set(0.0)
        except Exception:
            pass
        if self.preview_after_id:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
            self.preview_after_id = None

        # Automatisch erkannte Farbreihen gehören zum alten Ausgangsbild und werden
        # deshalb geleert. Manuelle Zeilen bleiben bewusst erhalten, falls der Nutzer
        # danach direkt weiter umfärben möchte.
        try:
            self.clear_basic_rows()
        except Exception:
            pass

        self.photo_scan_status_var.set("")
        self.step1_original_canvas.set_image(self.original_image, reset_view=False)
        self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)
        self._update_ai_upscale_original_size_label()
        self.status_var.set(tr("status.preview_base_ready"))
        if show_message:
            messagebox.showinfo(tr("msg.preview_base_title"), tr("msg.preview_base_body"))
        return True

    def use_edited_for_vector(self, show_message: bool = False) -> bool:
        self.update_step1_preview()
        if self.edited_image is None:
            messagebox.showwarning(tr("msg.no_intermediate_title"), tr("msg.no_intermediate_load_first"))
            return False
        rgb_image = _flatten_rgba_to_rgb(self.edited_image)
        self.vector_image_rgb = np.array(rgb_image)
        self.vector_source_from_step1 = True
        self.detected_contours = []
        self.selected_contour_index = None
        self.selected_contour_indices.clear()
        self._step1_transferred_color_rules = False
        # Wenn der Benutzer von Schritt 2 zurückgeht und das Zwischenbild erneut
        # übernimmt, soll die Lineart-Empfehlung wieder erscheinen. So kann er
        # nach Änderungen in Schritt 1 neu zwischen Konturlinien und Farbmaske wählen.
        self._lineart_recommendation_shown = False
        name = "Zwischenbild aus Schritt 1"
        if self.current_path:
            name = f"{self.current_path.name} → bearbeitet"
        self.vector_source_name_var.set(name)
        self.step2_original_canvas.set_image(rgb_image, reset_view=True)
        self.step2_vector_canvas.set_image(None, reset_view=True)

        transferred = self.transfer_step1_target_colors_to_vector_rows()
        if not transferred:
            self.autofill_vector_rows_from_image()

        bw_like = self.is_current_vector_image_bw_like()
        if bw_like:
            self.step2_auto_prompt_pending = False
            if not self._perfect_bw_source:
                self._maybe_recommend_lineart_mode()
        else:
            self.step2_auto_prompt_pending = True

        if not self.output_path_var.get():
            if self.current_path:
                self.output_path_var.set(str(self.current_path.with_suffix(".dxf")))
            else:
                self.output_path_var.set("vektor_export.dxf")
        self.status_var.set(tr("status.vector_source_ready_transferred") if transferred else tr("status.vector_source_ready_autofill"))
        if show_message:
            messagebox.showinfo(tr("msg.accepted_title"), tr("msg.accepted"))
        return True

    # ------------------------------------------------------------------ Schritt 2 Farbübergabe / Lineart-Erkennung
    def _set_preview_mode_key(self, key: str) -> None:
        if key not in PREVIEW_MODE_KEYS:
            return
        self.preview_mode_var.set(key)
        try:
            self.preview_mode_display_var.set(self._preview_label(key))
        except Exception:
            pass

    @staticmethod
    def _is_white_rgb(rgb: RGB) -> bool:
        return int(rgb[0]) >= 245 and int(rgb[1]) >= 245 and int(rgb[2]) >= 245

    @staticmethod
    def _is_black_rgb(rgb: RGB) -> bool:
        return int(rgb[0]) <= 12 and int(rgb[1]) <= 12 and int(rgb[2]) <= 12

    @staticmethod
    def _is_perfect_black_white_array(image_rgb: np.ndarray) -> bool:
        if image_rgb is None or image_rgb.size == 0:
            return False
        arr = image_rgb.astype(np.int16)
        channel_spread = np.max(arr, axis=2) - np.min(arr, axis=2)
        gray = arr.mean(axis=2)
        black = (channel_spread <= 2) & (gray <= 2)
        white = (channel_spread <= 2) & (gray >= 253)
        covered = float((black | white).mean())
        return covered >= 0.995 and bool(black.any()) and bool(white.any())

    @staticmethod
    def _is_high_contrast_black_white_array(image_rgb: np.ndarray) -> bool:
        """Erkennt bereits brauchbare S/W- oder Lineart-Vorlagen mit Antialiasing.

        Die strenge Prüfung oben erkennt nur echte 0/255-Pixel. Viele gute
        Vorlagen haben aber leichte Graukanten oder minimale Kompressionsreste.
        Solche Bilder sollen nicht erst durch Logo-Maske/Foto-Scan laufen,
        sondern direkt 1:1 übernommen werden können.
        """
        if image_rgb is None or image_rgb.size == 0:
            return False
        stats = WorkflowApp._bw_stats_from_array(image_rgb)
        return (
            stats["near_bw"] >= 0.985
            and stats["colored"] <= 0.005
            and stats["dynamic"] >= 170.0
            and stats["near_black"] >= 0.001
            and stats["near_white"] >= 0.050
            and (stats["near_black"] + stats["near_white"]) >= 0.550
        )

    @staticmethod
    def _bw_stats_from_array(image_rgb: np.ndarray) -> dict[str, float]:
        arr = image_rgb.astype(np.float32)
        if arr.size == 0:
            return {"near_bw": 0.0, "near_black": 0.0, "near_white": 0.0, "colored": 1.0, "dynamic": 0.0, "edge_density": 0.0, "aa": 0.0}
        gray = arr.mean(axis=2)
        channel_spread = np.max(arr, axis=2) - np.min(arr, axis=2)
        near_bw = float((channel_spread <= 10).mean())
        near_black = float((gray <= 28).mean())
        near_white = float((gray >= 227).mean())
        colored = float((channel_spread > 24).mean())
        dynamic = float(np.percentile(gray, 95) - np.percentile(gray, 5))
        if gray.shape[0] > 1 and gray.shape[1] > 1:
            grad_x = np.abs(np.diff(gray, axis=1))
            grad_y = np.abs(np.diff(gray, axis=0))
            edge_density = float(((grad_x > 18).mean() + (grad_y > 18).mean()) * 0.5)
        else:
            edge_density = 0.0
        aa = float(((gray > 8) & (gray < 247)).mean())
        return {
            "near_bw": near_bw,
            "near_black": near_black,
            "near_white": near_white,
            "colored": colored,
            "dynamic": dynamic,
            "edge_density": edge_density,
            "aa": aa,
        }

    def is_current_vector_image_bw_like(self) -> bool:
        if self.vector_image_rgb is None:
            return False
        stats = self._bw_stats_from_array(self.vector_image_rgb)
        return (
            stats["near_bw"] >= 0.92
            and stats["colored"] <= 0.015
            and stats["dynamic"] >= 120
            and stats["near_black"] >= 0.01
        )

    def _collect_actual_vector_palette(self, max_colors: int = 96) -> list[tuple[RGB, int, float]]:
        if self.vector_image_rgb is None or self.vector_image_rgb.size == 0:
            return []
        arr = self.vector_image_rgb.reshape(-1, 3)
        colors, counts = np.unique(arr, axis=0, return_counts=True)
        order = np.argsort(-counts)
        total = float(arr.shape[0]) if arr.shape[0] else 1.0
        result: list[tuple[RGB, int, float]] = []
        for idx in order[: max(1, int(max_colors))]:
            rgb = tuple(int(v) for v in colors[int(idx)])
            count = int(counts[int(idx)])
            result.append((rgb, count, (count / total) * 100.0))
        return result

    def _populate_vector_rows_from_palette(self, palette: list[tuple[RGB, int, float]], source_label: str) -> bool:
        if not palette:
            return False
        self.clear_vector_rows()
        motif_profile = self.motif_profile_var.get()
        try:
            current_epsilon = max(0.0, float(str(self.global_epsilon_var.get()).replace(",", ".")))
        except Exception:
            current_epsilon = 0.350
        if motif_profile == "logo" and len(palette) > 2:
            export_epsilon = max(current_epsilon, 1.500)
        elif motif_profile == "organic":
            export_epsilon = min(current_epsilon, 0.250)
        else:
            export_epsilon = current_epsilon
        export_eps_text = f"{export_epsilon:.3f}"
        ignored_eps_text = f"{max(0.350, export_epsilon):.3f}"
        for rgb, _count, percent in palette:
            is_white = self._is_white_rgb(rgb)
            is_black = self._is_black_rgb(rgb)
            name = _known_color_name(rgb)
            safe = (
                name.upper()
                .replace("WEISS", "WHITE")
                .replace("Ä", "AE")
                .replace("Ö", "OE")
                .replace("Ü", "UE")
                .replace(" ", "_")
            )
            rgb_suffix = f"RGB_{rgb[0]:03d}_{rgb[1]:03d}_{rgb[2]:03d}"
            if is_white:
                layer = f"IGNORE_WHITE_{rgb_suffix}"
                export = False
                tol = "130"
                min_area = "0"
                eps = "0.060" if motif_profile != "logo" else export_eps_text
            elif is_black:
                layer = f"CUT_BLACK_{rgb_suffix}"
                export = True
                tol = "190"
                min_area = "0"
                eps = export_eps_text
            else:
                bright_background = all(v >= 235 for v in rgb) and float(percent) >= 20.0
                export = not bright_background
                layer = f"CUT_{safe}_{rgb_suffix}" if export else f"IGNORE_{safe}_{rgb_suffix}"
                tol = "22" if export else "8"
                min_area = "0" if export else "2"
                eps = export_eps_text if export else ignored_eps_text
            self.add_vector_row(name, _rgb_to_text(rgb), tol, layer, export, min_area, eps)
        self._step1_transferred_color_rules = True
        self.sync_global_tolerance_from_rows()
        export_count = sum(1 for row in self.vector_rows if row.export_var.get())
        self.vector_diagnostics_var.set(
            f"{source_label}: {len(self.vector_rows)} Farbregeln erzeugt, davon {export_count} für Export aktiv."
        )
        if self.motif_profile_var.get() != "logo" and (self.is_current_vector_image_bw_like() or len(self.vector_rows) <= 2):
            self._apply_bw_detail_preset()
        return True

    def _collect_step1_target_palette(self) -> list[tuple[RGB, int, float]]:
        if not self.vector_source_from_step1:
            return []

        aggregated: dict[RGB, list[float]] = {}
        try:
            selected_tab = self.nametowidget(self.step1_notebook.select())
        except Exception:
            selected_tab = None

        if selected_tab is self.basic_tab and self.basic_rows:
            for row in self.basic_rows:
                try:
                    if not row.enabled_var.get():
                        continue
                    rgb = row.get_target_rgb()
                    pixels = float(getattr(row.detected, "pixels", 0) or 0)
                    percent = float(getattr(row.detected, "percent", 0.0) or 0.0)
                except Exception:
                    continue
                entry = aggregated.setdefault(rgb, [0.0, 0.0])
                entry[0] += pixels
                entry[1] += percent

        if selected_tab is self.manual_tab and not aggregated and self.manual_rows:
            for row in self.manual_rows:
                try:
                    if not row.enabled_var.get():
                        continue
                    rgb = _parse_rgb_any(row.target_var.get())
                except Exception:
                    continue
                entry = aggregated.setdefault(rgb, [0.0, 0.0])
                entry[0] += 1.0
                entry[1] += 0.0

        palette = [
            (rgb, int(values[0]), float(values[1]))
            for rgb, values in aggregated.items()
        ]
        palette.sort(key=lambda item: item[1], reverse=True)
        return palette

    def transfer_step1_target_colors_to_vector_rows(self) -> bool:
        target_palette = self._collect_step1_target_palette()
        if target_palette and self._populate_vector_rows_from_palette(target_palette, "Zielfarben aus Schritt 1 übernommen"):
            return True

        bw_like = self.is_current_vector_image_bw_like()
        if bw_like and self.vector_image_rgb is not None:
            gray = self.vector_image_rgb.astype(np.float32).mean(axis=2)
            total = float(gray.size) if gray.size else 1.0
            bw_palette: list[tuple[RGB, int, float]] = []
            dark_count = int((gray <= 127).sum())
            light_count = int((gray > 127).sum())
            if dark_count > 0:
                bw_palette.append(((0, 0, 0), dark_count, (dark_count / total) * 100.0))
            if light_count > 0:
                bw_palette.append(((255, 255, 255), light_count, (light_count / total) * 100.0))
            if self._populate_vector_rows_from_palette(bw_palette, "Schwarz/Weiß aus Zwischen-PNG übernommen"):
                return True
        actual_palette = self._collect_actual_vector_palette(max_colors=96)
        if actual_palette and self._populate_vector_rows_from_palette(actual_palette, "Endfarben aus Zwischen-PNG übernommen"):
            return True
        return False

    def _ask_lineart_recommendation(self) -> str | None:
        result = {"value": None}
        dialog = tk.Toplevel(self)
        dialog.title(tr("msg.lineart_recommend_title"))
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dark = bool(self.dark_mode_var.get())
        bg = "#2b2b2b" if dark else "#ffffff"
        fg = "#f3f4f6" if dark else "#111827"
        muted = "#d1d5db" if dark else "#4b5563"
        dialog.configure(bg=bg)
        body = tk.Frame(dialog, bg=bg, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=tr("msg.lineart_recommend_title"),
            bg=bg,
            fg=fg,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        tk.Label(
            body,
            text=tr("msg.lineart_recommend_intro"),
            bg=bg,
            fg=muted,
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(0, 12))
        choice = tk.StringVar(value="contour")
        for key, title, desc in (
            ("contour", tr("preview_mode.contour"), tr("msg.lineart_choice_contour")),
            ("mask", tr("preview_mode.mask"), tr("msg.lineart_choice_mask")),
        ):
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x", anchor="w", pady=4)
            tk.Radiobutton(row, variable=choice, value=key, bg=bg, fg=fg, selectcolor=bg, activebackground=bg, activeforeground=fg).pack(side="left")
            tk.Label(row, text=title, bg=bg, fg=fg, font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side="left")
            tk.Label(row, text=desc, bg=bg, fg=muted, anchor="w", justify="left", wraplength=360).pack(side="left", padx=(4, 0))
        tk.Label(
            body,
            text=tr("msg.lineart_expert_hint"),
            bg=bg,
            fg=muted,
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(12, 6))
        buttons = tk.Frame(body, bg=bg)
        buttons.pack(fill="x", pady=(4, 0))
        def done(value: str | None) -> None:
            result["value"] = value
            dialog.destroy()
        tk.Button(buttons, text=tr("button.cancel"), command=lambda: done(None), padx=12, pady=4).pack(side="right", padx=(6, 0))
        tk.Button(buttons, text=tr("button.apply"), command=lambda: done(choice.get()), bg="#2563eb", fg="white", activebackground="#1d4ed8", activeforeground="white", padx=14, pady=4).pack(side="right")
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        self.wait_window(dialog)
        return result["value"]

    def _maybe_recommend_lineart_mode(self) -> None:
        if self.motif_profile_var.get() == "logo":
            self._lineart_recommendation_shown = True
            return
        if self._lineart_recommendation_shown:
            self._apply_bw_detail_preset()
            return
        self._lineart_recommendation_shown = True
        try:
            choice = self._ask_lineart_recommendation()
        except Exception:
            choice = "contour"
        if choice:
            self._apply_bw_detail_preset()
            self._set_preview_mode_key(choice)
            self.status_var.set(tr("status.lineart_preset_applied"))

    # ------------------------------------------------------------------ Schritt 2 Logik
    def clear_vector_rows(self) -> None:
        for row in self.vector_rows:
            row.destroy()
        if hasattr(self, "vector_table"):
            for child in self.vector_table.winfo_children():
                child.destroy()
        self.vector_rows.clear()
        self.update_vector_color_count()

    def add_vector_row(self, name: str, rgb: str, tolerance: str, layer: str, export: bool, min_area: str, epsilon: str) -> None:
        row_index = len(self.vector_rows) + 1
        row = vector.ColorRow(self.vector_table, row_index, name, rgb, tolerance, layer, export, min_area, epsilon, remove_callback=self.remove_vector_row)
        self.vector_rows.append(row)
        self._bind_vector_row_live_events(row)
        self.update_vector_color_count()

    def add_empty_vector_row(self) -> None:
        self.add_vector_row("Neue Farbe", "255,0,0", "10", "CUT_LAYER", True, "20", "1.5")

    def remove_vector_row(self, row: Any) -> None:
        row.destroy()
        if row in self.vector_rows:
            self.vector_rows.remove(row)
        self.redraw_vector_rows()
        self.update_vector_color_count()

    def update_vector_color_count(self) -> None:
        if hasattr(self, "vector_color_count_var"):
            export_count = sum(1 for row in self.vector_rows if row.export_var.get())
            self.vector_color_count_var.set(f"{len(self.vector_rows)} Farben | Export aktiv: {export_count}")

    def _on_vector_row_value_changed(self, *_args: object) -> None:
        if self.vector_image_rgb is None:
            return
        if self.live_preview_var.get():
            self._schedule_live_preview_if_enabled()

    def _bind_vector_row_live_events(self, row: Any) -> None:
        # Modal-Änderungen (z. B. Toleranz) sollen bei aktivem LIVE-Modus
        # automatisch die Vorschau aktualisieren.
        for var in (
            row.name_var,
            row.rgb_var,
            row.tolerance_var,
            row.layer_var,
            row.export_var,
            row.min_area_var,
            row.epsilon_var,
        ):
            try:
                var.trace_add("write", self._on_vector_row_value_changed)
            except Exception:
                pass

    def sync_global_tolerance_from_rows(self) -> None:
        values: list[int] = []
        for row in self.vector_rows:
            try:
                values.append(int(round(float(str(row.tolerance_var.get()).replace(",", ".")))))
            except Exception:
                continue
        if not values:
            return
        values.sort()
        mid = values[len(values) // 2]
        self.global_tolerance_var.set(str(max(0, min(255, mid))))

    def redraw_vector_rows(self) -> None:
        saved = [(r.name_var.get(), r.rgb_var.get(), r.tolerance_var.get(), r.layer_var.get(), r.export_var.get(), r.min_area_var.get(), r.epsilon_var.get()) for r in self.vector_rows]
        self.clear_vector_rows()
        for data in saved:
            self.add_vector_row(*data)

    @staticmethod
    def _is_bw_profile_name(profile_name: str) -> bool:
        normalized = (profile_name or "").strip().lower().replace("ß", "ss")
        return "schwarz/weiss" in normalized or "schwarz/weiß" in normalized or "black/white" in normalized

    def _apply_bw_detail_preset(self) -> None:
        # Schwarz/Weiss soll feine Details behalten:
        # keine aggressiven Filter, niedrige Punktreduktion, offene Linien erlaubt.
        self.closed_paths_only_var.set(False)
        self.unique_cad_lines_var.set(False)
        self.smooth_contours_var.set(False)
        self.smart_smoothing_var.set(False)
        self.preprocess_vector_var.set(True)
        self.preprocess_blur_var.set(0.0)
        self.preprocess_edge_var.set(0.0)
        self.preprocess_noise_var.set(0.0)
        self.internal_scale_var.set("3")
        self.internal_scale_display_var.set(self._internal_scale_label("3"))
        self.cleanup_mode_var.set("off")
        try:
            self.cleanup_mode_display_var.set(self._cleanup_label("off"))
        except Exception:
            pass
        self.global_tolerance_var.set("180")
        self.min_object_area_mm2_var.set("0")
        self.min_object_percent_var.set("0,00")
        self.global_epsilon_var.set("0.060")

        for row in self.vector_rows:
            rgb_text = str(row.rgb_var.get()).strip().replace(" ", "")
            if rgb_text in ("0,0,0", "0;0;0"):
                row.tolerance_var.set("190")
                row.min_area_var.set("0")
                row.epsilon_var.set("0.060")
                row.export_var.set(True)
                if not row.layer_var.get().strip():
                    row.layer_var.set("CUT_BLACK")
            elif rgb_text in ("255,255,255", "255;255;255"):
                row.tolerance_var.set("130")
                row.min_area_var.set("0")
                row.epsilon_var.set("0.060")
                row.export_var.set(False)
                if not row.layer_var.get().strip():
                    row.layer_var.set("IGNORE_WHITE")
            else:
                row.tolerance_var.set("160")
                row.min_area_var.set("0")
                row.epsilon_var.set("0.060")

    @staticmethod
    def _is_bw_profile_name_safe(profile_name: str) -> bool:
        normalized = (profile_name or "").strip().lower()
        normalized = normalized.replace("ß", "ss").replace("ÃŸ", "ss")
        return "schwarz/weiss" in normalized or "black/white" in normalized

    def _find_bw_profile_key(self) -> Optional[str]:
        for key in vector.PROFILE_ROWS.keys():
            normalized = (key or "").strip().lower()
            normalized = normalized.replace("ß", "ss").replace("ÃŸ", "ss").replace("ÃƒÅ¸", "ss")
            if "schwarz/weiss" in normalized or "black/white" in normalized:
                return key
        return None

    def load_vector_profile(self, profile_name: str) -> None:
        rows = vector.PROFILE_ROWS.get(profile_name)
        if rows is None:
            messagebox.showerror(tr("msg.profile_title"), tr("msg.profile_unknown", profile=profile_name))
            return
        self.clear_vector_rows()
        for row_data in rows:
            self.add_vector_row(*row_data)
        bw_profile_key = self._find_bw_profile_key()
        if bw_profile_key and profile_name == bw_profile_key:
            self._apply_bw_detail_preset()
        self.sync_global_tolerance_from_rows()
        self.status_var.set(tr("status.profile_loaded", profile=profile_name))

    def apply_profile_and_preview(self) -> None:
        self.load_vector_profile(self.profile_var.get())
        if self.live_preview_var.get():
            self._schedule_live_preview_if_enabled()

    def apply_modal_profile_only(self) -> None:
        self.load_vector_profile(self.profile_var.get())
        messagebox.showinfo(tr("msg.profile_apply_title"), tr("msg.profile_apply_body"))
        if self.live_preview_var.get():
            self._schedule_live_preview_if_enabled()

    def on_profile_selected(self) -> None:
        self.load_vector_profile(self.profile_var.get())
        if self.vector_image_rgb is None:
            return
        if self.live_preview_var.get():
            self._schedule_live_preview_if_enabled()

    def _schedule_live_preview_if_enabled(self, *_args: object) -> None:
        if self._suspend_live_preview:
            return
        # WICHTIG: Live-Vorschau nur wenn Checkbox aktiviert ist
        if not self.live_preview_var.get():
            return
        # Die Punkt-/Linienanzeige ist eine reine technische Prognose und soll
        # auch dann aktualisiert werden, wenn die große Vorschau nicht live neu
        # berechnet wird. Dadurch sieht man sofort, ob Epsilon, Ankerpunkt-
        # Bereinigung oder Doppellinien-Cleanup die Exportdaten verändert.
        if self.vector_image_rgb is not None and self.detected_contours:
            try:
                self._update_cad_point_count()
            except Exception:
                pass
        if self.vector_image_rgb is None:
            return
        if _args and str(_args[0]) == str(self.anchor_neighbor_distance_var) and not self.remove_loose_points_var.get():
            return
        if _args and str(_args[0]) in (str(self.global_epsilon_var), str(self.anchor_neighbor_distance_var)):
            if self._apply_cad_deviation_live_only():
                return
        if self.step2_live_after_id:
            try:
                self.after_cancel(self.step2_live_after_id)
            except Exception:
                pass
        self.step2_live_after_id = self.after(280, lambda: self.detect_and_preview_vector(live=True))

    def _clone_contour_with_points_for_count(self, contour: Any, points: list[Tuple[float, float]]) -> Any:
        """Erzeugt eine leichte Kontur-Kopie für technische Zählungen.

        Die eigentlichen erkannten Konturen bleiben unverändert. Dadurch kann die
        Punkt-/Linienanzeige live berechnet werden, ohne sofort das reale
        Vektorergebnis oder die Vorschaupfade umzuschreiben.
        """
        return vector.DetectedContour(
            contour.rule,
            list(points),
            float(getattr(contour, "area", 0.0) or 0.0),
            bool(getattr(contour, "closed", True)),
            bool(getattr(contour, "is_hole", False)),
            list(getattr(contour, "raw_points", None) or getattr(contour, "points", []) or []),
        )

    def _estimated_export_contours_for_current_cad_settings(self) -> List[Any]:
        """Berechnet eine nicht-destruktive Export-Prognose für die Anzeige.

        Berücksichtigt werden hier vor allem die letzten CAD-/Vorexport-
        Einstellungen: globale CAD-Abweichung, nahe Ankerpunkte und die daraus
        entstehende Punktzahl. Doppellinien werden anschließend als Linien-
        Segmente gezählt, weil sie nicht die Punktzahl eines Pfads verändern,
        sondern die exportierten CAD-Segmente reduzieren.
        """
        if not self.detected_contours:
            return []
        try:
            epsilon = max(0.0, float(str(self.global_epsilon_var.get()).replace(",", ".")))
        except Exception:
            epsilon = 0.0
        estimated: List[Any] = []
        for item in self.detected_contours:
            raw_points = getattr(item, "raw_points", None) or getattr(item, "points", []) or []
            points = [(float(x), float(y)) for x, y in raw_points]
            if epsilon > 0.0 and len(points) >= 2:
                try:
                    points = vector.approximate_points(points, epsilon, closed=bool(getattr(item, "closed", True)))
                except Exception:
                    points = [(float(x), float(y)) for x, y in getattr(item, "points", []) or []]
            estimated.append(self._clone_contour_with_points_for_count(item, points))
        try:
            if self.remove_loose_points_var.get() and self.get_anchor_neighbor_distance_px() > 0.0:
                estimated = vector.remove_neighbor_anchor_points_from_contours(
                    estimated,
                    min_distance_px=self.get_anchor_neighbor_distance_px(),
                )
        except Exception:
            pass
        return estimated

    def _count_export_segments_for_display(self, contours: List[Any]) -> tuple[int, int]:
        """Zählt CAD-Segmente vor und nach optionalem Doppellinien-Cleanup."""
        if not contours:
            return 0, 0
        try:
            segment_count = vector.count_export_line_segments(contours)
        except Exception:
            segment_count = 0
        unique_count = segment_count
        if self.unique_cad_lines_var.get():
            try:
                unique_count = len(
                    vector.unique_line_segments_from_contours(
                        contours,
                        tolerance_px=self.get_duplicate_line_tolerance_px(),
                    )
                )
            except Exception:
                unique_count = segment_count
        return int(segment_count), int(unique_count)

    def _update_cad_point_count(self) -> None:
        """Aktualisiert die technische Punkt-/Linienanzeige für Schritt 2.

        Die Punktzahl beschreibt die Polylines nach der aktuellen CAD-
        Vereinfachung. Doppellinien-Cleanup verändert dagegen primär die Anzahl
        der exportierten CAD-Liniensegmente; deshalb wird dieser Wert separat
        angezeigt.
        """
        if not self.detected_contours:
            self.cad_point_count_var.set("")
            return
        raw_points = sum(len(getattr(c, "raw_points", None) or getattr(c, "points", []) or []) for c in self.detected_contours if c.rule.export)
        current_points = sum(len(getattr(c, "points", []) or []) for c in self.detected_contours if c.rule.export)
        estimated_contours = self._estimated_export_contours_for_current_cad_settings()
        estimated_points = sum(len(getattr(c, "points", []) or []) for c in estimated_contours if c.rule.export)
        segments_before, segments_after = self._count_export_segments_for_display(estimated_contours)
        if self.unique_cad_lines_var.get():
            self.cad_point_count_var.set(
                f"Punkte: {raw_points} → {estimated_points} | CAD-Linien: {segments_before} → {segments_after}"
            )
        else:
            # Wenn die Prognose der aktuellen realen Kontur entspricht, reicht die
            # gewohnte kurze Anzeige. Bei geänderter CAD-Abweichung wird die
            # erwartete Export-Punktzahl zusätzlich sichtbar.
            if estimated_points != current_points:
                self.cad_point_count_var.set(
                    f"Punkte: {raw_points} → {estimated_points} | aktuell {current_points} | CAD-Linien: {segments_before}"
                )
            else:
                self.cad_point_count_var.set(
                    f"Punkte: {raw_points} → {current_points} | CAD-Linien: {segments_before}"
                )

    def _set_all_vector_epsilons(self, epsilon: float) -> None:
        value = f"{max(0.0, float(epsilon)):.2f}"
        self._suspend_live_preview = True
        try:
            self.global_epsilon_var.set(value)
            for row in self.vector_rows:
                row.epsilon_var.set(value)
        finally:
            self._suspend_live_preview = False

    def _apply_cad_deviation_to_detected(self, epsilon: float) -> bool:
        changed = False
        for item in self.detected_contours:
            raw = getattr(item, "raw_points", None)
            if raw and len(raw) >= 2:
                item.points = vector.approximate_points(raw, epsilon, closed=item.closed)
                changed = True
        anchor_distance = self.get_anchor_neighbor_distance_px()
        if changed and self.remove_loose_points_var.get() and anchor_distance > 0.0:
            self.detected_contours = vector.remove_neighbor_anchor_points_from_contours(
                self.detected_contours,
                min_distance_px=anchor_distance,
            )
        if changed:
            self._update_cad_point_count()
        return changed

    def _draw_cad_cleanup_preview_image(self, epsilon: Optional[float], use_raw: bool) -> Image.Image:
        if self.vector_image_rgb is None:
            return Image.new("RGB", (800, 600), (255, 255, 255))
        h, w = self.vector_image_rgb.shape[:2]
        image = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        for item in self.detected_contours:
            if not item.rule.export:
                continue
            source_points = item.raw_points if use_raw and item.raw_points else item.raw_points or item.points
            if not source_points or len(source_points) < 2:
                continue
            if use_raw:
                pts = [(float(x), float(y)) for x, y in source_points]
                color = (150, 150, 150)
                width = 1
            else:
                pts = vector.approximate_points(source_points, max(0.0, float(epsilon or 0.0)), closed=item.closed)
                color = tuple(int(c) for c in item.rule.rgb)
                width = 2
            if item.closed and len(pts) >= 3:
                pts = pts + [pts[0]]
            if len(pts) >= 2:
                draw.line(pts, fill=color, width=width, joint="curve")
        return image

    def open_cad_cleanup_dialog(self) -> None:
        if not self.detected_contours:
            messagebox.showwarning(tr("msg.no_contours_title"), tr("status.no_contours_detected"))
            return
        dialog = tk.Toplevel(self)
        dialog.title(tr("step2.cad_cleanup_title"))
        dialog.transient(self)
        dialog.geometry("1100x720")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        controls = ttk.Frame(dialog, padding=8)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        local_near = tk.StringVar(value="0.00")
        local_epsilon = tk.StringVar(value="0.00")
        local_tolerance_mm = tk.StringVar(value=self.cad_tolerance_mm_var.get() or "0.03")
        local_live = tk.BooleanVar(value=True)
        local_show_anchors = tk.BooleanVar(value=True)
        local_anchor_radius = tk.StringVar(value="2.50")
        local_use_percent = tk.BooleanVar(value=False)
        local_unit_state = {"percent": False}
        reference_length_px = 1000.0
        if self.vector_image_rgb is not None:
            h, w = self.vector_image_rgb.shape[:2]
            reference_length_px = float(max(1, w, h))
        simplified_contours: List[Any] = []
        before_preview_image: Optional[Image.Image] = None
        local_update_after_id: Optional[str] = None
        pending_refresh_before = False

        ttk.Checkbutton(
            controls,
            text=tr("step2.use_percent_values"),
            variable=local_use_percent,
            command=lambda: on_unit_mode_changed(),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        near_label = ttk.Label(controls, text=tr("step2.anchor_min_distance"))
        near_label.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        near_scale = ttk.Scale(
            controls,
            from_=0.0,
            to=100.0,
            orient="horizontal",
            command=lambda value: on_value_changed(local_near, value),
        )
        near_scale.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 4))
        near_spin = ttk.Spinbox(controls, from_=0.0, to=100.0, increment=0.01, textvariable=local_near, width=8, format="%.2f")
        near_spin.grid(row=1, column=2, sticky="w", pady=(0, 4))

        epsilon_label = ttk.Label(controls, text=tr("step2.cad_deviation"))
        epsilon_label.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        epsilon_scale = ttk.Scale(
            controls,
            from_=0.0,
            to=100.0,
            orient="horizontal",
            command=lambda value: on_value_changed(local_epsilon, value),
        )
        epsilon_scale.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(0, 4))
        epsilon_spin = ttk.Spinbox(controls, from_=0.0, to=100.0, increment=0.01, textvariable=local_epsilon, width=8, format="%.2f")
        epsilon_spin.grid(row=2, column=2, sticky="w", pady=(0, 4))

        tolerance_mm_label = ttk.Label(controls, text=tr("step2.cad_tolerance_mm"))
        tolerance_mm_label.grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        tolerance_mm_scale = ttk.Scale(
            controls,
            from_=0.0,
            to=1.0,
            orient="horizontal",
            command=lambda value: on_value_changed(local_tolerance_mm, value, decimals=3),
        )
        tolerance_mm_scale.grid(row=3, column=1, sticky="ew", padx=(0, 8), pady=(0, 4))
        tolerance_mm_spin = ttk.Spinbox(controls, from_=0.0, to=10.0, increment=0.001, textvariable=local_tolerance_mm, width=8, format="%.3f")
        tolerance_mm_spin.grid(row=3, column=2, sticky="w", pady=(0, 4))

        ttk.Checkbutton(controls, text=tr("step2.live_preview"), variable=local_live).grid(row=4, column=0, sticky="w", pady=(4, 0))
        manual_refresh = tk.Button(
            controls,
            text=tr("step2.manual_refresh"),
            command=lambda: update_images(force=True),
            bg="#15803d",
            fg="white",
            activebackground="#166534",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=4,
        )
        manual_refresh.grid(row=4, column=1, sticky="w", pady=(4, 0))
        point_label = ttk.Label(controls, text="")
        point_label.grid(row=4, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=(4, 0))
        ttk.Checkbutton(
            controls,
            text=tr("step2.show_anchor_points"),
            variable=local_show_anchors,
            command=lambda: schedule_update(refresh_before=True),
        ).grid(row=5, column=0, sticky="w", pady=(4, 0))
        ttk.Label(controls, text=tr("step2.anchor_point_size")).grid(row=6, column=0, sticky="w", padx=(0, 8), pady=(4, 0))
        anchor_size_scale = ttk.Scale(
            controls,
            from_=1.0,
            to=12.0,
            orient="horizontal",
            command=lambda value: on_anchor_radius_changed(value),
        )
        anchor_size_scale.grid(row=6, column=1, sticky="ew", padx=(0, 8), pady=(4, 0))
        anchor_size_spin = ttk.Spinbox(controls, from_=1.0, to=12.0, increment=0.25, textvariable=local_anchor_radius, width=8, format="%.2f")
        anchor_size_spin.grid(row=6, column=2, sticky="w", pady=(4, 0))

        panes = ttk.Panedwindow(dialog, orient=tk.HORIZONTAL)
        panes.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        before_canvas = recolor.ZoomImageCanvas(panes, tr("step2.cad_cleanup_before"))
        after_canvas = recolor.ZoomImageCanvas(panes, tr("step2.cad_cleanup_after"))
        panes.add(before_canvas, weight=1)
        panes.add(after_canvas, weight=1)

        buttons = ttk.Frame(dialog, padding=(8, 0, 8, 8))
        buttons.grid(row=2, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)

        def display_value_to_px(text: str, percent: bool) -> float:
            try:
                value = max(0.0, float(str(text).replace(",", ".")))
            except Exception:
                return 0.0
            if percent:
                return (value / 100.0) * reference_length_px
            return value

        def px_to_display_value(px_value: float, percent: bool) -> float:
            value = max(0.0, float(px_value))
            if percent:
                return (value / reference_length_px) * 100.0
            return value

        def current_near_distance() -> float:
            return display_value_to_px(local_near.get(), local_unit_state["percent"])

        def current_epsilon() -> float:
            return display_value_to_px(local_epsilon.get(), local_unit_state["percent"])

        def current_mm_tolerance_px() -> float:
            try:
                tolerance_mm = max(0.0, float(str(local_tolerance_mm.get()).replace(",", ".")))
                pixel_to_mm = self.get_pixel_to_mm()
            except Exception:
                return 0.0
            if pixel_to_mm <= 0.0:
                return 0.0
            return tolerance_mm / pixel_to_mm

        def refresh_unit_labels() -> None:
            suffix = "%" if local_unit_state["percent"] else "px"
            near_base = tr("step2.anchor_min_distance").replace(" px", "").replace(" %", "")
            epsilon_base = tr("step2.cad_deviation").replace(" px", "").replace(" %", "")
            near_label.configure(text=f"{near_base} {suffix}")
            epsilon_label.configure(text=f"{epsilon_base} {suffix}")

        def configure_value_controls() -> None:
            if local_unit_state["percent"]:
                limit = 5.0
                increment = 0.01
            else:
                limit = 100.0
                increment = 0.01
            for scale in (near_scale, epsilon_scale):
                scale.configure(from_=0.0, to=limit)
            for spin in (near_spin, epsilon_spin):
                spin.configure(from_=0.0, to=limit, increment=increment)
            refresh_unit_labels()

        def on_unit_mode_changed() -> None:
            old_percent = local_unit_state["percent"]
            near_px = display_value_to_px(local_near.get(), old_percent)
            epsilon_px = display_value_to_px(local_epsilon.get(), old_percent)
            local_unit_state["percent"] = bool(local_use_percent.get())
            configure_value_controls()
            local_near.set(f"{px_to_display_value(near_px, local_unit_state['percent']):.2f}")
            local_epsilon.set(f"{px_to_display_value(epsilon_px, local_unit_state['percent']):.2f}")
            near_scale.set(float(local_near.get().replace(",", ".")))
            epsilon_scale.set(float(local_epsilon.get().replace(",", ".")))
            schedule_update()

        def current_anchor_radius() -> float:
            try:
                return max(1.0, min(20.0, float(str(local_anchor_radius.get()).replace(",", "."))))
            except Exception:
                return 2.5

        def clone_with_points(item: Any, points: List[Tuple[float, float]]) -> Any:
            return vector.DetectedContour(
                rule=item.rule,
                points=points,
                area=float(getattr(item, "area", 0.0) or 0.0),
                closed=bool(getattr(item, "closed", True)),
                is_hole=bool(getattr(item, "is_hole", False)),
                raw_points=list(getattr(item, "points", []) or []),
            )

        def simplify_current_contours() -> List[Any]:
            near_distance = current_near_distance()
            epsilon = max(current_epsilon(), current_mm_tolerance_px())
            result: List[Any] = []
            for item in self.detected_contours:
                points = [(float(x), float(y)) for x, y in getattr(item, "points", [])]
                if near_distance > 0.0:
                    points = vector.remove_neighbor_anchor_points(points, near_distance, closed=bool(getattr(item, "closed", True)))
                if epsilon > 0.0:
                    points = vector.approximate_points(points, epsilon, closed=bool(getattr(item, "closed", True)))
                result.append(clone_with_points(item, points))
            return result

        def draw_dialog_anchor_points(image: Image.Image, contours: List[Any]) -> None:
            if not local_show_anchors.get():
                return
            draw = ImageDraw.Draw(image)
            radius = current_anchor_radius()
            for item in contours:
                if not getattr(item.rule, "export", True):
                    continue
                for x, y in getattr(item, "points", []) or []:
                    cx = float(x)
                    cy = float(y)
                    draw.ellipse(
                        (cx - radius, cy - radius, cx + radius, cy + radius),
                        fill=(255, 204, 0),
                        outline=(17, 17, 17),
                    )

        def draw_dialog_path_lines(image: Image.Image, contours: List[Any]) -> None:
            """Zeichnet die echten Verbindungslinien zusätzlich unter die Ankerpunkte.

            Die Objektvorschau zeigt viele Strukturen als gefüllte Masken. Im
            Vereinfachungsdialog ist aber wichtig zu sehen, ob Punkte wirklich
            innerhalb desselben Pfades verbunden sind. Deshalb wird hier eine
            klare schwarze Pfadlinie mit hellem Unterzug gezeichnet, bevor die
            gelben Ankerpunkte darübergelegt werden.
            """
            draw = ImageDraw.Draw(image)
            for item in contours:
                if not getattr(item.rule, "export", True):
                    continue
                points = [(float(x), float(y)) for x, y in (getattr(item, "points", []) or [])]
                if len(points) < 2:
                    continue
                line = points + [points[0]] if bool(getattr(item, "closed", False)) and len(points) >= 3 else points
                draw.line(line, fill=(255, 255, 255), width=4, joint="curve")
                draw.line(line, fill=(0, 0, 0), width=2, joint="curve")

        def preview_image_for(contours: List[Any]) -> Image.Image:
            original = self.detected_contours
            original_selected = self.selected_contour_indices
            original_selected_index = self.selected_contour_index
            try:
                self.detected_contours = contours
                self.selected_contour_indices = set()
                self.selected_contour_index = None
                image = self.build_object_check_preview_image()
                draw_dialog_path_lines(image, contours)
                draw_dialog_anchor_points(image, contours)
                return image
            finally:
                self.detected_contours = original
                self.selected_contour_indices = original_selected
                self.selected_contour_index = original_selected_index

        def update_images(force: bool = False, refresh_before: bool = False) -> None:
            nonlocal simplified_contours, before_preview_image, local_update_after_id, pending_refresh_before
            if local_update_after_id:
                try:
                    dialog.after_cancel(local_update_after_id)
                except Exception:
                    pass
            local_update_after_id = None
            refresh_before = refresh_before or pending_refresh_before
            pending_refresh_before = False
            if not force and not local_live.get():
                return
            simplified_contours = simplify_current_contours()
            if before_preview_image is None or refresh_before:
                before_preview_image = preview_image_for(self.detected_contours)
            if before_canvas.image is None or refresh_before:
                before_canvas.set_image(before_preview_image, reset_view=before_canvas.image is None)
            after_canvas.set_image(preview_image_for(simplified_contours), reset_view=after_canvas.image is None)
            before = sum(len(item.points) for item in self.detected_contours if item.rule.export)
            after = sum(len(item.points) for item in simplified_contours if item.rule.export)
            mm_px = current_mm_tolerance_px()
            point_label.configure(text=tr("status.cad_points", before=before, after=after) + f" | {mm_px:.2f}px aus mm")

        def schedule_update(refresh_before: bool = False) -> None:
            nonlocal local_update_after_id, pending_refresh_before
            if not local_live.get() and not refresh_before:
                return
            pending_refresh_before = pending_refresh_before or refresh_before
            if local_update_after_id:
                try:
                    dialog.after_cancel(local_update_after_id)
                except Exception:
                    pass
            local_update_after_id = dialog.after(140, lambda: update_images(force=True))

        def on_value_changed(variable: tk.StringVar, value: object, decimals: int = 2) -> None:
            self._set_numeric_var(variable, str(value), decimals)
            schedule_update()

        def on_anchor_radius_changed(value: object) -> None:
            self._set_numeric_var(local_anchor_radius, str(value), 2)
            schedule_update(refresh_before=True)

        def on_spin_changed(_event: object = None) -> None:
            update_images(force=True)

        def apply_and_close() -> None:
            nonlocal simplified_contours
            if not simplified_contours:
                simplified_contours = simplify_current_contours()
            before = sum(len(item.points) for item in self.detected_contours if item.rule.export)
            after = sum(len(item.points) for item in simplified_contours if item.rule.export)
            epsilon = current_epsilon()
            self.cad_tolerance_mm_var.set(local_tolerance_mm.get())
            self.detected_contours = simplified_contours
            self._update_cad_point_count()
            self.render_vector_preview()
            self.status_var.set(tr("status.cad_cleanup_applied", value=f"{epsilon:.2f}") + f" | {before} → {after}")
            dialog.destroy()

        near_spin.bind("<Return>", on_spin_changed)
        near_spin.bind("<FocusOut>", on_spin_changed)
        epsilon_spin.bind("<Return>", on_spin_changed)
        epsilon_spin.bind("<FocusOut>", on_spin_changed)
        tolerance_mm_spin.bind("<Return>", on_spin_changed)
        tolerance_mm_spin.bind("<FocusOut>", on_spin_changed)
        anchor_size_spin.bind("<Return>", lambda _event: update_images(force=True, refresh_before=True))
        anchor_size_spin.bind("<FocusOut>", lambda _event: update_images(force=True, refresh_before=True))
        ttk.Button(buttons, text=tr("button.apply"), command=apply_and_close).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Button(buttons, text=tr("button.cancel"), command=dialog.destroy).grid(row=0, column=2, sticky="e", padx=(8, 0))

        configure_value_controls()
        near_scale.set(float(local_near.get().replace(",", ".")))
        epsilon_scale.set(float(local_epsilon.get().replace(",", ".")))
        try:
            tolerance_mm_scale.set(min(1.0, float(local_tolerance_mm.get().replace(",", "."))))
        except Exception:
            tolerance_mm_scale.set(0.03)
        anchor_size_scale.set(current_anchor_radius())
        update_images(force=True)

    def _apply_cad_deviation_live_only(self) -> bool:
        if not self.detected_contours:
            return False
        if (
            self.smooth_contours_var.get()
            or self.smart_smoothing_var.get()
            or self.bridge_tabs_var.get()
            or abs(self.get_hole_scale_factor() - 1.0) > 1e-6
        ):
            return False
        try:
            epsilon = max(0.0, float(str(self.global_epsilon_var.get()).replace(",", ".")))
        except Exception:
            return False
        self._set_all_vector_epsilons(epsilon)
        if not self._apply_cad_deviation_to_detected(epsilon):
            return False
        if self.step2_live_after_id:
            try:
                self.after_cancel(self.step2_live_after_id)
            except Exception:
                pass
        self.step2_live_after_id = self.after(80, self.render_vector_preview)
        return True

    def autofill_vector_rows_from_image(self) -> None:
        """Erzeugt die Farb-/Layer-Tabelle aus dem aktuell geladenen Bild.

        Bei Schwarz/Weiß-Zwischenbildern entstehen bewusst nur zwei Regeln:
        Schwarz = Export, Weiß = Ignore. Mehrfarbige technische Zwischenbilder
        übernehmen ihre echten Endfarben aus dem PNG.
        """
        if self.vector_image_rgb is None:
            return

        if self.transfer_step1_target_colors_to_vector_rows():
            return

        image = Image.fromarray(self.vector_image_rgb.astype(np.uint8), "RGB")
        detected = recolor.RecolorApp.detect_motif_colors_by_threshold(
            image,
            threshold=30,
            min_area=3,
            max_colors=12,
            alpha_min=0,
            noise_suppression=max(0, min(100, int(self.basic_noise_var.get()))),
        )
        if len(detected) < 2:
            detected = recolor.RecolorApp.detect_colors_by_threshold(
                image,
                threshold=18,
                min_area=1,
                max_colors=32,
                alpha_min=0,
            )
        palette = [
            (tuple(int(v) for v in item.source_rgb), int(getattr(item, "pixels", 0)), float(getattr(item, "percent", 0.0)))
            for item in detected
        ]
        if self._populate_vector_rows_from_palette(palette, "Auto-Farben aus Bild"):
            return

        self.load_vector_profile("Standard")
        self.vector_diagnostics_var.set("Keine Farben erkannt; Standardprofil geladen.")

    def load_vector_png_direct(self) -> None:
        path = filedialog.askopenfilename(
            title="PNG für Vektorisierung laden",
            initialdir=self._initial_dir_from_config("input"),
            filetypes=[("PNG", "*.png"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        self._remember_input_path(path)
        try:
            img = Image.open(path).convert("RGB")
            self.vector_image_rgb = np.array(img)
            self.vector_source_from_step1 = False
            self.step2_auto_prompt_pending = True
            self.vector_source_name_var.set(Path(path).name)
            self.step2_original_canvas.set_image(img, reset_view=True)
            self.step2_vector_canvas.set_image(None, reset_view=True)
            if not self.output_path_var.get():
                self.output_path_var.set(str(Path(path).with_suffix(".dxf")))
            self.autofill_vector_rows_from_image()
            self.status_var.set(tr("status.png_loaded", name=Path(path).name))
        except Exception as exc:
            messagebox.showerror(tr("msg.load_error"), str(exc))

    def choose_vector_output(self) -> None:
        current_output = self.output_path_var.get().strip()
        initial_file = Path(current_output).name if current_output else "vektor_export.dxf"
        if self.current_path and not current_output:
            initial_file = f"{self.current_path.stem}.dxf"
        path = filedialog.asksaveasfilename(
            title="Output speichern",
            defaultextension=".dxf",
            initialdir=self._initial_dir_from_config("output"),
            initialfile=initial_file,
            filetypes=[("DXF-Datei", "*.dxf"), ("SVG-Datei", "*.svg"), ("Alle Dateien", "*.*")],
        )
        if path:
            self.output_path_var.set(path)
            self._save_user_config()

    def get_vector_rules(self) -> List[Any]:
        return [row.to_rule() for row in self.vector_rows]

    def get_pixel_to_mm(self) -> float:
        value = float(self.pixel_to_mm_var.get().replace(",", "."))
        if value <= 0:
            raise ValueError("Pixel zu mm muss größer als 0 sein.")
        return value

    @staticmethod
    def _parse_optional_float(text: object) -> float:
        raw = str(text or "").strip()
        if not raw:
            return 0.0
        try:
            return max(0.0, float(raw.replace(",", ".")))
        except Exception:
            return 0.0

    def get_cad_tolerance_mm(self) -> float:
        return self._parse_optional_float(self.cad_tolerance_mm_var.get())

    def get_cad_tolerance_px_from_mm(self) -> float:
        tolerance_mm = self.get_cad_tolerance_mm()
        if tolerance_mm <= 0.0:
            return 0.0
        try:
            pixel_to_mm = self.get_pixel_to_mm()
        except Exception:
            return 0.0
        if pixel_to_mm <= 0.0:
            return 0.0
        return tolerance_mm / pixel_to_mm

    def get_vector_bbox_px(self) -> Optional[Tuple[float, float, float, float]]:
        points: list[Tuple[float, float]] = []
        for item in self.detected_contours:
            if not getattr(item.rule, "export", True):
                continue
            for x, y in getattr(item, "points", []) or []:
                points.append((float(x), float(y)))
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            min_x = min(xs)
            min_y = min(ys)
            max_x = max(xs)
            max_y = max(ys)
            return min_x, min_y, max(0.0, max_x - min_x), max(0.0, max_y - min_y)
        if self.vector_image_rgb is not None:
            h, w = self.vector_image_rgb.shape[:2]
            return 0.0, 0.0, float(w), float(h)
        return None

    def update_vector_bbox_info(self) -> None:
        bbox = self.get_vector_bbox_px()
        if not bbox:
            self.vector_bbox_info_var.set("")
            return
        _x, _y, width_px, height_px = bbox
        text = f"{width_px:.0f} x {height_px:.0f} px"
        try:
            pixel_to_mm = self.get_pixel_to_mm()
        except Exception:
            pixel_to_mm = 0.0
        if pixel_to_mm > 0.0:
            text += f" | {width_px * pixel_to_mm:.3f} x {height_px * pixel_to_mm:.3f} mm"
        self.vector_bbox_info_var.set(text)

    def apply_target_size_to_scale(self) -> None:
        bbox = self.get_vector_bbox_px()
        if not bbox:
            messagebox.showwarning(tr("msg.no_contours_title"), tr("status.no_contours_detected"))
            return
        _x, _y, width_px, height_px = bbox
        if width_px <= 0.0 or height_px <= 0.0:
            messagebox.showwarning(tr("msg.no_bbox_title"), tr("msg.no_bbox_body"))
            return
        target_w = self._parse_optional_float(self.target_width_mm_var.get())
        target_h = self._parse_optional_float(self.target_height_mm_var.get())
        if target_w <= 0.0 and target_h <= 0.0:
            messagebox.showwarning(tr("msg.target_size_title"), tr("msg.target_size_body"))
            return
        if target_w > 0.0:
            pixel_to_mm = target_w / width_px
            if target_h <= 0.0:
                target_h = height_px * pixel_to_mm
                self.target_height_mm_var.set(f"{target_h:.3f}")
        else:
            pixel_to_mm = target_h / height_px
            target_w = width_px * pixel_to_mm
            self.target_width_mm_var.set(f"{target_w:.3f}")
        self.pixel_to_mm_var.set(f"{pixel_to_mm:.8f}")
        self.update_vector_bbox_info()
        tolerance_px = self.get_cad_tolerance_px_from_mm()
        self.status_var.set(tr("status.scale_calculated", pixel_to_mm=f"{pixel_to_mm:.8f}", tolerance_px=f"{tolerance_px:.2f}"))

    def get_min_object_area_mm2(self) -> float:
        text = self.min_object_area_mm2_var.get().strip()
        return max(0.0, float(text.replace(",", "."))) if text else 0.0

    def get_min_object_percent(self) -> float:
        text = self.min_object_percent_var.get().strip()
        return max(0.0, float(text.replace(",", "."))) if text else 0.0

    def get_smooth_iterations(self) -> int:
        if not self.smooth_contours_var.get():
            return 0
        text = self.smooth_strength_var.get().strip()
        return min(5, max(0, int(float(text.replace(",", "."))))) if text else 0

    def apply_manual_smoothing_if_enabled(self, contours: List[Any], iterations: Optional[int] = None) -> List[Any]:
        smooth_iterations = self.get_smooth_iterations() if iterations is None else max(0, min(5, int(iterations)))
        if smooth_iterations <= 0:
            return contours
        return vector.smooth_contours(contours, smooth_iterations)

    def get_preprocess_blur(self) -> float:
        return min(3.0, max(0.0, float(str(self.preprocess_blur_var.get()).replace(",", "."))))

    def get_preprocess_edge_smoothing(self) -> float:
        return min(5.0, max(0.0, float(str(self.preprocess_edge_var.get()).replace(",", "."))))

    def get_preprocess_noise_area(self) -> float:
        return min(50.0, max(0.0, float(str(self.preprocess_noise_var.get()).replace(",", "."))))

    def get_internal_scale(self) -> int:
        if not self.preprocess_vector_var.get():
            return 1
        try:
            return max(1, min(3, int(self.internal_scale_var.get())))
        except Exception:
            return 1

    def get_smart_corner_angle(self) -> float:
        text = self.smart_corner_angle_var.get().strip()
        return min(120.0, max(10.0, float(text.replace(",", ".")))) if text else 45.0

    def get_smart_line_tolerance_px(self) -> float:
        text = self.smart_line_tolerance_var.get().strip()
        return min(5.0, max(0.2, float(text.replace(",", ".")))) if text else 1.0

    def get_smart_curve_strength(self) -> int:
        text = self.smart_curve_strength_var.get().strip()
        return min(5, max(0, int(float(text.replace(",", "."))))) if text else 2

    def get_hole_scale_factor(self) -> float:
        text = self.hole_scale_var.get().strip()
        return min(1.5, max(0.5, float(text.replace(",", ".")))) if text else 1.0

    def get_bridge_count(self) -> int:
        text = self.bridge_count_var.get().strip()
        if not text:
            return 2
        return max(1, min(8, int(round(float(text.replace(",", "."))))))

    def get_bridge_width_px(self) -> float:
        widths: List[float] = []
        mm_text = self.bridge_width_mm_var.get().strip()
        percent_text = self.bridge_width_percent_var.get().strip()
        try:
            mm = max(0.0, float(mm_text.replace(",", "."))) if mm_text else 0.0
        except Exception:
            mm = 0.0
        try:
            percent = max(0.0, float(percent_text.replace(",", "."))) if percent_text else 0.0
        except Exception:
            percent = 0.0

        pixel_to_mm = max(0.0001, self.get_pixel_to_mm())
        if mm > 0:
            widths.append(mm / pixel_to_mm)
        if percent > 0 and self.vector_image_rgb is not None:
            h, w = self.vector_image_rgb.shape[:2]
            widths.append(min(w, h) * percent / 100.0)

        if not widths:
            return 0.0
        return min(1000.0, max(0.1, max(widths)))

    def apply_smart_smoothing_if_enabled(self, contours: List[Any]) -> List[Any]:
        if not self.smart_smoothing_var.get():
            return contours
        return vector.smart_smooth_contours(
            contours,
            corner_angle_deg=self.get_smart_corner_angle(),
            line_tolerance_px=self.get_smart_line_tolerance_px(),
            curve_smoothing_strength=self.get_smart_curve_strength(),
        )

    def apply_circle_regularization_if_suitable(self, contours: List[Any]) -> List[Any]:
        # Automatische Kreis-/Ellipsen-Normalisierung greift bei freien Logoformen
        # zu aggressiv. Kreisfit darf nur als später bewusstes Spezialwerkzeug laufen.
        return contours

    def apply_hole_scaling(self, contours: List[Any]) -> List[Any]:
        return vector.scale_hole_contours(
            contours,
            hole_scale=self.get_hole_scale_factor(),
        )

    def apply_bridge_tabs_if_enabled(self, contours: List[Any]) -> List[Any]:
        if not self.bridge_tabs_var.get() or self.vector_image_rgb is None:
            return contours
        h, w = self.vector_image_rgb.shape[:2]
        return vector.apply_bridge_tabs(
            contours,
            bridge_width_px=self.get_bridge_width_px(),
            bridge_count=self.get_bridge_count(),
            image_size=(w, h),
        )

    def get_anchor_neighbor_distance_px(self) -> float:
        text = self.anchor_neighbor_distance_var.get().strip()
        if not text:
            return 0.5
        return max(0.0, min(20.0, float(text.replace(",", "."))))

    def apply_anchor_neighbor_cleanup_if_enabled(self, contours: List[Any]) -> List[Any]:
        distance = self.get_anchor_neighbor_distance_px()
        if not self.remove_loose_points_var.get() or distance <= 0.0:
            return contours
        return vector.remove_neighbor_anchor_points_from_contours(
            contours,
            min_distance_px=distance,
        )

    def get_centerline_merge_px(self) -> float:
        text = self.centerline_merge_px_var.get().strip()
        return max(0.0, float(text.replace(",", "."))) if text else 0.0

    def get_duplicate_line_tolerance_px(self) -> float:
        text = self.duplicate_line_tolerance_var.get().strip()
        if not text:
            return 1.25
        return max(0.25, float(text.replace(",", ".")))

    def _update_vector_diagnostics(
        self,
        rules: List[Any],
        contours_before_cleanup: List[Any],
        contours_after_cleanup: List[Any],
        centerline_mode: bool,
    ) -> str:
        """Zeigt pro Farbregel, wo eine Fläche verloren geht.

        Diagnose-Stufen:
        - Rohmaske: RGB/Toleranz findet Pixel?
        - nach MinArea/Noise: Filter löscht Pixel?
        - Konturen vor Cleanup: OpenCV hat Pfade erzeugt?
        - Konturen nach Cleanup: globale Filter löschen Pfade?
        """
        if self.vector_image_rgb is None or not rules:
            self.vector_diagnostics_var.set("")
            return ""

        try:
            scale = self.get_internal_scale()
            area_scale = max(1, scale * scale)
            work_image = vector.preprocess_vector_image(
                self.vector_image_rgb,
                enabled=self.preprocess_vector_var.get(),
                blur_radius=self.get_preprocess_blur(),
                edge_smoothing=self.get_preprocess_edge_smoothing(),
            )
            work_image = vector.upscale_vector_image(work_image, scale)
            mask_noise_area = max(0.0, self.get_preprocess_noise_area() * area_scale) if self.preprocess_vector_var.get() else 0.0
            mask_edge_smoothing = self.get_preprocess_edge_smoothing() if self.preprocess_vector_var.get() else 0.0
            merge_px = self.get_centerline_merge_px() * scale
        except Exception as exc:
            text = f"Diagnose nicht möglich: {exc}"
            self.vector_diagnostics_var.set(text)
            return text

        before_by_rule = {id(rule): 0 for rule in rules}
        after_by_rule = {id(rule): 0 for rule in rules}
        points_by_rule = {id(rule): 0 for rule in rules}
        for contour in contours_before_cleanup:
            before_by_rule[id(contour.rule)] = before_by_rule.get(id(contour.rule), 0) + 1
        for contour in contours_after_cleanup:
            after_by_rule[id(contour.rule)] = after_by_rule.get(id(contour.rule), 0) + 1
            points_by_rule[id(contour.rule)] = points_by_rule.get(id(contour.rule), 0) + len(getattr(contour, "points", []) or [])

        rows: list[str] = []
        problems: list[str] = []
        for rule in rules:
            try:
                mask_raw = vector.make_color_mask(work_image, rule.rgb, rule.tolerance)
                mask_for_cleanup = mask_raw
                if centerline_mode:
                    mask_for_cleanup = vector.merge_nearby_mask_lines(mask_for_cleanup, merge_px)
                scaled_min_area = max(0, int(round(float(rule.min_area) * area_scale)))
                mask_min = vector.remove_small_components(mask_for_cleanup, scaled_min_area)
                mask_final = vector.calm_mask_edges(mask_min, mask_edge_smoothing, mask_noise_area)
                raw_px = int(round(float((mask_raw > 0).sum()) / area_scale))
                min_px = int(round(float((mask_min > 0).sum()) / area_scale))
                final_px = int(round(float((mask_final > 0).sum()) / area_scale))
            except Exception as exc:
                raw_px = min_px = final_px = 0
                problems.append(f"{rule.name}: Diagnosefehler {exc}")

            before_count = before_by_rule.get(id(rule), 0)
            after_count = after_by_rule.get(id(rule), 0)
            point_count = points_by_rule.get(id(rule), 0)
            export_label = "Export" if bool(rule.export) else "Ignore"
            row_text = (
                f"{rule.name} {rule.rgb} [{export_label}]: "
                f"Maske {raw_px}px → Filter {min_px}px → Kante {final_px}px → "
                f"Konturen {before_count}/{after_count}, Punkte {point_count}"
            )
            rows.append(row_text)

            if bool(rule.export):
                if raw_px <= 0:
                    problems.append(f"{rule.name}: keine Maske, RGB/Toleranz prüfen")
                elif min_px <= 0 or final_px <= 0:
                    problems.append(f"{rule.name}: Maske wird durch MinArea/Noise/Kantenfilter gelöscht")
                elif before_count <= 0:
                    problems.append(f"{rule.name}: Maske vorhanden, aber keine Kontur erzeugt")
                elif after_count <= 0:
                    problems.append(f"{rule.name}: Kontur durch Cleanup/Objektfilter entfernt")

        details = "\n".join(rows)
        if problems:
            compact = "Diagnose: " + " | ".join(problems[:3])
            if len(problems) > 3:
                compact += f" | +{len(problems) - 3} weitere"
        else:
            active = sum(1 for rule in rules if bool(rule.export))
            compact = f"Diagnose: {active} aktive Farbregeln haben Maske/Kontur."

        # In der UI kompakt anzeigen, vollständige Werte zusätzlich in der Konsole.
        ui_text = compact + "  |  " + "  ||  ".join(rows[:4])
        if len(rows) > 4:
            ui_text += f"  ||  +{len(rows) - 4} weitere Regeln"
        self.vector_diagnostics_var.set(ui_text)
        print("\n[Vektorrazor Diagnose]\n" + details + "\n")
        return compact

    def detect_and_preview_vector(self, live: bool = False) -> None:
        if self.vector_image_rgb is None:
            messagebox.showwarning(tr("msg.no_intermediate_title"), tr("msg.no_intermediate_step"))
            return
        self.step2_live_after_id = None
        if not live:
            self.show_busy_dialog(tr("msg.busy_vector_title"), tr("msg.busy_vector_body"), cancellable=True)
        try:
            self._raise_if_cancel_requested()
            self.set_progress(5, tr("progress.read_vector_rules"))
            self.selected_contour_index = None
            self.selected_contour_indices.clear()
            self.selected_contour_text_var.set(tr("status.no_path_selected"))
            rules = self.get_vector_rules()
            self.last_rules = rules
            pixel_to_mm = self.get_pixel_to_mm()
            centerline_mode = self.vector_mode_var.get() == "centerline"
            self.set_progress(10, tr("progress.detecting_contours"))
            def progress_step(fraction: float) -> None:
                self._raise_if_cancel_requested()
                self.set_progress(10 + fraction * 65, tr("progress.detecting_contours"))

            contours = vector.detect_all_contours(
                self.vector_image_rgb,
                rules,
                closed_paths_only=self.closed_paths_only_var.get() and not centerline_mode,
                remove_loose_points=False,
                smooth_iterations=0,
                centerline_mode=centerline_mode,
                centerline_merge_px=self.get_centerline_merge_px(),
                preprocess_enabled=self.preprocess_vector_var.get(),
                preprocess_blur=self.get_preprocess_blur(),
                preprocess_edge_smoothing=self.get_preprocess_edge_smoothing(),
                preprocess_noise_area=self.get_preprocess_noise_area(),
                internal_scale=self.get_internal_scale(),
                progress_callback=progress_step
            )
            self._raise_if_cancel_requested()
            before = len(contours)
            self.set_progress(80, tr("progress.filter_small_objects"))
            h, w = self.vector_image_rgb.shape[:2]
            self.detected_contours = vector.filter_small_contours(
                contours,
                self.cleanup_mode_var.get(),
                self.get_min_object_area_mm2(),
                self.get_min_object_percent(),
                (w, h),
                pixel_to_mm,
            )
            self.detected_contours = self.apply_manual_smoothing_if_enabled(self.detected_contours)
            self.detected_contours = self.apply_smart_smoothing_if_enabled(self.detected_contours)
            self.detected_contours = self.apply_circle_regularization_if_suitable(self.detected_contours)
            self.detected_contours = self.apply_hole_scaling(self.detected_contours)
            self.detected_contours = self.apply_bridge_tabs_if_enabled(self.detected_contours)
            self.set_progress(90, tr("progress.render_preview"))
            self.render_vector_preview()
            exported = sum(1 for c in self.detected_contours if c.rule.export)
            points = sum(len(c.points) for c in self.detected_contours if c.rule.export)
            self._update_cad_point_count()
            removed = before - len(self.detected_contours)
            diagnostic_status = self._update_vector_diagnostics(
                rules,
                contours,
                self.detected_contours,
                centerline_mode,
            )
            final_status = f"Konturen: {len(self.detected_contours)} | Export aktiv: {exported} | Punkte: {points} | Cleanup entfernt: {removed}"
            if diagnostic_status:
                final_status += f" | {diagnostic_status}"
            self.set_progress(100, final_status)
        except InterruptedError:
            self.set_progress(0, tr("status.analysis_cancelled"))
        except Exception as exc:
            self.set_progress(0, tr("progress.detect_error"))
            if live:
                self.status_var.set(f"{tr('msg.recognize_error_title')}: {exc}")
            else:
                messagebox.showerror(tr("msg.recognize_error_title"), str(exc))
        finally:
            if not live:
                self.close_busy_dialog()

    def render_vector_preview(self) -> None:
        if self.vector_image_rgb is None:
            return

        self.update_vector_bbox_info()
        mode = self.preview_mode_var.get()
        reset = self.step2_vector_canvas.image is None
        if mode == "mask":
            preview = self.build_filled_mask_preview_image()
            self.draw_vector_bbox_overlay(preview)
            self.draw_anchor_points_overlay(preview)
            self.draw_selected_contour_overlay(preview)
            self.step2_vector_canvas.set_image(preview, reset_view=reset)
            return
        if mode == "object":
            preview = self.build_object_check_preview_image()
            self.draw_vector_bbox_overlay(preview)
            self.draw_anchor_points_overlay(preview)
            self.draw_selected_contour_overlay(preview)
            self.step2_vector_canvas.set_image(preview, reset_view=reset)
            return
        if mode == "cut_risk":
            preview = self.build_cut_risk_preview_image()
            self.draw_vector_bbox_overlay(preview)
            self.draw_anchor_points_overlay(preview)
            self.draw_selected_contour_overlay(preview)
            self.step2_vector_canvas.set_image(preview, reset_view=reset)
            return

        h, w = self.vector_image_rgb.shape[:2]
        self.step2_vector_canvas.set_image(Image.new("RGB", (w, h), (255, 255, 255)), reset_view=reset)

    def _get_valid_selected_contour_indices(self) -> set[int]:
        indices = set(getattr(self, "selected_contour_indices", set()))
        if self.selected_contour_index is not None:
            indices.add(self.selected_contour_index)
        valid_indices = {idx for idx in indices if 0 <= idx < len(self.detected_contours)}
        if valid_indices != indices:
            self.selected_contour_indices = valid_indices
            self.selected_contour_index = next(iter(valid_indices), None)
            if not valid_indices:
                self.selected_contour_text_var.set(tr("status.no_path_selected"))
        return valid_indices

    @staticmethod
    def _canvas_points_from_path(
        points: List[Tuple[float, float]],
        zoom: float,
        offset_x: float,
        offset_y: float,
    ) -> List[float]:
        coords: List[float] = []
        for px, py in points:
            coords.extend([px * zoom + offset_x, py * zoom + offset_y])
        return coords

    def draw_vector_canvas_overlay(self, viewer: recolor.ZoomImageCanvas) -> None:
        if self.preview_mode_var.get() != "contour":
            return
        if viewer.image is None:
            return

        canvas = viewer.canvas
        zoom = max(0.0001, float(getattr(viewer, "zoom", 1.0) or 1.0))
        offset_x = float(getattr(viewer, "offset_x", 0.0))
        offset_y = float(getattr(viewer, "offset_y", 0.0))

        if self.unique_cad_lines_var.get():
            for rule, a, b in vector.unique_line_segments_from_contours(
                self.detected_contours,
                tolerance_px=self.get_duplicate_line_tolerance_px(),
                exported_only=True,
            ):
                color = "#{:02x}{:02x}{:02x}".format(int(rule.rgb[0]), int(rule.rgb[1]), int(rule.rgb[2]))
                canvas.create_line(
                    float(a[0]) * zoom + offset_x,
                    float(a[1]) * zoom + offset_y,
                    float(b[0]) * zoom + offset_x,
                    float(b[1]) * zoom + offset_y,
                    fill=color,
                    width=2,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                )
        else:
            for item in self.detected_contours:
                if not item.rule.export or len(item.points) < 2:
                    continue
                raw_pts = getattr(item, "raw_points", None)
                if raw_pts and len(raw_pts) >= 2:
                    preview_raw = [(float(x), float(y)) for x, y in raw_pts]
                    if item.closed and len(preview_raw) >= 3:
                        preview_raw = preview_raw + [preview_raw[0]]
                    raw_coords = self._canvas_points_from_path(preview_raw, zoom, offset_x, offset_y)
                    if len(raw_coords) >= 4:
                        canvas.create_line(
                            raw_coords,
                            fill="#9ca3af",
                            width=1,
                            capstyle=tk.ROUND,
                            joinstyle=tk.ROUND,
                        )
                color = "#{:02x}{:02x}{:02x}".format(
                    int(item.rule.rgb[0]), int(item.rule.rgb[1]), int(item.rule.rgb[2])
                )
                pts = [(float(x), float(y)) for x, y in item.points]
                if item.closed and len(pts) >= 3:
                    pts = pts + [pts[0]]
                coords = self._canvas_points_from_path(pts, zoom, offset_x, offset_y)
                if len(coords) < 4:
                    continue
                canvas.create_line(coords, fill=color, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)

        self.draw_vector_bbox_canvas_overlay(canvas, zoom, offset_x, offset_y)
        self.draw_anchor_points_canvas_overlay(canvas, zoom, offset_x, offset_y)

        selected_indices = self._get_valid_selected_contour_indices()
        for idx in sorted(selected_indices):
            item = self.detected_contours[idx]
            if len(item.points) < 2:
                continue
            pts = [(float(x), float(y)) for x, y in item.points]
            if item.closed and len(pts) >= 3:
                pts = pts + [pts[0]]
            coords = self._canvas_points_from_path(pts, zoom, offset_x, offset_y)
            if len(coords) < 4:
                continue
            canvas.create_line(coords, fill="#ffffff", width=7, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            canvas.create_line(coords, fill="#ff0000", width=3, capstyle=tk.ROUND, joinstyle=tk.ROUND)

    def draw_anchor_points_canvas_overlay(
        self,
        canvas: tk.Canvas,
        zoom: float,
        offset_x: float,
        offset_y: float,
    ) -> None:
        if not self.show_anchor_points_var.get():
            return
        radius = max(2.0, min(5.0, 2.5 * math.sqrt(max(0.0001, zoom))))
        for item in self.detected_contours:
            if not item.rule.export:
                continue
            for x, y in item.points:
                cx = float(x) * zoom + offset_x
                cy = float(y) * zoom + offset_y
                canvas.create_oval(
                    cx - radius,
                    cy - radius,
                    cx + radius,
                    cy + radius,
                    fill="#ffcc00",
                    outline="#111111",
                    width=1,
                )

    def draw_vector_bbox_canvas_overlay(
        self,
        canvas: tk.Canvas,
        zoom: float,
        offset_x: float,
        offset_y: float,
    ) -> None:
        bbox = self.get_vector_bbox_px()
        if not bbox:
            return
        x, y, width, height = bbox
        if width <= 0.0 or height <= 0.0:
            return
        canvas.create_rectangle(
            x * zoom + offset_x,
            y * zoom + offset_y,
            (x + width) * zoom + offset_x,
            (y + height) * zoom + offset_y,
            outline="#ff3b30",
            width=2,
            dash=(6, 4),
        )

    def draw_vector_bbox_overlay(self, image: Image.Image) -> None:
        bbox = self.get_vector_bbox_px()
        if not bbox:
            return
        x, y, width, height = bbox
        if width <= 0.0 or height <= 0.0:
            return
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (x, y, x + width, y + height),
            outline=(255, 59, 48),
            width=2,
        )

    def draw_anchor_points_overlay(self, image: Image.Image) -> None:
        if not self.show_anchor_points_var.get():
            return
        draw = ImageDraw.Draw(image)
        radius = 2
        for item in self.detected_contours:
            if not item.rule.export:
                continue
            for x, y in item.points:
                cx = int(round(float(x)))
                cy = int(round(float(y)))
                draw.ellipse(
                    (cx - radius, cy - radius, cx + radius, cy + radius),
                    fill=(255, 204, 0),
                    outline=(17, 17, 17),
                )

    def draw_selected_contour_overlay(self, image: Image.Image) -> None:
        """Markiert alle aktuell ausgewählten Pfade auffällig in der Vorschau."""
        indices = set(getattr(self, "selected_contour_indices", set()))
        if self.selected_contour_index is not None:
            indices.add(self.selected_contour_index)

        valid_indices = {idx for idx in indices if 0 <= idx < len(self.detected_contours)}
        if valid_indices != indices:
            self.selected_contour_indices = valid_indices
            self.selected_contour_index = next(iter(valid_indices), None)
            if not valid_indices:
                self.selected_contour_text_var.set(tr("status.no_path_selected"))
                return

        if not valid_indices:
            return

        draw = ImageDraw.Draw(image)
        for idx in sorted(valid_indices):
            item = self.detected_contours[idx]
            if len(item.points) < 2:
                continue
            pts = [(float(x), float(y)) for x, y in item.points]
            if item.closed and len(pts) >= 3:
                line_pts = pts + [pts[0]]
            else:
                line_pts = pts
            # Weißer Rand + rote Linie: sichtbar auf dunklem und hellem Hintergrund.
            draw.line(line_pts, fill=(255, 255, 255), width=7, joint="curve")
            draw.line(line_pts, fill=(255, 0, 0), width=3, joint="curve")

    @staticmethod
    def _contour_preview_area(item: Any) -> float:
        try:
            return max(0.0, float(getattr(item, "area", 0.0) or 0.0))
        except Exception:
            return 0.0

    def _ordered_preview_contours(self, contours: List[Any]) -> tuple[List[Any], List[Any]]:
        drawable = [
            item for item in contours
            if getattr(item.rule, "export", True) and len(getattr(item, "points", []) or []) >= 2
        ]
        solids = [item for item in drawable if not bool(getattr(item, "is_hole", False))]
        holes = [item for item in drawable if bool(getattr(item, "is_hole", False))]

        # Gefuellte Vorschauen muessen grosse Objekte zuerst zeichnen.
        # Kleinere eingeschlossene Objekte bleiben dadurch sichtbar.
        solids.sort(key=self._contour_preview_area, reverse=True)
        holes.sort(key=self._contour_preview_area, reverse=True)
        return solids, holes

    def _render_preview_mask_for_contours(self, contours: List[Any], width: int, height: int, aa: int) -> np.ndarray:
        mask = np.zeros((height * aa, width * aa), dtype=np.uint8)
        solids, holes = self._ordered_preview_contours(contours)

        for item in solids:
            pts = np.array(
                [[int(round(float(x) * aa)), int(round(float(y) * aa))] for x, y in item.points],
                dtype=np.int32,
            )
            if bool(getattr(item, "closed", False)) and len(pts) >= 3:
                vector.cv2.fillPoly(mask, [pts], 255)
            elif len(pts) >= 2:
                vector.cv2.polylines(mask, [pts], isClosed=False, color=255, thickness=max(1, aa))

        for item in holes:
            pts = np.array(
                [[int(round(float(x) * aa)), int(round(float(y) * aa))] for x, y in item.points],
                dtype=np.int32,
            )
            if bool(getattr(item, "closed", False)) and len(pts) >= 3:
                vector.cv2.fillPoly(mask, [pts], 0)
            elif len(pts) >= 2:
                vector.cv2.polylines(mask, [pts], isClosed=False, color=0, thickness=max(1, aa))

        return mask

    def build_filled_mask_preview_image(self) -> Image.Image:
        """
        Reine Raster-Farbmaske aus den aktuellen Farbregeln.

        Diese Ansicht ist bewusst VOR Objektcheck und VOR Vektor-Lochlogik.
        Sie zeigt nur: Welche Pixel werden durch die aktiven Export-Farbregeln
        erkannt? Dadurch können weiße Innenflächen keine schwarzen Details in
        der Farbmaske übermalen.
        """
        if self.vector_image_rgb is None:
            return Image.new("RGB", (1, 1), (255, 255, 255))

        h, w = self.vector_image_rgb.shape[:2]
        preview = Image.new("RGB", (w, h), (255, 255, 255))
        rules = self.last_rules or self.get_vector_rules()
        if not rules:
            return preview

        try:
            work_image = vector.preprocess_vector_image(
                self.vector_image_rgb,
                enabled=self.preprocess_vector_var.get(),
                blur_radius=self.get_preprocess_blur(),
                edge_smoothing=self.get_preprocess_edge_smoothing(),
            )
            mask_edge_smoothing = self.get_preprocess_edge_smoothing() if self.preprocess_vector_var.get() else 0.0
            mask_noise_area = self.get_preprocess_noise_area() if self.preprocess_vector_var.get() else 0.0
        except Exception:
            work_image = self.vector_image_rgb
            mask_edge_smoothing = 0.0
            mask_noise_area = 0.0

        for rule in rules:
            if not rule.export:
                continue
            try:
                mask = vector.make_color_mask(work_image, rule.rgb, rule.tolerance)
                mask = vector.remove_small_components(mask, rule.min_area)
                # Bei Lineart ist Vorverarbeitung normalerweise aus; falls sie der
                # Benutzer bewusst aktiviert, soll die Farbmaske dieselbe frühe
                # Maskenberuhigung zeigen wie die Erkennung.
                if mask_edge_smoothing > 0.0 or mask_noise_area > 0.0:
                    mask = vector.calm_mask_edges(mask, mask_edge_smoothing, mask_noise_area)
                color_layer = Image.new("RGB", (w, h), tuple(int(v) for v in rule.rgb))
                preview.paste(color_layer, mask=Image.fromarray(mask.astype(np.uint8)))
            except Exception:
                continue

        return preview

    def build_object_check_preview_image(self) -> Image.Image:
        """
        Farbig codierte Objektvorschau aus den aktuell vorhandenen Pfaden.

        Wichtig ab v10:
        Vorher wurde die Objektcheck-Ansicht aus den Raster-Farbflächen des
        Zwischenbildes aufgebaut. Dadurch blieb ein Objekt optisch sichtbar,
        obwohl sein Vektorpfad bereits entfernt wurde. Jetzt wird die Anzeige aus
        self.detected_contours gerendert; entfernte Pfade verschwinden sofort.
        """
        if self.vector_image_rgb is None:
            return Image.new("RGB", (1, 1), (255, 255, 255))

        h, w = self.vector_image_rgb.shape[:2]
        aa = max(1, int(getattr(self, "vector_preview_supersample", 1)))
        preview_hr = Image.new("RGB", (w * aa, h * aa), (255, 255, 255))
        draw = ImageDraw.Draw(preview_hr)
        palette = [
            (0, 0, 255),
            (255, 0, 0),
            (0, 180, 0),
            (255, 128, 0),
            (128, 0, 255),
            (0, 180, 180),
            (255, 0, 180),
            (120, 120, 120),
            (0, 90, 255),
            (180, 90, 0),
        ]

        if not self.detected_contours:
            # Vor der ersten Erkennung als Orientierung weiterhin Raster-Komponenten anzeigen.
            arr = np.full((h, w, 3), 255, dtype=np.uint8)
            rules = self.last_rules or self.get_vector_rules()
            object_index = 0
            for rule_index, rule in enumerate(rules):
                if not rule.export:
                    continue
                mask = vector.make_color_mask(self.vector_image_rgb, rule.rgb, rule.tolerance)
                mask = vector.remove_small_components(mask, rule.min_area)
                num_labels, labels, stats, _centroids = vector.cv2.connectedComponentsWithStats(mask, connectivity=8)
                for label_id in range(1, num_labels):
                    area = int(stats[label_id, vector.cv2.CC_STAT_AREA])
                    if area < rule.min_area:
                        continue
                    color = palette[(object_index + rule_index) % len(palette)]
                    arr[labels == label_id] = np.array(color, dtype=np.uint8)
                    object_index += 1
            return Image.fromarray(arr, "RGB")

        # Jedes Objekt einzeln nach Fläche sortieren (große zuerst, dann kleine drüber)
        # So bleiben kleine Details sichtbar, auch wenn sie in großen Flächen liegen
        drawable = [
            item for item in self.detected_contours
            if getattr(item.rule, "export", True) and len(getattr(item, "points", []) or []) >= 2
        ]
        drawable.sort(key=self._contour_preview_area, reverse=True)
        
        # Farben nach Reihenfolge des ersten Auftretens zuweisen
        color_map: dict[tuple[int, int, int, str], int] = {}
        preview_arr = np.array(preview_hr, dtype=np.uint8)
        
        # Gruppierung für Löcher erstellen
        from collections import defaultdict
        grouped: dict[tuple[int, int, int, str], list] = defaultdict(list)
        for item in self.detected_contours:
            if getattr(item.rule, "export", True):
                key = (int(item.rule.rgb[0]), int(item.rule.rgb[1]), int(item.rule.rgb[2]), str(item.rule.layer))
                grouped[key].append(item)
        
        # PASS 1: Alle Farbfüllungen zeichnen (große zuerst, kleine drüber)
        for item in drawable:
            if bool(getattr(item, "is_hole", False)):
                continue  # Löcher werden später separat gezeichnet
            key = (int(item.rule.rgb[0]), int(item.rule.rgb[1]), int(item.rule.rgb[2]), str(item.rule.layer))
            if key not in color_map:
                color_map[key] = len(color_map)
            color_index = color_map[key]
            
            mask = self._render_preview_mask_for_contours([item], w, h, aa)
            color = np.array(palette[color_index % len(palette)], dtype=np.uint8)
            preview_arr[mask > 0] = color
        
        # PASS 2: Alle schwarzen Konturen zeichnen (große zuerst, kleine drüber)
        # Dadurch übermalen die Konturen großer Objekte nicht die Füllungen kleiner Objekte
        kernel = np.ones((max(1, aa), max(1, aa)), dtype=np.uint8)
        for item in drawable:
            if bool(getattr(item, "is_hole", False)):
                continue
            mask = self._render_preview_mask_for_contours([item], w, h, aa)
            outline_mask = vector.cv2.morphologyEx(mask, vector.cv2.MORPH_GRADIENT, kernel)
            preview_arr[outline_mask > 0] = np.array((0, 0, 0), dtype=np.uint8)

        preview_hr = Image.fromarray(preview_arr, "RGB")
        draw = ImageDraw.Draw(preview_hr)
        for items in grouped.values():
            _solids, holes = self._ordered_preview_contours(items)
            for item in holes:
                pts = [(float(x) * aa, float(y) * aa) for x, y in item.points]
                if len(pts) < 2:
                    continue
                line = pts + [pts[0]] if bool(getattr(item, "closed", False)) and len(pts) >= 3 else pts
                draw.line(line, fill=(255, 255, 255), width=max(2, int(round(3 * aa))), joint="curve")
                draw.line(line, fill=(80, 80, 80), width=max(1, aa), joint="curve")
        if aa > 1:
            return preview_hr.resize((w, h), Image.Resampling.LANCZOS)
        return preview_hr
        # Objektcheck Variante C:
        # Normale Objekte werden bunt gefüllt. Löcher werden NICHT weiß gefüllt,
        # sondern nur als Umrandung markiert. Dadurch können weiße Innenflächen
        # keine bereits vorhandenen bunten Objektflächen mehr übermalen.
    def build_cut_risk_preview_image(self) -> Image.Image:
        """
        Vorschau fuer Schneid-/Fallteile.

        Rot markiert Innenloecher, die beim Durchschneiden als Ausschnitte
        herausfallen koennen. Orange markiert kleine geschlossene Einzelinseln.
        Die Ansicht nutzt die bereits erkannten Vektorpfade und passt damit zum
        aktuellen Exportzustand.
        """
        if self.vector_image_rgb is None:
            return Image.new("RGB", (1, 1), (255, 255, 255))

        h, w = self.vector_image_rgb.shape[:2]
        aa = max(1, int(getattr(self, "vector_preview_supersample", 1)))
        preview_hr = Image.new("RGB", (w * aa, h * aa), (248, 250, 252))

        solids, holes = self._ordered_preview_contours(self.detected_contours)
        exported = solids + holes
        if not exported:
            return preview_hr.resize((w, h), Image.Resampling.LANCZOS) if aa > 1 else preview_hr

        areas = [max(0.0, float(getattr(item, "area", 0.0) or 0.0)) for item in exported]
        max_area = max(areas) if areas else 0.0
        image_area = max(1.0, float(w * h))
        small_island_limit = max(
            12.0,
            min(image_area * 0.015, max_area * 0.18 if max_area > 0 else image_area * 0.015),
        )

        normal_solids: List[Any] = []
        small_islands: List[Any] = []
        for item in solids:
            area = max(0.0, float(getattr(item, "area", 0.0) or 0.0))
            if bool(getattr(item, "closed", False)) and area <= small_island_limit:
                small_islands.append(item)
            else:
                normal_solids.append(item)

        preview_arr = np.array(preview_hr, dtype=np.uint8)
        for items, fill, stroke in (
            (normal_solids, (226, 232, 240), (30, 41, 59)),
            (small_islands, (255, 237, 213), (234, 88, 12)),
            (holes, (255, 218, 218), (220, 38, 38)),
        ):
            if not items:
                continue
            if items is holes:
                mask = np.zeros((h * aa, w * aa), dtype=np.uint8)
                for item in items:
                    pts = np.array(
                        [[int(round(float(x) * aa)), int(round(float(y) * aa))] for x, y in item.points],
                        dtype=np.int32,
                    )
                    if bool(getattr(item, "closed", False)) and len(pts) >= 3:
                        vector.cv2.fillPoly(mask, [pts], 255)
                    elif len(pts) >= 2:
                        vector.cv2.polylines(mask, [pts], isClosed=False, color=255, thickness=max(1, aa))
            else:
                mask = self._render_preview_mask_for_contours(items, w, h, aa)
            preview_arr[mask > 0] = np.array(fill, dtype=np.uint8)
            kernel = np.ones((max(1, aa), max(1, aa)), dtype=np.uint8)
            outline_mask = vector.cv2.morphologyEx(mask, vector.cv2.MORPH_GRADIENT, kernel)
            preview_arr[outline_mask > 0] = np.array(stroke, dtype=np.uint8)

        preview_hr = Image.fromarray(preview_arr, "RGB")

        if aa > 1:
            return preview_hr.resize((w, h), Image.Resampling.LANCZOS)
        return preview_hr

    def update_vector_selection_mode_ui(self) -> None:
        """Zeigt optisch, ob Klicks in der Vektorvorschau auswählen oder nur verschieben."""
        try:
            if self.vector_selection_mode_var.get():
                self.step2_vector_canvas.canvas.configure(cursor="crosshair")
                self.status_var.set(tr("status.selection_mode_on"))
            else:
                self.step2_vector_canvas.canvas.configure(cursor="")
                self.status_var.set(tr("status.selection_mode_off"))
        except Exception:
            pass

    @staticmethod
    def mouse_modifiers(event: tk.Event) -> Tuple[bool, bool]:
        """Gibt (ctrl, alt) zurück. Tk liefert Modifier als Bitmaske im event.state.

        Wichtig: Unter Windows kann das alte Mod1-Bit 0x0008 je nach Tastaturstatus
        fälschlich gesetzt sein. Darum wird ALT hier nicht mehr als alleiniger
        Auslöser verwendet. Direktes Löschen per ALT ist nur im Auswahl-Modus aktiv.
        """
        state = int(getattr(event, "state", 0) or 0)
        ctrl = bool(state & 0x0004)
        # Windows liefert Alt häufig als 0x20000; 0x0008 wird bewusst nicht mehr
        # als alleiniger Lösch-Trigger verwendet, weil es auf manchen Systemen
        # ungewollt gesetzt sein kann.
        alt = bool(state & 0x20000)
        return ctrl, alt

    def on_vector_mouse_press(self, event: tk.Event):
        ctrl, alt = self.mouse_modifiers(event)
        selection_mode = bool(self.vector_selection_mode_var.get())

        # Harte Sperre gegen versehentliches Auswählen/Löschen:
        # Ohne Auswahl-Modus und ohne STRG bleibt der Klick komplett dem Pan/Verschieben vorbehalten.
        if not selection_mode and not ctrl:
            self.vector_select_press = None
            return None

        # Direktes Löschen per ALT ist nur im bewusst aktivierten Auswahl-Modus erlaubt.
        mode = "remove" if (selection_mode and alt) else "select"
        self.vector_select_press = (int(event.x), int(event.y), mode)
        try:
            self.step2_vector_canvas.canvas.focus_set()
        except Exception:
            pass

        # Kein "break": ZoomImageCanvas darf weiterhin normal Pan/Verschieben machen.
        return None

    def on_vector_mouse_release(self, event: tk.Event):
        if self.vector_select_press is None:
            return None
        sx, sy, mode = self.vector_select_press
        self.vector_select_press = None
        if abs(int(event.x) - sx) > 4 or abs(int(event.y) - sy) > 4:
            # Das war wahrscheinlich Verschieben/Pan, keine Auswahl.
            return None

        ctrl, alt = self.mouse_modifiers(event)
        selection_mode = bool(self.vector_selection_mode_var.get())

        # Sicherheitsregel:
        # Entfernen nur bei aktivem Auswahl-Modus + ALT oder über den separaten Button/Entf.
        if mode == "remove" and selection_mode:
            self.remove_contour_at_canvas_position(int(event.x), int(event.y))
        else:
            # STRG: Mehrfachauswahl/toggle. Ohne STRG: einzelne Auswahl.
            self.select_contour_at_canvas_position(int(event.x), int(event.y), add_to_selection=ctrl)
        return None

    # Kompatibilität: Falls irgendwo noch alte Modifier-Bindings aktiv wären.
    def on_vector_select_press(self, event: tk.Event, mode: str) -> str:
        # Auch hier dieselbe Sicherheitsregel: ohne Auswahl-Modus keine direkte Entfernung.
        if mode == "remove" and not self.vector_selection_mode_var.get():
            self.vector_select_press = None
            return "break"
        self.vector_select_press = (int(event.x), int(event.y), mode)
        try:
            self.step2_vector_canvas.canvas.focus_set()
        except Exception:
            pass
        return "break"

    def on_vector_select_release(self, event: tk.Event) -> str:
        self.on_vector_mouse_release(event)
        return "break"

    def canvas_to_vector_image_point(self, canvas_x: int, canvas_y: int) -> Optional[Tuple[float, float]]:
        if self.step2_vector_canvas.image is None:
            return None
        zoom = float(getattr(self.step2_vector_canvas, "zoom", 1.0) or 1.0)
        offset_x = float(getattr(self.step2_vector_canvas, "offset_x", 0.0))
        offset_y = float(getattr(self.step2_vector_canvas, "offset_y", 0.0))
        x = (float(canvas_x) - offset_x) / zoom
        y = (float(canvas_y) - offset_y) / zoom
        if x < 0 or y < 0 or x >= self.step2_vector_canvas.image.width or y >= self.step2_vector_canvas.image.height:
            return None
        return x, y

    @staticmethod
    def point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
        vx = bx - ax
        vy = by - ay
        wx = px - ax
        wy = py - ay
        length_sq = vx * vx + vy * vy
        if length_sq <= 1e-9:
            return float(((px - ax) ** 2 + (py - ay) ** 2) ** 0.5)
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / length_sq))
        cx = ax + t * vx
        cy = ay + t * vy
        return float(((px - cx) ** 2 + (py - cy) ** 2) ** 0.5)

    def contour_hit_score(self, contour: Any, x: float, y: float) -> Optional[Tuple[float, float]]:
        """
        Gibt (Distanz, Fläche) zurück. Distanz 0 bedeutet: Klick liegt in einer
        geschlossenen Kontur. Die Fläche hilft, bei verschachtelten Pfaden den
        kleineren/spezifischeren Pfad zu bevorzugen.
        """
        pts = [(float(px), float(py)) for px, py in getattr(contour, "points", [])]
        if len(pts) < 2:
            return None

        area = 0.0
        if len(pts) >= 3:
            try:
                area = float(vector.polygon_area(pts))
            except Exception:
                area = 0.0

        if getattr(contour, "closed", False) and len(pts) >= 3:
            try:
                poly = np.array(pts, dtype=np.float32).reshape(-1, 1, 2)
                inside = vector.cv2.pointPolygonTest(poly, (float(x), float(y)), False)
                if inside >= 0:
                    return (0.0, max(0.0, area))
            except Exception:
                pass
            segments = list(zip(pts, pts[1:] + [pts[0]]))
        else:
            segments = list(zip(pts, pts[1:]))

        if not segments:
            return None
        distance = min(self.point_segment_distance(x, y, a[0], a[1], b[0], b[1]) for a, b in segments)
        return (float(distance), max(0.0, area))

    def find_contour_index_at_canvas_position(self, canvas_x: int, canvas_y: int) -> Optional[int]:
        point = self.canvas_to_vector_image_point(canvas_x, canvas_y)
        if point is None:
            return None
        if not self.detected_contours:
            self.selected_contour_text_var.set(tr("status.no_contours_detected"))
            return None

        x, y = point
        zoom = float(getattr(self.step2_vector_canvas, "zoom", 1.0) or 1.0)
        # Bei wenig Zoom darf die Klick-Toleranz im Bild größer sein.
        hit_distance_px = max(6.0, 12.0 / max(0.15, zoom))

        best_inside: Optional[Tuple[float, int]] = None  # area, index
        best_near: Optional[Tuple[float, int]] = None    # distance, index

        for index, contour in enumerate(self.detected_contours):
            if not getattr(contour.rule, "export", True):
                continue
            score = self.contour_hit_score(contour, x, y)
            if score is None:
                continue
            distance, area = score
            if distance <= 0.0:
                # Bei Klick in gefüllte/geschlossene Konturen lieber das kleinste passende Objekt wählen.
                candidate = (area if area > 0 else 1e18, index)
                if best_inside is None or candidate[0] < best_inside[0]:
                    best_inside = candidate
            elif distance <= hit_distance_px:
                candidate = (distance, index)
                if best_near is None or candidate[0] < best_near[0]:
                    best_near = candidate

        if best_inside is not None:
            return best_inside[1]
        if best_near is not None:
            return best_near[1]
        return None

    def select_contour_at_canvas_position(self, canvas_x: int, canvas_y: int, add_to_selection: bool = False) -> None:
        selected_index = self.find_contour_index_at_canvas_position(canvas_x, canvas_y)
        if selected_index is None:
            self.selected_contour_text_var.set(tr("status.no_path_hit"))
            self.render_vector_preview()
            return

        if not add_to_selection:
            self.selected_contour_indices.clear()
        # STRG-Klick toggelt: noch nicht gewählt -> hinzufügen, schon gewählt -> abwählen.
        if selected_index in self.selected_contour_indices:
            self.selected_contour_indices.remove(selected_index)
            if self.selected_contour_index == selected_index:
                self.selected_contour_index = next(iter(self.selected_contour_indices), None)
        else:
            self.selected_contour_indices.add(selected_index)
            self.selected_contour_index = selected_index

        self.update_selected_contour_text()
        self.status_var.set(tr("status.path_selection_changed"))
        self.render_vector_preview()

    def remove_contour_at_canvas_position(self, canvas_x: int, canvas_y: int) -> None:
        index = self.find_contour_index_at_canvas_position(canvas_x, canvas_y)
        if index is None:
            self.selected_contour_text_var.set(tr("status.no_path_hit"))
            self.render_vector_preview()
            return
        self.selected_contour_indices = {index}
        self.selected_contour_index = index
        self.remove_selected_contour()

    def update_selected_contour_text(self) -> None:
        count = len(self.selected_contour_indices)
        if count <= 0:
            self.selected_contour_text_var.set(tr("status.no_path_selected"))
            return
        if count == 1:
            selected_index = next(iter(self.selected_contour_indices))
            if not (0 <= selected_index < len(self.detected_contours)):
                self.selected_contour_indices.clear()
                self.selected_contour_index = None
                self.selected_contour_text_var.set(tr("status.no_path_selected"))
                return
            contour = self.detected_contours[selected_index]
            points = len(getattr(contour, "points", []))
            area = float(getattr(contour, "area", 0.0))
            layer = getattr(contour.rule, "layer", getattr(contour.rule, "name", "Layer"))
            self.selected_contour_text_var.set(
                tr("status.path_selected_details", index=selected_index + 1, layer=layer, points=points, area=area)
            )
            return
        self.selected_contour_text_var.set(tr("status.paths_selected_count", count=count))

    def clear_selected_contour(self) -> None:
        self.selected_contour_index = None
        self.selected_contour_indices.clear()
        self.selected_contour_text_var.set(tr("status.no_path_selected"))
        self.render_vector_preview()

    def remove_selected_contour(self) -> None:
        indices = sorted(self.selected_contour_indices, reverse=True)
        if not indices and self.selected_contour_index is not None:
            indices = [self.selected_contour_index]
        indices = [idx for idx in indices if 0 <= idx < len(self.detected_contours)]
        if not indices:
            self.status_var.set(tr("status.no_path_selected"))
            return

        removed_info = []
        for idx in indices:
            removed = self.detected_contours.pop(idx)
            layer = getattr(removed.rule, "layer", getattr(removed.rule, "name", "Layer"))
            points = len(getattr(removed, "points", []))
            removed_info.append((idx, layer, points))

        self.selected_contour_index = None
        self.selected_contour_indices.clear()
        if len(removed_info) == 1:
            idx, layer, points = removed_info[0]
            self.selected_contour_text_var.set(tr("status.path_removed_details", index=idx + 1, layer=layer, points=points))
        else:
            self.selected_contour_text_var.set(tr("status.paths_removed_count", count=len(removed_info)))
        exported = sum(1 for c in self.detected_contours if c.rule.export)
        total_points = sum(len(c.points) for c in self.detected_contours if c.rule.export)
        self.status_var.set(tr("status.path_removed", remaining=len(self.detected_contours), exported=exported, points=total_points))
        # Bildreferenz kurz leeren, damit Tkinter garantiert neu rendert.
        try:
            self.step2_vector_canvas.tk_image = None
        except Exception:
            pass
        self.render_vector_preview()

    def auto_optimize_vector_settings(self) -> None:
        if self.vector_image_rgb is None:
            messagebox.showwarning(tr("msg.no_intermediate_title"), tr("msg.no_intermediate_step"))
            return
        original_epsilons = [row.epsilon_var.get() for row in self.vector_rows]
        try:
            self.set_progress(0, tr("progress.auto_prepare"))
            pixel_to_mm = self.get_pixel_to_mm()
            centerline_mode = self.vector_mode_var.get() == "centerline"
            if centerline_mode:
                candidates = [
                    {"epsilon": 0.8, "smooth": 0, "merge": 0.0},
                    {"epsilon": 1.2, "smooth": 0, "merge": 1.0},
                    {"epsilon": 1.8, "smooth": 0, "merge": 2.0},
                    {"epsilon": 2.4, "smooth": 0, "merge": 3.0},
                    {"epsilon": 3.0, "smooth": 0, "merge": 4.0},
                ]
            else:
                candidates = [
                    {"epsilon": 0.4, "smooth": 0, "merge": 0.0},
                    {"epsilon": 0.6, "smooth": 1, "merge": 0.0},
                    {"epsilon": 0.8, "smooth": 1, "merge": 0.0},
                    {"epsilon": 1.0, "smooth": 1, "merge": 0.0},
                    {"epsilon": 1.2, "smooth": 2, "merge": 0.0},
                    {"epsilon": 1.6, "smooth": 2, "merge": 0.0},
                ]
            best_score = -1.0
            best_candidate = candidates[0]
            best_contours: List[Any] = []
            h, w = self.vector_image_rgb.shape[:2]
            for idx, cand in enumerate(candidates):
                self.set_progress(idx / max(1, len(candidates)) * 90, tr("progress.auto_test", index=idx + 1, total=len(candidates)))
                for row in self.vector_rows:
                    row.epsilon_var.set(str(cand["epsilon"]).replace(".", ","))
                    try:
                        if vector.parse_rgb(row.rgb_var.get()) == (255, 255, 255):
                            row.export_var.set(False)
                    except Exception:
                        pass
                rules = self.get_vector_rules()
                contours = vector.detect_all_contours(
                    self.vector_image_rgb,
                    rules,
                    closed_paths_only=self.closed_paths_only_var.get() and not centerline_mode,
                    remove_loose_points=False,
                    smooth_iterations=0,
                    centerline_mode=centerline_mode,
                    centerline_merge_px=float(cand["merge"]),
                    preprocess_enabled=self.preprocess_vector_var.get(),
                    preprocess_blur=self.get_preprocess_blur(),
                    preprocess_edge_smoothing=self.get_preprocess_edge_smoothing(),
                    preprocess_noise_area=self.get_preprocess_noise_area(),
                    internal_scale=self.get_internal_scale(),
                )
                contours = vector.filter_small_contours(contours, self.cleanup_mode_var.get(), self.get_min_object_area_mm2(), self.get_min_object_percent(), (w, h), pixel_to_mm)
                contours = self.apply_manual_smoothing_if_enabled(contours, iterations=int(cand["smooth"]))
                contours = self.apply_smart_smoothing_if_enabled(contours)
                contours = self.apply_hole_scaling(contours)
                contours = self.apply_bridge_tabs_if_enabled(contours)
                score = vector.score_vector_result(self.vector_image_rgb, rules, contours, centerline_mode)
                if score > best_score:
                    best_score = score
                    best_candidate = cand
                    best_contours = contours
            for row in self.vector_rows:
                row.epsilon_var.set(str(best_candidate["epsilon"]).replace(".", ","))
            self.smooth_contours_var.set(bool(best_candidate["smooth"]))
            self.smooth_strength_var.set(str(best_candidate["smooth"]).replace(".", ","))
            self.centerline_merge_px_var.set(str(best_candidate["merge"]).replace(".", ","))
            self.last_rules = self.get_vector_rules()
            self.detected_contours = best_contours
            self.render_vector_preview()
            points = sum(len(c.points) for c in self.detected_contours if c.rule.export)
            self.set_progress(100, tr("progress.auto_applied", score=best_score, points=points))
        except Exception as exc:
            for row, eps in zip(self.vector_rows, original_epsilons):
                row.epsilon_var.set(eps)
            self.set_progress(0, tr("progress.auto_error"))
            messagebox.showerror(tr("msg.auto_values_error_title"), str(exc))

    def _clone_contour_for_export(self, item: Any, points: List[Tuple[float, float]]) -> Any:
        return vector.DetectedContour(
            rule=item.rule,
            points=points,
            area=float(getattr(item, "area", 0.0) or 0.0),
            closed=bool(getattr(item, "closed", True)),
            is_hole=bool(getattr(item, "is_hole", False)),
            raw_points=list(getattr(item, "raw_points", []) or getattr(item, "points", []) or []),
        )

    def _simplify_contours_for_export(self, contours: List[Any], epsilon_px: float) -> List[Any]:
        epsilon = max(0.0, float(epsilon_px))
        if epsilon <= 0.0:
            return [
                self._clone_contour_for_export(
                    item,
                    [(float(x), float(y)) for x, y in getattr(item, "points", []) or []],
                )
                for item in contours
            ]
        simplified: List[Any] = []
        for item in contours:
            points = [(float(x), float(y)) for x, y in getattr(item, "points", []) or []]
            if len(points) >= 3:
                points = vector.approximate_points(points, epsilon, closed=bool(getattr(item, "closed", True)))
            simplified.append(self._clone_contour_for_export(item, points))
        return simplified

    def _export_contours_to_file(self, out: str, contours: List[Any], pixel_to_mm: float) -> None:
        suffix = Path(out).suffix.lower()
        h, w = self.vector_image_rgb.shape[:2]
        self.set_progress(60, tr("progress.writing_file"))
        if suffix == ".svg":
            vector.export_svg(
                out,
                (w, h),
                contours,
                pixel_to_mm,
                fill_closed_shapes=self.fill_closed_shapes_var.get(),
                use_bezier=self.use_bezier_var.get(),
                group_connected_paths=self.group_connected_paths_var.get(),
                force_color_layers=self.force_color_layers_var.get(),
            )
        elif suffix == ".dxf":
            vector.export_dxf(
                out,
                (w, h),
                contours,
                pixel_to_mm,
                invert_y=True,
                dxf_version=self.get_selected_dxf_version(),
                dedupe_segments=self.unique_cad_lines_var.get(),
                dedupe_tolerance_px=self.get_duplicate_line_tolerance_px(),
                force_color_layers=self.force_color_layers_var.get(),
                object_layers=self.object_layers_dxf_var.get(),
            )
        else:
            raise ValueError("Output muss .dxf oder .svg sein.")
        cad_cleanup = "ein / eindeutige Einzellinien" if self.unique_cad_lines_var.get() else "aus / originale Polylines"
        self.set_progress(100, tr("progress.export_done", out=out, dxf_version=self.get_selected_dxf_version(), cad_cleanup=cad_cleanup))
        messagebox.showinfo(
            tr("msg.export_done_title"),
            f"Datei wurde gespeichert:\n{out}\n\nKompatibilitÃ¤t: {self.dxf_compatibility_display_var.get()}\nDXF-Format: {self.dxf_version_var.get()}\nDXF-Version intern: {self.get_selected_dxf_version()}\nDoppelte Linien entfernen: {cad_cleanup}"
        )

    def open_scaled_export_dialog(self) -> None:
        dialogs_scale_export.open_scaled_export_dialog(self)

    def open_stl_export_dialog(
        self,
        contours: List[Any],
        pixel_to_mm: float,
        parent: Optional[tk.Widget] = None,
        preview_builder: Optional[Any] = None,
    ) -> None:
        dialogs_scale_export.open_stl_export_dialog(
            self,
            contours,
            pixel_to_mm,
            parent=parent,
            preview_builder=preview_builder,
        )

    def export_vector_file(self) -> None:
        if self.vector_image_rgb is None:
            messagebox.showwarning(tr("msg.no_intermediate_title"), tr("msg.no_intermediate_step"))
            return
        if not self.detected_contours:
            self.detect_and_preview_vector()
            if not self.detected_contours:
                return
        out = self.output_path_var.get().strip()
        if not out:
            self.choose_vector_output()
            out = self.output_path_var.get().strip()
        if not out:
            return
        try:
            suffix = Path(out).suffix.lower()
            pixel_to_mm = self.get_pixel_to_mm()
            h, w = self.vector_image_rgb.shape[:2]
            self.set_progress(60, tr("progress.writing_file"))
            if suffix == ".svg":
                vector.export_svg(
                    out,
                    (w, h),
                    self.detected_contours,
                    pixel_to_mm,
                    fill_closed_shapes=self.fill_closed_shapes_var.get(),
                    use_bezier=self.use_bezier_var.get(),
                    group_connected_paths=self.group_connected_paths_var.get(),
                    force_color_layers=self.force_color_layers_var.get(),
                )
            elif suffix == ".dxf":
                vector.export_dxf(
                    out,
                    (w, h),
                    self.detected_contours,
                    pixel_to_mm,
                    invert_y=True,
                    dxf_version=self.get_selected_dxf_version(),
                    dedupe_segments=self.unique_cad_lines_var.get(),
                    dedupe_tolerance_px=self.get_duplicate_line_tolerance_px(),
                    force_color_layers=self.force_color_layers_var.get(),
                    object_layers=self.object_layers_dxf_var.get(),
                )
            else:
                raise ValueError("Output muss .dxf oder .svg sein.")
            cad_cleanup = "ein / eindeutige Einzellinien" if self.unique_cad_lines_var.get() else "aus / originale Polylines"
            self.set_progress(100, tr("progress.export_done", out=out, dxf_version=self.get_selected_dxf_version(), cad_cleanup=cad_cleanup))
            messagebox.showinfo(
                tr("msg.export_done_title"),
                f"Datei wurde gespeichert:\n{out}\n\nKompatibilität: {self.dxf_compatibility_display_var.get()}\nDXF-Format: {self.dxf_version_var.get()}\nDXF-Version intern: {self.get_selected_dxf_version()}\nDoppelte Linien entfernen: {cad_cleanup}"
            )
        except Exception as exc:
            self.set_progress(0, "Fehler beim Export")
            messagebox.showerror(tr("msg.export_error"), str(exc))


def main() -> None:
    app = WorkflowApp()
    app.mainloop()


if __name__ == "__main__":
    main()
