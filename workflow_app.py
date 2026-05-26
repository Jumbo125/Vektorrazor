# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""
Workflow-App für PNG-Aufbereitung und Vektorisierung.

Datei-Struktur:
- main.py             -> Startdatei
- workflow_app.py     -> Haupt-Workflow-Oberfläche
- recolor_engine.py   -> Bildvorbereitung / Umfärben / PNG-Export
- vector_engine.py    -> Vektorisierung / SVG / DXF
- requirements.txt    -> Python-Abhängigkeiten
"""

from __future__ import annotations


from pathlib import Path
from typing import Optional, Tuple, List, Any
import sys

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import numpy as np
from PIL import Image, ImageTk, ImageDraw

import recolor_engine as recolor
import vector_engine as vector


def resource_path(relative_path: str) -> Path:
    """Pfad funktioniert im Quellordner und in einer PyInstaller-Onefile-EXE."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path


RGB = Tuple[int, int, int]


DXF_COMPATIBILITY_PRESETS = {
    "Illustrator / CorelDRAW (empfohlen)": (
        "R2000",
        "Empfohlen für Grafikprogramme: robust, alt genug und für viele Importfilter gut lesbar."
    ),
    "Adobe Illustrator": (
        "R2007",
        "Illustrator-kompatibler Modus bis AutoCAD 2007. Falls Import scheitert: R2000 wählen."
    ),
    "CorelDRAW": (
        "R2000",
        "Robuster CorelDRAW-Modus. Corel kann zwar neuere AutoCAD-Versionen, R2000 ist oft stabiler."
    ),
    "CorelDRAW modern": (
        "R2007",
        "Für neuere CorelDRAW-Versionen. Bei Importproblemen zurück auf R2000."
    ),
    "AutoCAD / CAD modern": (
        "R2010",
        "Für moderne CAD-Programme. Nicht ideal für Illustrator."
    ),
    "FreeCAD / LibreCAD / CAM": (
        "R2000",
        "Allgemeiner Austauschmodus für freie CAD/CAM-Programme."
    ),
    "Manuell": (
        "R2000",
        "DXF-Format rechts selbst wählen."
    ),
}


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
        (255, 255, 255): "Weiss",
        (0, 0, 255): "Blau",
        (255, 0, 0): "Rot",
        (0, 255, 0): "Gruen",
        (255, 0, 255): "Magenta",
        (0, 255, 255): "Cyan",
        (255, 255, 0): "Gelb",
        (255, 128, 0): "Orange",
        (128, 0, 255): "Violett",
        (128, 128, 128): "Grau",
    }
    return names.get(tuple(rgb), f"RGB_{rgb[0]}_{rgb[1]}_{rgb[2]}")


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
        ttk.Button(self.frame, text="wählen", width=7, command=self.choose_target_color).grid(row=0, column=8, sticky="w")

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
        self.frame.columnconfigure(12, weight=1)

        self.radio = ttk.Radiobutton(self.frame, variable=app.selected_manual_row_var, value=index, command=app.update_manual_status)
        self.radio.grid(row=0, column=0, padx=(0, 2))
        ttk.Label(self.frame, text=f"#{index + 1}", width=4).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(self.frame, variable=self.enabled_var, command=app.schedule_step1_preview).grid(row=0, column=2, padx=(0, 4))
        ttk.Entry(self.frame, textvariable=self.source_var, width=13).grid(row=0, column=3, sticky="w")
        self.source_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.source_swatch.grid(row=0, column=4, padx=(4, 8))
        ttk.Label(self.frame, text="Tol.").grid(row=0, column=5, sticky="w")
        ttk.Entry(self.frame, textvariable=self.tolerance_var, width=5).grid(row=0, column=6, sticky="w", padx=(2, 8))
        ttk.Label(self.frame, text="→").grid(row=0, column=7)
        ttk.Entry(self.frame, textvariable=self.target_var, width=13).grid(row=0, column=8, sticky="w", padx=(4, 0))
        self.target_swatch = tk.Label(self.frame, width=3, relief="solid", bd=1)
        self.target_swatch.grid(row=0, column=9, padx=(4, 4))
        ttk.Button(self.frame, text="wählen", width=7, command=self.choose_target_color).grid(row=0, column=10, sticky="w")

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
        self.title("Vektorrazor - PNG Logo zu CAD-tauglichen Vektordaten")
        self._set_window_icon()
        self.geometry("1480x920")
        self.minsize(1180, 760)

        self.current_step = 0
        self.original_image: Optional[Image.Image] = None
        self.prepared_image: Optional[Image.Image] = None
        self.edited_image: Optional[Image.Image] = None
        self.special_result_image: Optional[Image.Image] = None
        self.current_path: Optional[Path] = None
        self.preview_after_id: Optional[str] = None

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
        self.basic_threshold_var = tk.IntVar(value=10)
        self.basic_min_area_var = tk.IntVar(value=30)
        self.basic_max_colors_var = tk.IntVar(value=12)
        self.basic_alpha_var = tk.IntVar(value=10)
        self.logo_mask_threshold_var = tk.IntVar(value=18)
        self.logo_mask_blur_var = tk.IntVar(value=31)
        self.logo_mask_clean_var = tk.BooleanVar(value=True)
        self.logo_mask_fg_var = tk.StringVar(value="0,0,0")
        self.logo_mask_bg_var = tk.StringVar(value="255,255,255")

        # Schritt 2 Variablen
        self.vector_image_rgb: Optional[np.ndarray] = None
        self.vector_source_name_var = tk.StringVar(value="Noch kein Zwischenbild übernommen")
        self.output_path_var = tk.StringVar()
        self.pixel_to_mm_var = tk.StringVar(value="1.0")
        self.dxf_compatibility_var = tk.StringVar(value="Illustrator / CorelDRAW (empfohlen)")
        self.dxf_version_var = tk.StringVar(value=_dxf_choice_for_version("R2000"))
        self.dxf_compatibility_info_var = tk.StringVar(
            value=DXF_COMPATIBILITY_PRESETS["Illustrator / CorelDRAW (empfohlen)"][1] + "  Aktuell: DXF R2000"
        )
        self.profile_var = tk.StringVar(value="Standard")
        self.vector_mode_var = tk.StringVar(value="Flächenkontur")
        self.centerline_merge_px_var = tk.StringVar(value="0")
        self.closed_paths_only_var = tk.BooleanVar(value=True)
        self.fill_closed_shapes_var = tk.BooleanVar(value=False)
        self.preview_mode_var = tk.StringVar(value="Objektcheck")
        self.use_bezier_var = tk.BooleanVar(value=False)
        self.remove_loose_points_var = tk.BooleanVar(value=False)
        self.smooth_contours_var = tk.BooleanVar(value=True)
        self.smooth_strength_var = tk.StringVar(value="2")
        self.cleanup_mode_var = tk.StringVar(value="% Bildfläche")
        self.min_object_area_mm2_var = tk.StringVar(value="0")
        self.min_object_percent_var = tk.StringVar(value="0,01")
        self.detected_contours: List[Any] = []
        self.last_rules: List[Any] = []
        self.selected_contour_index: Optional[int] = None
        self.selected_contour_indices: set[int] = set()
        self.vector_select_press: Optional[Tuple[int, int, str]] = None
        self.vector_selection_mode_var = tk.BooleanVar(value=False)
        self.selected_contour_text_var = tk.StringVar(value="Kein Pfad ausgewählt")

        self.status_var = tk.StringVar(value="Bereit")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()
        self.add_manual_row()
        self.load_vector_profile("Standard")
        self.show_step(0)

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
        self.back_btn.grid(row=0, column=3, padx=(6, 4))
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
        self.next_btn.grid(row=0, column=4, padx=(4, 0))

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

    def _build_step1(self) -> None:
        frame = self.step1_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(toolbar, text="Input-Bild:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(toolbar, textvariable=self.input_path_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(toolbar, text="Bild laden", command=self.choose_input_image).grid(row=0, column=2, padx=(6, 4))
        ttk.Button(toolbar, text="PNG speichern", command=self.export_intermediate_png).grid(row=0, column=3, padx=4)

        step1_actions = ttk.LabelFrame(toolbar, text="Workflow / Abschluss Schritt 1", padding=(8, 6, 8, 6))
        step1_actions.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        step1_actions.columnconfigure(3, weight=1)

        self.step1_next_action_btn = tk.Button(
            step1_actions,
            text="Weiter zur Vektorisierung →",
            command=self.next_step,
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=16,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.step1_next_action_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))

        ttk.Button(
            step1_actions,
            text="Zwischenbild nur aktualisieren",
            command=lambda: self.use_edited_for_vector(show_message=True),
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))

        ttk.Label(
            step1_actions,
            text="Hinweis: 'Weiter zur Vektorisierung' übernimmt das bearbeitete Bild automatisch. Der Aktualisieren-Button ist nur optional.",
            foreground="#555",
        ).grid(row=0, column=3, sticky="w")

        panes = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        panes.grid(row=1, column=0, sticky="nsew")

        preview = ttk.Frame(panes)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        preview_panes = ttk.Panedwindow(preview, orient=tk.HORIZONTAL)
        preview_panes.grid(row=0, column=0, sticky="nsew")
        self.step1_original_canvas = recolor.ZoomImageCanvas(preview_panes, "Original", self.on_pick_color)
        self.step1_edited_canvas = recolor.ZoomImageCanvas(preview_panes, "Bearbeitet / technische Zwischenstufe")
        preview_panes.add(self.step1_original_canvas, weight=1)
        preview_panes.add(self.step1_edited_canvas, weight=1)

        settings = ttk.Frame(panes)
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(0, weight=1)
        self.step1_notebook = ttk.Notebook(settings)
        self.step1_notebook.grid(row=0, column=0, sticky="nsew")
        self.step1_notebook.bind("<<NotebookTabChanged>>", lambda _e: self.on_step1_mode_changed())

        self.basic_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.manual_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.logo_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.step1_notebook.add(self.basic_tab, text="Basis: Farben reduzieren")
        self.step1_notebook.add(self.manual_tab, text="Erweitert: manuell")
        self.step1_notebook.add(self.logo_tab, text="Logo-Maske")
        self._build_step1_basic_tab()
        self._build_step1_manual_tab()
        self._build_step1_logo_tab()

        panes.add(preview, weight=3)
        panes.add(settings, weight=2)

    def _add_scale(self, parent: tk.Widget, row: int, label: str, variable: tk.Variable, from_: float, to: float, resolution: float) -> None:
        ttk.Label(parent, text=label, width=14).grid(row=row, column=0, sticky="w", pady=1)
        scale = tk.Scale(
            parent, from_=from_, to=to, resolution=resolution, orient="horizontal",
            variable=variable, showvalue=True, length=200, command=lambda _v: self.on_preprocess_changed()
        )
        scale.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=1)

    def _build_step1_basic_tab(self) -> None:
        tab = self.basic_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)

        prep = ttk.LabelFrame(tab, text="1) Bildvorbereitung", padding=8)
        prep.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        prep.columnconfigure(1, weight=1)
        self._add_scale(prep, 0, "Helligkeit", self.prep_brightness_var, -100, 100, 1)
        self._add_scale(prep, 1, "Kontrast", self.prep_contrast_var, -100, 100, 1)
        self._add_scale(prep, 2, "Schwarzpunkt", self.prep_black_var, 0, 254, 1)
        self._add_scale(prep, 3, "Weißpunkt", self.prep_white_var, 1, 255, 1)
        self._add_scale(prep, 4, "Gamma", self.prep_gamma_var, 0.30, 3.00, 0.05)
        ttk.Button(prep, text="Zurücksetzen", command=self.reset_preprocessing).grid(row=5, column=0, sticky="w", pady=(6, 0))
        ttk.Button(prep, text="Vorbereitung + Farben neu erkennen", command=self.detect_basic_colors).grid(row=5, column=1, sticky="w", pady=(6, 0))

        detect = ttk.LabelFrame(tab, text="2) Automatische Farberkennung", padding=8)
        detect.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for col in range(6):
            detect.columnconfigure(col, weight=0)
        ttk.Label(detect, text="Schwelle").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(detect, from_=0, to=255, textvariable=self.basic_threshold_var, width=7).grid(row=0, column=1, padx=(4, 12))
        ttk.Label(detect, text="Min. Fläche").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(detect, from_=1, to=999999, textvariable=self.basic_min_area_var, width=8).grid(row=0, column=3, padx=(4, 12))
        ttk.Label(detect, text="Max. Farben").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Spinbox(detect, from_=1, to=64, textvariable=self.basic_max_colors_var, width=7).grid(row=1, column=1, padx=(4, 12), pady=(4, 0))
        ttk.Label(detect, text="Alpha ab").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Spinbox(detect, from_=0, to=255, textvariable=self.basic_alpha_var, width=8).grid(row=1, column=3, padx=(4, 12), pady=(4, 0))
        ttk.Button(detect, text="Farben erkennen", command=self.detect_basic_colors).grid(row=0, column=4, rowspan=2, sticky="ns", padx=(4, 4))
        ttk.Button(detect, text="Kontrastfarben neu", command=self.reassign_basic_targets).grid(row=0, column=5, rowspan=2, sticky="ns")

        hint = ttk.Label(tab, text="Tipp: Schritt 1 schreibt exakte RGB-Farben ins Zwischen-PNG. Diese RGB-Werte werden in Schritt 2 automatisch als Layer-Regeln übernommen.", foreground="#555", wraplength=430)
        hint.grid(row=2, column=0, sticky="ew", pady=(0, 6))

        rows_box = ttk.LabelFrame(tab, text="3) Erkannte Farbbereiche", padding=4)
        rows_box.grid(row=3, column=0, sticky="nsew")
        rows_box.columnconfigure(0, weight=1)
        rows_box.rowconfigure(1, weight=1)
        header = ttk.Frame(rows_box)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Aktiv  Quelle / Anteil  → Ziel-RGB", foreground="#555").pack(anchor="w")
        self.basic_rows_scroll = recolor.ScrollableFrame(rows_box, height=210)
        self.basic_rows_scroll.grid(row=1, column=0, sticky="nsew")
        self.basic_rows_container = self.basic_rows_scroll.inner
        self.basic_rows_container.columnconfigure(0, weight=1)

    def _build_step1_manual_tab(self) -> None:
        tab = self.manual_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        top = ttk.Frame(tab)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(top, text="+ Farbumsetzung", command=self.add_manual_row).pack(side="left", padx=(0, 4))
        ttk.Button(top, text="- selektierte löschen", command=self.remove_selected_manual_row).pack(side="left", padx=(0, 12))
        self.manual_status_label = ttk.Label(top, text="Kurzer Klick ins Originalbild übernimmt Farbe in die selektierte Zeile. Ziehen verschiebt die Vorschau.")
        self.manual_status_label.pack(side="left")
        rows_box = ttk.LabelFrame(tab, text="Manuelle Farbumsetzungen", padding=4)
        rows_box.grid(row=1, column=0, sticky="nsew")
        rows_box.columnconfigure(0, weight=1)
        rows_box.rowconfigure(0, weight=1)
        self.manual_rows_scroll = recolor.ScrollableFrame(rows_box, height=360)
        self.manual_rows_scroll.grid(row=0, column=0, sticky="nsew")
        self.manual_rows_container = self.manual_rows_scroll.inner
        self.manual_rows_container.columnconfigure(0, weight=1)

    def _build_step1_logo_tab(self) -> None:
        tab = self.logo_tab
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Für graue Logos, Schatten oder Verläufe: Maske über lokalen Kontrast erzeugen.", foreground="#555", wraplength=480).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Label(tab, text="Logo-Schwelle").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Spinbox(tab, from_=1, to=100, textvariable=self.logo_mask_threshold_var, width=8).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(tab, text="höher = weniger wird schwarz", foreground="#555").grid(row=1, column=2, sticky="w", padx=(8, 0))
        ttk.Label(tab, text="Hintergrund-Radius").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Spinbox(tab, from_=5, to=151, increment=2, textvariable=self.logo_mask_blur_var, width=8).grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(tab, text="größer = Schatten/Verläufe werden eher ignoriert", foreground="#555").grid(row=2, column=2, sticky="w", padx=(8, 0))
        ttk.Label(tab, text="Logo RGB").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(tab, textvariable=self.logo_mask_fg_var, width=14).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(tab, text="Hintergrund RGB").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(tab, textvariable=self.logo_mask_bg_var, width=14).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Checkbutton(tab, text="kleine Pixelstörungen glätten", variable=self.logo_mask_clean_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(tab, text="Logo-Maske erzeugen", command=self.create_logo_mask_preview).grid(row=6, column=0, sticky="w", pady=(12, 0))
        ttk.Button(tab, text="Maske entfernen / normale Vorschau", command=self.clear_logo_mask).grid(row=6, column=1, sticky="w", pady=(12, 0))

    def _build_step2(self) -> None:
        frame = self.step2_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(toolbar, text="Zwischenbild:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(toolbar, textvariable=self.vector_source_name_var, foreground="#555").grid(row=0, column=1, sticky="w")
        ttk.Button(toolbar, text="PNG direkt laden", command=self.load_vector_png_direct).grid(row=0, column=2, padx=(6, 4))
        ttk.Label(toolbar, text="Output:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        ttk.Entry(toolbar, textvariable=self.output_path_var).grid(row=1, column=1, sticky="ew", pady=(4, 0))
        ttk.Button(toolbar, text="Speichern als", command=self.choose_vector_output).grid(row=1, column=2, padx=(6, 4), pady=(4, 0))
        ttk.Label(toolbar, text="Pixel zu mm:").grid(row=1, column=3, sticky="w", padx=(8, 4), pady=(4, 0))
        ttk.Entry(toolbar, textvariable=self.pixel_to_mm_var, width=8).grid(row=1, column=4, sticky="w", pady=(4, 0))

        ttk.Label(toolbar, text="Kompatibilität:").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(6, 0))
        compat_box = ttk.Combobox(
            toolbar,
            textvariable=self.dxf_compatibility_var,
            values=list(DXF_COMPATIBILITY_PRESETS.keys()),
            state="readonly",
            width=32,
        )
        compat_box.grid(row=2, column=1, sticky="w", pady=(6, 0))
        compat_box.bind("<<ComboboxSelected>>", lambda _event: self.on_dxf_compatibility_changed())

        ttk.Label(toolbar, text="DXF-Format:").grid(row=2, column=2, sticky="w", padx=(12, 4), pady=(6, 0))
        version_box = ttk.Combobox(
            toolbar,
            textvariable=self.dxf_version_var,
            values=list(DXF_VERSION_CHOICES.values()),
            state="readonly",
            width=55,
        )
        version_box.grid(row=2, column=3, columnspan=2, sticky="w", pady=(6, 0))
        version_box.bind("<<ComboboxSelected>>", lambda _event: self.on_dxf_version_changed())

        ttk.Label(
            toolbar,
            textvariable=self.dxf_compatibility_info_var,
            foreground="#555",
            wraplength=520,
            justify="left",
        ).grid(row=2, column=5, columnspan=3, sticky="w", padx=(8, 0), pady=(6, 0))

        # Die Abschluss-/Aktionsbuttons sind bewusst separat gruppiert.
        # Dadurch erkennt man schneller: Hier startet die Berechnung bzw. der Export.
        actions = ttk.LabelFrame(toolbar, text="Abschluss / Aktionen", padding=(8, 6, 8, 6))
        actions.grid(row=3, column=0, columnspan=8, sticky="ew", pady=(8, 0))
        actions.columnconfigure(4, weight=1)

        self.auto_action_btn = tk.Button(
            actions,
            text="1  Optional: Auto-Werte testen",
            command=self.auto_optimize_vector_settings,
            bg="#7c3aed",
            fg="white",
            activebackground="#6d28d9",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=14,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.auto_action_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.detect_action_btn = tk.Button(
            actions,
            text="2  Erkennen / Vorschau",
            command=self.detect_and_preview_vector,
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=14,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.detect_action_btn.grid(row=0, column=1, sticky="w", padx=(0, 8))

        self.export_action_btn = tk.Button(
            actions,
            text="3  Export DXF / SVG",
            command=self.export_vector_file,
            bg="#15803d",
            fg="white",
            activebackground="#166534",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=16,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.export_action_btn.grid(row=0, column=2, sticky="w", padx=(0, 12))

        ttk.Label(
            actions,
            text="Auto-Werte ist optional und rechnet selbst eine Vorschau. Danach Vorschau prüfen oder direkt exportieren.",
            foreground="#555",
            wraplength=520,
            justify="left",
        ).grid(row=0, column=4, sticky="w")

        panes = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        panes.grid(row=1, column=0, sticky="nsew")

        settings = ttk.Frame(panes)
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(1, weight=1)
        ttk.Label(settings, text="Farben / Layer", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        table_box = ttk.LabelFrame(settings, text="Dynamische Farbtabelle", padding=4)
        table_box.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        table_box.columnconfigure(0, weight=1)
        table_box.rowconfigure(1, weight=1)
        header = ttk.Frame(table_box)
        header.grid(row=0, column=0, sticky="ew")
        for col, text in enumerate(["Name", "RGB", "Tol.", "Layer", "Export", "Min.", "Epsilon", ""]):
            ttk.Label(header, text=text, width=[14,13,7,14,7,7,7,3][col]).grid(row=0, column=col, padx=2, sticky="w")
        self.vector_rows_scroll = recolor.ScrollableFrame(table_box, height=270)
        self.vector_rows_scroll.grid(row=1, column=0, sticky="nsew")
        self.vector_table = ttk.Frame(self.vector_rows_scroll.inner)
        self.vector_table.grid(row=0, column=0, sticky="ew")

        row_buttons = ttk.Frame(settings)
        row_buttons.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(row_buttons, text="+ Farbe", command=self.add_empty_vector_row).pack(side="left", padx=(0, 4))
        ttk.Label(row_buttons, text="Profil:").pack(side="left", padx=(12, 4))
        ttk.Combobox(row_buttons, textvariable=self.profile_var, values=list(vector.PROFILE_ROWS.keys()), state="readonly", width=18).pack(side="left")
        ttk.Button(row_buttons, text="Anwenden", command=lambda: self.load_vector_profile(self.profile_var.get())).pack(side="left", padx=(4, 0))

        opts = ttk.LabelFrame(settings, text="Vektor-Optionen", padding=8)
        opts.grid(row=3, column=0, sticky="ew")
        opts.columnconfigure(2, weight=1)
        ttk.Label(opts, text="Vektorart").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opts, textvariable=self.vector_mode_var, values=["Flächenkontur", "Mittellinie / Gravur"], state="readonly", width=20).grid(row=0, column=1, sticky="w", padx=(4, 12))
        ttk.Label(opts, text="Linien zusammenführen px").grid(row=0, column=2, sticky="w")
        ttk.Entry(opts, textvariable=self.centerline_merge_px_var, width=8).grid(row=0, column=3, sticky="w", padx=(4, 0))
        ttk.Checkbutton(opts, text="Nur geschlossene Pfade", variable=self.closed_paths_only_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="SVG-Flächen füllen (Export)", variable=self.fill_closed_shapes_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Checkbutton(opts, text="Bezier für SVG", variable=self.use_bezier_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Vorschau-Modus").grid(row=6, column=0, sticky="w", pady=(8, 0))
        preview_mode_box = ttk.Combobox(opts, textvariable=self.preview_mode_var, values=["Objektcheck", "Konturlinien", "Farbmaske"], state="readonly", width=18)
        preview_mode_box.grid(row=6, column=1, sticky="w", padx=(4, 12), pady=(8, 0))
        preview_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.render_vector_preview())
        ttk.Checkbutton(opts, text="Lose Ankerpunkte entfernen", variable=self.remove_loose_points_var).grid(row=1, column=2, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="Rundungen glätten", variable=self.smooth_contours_var).grid(row=2, column=2, sticky="w", pady=(2, 0))
        ttk.Entry(opts, textvariable=self.smooth_strength_var, width=8).grid(row=2, column=3, sticky="w", padx=(4, 0), pady=(2, 0))
        ttk.Label(opts, text="Kleine Objekte löschen").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(opts, textvariable=self.cleanup_mode_var, values=["Aus", "mm²", "% Bildfläche"], state="readonly", width=12).grid(row=4, column=1, sticky="w", padx=(4, 12), pady=(8, 0))
        ttk.Label(opts, text="mm²").grid(row=4, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(opts, textvariable=self.min_object_area_mm2_var, width=8).grid(row=4, column=3, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Label(opts, text="% Bildfläche").grid(row=5, column=2, sticky="w", pady=(2, 0))
        ttk.Entry(opts, textvariable=self.min_object_percent_var, width=8).grid(row=5, column=3, sticky="w", padx=(4, 0), pady=(2, 0))

        preview = ttk.Frame(panes)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)

        select_tools = ttk.LabelFrame(preview, text="Pfad-Auswahl", padding=(6, 4, 6, 4))
        select_tools.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        select_tools.columnconfigure(2, weight=1)
        self.selection_mode_check = ttk.Checkbutton(
            select_tools,
            text="Auswahl-Modus",
            variable=self.vector_selection_mode_var,
            command=self.update_vector_selection_mode_ui,
        )
        self.selection_mode_check.grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Button(select_tools, text="Ausgewählte Pfade entfernen", command=self.remove_selected_contour).grid(row=0, column=1, sticky="w", padx=(0, 6))
        ttk.Button(select_tools, text="Auswahl aufheben", command=self.clear_selected_contour).grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(select_tools, textvariable=self.selected_contour_text_var, foreground="#555").grid(row=0, column=3, sticky="w")
        ttk.Label(
            select_tools,
            text="Auswahl-Modus EIN: Klick = Pfad wählen, STRG+Klick = hinzufügen/umschalten, ALT+Klick = direkt entfernen. Auswahl-Modus AUS: Klick/Ziehen verschiebt die Vorschau; nur STRG+Klick wählt temporär.",
            foreground="#777",
            wraplength=840,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 0))

        preview_panes = ttk.Panedwindow(preview, orient=tk.HORIZONTAL)
        preview_panes.grid(row=1, column=0, sticky="nsew")
        self.step2_original_canvas = recolor.ZoomImageCanvas(preview_panes, "Zwischen-PNG")
        self.step2_vector_canvas = recolor.ZoomImageCanvas(preview_panes, "Vektor-Vorschau")
        # Robuste Pfad-Auswahl: Wir hängen uns zusätzlich an den normalen Klick.
        # Dadurch funktioniert Auswahl auch dann, wenn STRG/ALT-Bindings vom System/Tk nicht sauber ankommen.
        # Ohne Auswahl-Modus bleibt normales Klicken/Ziehen weiterhin Pan/Verschieben.
        self.step2_vector_canvas.canvas.bind("<ButtonPress-1>", self.on_vector_mouse_press, add="+")
        self.step2_vector_canvas.canvas.bind("<ButtonRelease-1>", self.on_vector_mouse_release, add="+")
        self.step2_vector_canvas.canvas.bind("<Delete>", lambda _event: self.remove_selected_contour(), add="+")
        self.step2_vector_canvas.canvas.bind("<BackSpace>", lambda _event: self.remove_selected_contour(), add="+")
        preview_panes.add(self.step2_original_canvas, weight=1)
        preview_panes.add(self.step2_vector_canvas, weight=1)

        panes.add(settings, weight=2)
        panes.add(preview, weight=3)

    # ------------------------------------------------------------------ Navigation
    def show_step(self, index: int) -> None:
        self.current_step = max(0, min(1, index))
        if self.current_step == 0:
            self.step1_frame.tkraise()
            self.step_label.configure(text="Schritt 1 von 2: Bild bearbeiten / Farben exakt vorbereiten")
            self.back_btn.configure(text="← Zurück", state="disabled", bg="#9ca3af", fg="#eeeeee", cursor="arrow")
            self.next_btn.configure(
                text="Weiter zur Vektorisierung →",
                state="normal",
                bg="#2563eb",
                fg="white",
                activebackground="#1d4ed8",
                cursor="hand2",
            )
        else:
            self.step2_frame.tkraise()
            self.step_label.configure(text="Schritt 2 von 2: Vektorisieren / DXF oder SVG exportieren")
            self.back_btn.configure(
                text="← Zurück zu Schritt 1",
                state="normal",
                bg="#f97316",
                fg="white",
                activebackground="#ea580c",
                cursor="hand2",
            )
            self.next_btn.configure(
                text="Export DXF / SVG →",
                state="normal",
                bg="#15803d",
                fg="white",
                activebackground="#166534",
                cursor="hand2",
            )

    def next_step(self) -> None:
        if self.current_step == 0:
            if self.use_edited_for_vector(show_message=False):
                self.show_step(1)
        else:
            self.export_vector_file()

    def back_step(self) -> None:
        self.show_step(0)

    def get_selected_dxf_version(self) -> str:
        return _dxf_version_from_choice(self.dxf_version_var.get())

    def on_dxf_compatibility_changed(self) -> None:
        profile = self.dxf_compatibility_var.get()
        version, info = DXF_COMPATIBILITY_PRESETS.get(
            profile,
            DXF_COMPATIBILITY_PRESETS["Illustrator / CorelDRAW (empfohlen)"],
        )
        if profile != "Manuell":
            self.dxf_version_var.set(_dxf_choice_for_version(version))
        self.dxf_compatibility_info_var.set(f"{info}  Aktuell: DXF {self.get_selected_dxf_version()}")

    def on_dxf_version_changed(self) -> None:
        # Wenn der Benutzer das Format selbst ändert, soll sichtbar sein,
        # dass nicht mehr strikt das Programmprofil gilt.
        selected_version = self.get_selected_dxf_version()
        current_profile = self.dxf_compatibility_var.get()
        expected_version = DXF_COMPATIBILITY_PRESETS.get(current_profile, ("", ""))[0]
        if current_profile != "Manuell" and selected_version != expected_version:
            self.dxf_compatibility_var.set("Manuell")
        self.dxf_compatibility_info_var.set(
            f"Manuelles DXF-Format gewählt: {selected_version}. "
            "Bei Grafikprogrammen zuerst R2000 probieren."
        )

    def set_progress(self, value: float, status: Optional[str] = None) -> None:
        self.progress_var.set(max(0.0, min(100.0, value)))
        if status is not None:
            self.status_var.set(status)
        self.update_idletasks()

    # ------------------------------------------------------------------ Schritt 1 Logik
    def choose_input_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Bild laden",
            filetypes=[("Bilddateien", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"), ("Alle Dateien", "*.*")],
        )
        if path:
            self.input_path_var.set(path)
            self.load_input_image(path)

    def load_input_image(self, path: str) -> None:
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as exc:
            messagebox.showerror("Fehler beim Laden", str(exc))
            return
        self.current_path = Path(path)
        self.original_image = img
        self.prepared_image = None
        self.edited_image = self.get_prepared_image(force=True)
        self.special_result_image = None
        self.step1_original_canvas.set_image(self.original_image, reset_view=True)
        self.step1_edited_canvas.set_image(self.edited_image, reset_view=True)
        if not self.output_path_var.get():
            self.output_path_var.set(str(self.current_path.with_suffix(".dxf")))
        self.status_var.set(f"Bild geladen: {self.current_path.name} | {img.width} x {img.height}px")
        if self.step1_notebook.index(self.step1_notebook.select()) == 0:
            self.detect_basic_colors()
        else:
            self.update_step1_preview()

    def get_prepared_image(self, force: bool = False) -> Optional[Image.Image]:
        if self.original_image is None:
            return None
        if self.prepared_image is not None and not force:
            return self.prepared_image
        self.prepared_image = recolor.apply_image_preparation(
            self.original_image,
            brightness=int(self.prep_brightness_var.get()),
            contrast=int(self.prep_contrast_var.get()),
            black_point=int(self.prep_black_var.get()),
            white_point=int(self.prep_white_var.get()),
            gamma=float(self.prep_gamma_var.get()),
        )
        return self.prepared_image

    def on_preprocess_changed(self) -> None:
        self.special_result_image = None
        self.get_prepared_image(force=True)
        self.schedule_step1_preview()

    def reset_preprocessing(self) -> None:
        self.prep_brightness_var.set(0)
        self.prep_contrast_var.set(0)
        self.prep_black_var.set(0)
        self.prep_white_var.set(255)
        self.prep_gamma_var.set(1.0)
        self.on_preprocess_changed()

    def schedule_step1_preview(self) -> None:
        if self.preview_after_id:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
        self.preview_after_id = self.after(180, self.update_step1_preview)

    def on_step1_mode_changed(self) -> None:
        self.update_step1_preview()

    def clear_basic_rows(self) -> None:
        for row in self.basic_rows:
            row.destroy()
        self.basic_rows.clear()

    def detect_basic_colors(self) -> None:
        if self.original_image is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein Bild laden.")
            return
        try:
            base = self.get_prepared_image(force=True)
            detected = recolor.RecolorApp.detect_colors_by_threshold(
                base,
                threshold=max(0, min(255, int(self.basic_threshold_var.get()))),
                min_area=max(1, int(self.basic_min_area_var.get())),
                max_colors=max(1, min(64, int(self.basic_max_colors_var.get()))),
                alpha_min=max(0, min(255, int(self.basic_alpha_var.get()))),
            )
        except Exception as exc:
            messagebox.showerror("Fehler", f"Farben konnten nicht erkannt werden:\n{exc}")
            return
        self.clear_basic_rows()
        for i, item in enumerate(detected):
            self.basic_rows.append(BasicWorkflowRow(self, self.basic_rows_container, i, item))
        self.status_var.set(f"{len(detected)} Farbbereiche erkannt. Ziel-RGB kann direkt in der Tabelle angepasst werden.")
        self.update_step1_preview()

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
            self.manual_status_label.configure(text=f"Selektierte Zeile: #{self.selected_manual_row_var.get() + 1} | Klick ins Original übernimmt die Farbe.")
        except Exception:
            pass

    def on_pick_color(self, rgb: RGB, x: int, y: int) -> None:
        if self.step1_notebook.index(self.step1_notebook.select()) != 1:
            self.status_var.set(f"Pixel-Farbe bei x={x}, y={y}: {_rgb_to_text(rgb)}")
            return
        if not self.manual_rows:
            self.add_manual_row()
        index = max(0, min(self.selected_manual_row_var.get(), len(self.manual_rows) - 1))
        self.manual_rows[index].set_source_rgb(rgb)
        self.status_var.set(f"Farbe {_rgb_to_text(rgb)} in Zeile #{index + 1} übernommen.")

    def collect_basic_mappings(self) -> List[Any]:
        mappings = []
        tol = max(0, min(255, int(self.basic_threshold_var.get())))
        for row in self.basic_rows:
            try:
                mapping = row.get_mapping(tol)
                if mapping:
                    mappings.append(mapping)
            except Exception as exc:
                self.status_var.set(f"Ungültige Basis-Farbe: {exc}")
        return mappings

    def collect_manual_mappings(self) -> List[Any]:
        mappings = []
        for row in self.manual_rows:
            try:
                mapping = row.get_mapping()
                if mapping:
                    mappings.append(mapping)
            except Exception as exc:
                self.status_var.set(f"Ungültige manuelle Farbe: {exc}")
        return mappings

    def update_step1_preview(self) -> None:
        self.preview_after_id = None
        if self.original_image is None:
            return
        mode = self.step1_notebook.index(self.step1_notebook.select())
        try:
            if mode == 2 and self.special_result_image is not None:
                self.edited_image = self.special_result_image.copy()
            elif mode == 1:
                mappings = self.collect_manual_mappings()
                self.edited_image = recolor.RecolorApp.apply_mappings(self.original_image, mappings) if mappings else self.original_image.copy()
            else:
                base = self.get_prepared_image(force=False)
                mappings = self.collect_basic_mappings()
                self.edited_image = recolor.RecolorApp.apply_mappings(base, mappings) if mappings else base.copy()
        except Exception as exc:
            self.status_var.set(f"Vorschaufehler: {exc}")
            return
        reset = self.step1_edited_canvas.image is None or self.step1_edited_canvas.image.size != self.edited_image.size
        self.step1_edited_canvas.set_image(self.edited_image, reset_view=reset)

    def create_logo_mask_preview(self) -> None:
        if self.original_image is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein Bild laden.")
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
            )
            self.edited_image = self.special_result_image.copy()
            self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)
            self.status_var.set("Logo-Maske erzeugt. Diese Maske kann direkt in Schritt 2 vektorisiert werden.")
        except Exception as exc:
            messagebox.showerror("Fehler", f"Logo-Maske konnte nicht erzeugt werden:\n{exc}")

    def clear_logo_mask(self) -> None:
        self.special_result_image = None
        self.update_step1_preview()

    def export_intermediate_png(self) -> None:
        self.update_step1_preview()
        if self.edited_image is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein Bild bearbeiten.")
            return
        initial = "workflow_zwischenbild.png"
        if self.current_path:
            initial = f"{self.current_path.stem}_workflow_zwischenbild.png"
        path = filedialog.asksaveasfilename(title="Zwischen-PNG speichern", defaultextension=".png", initialfile=initial, filetypes=[("PNG", "*.png")])
        if not path:
            return
        try:
            self.edited_image.save(path, format="PNG")
            self.status_var.set(f"Zwischen-PNG gespeichert: {path}")
        except Exception as exc:
            messagebox.showerror("Exportfehler", str(exc))

    def use_edited_for_vector(self, show_message: bool = False) -> bool:
        self.update_step1_preview()
        if self.edited_image is None:
            messagebox.showwarning("Kein Zwischenbild", "Bitte zuerst ein Bild laden oder bearbeiten.")
            return False
        rgb_image = _flatten_rgba_to_rgb(self.edited_image)
        self.vector_image_rgb = np.array(rgb_image)
        self.detected_contours = []
        name = "Zwischenbild aus Schritt 1"
        if self.current_path:
            name = f"{self.current_path.name} → bearbeitet"
        self.vector_source_name_var.set(name)
        self.step2_original_canvas.set_image(rgb_image, reset_view=True)
        self.step2_vector_canvas.set_image(None, reset_view=True)
        self.autofill_vector_rows_from_image()
        if not self.output_path_var.get():
            if self.current_path:
                self.output_path_var.set(str(self.current_path.with_suffix(".dxf")))
            else:
                self.output_path_var.set("vektor_export.dxf")
        self.status_var.set("Bearbeitetes Bild ist für Schritt 2 bereit. Farb-/Layer-Regeln wurden automatisch vorgeschlagen.")
        if show_message:
            messagebox.showinfo("Übernommen", "Das bearbeitete Bild wurde für Schritt 2 übernommen.")
        return True

    # ------------------------------------------------------------------ Schritt 2 Logik
    def clear_vector_rows(self) -> None:
        for row in self.vector_rows:
            row.destroy()
        self.vector_rows.clear()

    def add_vector_row(self, name: str, rgb: str, tolerance: str, layer: str, export: bool, min_area: str, epsilon: str) -> None:
        row_index = len(self.vector_rows) + 1
        row = vector.ColorRow(self.vector_table, row_index, name, rgb, tolerance, layer, export, min_area, epsilon, remove_callback=self.remove_vector_row)
        self.vector_rows.append(row)

    def add_empty_vector_row(self) -> None:
        self.add_vector_row("Neue Farbe", "255,0,0", "10", "CUT_LAYER", True, "20", "1.5")

    def remove_vector_row(self, row: Any) -> None:
        row.destroy()
        if row in self.vector_rows:
            self.vector_rows.remove(row)
        self.redraw_vector_rows()

    def redraw_vector_rows(self) -> None:
        saved = [(r.name_var.get(), r.rgb_var.get(), r.tolerance_var.get(), r.layer_var.get(), r.export_var.get(), r.min_area_var.get(), r.epsilon_var.get()) for r in self.vector_rows]
        self.clear_vector_rows()
        for data in saved:
            self.add_vector_row(*data)

    def load_vector_profile(self, profile_name: str) -> None:
        rows = vector.PROFILE_ROWS.get(profile_name)
        if rows is None:
            messagebox.showerror("Profil", f"Unbekanntes Profil: {profile_name}")
            return
        self.clear_vector_rows()
        for row_data in rows:
            self.add_vector_row(*row_data)
        self.status_var.set(f"Profil geladen: {profile_name}")

    def autofill_vector_rows_from_image(self) -> None:
        if self.vector_image_rgb is None:
            return
        pixels = self.vector_image_rgb.reshape(-1, 3)
        unique, counts = np.unique(pixels, axis=0, return_counts=True)
        order = np.argsort(counts)[::-1]
        max_colors = min(32, len(order))
        self.clear_vector_rows()
        for idx in order[:max_colors]:
            rgb = tuple(int(v) for v in unique[idx])
            name = _known_color_name(rgb)
            is_white = rgb == (255, 255, 255)
            is_near_white = all(v >= 245 for v in rgb)
            export = not (is_white or is_near_white)
            safe = name.upper().replace("WEISS", "WHITE").replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace(" ", "_")
            layer = f"CUT_{safe}" if export else f"IGNORE_{safe}"
            tol = "8" if export else "5"
            min_area = "50" if export else "50"
            eps = "1.5" if export else "1.5"
            self.add_vector_row(name, _rgb_to_text(rgb), tol, layer, export, min_area, eps)
        if not self.vector_rows:
            self.load_vector_profile("Standard")

    def load_vector_png_direct(self) -> None:
        path = filedialog.askopenfilename(title="PNG für Vektorisierung laden", filetypes=[("PNG", "*.png"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            img = Image.open(path).convert("RGB")
            self.vector_image_rgb = np.array(img)
            self.vector_source_name_var.set(Path(path).name)
            self.step2_original_canvas.set_image(img, reset_view=True)
            self.step2_vector_canvas.set_image(None, reset_view=True)
            if not self.output_path_var.get():
                self.output_path_var.set(str(Path(path).with_suffix(".dxf")))
            self.autofill_vector_rows_from_image()
            self.status_var.set(f"PNG geladen: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Fehler beim Laden", str(exc))

    def choose_vector_output(self) -> None:
        path = filedialog.asksaveasfilename(title="Output speichern", defaultextension=".dxf", filetypes=[("DXF-Datei", "*.dxf"), ("SVG-Datei", "*.svg"), ("Alle Dateien", "*.*")])
        if path:
            self.output_path_var.set(path)

    def get_vector_rules(self) -> List[Any]:
        return [row.to_rule() for row in self.vector_rows]

    def get_pixel_to_mm(self) -> float:
        value = float(self.pixel_to_mm_var.get().replace(",", "."))
        if value <= 0:
            raise ValueError("Pixel zu mm muss größer als 0 sein.")
        return value

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

    def get_centerline_merge_px(self) -> float:
        text = self.centerline_merge_px_var.get().strip()
        return max(0.0, float(text.replace(",", "."))) if text else 0.0

    def detect_and_preview_vector(self) -> None:
        if self.vector_image_rgb is None:
            messagebox.showwarning("Kein Zwischenbild", "Bitte zuerst Schritt 1 übernehmen oder ein PNG direkt laden.")
            return
        try:
            self.set_progress(5, "Vektor-Regeln werden gelesen...")
            self.selected_contour_index = None
            self.selected_contour_indices.clear()
            self.selected_contour_text_var.set("Kein Pfad ausgewählt")
            rules = self.get_vector_rules()
            self.last_rules = rules
            pixel_to_mm = self.get_pixel_to_mm()
            centerline_mode = self.vector_mode_var.get() == "Mittellinie / Gravur"
            self.set_progress(10, "Konturen werden erkannt...")
            contours = vector.detect_all_contours(
                self.vector_image_rgb,
                rules,
                closed_paths_only=self.closed_paths_only_var.get() and not centerline_mode,
                remove_loose_points=self.remove_loose_points_var.get(),
                smooth_iterations=self.get_smooth_iterations(),
                centerline_mode=centerline_mode,
                centerline_merge_px=self.get_centerline_merge_px(),
                progress_callback=lambda fraction: self.set_progress(10 + fraction * 65, "Konturen werden erkannt...")
            )
            before = len(contours)
            self.set_progress(80, "Kleine Objekte werden gefiltert...")
            h, w = self.vector_image_rgb.shape[:2]
            self.detected_contours = vector.filter_small_contours(
                contours,
                self.cleanup_mode_var.get(),
                self.get_min_object_area_mm2(),
                self.get_min_object_percent(),
                (w, h),
                pixel_to_mm,
            )
            self.render_vector_preview()
            exported = sum(1 for c in self.detected_contours if c.rule.export)
            points = sum(len(c.points) for c in self.detected_contours if c.rule.export)
            removed = before - len(self.detected_contours)
            self.set_progress(100, f"Konturen: {len(self.detected_contours)} | Export aktiv: {exported} | Punkte: {points} | Cleanup entfernt: {removed}")
        except Exception as exc:
            self.set_progress(0, "Fehler bei Erkennung")
            messagebox.showerror("Fehler bei Erkennung", str(exc))

    def render_vector_preview(self) -> None:
        if self.vector_image_rgb is None:
            return

        mode = self.preview_mode_var.get()
        reset = self.step2_vector_canvas.image is None
        if mode == "Farbmaske":
            preview = self.build_filled_mask_preview_image()
            self.draw_selected_contour_overlay(preview)
            self.step2_vector_canvas.set_image(preview, reset_view=reset)
            return
        if mode == "Objektcheck":
            preview = self.build_object_check_preview_image()
            self.draw_selected_contour_overlay(preview)
            self.step2_vector_canvas.set_image(preview, reset_view=reset)
            return

        h, w = self.vector_image_rgb.shape[:2]
        preview = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(preview)
        for item in self.detected_contours:
            if not item.rule.export or len(item.points) < 2:
                continue
            color = tuple(int(v) for v in item.rule.rgb)
            pts = [(float(x), float(y)) for x, y in item.points]
            if item.closed and len(pts) >= 3:
                draw.line(pts + [pts[0]], fill=color, width=2, joint="curve")
            else:
                draw.line(pts, fill=color, width=2, joint="curve")
        self.draw_selected_contour_overlay(preview)
        self.step2_vector_canvas.set_image(preview, reset_view=reset)

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
                self.selected_contour_text_var.set("Kein Pfad ausgewählt")
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

    def build_filled_mask_preview_image(self) -> Image.Image:
        """
        Farbige Kontrollansicht aus den aktuell erkannten Vektorkonturen.

        Wichtig ab v10:
        Diese Vorschau wird nicht mehr direkt aus dem ursprünglichen Rasterbild
        aufgebaut, sondern aus self.detected_contours. Dadurch verschwinden manuell
        entfernte Pfade sofort auch aus der Vorschau und später aus dem Export.
        """
        if self.vector_image_rgb is None:
            return Image.new("RGB", (1, 1), (255, 255, 255))

        h, w = self.vector_image_rgb.shape[:2]
        preview = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(preview)

        if not self.detected_contours:
            # Vor der ersten Erkennung weiterhin eine einfache Raster-Farbmaske zeigen.
            rules = self.last_rules or self.get_vector_rules()
            for rule in rules:
                if not rule.export:
                    continue
                mask = vector.make_color_mask(self.vector_image_rgb, rule.rgb, rule.tolerance)
                mask = vector.remove_small_components(mask, rule.min_area)
                color_layer = Image.new("RGB", (w, h), tuple(int(v) for v in rule.rgb))
                preview.paste(color_layer, mask=Image.fromarray(mask))
            return preview

        for item in self.detected_contours:
            if not item.rule.export or len(item.points) < 2:
                continue
            color = tuple(int(v) for v in item.rule.rgb)
            pts = [(float(x), float(y)) for x, y in item.points]
            if item.closed and len(pts) >= 3:
                draw.polygon(pts, fill=color)
                draw.line(pts + [pts[0]], fill=(0, 0, 0), width=1, joint="curve")
            else:
                draw.line(pts, fill=color, width=3, joint="curve")

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
        preview = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(preview)
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

        for index, item in enumerate(self.detected_contours):
            if not item.rule.export or len(item.points) < 2:
                continue
            color = palette[index % len(palette)]
            pts = [(float(x), float(y)) for x, y in item.points]
            if item.closed and len(pts) >= 3:
                draw.polygon(pts, fill=color)
                draw.line(pts + [pts[0]], fill=(0, 0, 0), width=1, joint="curve")
            else:
                draw.line(pts, fill=color, width=4, joint="curve")

        return preview

    def update_vector_selection_mode_ui(self) -> None:
        """Zeigt optisch, ob Klicks in der Vektorvorschau auswählen oder nur verschieben."""
        try:
            if self.vector_selection_mode_var.get():
                self.step2_vector_canvas.canvas.configure(cursor="crosshair")
                self.status_var.set("Auswahl-Modus aktiv: Klick in die Vektor-Vorschau wählt einen Pfad. STRG fügt hinzu, ALT entfernt direkt.")
            else:
                self.step2_vector_canvas.canvas.configure(cursor="")
                self.status_var.set("Auswahl-Modus aus: Vorschau kann normal verschoben werden.")
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
            self.selected_contour_text_var.set("Noch keine Konturen erkannt")
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
            self.selected_contour_text_var.set("Kein Pfad getroffen")
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
        self.status_var.set("Pfad-Auswahl geändert. Entf oder Button entfernt die ausgewählten Pfade.")
        self.render_vector_preview()

    def remove_contour_at_canvas_position(self, canvas_x: int, canvas_y: int) -> None:
        index = self.find_contour_index_at_canvas_position(canvas_x, canvas_y)
        if index is None:
            self.selected_contour_text_var.set("Kein Pfad getroffen")
            self.render_vector_preview()
            return
        self.selected_contour_indices = {index}
        self.selected_contour_index = index
        self.remove_selected_contour()

    def update_selected_contour_text(self) -> None:
        count = len(self.selected_contour_indices)
        if count <= 0:
            self.selected_contour_text_var.set("Kein Pfad ausgewählt")
            return
        if count == 1:
            selected_index = next(iter(self.selected_contour_indices))
            if not (0 <= selected_index < len(self.detected_contours)):
                self.selected_contour_indices.clear()
                self.selected_contour_index = None
                self.selected_contour_text_var.set("Kein Pfad ausgewählt")
                return
            contour = self.detected_contours[selected_index]
            points = len(getattr(contour, "points", []))
            area = float(getattr(contour, "area", 0.0))
            layer = getattr(contour.rule, "layer", getattr(contour.rule, "name", "Layer"))
            self.selected_contour_text_var.set(
                f"Ausgewählt: Pfad #{selected_index + 1} | Layer {layer} | Punkte {points} | Fläche ca. {area:.0f}px²"
            )
            return
        self.selected_contour_text_var.set(f"{count} Pfade ausgewählt | Entf oder Button entfernt alle ausgewählten Pfade")

    def clear_selected_contour(self) -> None:
        self.selected_contour_index = None
        self.selected_contour_indices.clear()
        self.selected_contour_text_var.set("Kein Pfad ausgewählt")
        self.render_vector_preview()

    def remove_selected_contour(self) -> None:
        indices = sorted(self.selected_contour_indices, reverse=True)
        if not indices and self.selected_contour_index is not None:
            indices = [self.selected_contour_index]
        indices = [idx for idx in indices if 0 <= idx < len(self.detected_contours)]
        if not indices:
            self.status_var.set("Kein Pfad ausgewählt.")
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
            self.selected_contour_text_var.set(f"Entfernt: Pfad #{idx + 1} | Layer {layer} | Punkte {points}")
        else:
            self.selected_contour_text_var.set(f"Entfernt: {len(removed_info)} Pfade")
        exported = sum(1 for c in self.detected_contours if c.rule.export)
        total_points = sum(len(c.points) for c in self.detected_contours if c.rule.export)
        self.status_var.set(f"Pfad entfernt. Verbleibend: {len(self.detected_contours)} | Export aktiv: {exported} | Punkte: {total_points}")
        # Bildreferenz kurz leeren, damit Tkinter garantiert neu rendert.
        try:
            self.step2_vector_canvas.tk_image = None
        except Exception:
            pass
        self.render_vector_preview()

    def auto_optimize_vector_settings(self) -> None:
        if self.vector_image_rgb is None:
            messagebox.showwarning("Kein Zwischenbild", "Bitte zuerst Schritt 1 übernehmen oder ein PNG direkt laden.")
            return
        original_epsilons = [row.epsilon_var.get() for row in self.vector_rows]
        try:
            self.set_progress(0, "Auto-Werte werden vorbereitet...")
            pixel_to_mm = self.get_pixel_to_mm()
            centerline_mode = self.vector_mode_var.get() == "Mittellinie / Gravur"
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
                self.set_progress(idx / max(1, len(candidates)) * 90, f"Auto-Werte: Test {idx + 1}/{len(candidates)}...")
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
                    remove_loose_points=self.remove_loose_points_var.get(),
                    smooth_iterations=int(cand["smooth"]),
                    centerline_mode=centerline_mode,
                    centerline_merge_px=float(cand["merge"]),
                )
                contours = vector.filter_small_contours(contours, self.cleanup_mode_var.get(), self.get_min_object_area_mm2(), self.get_min_object_percent(), (w, h), pixel_to_mm)
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
            self.set_progress(100, f"Auto-Werte gesetzt | Score: {best_score:.3f} | Punkte: {points}")
        except Exception as exc:
            for row, eps in zip(self.vector_rows, original_epsilons):
                row.epsilon_var.set(eps)
            self.set_progress(0, "Fehler bei Auto-Werten")
            messagebox.showerror("Fehler bei Auto-Werten", str(exc))

    def export_vector_file(self) -> None:
        if self.vector_image_rgb is None:
            messagebox.showwarning("Kein Zwischenbild", "Bitte zuerst Schritt 1 übernehmen oder ein PNG direkt laden.")
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
            self.set_progress(60, "Datei wird geschrieben...")
            if suffix == ".svg":
                vector.export_svg(out, (w, h), self.detected_contours, pixel_to_mm, fill_closed_shapes=self.fill_closed_shapes_var.get(), use_bezier=self.use_bezier_var.get())
            elif suffix == ".dxf":
                vector.export_dxf(
                    out,
                    (w, h),
                    self.detected_contours,
                    pixel_to_mm,
                    invert_y=True,
                    dxf_version=self.get_selected_dxf_version(),
                )
            else:
                raise ValueError("Output muss .dxf oder .svg sein.")
            self.set_progress(100, f"Export fertig: {out} | DXF {self.get_selected_dxf_version()}")
            messagebox.showinfo(
                "Export fertig",
                f"Datei wurde gespeichert:\n{out}\n\nKompatibilität: {self.dxf_compatibility_var.get()}\nDXF-Format: {self.dxf_version_var.get()}\nDXF-Version intern: {self.get_selected_dxf_version()}"
            )
        except Exception as exc:
            self.set_progress(0, "Fehler beim Export")
            messagebox.showerror("Fehler beim Export", str(exc))


def main() -> None:
    app = WorkflowApp()
    app.mainloop()


if __name__ == "__main__":
    main()
