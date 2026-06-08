# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""UI-Aufbau für Workflow-Schritt 1.

Ausgelagert aus workflow_app.py, damit die Hauptdatei kleiner bleibt.
Die Funktionen erwarten weiterhin die WorkflowApp-Instanz als erstes Argument.
"""

from __future__ import annotations

from typing import Optional
import tkinter as tk
from tkinter import ttk

import recolor_engine as recolor
from i18n import tr


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
        self.photo_scan_tab = ttk.Frame(self.step1_notebook, padding=8)
        self.step1_notebook.add(self.basic_tab, text="Basis: Farben reduzieren")
        self.step1_notebook.add(self.manual_tab, text="Erweitert: manuell")
        self.step1_notebook.add(self.logo_tab, text="Logo-Maske")
        self.step1_notebook.add(self.photo_scan_tab, text=tr("step1.tab_photo_scan"))
        self._build_step1_basic_tab()
        self._build_step1_manual_tab()
        self._build_step1_logo_tab()
        self._build_step1_photo_scan_tab()

        step1_tools = ttk.LabelFrame(settings, text=tr("step1.tools"), padding=(8, 6, 8, 6))
        step1_tools.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        step1_tools.columnconfigure(3, weight=1)
        self._register_i18n(step1_tools, "text", "step1.tools")
        auto_btn = ttk.Button(step1_tools, text=tr("step1.auto_from_image"), command=self.auto_tune_from_input_image)
        auto_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._register_i18n(auto_btn, "text", "step1.auto_from_image")
        save_png_btn = ttk.Button(step1_tools, text=tr("step1.save_png"), command=self.export_intermediate_png)
        save_png_btn.grid(row=0, column=1, sticky="w")
        self._register_i18n(save_png_btn, "text", "step1.save_png")
        update_intermediate_btn = ttk.Button(
            step1_tools,
            text=tr("step1.update_intermediate"),
            command=lambda: self.use_edited_for_vector(show_message=True),
        )
        update_intermediate_btn.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._register_i18n(update_intermediate_btn, "text", "step1.update_intermediate")
        self.step1_next_action_btn = tk.Button(
            step1_tools,
            text=tr("nav.next_vectorize"),
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
        self.step1_next_action_btn.grid(row=0, column=4, sticky="e", padx=(12, 0))
        self._register_i18n(self.step1_next_action_btn, "text", "nav.next_vectorize")

        self.problem_hint_frame = ttk.LabelFrame(settings, text=tr("step1.problem_hint_title"), padding=(8, 6, 8, 6))
        self.problem_hint_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
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

        panes.add(settings, weight=2)
        panes.add(preview, weight=3)

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
        ttk.Button(prep, text="Zurücksetzen", command=self.reset_preprocessing).grid(row=6, column=0, sticky="w", pady=(6, 0))
        ttk.Button(prep, text="Vorbereitung + Farben neu erkennen", command=self.detect_basic_colors).grid(row=6, column=1, sticky="w", pady=(6, 0))

        detect = ttk.LabelFrame(tab, text="2) Automatische Farberkennung", padding=8)
        detect.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for col in range(6):
            detect.columnconfigure(col, weight=0)
        threshold_label = ttk.Label(detect, text="Schwelle")
        threshold_label.grid(row=0, column=0, sticky="w")
        self._add_tooltip(threshold_label, "tooltip.step1.threshold")
        ttk.Spinbox(detect, from_=0, to=255, textvariable=self.basic_threshold_var, width=7).grid(row=0, column=1, padx=(4, 12))
        min_area_label = ttk.Label(detect, text="Min. Fläche")
        min_area_label.grid(row=0, column=2, sticky="w")
        self._add_tooltip(min_area_label, "tooltip.step1.min_area")
        ttk.Spinbox(detect, from_=1, to=999999, textvariable=self.basic_min_area_var, width=8).grid(row=0, column=3, padx=(4, 12))
        max_colors_label = ttk.Label(detect, text="Max. Farben")
        max_colors_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._add_tooltip(max_colors_label, "tooltip.step1.max_colors")
        ttk.Spinbox(detect, from_=1, to=64, textvariable=self.basic_max_colors_var, width=7).grid(row=1, column=1, padx=(4, 12), pady=(4, 0))
        alpha_label = ttk.Label(detect, text="Alpha ab")
        alpha_label.grid(row=1, column=2, sticky="w", pady=(4, 0))
        self._add_tooltip(alpha_label, "tooltip.step1.alpha_from")
        ttk.Spinbox(detect, from_=0, to=255, textvariable=self.basic_alpha_var, width=8).grid(row=1, column=3, padx=(4, 12), pady=(4, 0))
        noise_label = ttk.Label(detect, text=tr("step1.noise_suppression"))
        noise_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._register_i18n(noise_label, "text", "step1.noise_suppression")
        self._add_tooltip(noise_label, "tooltip.step1.noise_suppression")
        ttk.Scale(detect, from_=0, to=100, variable=self.basic_noise_var, orient="horizontal").grid(row=2, column=1, sticky="ew", padx=(4, 12), pady=(4, 0))
        ttk.Spinbox(detect, from_=0, to=100, textvariable=self.basic_noise_var, width=8).grid(row=2, column=2, sticky="w", pady=(4, 0))
        fill_check = ttk.Checkbutton(detect, text=tr("step1.fill_solid_areas"), variable=self.basic_fill_solid_var, command=self.schedule_step1_preview)
        fill_check.grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self._register_i18n(fill_check, "text", "step1.fill_solid_areas")
        ttk.Button(detect, text="Farben erkennen", command=self.detect_basic_colors).grid(row=0, column=4, rowspan=4, sticky="ns", padx=(4, 4))
        ttk.Button(detect, text="Kontrastfarben neu", command=self.reassign_basic_targets).grid(row=0, column=5, rowspan=4, sticky="ns")

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
        logo_threshold_label = ttk.Label(tab, text="Logo-Schwelle")
        logo_threshold_label.grid(row=1, column=0, sticky="w", pady=3)
        self._add_tooltip(logo_threshold_label, "tooltip.step1.logo_threshold")
        ttk.Spinbox(tab, from_=1, to=100, textvariable=self.logo_mask_threshold_var, width=8).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(tab, text="höher = weniger wird schwarz", foreground="#555").grid(row=1, column=2, sticky="w", padx=(8, 0))
        logo_radius_label = ttk.Label(tab, text="Hintergrund-Radius")
        logo_radius_label.grid(row=2, column=0, sticky="w", pady=3)
        self._add_tooltip(logo_radius_label, "tooltip.step1.logo_radius")
        ttk.Spinbox(tab, from_=5, to=151, increment=2, textvariable=self.logo_mask_blur_var, width=8).grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(tab, text="größer = Schatten/Verläufe werden eher ignoriert", foreground="#555").grid(row=2, column=2, sticky="w", padx=(8, 0))
        ttk.Label(tab, text="Logo RGB").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(tab, textvariable=self.logo_mask_fg_var, width=14).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(tab, text="Hintergrund RGB").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(tab, textvariable=self.logo_mask_bg_var, width=14).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Checkbutton(tab, text="kleine Pixelstörungen glätten", variable=self.logo_mask_clean_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        accent_check = ttk.Checkbutton(tab, text=tr("step1.logo_preserve_accents"), variable=self.logo_mask_preserve_accents_var)
        accent_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._register_i18n(accent_check, "text", "step1.logo_preserve_accents")
        accent_label = ttk.Label(tab, text=tr("step1.logo_accent_rgb"))
        accent_label.grid(row=7, column=0, sticky="w", pady=3)
        self._register_i18n(accent_label, "text", "step1.logo_accent_rgb")
        ttk.Entry(tab, textvariable=self.logo_mask_accent_var, width=14).grid(row=7, column=1, sticky="w", pady=3)
        ttk.Button(tab, text="Logo-Maske erzeugen", command=self.create_logo_mask_preview).grid(row=8, column=0, sticky="w", pady=(12, 0))
        ttk.Button(tab, text="Maske entfernen / normale Vorschau", command=self.clear_logo_mask).grid(row=8, column=1, sticky="w", pady=(12, 0))

def _build_step1_photo_scan_tab(self) -> None:
        tab = self.photo_scan_tab
        tab.columnconfigure(1, weight=1)
        hint = ttk.Label(tab, text=tr("step1.photo_scan_hint"), foreground="#555", wraplength=500)
        hint.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._register_i18n(hint, "text", "step1.photo_scan_hint")

        max_label = ttk.Label(tab, text=tr("step1.photo_scan_max_colors"))
        max_label.grid(row=1, column=0, sticky="w", pady=3)
        self._register_i18n(max_label, "text", "step1.photo_scan_max_colors")
        self._add_tooltip(max_label, "tooltip.step1.photo_scan_max_colors")
        ttk.Spinbox(tab, from_=1, to=12, textvariable=self.photo_scan_max_colors_var, width=8).grid(row=1, column=1, sticky="w", pady=3)

        area_label = ttk.Label(tab, text=tr("step1.photo_scan_min_area"))
        area_label.grid(row=2, column=0, sticky="w", pady=3)
        self._register_i18n(area_label, "text", "step1.photo_scan_min_area")
        self._add_tooltip(area_label, "tooltip.step1.photo_scan_min_area")
        ttk.Spinbox(tab, from_=1, to=9999, textvariable=self.photo_scan_min_area_var, width=8).grid(row=2, column=1, sticky="w", pady=3)

        noise_label = ttk.Label(tab, text=tr("step1.photo_scan_noise"))
        noise_label.grid(row=3, column=0, sticky="w", pady=3)
        self._register_i18n(noise_label, "text", "step1.photo_scan_noise")
        self._add_tooltip(noise_label, "tooltip.step1.photo_scan_noise")
        ttk.Scale(tab, from_=0, to=100, variable=self.photo_scan_noise_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.photo_scan_noise_var, value, 0)).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Spinbox(tab, from_=0, to=100, textvariable=self.photo_scan_noise_var, width=8).grid(row=3, column=2, sticky="w", padx=(8, 0), pady=3)

        distance_label = ttk.Label(tab, text=tr("step1.photo_scan_foreground_distance"))
        distance_label.grid(row=4, column=0, sticky="w", pady=3)
        self._register_i18n(distance_label, "text", "step1.photo_scan_foreground_distance")
        self._add_tooltip(distance_label, "tooltip.step1.photo_scan_foreground_distance")
        ttk.Scale(tab, from_=5, to=80, variable=self.photo_scan_foreground_distance_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.photo_scan_foreground_distance_var, value, 0)).grid(row=4, column=1, sticky="ew", pady=3)
        ttk.Spinbox(tab, from_=5, to=80, textvariable=self.photo_scan_foreground_distance_var, width=8).grid(row=4, column=2, sticky="w", padx=(8, 0), pady=3)

        bg_check = ttk.Checkbutton(
            tab,
            text=tr("step1.photo_scan_protect_background"),
            variable=self.photo_scan_protect_background_var,
            command=self.schedule_step1_preview,
        )
        bg_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._register_i18n(bg_check, "text", "step1.photo_scan_protect_background")
        self._add_tooltip(bg_check, "tooltip.step1.photo_scan_protect_background")

        despeckle_check = ttk.Checkbutton(
            tab,
            text=tr("step1.photo_scan_despeckle"),
            variable=self.photo_scan_despeckle_var,
            command=self.on_photo_scan_despeckle_toggle,
        )
        despeckle_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._register_i18n(despeckle_check, "text", "step1.photo_scan_despeckle")
        self._add_tooltip(despeckle_check, "tooltip.step1.photo_scan_despeckle")

        despeckle_area_label = ttk.Label(tab, text=tr("step1.photo_scan_despeckle_area"))
        despeckle_area_label.grid(row=7, column=0, sticky="w", pady=3)
        self._register_i18n(despeckle_area_label, "text", "step1.photo_scan_despeckle_area")
        self._add_tooltip(despeckle_area_label, "tooltip.step1.photo_scan_despeckle_area")
        ttk.Scale(tab, from_=0, to=500, variable=self.photo_scan_despeckle_area_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.photo_scan_despeckle_area_var, value, 0)).grid(row=7, column=1, sticky="ew", pady=3)
        ttk.Spinbox(tab, from_=0, to=500, textvariable=self.photo_scan_despeckle_area_var, width=8).grid(row=7, column=2, sticky="w", padx=(8, 0), pady=3)

        apply_btn = ttk.Button(tab, text=tr("step1.photo_scan_apply"), command=self.create_photo_scan_cleanup_preview)
        apply_btn.grid(row=8, column=0, sticky="w", pady=(12, 0))
        self._register_i18n(apply_btn, "text", "step1.photo_scan_apply")
        clear_btn = ttk.Button(tab, text=tr("step1.clear_mask"), command=self.clear_logo_mask)
        clear_btn.grid(row=8, column=1, sticky="w", pady=(12, 0))
        self._register_i18n(clear_btn, "text", "step1.clear_mask")

        status_label = ttk.Label(tab, textvariable=self.photo_scan_status_var, foreground="#555", wraplength=500)
        status_label.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 0))
