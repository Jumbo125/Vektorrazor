# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""UI-Aufbau für Workflow-Schritt 2.

Ausgelagert aus workflow_app.py, damit die Hauptdatei kleiner bleibt.
Die Funktionen erwarten weiterhin die WorkflowApp-Instanz als erstes Argument.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import recolor_engine as recolor
import vector_engine as vector
from i18n import tr


DXF_COMPATIBILITY_KEYS = [
    "default",
    "illustrator",
    "coreldraw",
    "coreldraw_modern",
    "autocad",
    "freecad",
    "manual",
]
VECTOR_MODE_KEYS = ["area", "centerline"]
PREVIEW_MODE_KEYS = ["object", "contour", "mask", "cut_risk"]
CLEANUP_MODE_KEYS = ["off", "mm2", "percent"]
INTERNAL_SCALE_KEYS = ["1", "2", "3"]
MOTIF_PROFILE_KEYS = ["logo", "organic", "mixed"]

DXF_VERSION_CHOICES = {
    "R2000": "R2000  –  Illustrator/CorelDRAW/LibreCAD/CAM  (empfohlen)",
    "R2004": "R2004  –  ältere AutoCAD/CAD-Systeme",
    "R2007": "R2007  –  Illustrator bis AutoCAD 2007 / CorelDRAW modern",
    "R2010": "R2010  –  AutoCAD/CAD modern  (nicht ideal für Illustrator)",
    "R2013": "R2013  –  neue CAD-Systeme",
    "R2018": "R2018  –  sehr neue CAD-Systeme",
}


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
        scale_hint_top = ttk.Label(
            toolbar,
            text=tr("step2.scale_default_hint"),
            foreground="#555",
            wraplength=360,
            justify="left",
        )
        scale_hint_top.grid(row=1, column=5, columnspan=3, sticky="w", padx=(10, 0), pady=(4, 0))

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
        actions.grid_remove()

        panes = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        panes.grid(row=1, column=0, sticky="nsew")

        settings = ttk.Frame(panes)
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(2, weight=1)
        workflow_bar = ttk.LabelFrame(settings, text=tr("step2.save_options"), padding=(8, 6, 8, 6))
        workflow_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        workflow_bar.columnconfigure(1, weight=1)
        self.step2_workflow_bar = workflow_bar
        self._register_i18n(workflow_bar, "text", "step2.save_options")
        ttk.Label(workflow_bar, text="Zwischenbild:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(workflow_bar, textvariable=self.vector_source_name_var, style="Source.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(workflow_bar, text="Output:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        ttk.Entry(workflow_bar, textvariable=self.output_path_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(4, 0))
        output_location_btn = ttk.Button(workflow_bar, text=tr("step2.choose_output"), command=self.choose_vector_output)
        output_location_btn.grid(row=1, column=3, padx=(6, 0), pady=(4, 0))
        self._register_i18n(output_location_btn, "text", "step2.choose_output")
        pixel_mm_label = ttk.Label(workflow_bar, text=tr("step2.pixel_to_mm"))
        pixel_mm_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self._register_i18n(pixel_mm_label, "text", "step2.pixel_to_mm")
        ttk.Entry(workflow_bar, textvariable=self.pixel_to_mm_var, width=8).grid(row=2, column=1, sticky="w", pady=(6, 0))
        scale_hint_side = ttk.Label(
            workflow_bar,
            text=tr("step2.scale_default_hint"),
            foreground="#555",
            wraplength=420,
            justify="left",
        )
        scale_hint_side.grid(row=2, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=(6, 0))
        bbox_label = ttk.Label(workflow_bar, text=tr("step2.bbox"))
        bbox_label.grid(row=3, column=0, sticky="nw", pady=(6, 0))
        self._register_i18n(bbox_label, "text", "step2.bbox")
        ttk.Label(workflow_bar, textvariable=self.vector_bbox_info_var, foreground="#555", justify="left").grid(row=3, column=1, columnspan=3, sticky="w", pady=(6, 0))
        target_w_label = ttk.Label(workflow_bar, text=tr("step2.target_width_mm"))
        target_w_label.grid(row=4, column=0, sticky="w", pady=(6, 0))
        self._register_i18n(target_w_label, "text", "step2.target_width_mm")
        ttk.Entry(workflow_bar, textvariable=self.target_width_mm_var, width=8).grid(row=4, column=1, sticky="w", pady=(6, 0))
        target_h_label = ttk.Label(workflow_bar, text=tr("step2.target_height_mm"))
        target_h_label.grid(row=4, column=2, sticky="w", padx=(12, 4), pady=(6, 0))
        self._register_i18n(target_h_label, "text", "step2.target_height_mm")
        ttk.Entry(workflow_bar, textvariable=self.target_height_mm_var, width=8).grid(row=4, column=3, sticky="w", pady=(6, 0))
        scale_btn = ttk.Button(workflow_bar, text=tr("step2.calculate_scale"), command=self.apply_target_size_to_scale)
        scale_btn.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._register_i18n(scale_btn, "text", "step2.calculate_scale")
        cad_tol_label = ttk.Label(workflow_bar, text=tr("step2.cad_tolerance_mm"))
        cad_tol_label.grid(row=5, column=2, sticky="w", padx=(12, 4), pady=(6, 0))
        self._register_i18n(cad_tol_label, "text", "step2.cad_tolerance_mm")
        ttk.Entry(workflow_bar, textvariable=self.cad_tolerance_mm_var, width=8).grid(row=5, column=3, sticky="w", pady=(6, 0))
        ttk.Label(workflow_bar, text="Kompatibilität:").grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.compat_box_side = ttk.Combobox(
            workflow_bar,
            textvariable=self.dxf_compatibility_display_var,
            values=[self._compat_label(key) for key in DXF_COMPATIBILITY_KEYS],
            state="readonly",
            width=30,
        )
        self.compat_box_side.grid(row=6, column=1, sticky="w", pady=(6, 0))
        self.compat_box_side.bind("<<ComboboxSelected>>", lambda _event: self.on_dxf_compatibility_display_changed())
        ttk.Label(workflow_bar, text="DXF-Format:").grid(row=7, column=0, sticky="w", pady=(6, 0))
        self.version_box_side = ttk.Combobox(
            workflow_bar,
            textvariable=self.dxf_version_var,
            values=list(DXF_VERSION_CHOICES.values()),
            state="readonly",
            width=42,
        )
        self.version_box_side.grid(row=7, column=1, columnspan=3, sticky="w", pady=(6, 0))
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
        self.vector_opts_head = ttk.LabelFrame(self.step2_opts_scroll.inner, text=tr("step2.motif_profile_group"), padding=(8, 6, 8, 6))
        self.vector_opts_head.grid(row=0, column=0, sticky="ew", pady=(12, 12))
        self.vector_opts_head.columnconfigure(4, weight=1)
        self._register_i18n(self.vector_opts_head, "text", "step2.motif_profile_group")
        motif_label = ttk.Label(self.vector_opts_head, text=tr("step2.motif_profile"))
        motif_label.grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._register_i18n(motif_label, "text", "step2.motif_profile")
        self.motif_profile_box = ttk.Combobox(
            self.vector_opts_head,
            textvariable=self.motif_profile_display_var,
            values=[self._motif_profile_label(key) for key in MOTIF_PROFILE_KEYS],
            state="readonly",
            width=24,
        )
        self.motif_profile_box.grid(row=0, column=1, sticky="w", padx=(0, 12))
        self.motif_profile_box.bind("<<ComboboxSelected>>", lambda _event: self.on_motif_profile_display_changed())
        self.motif_profile_display_var.set(self._motif_profile_label(self.motif_profile_var.get()))
        self.auto_expert_btn = ttk.Button(self.vector_opts_head, text=tr("step2.auto_expert_from_image"), command=self.auto_tune_expert_values_from_image)
        self.auto_expert_btn.grid(row=0, column=2, sticky="w")
        self._register_i18n(self.auto_expert_btn, "text", "step2.auto_expert_from_image")
        opts_outer = ttk.LabelFrame(self.step2_opts_scroll.inner, text="Vektor-Optionen", padding=8)
        opts_outer.grid(row=1, column=0, sticky="nsew")
        self.vector_options_container = opts_outer
        opts_outer.columnconfigure(0, weight=1)

        self.complexity_toggle_frame = tk.Frame(opts_outer, bd=0, highlightthickness=0)
        self.complexity_toggle_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.complexity_mode_label = tk.Label(
            self.complexity_toggle_frame,
            text=tr("ui.mode"),
            font=("Segoe UI", 9, "bold"),
            bd=0,
        )
        self.complexity_mode_label.pack(side="left", padx=(0, 8))
        self._register_i18n(self.complexity_mode_label, "text", "ui.mode")
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

        self.preview_view_frame = ttk.Frame(opts_outer)
        self.preview_view_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        preview_view_label = ttk.Label(self.preview_view_frame, text=tr("step2.preview_mode"))
        preview_view_label.grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._register_i18n(preview_view_label, "text", "step2.preview_mode")
        self.preview_mode_box = ttk.Combobox(
            self.preview_view_frame,
            textvariable=self.preview_mode_display_var,
            values=[self._preview_label(key) for key in PREVIEW_MODE_KEYS],
            state="readonly",
            width=18,
        )
        self.preview_mode_box.grid(row=0, column=1, sticky="w", padx=(4, 12))
        self.preview_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_preview_mode_display_changed())

        opts = ttk.Frame(opts_outer)
        opts.grid(row=2, column=0, sticky="nsew")
        self.vector_options_frame = opts
        opts.columnconfigure(1, weight=1)
        opts.columnconfigure(3, weight=1)
        ttk.Label(opts, text="Vektorart").grid(row=0, column=0, sticky="w")
        self.vector_mode_box = ttk.Combobox(opts, textvariable=self.vector_mode_display_var, values=[self._mode_label(key) for key in VECTOR_MODE_KEYS], state="readonly", width=20)
        self.vector_mode_box.grid(row=0, column=1, sticky="w", padx=(4, 12))
        self.vector_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_vector_mode_display_changed())
        ttk.Label(opts, text="Linien zusammenführen px").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(opts, textvariable=self.centerline_merge_px_var, width=8).grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(6, 0))
        ttk.Checkbutton(opts, text="Nur geschlossene Pfade", variable=self.closed_paths_only_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="Zusammenhängende Pfade gruppieren (SVG)", variable=self.group_connected_paths_var).grid(row=3, column=0, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Checkbutton(opts, text="SVG-Flächen füllen (Export)", variable=self.fill_closed_shapes_var).grid(row=28, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opts, text="Export-Layer pro Farbe", variable=self.force_color_layers_var).grid(row=28, column=2, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opts, text="Bezier für SVG", variable=self.use_bezier_var).grid(row=29, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Checkbutton(opts, text="Objekte in Layer erstellen (DXF)", variable=self.object_layers_dxf_var).grid(row=29, column=2, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Checkbutton(
            opts,
            text="Doppelte Linien entfernen (CAD)",
            variable=self.unique_cad_lines_var,
            command=self.render_vector_preview
        ).grid(row=22, column=0, columnspan=2, sticky="w", pady=(8, 0))
        cad_epsilon_label = ttk.Label(opts, text=tr("step2.cad_deviation"))
        cad_epsilon_label.grid(row=30, column=0, sticky="w", pady=(8, 0))
        self._register_i18n(cad_epsilon_label, "text", "step2.cad_deviation")
        self._add_tooltip(cad_epsilon_label, "tooltip.step2.cad_deviation")
        ttk.Scale(opts, from_=0.0, to=5.0, variable=self.global_epsilon_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.global_epsilon_var, value, 2)).grid(row=30, column=1, sticky="ew", padx=(4, 4), pady=(8, 0))
        ttk.Spinbox(opts, from_=0.0, to=5.0, increment=0.01, textvariable=self.global_epsilon_var, width=8, format="%.2f").grid(row=30, column=2, sticky="w", pady=(8, 0))
        ttk.Label(opts, textvariable=self.cad_point_count_var, foreground="#555").grid(row=30, column=3, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 0))
        cad_dialog_btn = tk.Button(
            opts,
            text=tr("step2.open_cad_cleanup"),
            command=self.open_cad_cleanup_dialog,
            bg="#7c3aed",
            fg="white",
            activebackground="#6d28d9",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=5,
            font=("Segoe UI", 9, "bold"),
        )
        cad_dialog_btn.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._register_i18n(cad_dialog_btn, "text", "step2.open_cad_cleanup")
        ttk.Button(opts, text="Epsilon auf alle Farben anwenden", command=self.apply_global_epsilon_to_rows).grid(row=31, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.high_detail_btn = ttk.Button(opts, text=tr("step2.high_detail"), command=self.apply_high_detail_mode)
        self.high_detail_btn.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._register_i18n(self.high_detail_btn, "text", "step2.high_detail")
        ttk.Label(opts, text="Doppellinien-Toleranz px").grid(row=22, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(opts, textvariable=self.duplicate_line_tolerance_var, width=8).grid(row=22, column=3, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Checkbutton(opts, text="Rundungen glätten", variable=self.smooth_contours_var).grid(row=21, column=0, sticky="w", pady=(8, 0))
        ttk.Scale(opts, from_=0, to=5, variable=self.smooth_strength_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.smooth_strength_var, value, 3)).grid(row=21, column=1, sticky="ew", padx=(4, 4), pady=(8, 0))
        ttk.Spinbox(opts, from_=0, to=5, increment=0.001, textvariable=self.smooth_strength_var, width=8, format="%.3f").grid(row=21, column=2, sticky="w", padx=(4, 0), pady=(8, 0))
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
        anchor_cleanup_check = ttk.Checkbutton(opts, text=tr("step2.anchor_cleanup"), variable=self.remove_loose_points_var, command=self.on_anchor_cleanup_toggle)
        anchor_cleanup_check.grid(row=17, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._register_i18n(anchor_cleanup_check, "text", "step2.anchor_cleanup")
        self.anchor_distance_label = ttk.Label(opts, text=tr("step2.anchor_min_distance"))
        self.anchor_distance_label.grid(row=18, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(self.anchor_distance_label, "text", "step2.anchor_min_distance")
        self._add_tooltip(self.anchor_distance_label, "tooltip.step2.anchor_min_distance")
        self.anchor_distance_scale = ttk.Scale(opts, from_=0.0, to=5.0, variable=self.anchor_neighbor_distance_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.anchor_neighbor_distance_var, value, 2))
        self.anchor_distance_scale.grid(row=18, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        self.anchor_distance_spin = ttk.Spinbox(opts, from_=0.0, to=5.0, increment=0.01, textvariable=self.anchor_neighbor_distance_var, width=8, format="%.2f")
        self.anchor_distance_spin.grid(row=18, column=2, sticky="w", pady=(2, 0))
        self._refresh_anchor_cleanup_controls()
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
        bridge_check.grid(row=23, column=0, sticky="w", pady=(10, 0))
        self._register_i18n(bridge_check, "text", "step2.bridge_tabs")
        ttk.Button(
            opts,
            text="?",
            width=3,
            command=lambda: self.show_i18n_info("msg.bridge_tabs_info_title", "msg.bridge_tabs_info_body"),
        ).grid(row=23, column=1, sticky="w", padx=(4, 0), pady=(10, 0))
        bridge_mm_label = ttk.Label(opts, text=tr("step2.bridge_width_mm"))
        bridge_mm_label.grid(row=24, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(bridge_mm_label, "text", "step2.bridge_width_mm")
        ttk.Scale(opts, from_=0.0, to=10.0, variable=self.bridge_width_mm_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.bridge_width_mm_var, value, 3)).grid(row=24, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0.0, to=10.0, increment=0.001, textvariable=self.bridge_width_mm_var, width=8, format="%.3f").grid(row=24, column=2, sticky="w", pady=(2, 0))
        bridge_percent_label = ttk.Label(opts, text=tr("step2.bridge_width_percent"))
        bridge_percent_label.grid(row=25, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(bridge_percent_label, "text", "step2.bridge_width_percent")
        ttk.Scale(opts, from_=0.0, to=5.0, variable=self.bridge_width_percent_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.bridge_width_percent_var, value, 3)).grid(row=25, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=0.0, to=5.0, increment=0.001, textvariable=self.bridge_width_percent_var, width=8, format="%.3f").grid(row=25, column=2, sticky="w", pady=(2, 0))
        bridge_count_label = ttk.Label(opts, text=tr("step2.bridge_count"))
        bridge_count_label.grid(row=26, column=0, sticky="w", pady=(2, 0))
        self._register_i18n(bridge_count_label, "text", "step2.bridge_count")
        ttk.Scale(opts, from_=1.0, to=8.0, variable=self.bridge_count_var, orient="horizontal", command=lambda value: self._set_numeric_var(self.bridge_count_var, value, 3)).grid(row=26, column=1, sticky="ew", padx=(4, 4), pady=(2, 0))
        ttk.Spinbox(opts, from_=1.0, to=8.0, increment=1.000, textvariable=self.bridge_count_var, width=8, format="%.3f").grid(row=26, column=2, sticky="w", pady=(2, 0))
        ttk.Label(opts, text="Kleine Objekte löschen").grid(row=19, column=0, sticky="w", pady=(8, 0))
        self.cleanup_mode_box = ttk.Combobox(opts, textvariable=self.cleanup_mode_display_var, values=[self._cleanup_label(key) for key in CLEANUP_MODE_KEYS], state="readonly", width=12)
        self.cleanup_mode_box.grid(row=19, column=1, sticky="w", padx=(4, 12), pady=(8, 0))
        self.cleanup_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_cleanup_mode_display_changed())
        ttk.Label(opts, text="mm²").grid(row=19, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(opts, textvariable=self.min_object_area_mm2_var, width=8).grid(row=19, column=3, sticky="w", padx=(4, 0), pady=(8, 0))
        ttk.Label(opts, text="% Bildfläche").grid(row=20, column=2, sticky="w", pady=(2, 0))
        ttk.Entry(opts, textvariable=self.min_object_percent_var, width=8).grid(row=20, column=3, sticky="w", padx=(4, 0), pady=(2, 0))

        preview = ttk.Frame(panes)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)

        select_tools = ttk.LabelFrame(preview, text="Pfad-Auswahl", padding=(6, 4, 6, 4))
        select_tools.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        select_tools.columnconfigure(5, weight=1)
        select_tools.columnconfigure(8, weight=1)
        self.selection_mode_check = ttk.Checkbutton(
            select_tools,
            text="Auswahl-Modus",
            variable=self.vector_selection_mode_var,
            command=self.update_vector_selection_mode_ui,
        )
        self.selection_mode_check.grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Button(select_tools, text="Ausgewählte Pfade entfernen", command=self.remove_selected_contour).grid(row=0, column=1, sticky="w", padx=(0, 6))
        ttk.Button(select_tools, text="Auswahl aufheben", command=self.clear_selected_contour).grid(row=0, column=2, sticky="w", padx=(0, 8))
        anchor_check = ttk.Checkbutton(
            select_tools,
            text=tr("step2.show_anchor_points"),
            variable=self.show_anchor_points_var,
            command=self.render_vector_preview,
        )
        anchor_check.grid(row=0, column=3, sticky="w", padx=(0, 8))
        self._register_i18n(anchor_check, "text", "step2.show_anchor_points")
        ttk.Label(select_tools, text="Zoom").grid(row=0, column=4, sticky="w", padx=(8, 4))
        self.step2_zoom_scale = ttk.Scale(
            select_tools,
            from_=0.25,
            to=8.0,
            variable=self.step2_shared_zoom_var,
            orient="horizontal",
            command=self.on_step2_shared_zoom_changed,
        )
        self.step2_zoom_scale.grid(row=0, column=5, sticky="ew", padx=(0, 8))
        self.step2_zoom_spin = ttk.Spinbox(
            select_tools,
            from_=25,
            to=800,
            increment=1,
            textvariable=self.step2_zoom_percent_var,
            width=7,
            format="%.0f",
            command=self.on_step2_zoom_spin_changed,
        )
        self.step2_zoom_spin.grid(row=0, column=6, sticky="w", padx=(0, 6))
        self.step2_zoom_spin.bind("<Return>", lambda _event: self.on_step2_zoom_spin_changed())
        self.step2_zoom_spin.bind("<FocusOut>", lambda _event: self.on_step2_zoom_spin_changed())
        self.step2_zoom_preset_box = ttk.Combobox(
            select_tools,
            textvariable=self.step2_zoom_preset_var,
            values=["25%", "50%", "75%", "100%", "150%", "200%", "300%", "400%", "800%"],
            state="readonly",
            width=7,
        )
        self.step2_zoom_preset_box.grid(row=0, column=7, sticky="w", padx=(0, 8))
        self.step2_zoom_preset_box.bind("<<ComboboxSelected>>", lambda _event: self.on_step2_zoom_preset_changed())
        ttk.Label(select_tools, textvariable=self.selected_contour_text_var, foreground="#555").grid(row=0, column=8, sticky="w")
        ttk.Label(
            select_tools,
            text="Auswahl-Modus EIN: Klick = Pfad wählen, STRG+Klick = hinzufügen/umschalten, ALT+Klick = direkt entfernen. Auswahl-Modus AUS: Klick/Ziehen verschiebt die Vorschau; nur STRG+Klick wählt temporär.",
            foreground="#777",
            wraplength=840,
            justify="left",
        ).grid(row=1, column=0, columnspan=9, sticky="w", pady=(3, 0))

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

        bottom_actions = ttk.LabelFrame(preview, text=tr("step2.actions"), padding=(8, 6, 8, 6))
        bottom_actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        bottom_actions.columnconfigure(2, weight=1)
        self.step2_actions_frame = bottom_actions
        self._register_i18n(bottom_actions, "text", "step2.actions")

        self.step2_back_action_btn = tk.Button(
            bottom_actions,
            text=tr("nav.back_to_step1"),
            command=self.back_step,
            bg="#f97316",
            fg="white",
            activebackground="#ea580c",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=14,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.step2_back_action_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._register_i18n(self.step2_back_action_btn, "text", "nav.back_to_step1")

        self.export_action_btn = tk.Button(
            bottom_actions,
            text=tr("nav.export"),
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
        self._register_i18n(self.export_action_btn, "text", "nav.export")

        self.scale_export_action_btn = tk.Button(
            bottom_actions,
            text=tr("nav.scale_export"),
            command=self.open_scaled_export_dialog,
            bg="#0f766e",
            fg="white",
            activebackground="#115e59",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=16,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.scale_export_action_btn.grid(row=0, column=2, sticky="w", padx=(0, 12))
        self._register_i18n(self.scale_export_action_btn, "text", "nav.scale_export")

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
        controls.columnconfigure(6, weight=1)
        add_button = ttk.Button(controls, text="+ Farbe", command=self.add_empty_vector_row)
        add_button.grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._register_i18n(add_button, "text", "step2.add_color")
        profile_label = ttk.Label(controls, text="Profil:")
        profile_label.grid(row=0, column=1, sticky="w", padx=(12, 4))
        self._register_i18n(profile_label, "text", "step2.profile")
        ttk.Combobox(controls, textvariable=self.profile_var, values=list(vector.PROFILE_ROWS.keys()), state="readonly", width=18).grid(row=0, column=2, sticky="w")
        apply_button = ttk.Button(controls, text="Anwenden", command=self.apply_modal_profile_only)
        apply_button.grid(row=0, column=3, sticky="w", padx=(4, 0))
        self._register_i18n(apply_button, "text", "step2.apply")
        detect_button = ttk.Button(controls, text="Farben aus Bild erkennen", command=self.autofill_vector_rows_from_image)
        detect_button.grid(row=0, column=4, sticky="w", padx=(12, 0))
        self._register_i18n(detect_button, "text", "step2.detect_colors_from_image")
        refresh_button = tk.Button(
            controls,
            text=tr("step2.refresh_preview"),
            command=self.detect_and_preview_vector,
            bg="#15803d",
            fg="white",
            activebackground="#166534",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=12,
            pady=3,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        refresh_button.grid(row=0, column=5, sticky="w", padx=(12, 0))
        self._register_i18n(refresh_button, "text", "step2.refresh_preview")
        close_button = ttk.Button(controls, text=tr("button.close"), command=self.close_vector_colors_modal)
        close_button.grid(row=0, column=7, sticky="e")
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
