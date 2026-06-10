# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""Ausgelagerte Dialoge für Skalieren/Export und STL-Extrusion.

Diese Datei sammelt Dialogfenster, die nicht zum permanent sichtbaren
Hauptlayout gehören, aber im Arbeitsablauf regelmäßig gebraucht werden.
Dazu zählen insbesondere Export- und Skalierungsdialoge sowie Optionen rund um
3D-/STL-nahe Ausgaben.

Die Dialoge werden absichtlich separat gehalten, damit workflow_app.py nicht
mit langem Dialog-UI-Code überfrachtet wird. Die WorkflowApp-Instanz wird als
``app`` übergeben, sodass bestehende Zustände, Vorschaubilder und Einstellungen
weiterverwendet werden können.
"""

from __future__ import annotations

# Dialog-Code ist absichtlich ausgelagert, damit die Hauptdatei auf die
# Ablaufsteuerung fokussiert bleibt und Exportfenster separat pflegbar sind.

from pathlib import Path
from typing import Any, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw

import recolor_engine as recolor
import vector_engine as vector
from i18n import tr


def _dialog_muted_fg(app: Any) -> str:
    """Lesbare Infofarbe in Light- und Darkmode."""
    try:
        return "#bcbcbc" if bool(app.dark_mode_var.get()) else "#555555"
    except Exception:
        return "#555555"


def _dialog_text_fg(app: Any) -> str:
    try:
        return "#f3f3f3" if bool(app.dark_mode_var.get()) else "#111827"
    except Exception:
        return "#111827"


def open_scaled_export_dialog(app: Any) -> None:
    self = app
    if self.vector_image_rgb is None:
        messagebox.showwarning(tr("msg.no_intermediate_title"), tr("msg.no_intermediate_step"))
        return
    if not self.detected_contours:
        self.detect_and_preview_vector()
        if not self.detected_contours:
            return
    bbox = self.get_vector_bbox_px()
    if not bbox:
        messagebox.showwarning(tr("msg.no_bbox_title"), tr("msg.no_bbox_body"))
        return

    config = self._load_scale_export_config()
    _x, _y, bbox_w, bbox_h = bbox
    reference_px = max(1.0, bbox_w, bbox_h)
    local_enabled = tk.BooleanVar(value=bool(config.get("enabled", True)))
    local_percent = tk.StringVar(value=f"{self._parse_optional_float(config.get('tolerance_percent', 0.30)):.2f}")
    local_target_w = tk.StringVar(value=str(self.target_width_mm_var.get() or config.get("target_width_mm", "") or ""))
    local_target_h = tk.StringVar(value=str(self.target_height_mm_var.get() or config.get("target_height_mm", "") or ""))
    local_keep_proportions = tk.BooleanVar(value=bool(config.get("keep_proportions", True)))
    local_show_anchors = tk.BooleanVar(value=bool(config.get("show_anchor_points", True)))
    local_anchor_radius = tk.StringVar(value=f"{self._parse_optional_float(config.get('anchor_point_size', 2.50)) or 2.50:.2f}")
    local_live = tk.BooleanVar(value=False)
    simplified_contours: List[Any] = []
    update_after_id: Optional[str] = None
    sync_size_fields = False

    dialog = tk.Toplevel(self)
    dialog.title(tr("step2.scale_export_title"))
    dialog.transient(self)
    dialog.geometry("1120x720")
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(1, weight=1)

    controls = ttk.Frame(dialog, padding=8)
    controls.grid(row=0, column=0, sticky="ew")
    controls.columnconfigure(1, weight=1)

    ttk.Checkbutton(
        controls,
        text=tr("step2.scale_export_enable"),
        variable=local_enabled,
        command=lambda: schedule_update(),
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

    bbox_info_var = tk.StringVar(value="")
    ttk.Label(controls, text=tr("step2.bbox")).grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=(0, 4))
    ttk.Label(controls, textvariable=bbox_info_var, justify="left").grid(row=1, column=1, columnspan=3, sticky="w", pady=(0, 4))
    ttk.Label(
        controls,
        text=tr("step2.scale_default_hint"),
        foreground=_dialog_muted_fg(self),
        wraplength=360,
        justify="left",
    ).grid(row=1, column=4, sticky="w", padx=(18, 0), pady=(0, 4))

    ttk.Label(controls, text=tr("step2.target_width_mm")).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
    ttk.Spinbox(controls, from_=0.0, to=100000.0, increment=0.01, textvariable=local_target_w, width=10, format="%.2f").grid(row=2, column=1, sticky="w", pady=(0, 4))
    ttk.Label(controls, text=tr("step2.target_height_mm")).grid(row=2, column=2, sticky="w", padx=(16, 8), pady=(0, 4))
    ttk.Spinbox(controls, from_=0.0, to=100000.0, increment=0.01, textvariable=local_target_h, width=10, format="%.2f").grid(row=2, column=3, sticky="w", pady=(0, 4))

    ttk.Checkbutton(
        controls,
        text=tr("step2.keep_proportions"),
        variable=local_keep_proportions,
        command=lambda: on_size_changed("width"),
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 4))

    tol_label = ttk.Label(controls, text=tr("step2.scale_export_tolerance_percent"))
    tol_label.grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
    self._add_tooltip(tol_label, "tooltip.step2.scale_export_tolerance_percent")
    tol_scale = ttk.Scale(
        controls,
        from_=0.0,
        to=5.0,
        orient="horizontal",
        command=lambda value: on_percent_changed(value),
    )
    tol_scale.grid(row=4, column=1, sticky="ew", padx=(0, 8), pady=(0, 4))
    tol_spin = ttk.Spinbox(controls, from_=0.0, to=20.0, increment=0.01, textvariable=local_percent, width=8, format="%.2f")
    tol_spin.grid(row=4, column=2, sticky="w", pady=(0, 4))

    ttk.Checkbutton(
        controls,
        text=tr("step2.show_anchor_points"),
        variable=local_show_anchors,
        command=lambda: update_preview(force=True),
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

    ttk.Checkbutton(controls, text=tr("step2.live_preview"), variable=local_live).grid(row=7, column=0, sticky="w", pady=(4, 0))
    refresh_btn = tk.Button(
        controls,
        text=tr("step2.manual_refresh"),
        command=lambda: update_preview(force=True),
        bg="#15803d",
        fg="white",
        activebackground="#166534",
        activeforeground="white",
        relief="flat",
        padx=12,
        pady=4,
    )
    refresh_btn.grid(row=7, column=1, sticky="w", pady=(4, 0))
    info_var = tk.StringVar(value="")
    ttk.Label(controls, textvariable=info_var, foreground=_dialog_muted_fg(self)).grid(row=7, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=(4, 0))

    panes = ttk.Panedwindow(dialog, orient=tk.HORIZONTAL)
    panes.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
    before_canvas = recolor.ZoomImageCanvas(panes, tr("step2.scale_export_before"))
    after_canvas = recolor.ZoomImageCanvas(panes, tr("step2.scale_export_after"))
    panes.add(before_canvas, weight=1)
    panes.add(after_canvas, weight=1)

    buttons = ttk.Frame(dialog, padding=(8, 0, 8, 8))
    buttons.grid(row=2, column=0, sticky="ew")
    buttons.columnconfigure(0, weight=1)

    def compute_pixel_to_mm() -> float:
        target_w = self._parse_optional_float(local_target_w.get())
        target_h = self._parse_optional_float(local_target_h.get())
        if target_w > 0.0:
            return target_w / max(1.0, bbox_w)
        if target_h > 0.0:
            return target_h / max(1.0, bbox_h)
        try:
            return self.get_pixel_to_mm()
        except Exception:
            return 1.0

    def current_percent() -> float:
        return max(0.0, self._parse_optional_float(local_percent.get()))

    def current_epsilon_px() -> float:
        if not local_enabled.get():
            return 0.0
        return reference_px * current_percent() / 100.0

    def current_anchor_radius() -> float:
        try:
            return max(1.0, min(20.0, float(str(local_anchor_radius.get()).replace(",", "."))))
        except Exception:
            return 2.5

    def update_bbox_text() -> None:
        pixel_to_mm = compute_pixel_to_mm()
        if pixel_to_mm <= 0.0:
            pixel_to_mm = 1.0
        width_mm = bbox_w * pixel_to_mm
        height_mm = bbox_h * pixel_to_mm
        bbox_info_var.set("\n".join((
            tr("step2.bbox_px_line", width_px=bbox_w, height_px=bbox_h),
            tr("step2.scale_line", pixel_to_mm=pixel_to_mm),
            tr("step2.export_size_line", width_mm=width_mm, height_mm=height_mm),
        )))

    def draw_anchor_points_for_dialog(image: Image.Image, contours: List[Any]) -> None:
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

    def build_preview_for(contours: List[Any]) -> Image.Image:
        original = self.detected_contours
        original_selected = self.selected_contour_indices
        original_selected_index = self.selected_contour_index
        try:
            self.detected_contours = contours
            self.selected_contour_indices = set()
            self.selected_contour_index = None
            image = self.build_object_check_preview_image()
            self.draw_vector_bbox_overlay(image)
            draw_anchor_points_for_dialog(image, contours)
            return image
        finally:
            self.detected_contours = original
            self.selected_contour_indices = original_selected
            self.selected_contour_index = original_selected_index

    def simplify_for_dialog() -> List[Any]:
        return self._simplify_contours_for_export(self.detected_contours, current_epsilon_px())

    def update_info() -> None:
        update_bbox_text()
        before = sum(len(item.points) for item in self.detected_contours if item.rule.export)
        after = sum(len(item.points) for item in simplified_contours if item.rule.export)
        epsilon_px = current_epsilon_px()
        tolerance_mm = epsilon_px * compute_pixel_to_mm()
        info_var.set(tr("status.scale_export_points", before=before, after=after, px=f"{epsilon_px:.2f}", mm=f"{tolerance_mm:.2f}"))

    def update_preview(force: bool = False) -> None:
        nonlocal simplified_contours, update_after_id
        if update_after_id:
            try:
                dialog.after_cancel(update_after_id)
            except Exception:
                pass
            update_after_id = None
        if not force and not local_live.get():
            return
        simplified_contours = simplify_for_dialog()
        before_canvas.set_image(build_preview_for(self.detected_contours), reset_view=before_canvas.image is None)
        after_canvas.set_image(build_preview_for(simplified_contours), reset_view=after_canvas.image is None)
        update_info()

    def schedule_update() -> None:
        nonlocal update_after_id
        if not local_live.get():
            return
        if update_after_id:
            try:
                dialog.after_cancel(update_after_id)
            except Exception:
                pass
        update_after_id = dialog.after(160, lambda: update_preview(force=True))

    def on_size_changed(source: str) -> None:
        nonlocal sync_size_fields
        if sync_size_fields:
            return
        if local_keep_proportions.get():
            sync_size_fields = True
            try:
                width = self._parse_optional_float(local_target_w.get())
                height = self._parse_optional_float(local_target_h.get())
                if source == "width" and width > 0.0 and bbox_w > 0.0:
                    local_target_h.set(f"{width * bbox_h / bbox_w:.2f}")
                elif source == "height" and height > 0.0 and bbox_h > 0.0:
                    local_target_w.set(f"{height * bbox_w / bbox_h:.2f}")
            finally:
                sync_size_fields = False
        update_bbox_text()
        schedule_update()

    def on_percent_changed(value: object) -> None:
        self._set_numeric_var(local_percent, str(value), 2)
        schedule_update()

    def on_anchor_radius_changed(value: object) -> None:
        self._set_numeric_var(local_anchor_radius, str(value), 2)
        update_preview(force=True)

    def on_spin_changed(_event: object = None) -> None:
        update_preview(force=True)

    def reset_dialog_values() -> None:
        default = self._default_scale_export_config()
        local_enabled.set(bool(default["enabled"]))
        local_percent.set(f"{float(default['tolerance_percent']):.2f}")
        local_target_w.set("")
        local_target_h.set("")
        local_keep_proportions.set(bool(default["keep_proportions"]))
        local_show_anchors.set(bool(default["show_anchor_points"]))
        local_anchor_radius.set(f"{float(default['anchor_point_size']):.2f}")
        local_live.set(bool(default["live_preview"]))
        tol_scale.set(float(default["tolerance_percent"]))
        anchor_size_scale.set(float(default["anchor_point_size"]))
        update_preview(force=True)

    def save_dialog_config() -> None:
        self._save_scale_export_config({
            "enabled": bool(local_enabled.get()),
            "tolerance_percent": current_percent(),
            "target_width_mm": local_target_w.get().strip(),
            "target_height_mm": local_target_h.get().strip(),
            "keep_proportions": bool(local_keep_proportions.get()),
            "show_anchor_points": bool(local_show_anchors.get()),
            "anchor_point_size": current_anchor_radius(),
            "live_preview": bool(local_live.get()),
        })

    def export_scaled() -> None:
        nonlocal simplified_contours
        save_dialog_config()
        if not simplified_contours:
            simplified_contours = simplify_for_dialog()
        pixel_to_mm = compute_pixel_to_mm()
        self.pixel_to_mm_var.set(f"{pixel_to_mm:.8f}")
        self.target_width_mm_var.set(local_target_w.get().strip())
        self.target_height_mm_var.set(local_target_h.get().strip())
        self.update_vector_bbox_info()
        out = self.output_path_var.get().strip()
        if not out:
            self.choose_vector_output()
            out = self.output_path_var.get().strip()
        if not out:
            return
        try:
            self._export_contours_to_file(out, simplified_contours, pixel_to_mm)
            dialog.destroy()
        except Exception as exc:
            self.set_progress(0, tr("progress.detect_error"))
            messagebox.showerror(tr("msg.export_error"), str(exc))

    def open_stl_from_scaled() -> None:
        nonlocal simplified_contours
        save_dialog_config()
        if not simplified_contours:
            simplified_contours = simplify_for_dialog()
        pixel_to_mm = compute_pixel_to_mm()
        self.pixel_to_mm_var.set(f"{pixel_to_mm:.8f}")
        self.target_width_mm_var.set(local_target_w.get().strip())
        self.target_height_mm_var.set(local_target_h.get().strip())
        self.update_vector_bbox_info()
        self.open_stl_export_dialog(
            simplified_contours,
            pixel_to_mm,
            parent=dialog,
            preview_builder=build_preview_for,
        )

    tol_spin.bind("<Return>", on_spin_changed)
    tol_spin.bind("<FocusOut>", on_spin_changed)
    anchor_size_spin.bind("<Return>", lambda _event: update_preview(force=True))
    anchor_size_spin.bind("<FocusOut>", lambda _event: update_preview(force=True))
    try:
        local_target_w.trace_add("write", lambda *_: on_size_changed("width"))
        local_target_h.trace_add("write", lambda *_: on_size_changed("height"))
    except Exception:
        pass
    try:
        tol_scale.set(min(5.0, current_percent()))
    except Exception:
        tol_scale.set(0.30)
    anchor_size_scale.set(current_anchor_radius())
    ttk.Button(buttons, text=tr("button.reset"), command=reset_dialog_values).grid(row=0, column=0, sticky="w")
    ttk.Button(buttons, text=tr("button.cancel"), command=dialog.destroy).grid(row=0, column=1, sticky="e", padx=(8, 0))
    tk.Button(
        buttons,
        text=tr("step2.export_stl"),
        command=open_stl_from_scaled,
        bg="#7c3aed",
        fg="white",
        activebackground="#6d28d9",
        activeforeground="white",
        relief="flat",
        padx=14,
        pady=5,
    ).grid(row=0, column=2, sticky="e", padx=(8, 0))
    tk.Button(
        buttons,
        text=tr("nav.scale_export"),
        command=export_scaled,
        bg="#15803d",
        fg="white",
        activebackground="#166534",
        activeforeground="white",
        relief="flat",
        padx=14,
        pady=5,
    ).grid(row=0, column=3, sticky="e", padx=(8, 0))
    update_preview(force=True)




def open_stl_export_dialog(
    app: Any,
    contours: List[Any],
    pixel_to_mm: float,
    parent: Optional[tk.Widget] = None,
    preview_builder: Optional[Any] = None,
) -> None:
    self = app
    if self.vector_image_rgb is None:
        messagebox.showwarning(tr("msg.no_intermediate_title"), tr("msg.no_intermediate_step"))
        return

    image_h, image_w = self.vector_image_rgb.shape[:2]

    def _export_rule() -> Any:
        for item in contours:
            rule = getattr(item, "rule", None)
            if rule is not None and getattr(rule, "export", True):
                return rule
        return vector.ColorRule("STL", (0, 0, 255), 255, "STL", True, 1, 0.5)

    def _build_stl_selection_contours() -> List[Any]:
        """Erzeugt echte anklickbare STL-Flächen aus der aktuellen Exportmaske.

        Wichtig: Für die STL-Auswahl werden nicht nur die sichtbaren Kontur-Objekte
        verwendet, sondern zuerst die aktuelle Exportmaske gerendert und daraus
        Außenflächen + Innenlöcher erneut erkannt. Dadurch lassen sich Löcher und
        getrennte Inseln gezielt anwählen, auch wenn die ursprüngliche Konturliste
        nach der Vereinfachung nur schwer anklickbar ist.
        """
        mask = vector.np.zeros((image_h, image_w), dtype=vector.np.uint8)
        exportable = []
        for item in contours:
            if not getattr(getattr(item, "rule", None), "export", True):
                continue
            if not bool(getattr(item, "closed", False)):
                continue
            pts_raw = getattr(item, "points", []) or []
            if len(pts_raw) < 3:
                continue
            pts = vector.np.array(
                [[int(round(float(x))), int(round(float(y)))] for x, y in pts_raw],
                dtype=vector.np.int32,
            )
            if len(pts) < 3:
                continue
            exportable.append(item)
            fill_value = 0 if bool(getattr(item, "is_hole", False)) else 255
            try:
                vector.cv2.fillPoly(mask, [pts], int(fill_value))
            except Exception:
                pass

        if not exportable or int(mask.max()) <= 0:
            return []

        try:
            found, hierarchy = vector.cv2.findContours(mask, vector.cv2.RETR_CCOMP, vector.cv2.CHAIN_APPROX_NONE)
        except Exception:
            return []

        hierarchy_view = hierarchy[0] if hierarchy is not None and len(hierarchy) > 0 else None
        rule = _export_rule()
        result: List[Any] = []
        for contour_index, contour_cv in enumerate(found):
            if contour_cv is None or len(contour_cv) < 3:
                continue
            parent_index = -1
            if hierarchy_view is not None and contour_index < len(hierarchy_view):
                parent_index = int(hierarchy_view[contour_index][3])
            is_hole = parent_index != -1
            area = abs(float(vector.cv2.contourArea(contour_cv)))
            if area < 1.0:
                continue
            try:
                approx = vector.cv2.approxPolyDP(contour_cv, 0.75, True)
                pts_arr = approx.reshape(-1, 2)
            except Exception:
                pts_arr = contour_cv.reshape(-1, 2)
            points = [(float(x), float(y)) for x, y in pts_arr]
            if len(points) < 3:
                continue
            result.append(vector.DetectedContour(
                rule=rule,
                points=points,
                area=area,
                closed=True,
                is_hole=is_hole,
                raw_points=list(points),
            ))
        return result

    stl_contours = _build_stl_selection_contours()
    solid_indices = [
        index for index, item in enumerate(stl_contours)
        if getattr(item.rule, "export", True)
        and bool(getattr(item, "closed", False))
        and not bool(getattr(item, "is_hole", False))
        and len(getattr(item, "points", []) or []) >= 3
    ]
    hole_indices = [
        index for index, item in enumerate(stl_contours)
        if getattr(item.rule, "export", True)
        and bool(getattr(item, "closed", False))
        and bool(getattr(item, "is_hole", False))
        and len(getattr(item, "points", []) or []) >= 3
    ]
    if not solid_indices:
        messagebox.showwarning(tr("msg.stl_no_surfaces_title"), tr("msg.stl_no_surfaces_body"))
        return

    # Klare Semantik:
    # - selected_solids = Flächen, die wirklich extrudiert werden.
    # - cutout_holes = Innenlöcher, die AUSGESPART werden, also gerade NICHT extrudiert werden.
    selected_solids = set(solid_indices)
    cutout_holes = set(hole_indices)
    extrusion_var = tk.StringVar(value="2.00")
    info_var = tk.StringVar(value="")
    use_holes_as_cutout_var = tk.BooleanVar(value=True)
    press_pos: list[Optional[Tuple[int, int]]] = [None]

    dialog = tk.Toplevel(parent or self)
    dialog.title(tr("step2.stl_export_title"))
    dialog.transient(parent or self)
    dialog.geometry("1040x740")
    dialog.minsize(780, 540)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(1, weight=1)

    controls = ttk.Frame(dialog, padding=8)
    controls.grid(row=0, column=0, sticky="ew")
    controls.columnconfigure(8, weight=1)

    ttk.Label(controls, text=tr("step2.stl_extrusion_mm")).grid(row=0, column=0, sticky="w", padx=(0, 6))
    extrusion_spin = ttk.Spinbox(
        controls,
        from_=0.1,
        to=1000.0,
        increment=0.1,
        textvariable=extrusion_var,
        width=9,
        format="%.2f",
    )
    extrusion_spin.grid(row=0, column=1, sticky="w", padx=(0, 12))

    ttk.Button(controls, text=tr("step2.stl_select_all"), command=lambda: select_all()).grid(row=0, column=2, sticky="w", padx=(0, 6))
    ttk.Button(controls, text=tr("step2.stl_select_none"), command=lambda: select_none()).grid(row=0, column=3, sticky="w", padx=(0, 6))
    ttk.Button(controls, text=tr("step2.stl_holes_all_cutout"), command=lambda: holes_all_cutout()).grid(row=0, column=4, sticky="w", padx=(0, 6))
    ttk.Button(controls, text=tr("step2.stl_holes_none_cutout"), command=lambda: holes_none_cutout()).grid(row=0, column=5, sticky="w", padx=(0, 12))
    ttk.Label(controls, textvariable=info_var, foreground=_dialog_muted_fg(self)).grid(row=0, column=6, columnspan=3, sticky="w")

    cutout_options = ttk.Frame(dialog, padding=(8, 0, 8, 2))
    cutout_options.grid(row=2, column=0, sticky="ew")
    ttk.Checkbutton(
        cutout_options,
        text=tr("step2.stl_use_holes_as_cutout"),
        variable=use_holes_as_cutout_var,
        command=lambda: update_preview(),
    ).pack(side="left")
    ttk.Label(
        cutout_options,
        text=tr("step2.stl_preview_note"),
        foreground=_dialog_muted_fg(self),
        wraplength=620,
        justify="left",
    ).pack(side="left", padx=(18, 0))

    hint = ttk.Label(dialog, text=tr("step2.stl_select_hint"), foreground=_dialog_muted_fg(self), padding=(8, 0, 8, 2), wraplength=980)
    hint.grid(row=3, column=0, sticky="ew")
    legend = ttk.Label(dialog, text=tr("step2.stl_selection_legend"), foreground=_dialog_text_fg(self), padding=(8, 0, 8, 6), wraplength=980)
    legend.grid(row=4, column=0, sticky="ew")

    stl_canvas = recolor.ZoomImageCanvas(dialog, tr("step2.stl_preview"))
    stl_canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    buttons = ttk.Frame(dialog, padding=(8, 0, 8, 8))
    buttons.grid(row=5, column=0, sticky="ew")
    buttons.columnconfigure(0, weight=1)
    ttk.Button(buttons, text=tr("button.cancel"), command=dialog.destroy).grid(row=0, column=1, sticky="e", padx=(8, 0))
    tk.Button(
        buttons,
        text=tr("step2.stl_save_button"),
        command=lambda: export_selected_stl(),
        bg="#7c3aed",
        fg="white",
        activebackground="#6d28d9",
        activeforeground="white",
        relief="flat",
        padx=14,
        pady=5,
    ).grid(row=0, column=2, sticky="e", padx=(8, 0))

    def parse_extrusion() -> float:
        try:
            value = float(str(extrusion_var.get()).replace(",", "."))
        except Exception as exc:
            raise ValueError(tr("msg.stl_invalid_extrusion")) from exc
        if value <= 0.0:
            raise ValueError(tr("msg.stl_invalid_extrusion"))
        return value

    def build_base_preview() -> Image.Image:
        if preview_builder is not None:
            try:
                return preview_builder(contours).convert("RGB")
            except Exception:
                pass
        original = self.detected_contours
        original_selected = self.selected_contour_indices
        original_selected_index = self.selected_contour_index
        try:
            self.detected_contours = list(contours)
            self.selected_contour_indices = set()
            self.selected_contour_index = None
            image = self.build_object_check_preview_image()
            self.draw_vector_bbox_overlay(image)
            return image.convert("RGB")
        finally:
            self.detected_contours = original
            self.selected_contour_indices = original_selected
            self.selected_contour_index = original_selected_index

    def _contour_points(index: int) -> list[Tuple[float, float]]:
        item = stl_contours[index]
        return [(float(x), float(y)) for x, y in getattr(item, "points", []) or []]

    def _draw_polygon_lines(
        draw: ImageDraw.ImageDraw,
        pts: list[Tuple[float, float]],
        fill: tuple[int, int, int, int],
        width: int,
        inner_fill: Optional[tuple[int, int, int, int]] = None,
        inner_width: int = 1,
    ) -> None:
        if len(pts) < 3:
            return
        closed_pts = pts + [pts[0]]
        draw.line(closed_pts, fill=fill, width=width, joint="curve")
        if inner_fill is not None and inner_width > 0:
            draw.line(closed_pts, fill=inner_fill, width=inner_width, joint="curve")

    def _draw_hole_marker(draw: ImageDraw.ImageDraw, pts: list[Tuple[float, float]], active: bool) -> None:
        if len(pts) < 3:
            return
        xs = [x for x, _y in pts]
        ys = [y for _x, y in pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        cx = (min_x + max_x) * 0.5
        cy = (min_y + max_y) * 0.5
        size = max(10.0, min(max_x - min_x, max_y - min_y) * 0.42)
        color = (255, 0, 0, 255) if active else (255, 165, 0, 255)
        outline = (255, 255, 255, 245)
        draw.line((cx - size, cy - size, cx + size, cy + size), fill=outline, width=10)
        draw.line((cx - size, cy + size, cx + size, cy - size), fill=outline, width=10)
        draw.line((cx - size, cy - size, cx + size, cy + size), fill=color, width=5)
        draw.line((cx - size, cy + size, cx + size, cy - size), fill=color, width=5)

    def effective_cutout_holes() -> set[int]:
        if not bool(use_holes_as_cutout_var.get()):
            return set()
        return set(cutout_holes)

    def build_stl_preview() -> Image.Image:
        image = build_base_preview().convert("RGBA")
        active_cutout_holes = effective_cutout_holes()

        # 1) Gewählte Außenflächen = werden extrudiert.
        solid_selected_mask = Image.new("L", image.size, 0)
        solid_off_mask = Image.new("L", image.size, 0)
        solid_selected_draw = ImageDraw.Draw(solid_selected_mask)
        solid_off_draw = ImageDraw.Draw(solid_off_mask)
        for index in solid_indices:
            pts = _contour_points(index)
            if len(pts) < 3:
                continue
            if index in selected_solids:
                solid_selected_draw.polygon(pts, fill=115)
            else:
                solid_off_draw.polygon(pts, fill=120)

        selected_overlay = Image.new("RGBA", image.size, (124, 58, 237, 0))
        selected_overlay.putalpha(solid_selected_mask)
        result = Image.alpha_composite(image, selected_overlay)
        off_overlay = Image.new("RGBA", image.size, (107, 114, 128, 0))
        off_overlay.putalpha(solid_off_mask)
        result = Image.alpha_composite(result, off_overlay)

        # 2) Aktive Löcher = Aussparung, also nicht extrudieren.
        cutout_mask = Image.new("L", image.size, 0)
        fill_hole_mask = Image.new("L", image.size, 0)
        cutout_draw = ImageDraw.Draw(cutout_mask)
        fill_hole_draw = ImageDraw.Draw(fill_hole_mask)
        for index in hole_indices:
            pts = _contour_points(index)
            if len(pts) < 3:
                continue
            if index in active_cutout_holes:
                cutout_draw.polygon(pts, fill=210)
            else:
                fill_hole_draw.polygon(pts, fill=190)

        cutout_overlay = Image.new("RGBA", image.size, (255, 0, 0, 0))
        cutout_overlay.putalpha(cutout_mask)
        result = Image.alpha_composite(result, cutout_overlay)
        filled_hole_overlay = Image.new("RGBA", image.size, (255, 165, 0, 0))
        filled_hole_overlay.putalpha(fill_hole_mask)
        result = Image.alpha_composite(result, filled_hole_overlay)

        draw = ImageDraw.Draw(result)
        for index in solid_indices:
            pts = _contour_points(index)
            if len(pts) < 3:
                continue
            if index in selected_solids:
                _draw_polygon_lines(draw, pts, (124, 58, 237, 255), 7, (255, 255, 255, 245), 2)
            else:
                _draw_polygon_lines(draw, pts, (75, 85, 99, 250), 6, (255, 255, 255, 230), 2)

        for index in hole_indices:
            pts = _contour_points(index)
            if len(pts) < 3:
                continue
            if index in active_cutout_holes:
                _draw_polygon_lines(draw, pts, (255, 0, 0, 255), 12, (255, 255, 255, 255), 4)
                _draw_hole_marker(draw, pts, active=True)
            else:
                _draw_polygon_lines(draw, pts, (255, 165, 0, 255), 12, (255, 255, 255, 255), 4)
                _draw_hole_marker(draw, pts, active=False)

        return result.convert("RGB")

    def update_info() -> None:
        info_var.set(tr(
            "status.stl_selected_surfaces_holes",
            selected=len(selected_solids),
            total=len(solid_indices),
            holes=len(effective_cutout_holes()),
            total_holes=len(hole_indices),
        ))

    def update_preview(reset: bool = False) -> None:
        stl_canvas.set_image(build_stl_preview(), reset_view=reset or stl_canvas.image is None)
        update_info()

    def select_all() -> None:
        selected_solids.clear()
        selected_solids.update(solid_indices)
        cutout_holes.clear()
        cutout_holes.update(hole_indices)
        update_preview()

    def select_none() -> None:
        selected_solids.clear()
        cutout_holes.clear()
        update_preview()

    def holes_all_cutout() -> None:
        cutout_holes.clear()
        cutout_holes.update(hole_indices)
        update_preview()

    def holes_none_cutout() -> None:
        cutout_holes.clear()
        update_preview()

    def canvas_to_stl_point(canvas_x: int, canvas_y: int) -> Optional[Tuple[float, float]]:
        if stl_canvas.image is None:
            return None
        zoom = float(getattr(stl_canvas, "zoom", 1.0) or 1.0)
        offset_x = float(getattr(stl_canvas, "offset_x", 0.0))
        offset_y = float(getattr(stl_canvas, "offset_y", 0.0))
        x = (float(canvas_x) - offset_x) / max(0.0001, zoom)
        y = (float(canvas_y) - offset_y) / max(0.0001, zoom)
        if x < 0 or y < 0 or x >= stl_canvas.image.width or y >= stl_canvas.image.height:
            return None
        return x, y

    def _point_polygon_signed_distance(index: int, x: float, y: float) -> Optional[Tuple[float, float]]:
        pts = _contour_points(index)
        if len(pts) < 3:
            return None
        try:
            poly = vector.np.array(pts, dtype=vector.np.float32).reshape(-1, 1, 2)
            signed_distance = float(vector.cv2.pointPolygonTest(poly, (float(x), float(y)), True))
        except Exception:
            return None
        try:
            area = abs(float(vector.polygon_area(pts)))
        except Exception:
            area = 0.0
        return signed_distance, max(0.0, area)

    def find_stl_hit_at(canvas_x: int, canvas_y: int) -> Optional[Tuple[str, int]]:
        point = canvas_to_stl_point(canvas_x, canvas_y)
        if point is None:
            return None
        x, y = point
        zoom = float(getattr(stl_canvas, "zoom", 1.0) or 1.0)
        hit_distance_px = max(8.0, 18.0 / max(0.15, zoom))

        # Löcher zuerst: Klick im Loch soll nicht die große Außenfläche treffen.
        best_hole: Optional[Tuple[float, float, int]] = None
        for index in hole_indices:
            result = _point_polygon_signed_distance(index, x, y)
            if result is None:
                continue
            signed_distance, area = result
            if signed_distance >= -hit_distance_px:
                priority = 0.0 if signed_distance >= 0.0 else abs(signed_distance)
                candidate = (priority, area if area > 0 else 1e18, index)
                if best_hole is None or candidate < best_hole:
                    best_hole = candidate
        if best_hole is not None:
            return "hole", best_hole[2]

        best_solid_inside: Optional[Tuple[float, int]] = None
        best_solid_near: Optional[Tuple[float, int]] = None
        for index in solid_indices:
            result = _point_polygon_signed_distance(index, x, y)
            if result is None:
                continue
            signed_distance, area = result
            if signed_distance >= 0.0:
                candidate = (area if area > 0 else 1e18, index)
                if best_solid_inside is None or candidate < best_solid_inside:
                    best_solid_inside = candidate
            elif abs(signed_distance) <= hit_distance_px:
                candidate = (abs(signed_distance), index)
                if best_solid_near is None or candidate < best_solid_near:
                    best_solid_near = candidate
        if best_solid_inside is not None:
            return "solid", best_solid_inside[1]
        if best_solid_near is not None:
            return "solid", best_solid_near[1]
        return None

    def on_stl_press(event: tk.Event) -> None:
        press_pos[0] = (int(event.x), int(event.y))

    def on_stl_release(event: tk.Event) -> None:
        if press_pos[0] is None:
            return
        sx, sy = press_pos[0]
        press_pos[0] = None
        if abs(int(event.x) - sx) > 4 or abs(int(event.y) - sy) > 4:
            return
        hit = find_stl_hit_at(int(event.x), int(event.y))
        if hit is None:
            return
        kind, index = hit
        if kind == "hole":
            if not bool(use_holes_as_cutout_var.get()):
                use_holes_as_cutout_var.set(True)
            if index in cutout_holes:
                cutout_holes.remove(index)
            else:
                cutout_holes.add(index)
        else:
            if index in selected_solids:
                selected_solids.remove(index)
            else:
                selected_solids.add(index)
        update_preview()

    def default_stl_path() -> str:
        raw_output = self.output_path_var.get().strip()
        if raw_output:
            return str(Path(raw_output).with_suffix(".stl"))
        if self.current_path is not None:
            return str(Path(self.current_path).with_suffix(".stl"))
        return "vektorrazor_export.stl"

    def export_selected_stl() -> None:
        if not selected_solids:
            messagebox.showwarning(tr("msg.stl_no_selection_title"), tr("msg.stl_no_selection_body"), parent=dialog)
            return
        try:
            extrusion_mm = parse_extrusion()
        except Exception as exc:
            messagebox.showerror(tr("msg.export_error"), str(exc), parent=dialog)
            return
        default_path = Path(default_stl_path())
        save_kwargs = {
            "parent": dialog,
            "title": tr("step2.stl_save_dialog_title"),
            "defaultextension": ".stl",
            "filetypes": [("STL", "*.stl")],
            "initialfile": default_path.name,
        }
        if default_path.parent.exists():
            save_kwargs["initialdir"] = str(default_path.parent)
        out = filedialog.asksaveasfilename(**save_kwargs)
        if not out:
            return
        try:
            export_indices = set(selected_solids) | effective_cutout_holes()
            facet_count = vector.export_stl_extruded(
                out,
                (image_w, image_h),
                list(stl_contours),
                pixel_to_mm,
                extrusion_mm,
                selected_indices=export_indices,
                invert_y=True,
            )
            self.status_var.set(tr("status.stl_export_done", facets=facet_count, out=out))
            messagebox.showinfo(
                tr("msg.export_done_title"),
                tr(
                    "msg.stl_export_done",
                    out=out,
                    surfaces=len(selected_solids),
                    extrusion=extrusion_mm,
                    facets=facet_count,
                ),
                parent=dialog,
            )
            dialog.destroy()
        except Exception as exc:
            self.set_progress(0, tr("progress.detect_error"))
            messagebox.showerror(tr("msg.export_error"), str(exc), parent=dialog)

    stl_canvas.canvas.bind("<ButtonPress-1>", on_stl_press, add="+")
    stl_canvas.canvas.bind("<ButtonRelease-1>", on_stl_release, add="+")
    extrusion_spin.bind("<Return>", lambda _event: update_info())
    extrusion_spin.bind("<FocusOut>", lambda _event: update_info())
    update_preview(reset=True)
