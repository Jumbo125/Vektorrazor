# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


FALLBACK_LANGUAGE = "de"
_current_language = FALLBACK_LANGUAGE
_languages: dict[str, dict[str, str]] = {}
_language_names: dict[str, str] = {}
_missing_keys: dict[str, list[str]] = {}
_last_status_message = ""


FALLBACK_DE: dict[str, str] = {
    "app.title": "Vektorrazor - PNG Logo zu CAD-tauglichen Vektordaten",
    "app.header": "PNG-Logo -> CAD-nahe Vektordaten",
    "language.fallback_name": "Deutsch (Fallback)",
    "language.incomplete": "Sprachdatei unvollstaendig, Fallback fuer fehlende Texte verwendet.",
    "nav.back": "<- Zurueck",
    "nav.next": "Weiter ->",
    "nav.next_vectorize": "Weiter zur Vektorisierung ->",
    "nav.back_to_step1": "<- Zurueck zu Schritt 1",
    "nav.export": "Export DXF / SVG ->",
    "step1.label": "Schritt 1 von 2: Bild bearbeiten / Farben exakt vorbereiten",
    "step2.label": "Schritt 2 von 2: Vektorisieren / DXF oder SVG exportieren",
    "status.ready": "Bereit",
    "status.no_intermediate": "Noch kein Zwischenbild uebernommen",
    "status.language_changed": "Sprache geaendert.",
    "step1.input_image": "Input-Bild:",
    "step1.load_image": "Bild laden",
    "step1.save_png": "PNG speichern",
    "step1.actions": "Workflow / Abschluss Schritt 1",
    "step1.update_intermediate": "Zwischenbild nur aktualisieren",
    "step1.update_hint": "Hinweis: 'Weiter zur Vektorisierung' uebernimmt das bearbeitete Bild automatisch. Der Aktualisieren-Button ist nur optional.",
    "step1.tab_basic": "Basis: Farben reduzieren",
    "step1.tab_manual": "Erweitert: manuell",
    "step1.tab_logo": "Logo-Maske",
    "step1.prep": "1) Bildvorbereitung",
    "step1.brightness": "Helligkeit",
    "step1.contrast": "Kontrast",
    "step1.black_point": "Schwarzpunkt",
    "step1.white_point": "Weisspunkt",
    "step1.gamma": "Gamma",
    "step1.reset": "Zuruecksetzen",
    "step1.prep_detect": "Vorbereitung + Farben neu erkennen",
    "step1.detect": "2) Automatische Farberkennung",
    "step1.threshold": "Schwelle",
    "step1.min_area": "Min. Flaeche",
    "step1.max_colors": "Max. Farben",
    "step1.alpha_from": "Alpha ab",
    "step1.detect_colors": "Farben erkennen",
    "step1.reassign": "Kontrastfarben neu",
    "step1.basic_hint": "Tipp: Schritt 1 schreibt exakte RGB-Farben ins Zwischen-PNG. Diese RGB-Werte werden in Schritt 2 automatisch als Layer-Regeln uebernommen.",
    "step1.detected_ranges": "3) Erkannte Farbbereiche",
    "step1.rows_header": "Aktiv  Quelle / Anteil  -> Ziel-RGB",
    "step1.add_mapping": "+ Farbumsetzung",
    "step1.delete_selected": "- selektierte loeschen",
    "step1.manual_status": "Kurzer Klick ins Originalbild uebernimmt Farbe in die selektierte Zeile. Ziehen verschiebt die Vorschau.",
    "step1.manual_mappings": "Manuelle Farbumsetzungen",
    "step1.logo_hint": "Fuer graue Logos, Schatten oder Verlaeufe: Maske ueber lokalen Kontrast erzeugen.",
    "step1.logo_threshold": "Logo-Schwelle",
    "step1.logo_threshold_hint": "hoeher = weniger wird schwarz",
    "step1.logo_radius": "Hintergrund-Radius",
    "step1.logo_radius_hint": "groesser = Schatten/Verlaeufe werden eher ignoriert",
    "step1.logo_rgb": "Logo RGB",
    "step1.background_rgb": "Hintergrund RGB",
    "step1.clean_pixels": "kleine Pixelstoerungen glaetten",
    "step1.create_mask": "Logo-Maske erzeugen",
    "step1.clear_mask": "Maske entfernen / normale Vorschau",
    "step2.source": "Zwischenbild:",
    "step2.load_png": "PNG direkt laden",
    "step2.output": "Output:",
    "step2.save_as": "Speichern als",
    "step2.pixel_to_mm": "Pixel zu mm:",
    "step2.compatibility": "Kompatibilitaet:",
    "step2.dxf_format": "DXF-Format:",
    "step2.actions": "Abschluss / Aktionen",
    "step2.auto": "1  Optional: Auto-Werte testen",
    "step2.detect_preview": "2  Erkennen / Vorschau",
    "step2.export": "3  Export DXF / SVG",
    "step2.actions_hint": "Auto-Werte ist optional und rechnet selbst eine Vorschau. Danach Vorschau pruefen oder direkt exportieren.",
    "step2.colors_layer": "Farben / Layer",
    "step2.edit_colors": "Farben / Layer bearbeiten",
    "step2.detect_colors_from_image": "Farben aus Bild erkennen",
    "step2.dynamic_table": "Dynamische Farbtabelle",
    "step2.add_color": "+ Farbe",
    "step2.profile": "Profil:",
    "step2.apply": "Anwenden",
    "step2.options": "Vektor-Optionen",
    "step2.vector_type": "Vektorart",
    "step2.merge_lines": "Linien zusammenfuehren px",
    "step2.closed_only": "Nur geschlossene Pfade",
    "step2.fill_svg": "SVG-Flaechen fuellen (Export)",
    "step2.group_connected_paths": "Zusammenhaengende Pfade gruppieren (SVG)",
    "step2.force_color_layers": "Export-Layer pro Farbe",
    "step2.object_layers_dxf": "Objekte in Layer erstellen (DXF)",
    "step2.bezier_svg": "Bezier fuer SVG",
    "step2.dedupe": "Doppelte Linien entfernen (CAD)",
    "step2.dedupe_tolerance": "Doppellinien-Toleranz px",
    "step2.preview_mode": "Vorschau-Modus",
    "step2.loose_points": "Lose Ankerpunkte entfernen",
    "step2.smooth": "Rundungen glaetten",
    "step2.global_epsilon": "Punktreduktion / Epsilon px",
    "step2.apply_all_colors": "Auf alle Farben anwenden",
    "step2.preprocess_enabled": "Vorverarbeitung aktiv",
    "step2.preprocess_blur": "Weichzeichnen / Blur",
    "step2.preprocess_edges": "Kanten beruhigen",
    "step2.preprocess_noise": "Mindeststoerung px",
    "step2.internal_scale": "Interne Skalierung",
    "step2.refresh_preview": "Vorschau aktualisieren",
    "step2.smart_smoothing": "Smart CAD Smoothing",
    "step2.smart_corner_angle": "Ecken schuetzen Grad",
    "step2.smart_line_tolerance": "Gerade Linien Toleranz px",
    "step2.smart_curve_strength": "Kurven-Glaettung",
    "step2.delete_small": "Kleine Objekte loeschen",
    "step2.percent_area": "% Bildflaeche",
    "step2.path_selection": "Pfad-Auswahl",
    "step2.selection_mode": "Auswahl-Modus",
    "step2.remove_selected_paths": "Ausgewaehlte Pfade entfernen",
    "step2.clear_selection": "Auswahl aufheben",
    "step2.selection_help": "Auswahl-Modus EIN: Klick = Pfad waehlen, STRG+Klick = hinzufuegen/umschalten, ALT+Klick = direkt entfernen. Auswahl-Modus AUS: Klick/Ziehen verschiebt die Vorschau; nur STRG+Klick waehlt temporaer.",
    "canvas.original": "Original",
    "canvas.edited": "Bearbeitet / technische Zwischenstufe",
    "canvas.step2_original": "Zwischen-PNG",
    "canvas.vector_preview": "Vektor-Vorschau",
    "button.choose": "waehlen",
    "button.close": "Schliessen",
    "label.tolerance_short": "Tol.",
    "vector_mode.area": "Flaechenkontur",
    "vector_mode.centerline": "Mittellinie / Gravur",
    "preview_mode.object": "Objektcheck",
    "preview_mode.contour": "Konturlinien",
    "preview_mode.mask": "Farbmaske",
    "cleanup.off": "Aus",
    "cleanup.mm2": "mm2",
    "cleanup.percent": "% Bildflaeche",
    "internal_scale.1x": "1x",
    "internal_scale.2x": "2x",
    "internal_scale.3x": "3x",
    "dxf.compat.default": "Illustrator / CorelDRAW (empfohlen)",
    "dxf.compat.illustrator": "Adobe Illustrator",
    "dxf.compat.coreldraw": "CorelDRAW",
    "dxf.compat.coreldraw_modern": "CorelDRAW modern",
    "dxf.compat.autocad": "AutoCAD / CAD modern",
    "dxf.compat.freecad": "FreeCAD / LibreCAD / CAM",
    "dxf.compat.manual": "Manuell",
    "msg.error": "Fehler",
    "msg.load_error": "Fehler beim Laden",
    "msg.export_error": "Exportfehler",
    "msg.no_image_title": "Kein Bild",
    "msg.no_image_load": "Bitte zuerst ein Bild laden.",
    "msg.no_image_edit": "Bitte zuerst ein Bild bearbeiten.",
    "msg.no_intermediate_title": "Kein Zwischenbild",
    "msg.no_intermediate_step": "Bitte zuerst Schritt 1 uebernehmen oder ein PNG direkt laden.",
    "msg.accepted_title": "Uebernommen",
    "msg.accepted": "Das bearbeitete Bild wurde fuer Schritt 2 uebernommen.",
    "msg.export_done_title": "Export fertig",
}


def _source_dir() -> Path:
    return Path(__file__).resolve().parent


def _external_lang_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "lang")
    dirs.append(_source_dir() / "lang")
    return dirs


def validate_language_file(language_dict: dict[str, Any], fallback_dict: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    clean = {str(k): str(v) for k, v in language_dict.items() if isinstance(k, str) and isinstance(v, str)}
    missing = sorted(k for k in fallback_dict if k not in clean)
    merged = dict(fallback_dict)
    merged.update(clean)
    return merged, missing


def load_languages() -> None:
    global _languages, _language_names, _missing_keys, _current_language, _last_status_message
    _languages = {}
    _language_names = {}
    _missing_keys = {}
    _last_status_message = ""

    found_any = False
    for lang_dir in _external_lang_dirs():
        if not lang_dir.is_dir():
            continue
        for code in ("de", "en"):
            path = lang_dir / f"lang_{code}.json"
            if not path.is_file():
                continue
            found_any = True
            try:
                with path.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                if not isinstance(raw, dict):
                    raise ValueError("language root must be an object")
                merged, missing = validate_language_file(raw, FALLBACK_DE)
                _languages[code] = merged
                _language_names[code] = merged.get("language.name", code)
                if missing:
                    _missing_keys[code] = missing
                    _last_status_message = FALLBACK_DE["language.incomplete"]
                    print(f"{path}: missing translation keys: {', '.join(missing)}")
            except Exception as exc:
                print(f"{path}: could not load language file: {exc}")
        if found_any:
            break

    if not _languages:
        _languages[FALLBACK_LANGUAGE] = dict(FALLBACK_DE)
        _language_names[FALLBACK_LANGUAGE] = FALLBACK_DE["language.fallback_name"]

    if _current_language not in _languages:
        _current_language = FALLBACK_LANGUAGE if FALLBACK_LANGUAGE in _languages else next(iter(_languages))


def available_languages() -> list[tuple[str, str]]:
    if not _languages:
        load_languages()
    return [(code, _language_names.get(code, code)) for code in _languages]


def set_language(code: str) -> bool:
    global _current_language
    if not _languages:
        load_languages()
    if code not in _languages:
        return False
    _current_language = code
    return True


def current_language() -> str:
    if not _languages:
        load_languages()
    return _current_language


def language_status_message() -> str:
    return _last_status_message


def tr(key: str, default: str | None = None, **kwargs: Any) -> str:
    if not _languages:
        load_languages()
    value = _languages.get(_current_language, {}).get(key)
    if value is None:
        value = FALLBACK_DE.get(key, default if default is not None else key)
    try:
        return value.format(**kwargs)
    except Exception:
        return value
