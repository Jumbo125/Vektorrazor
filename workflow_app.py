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
from PIL import Image, ImageTk, ImageDraw, ImageFilter

import recolor_engine as recolor
import vector_engine as vector
import i18n
from i18n import tr


def resource_path(relative_path: str) -> Path:
    """Pfad funktioniert im Quellordner und in einer PyInstaller-Onefile-EXE."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path


RGB = Tuple[int, int, int]


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
        i18n.load_languages()
        self.title(tr("app.title"))
        self._set_window_icon()
        self.geometry("1480x920")
        self.minsize(1180, 760)
        self.after(10, self._force_maximized)
        self.after(300, self._force_maximized)

        self._i18n_widgets: list[tuple[tk.Widget, str, str]] = []
        self._i18n_notebook_tabs: list[tuple[ttk.Notebook, tk.Widget, str]] = []
        self._step1_scales: list[tk.Scale] = []
        self.style = ttk.Style(self)
        self.dark_mode_var = tk.BooleanVar(value=False)
        self.ui_theme_key_var = tk.StringVar(value="classic")
        self.ui_theme_display_var = tk.StringVar()
        self.ui_complexity_var = tk.StringVar(value="simple")
        self.ui_complexity_display_var = tk.StringVar()

        self.current_step = 0
        self.original_image: Optional[Image.Image] = None
        self.prepared_image: Optional[Image.Image] = None
        self.edited_image: Optional[Image.Image] = None
        self.special_result_image: Optional[Image.Image] = None
        self.current_path: Optional[Path] = None
        self.preview_after_id: Optional[str] = None
        self.step2_live_after_id: Optional[str] = None

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
        self.logo_mask_threshold_var = tk.IntVar(value=10)
        self.logo_mask_blur_var = tk.IntVar(value=50)
        self.logo_mask_clean_var = tk.BooleanVar(value=True)
        self.logo_mask_fg_var = tk.StringVar(value="0,0,0")
        self.logo_mask_bg_var = tk.StringVar(value="255,255,255")

        # Schritt 2 Variablen
        self.vector_image_rgb: Optional[np.ndarray] = None
        self.vector_source_name_var = tk.StringVar(value=tr("status.no_intermediate"))
        self.output_path_var = tk.StringVar()
        self.pixel_to_mm_var = tk.StringVar(value="1.0")
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
        self.selected_contour_text_var = tk.StringVar(value=tr("status.no_path_selected"))
        self.step2_shared_zoom_var = tk.DoubleVar(value=1.0)
        self._syncing_step2_zoom = False
        self.step2_auto_prompt_pending = True
        self.vector_preview_supersample = 2
        self.vector_diagnostics_var = tk.StringVar(value="")
        self._lineart_recommendation_shown = False
        self._step1_recommendation_shown_for: Optional[str] = None
        self._busy_dialog: Optional[tk.Toplevel] = None

        self.status_var = tk.StringVar(value=tr("status.ready"))
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()
        self._bind_live_preview_traces()
        self.add_manual_row()
        self.load_vector_profile("Standard")
        self.show_step(0)

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

    def _bind_live_preview_traces(self) -> None:
        vars_to_watch: list[tk.Variable] = [
            self.vector_mode_var,
            self.centerline_merge_px_var,
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
            self.smooth_strength_var,
            self.global_epsilon_var,
            self.preprocess_vector_var,
            self.preprocess_blur_var,
            self.preprocess_edge_var,
            self.preprocess_noise_var,
            self.internal_scale_var,
            self.smart_smoothing_var,
            self.smart_corner_angle_var,
            self.smart_line_tolerance_var,
            self.smart_curve_strength_var,
            self.global_tolerance_var,
            self.hole_scale_var,
            self.bridge_tabs_var,
            self.bridge_width_mm_var,
            self.bridge_width_percent_var,
            self.bridge_count_var,
            self.cleanup_mode_var,
            self.min_object_area_mm2_var,
            self.min_object_percent_var,
        ]
        for var in vars_to_watch:
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

    def _refresh_combobox_labels(self) -> None:
        if hasattr(self, "language_box"):
            languages = i18n.available_languages()
            self.language_box.configure(values=[name for _code, name in languages])
            current = i18n.current_language()
            for code, name in languages:
                if code == current:
                    self.language_var.set(name)
                    break

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
            "Zwischenbild nur aktualisieren": "step1.update_intermediate",
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
            "Farben erkennen": "step1.detect_colors",
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

        def walk(widget: tk.Widget) -> None:
            try:
                text = str(widget.cget("text"))
                key = text_to_key.get(text)
                if key:
                    self._register_i18n(widget, "text", key)
            except Exception:
                pass
            for child in widget.winfo_children():
                walk(child)

        walk(self)
        self._register_notebook_tab(self.step1_notebook, self.basic_tab, "step1.tab_basic")
        self._register_notebook_tab(self.step1_notebook, self.manual_tab, "step1.tab_manual")
        self._register_notebook_tab(self.step1_notebook, self.logo_tab, "step1.tab_logo")

    def on_language_changed(self, _event: tk.Event | None = None) -> None:
        code = self._language_display_to_code().get(self.language_var.get())
        if not code or not i18n.set_language(code):
            return
        self.refresh_ui_texts()
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
        self.ui_theme_box = ttk.Combobox(header, textvariable=self.ui_theme_display_var, state="readonly", width=12)
        self.ui_theme_box.grid(row=0, column=3, sticky="e", padx=(0, 6))
        self.ui_theme_box.bind("<<ComboboxSelected>>", lambda _event: self.on_ui_theme_display_changed())
        # Einfach/Experte wird bewusst nicht mehr im Header angezeigt.
        # Die Umschaltung sitzt jetzt direkt links oben in den Vektor-Optionen.
        self.ui_complexity_box = ttk.Combobox(header, textvariable=self.ui_complexity_display_var, state="readonly", width=12)
        self.ui_complexity_box.bind("<<ComboboxSelected>>", lambda _event: self.on_ui_complexity_display_changed())
        self.dark_toggle = ttk.Checkbutton(header, text=tr("ui.dark_mode"), variable=self.dark_mode_var, command=self.apply_ui_theme)
        self.dark_toggle.grid(row=0, column=4, sticky="e", padx=(0, 8))
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
        frame = self.step1_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(1, weight=1)
        self.step1_top_toolbar = toolbar
        ttk.Label(toolbar, text="Input-Bild:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(toolbar, textvariable=self.input_path_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(toolbar, text="Bild laden", command=self.choose_input_image).grid(row=0, column=2, padx=(6, 4))
        ttk.Button(toolbar, text="PNG speichern", command=self.export_intermediate_png).grid(row=0, column=3, padx=4)
        auto_btn = ttk.Button(toolbar, text=tr("step1.auto_from_image"), command=self.auto_tune_from_input_image)
        auto_btn.grid(row=0, column=4, padx=(4, 0))
        self._register_i18n(auto_btn, "text", "step1.auto_from_image")

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
        self.step1_original_canvas.canvas.bind("<Enter>", lambda _event: self.update_step1_picker_cursor(), add="+")
        self.step1_original_canvas.canvas.bind("<Leave>", lambda _event: self.step1_original_canvas.canvas.configure(cursor=""), add="+")
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
            variable=variable, showvalue=True, length=200, command=lambda _v: self.on_preprocess_changed(),
            highlightthickness=0, relief="flat", borderwidth=0
        )
        scale.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=1)
        self._step1_scales.append(scale)

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
        self.basic_rows_scroll = recolor.ScrollableFrame(rows_box, height=120)
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
        self.manual_rows_scroll = recolor.ScrollableFrame(rows_box, height=120)
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
        self.step2_top_toolbar = toolbar
        ttk.Label(toolbar, text="Zwischenbild:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(toolbar, textvariable=self.vector_source_name_var, style="Source.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Button(toolbar, text="PNG direkt laden", command=self.load_vector_png_direct).grid(row=0, column=2, padx=(6, 4))
        ttk.Label(toolbar, text="Output:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        ttk.Entry(toolbar, textvariable=self.output_path_var).grid(row=1, column=1, sticky="ew", pady=(4, 0))
        ttk.Button(toolbar, text="Speichern als", command=self.choose_vector_output).grid(row=1, column=2, padx=(6, 4), pady=(4, 0))
        ttk.Label(toolbar, text="Pixel zu mm:").grid(row=1, column=3, sticky="w", padx=(8, 4), pady=(4, 0))
        ttk.Entry(toolbar, textvariable=self.pixel_to_mm_var, width=8).grid(row=1, column=4, sticky="w", pady=(4, 0))

        ttk.Label(toolbar, text="Kompatibilität:").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(6, 0))
        self.compat_box = ttk.Combobox(
            toolbar,
            textvariable=self.dxf_compatibility_display_var,
            values=[self._compat_label(key) for key in DXF_COMPATIBILITY_KEYS],
            state="readonly",
            width=32,
        )
        self.compat_box.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.compat_box.bind("<<ComboboxSelected>>", lambda _event: self.on_dxf_compatibility_display_changed())

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
        self.step2_actions_frame = actions

        self.detect_action_btn = tk.Button(
            actions,
            text="1  Erkennen / Vorschau",
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
        self.detect_action_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.export_action_btn = tk.Button(
            actions,
            text="2  Export DXF / SVG",
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
        self.export_action_btn.grid(row=0, column=1, sticky="w", padx=(0, 12))

        self.auto_action_btn = tk.Button(
            actions,
            text="3  Optional: Auto-Werte testen",
            command=self.auto_optimize_vector_settings,
            bg="#4b5563",
            fg="white",
            activebackground="#374151",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=14,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.auto_action_btn.grid(row=0, column=2, sticky="w", padx=(0, 8))

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
        settings.rowconfigure(2, weight=1)
        workflow_bar = ttk.LabelFrame(settings, text="Workflow", padding=(8, 6, 8, 6))
        workflow_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        workflow_bar.columnconfigure(1, weight=1)
        self.step2_workflow_bar = workflow_bar
        ttk.Label(workflow_bar, text="Zwischenbild:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(workflow_bar, textvariable=self.vector_source_name_var, style="Source.TLabel").grid(row=0, column=1, sticky="w")
        load_img_btn = ttk.Button(workflow_bar, text=tr("step1.load_image"), command=self.load_vector_png_direct)
        load_img_btn.grid(row=0, column=2, padx=(6, 0))
        self._register_i18n(load_img_btn, "text", "step1.load_image")
        load_png_btn = ttk.Button(workflow_bar, text=tr("step2.load_png"), command=self.load_vector_png_direct)
        load_png_btn.grid(row=0, column=3, padx=(6, 0))
        self._register_i18n(load_png_btn, "text", "step2.load_png")
        ttk.Label(workflow_bar, text="Output:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        ttk.Entry(workflow_bar, textvariable=self.output_path_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(workflow_bar, text="Speichern als", command=self.choose_vector_output).grid(row=1, column=3, padx=(6, 0), pady=(4, 0))
        ttk.Label(workflow_bar, text="Pixel zu mm:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(workflow_bar, textvariable=self.pixel_to_mm_var, width=8).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(workflow_bar, text="Kompatibilität:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.compat_box_side = ttk.Combobox(
            workflow_bar,
            textvariable=self.dxf_compatibility_display_var,
            values=[self._compat_label(key) for key in DXF_COMPATIBILITY_KEYS],
            state="readonly",
            width=30,
        )
        self.compat_box_side.grid(row=3, column=1, sticky="w", pady=(6, 0))
        self.compat_box_side.bind("<<ComboboxSelected>>", lambda _event: self.on_dxf_compatibility_display_changed())
        ttk.Label(workflow_bar, text="DXF-Format:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.version_box_side = ttk.Combobox(
            workflow_bar,
            textvariable=self.dxf_version_var,
            values=list(DXF_VERSION_CHOICES.values()),
            state="readonly",
            width=42,
        )
        self.version_box_side.grid(row=4, column=1, columnspan=3, sticky="w", pady=(6, 0))
        self.version_box_side.bind("<<ComboboxSelected>>", lambda _event: self.on_dxf_version_changed())

        colors_bar = ttk.LabelFrame(settings, text="Farben / Layer", padding=(8, 6, 8, 6))
        colors_bar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        colors_bar.columnconfigure(4, weight=1)
        colors_bar.columnconfigure(5, weight=1)
        self.step2_colors_bar = colors_bar
        ttk.Button(colors_bar, text="Farben / Layer bearbeiten", command=self.open_vector_colors_modal).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(colors_bar, text="Profil:").grid(row=0, column=1, sticky="w", padx=(8, 4))
        self.profile_box = ttk.Combobox(colors_bar, textvariable=self.profile_var, values=list(vector.PROFILE_ROWS.keys()), state="readonly", width=18)
        self.profile_box.grid(row=0, column=2, sticky="w")
        self.profile_box.bind("<<ComboboxSelected>>", lambda _event: self.on_profile_selected())
        self.vector_color_count_var = tk.StringVar(value="")
        ttk.Label(colors_bar, textvariable=self.vector_color_count_var, foreground="#555").grid(row=0, column=4, sticky="w", padx=(12, 0))
        ttk.Label(
            colors_bar,
            textvariable=self.vector_diagnostics_var,
            foreground="#555",
            wraplength=820,
            justify="left",
        ).grid(row=2, column=0, columnspan=6, sticky="ew", pady=(6, 0))

        # Wichtigste Vorschau-Steuerung sichtbar und direkt erreichbar.
        self.live_preview_check = ttk.Checkbutton(
            colors_bar,
            text=tr("step2.live_preview"),
            variable=self.live_preview_var,
            style="Live.TCheckbutton",
        )
        self.live_preview_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._register_i18n(self.live_preview_check, "text", "step2.live_preview")
        self.step2_quick_preview_btn = tk.Button(
            colors_bar,
            text=tr("step2.manual_refresh"),
            command=self.detect_and_preview_vector,
            relief="raised",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.step2_quick_preview_btn.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(8, 0))
        self._register_i18n(self.step2_quick_preview_btn, "text", "step2.manual_refresh")
        # Export/Bild laden bewusst nicht in diesem Frame: passt nicht zum Layer-Workflow.
        self._build_vector_colors_modal()

        self.step2_opts_scroll = recolor.ScrollableFrame(settings, height=120, horizontal=True)
        self.step2_opts_scroll.grid(row=2, column=0, sticky="nsew")
        self.step2_opts_scroll.inner.columnconfigure(0, weight=1)
        self.vector_opts_head = ttk.Frame(self.step2_opts_scroll.inner)
        self.vector_opts_head.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.vector_opts_head.columnconfigure(2, weight=1)
        self.auto_expert_btn = ttk.Button(self.vector_opts_head, text=tr("step2.auto_expert_from_image"), command=self.auto_tune_expert_values_from_image)
        self.auto_expert_btn.grid(row=0, column=0, sticky="w")
        self._register_i18n(self.auto_expert_btn, "text", "step2.auto_expert_from_image")
        opts_outer = ttk.LabelFrame(self.step2_opts_scroll.inner, text="Vektor-Optionen", padding=8)
        opts_outer.grid(row=1, column=0, sticky="nsew")
        self.vector_options_container = opts_outer
        opts_outer.columnconfigure(0, weight=1)

        self.complexity_toggle_frame = tk.Frame(opts_outer, bd=0, highlightthickness=0)
        self.complexity_toggle_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Label(
            self.complexity_toggle_frame,
            text="Ansicht:",
            font=("Segoe UI", 9, "bold"),
            bd=0,
        ).pack(side="left", padx=(0, 8))
        self.simple_mode_btn = tk.Button(
            self.complexity_toggle_frame,
            text=tr("ui.mode.simple"),
            command=lambda: self.set_ui_complexity_mode("simple"),
            relief="raised",
            bd=1,
            padx=12,
            pady=4,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.simple_mode_btn.pack(side="left", padx=(0, 6))
        self.expert_mode_btn = tk.Button(
            self.complexity_toggle_frame,
            text=tr("ui.mode.expert"),
            command=lambda: self.set_ui_complexity_mode("expert"),
            relief="raised",
            bd=1,
            padx=12,
            pady=4,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.expert_mode_btn.pack(side="left", padx=(0, 10))
        self.complexity_hint_label = tk.Label(
            self.complexity_toggle_frame,
            text="Einfach zeigt nur Kernwerte, Experte alle Vektor-Optionen.",
            bd=0,
        )
        self.complexity_hint_label.pack(side="left", padx=(4, 0))

        opts = ttk.Frame(opts_outer)
        opts.grid(row=1, column=0, sticky="nsew")
        self.vector_options_frame = opts
        opts.columnconfigure(1, weight=1)
        opts.columnconfigure(3, weight=1)
        ttk.Label(opts, text="Vektorart").grid(row=0, column=0, sticky="w")
        self.vector_mode_box = ttk.Combobox(opts, textvariable=self.vector_mode_display_var, values=[self._mode_label(key) for key in VECTOR_MODE_KEYS], state="readonly", width=20)
        self.vector_mode_box.grid(row=0, column=1, sticky="w", padx=(4, 12))
        self.vector_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_vector_mode_display_changed())
        ttk.Label(opts, text="Linien zusammenführen px").grid(row=0, column=2, sticky="w")
        ttk.Entry(opts, textvariable=self.centerline_merge_px_var, width=8).grid(row=0, column=3, sticky="w", padx=(4, 0))
        ttk.Checkbutton(opts, text="Nur geschlossene Pfade", variable=self.closed_paths_only_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="SVG-Flächen füllen (Export)", variable=self.fill_closed_shapes_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Checkbutton(opts, text="Zusammenhängende Pfade gruppieren (SVG)", variable=self.group_connected_paths_var).grid(row=1, column=2, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="Export-Layer pro Farbe", variable=self.force_color_layers_var).grid(row=2, column=2, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Checkbutton(opts, text="Objekte in Layer erstellen (DXF)", variable=self.object_layers_dxf_var).grid(row=3, column=2, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Checkbutton(opts, text="Bezier für SVG", variable=self.use_bezier_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Checkbutton(
            opts,
            text="Doppelte Linien entfernen (CAD)",
            variable=self.unique_cad_lines_var,
            command=self.render_vector_preview
        ).grid(row=21, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(opts, text="Punktreduktion / Epsilon px").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Scale(opts, from_=0.0, to=5.0, variable=self.global_epsilon_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.global_epsilon_var, value, 3)).grid(row=4, column=1, sticky="ew", padx=(4, 4), pady=(8, 0))
        ttk.Spinbox(opts, from_=0.0, to=5.0, increment=0.001, textvariable=self.global_epsilon_var, width=8, format="%.3f").grid(row=4, column=2, sticky="w", pady=(8, 0))
        ttk.Button(opts, text="Epsilon auf alle Farben anwenden", command=self.apply_global_epsilon_to_rows).grid(row=5, column=3, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 0))
        self.high_detail_btn = ttk.Button(opts, text=tr("step2.high_detail"), command=self.apply_high_detail_mode)
        self.high_detail_btn.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._register_i18n(self.high_detail_btn, "text", "step2.high_detail")
        ttk.Label(opts, text="Doppellinien-Toleranz px").grid(row=21, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(opts, textvariable=self.duplicate_line_tolerance_var, width=8).grid(row=21, column=3, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Label(opts, text="Vorschau-Modus").grid(row=17, column=0, sticky="w", pady=(8, 0))
        self.preview_mode_box = ttk.Combobox(opts, textvariable=self.preview_mode_display_var, values=[self._preview_label(key) for key in PREVIEW_MODE_KEYS], state="readonly", width=18)
        self.preview_mode_box.grid(row=17, column=1, sticky="w", padx=(4, 12), pady=(8, 0))
        self.preview_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_preview_mode_display_changed())
        ttk.Checkbutton(opts, text="Lose Ankerpunkte entfernen", variable=self.remove_loose_points_var).grid(row=20, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opts, text="Rundungen glätten", variable=self.smooth_contours_var).grid(row=20, column=2, sticky="w", pady=(8, 0))
        ttk.Scale(opts, from_=0, to=5, variable=self.smooth_strength_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.smooth_strength_var, value, 3)).grid(row=20, column=3, sticky="ew", padx=(4, 4), pady=(8, 0))
        ttk.Spinbox(opts, from_=0, to=5, increment=0.001, textvariable=self.smooth_strength_var, width=8, format="%.3f").grid(row=20, column=4, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Checkbutton(opts, text="Vorverarbeitung aktiv", variable=self.preprocess_vector_var).grid(row=8, column=0, sticky="w", pady=(8, 0))
        ttk.Button(
            opts,
            text="?",
            width=3,
            command=lambda: self.show_i18n_info("msg.preprocess_info_title", "msg.preprocess_info_body"),
        ).grid(row=8, column=1, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Label(opts, text="Weichzeichnen / Blur").grid(row=9, column=0, sticky="w", pady=(2, 0))
        ttk.Scale(opts, from_=0.0, to=3.0, variable=self.preprocess_blur_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.preprocess_blur_var, value, 3)).grid(row=9, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0.0, to=3.0, increment=0.001, textvariable=self.preprocess_blur_var, width=8, format="%.3f").grid(row=9, column=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Kanten beruhigen").grid(row=10, column=0, sticky="w", pady=(2, 0))
        ttk.Scale(opts, from_=0, to=5, variable=self.preprocess_edge_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.preprocess_edge_var, value, 3)).grid(row=10, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0, to=5, increment=0.001, textvariable=self.preprocess_edge_var, width=8, format="%.3f").grid(row=10, column=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Mindeststörung px").grid(row=11, column=0, sticky="w", pady=(2, 0))
        ttk.Scale(opts, from_=0, to=50, variable=self.preprocess_noise_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.preprocess_noise_var, value, 3)).grid(row=11, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0, to=50, increment=0.001, textvariable=self.preprocess_noise_var, width=8, format="%.3f").grid(row=11, column=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Interne Skalierung").grid(row=12, column=0, sticky="w", pady=(2, 0))
        self.internal_scale_box = ttk.Combobox(opts, textvariable=self.internal_scale_display_var, values=[self._internal_scale_label(key) for key in INTERNAL_SCALE_KEYS], state="readonly", width=10)
        self.internal_scale_box.grid(row=12, column=1, sticky="w", padx=(4, 12), pady=(2, 0))
        self.internal_scale_box.bind("<<ComboboxSelected>>", lambda _event: self.on_internal_scale_display_changed())
        # Manuelle Vorschau-Aktualisierung erfolgt jetzt im Farben/Layer-Frame per Refresh-Button.
        ttk.Checkbutton(opts, text="Smart CAD Smoothing", variable=self.smart_smoothing_var).grid(row=13, column=0, sticky="w", pady=(8, 0))
        ttk.Button(
            opts,
            text="?",
            width=3,
            command=lambda: self.show_i18n_info("msg.smart_smoothing_info_title", "msg.smart_smoothing_info_body"),
        ).grid(row=13, column=1, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Label(opts, text="Ecken schützen °").grid(row=14, column=0, sticky="w", pady=(2, 0))
        ttk.Scale(opts, from_=10, to=120, variable=self.smart_corner_angle_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.smart_corner_angle_var, value, 3)).grid(row=14, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=10, to=120, increment=0.001, textvariable=self.smart_corner_angle_var, width=8, format="%.3f").grid(row=14, column=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Gerade Linien Toleranz px").grid(row=15, column=0, sticky="w", pady=(2, 0))
        ttk.Scale(opts, from_=0.2, to=5.0, variable=self.smart_line_tolerance_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.smart_line_tolerance_var, value, 3)).grid(row=15, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0.2, to=5.0, increment=0.001, textvariable=self.smart_line_tolerance_var, width=8, format="%.3f").grid(row=15, column=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Kurven-Glättung").grid(row=16, column=0, sticky="w", pady=(2, 0))
        ttk.Scale(opts, from_=0, to=5, variable=self.smart_curve_strength_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.smart_curve_strength_var, value, 3)).grid(row=16, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0, to=5, increment=0.001, textvariable=self.smart_curve_strength_var, width=8, format="%.3f").grid(row=16, column=2, sticky="w", pady=(2, 0))
        hole_scale_label = ttk.Label(opts, text=tr("step2.hole_scale"))
        hole_scale_label.grid(row=5, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(hole_scale_label, "text", "step2.hole_scale")
        ttk.Scale(
            opts,
            from_=0.5,
            to=1.5,
            variable=self.hole_scale_var,
            orient="horizontal",
            command=lambda value: self._set_numeric_var(self.hole_scale_var, value, 3),
        ).grid(row=5, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0.5, to=1.5, increment=0.001, textvariable=self.hole_scale_var, width=8, format="%.3f").grid(row=5, column=2, sticky="w", pady=(2, 0))
        bridge_check = ttk.Checkbutton(opts, text=tr("step2.bridge_tabs"), variable=self.bridge_tabs_var)
        bridge_check.grid(row=22, column=0, sticky="w", pady=(10, 0))
        self._register_i18n(bridge_check, "text", "step2.bridge_tabs")
        ttk.Button(
            opts,
            text="?",
            width=3,
            command=lambda: self.show_i18n_info("msg.bridge_tabs_info_title", "msg.bridge_tabs_info_body"),
        ).grid(row=22, column=1, sticky="w", padx=(4, 0), pady=(10, 0))
        bridge_mm_label = ttk.Label(opts, text=tr("step2.bridge_width_mm"))
        bridge_mm_label.grid(row=23, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(bridge_mm_label, "text", "step2.bridge_width_mm")
        ttk.Scale(opts, from_=0.0, to=10.0, variable=self.bridge_width_mm_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.bridge_width_mm_var, value, 3)).grid(row=23, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0.0, to=10.0, increment=0.001, textvariable=self.bridge_width_mm_var, width=8, format="%.3f").grid(row=23, column=2, sticky="w", pady=(2, 0))
        bridge_percent_label = ttk.Label(opts, text=tr("step2.bridge_width_percent"))
        bridge_percent_label.grid(row=24, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(bridge_percent_label, "text", "step2.bridge_width_percent")
        ttk.Scale(opts, from_=0.0, to=5.0, variable=self.bridge_width_percent_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.bridge_width_percent_var, value, 3)).grid(row=24, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0.0, to=5.0, increment=0.001, textvariable=self.bridge_width_percent_var, width=8, format="%.3f").grid(row=24, column=2, sticky="w", pady=(2, 0))
        bridge_count_label = ttk.Label(opts, text=tr("step2.bridge_count"))
        bridge_count_label.grid(row=25, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(bridge_count_label, "text", "step2.bridge_count")
        ttk.Scale(opts, from_=1.0, to=8.0, variable=self.bridge_count_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.bridge_count_var, value, 3)).grid(row=25, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=1.0, to=8.0, increment=1.000, textvariable=self.bridge_count_var, width=8, format="%.3f").grid(row=25, column=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Kleine Objekte löschen").grid(row=18, column=0, sticky="w", pady=(8, 0))
        self.cleanup_mode_box = ttk.Combobox(opts, textvariable=self.cleanup_mode_display_var, values=[self._cleanup_label(key) for key in CLEANUP_MODE_KEYS], state="readonly", width=12)
        self.cleanup_mode_box.grid(row=18, column=1, sticky="w", padx=(4, 12), pady=(8, 0))
        self.cleanup_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_cleanup_mode_display_changed())
        ttk.Label(opts, text="mm²").grid(row=18, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(opts, textvariable=self.min_object_area_mm2_var, width=8).grid(row=18, column=3, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Label(opts, text="% Bildfläche").grid(row=19, column=2, sticky="w", pady=(2, 0))
        ttk.Entry(opts, textvariable=self.min_object_percent_var, width=8).grid(row=19, column=3, sticky="w", padx=(4, 0), pady=(2, 0))

        preview = ttk.Frame(panes)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)

        select_tools = ttk.LabelFrame(preview, text="Pfad-Auswahl", padding=(6, 4, 6, 4))
        select_tools.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        select_tools.columnconfigure(4, weight=1)
        self.selection_mode_check = ttk.Checkbutton(
            select_tools,
            text="Auswahl-Modus",
            variable=self.vector_selection_mode_var,
            command=self.update_vector_selection_mode_ui,
        )
        self.selection_mode_check.grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Button(select_tools, text="Ausgewählte Pfade entfernen", command=self.remove_selected_contour).grid(row=0, column=1, sticky="w", padx=(0, 6))
        ttk.Button(select_tools, text="Auswahl aufheben", command=self.clear_selected_contour).grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(select_tools, text="Zoom").grid(row=0, column=3, sticky="w", padx=(8, 4))
        self.step2_zoom_scale = ttk.Scale(
            select_tools,
            from_=0.25,
            to=8.0,
            variable=self.step2_shared_zoom_var,
            orient="horizontal",
            command=self.on_step2_shared_zoom_changed,
        )
        self.step2_zoom_scale.grid(row=0, column=4, sticky="ew", padx=(0, 8))
        ttk.Label(select_tools, textvariable=self.selected_contour_text_var, foreground="#555").grid(row=0, column=5, sticky="w")
        ttk.Label(
            select_tools,
            text="Auswahl-Modus EIN: Klick = Pfad wählen, STRG+Klick = hinzufügen/umschalten, ALT+Klick = direkt entfernen. Auswahl-Modus AUS: Klick/Ziehen verschiebt die Vorschau; nur STRG+Klick wählt temporär.",
            foreground="#777",
            wraplength=840,
            justify="left",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(3, 0))

        preview_doc = ttk.LabelFrame(preview, text="Dokument / Vorschau", padding=(6, 4, 6, 6))
        preview_doc.grid(row=1, column=0, sticky="nsew")
        preview_doc.columnconfigure(0, weight=1)
        preview_doc.rowconfigure(0, weight=1)
        preview_panes = ttk.Panedwindow(preview_doc, orient=tk.HORIZONTAL)
        preview_panes.grid(row=0, column=0, sticky="nsew")
        self.step2_original_canvas = recolor.ZoomImageCanvas(
            preview_panes, "Zwischen-PNG", zoom_callback=self.on_step2_canvas_zoom_changed
        )
        self.step2_vector_canvas = recolor.ZoomImageCanvas(
            preview_panes,
            "Vektor-Vorschau",
            zoom_callback=self.on_step2_canvas_zoom_changed,
            overlay_draw_callback=self.draw_vector_canvas_overlay,
        )
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
        panes.add(preview, weight=5)

    def _build_vector_colors_modal(self) -> None:
        self.vector_colors_window = tk.Toplevel(self)
        self.vector_colors_window.title(tr("step2.edit_colors"))
        self.vector_colors_window.geometry("980x520")
        self.vector_colors_window.minsize(760, 360)
        self.vector_colors_window.withdraw()
        self.vector_colors_window.protocol("WM_DELETE_WINDOW", self.close_vector_colors_modal)
        self.vector_colors_window.columnconfigure(0, weight=1)
        self.vector_colors_window.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.vector_colors_window, padding=(8, 8, 8, 4))
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(5, weight=1)
        add_button = ttk.Button(controls, text="+ Farbe", command=self.add_empty_vector_row)
        add_button.grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._register_i18n(add_button, "text", "step2.add_color")
        profile_label = ttk.Label(controls, text="Profil:")
        profile_label.grid(row=0, column=1, sticky="w", padx=(12, 4))
        self._register_i18n(profile_label, "text", "step2.profile")
        ttk.Combobox(controls, textvariable=self.profile_var, values=list(vector.PROFILE_ROWS.keys()), state="readonly", width=18).grid(row=0, column=2, sticky="w")
        apply_button = ttk.Button(controls, text="Anwenden", command=lambda: self.load_vector_profile(self.profile_var.get()))
        apply_button.grid(row=0, column=3, sticky="w", padx=(4, 0))
        self._register_i18n(apply_button, "text", "step2.apply")
        detect_button = ttk.Button(controls, text="Farben aus Bild erkennen", command=self.autofill_vector_rows_from_image)
        detect_button.grid(row=0, column=4, sticky="w", padx=(12, 0))
        self._register_i18n(detect_button, "text", "step2.detect_colors_from_image")
        close_button = ttk.Button(controls, text=tr("button.close"), command=self.close_vector_colors_modal)
        close_button.grid(row=0, column=6, sticky="e")
        self._register_i18n(close_button, "text", "button.close")

        table_box = ttk.LabelFrame(self.vector_colors_window, text="Dynamische Farbtabelle", padding=4)
        table_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self._register_i18n(table_box, "text", "step2.dynamic_table")
        table_box.columnconfigure(0, weight=1)
        table_box.rowconfigure(1, weight=1)
        header = ttk.Frame(table_box)
        header.grid(row=0, column=0, sticky="ew")
        for col, text in enumerate(["Name", "RGB", "Tol.", "Layer", "Export", "Min.", "Epsilon", ""]):
            ttk.Label(header, text=text, width=[14, 13, 28, 14, 7, 7, 7, 3][col]).grid(row=0, column=col, padx=2, sticky="w")
        self.vector_rows_scroll = recolor.ScrollableFrame(table_box, height=120)
        self.vector_rows_scroll.grid(row=1, column=0, sticky="nsew")
        self.vector_table = ttk.Frame(self.vector_rows_scroll.inner)
        self.vector_table.grid(row=0, column=0, sticky="ew")

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
        finally:
            self._syncing_step2_zoom = False

    def on_step2_canvas_zoom_changed(self, zoom: float) -> None:
        if self._syncing_step2_zoom:
            return
        self._syncing_step2_zoom = True
        try:
            self.step2_shared_zoom_var.set(float(zoom))
            if hasattr(self, "step2_zoom_scale"):
                self.step2_zoom_scale.update_idletasks()
            # Beide Vorschauen synchron halten, wenn per Mausrad in einem Canvas gezoomt wird.
            if hasattr(self, "step2_original_canvas"):
                self.step2_original_canvas.set_zoom(float(zoom))
            if hasattr(self, "step2_vector_canvas"):
                self.step2_vector_canvas.set_zoom(float(zoom))
        finally:
            self._syncing_step2_zoom = False

    def on_ui_theme_display_changed(self) -> None:
        selected = self.ui_theme_display_var.get()
        for key in UI_THEME_KEYS:
            if selected == self._ui_theme_label(key):
                self.ui_theme_key_var.set(key)
                break
        self.apply_ui_theme()

    def on_ui_complexity_display_changed(self) -> None:
        selected = self.ui_complexity_display_var.get()
        for key in UI_COMPLEXITY_KEYS:
            if selected == self._ui_complexity_label(key):
                self.ui_complexity_var.set(key)
                break
        self.apply_ui_complexity_mode()

    def set_ui_complexity_mode(self, key: str) -> None:
        if key not in UI_COMPLEXITY_KEYS:
            return
        self.ui_complexity_var.set(key)
        try:
            self.ui_complexity_display_var.set(self._ui_complexity_label(key))
        except Exception:
            pass
        self.apply_ui_complexity_mode()

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
            if simple:
                if row in (0, 1, 4, 9, 14, 17):
                    child.grid()
                else:
                    child.grid_remove()
            else:
                child.grid()
        if hasattr(self, "step2_actions_frame"):
            if simple:
                self.step2_actions_frame.grid_remove()
            else:
                self.step2_actions_frame.grid()
        self._refresh_complexity_buttons_style()

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
            show_top_toolbar = True
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
        self.step1_next_action_btn.configure(bg=step_bg, activebackground=step_bg, fg="white", activeforeground="white", relief=btn_relief, bd=btn_bd, padx=btn_padx, pady=btn_pady, font=compact_font)
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
        if hasattr(self, "export_action_btn"):
            self.export_action_btn.configure(activeforeground="white")
        if hasattr(self, "auto_action_btn"):
            self.auto_action_btn.configure(activeforeground="white")
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
            else:
                self.detect_and_preview_vector()

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

    def set_progress(self, value: float, status: Optional[str] = None) -> None:
        self.progress_var.set(max(0.0, min(100.0, value)))
        if status is not None:
            self.status_var.set(status)
        self.update_idletasks()

    def show_busy_dialog(self, title: str = "Bitte warten", message: str = "Bild wird analysiert...") -> None:
        """Blockiert kurz die Oberfläche, damit man während Auto-Analyse nicht versehentlich klickt."""
        try:
            self.close_busy_dialog()
        except Exception:
            pass
        try:
            dialog = tk.Toplevel(self)
            self._busy_dialog = dialog
            dialog.title(title)
            dialog.transient(self)
            dialog.resizable(False, False)
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)
            frame = ttk.Frame(dialog, padding=(18, 14, 18, 14))
            frame.grid(row=0, column=0, sticky="nsew")
            ttk.Label(frame, text=message, justify="left", wraplength=420).grid(row=0, column=0, sticky="w")
            bar = ttk.Progressbar(frame, mode="indeterminate", length=360)
            bar.grid(row=1, column=0, sticky="ew", pady=(12, 0))
            bar.start(12)
            self.update_idletasks()
            x = self.winfo_rootx() + max(80, (self.winfo_width() - 430) // 2)
            y = self.winfo_rooty() + max(80, (self.winfo_height() - 130) // 2)
            dialog.geometry(f"430x120+{x}+{y}")
            dialog.grab_set()
            try:
                self.configure(cursor="watch")
            except Exception:
                pass
            dialog.update_idletasks()
            dialog.update()
        except Exception:
            self._busy_dialog = None
            self.status_var.set(message)
            self.update_idletasks()

    def close_busy_dialog(self) -> None:
        dialog = getattr(self, "_busy_dialog", None)
        self._busy_dialog = None
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
        channel_spread = (np.max(rgb, axis=2) - np.min(rgb, axis=2))[alpha]
        p5 = float(np.percentile(gvals, 5))
        p95 = float(np.percentile(gvals, 95))
        dyn = p95 - p5
        near_bw = float((channel_spread <= 14).mean())
        near_black = float((gvals <= 45).mean())
        near_white = float((gvals >= 225).mean())
        sat_mean = float(sat[alpha].mean())
        sat_p95 = float(np.percentile(sat[alpha], 95))
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
            "edge_density": edge_density,
            "mask_blur": float(best_blur),
            "mask_threshold": float(best_threshold),
            "mask_coverage": float(best_coverage),
            "mask_target_coverage": float(target_coverage),
            "mask_score": float(best_score),
            "mask_edge": float(best_foreground_edge),
        }

    def recommend_step1_mode_from_image(self, force: bool = False) -> None:
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

        mask_like = (
            stats["near_bw"] >= 0.72
            and stats["sat_mean"] <= 0.070
            and 18.0 <= stats["dynamic"] <= 155.0
            and stats["near_black"] < 0.10
            and 1.0 <= stats["mask_coverage"] <= 65.0
        )
        bw_lineart_like = (
            stats["near_bw"] >= 0.88
            and stats["dynamic"] >= 130.0
            and stats["near_black"] >= 0.01
            and stats["near_white"] >= 0.30
        )
        color_like = stats["sat_mean"] >= 0.08 or stats["sat_p95"] >= 0.18

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
                self.create_logo_mask_preview()
                self.status_var.set(tr("status.step1_recommend_mask_applied", threshold=threshold, blur=blur))
            else:
                self.status_var.set(tr("status.step1_recommend_mask_skipped"))
            return

        if bw_lineart_like:
            try:
                self.step1_notebook.select(self.basic_tab)
            except Exception:
                pass
            threshold = 30 if stats["dynamic"] > 180 else 40
            msg = tr("msg.step1_recommend_bw", threshold=threshold)
            if messagebox.askyesno(tr("msg.step1_recommend_title"), msg, default=messagebox.YES, icon=messagebox.QUESTION):
                self.basic_threshold_var.set(threshold)
                self.basic_min_area_var.set(1)
                self.basic_max_colors_var.set(2)
                self.basic_alpha_var.set(10)
                self.detect_basic_colors(show_busy=True)
                self.status_var.set(tr("status.step1_recommend_bw_applied"))
            else:
                self.status_var.set(tr("status.step1_recommend_bw_skipped"))
            return

        if color_like:
            try:
                self.step1_notebook.select(self.basic_tab)
            except Exception:
                pass
            suggested_colors = 8 if stats["sat_p95"] < 0.30 else 12
            threshold = 14 if stats["edge_density"] > 0.08 else 18
            min_area = 5 if stats["edge_density"] > 0.08 else 10
            msg = tr("msg.step1_recommend_color", threshold=threshold, suggested_colors=suggested_colors, min_area=min_area)
            if messagebox.askyesno(tr("msg.step1_recommend_title"), msg, default=messagebox.YES, icon=messagebox.QUESTION):
                self.basic_threshold_var.set(threshold)
                self.basic_min_area_var.set(min_area)
                self.basic_max_colors_var.set(suggested_colors)
                self.basic_alpha_var.set(10)
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
        path = filedialog.askopenfilename(
            title="Bild laden",
            filetypes=[("Bilddateien", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"), ("Alle Dateien", "*.*")],
        )
        if path:
            self.input_path_var.set(path)
            self.load_input_image(path)

    def load_input_image(self, path: str) -> None:
        self.show_busy_dialog(tr("msg.busy_load_image_title"), tr("msg.busy_load_image_body"))
        try:
            try:
                img = Image.open(path).convert("RGBA")
            except Exception as exc:
                messagebox.showerror(tr("msg.load_error"), str(exc))
                return
            self.current_path = Path(path)
            self.original_image = img
            self.step2_auto_prompt_pending = True
            self.prepared_image = None
            self.edited_image = self.get_prepared_image(force=True)
            self.special_result_image = None
            self.step1_original_canvas.set_image(self.original_image, reset_view=True)
            self.step1_edited_canvas.set_image(self.edited_image, reset_view=True)
            if not self.output_path_var.get():
                self.output_path_var.set(str(self.current_path.with_suffix(".dxf")))
            self.status_var.set(tr("status.image_loaded", name=self.current_path.name, width=img.width, height=img.height))
            if self.step1_notebook.index(self.step1_notebook.select()) == 0:
                self.detect_basic_colors(show_busy=False)
            else:
                self.update_step1_preview()
        finally:
            self.close_busy_dialog()

        # Nach der ersten schnellen Erkennung noch eine Workflow-Empfehlung anbieten.
        # after_idle sorgt dafür, dass das Bild schon sichtbar ist, bevor das Modal erscheint.
        self.after_idle(lambda: self.recommend_step1_mode_from_image(force=False))

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

    def auto_tune_from_input_image(self) -> None:
        if self.original_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_load"))
            return
        arr = np.array(self.original_image.convert("RGB"), dtype=np.float32)
        gray = arr.mean(axis=2)
        dyn = float(np.percentile(gray, 95) - np.percentile(gray, 5))
        grad_x = np.abs(np.diff(gray, axis=1))
        grad_y = np.abs(np.diff(gray, axis=0))
        edge_density = float(((grad_x > 18).mean() + (grad_y > 18).mean()) * 0.5)
        near_black = float((gray < 70).mean())
        near_white = float((gray > 185).mean())
        binary_like = near_black + near_white
        text_logo_mode = binary_like > 0.72 and dyn > 110 and edge_density > 0.04
        organic_score = edge_density + max(0.0, (80.0 - dyn) / 200.0)

        self.preprocess_vector_var.set(True)
        if text_logo_mode:
            # Text/Logo: Details priorisieren, fast keine Rundungsverluste.
            self.preprocess_blur_var.set(0.25)
            self.preprocess_edge_var.set(0)
            self.preprocess_noise_var.set(1)
            self.internal_scale_var.set("3")
            self.smooth_contours_var.set(False)
            self.smooth_strength_var.set("0.000")
            self.smart_smoothing_var.set(True)
            self.smart_corner_angle_var.set("32.000")
            self.smart_line_tolerance_var.set("0.550")
            self.smart_curve_strength_var.set("1.000")
            self.global_epsilon_var.set("0.350")
            self.status_var.set(tr("status.auto_from_image_textlogo"))
        elif organic_score >= 0.20:
            self.preprocess_blur_var.set(1.2)
            self.preprocess_edge_var.set(2)
            self.preprocess_noise_var.set(2)
            self.internal_scale_var.set("3")
            self.smooth_contours_var.set(True)
            self.smooth_strength_var.set("2.500")
            self.smart_smoothing_var.set(True)
            self.smart_corner_angle_var.set("42.000")
            self.smart_line_tolerance_var.set("0.900")
            self.smart_curve_strength_var.set("2.500")
            self.global_epsilon_var.set("0.900")
        else:
            self.preprocess_blur_var.set(0.7)
            self.preprocess_edge_var.set(1)
            self.preprocess_noise_var.set(3)
            self.internal_scale_var.set("2")
            self.smooth_contours_var.set(True)
            self.smooth_strength_var.set("1.600")
            self.smart_smoothing_var.set(True)
            self.smart_corner_angle_var.set("50.000")
            self.smart_line_tolerance_var.set("1.100")
            self.smart_curve_strength_var.set("1.600")
            self.global_epsilon_var.set("1.200")
        self.internal_scale_display_var.set(self._internal_scale_label(self.internal_scale_var.get()))
        try:
            self.apply_global_epsilon_to_rows()
        except Exception:
            pass
        if not text_logo_mode:
            self.set_progress(0, tr("status.auto_from_image_done"))
        self.schedule_step1_preview()

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

    def on_step1_mode_changed(self) -> None:
        self.update_step1_picker_cursor()
        self.update_step1_preview()

    def update_step1_picker_cursor(self) -> None:
        try:
            cursor = "crosshair" if self.step1_notebook.index(self.step1_notebook.select()) == 1 else ""
            self.step1_original_canvas.canvas.configure(cursor=cursor)
        except Exception:
            pass

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
        try:
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
                messagebox.showerror(tr("msg.error"), tr("msg.detect_colors_error", error=exc))
                return
            self.clear_basic_rows()
            for i, item in enumerate(detected):
                self.basic_rows.append(BasicWorkflowRow(self, self.basic_rows_container, i, item))
            self.status_var.set(tr("status.detected_color_regions", count=len(detected)))
            self.update_step1_preview()
        finally:
            if show_busy:
                self.close_busy_dialog()

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
        if self.step1_notebook.index(self.step1_notebook.select()) != 1:
            self.status_var.set(tr("status.pixel_color_at", x=x, y=y, rgb=_rgb_to_text(rgb)))
            return
        if not self.manual_rows:
            self.add_manual_row()
        index = max(0, min(self.selected_manual_row_var.get(), len(self.manual_rows) - 1))
        self.manual_rows[index].set_source_rgb(rgb)
        self.status_var.set(tr("status.color_copied_to_row", rgb=_rgb_to_text(rgb), row=index + 1))

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
            )
            self.edited_image = self.special_result_image.copy()
            self.step1_edited_canvas.set_image(self.edited_image, reset_view=False)
            self.status_var.set(tr("status.logo_mask_created"))
        except Exception as exc:
            messagebox.showerror(tr("msg.error"), tr("msg.logo_mask_error", error=exc))

    def clear_logo_mask(self) -> None:
        self.special_result_image = None
        self.update_step1_preview()

    def export_intermediate_png(self) -> None:
        self.update_step1_preview()
        if self.edited_image is None:
            messagebox.showwarning(tr("msg.no_image_title"), tr("msg.no_image_edit"))
            return
        initial = "workflow_zwischenbild.png"
        if self.current_path:
            initial = f"{self.current_path.stem}_workflow_zwischenbild.png"
        path = filedialog.asksaveasfilename(title=tr("msg.export_intermediate_title"), defaultextension=".png", initialfile=initial, filetypes=[("PNG", "*.png")])
        if not path:
            return
        try:
            self.edited_image.save(path, format="PNG")
            self.status_var.set(tr("status.intermediate_saved", path=path))
        except Exception as exc:
            messagebox.showerror(tr("msg.export_error"), str(exc))

    def use_edited_for_vector(self, show_message: bool = False) -> bool:
        self.update_step1_preview()
        if self.edited_image is None:
            messagebox.showwarning(tr("msg.no_intermediate_title"), tr("msg.no_intermediate_load_first"))
            return False
        rgb_image = _flatten_rgba_to_rgb(self.edited_image)
        self.vector_image_rgb = np.array(rgb_image)
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
                eps = "0.060"
            elif is_black:
                layer = f"CUT_BLACK_{rgb_suffix}"
                export = True
                tol = "190"
                min_area = "0"
                eps = "0.060"
            else:
                bright_background = all(v >= 235 for v in rgb) and float(percent) >= 20.0
                export = not bright_background
                layer = f"CUT_{safe}_{rgb_suffix}" if export else f"IGNORE_{safe}_{rgb_suffix}"
                tol = "22" if export else "8"
                min_area = "0" if export else "2"
                eps = "0.060" if export else "0.350"
            self.add_vector_row(name, _rgb_to_text(rgb), tol, layer, export, min_area, eps)
        self._step1_transferred_color_rules = True
        self.sync_global_tolerance_from_rows()
        export_count = sum(1 for row in self.vector_rows if row.export_var.get())
        self.vector_diagnostics_var.set(
            f"{source_label}: {len(self.vector_rows)} Farbregeln erzeugt, davon {export_count} für Export aktiv."
        )
        if self.is_current_vector_image_bw_like() or len(self.vector_rows) <= 2:
            self._apply_bw_detail_preset()
        return True

    def transfer_step1_target_colors_to_vector_rows(self) -> bool:
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
        self.detect_and_preview_vector()

    def on_profile_selected(self) -> None:
        self.load_vector_profile(self.profile_var.get())
        if self.vector_image_rgb is None:
            return
        if self.live_preview_var.get():
            self._schedule_live_preview_if_enabled()
        else:
            self.detect_and_preview_vector()

    def _schedule_live_preview_if_enabled(self, *_args: object) -> None:
        if not self.live_preview_var.get():
            return
        if self.vector_image_rgb is None:
            return
        if self.step2_live_after_id:
            try:
                self.after_cancel(self.step2_live_after_id)
            except Exception:
                pass
        self.step2_live_after_id = self.after(280, lambda: self.detect_and_preview_vector(live=True))

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
        detected = recolor.RecolorApp.detect_colors_by_threshold(
            image,
            threshold=18,
            min_area=1,
            max_colors=96,
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
        path = filedialog.askopenfilename(title="PNG für Vektorisierung laden", filetypes=[("PNG", "*.png"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            img = Image.open(path).convert("RGB")
            self.vector_image_rgb = np.array(img)
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
        try:
            self.set_progress(5, tr("progress.read_vector_rules"))
            self.selected_contour_index = None
            self.selected_contour_indices.clear()
            self.selected_contour_text_var.set(tr("status.no_path_selected"))
            rules = self.get_vector_rules()
            self.last_rules = rules
            pixel_to_mm = self.get_pixel_to_mm()
            centerline_mode = self.vector_mode_var.get() == "centerline"
            self.set_progress(10, tr("progress.detecting_contours"))
            contours = vector.detect_all_contours(
                self.vector_image_rgb,
                rules,
                closed_paths_only=self.closed_paths_only_var.get() and not centerline_mode,
                remove_loose_points=self.remove_loose_points_var.get(),
                smooth_iterations=0,
                centerline_mode=centerline_mode,
                centerline_merge_px=self.get_centerline_merge_px(),
                preprocess_enabled=self.preprocess_vector_var.get(),
                preprocess_blur=self.get_preprocess_blur(),
                preprocess_edge_smoothing=self.get_preprocess_edge_smoothing(),
                preprocess_noise_area=self.get_preprocess_noise_area(),
                internal_scale=self.get_internal_scale(),
                progress_callback=lambda fraction: self.set_progress(10 + fraction * 65, tr("progress.detecting_contours"))
            )
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
            self.detected_contours = self.apply_hole_scaling(self.detected_contours)
            self.detected_contours = self.apply_bridge_tabs_if_enabled(self.detected_contours)
            self.render_vector_preview()
            exported = sum(1 for c in self.detected_contours if c.rule.export)
            points = sum(len(c.points) for c in self.detected_contours if c.rule.export)
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
        except Exception as exc:
            self.set_progress(0, tr("progress.detect_error"))
            if live:
                self.status_var.set(f"{tr('msg.recognize_error_title')}: {exc}")
            else:
                messagebox.showerror(tr("msg.recognize_error_title"), str(exc))

    def render_vector_preview(self) -> None:
        if self.vector_image_rgb is None:
            return

        mode = self.preview_mode_var.get()
        reset = self.step2_vector_canvas.image is None
        if mode == "mask":
            preview = self.build_filled_mask_preview_image()
            self.draw_selected_contour_overlay(preview)
            self.step2_vector_canvas.set_image(preview, reset_view=reset)
            return
        if mode == "object":
            preview = self.build_object_check_preview_image()
            self.draw_selected_contour_overlay(preview)
            self.step2_vector_canvas.set_image(preview, reset_view=reset)
            return
        if mode == "cut_risk":
            preview = self.build_cut_risk_preview_image()
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

        visible_index = 0
        # Objektcheck Variante C:
        # Normale Objekte werden bunt gefüllt. Löcher werden NICHT weiß gefüllt,
        # sondern nur als Umrandung markiert. Dadurch können weiße Innenflächen
        # keine bereits vorhandenen bunten Objektflächen mehr übermalen.
        for item in self.detected_contours:
            if not item.rule.export or len(item.points) < 2:
                continue
            is_hole = bool(getattr(item, "is_hole", False))
            pts = [(float(x) * aa, float(y) * aa) for x, y in item.points]
            if is_hole:
                hole_outline = (80, 80, 80)
                hole_highlight = (255, 255, 255)
                if item.closed and len(pts) >= 3:
                    draw.line(pts + [pts[0]], fill=hole_highlight, width=max(2, int(round(3 * aa))), joint="curve")
                    draw.line(pts + [pts[0]], fill=hole_outline, width=max(1, aa), joint="curve")
                else:
                    draw.line(pts, fill=hole_outline, width=max(1, int(round(2 * aa))), joint="curve")
                continue

            color = palette[visible_index % len(palette)]
            outline = (0, 0, 0)
            visible_index += 1
            if item.closed and len(pts) >= 3:
                draw.polygon(pts, fill=color)
                draw.line(pts + [pts[0]], fill=outline, width=max(1, aa), joint="curve")
            else:
                draw.line(pts, fill=color, width=max(1, int(round(4 * aa))), joint="curve")

        if aa > 1:
            return preview_hr.resize((w, h), Image.Resampling.LANCZOS)
        return preview_hr

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
        draw = ImageDraw.Draw(preview_hr)

        exported = [
            item for item in self.detected_contours
            if getattr(item.rule, "export", True) and len(getattr(item, "points", []) or []) >= 2
        ]
        if not exported:
            return preview_hr.resize((w, h), Image.Resampling.LANCZOS) if aa > 1 else preview_hr

        areas = [max(0.0, float(getattr(item, "area", 0.0) or 0.0)) for item in exported]
        max_area = max(areas) if areas else 0.0
        image_area = max(1.0, float(w * h))
        small_island_limit = max(
            12.0,
            min(image_area * 0.015, max_area * 0.18 if max_area > 0 else image_area * 0.015),
        )

        for item in exported:
            pts = [(float(x) * aa, float(y) * aa) for x, y in item.points]
            if len(pts) < 2:
                continue

            closed = bool(getattr(item, "closed", False))
            is_hole = bool(getattr(item, "is_hole", False))
            area = max(0.0, float(getattr(item, "area", 0.0) or 0.0))
            is_small_island = closed and not is_hole and area <= small_island_limit

            if is_hole:
                fill = (255, 218, 218)
                stroke = (220, 38, 38)
                width = max(2, int(round(3 * aa)))
            elif is_small_island:
                fill = (255, 237, 213)
                stroke = (234, 88, 12)
                width = max(2, int(round(3 * aa)))
            else:
                fill = (226, 232, 240)
                stroke = (30, 41, 59)
                width = max(1, int(round(2 * aa)))

            if closed and len(pts) >= 3:
                draw.polygon(pts, fill=fill)
                draw.line(pts + [pts[0]], fill=stroke, width=width, joint="curve")
            else:
                draw.line(pts, fill=stroke, width=width, joint="curve")

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
                    remove_loose_points=self.remove_loose_points_var.get(),
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
