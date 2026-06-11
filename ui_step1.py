# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""UI-Aufbau für Workflow-Schritt 1.

Diese Datei enthält ausschließlich den strukturellen Aufbau der Oberfläche für
Schritt 1. Hier werden also Frames, Buttons, Notebook-Tabs, Skalen,
Eingabefelder und Statusbereiche erzeugt, nicht aber die eigentliche
Bildverarbeitungslogik.

Ziel der Auslagerung:
- workflow_app.py bleibt übersichtlicher
- die UI-Struktur für Schritt 1 ist an einer Stelle gebündelt
- spätere Layout-Anpassungen lassen sich einfacher pflegen

Inhaltlich deckt Schritt 1 ab:
- Vorbereitungswerkzeuge für das Eingangsbild
- manuelle Farbumsetzung
- Radierer- und Bereinigungswerkzeuge
- Logo-Masken-Modus
- Foto-Scan-Modus
- KI-Skalierung
- Abschlussleiste zum Speichern und Weitergeben an Schritt 2
"""

from __future__ import annotations

from typing import Optional
import tkinter as tk
from tkinter import ttk

import recolor_engine as recolor
from i18n import tr


ACTION_GREEN = "#15803d"
ACTION_GREEN_ACTIVE = "#166534"
ACTION_YELLOW = "#ca8a04"
ACTION_YELLOW_ACTIVE = "#a16207"
ACTION_BLUE = "#2563eb"
ACTION_BLUE_ACTIVE = "#1d4ed8"
ACTION_GRAY = "#6b7280"
ACTION_GRAY_ACTIVE = "#4b5563"
STEP1_SCALE_MIN_LENGTH = 210
STEP1_SCALE_MAX_LENGTH = 380
STEP1_NOISE_SCALE_MAX_LENGTH = 300


def _bind_responsive_scale_length(
    parent: tk.Widget,
    scale: tk.Widget,
    *,
    min_length: int = STEP1_SCALE_MIN_LENGTH,
    max_length: int = STEP1_SCALE_MAX_LENGTH,
    reserve_px: int = 170,
) -> None:
    """Scale-Laenge an die verfuegbare Breite anpassen, aber nicht endlos strecken."""
    def _resize(_event: tk.Event | None = None) -> None:
        try:
            available = int(parent.winfo_width()) - int(reserve_px)
            length = max(int(min_length), min(int(max_length), available))
            scale.configure(length=length)
        except Exception:
            pass

    try:
        parent.bind("<Configure>", _resize, add="+")
        parent.after(40, _resize)
    except Exception:
        pass


def _create_action_button(
    parent: tk.Widget,
    text: str,
    command,
    *,
    bg: str,
    activebackground: str,
    padx: int = 14,
    width: int | None = None,
):
    options = {
        "text": text,
        "command": command,
        "bg": bg,
        "fg": "white",
        "activebackground": activebackground,
        "activeforeground": "white",
        "relief": "raised",
        "bd": 1,
        "padx": padx,
        "pady": 6,
        "font": ("Segoe UI", 9, "bold"),
        "cursor": "hand2",
    }
    if width is not None:
        options["width"] = width
    return tk.Button(parent, **options)


def _build_step1(self) -> None:
        frame = self.step1_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(1, weight=1)
        self.step1_top_toolbar = toolbar
        ttk.Label(toolbar, text="Input-Bild:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(toolbar, textvariable=self.input_path_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(toolbar, text="Bild laden", command=self.choose_input_image).grid(row=0, column=2, padx=(6, 4))
        reset_workflow_btn = ttk.Button(toolbar, text=tr("step1.reset_workflow"), command=self.reset_workflow_for_new_image)
        reset_workflow_btn.grid(row=0, column=3, padx=(6, 0))
        self._register_i18n(reset_workflow_btn, "text", "step1.reset_workflow")

        step1_actions = ttk.LabelFrame(frame, text="Workflow / Abschluss Schritt 1", padding=(8, 6, 8, 6))
        step1_actions.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        step1_actions.columnconfigure(3, weight=1)
        self._register_i18n(step1_actions, "text", "step1.actions")
        step1_actions.grid_remove()

        self.step1_next_action_btn = tk.Button(
            step1_actions,
            text="Weiter zur Vektorisierung →",
            command=self.next_step,
            bg=ACTION_GREEN,
            fg="white",
            activebackground=ACTION_GREEN_ACTIVE,
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=16,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.step1_next_action_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))

        update_only_btn = ttk.Button(
            step1_actions,
            text=tr("step1.use_preview_as_base"),
            command=lambda: self.use_current_preview_as_new_base(show_message=True),
        )
        update_only_btn.grid(row=0, column=1, sticky="w", padx=(0, 10))
        self._register_i18n(update_only_btn, "text", "step1.use_preview_as_base")

        update_hint = ttk.Label(
            step1_actions,
            text=tr("step1.update_hint"),
            foreground="#555",
        )
        update_hint.grid(row=0, column=3, sticky="w")
        self._register_i18n(update_hint, "text", "step1.update_hint")

        panes = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        panes.grid(row=2, column=0, sticky="nsew")

        preview = ttk.Frame(panes)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)
        rotation_bar = ttk.Frame(preview)
        rotation_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        rotate_left_btn = ttk.Button(rotation_bar, text=tr("step1.rotate_left"), command=lambda: self.rotate_step1_image(-90))
        rotate_left_btn.pack(side="left", padx=(0, 4))
        self._register_i18n(rotate_left_btn, "text", "step1.rotate_left")
        rotate_right_btn = ttk.Button(rotation_bar, text=tr("step1.rotate_right"), command=lambda: self.rotate_step1_image(90))
        rotate_right_btn.pack(side="left")
        self._register_i18n(rotate_right_btn, "text", "step1.rotate_right")

        preview_panes = ttk.Panedwindow(preview, orient=tk.HORIZONTAL)
        preview_panes.grid(row=1, column=0, sticky="nsew")
        self.step1_original_canvas = recolor.ZoomImageCanvas(
            preview_panes,
            "Originalbild",
            self.on_pick_color,
            view_callback=self.on_step1_canvas_view_changed,
        )
        self.step1_edited_canvas = recolor.ZoomImageCanvas(
            preview_panes,
            "Bearbeitet / technische Zwischenstufe",
            view_callback=self.on_step1_canvas_view_changed,
        )
        ttk.Checkbutton(
            self.step1_original_canvas.header_frame,
            text="Gemeinsames Verschieben",
            variable=self.step1_sync_view_var,
            command=self.sync_step1_canvas_views_now,
        ).pack(side="left", padx=(18, 0))
        # Rechte Vorschau: Im normalen Modus bleibt Ziehen = Verschieben.
        # Im Radierer-Modus werden die Standard-Bindings ersetzt und an die App delegiert,
        # damit Pinseln nicht gleichzeitig die Ansicht verschiebt.
        self.step1_edited_canvas.canvas.bind("<ButtonPress-1>", self.on_step1_edited_press)
        self.step1_edited_canvas.canvas.bind("<B1-Motion>", self.on_step1_edited_motion)
        self.step1_edited_canvas.canvas.bind("<ButtonRelease-1>", self.on_step1_edited_release)
        self.step1_edited_canvas.canvas.bind("<Enter>", lambda _event: self.update_step1_picker_cursor(), add="+")
        self.step1_edited_canvas.canvas.bind("<Leave>", lambda _event: self.step1_edited_canvas.canvas.configure(cursor=""), add="+")
        self.step1_original_canvas.canvas.bind("<Enter>", lambda _event: self.update_step1_picker_cursor(), add="+")
        self.step1_original_canvas.canvas.bind("<Leave>", lambda _event: self.step1_original_canvas.canvas.configure(cursor=""), add="+")
        preview_panes.add(self.step1_original_canvas, weight=1)
        preview_panes.add(self.step1_edited_canvas, weight=1)

        settings_shell = ttk.Frame(panes)
        settings_shell.configure(width=500)
        settings_shell.columnconfigure(0, weight=1)
        settings_shell.rowconfigure(0, weight=1)
        # Der komplette Einstellungsbereich bekommt horizontale UND vertikale Scrollbars.
        # Dadurch bleibt Schritt 1 auch bei kleinen Fenstern und Darkmode bedienbar.
        # Keine feste Hoehe erzwingen.
        self.step1_settings_scroll = recolor.ScrollableFrame(settings_shell, height=1, horizontal=True)
        self.step1_settings_scroll.grid(row=0, column=0, sticky="nsew")
        settings = self.step1_settings_scroll.inner
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(1, weight=1)

        # Tk/ttk-Notebook kann Tabs nicht sauber umbrechen. Deshalb bleibt das
        # Notebook intern ohne sichtbare Tabs und die Methode wird per Dropdown gewählt.
        self.step1_tab_key_var = tk.StringVar(value="prep")
        self.step1_tab_display_var = tk.StringVar(value=tr("step1.mode.prep"))
        self.step1_tab_hint_var = tk.StringVar(value=tr("step1.mode_hint.prep"))
        self.step1_mode_keys = ["prep", "basic", "manual", "eraser", "logo", "photo_scan", "ai_upscale"]
        self.step1_mode_display_to_key = {tr(f"step1.mode.{key}"): key for key in self.step1_mode_keys}

        self.step1_mode_selector = ttk.LabelFrame(settings, text=tr("step1.mode_selector"), padding=(8, 6, 8, 6))
        self.step1_mode_selector.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.step1_mode_selector.columnconfigure(0, weight=0)
        self.step1_mode_selector.columnconfigure(1, weight=0)
        self._register_i18n(self.step1_mode_selector, "text", "step1.mode_selector")

        self.step1_methods_intro_label = ttk.Label(
            self.step1_mode_selector,
            text=tr("step1.methods_intro"),
            foreground="#555",
            wraplength=340,
            justify="left",
        )
        self.step1_methods_intro_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self._register_i18n(self.step1_methods_intro_label, "text", "step1.methods_intro")

        def _resize_mode_texts(event: tk.Event) -> None:
            width = min(420, max(260, int(event.width) - 28))
            try:
                self.step1_methods_intro_label.configure(wraplength=width)
                self.step1_mode_hint_label.configure(wraplength=width)
            except Exception:
                pass

        self.step1_mode_selector.bind("<Configure>", _resize_mode_texts, add="+")

        mode_label = ttk.Label(self.step1_mode_selector, text=tr("step1.mode_choose"))
        mode_label.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._register_i18n(mode_label, "text", "step1.mode_choose")
        self.step1_mode_box = ttk.Combobox(
            self.step1_mode_selector,
            textvariable=self.step1_tab_display_var,
            values=[tr(f"step1.mode.{key}") for key in self.step1_mode_keys],
            state="readonly",
            width=22,
        )
        self.step1_mode_box.grid(row=1, column=1, sticky="w")
        self.step1_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_step1_mode_display_changed())
        self.step1_mode_hint_label = ttk.Label(
            self.step1_mode_selector,
            textvariable=self.step1_tab_hint_var,
            foreground="#555",
            wraplength=340,
            justify="left",
        )
        self.step1_mode_hint_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        try:
            hidden_style = ttk.Style(self)
            hidden_style.layout("Step1Hidden.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
            hidden_style.layout("Step1Hidden.TNotebook.Tab", [])
            hidden_style.configure("Step1Hidden.TNotebook", borderwidth=0, tabmargins=(0, 0, 0, 0), padding=0)
            hidden_style.configure("Step1Hidden.TNotebook.Tab", padding=0)
        except Exception:
            pass
        self.step1_notebook = ttk.Notebook(settings, style="Step1Hidden.TNotebook")
        self.step1_notebook.grid(row=1, column=0, sticky="nsew")
        self.step1_notebook.bind("<<NotebookTabChanged>>", lambda _e: self.on_step1_mode_changed())

        self.prep_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.basic_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.manual_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.eraser_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.logo_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.photo_scan_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.ai_upscale_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.step1_notebook.add(self.prep_tab, text=tr("step1.tab_preprocess"))
        self.step1_notebook.add(self.basic_tab, text=tr("step1.tab_basic"))
        self.step1_notebook.add(self.manual_tab, text=tr("step1.tab_manual"))
        self.step1_notebook.add(self.eraser_tab, text=tr("step1.tab_eraser"))
        self.step1_notebook.add(self.logo_tab, text=tr("step1.tab_logo"))
        self.step1_notebook.add(self.photo_scan_tab, text=tr("step1.tab_photo_scan"))
        self.step1_notebook.add(self.ai_upscale_tab, text=tr("step1.tab_ai_upscale"))
        self.step1_tabs_by_key = {
            "prep": self.prep_tab,
            "basic": self.basic_tab,
            "manual": self.manual_tab,
            "eraser": self.eraser_tab,
            "logo": self.logo_tab,
            "photo_scan": self.photo_scan_tab,
            "ai_upscale": self.ai_upscale_tab,
        }
        self.step1_tab_keys_by_widget = {widget: key for key, widget in self.step1_tabs_by_key.items()}

        _build_step1_preprocess_tab(self)
        self._build_step1_basic_tab()
        self._build_step1_manual_tab()
        self._build_step1_eraser_tab()
        self._build_step1_logo_tab()
        self._build_step1_photo_scan_tab()
        self._build_step1_ai_upscale_tab()
        self.select_step1_tab("prep")

        step1_tools = ttk.LabelFrame(preview, text=tr("step1.tools"), padding=(8, 6, 8, 6))
        step1_tools.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for _col in range(4):
            step1_tools.columnconfigure(_col, weight=1, uniform="step1_tools_actions")
        self._register_i18n(step1_tools, "text", "step1.tools")
        auto_btn = _create_action_button(step1_tools, tr("step1.auto_from_image"), self.auto_tune_from_input_image, bg=ACTION_GRAY, activebackground=ACTION_GRAY_ACTIVE)
        auto_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._register_i18n(auto_btn, "text", "step1.auto_from_image")
        save_png_btn = _create_action_button(step1_tools, tr("step1.save_png"), self.export_intermediate_png, bg=ACTION_GRAY, activebackground=ACTION_GRAY_ACTIVE)
        save_png_btn.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._register_i18n(save_png_btn, "text", "step1.save_png")
        update_intermediate_btn = _create_action_button(
            step1_tools,
            tr("step1.use_preview_as_base"),
            lambda: self.use_current_preview_as_new_base(show_message=True),
            bg=ACTION_YELLOW,
            activebackground=ACTION_YELLOW_ACTIVE,
        )
        update_intermediate_btn.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self._register_i18n(update_intermediate_btn, "text", "step1.use_preview_as_base")
        self.step1_next_action_btn = _create_action_button(
            step1_tools,
            tr("nav.next_vectorize"),
            self.next_step,
            bg=ACTION_GREEN,
            activebackground=ACTION_GREEN_ACTIVE,
            padx=16,
        )
        self.step1_next_action_btn.grid(row=0, column=3, sticky="ew")
        self._register_i18n(self.step1_next_action_btn, "text", "nav.next_vectorize")

        self.problem_hint_frame = ttk.LabelFrame(settings, text=tr("step1.problem_hint_title"), padding=(8, 6, 8, 6))
        self.problem_hint_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.problem_hint_frame.columnconfigure(0, weight=1)
        self._register_i18n(self.problem_hint_frame, "text", "step1.problem_hint_title")
        self.problem_hint_label = ttk.Label(
            self.problem_hint_frame,
            text=tr("step1.problem_hint_body"),
            wraplength=520,
            foreground="#6b4e00",
        )
        self.problem_hint_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self._register_i18n(self.problem_hint_label, "text", "step1.problem_hint_body")
        manual_open_btn = ttk.Button(
            self.problem_hint_frame,
            text=tr("step1.open_manual_colors"),
            command=self.open_manual_colors_from_hint,
        )
        manual_open_btn.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self._register_i18n(manual_open_btn, "text", "step1.open_manual_colors")
        high_tol_btn = ttk.Button(
            self.problem_hint_frame,
            text=tr("step1.apply_high_tolerance"),
            command=self.apply_high_tolerance_manual_colors,
        )
        high_tol_btn.grid(row=1, column=1, sticky="w")
        self._register_i18n(high_tol_btn, "text", "step1.apply_high_tolerance")
        self.problem_hint_frame.grid_remove()

        panes.add(settings_shell, weight=1)
        panes.add(preview, weight=5)

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
        label_widget = ttk.Label(parent, text=tr(i18n_key) if i18n_key else label, width=14)
        label_widget.grid(row=row, column=0, sticky="w", pady=1)
        if i18n_key:
            self._register_i18n(label_widget, "text", i18n_key)
        tooltip_by_label = {
            "Helligkeit": "tooltip.step1.brightness",
            "Kontrast": "tooltip.step1.contrast",
            "Schwarzpunkt": "tooltip.step1.black_point",
            "Weißpunkt": "tooltip.step1.white_point",
            "Gamma": "tooltip.step1.gamma",
        }
        if tooltip_key:
            self._add_tooltip(label_widget, tooltip_key)
        elif label in tooltip_by_label:
            self._add_tooltip(label_widget, tooltip_by_label[label])
        scale = tk.Scale(
            parent, from_=from_, to=to, resolution=resolution, orient="horizontal",
            variable=variable, showvalue=True, length=STEP1_SCALE_MIN_LENGTH, command=lambda _v: self.on_preprocess_changed(),
            highlightthickness=0, relief="flat", borderwidth=0
        )
        scale.grid(row=row, column=1, sticky="w", padx=(4, 0), pady=1)
        _bind_responsive_scale_length(parent, scale)
        self._step1_scales.append(scale)

def _build_step1_preprocess_tab(self) -> None:
        tab = self.prep_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        prep = ttk.LabelFrame(tab, text=tr("step1.prep"), padding=8)
        prep.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        prep.columnconfigure(1, weight=1)
        self._register_i18n(prep, "text", "step1.prep")
        self._add_scale(prep, 0, "Helligkeit", self.prep_brightness_var, -100, 100, 1, i18n_key="step1.brightness")
        self._add_scale(prep, 1, "Kontrast", self.prep_contrast_var, -100, 100, 1, i18n_key="step1.contrast")
        self._add_scale(prep, 2, "Schwarzpunkt", self.prep_black_var, 0, 254, 1, i18n_key="step1.black_point")
        self._add_scale(prep, 3, "Weißpunkt", self.prep_white_var, 1, 255, 1, i18n_key="step1.white_point")
        self._add_scale(prep, 4, "Gamma", self.prep_gamma_var, 0.30, 3.00, 0.05, i18n_key="step1.gamma")
        self._add_scale(
            prep,
            5,
            "Rotation °",
            self.prep_rotation_var,
            -180,
            180,
            1,
            i18n_key="step1.rotation",
            tooltip_key="tooltip.step1.rotation",
        )
        reset_btn = ttk.Button(prep, text=tr("step1.reset"), command=self.reset_preprocessing)
        reset_btn.grid(row=6, column=0, sticky="w", pady=(6, 0))
        self._register_i18n(reset_btn, "text", "step1.reset")

        apply_btn = _create_action_button(
            prep,
            tr("step1.apply_preprocess"),
            self.schedule_step1_preview,
            bg=ACTION_GREEN,
            activebackground=ACTION_GREEN_ACTIVE,
        )
        apply_btn.grid(row=6, column=1, sticky="w", pady=(6, 0))
        self._register_i18n(apply_btn, "text", "step1.apply_preprocess")

        hint = ttk.Label(
            tab,
            text=tr("step1.preprocess_hint"),
            foreground="#555",
            wraplength=520,
            justify="left",
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._register_i18n(hint, "text", "step1.preprocess_hint")


def _build_step1_basic_tab(self) -> None:
        tab = self.basic_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        detect = ttk.LabelFrame(tab, text=tr("step1.detect"), padding=8)
        detect.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        detect.columnconfigure(0, weight=0)
        detect.columnconfigure(1, weight=0)
        detect.columnconfigure(2, weight=1)
        self._register_i18n(detect, "text", "step1.detect")

        threshold_label = ttk.Label(detect, text=tr("step1.threshold"))
        threshold_label.grid(row=0, column=0, sticky="w")
        self._register_i18n(threshold_label, "text", "step1.threshold")
        self._add_tooltip(threshold_label, "tooltip.step1.threshold")
        ttk.Spinbox(detect, from_=0, to=255, textvariable=self.basic_threshold_var, width=7).grid(row=0, column=1, sticky="w", padx=(8, 0))

        min_area_label = ttk.Label(detect, text=tr("step1.min_area"))
        min_area_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._register_i18n(min_area_label, "text", "step1.min_area")
        self._add_tooltip(min_area_label, "tooltip.step1.min_area")
        ttk.Spinbox(detect, from_=1, to=999999, textvariable=self.basic_min_area_var, width=8).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(4, 0))

        max_colors_label = ttk.Label(detect, text=tr("step1.max_colors"))
        max_colors_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._register_i18n(max_colors_label, "text", "step1.max_colors")
        self._add_tooltip(max_colors_label, "tooltip.step1.max_colors")
        ttk.Spinbox(detect, from_=1, to=64, textvariable=self.basic_max_colors_var, width=7).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(4, 0))

        alpha_label = ttk.Label(detect, text=tr("step1.alpha_from"))
        alpha_label.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self._register_i18n(alpha_label, "text", "step1.alpha_from")
        self._add_tooltip(alpha_label, "tooltip.step1.alpha_from")
        ttk.Spinbox(detect, from_=0, to=255, textvariable=self.basic_alpha_var, width=8).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(4, 0))

        noise_label = ttk.Label(detect, text=tr("step1.noise_suppression"))
        noise_label.grid(row=4, column=0, sticky="w", pady=(6, 0))
        self._register_i18n(noise_label, "text", "step1.noise_suppression")
        self._add_tooltip(noise_label, "tooltip.step1.noise_suppression")
        noise_scale = ttk.Scale(detect, from_=0, to=100, variable=self.basic_noise_var, orient="horizontal", length=STEP1_SCALE_MIN_LENGTH)
        noise_scale.grid(row=4, column=1, sticky="w", padx=(8, 8), pady=(6, 0))
        _bind_responsive_scale_length(
            detect,
            noise_scale,
            min_length=180,
            max_length=STEP1_NOISE_SCALE_MAX_LENGTH,
            reserve_px=210,
        )
        ttk.Spinbox(detect, from_=0, to=100, textvariable=self.basic_noise_var, width=8).grid(row=4, column=2, sticky="w", pady=(6, 0))

        fill_check = ttk.Checkbutton(detect, text=tr("step1.fill_solid_areas"), variable=self.basic_fill_solid_var, command=self.schedule_step1_preview)
        fill_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._register_i18n(fill_check, "text", "step1.fill_solid_areas")

        button_row = ttk.Frame(detect)
        button_row.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        update_colors_btn = _create_action_button(button_row, tr("step1.update_colors"), self.detect_basic_colors, bg=ACTION_YELLOW, activebackground=ACTION_YELLOW_ACTIVE)
        update_colors_btn.pack(side="left", padx=(0, 8))
        self._register_i18n(update_colors_btn, "text", "step1.update_colors")
        reassign_btn = _create_action_button(button_row, tr("step1.reassign"), self.reassign_basic_targets, bg=ACTION_GREEN, activebackground=ACTION_GREEN_ACTIVE)
        reassign_btn.pack(side="left")
        self._register_i18n(reassign_btn, "text", "step1.reassign")

        hint = ttk.Label(tab, text=tr("step1.basic_hint"), foreground="#555", wraplength=430, justify="left")
        hint.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self._register_i18n(hint, "text", "step1.basic_hint")

        rows_box = ttk.LabelFrame(tab, text=tr("step1.detected_ranges"), padding=4)
        rows_box.grid(row=2, column=0, sticky="nsew")
        self._register_i18n(rows_box, "text", "step1.detected_ranges")
        rows_box.columnconfigure(0, weight=1)
        rows_box.rowconfigure(1, weight=1)
        header = ttk.Frame(rows_box)
        header.grid(row=0, column=0, sticky="ew")
        rows_header = ttk.Label(header, text=tr("step1.rows_header"), foreground="#555")
        rows_header.pack(anchor="w")
        self._register_i18n(rows_header, "text", "step1.rows_header")
        self.basic_rows_scroll = recolor.ScrollableFrame(rows_box, height=1)
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
        self.manual_rows_scroll = recolor.ScrollableFrame(rows_box, height=1)
        self.manual_rows_scroll.grid(row=0, column=0, sticky="nsew")
        self.manual_rows_container = self.manual_rows_scroll.inner
        self.manual_rows_container.columnconfigure(0, weight=1)

def _build_step1_eraser_tab(self) -> None:
        tab = self.eraser_tab
        tab.columnconfigure(1, weight=1)

        hint = ttk.Label(
            tab,
            text=tr("step1.eraser_hint"),
            foreground="#555",
            wraplength=560,
            justify="left",
        )
        hint.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        self._register_i18n(hint, "text", "step1.eraser_hint")

        size_label = ttk.Label(tab, text=tr("step1.eraser_size"))
        size_label.grid(row=1, column=0, sticky="w", pady=3)
        self._register_i18n(size_label, "text", "step1.eraser_size")
        self._add_tooltip(size_label, "tooltip.step1.eraser_size")
        size_scale = ttk.Scale(
            tab,
            from_=1,
            to=200,
            variable=self.eraser_size_var,
            orient="horizontal",
            length=STEP1_SCALE_MIN_LENGTH,
            command=lambda value: self._set_numeric_var(self.eraser_size_var, value, 0),
        )
        size_scale.grid(row=1, column=1, sticky="w", padx=(8, 8), pady=3)
        _bind_responsive_scale_length(tab, size_scale, min_length=180, max_length=STEP1_NOISE_SCALE_MAX_LENGTH, reserve_px=240)
        ttk.Spinbox(tab, from_=1, to=999, textvariable=self.eraser_size_var, width=8).grid(row=1, column=2, sticky="w", pady=3)

        shape_label = ttk.Label(tab, text=tr("step1.eraser_shape"))
        shape_label.grid(row=2, column=0, sticky="w", pady=3)
        self._register_i18n(shape_label, "text", "step1.eraser_shape")
        shape_box = ttk.Frame(tab)
        shape_box.grid(row=2, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=3)
        for index, (shape_key, text_key) in enumerate((("round", "step1.eraser_shape_round"), ("square", "step1.eraser_shape_square"))):
            rb = ttk.Radiobutton(
                shape_box,
                text=tr(text_key),
                value=shape_key,
                variable=self.eraser_shape_var,
            )
            rb.grid(row=0, column=index, sticky="w", padx=(0, 16))
            self._register_i18n(rb, "text", text_key)

        color_label = ttk.Label(tab, text=tr("step1.eraser_color"))
        color_label.grid(row=3, column=0, sticky="w", pady=3)
        self._register_i18n(color_label, "text", "step1.eraser_color")
        self._add_tooltip(color_label, "tooltip.step1.eraser_color")
        color_entry = ttk.Entry(tab, textvariable=self.eraser_color_var, width=14)
        color_entry.grid(row=3, column=1, sticky="w", padx=(8, 4), pady=3)
        self.eraser_color_swatch = tk.Label(tab, width=3, relief="solid", bd=1)
        self.eraser_color_swatch.grid(row=3, column=2, sticky="w", padx=(0, 8), pady=3)
        choose_btn = _create_action_button(
            tab,
            tr("button.choose"),
            self.choose_eraser_color,
            bg=ACTION_GREEN,
            activebackground=ACTION_GREEN_ACTIVE,
            padx=8,
        )
        choose_btn.grid(row=3, column=3, sticky="w", pady=3)
        self._register_i18n(choose_btn, "text", "button.choose")

        action_row = ttk.Frame(tab)
        action_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        action_row.columnconfigure(2, weight=1)
        prepare_btn = _create_action_button(
            action_row,
            tr("step1.eraser_take_current"),
            self.prepare_eraser_from_current_preview,
            bg=ACTION_YELLOW,
            activebackground=ACTION_YELLOW_ACTIVE,
        )
        prepare_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._register_i18n(prepare_btn, "text", "step1.eraser_take_current")
        base_btn = _create_action_button(
            action_row,
            tr("step1.use_preview_as_base"),
            lambda: self.use_current_preview_as_new_base(show_message=True),
            bg=ACTION_GRAY,
            activebackground=ACTION_GRAY_ACTIVE,
        )
        base_btn.grid(row=0, column=1, sticky="w")
        self._register_i18n(base_btn, "text", "step1.use_preview_as_base")

        status = ttk.Label(
            tab,
            textvariable=self.eraser_status_var,
            foreground="#555",
            wraplength=560,
            justify="left",
        )
        status.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        self.eraser_color_var.trace_add("write", lambda *_: self.update_eraser_color_swatch())
        self.update_eraser_color_swatch()


def _build_step1_logo_tab(self) -> None:
        tab = self.logo_tab
        tab.columnconfigure(1, weight=1)
        hint = ttk.Label(tab, text=tr("step1.logo_hint"), foreground="#555", wraplength=520, justify="left")
        hint.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._register_i18n(hint, "text", "step1.logo_hint")
        logo_threshold_label = ttk.Label(tab, text=tr("step1.logo_threshold"))
        logo_threshold_label.grid(row=1, column=0, sticky="w", pady=3)
        self._register_i18n(logo_threshold_label, "text", "step1.logo_threshold")
        self._add_tooltip(logo_threshold_label, "tooltip.step1.logo_threshold")
        ttk.Spinbox(tab, from_=1, to=100, textvariable=self.logo_mask_threshold_var, width=8).grid(row=1, column=1, sticky="w", pady=3)
        threshold_hint = ttk.Label(tab, text=tr("step1.logo_threshold_hint"), foreground="#555")
        threshold_hint.grid(row=1, column=2, sticky="w", padx=(8, 0))
        self._register_i18n(threshold_hint, "text", "step1.logo_threshold_hint")
        logo_radius_label = ttk.Label(tab, text=tr("step1.logo_radius"))
        logo_radius_label.grid(row=2, column=0, sticky="w", pady=3)
        self._register_i18n(logo_radius_label, "text", "step1.logo_radius")
        self._add_tooltip(logo_radius_label, "tooltip.step1.logo_radius")
        ttk.Spinbox(tab, from_=5, to=151, increment=2, textvariable=self.logo_mask_blur_var, width=8).grid(row=2, column=1, sticky="w", pady=3)
        radius_hint = ttk.Label(tab, text=tr("step1.logo_radius_hint"), foreground="#555")
        radius_hint.grid(row=2, column=2, sticky="w", padx=(8, 0))
        self._register_i18n(radius_hint, "text", "step1.logo_radius_hint")
        logo_rgb_label = ttk.Label(tab, text=tr("step1.logo_rgb"))
        logo_rgb_label.grid(row=3, column=0, sticky="w", pady=3)
        self._register_i18n(logo_rgb_label, "text", "step1.logo_rgb")
        ttk.Entry(tab, textvariable=self.logo_mask_fg_var, width=14).grid(row=3, column=1, sticky="w", pady=3)
        bg_rgb_label = ttk.Label(tab, text=tr("step1.logo_bg_rgb"))
        bg_rgb_label.grid(row=4, column=0, sticky="w", pady=3)
        self._register_i18n(bg_rgb_label, "text", "step1.logo_bg_rgb")
        ttk.Entry(tab, textvariable=self.logo_mask_bg_var, width=14).grid(row=4, column=1, sticky="w", pady=3)
        clean_check = ttk.Checkbutton(tab, text=tr("step1.logo_cleanup"), variable=self.logo_mask_clean_var)
        clean_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._register_i18n(clean_check, "text", "step1.logo_cleanup")
        clean_hint = ttk.Label(tab, text=tr("step1.logo_cleanup_hint"), foreground="#555", wraplength=520, justify="left")
        clean_hint.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self._register_i18n(clean_hint, "text", "step1.logo_cleanup_hint")
        direct_hint = ttk.Label(tab, text=tr("step1.logo_direct_hint"), foreground="#555", wraplength=520, justify="left")
        direct_hint.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._register_i18n(direct_hint, "text", "step1.logo_direct_hint")
        accent_check = ttk.Checkbutton(tab, text=tr("step1.logo_preserve_accents"), variable=self.logo_mask_preserve_accents_var)
        accent_check.grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._register_i18n(accent_check, "text", "step1.logo_preserve_accents")
        accent_label = ttk.Label(
            tab,
            text=tr("step1.logo_accent_contrast_hint"),
            foreground="#555",
            wraplength=520,
            justify="left",
        )
        accent_label.grid(row=9, column=0, columnspan=3, sticky="ew", pady=3)
        self._register_i18n(accent_label, "text", "step1.logo_accent_contrast_hint")
        create_btn = _create_action_button(tab, tr("step1.create_mask"), self.create_logo_mask_preview, bg=ACTION_GREEN, activebackground=ACTION_GREEN_ACTIVE)
        create_btn.grid(row=10, column=0, sticky="w", pady=(12, 0))
        self._register_i18n(create_btn, "text", "step1.create_mask")
        direct_btn = _create_action_button(tab, tr("step1.logo_direct_black"), self.create_logo_direct_black_preview, bg=ACTION_BLUE, activebackground=ACTION_BLUE_ACTIVE)
        direct_btn.grid(row=10, column=1, sticky="w", padx=(8, 0), pady=(12, 0))
        self._register_i18n(direct_btn, "text", "step1.logo_direct_black")
        clear_btn = _create_action_button(tab, tr("step1.clear_mask"), self.clear_logo_mask, bg=ACTION_YELLOW, activebackground=ACTION_YELLOW_ACTIVE)
        clear_btn.grid(row=10, column=2, sticky="w", padx=(8, 0), pady=(12, 0))
        self._register_i18n(clear_btn, "text", "step1.clear_mask")

def _build_step1_photo_scan_tab(self) -> None:
        tab = self.photo_scan_tab
        tab.columnconfigure(1, weight=1)
        hint = ttk.Label(tab, text=tr("step1.photo_scan_hint"), foreground="#555", wraplength=560, justify="left")
        hint.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        self._register_i18n(hint, "text", "step1.photo_scan_hint")

        mode_box = ttk.LabelFrame(tab, text=tr("step1.photo_scan_mode"), padding=(8, 6, 8, 6))
        mode_box.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        # Alle Auswahlbuttons bleiben content-breit nebeneinander.
        # Nur die unsichtbare letzte Spalte nimmt Restbreite auf.
        for _col in range(3):
            mode_box.columnconfigure(_col, weight=0)
        mode_box.columnconfigure(3, weight=1)
        self._register_i18n(mode_box, "text", "step1.photo_scan_mode")
        for index, mode in enumerate(("auto", "clean", "detail", "color", "bw", "faded")):
            rb = ttk.Radiobutton(
                mode_box,
                text=tr(f"step1.photo_scan_mode_{mode}"),
                value=mode,
                variable=self.photo_scan_mode_var,
                command=self.apply_photo_scan_mode_defaults,
            )
            rb.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 12), pady=2)
            self._register_i18n(rb, "text", f"step1.photo_scan_mode_{mode}")

        action_row = ttk.Frame(tab)
        action_row.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        action_row.columnconfigure(0, weight=0)
        action_row.columnconfigure(1, weight=0)
        action_row.columnconfigure(2, weight=0)
        action_row.columnconfigure(3, weight=1)
        auto_apply_btn = _create_action_button(
            action_row,
            tr("step1.photo_scan_apply_auto"),
            self.run_photo_scan_auto_best,
            bg=ACTION_GRAY,
            activebackground=ACTION_GRAY_ACTIVE,
        )
        auto_apply_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._register_i18n(auto_apply_btn, "text", "step1.photo_scan_apply_auto")
        clear_btn = _create_action_button(action_row, tr("step1.clear_mask"), self.clear_logo_mask, bg=ACTION_YELLOW, activebackground=ACTION_YELLOW_ACTIVE)
        clear_btn.grid(row=0, column=1, sticky="w")
        self._register_i18n(clear_btn, "text", "step1.clear_mask")

        optional = ttk.LabelFrame(tab, text=tr("step1.photo_scan_optional"), padding=(8, 6, 8, 6))
        optional.grid(row=3, column=0, columnspan=4, sticky="ew")
        optional.columnconfigure(0, weight=0)
        optional.columnconfigure(1, weight=0)
        optional.columnconfigure(2, weight=0)
        optional.columnconfigure(3, weight=1)
        self._register_i18n(optional, "text", "step1.photo_scan_optional")

        max_label = ttk.Label(optional, text=tr("step1.photo_scan_max_colors"))
        max_label.grid(row=0, column=0, sticky="w", pady=3)
        self._register_i18n(max_label, "text", "step1.photo_scan_max_colors")
        self._add_tooltip(max_label, "tooltip.step1.photo_scan_max_colors")
        ttk.Spinbox(optional, from_=1, to=8, textvariable=self.photo_scan_max_colors_var, width=8).grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)

        area_label = ttk.Label(optional, text=tr("step1.photo_scan_min_area"))
        area_label.grid(row=1, column=0, sticky="w", pady=3)
        self._register_i18n(area_label, "text", "step1.photo_scan_min_area")
        self._add_tooltip(area_label, "tooltip.step1.photo_scan_min_area")
        ttk.Spinbox(optional, from_=1, to=9999, textvariable=self.photo_scan_min_area_var, width=8).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=3)

        weak_label = ttk.Label(optional, text=tr("step1.photo_scan_weak_contrast"))
        weak_label.grid(row=2, column=0, sticky="w", pady=3)
        self._register_i18n(weak_label, "text", "step1.photo_scan_weak_contrast")
        self._add_tooltip(weak_label, "tooltip.step1.photo_scan_weak_contrast")
        weak_scale = ttk.Scale(optional, from_=0, to=100, variable=self.photo_scan_weak_contrast_var, orient="horizontal", length=STEP1_SCALE_MIN_LENGTH, command=lambda value: self._set_numeric_var(self.photo_scan_weak_contrast_var, value, 0))
        weak_scale.grid(row=2, column=1, sticky="w", padx=(8, 8), pady=3)
        _bind_responsive_scale_length(
            optional,
            weak_scale,
            min_length=180,
            max_length=STEP1_NOISE_SCALE_MAX_LENGTH,
            reserve_px=250,
        )
        ttk.Spinbox(optional, from_=0, to=100, textvariable=self.photo_scan_weak_contrast_var, width=8).grid(row=2, column=2, sticky="w", pady=3)

        checks = ttk.Frame(optional)
        checks.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        for index, (key, var, tip) in enumerate((
            ("step1.photo_scan_protect_background", self.photo_scan_protect_background_var, "tooltip.step1.photo_scan_protect_background"),
            ("step1.photo_scan_object_mask_first", self.photo_scan_object_mask_first_var, "tooltip.step1.photo_scan_object_mask_first"),
            ("step1.photo_scan_protect_thin_lines", self.photo_scan_protect_thin_lines_var, "tooltip.step1.photo_scan_weak_contrast"),
            ("step1.photo_scan_close_lines", self.photo_scan_close_lines_var, "tooltip.step1.photo_scan_close_lines"),
            ("step1.photo_scan_fill_small_holes", self.photo_scan_fill_small_holes_var, "tooltip.step1.photo_scan_fill_small_holes"),
            ("step1.photo_scan_preserve_accents", self.photo_scan_preserve_accents_var, "tooltip.step1.photo_scan_preserve_accents"),
        )):
            check = ttk.Checkbutton(checks, text=tr(key), variable=var)
            check.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 18), pady=2)
            self._register_i18n(check, "text", key)
            self._add_tooltip(check, tip)

        despeckle_check = ttk.Checkbutton(
            optional,
            text=tr("step1.photo_scan_despeckle"),
            variable=self.photo_scan_despeckle_var,
            command=self.on_photo_scan_despeckle_toggle,
        )
        despeckle_check.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self._register_i18n(despeckle_check, "text", "step1.photo_scan_despeckle")
        self._add_tooltip(despeckle_check, "tooltip.step1.photo_scan_despeckle")
        despeckle_area_label = ttk.Label(optional, text=tr("step1.photo_scan_despeckle_area"))
        despeckle_area_label.grid(row=5, column=1, sticky="e", pady=(8, 0), padx=(8, 4))
        self._register_i18n(despeckle_area_label, "text", "step1.photo_scan_despeckle_area")
        self._add_tooltip(despeckle_area_label, "tooltip.step1.photo_scan_despeckle_area")
        ttk.Spinbox(optional, from_=0, to=500, textvariable=self.photo_scan_despeckle_area_var, width=8).grid(row=5, column=2, sticky="w", pady=(8, 0))

        optional_action_row = ttk.Frame(optional)
        optional_action_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        optional_action_row.columnconfigure(1, weight=1)
        current_apply_btn = _create_action_button(
            optional_action_row,
            tr("step1.photo_scan_apply_current"),
            self.create_photo_scan_cleanup_preview,
            bg=ACTION_GREEN,
            activebackground=ACTION_GREEN_ACTIVE,
        )
        current_apply_btn.grid(row=0, column=0, sticky="w")
        self._register_i18n(current_apply_btn, "text", "step1.photo_scan_apply_current")

        status_label = ttk.Label(tab, textvariable=self.photo_scan_status_var, foreground="#555", wraplength=560, justify="left")
        status_label.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))

def _build_step1_ai_upscale_tab(self) -> None:
        tab = self.ai_upscale_tab
        tab.columnconfigure(1, weight=1)
        
        hint = ttk.Label(tab, text=tr("step1.ai_upscale_hint"), foreground="#555", wraplength=560, justify="left")
        hint.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._register_i18n(hint, "text", "step1.ai_upscale_hint")
        
        model_label = ttk.Label(tab, text=tr("step1.ai_upscale_model"))
        model_label.grid(row=1, column=0, sticky="w", pady=3)
        self._register_i18n(model_label, "text", "step1.ai_upscale_model")
        ttk.Entry(tab, textvariable=self.ai_upscale_model_var, width=40).grid(row=1, column=1, sticky="ew", pady=3, padx=(8, 4))
        ttk.Button(tab, text=tr("button.choose"), command=self.choose_ai_upscale_model).grid(row=1, column=2, sticky="w", pady=3)
        
        size_frame = ttk.LabelFrame(tab, text=tr("step1.ai_upscale_size"), padding=(8, 6, 8, 6))
        size_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        size_frame.columnconfigure(1, weight=1)
        self._register_i18n(size_frame, "text", "step1.ai_upscale_size")

        original_size_label = ttk.Label(
            size_frame,
            textvariable=self.ai_upscale_original_size_var,
            foreground="#555",
            justify="left",
        )
        original_size_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        
        ttk.Radiobutton(size_frame, text=tr("step1.ai_upscale_px"), value="px", variable=self.ai_upscale_unit_var).grid(row=1, column=0, sticky="w", padx=(0, 12))
        self._register_i18n(size_frame.winfo_children()[-1], "text", "step1.ai_upscale_px")
        ttk.Radiobutton(size_frame, text=tr("step1.ai_upscale_percent"), value="percent", variable=self.ai_upscale_unit_var).grid(row=1, column=1, sticky="w")
        self._register_i18n(size_frame.winfo_children()[-1], "text", "step1.ai_upscale_percent")
        
        width_label = ttk.Label(size_frame, text=tr("step1.ai_upscale_width"))
        width_label.grid(row=2, column=0, sticky="w", pady=(8, 3))
        self._register_i18n(width_label, "text", "step1.ai_upscale_width")
        width_entry = ttk.Entry(size_frame, textvariable=self.ai_upscale_width_var, width=12)
        width_entry.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 3))
        
        height_label = ttk.Label(size_frame, text=tr("step1.ai_upscale_height"))
        height_label.grid(row=3, column=0, sticky="w", pady=3)
        self._register_i18n(height_label, "text", "step1.ai_upscale_height")
        height_entry = ttk.Entry(size_frame, textvariable=self.ai_upscale_height_var, width=12)
        height_entry.grid(row=3, column=1, sticky="w", padx=(8, 0), pady=3)
        self.ai_upscale_width_entry = width_entry
        self.ai_upscale_height_entry = height_entry

        master_frame = ttk.Frame(size_frame)
        master_frame.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.ai_upscale_master_frame = master_frame
        ttk.Label(master_frame, text="Bei festen Proportionen bearbeiten:").pack(side="left")
        ttk.Radiobutton(master_frame, text="Breite", value="width", variable=self.ai_upscale_aspect_master_var, command=self.update_ai_upscale_dimension_edit_state).pack(side="left", padx=(8, 4))
        ttk.Radiobutton(master_frame, text="Höhe", value="height", variable=self.ai_upscale_aspect_master_var, command=self.update_ai_upscale_dimension_edit_state).pack(side="left")
        
        keep_aspect_btn = ttk.Checkbutton(size_frame, text=tr("step1.ai_upscale_keep_aspect"), variable=self.ai_upscale_keep_aspect_var, command=self.update_ai_upscale_dimension_edit_state)
        keep_aspect_btn.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.update_ai_upscale_dimension_edit_state()
        self._register_i18n(keep_aspect_btn, "text", "step1.ai_upscale_keep_aspect")
        
        output_label = ttk.Label(tab, text=tr("step1.ai_upscale_output"))
        output_label.grid(row=3, column=0, sticky="w", pady=(12, 3))
        self._register_i18n(output_label, "text", "step1.ai_upscale_output")
        ttk.Entry(tab, textvariable=self.ai_upscale_output_var, width=40).grid(row=3, column=1, sticky="ew", pady=(12, 3), padx=(8, 4))
        ttk.Button(tab, text=tr("button.choose"), command=self.choose_ai_upscale_output).grid(row=3, column=2, sticky="w", pady=(12, 3))
        
        action_row = ttk.Frame(tab)
        action_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        action_row.columnconfigure(1, weight=1)
        
        preview_btn = _create_action_button(
            action_row,
            tr("step1.ai_upscale_preview"),
            self.create_ai_upscale_preview,
            bg=ACTION_GREEN,
            activebackground=ACTION_GREEN_ACTIVE,
        )
        preview_btn.grid(row=0, column=0, sticky="w")
        self._register_i18n(preview_btn, "text", "step1.ai_upscale_preview")
        
        warning_label = ttk.Label(tab, text=tr("step1.ai_upscale_warning"), foreground="#ca8a04", wraplength=560, justify="left")
        warning_label.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._register_i18n(warning_label, "text", "step1.ai_upscale_warning")
