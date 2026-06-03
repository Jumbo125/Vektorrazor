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
    "status.auto_from_image_done": "Auto-Einstellungen aus Bild gesetzt.",
    "status.auto_from_image_textlogo": "Auto-Einstellungen: Text/Logo-Modus (Feindetails priorisiert).",
    "status.auto_expert_done": "Expertenwerte automatisch aus Bild gesetzt.",
    "status.high_detail_applied": "Hohe Detailtreue aktiviert.",
    "status.lineart_preset_applied": "Schwarzweiß-Lineart-Vorschlag angewendet.",
    "status.epsilon_applied_all": "Epsilon auf alle Farben angewendet: {value}",
    "status.tolerance_applied_all": "Toleranz auf alle Farben angewendet: {value}",
    "status.startup_preset_logo": "Startprofil gesetzt: Logo / CAD / klare Formen.",
    "status.startup_preset_organic": "Startprofil gesetzt: Bild / organisch.",
    "status.startup_preset_mixed": "Startprofil gesetzt: Gemischt.",
    "status.workflow_reset": "Workflow zurückgesetzt. Bitte neues Bild laden.",
    "step1.input_image": "Input-Bild:",
    "step1.load_image": "Bild laden",
    "step1.save_png": "PNG speichern",
    "step1.auto_from_image": "Auto aus Bild",
    "step1.reset_workflow": "Neu starten",
    "step1.actions": "Workflow / Abschluss Schritt 1",
    "step1.tools": "Weitere Aktionen",
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
    "step2.motif_profile": "Motivtyp:",
    "step2.motif_profile_group": "Motiv / automatische Werte",
    "step2.load_png": "PNG direkt laden",
    "step2.output": "Output:",
    "step2.save_as": "Speichern als",
    "step2.save_options": "Speicheroptionen",
    "step2.choose_output": "Speicherort festlegen",
    "step2.pixel_to_mm": "Pixel zu mm:",
    "step2.compatibility": "Kompatibilitaet:",
    "step2.dxf_format": "DXF-Format:",
    "step2.actions": "Abschluss / Aktionen",
    "step2.auto": "1  Optional: Auto-Werte testen",
    "step2.detect_preview": "2  Erkennen / Vorschau",
    "step2.export": "3  Export DXF / SVG",
    "step2.actions_hint": "Auto-Werte ist optional und rechnet selbst eine Vorschau. Danach Vorschau pruefen oder direkt exportieren.",
    "step2.auto_expert_from_image": "Auto-Werte vorschlagen (optional)",
    "step2.live_preview": "Änderungen LIVE anzeigen",
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
    "step2.preview_mode": "Vorschau-Ansicht",
    "step2.loose_points": "Lose Ankerpunkte entfernen",
    "step2.smooth": "Rundungen glaetten",
    "step2.global_epsilon": "Punktreduktion / Epsilon px",
    "step2.apply_all_colors": "Epsilon auf alle Farben anwenden",
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
    "step2.hole_scale": "Lochgröße / Innenlöcher",
    "step2.bridge_tabs": "Intelligente Brücken setzen",
    "step2.bridge_width_mm": "Brückenbreite mm",
    "step2.bridge_width_percent": "Brückenbreite % vom Bild",
    "step2.bridge_count": "Brücken pro Teil",
    "step2.high_detail": "Hohe Detailtreue",
    "step2.quick_preview": "Vorschau",
    "step2.manual_refresh": "Vorschau manuell aktualisieren",
    "step2.quick_export": "Export",
    "step2.quick_colors": "Farben...",
    "step2.delete_small": "Kleine Objekte loeschen",
    "step2.percent_area": "% Bildflaeche",
    "step2.path_selection": "Pfad-Auswahl",
    "step2.show_anchor_points": "Ankerpunkte anzeigen",
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
    "button.apply": "Anwenden",
    "button.cancel": "Abbrechen",
    "label.tolerance_short": "Tol.",
    "vector_mode.area": "Flaechenkontur",
    "vector_mode.centerline": "Mittellinie / Gravur",
    "preview_mode.object": "Objektcheck",
    "preview_mode.contour": "Konturlinien",
    "preview_mode.mask": "Farbmaske",
    "preview_mode.cut_risk": "Schnitt-/Fallteile",
    "cleanup.off": "Aus",
    "cleanup.mm2": "mm2",
    "cleanup.percent": "% Bildflaeche",
    "internal_scale.1x": "1x",
    "internal_scale.2x": "2x",
    "internal_scale.3x": "3x",
    "ui.dark_mode": "Dark-Mode",
    "ui.mode": "Bearbeitungs-Modus:",
    "ui.mode.simple": "Einfach",
    "ui.mode.expert": "Experte",
    "ui.theme.classic": "Klassisch (Illustrator/Corel-Style)",
    "ui.theme.modern": "Modern",
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
    "msg.no_intermediate_load_first": "Bitte zuerst ein Bild laden oder bearbeiten.",
    "msg.accepted_title": "Uebernommen",
    "msg.accepted": "Das bearbeitete Bild wurde fuer Schritt 2 uebernommen.",
    "msg.welcome_title": "Herzlich willkommen",
    "msg.welcome_body": "Vektorrazor arbeitet in zwei Schritten:\n\n1. Bild vorbereiten\nBild laden und bei Bedarf Farben bearbeiten, damit ein klarer Kontrast entsteht.\nBeim Laden schlägt der Automodus passende Werte vor. Wenn du selbst einstellen möchtest, klicke einfach auf Nein.\n\n2. Vektorisieren\nWenn das Zwischenbild passt, gehe weiter zu Schritt 2.\nDort erkennt Vektorrazor die Formen und erstellt Vorschau und Export.",
    "motif_profile.logo": "Logo / CAD / klare Formen",
    "motif_profile.organic": "Bild / organisch",
    "motif_profile.mixed": "Gemischt",
    "startup_preset.choose": "Welcher Ausgangstyp passt am besten? Du kannst die Auswahl später in Schritt 2 jederzeit ändern.",
    "startup_preset.logo.title": "Logo / CAD / klare Formen",
    "startup_preset.logo.desc": "Klare Kanten, ruhigere gerade Linien, weniger Punkte und Smart CAD Smoothing eher aktiv.",
    "startup_preset.organic.title": "Bild / organisch",
    "startup_preset.organic.desc": "Mehr Details erhalten, weniger harte Begradigung und organische Konturen vorsichtig behandeln.",
    "startup_preset.mixed.title": "Gemischt",
    "startup_preset.mixed.desc": "Mittelweg zwischen klaren Formen und organischen Motiven.",
    "msg.profile_title": "Profil",
    "msg.profile_unknown": "Unbekanntes Profil: {profile}",
    "msg.recognize_error_title": "Fehler bei Erkennung",
    "msg.auto_values_error_title": "Fehler bei Auto-Werten",
    "msg.auto_expert_prompt_title": "Schritt 2 vorbereiten",
    "msg.auto_expert_prompt": "Möchten Sie passende Expertenwerte für dieses Bild automatisch vorschlagen und direkt anwenden lassen?\n\nJa: Werte werden automatisch gesetzt und die Vorschau neu berechnet.\nNein: Aktuelle Werte bleiben unverändert.",
    "msg.motif_recalculate_title": "Motivtyp geändert",
    "msg.motif_recalculate_body": "Soll Vektorrazor die Auto-Werte mit dem neuen Motivtyp neu berechnen?\n\nJa: Auto-Check wird erneut ausgeführt und die Vorschau aktualisiert.\nNein: Nur das Profil wird gesetzt, du kannst die Werte manuell weiter ändern.",
    "msg.lineart_recommend_title": "Schwarzweiß-Lineart erkannt",
    "msg.lineart_recommend_intro": "Dieses Zwischenbild wirkt wie Schwarzweiß-Lineart. Empfohlen werden detailfreundliche Werte: keine automatische Weichzeichnung, keine kleinen Objektlöschungen und Schwarz/Weiß-Regeln aus dem Zwischen-PNG.\n\nWähle, welche Vorschau direkt geöffnet werden soll:",
    "msg.lineart_choice_contour": "zeigt die echten Vektorpfade und ist für CAD-Kontrolle meist besser",
    "msg.lineart_choice_mask": "zeigt die reine Raster-Farberkennung vor der Konturfindung",
    "msg.lineart_expert_hint": "Du kannst diese Ansicht später im Expertenmodus jederzeit unter 'Vorschau-Ansicht' wechseln.",
    "msg.export_done_title": "Export fertig",
    "msg.preprocess_info_title": "Vorverarbeitung",
    "msg.preprocess_info_body": "Vorverarbeitung verändert nur das Arbeitsbild für die Vektorerkennung, nicht das Originalbild.\n\nWeichzeichnen / Blur: Mehr beruhigt Pixelkanten stärker, kann aber feine Details verlieren. Weniger erhält Details, lässt aber mehr Treppchen stehen.\nKanten beruhigen: Gehört zur Vorverarbeitung. Mehr glättet verpixelte Konturen stärker, damit Linien gerader und CAD-tauglicher werden. Weniger bleibt näher am Rasterbild.\nMindeststörung px: Mehr entfernt mehr kleine Flecken und Punkte. Weniger erhält mehr Kleindetails.\nInterne Skalierung: Höher rechnet die Erkennung feiner und kann Kurven sauberer machen, ist aber langsamer.",
    "msg.smart_smoothing_info_title": "Smart CAD Smoothing",
    "msg.smart_smoothing_info_body": "Smart CAD Smoothing analysiert die bereits erkannten Vektorkonturen, also nach der Vorverarbeitung.\n\nGerade Bereiche wie Hauskanten bleiben eher gerade. Runde Bereiche wie Augen, Blüten oder Ornamente werden geglättet. Organische Formen wie Baumstämme sollen nicht perfekt technisch wirken, sondern ihre natürliche Unregelmäßigkeit behalten.\n\nEcken schützen Grad: Höher schützt mehr Winkel als Ecke, niedriger glättet mehr Übergänge.\nGerade Linien Toleranz px: Höher erkennt mehr Bereiche als gerade Linie, niedriger bleibt strenger.\nKurven-Glättung: Höher macht Kurven runder und ruhiger, niedriger erhält mehr originale Unruhe.",
    "msg.bridge_tabs_info_title": "Intelligente Brücken",
    "msg.bridge_tabs_info_body": "Brücken öffnen geschlossene Risikokonturen an kurzen Stellen. Dadurch bleiben Inneninseln und kleine ausgeschnittene Teile mit dem Material verbunden und fallen beim Schneiden weniger leicht heraus.\n\nBrückenbreite mm: Größere Werte erzeugen breitere Stege, kleinere Werte lassen mehr Kontur stehen.\nBrückenbreite % vom Bild: Alternative Breite abhängig von der Bildgröße. Wenn mm und Prozent gesetzt sind, wird der größere Wert verwendet.\nBrücken pro Teil: Mehr Brücken halten Teile stabiler, schneiden aber mehr Unterbrechungen in die Kontur.\n\nDie Vorschau Schnitt-/Fallteile zeigt, welche Teile ohne Brücken kritisch wären. Aktivierte Brücken werden auch in SVG/DXF exportiert.",
    "msg.step1_recommend_title": "Empfehlung für Schritt 1",
    "msg.step1_recommend_mask": "Dieses Bild wirkt wie ein helles/graues Logo auf hellem oder verlaufendem Hintergrund.\n\nEmpfehlung: Logo-Maske erzeugen.\nDie Werte wurden aus dem Bild berechnet, nicht fix gesetzt.\n\nVorschlag:\n- Logo-Schwelle: {threshold}\n- Hintergrund-Radius: {blur}\n- geschätzte Maskenfläche: ca. {coverage:.1f}%\n- Zielbereich laut Analyse: ca. {target:.1f}%\n\nJetzt anwenden?\n\nNein = nur im passenden Tab bleiben, Werte werden nicht geändert.",
    "msg.step1_recommend_bw": "Dieses Bild wirkt wie kontrastreiches Schwarz/Weiß-Lineart.\n\nEmpfehlung: Schwarz/Weiß-Maske erzeugen, statt viele Restfarben aus Kantenpixeln zu übernehmen.\nVorschlag:\n- Logo-Schwelle: {threshold}\n- Hintergrund-Radius: {blur}\n- feine Details bleiben ohne zusätzliche Pixelglättung erhalten\n- später in Schritt 2 Konturlinien prüfen\n\nJetzt anwenden?\n\nNein = nur im passenden Tab bleiben, Werte werden nicht geändert.",
    "msg.step1_recommend_color": "Dieses Bild enthält mehrere echte Farben.\n\nEmpfehlung: Farben reduzieren und technische Ziel-RGBs zuweisen.\nVorschlag:\n- Schwelle: {threshold}\n- Max. Farben: {suggested_colors}\n- Mindestfläche: {min_area}\nDanach die Farbtabelle prüfen.\n\nJetzt anwenden?\n\nNein = nur im passenden Tab bleiben, Werte werden nicht geändert.",
    "msg.step1_recommend_manual": "Das Bild passt zu keinem eindeutigen Automatikmodus.\n\nEmpfehlung: Manuelle Farbumsetzung.\nDu kannst im Originalbild eine Farbe anklicken und die Ziel-RGB-Farbe gezielt setzen.\n\nDer passende Tab wurde bereits geöffnet.",
    "status.step1_recommend_mask_applied": "Empfehlung angewendet: Logo-Maske mit Schwelle {threshold}, Radius {blur}.",
    "status.step1_recommend_mask_skipped": "Empfehlung: Logo-Maske. Werte wurden nicht geändert.",
    "status.step1_recommend_bw_applied": "Empfehlung angewendet: Schwarz/Weiß-Maske erzeugt.",
    "status.step1_recommend_bw_skipped": "Empfehlung: Schwarz/Weiß-Maske. Werte wurden nicht geändert.",
    "status.step1_recommend_color_applied": "Empfehlung angewendet: Farben reduzieren.",
    "status.step1_recommend_color_skipped": "Empfehlung: Farben reduzieren. Werte wurden nicht geändert.",
    "status.step1_recommend_manual": "Keine eindeutige Automatik erkannt: Manuelle Farbumsetzung empfohlen.",
    "msg.busy_load_image_title": "Bild wird geladen",
    "msg.busy_load_image_body": "Bild wird geladen und analysiert...\n\nBitte kurz warten. Währenddessen sind Klicks blockiert.",
    "status.image_loaded": "Bild geladen: {name} | {width} x {height}px",
    "msg.busy_detect_colors_title": "Farben werden erkannt",
    "msg.busy_detect_colors_body": "Farben und Flächen werden analysiert...\n\nBitte kurz warten.",
    "msg.detect_colors_error": "Farben konnten nicht erkannt werden:\n{error}",
    "status.detected_color_regions": "{count} Farbbereiche erkannt. Ziel-RGB kann direkt in der Tabelle angepasst werden.",
    "status.manual_row_selected": "Selektierte Zeile: #{row} | Klick ins Original übernimmt die Farbe.",
    "status.pixel_color_at": "Pixel-Farbe bei x={x}, y={y}: {rgb}",
    "status.color_copied_to_row": "Farbe {rgb} in Zeile #{row} übernommen.",
    "status.invalid_base_color": "Ungültige Basis-Farbe: {error}",
    "status.invalid_manual_color": "Ungültige manuelle Farbe: {error}",
    "status.preview_error": "Vorschaufehler: {error}",
    "status.logo_mask_created": "Logo-Maske erzeugt. Diese Maske kann direkt in Schritt 2 vektorisiert werden.",
    "msg.logo_mask_error": "Logo-Maske konnte nicht erzeugt werden:\n{error}",
    "msg.export_intermediate_title": "Zwischen-PNG speichern",
    "status.intermediate_saved": "Zwischen-PNG gespeichert: {path}",
    "status.vector_source_ready_transferred": "Bearbeitetes Bild ist für Schritt 2 bereit. Farb-/Layer-Regeln wurden aus dem Zwischen-PNG übernommen.",
    "status.vector_source_ready_autofill": "Bearbeitetes Bild ist für Schritt 2 bereit. Farb-/Layer-Regeln wurden automatisch vorgeschlagen.",
    "status.profile_loaded": "Profil geladen: {profile}",
    "status.png_loaded": "PNG geladen: {name}",
    "status.no_path_selected": "Kein Pfad ausgewählt.",
    "status.no_path_hit": "Kein Pfad getroffen.",
    "status.no_contours_detected": "Noch keine Konturen erkannt.",
    "status.path_selection_changed": "Pfad-Auswahl geändert. Entf oder Button entfernt die ausgewählten Pfade.",
    "status.selection_mode_on": "Auswahl-Modus aktiv: Klick in die Vektor-Vorschau wählt einen Pfad. STRG fügt hinzu, ALT entfernt direkt.",
    "status.selection_mode_off": "Auswahl-Modus aus: Vorschau kann normal verschoben werden.",
    "status.path_selected_details": "Ausgewählt: Pfad #{index} | Layer {layer} | Punkte {points} | Fläche ca. {area:.0f}px²",
    "status.paths_selected_count": "{count} Pfade ausgewählt | Entf oder Button entfernt alle ausgewählten Pfade",
    "status.path_removed_details": "Entfernt: Pfad #{index} | Layer {layer} | Punkte {points}",
    "status.paths_removed_count": "Entfernt: {count} Pfade",
    "status.path_removed": "Pfad entfernt. Verbleibend: {remaining} | Export aktiv: {exported} | Punkte: {points}",
    "progress.read_vector_rules": "Vektor-Regeln werden gelesen...",
    "progress.detecting_contours": "Konturen werden erkannt...",
    "progress.filter_small_objects": "Kleine Objekte werden gefiltert...",
    "progress.detect_error": "Fehler bei Erkennung",
    "progress.auto_prepare": "Auto-Werte werden vorbereitet...",
    "progress.auto_test": "Auto-Werte: Test {index}/{total}...",
    "progress.auto_applied": "Auto-Werte gesetzt | Score: {score:.3f} | Punkte: {points}",
    "progress.auto_error": "Fehler bei Auto-Werten",
    "progress.writing_file": "Datei wird geschrieben...",
    "progress.export_done": "Export fertig: {out} | DXF {dxf_version} | Doppellinien-Cleanup: {cad_cleanup}",
    "msg.auto_expert_prompt_details": "Smart CAD Smoothing: Hält gerade Bereiche (z. B. Hauskanten) eher gerade, glättet runde Bereiche (z. B. Augen/Kurven) und lässt organische Formen (z. B. Baumstämme) natürlicher wirken.\nKanten beruhigen: Hilft bei verpixelten Vorlagen, damit Linien ruhiger und technischer erfasst werden.",
}

FALLBACK_EN_PATCH: dict[str, str] = {
    "step2.auto_expert_from_image": "Suggest Auto Values (Optional)",
    "step1.reset_workflow": "Start over",
    "step2.motif_profile": "Source type:",
    "step2.motif_profile_group": "Source type / automatic values",
    "step2.save_options": "Save options",
    "step2.choose_output": "Set save location",
    "step2.show_anchor_points": "Show anchor points",
    "step2.hole_scale": "Hole size / inner holes",
    "step2.bridge_tabs": "Add intelligent bridges",
    "step2.bridge_width_mm": "Bridge width mm",
    "step2.bridge_width_percent": "Bridge width % of image",
    "step2.bridge_count": "Bridges per part",
    "step2.high_detail": "High Detail Fidelity",
    "status.high_detail_applied": "High detail fidelity enabled.",
    "status.lineart_preset_applied": "Black/white line-art preset applied.",
    "status.startup_preset_logo": "Startup preset applied: Logo / CAD / clear shapes.",
    "status.startup_preset_organic": "Startup preset applied: Image / organic.",
    "status.startup_preset_mixed": "Startup preset applied: Mixed.",
    "status.workflow_reset": "Workflow reset. Please load a new image.",
    "preview_mode.cut_risk": "Cut/dropout risk",
    "button.apply": "Apply",
    "button.cancel": "Cancel",
    "msg.lineart_recommend_title": "Black/White Line Art Detected",
    "msg.lineart_recommend_intro": "This intermediate image looks like black/white line art. Detail-friendly values are recommended: no automatic blur, no small-object deletion, and black/white rules from the intermediate PNG.\n\nChoose which preview should open now:",
    "msg.lineart_choice_contour": "shows the actual vector paths and is usually best for CAD checking",
    "msg.lineart_choice_mask": "shows raw raster color detection before contour finding",
    "msg.lineart_expert_hint": "You can change this later in Expert mode under 'Preview view'.",
    "msg.auto_expert_prompt_title": "Prepare Step 2",
    "msg.auto_expert_prompt": "Do you want Vektorrazor to suggest suitable expert values for this image and apply them now?\n\nYes: values are set automatically and the preview is recalculated.\nNo: current values stay unchanged.",
    "msg.motif_recalculate_title": "Source type changed",
    "msg.motif_recalculate_body": "Should Vektorrazor recalculate the auto values using the new source type?\n\nYes: Auto check runs again and the preview is updated.\nNo: Only the profile is set; you can keep adjusting values manually.",
    "msg.welcome_title": "Welcome",
    "msg.welcome_body": "Vektorrazor works in two steps:\n\n1. Prepare image\nLoad an image and adjust colors if needed so the contrast is clear.\nWhen loading an image, Auto mode suggests suitable values. If you want to adjust things yourself, choose No.\n\n2. Vectorize\nWhen the intermediate image looks right, continue to step 2.\nThere Vektorrazor detects the shapes and creates the preview and export.",
    "motif_profile.logo": "Logo / CAD / clear shapes",
    "motif_profile.organic": "Image / organic",
    "motif_profile.mixed": "Mixed",
    "startup_preset.choose": "Which source type fits best? You can change this anytime later in step 2.",
    "startup_preset.logo.title": "Logo / CAD / clear shapes",
    "startup_preset.logo.desc": "Clear edges, calmer straight lines, fewer points and Smart CAD Smoothing more likely enabled.",
    "startup_preset.organic.title": "Image / organic",
    "startup_preset.organic.desc": "Preserve more detail, avoid hard straightening and treat organic contours carefully.",
    "startup_preset.mixed.title": "Mixed",
    "startup_preset.mixed.desc": "Balanced preset between clear shapes and organic subjects.",
    "msg.preprocess_info_title": "Preprocessing",
    "msg.preprocess_info_body": "Preprocessing changes only the working image used for vector detection, not the original image.\n\nBlur: Higher values calm pixel edges more strongly, but can remove fine detail. Lower values preserve detail, but keep more stair-stepping.\nEdge calming: This belongs to preprocessing. Higher values smooth pixelated contours more strongly so lines become straighter and more CAD-friendly. Lower values stay closer to the raster image.\nMinimum noise px: Higher values remove more small specks and dots. Lower values preserve more tiny details.\nInternal scaling: Higher values run detection at a finer working size and can clean curves, but are slower.",
    "msg.smart_smoothing_info_title": "Smart CAD Smoothing",
    "msg.smart_smoothing_info_body": "Smart CAD Smoothing analyzes the detected vector contours, after preprocessing.\n\nStraight areas such as building edges stay straighter. Round areas such as eyes, flowers, or ornaments are smoothed. Organic shapes such as tree trunks should not become perfectly technical, but keep their natural irregularity.\n\nProtect corners deg: Higher values protect more angles as corners, lower values smooth more transitions.\nStraight line tolerance px: Higher values classify more regions as straight lines, lower values are stricter.\nCurve smoothing: Higher values make curves rounder and calmer, lower values preserve more original irregularity.",
    "msg.bridge_tabs_info_title": "Intelligent Bridges",
    "msg.bridge_tabs_info_body": "Bridges open closed risk contours at short positions. This keeps inner islands and small cutout parts connected to the material so they are less likely to fall out while cutting.\n\nBridge width mm: Higher values create wider bridges, lower values keep more of the original contour.\nBridge width % of image: Alternative width based on image size. If mm and percent are set, the larger value is used.\nBridges per part: More bridges hold parts more securely, but add more interruptions to the contour.\n\nThe Cut/dropout risk preview shows which parts would be critical without bridges. Enabled bridges are exported to SVG/DXF.",
    "msg.no_intermediate_load_first": "Please load or edit an image first.",
    "msg.profile_title": "Profile",
    "msg.profile_unknown": "Unknown profile: {profile}",
    "msg.recognize_error_title": "Detection Error",
    "msg.auto_values_error_title": "Auto Values Error",
    "status.epsilon_applied_all": "Epsilon applied to all colors: {value}",
    "status.tolerance_applied_all": "Tolerance applied to all colors: {value}",
    "msg.step1_recommend_title": "Recommendation for Step 1",
    "msg.step1_recommend_mask": "This image looks like a bright/gray logo on a bright or gradient background.\n\nRecommendation: create a logo mask.\nThe values were derived from the image, not fixed defaults.\n\nSuggestion:\n- Logo threshold: {threshold}\n- Background radius: {blur}\n- estimated mask area: about {coverage:.1f}%\n- target range from analysis: about {target:.1f}%\n\nApply now?\n\nNo = stay on the matching tab only, values are not changed.",
    "msg.step1_recommend_bw": "This image looks like high-contrast black/white line art.\n\nRecommendation: create a black/white mask instead of carrying many residual edge colors into vectorization.\nSuggestion:\n- Logo threshold: {threshold}\n- Background radius: {blur}\n- fine details are preserved without extra pixel cleanup\n- then check contour lines in step 2\n\nApply now?\n\nNo = stay on the matching tab only, values are not changed.",
    "msg.step1_recommend_color": "This image contains multiple real colors.\n\nRecommendation: reduce colors and assign technical target RGB values.\nSuggestion:\n- Threshold: {threshold}\n- Max. colors: {suggested_colors}\n- Min. area: {min_area}\nThen review the color table.\n\nApply now?\n\nNo = stay on the matching tab only, values are not changed.",
    "msg.step1_recommend_manual": "This image does not match a clear automatic mode.\n\nRecommendation: manual color mapping.\nYou can click a color in the original image and assign the target RGB directly.\n\nThe matching tab has already been opened.",
    "status.step1_recommend_mask_applied": "Recommendation applied: logo mask with threshold {threshold}, radius {blur}.",
    "status.step1_recommend_mask_skipped": "Recommendation: logo mask. Values were not changed.",
    "status.step1_recommend_bw_applied": "Recommendation applied: black/white mask created.",
    "status.step1_recommend_bw_skipped": "Recommendation: black/white mask. Values were not changed.",
    "status.step1_recommend_color_applied": "Recommendation applied: reduce colors.",
    "status.step1_recommend_color_skipped": "Recommendation: reduce colors. Values were not changed.",
    "status.step1_recommend_manual": "No clear automatic mode detected: manual color mapping recommended.",
    "msg.busy_load_image_title": "Loading image",
    "msg.busy_load_image_body": "Image is being loaded and analyzed...\n\nPlease wait a moment. Clicks are blocked during this process.",
    "status.image_loaded": "Image loaded: {name} | {width} x {height}px",
    "msg.busy_detect_colors_title": "Detecting colors",
    "msg.busy_detect_colors_body": "Colors and areas are being analyzed...\n\nPlease wait a moment.",
    "msg.detect_colors_error": "Could not detect colors:\n{error}",
    "status.detected_color_regions": "{count} color regions detected. Target RGB can be adjusted directly in the table.",
    "status.manual_row_selected": "Selected row: #{row} | click in original image copies the color.",
    "status.pixel_color_at": "Pixel color at x={x}, y={y}: {rgb}",
    "status.color_copied_to_row": "Color {rgb} copied to row #{row}.",
    "status.invalid_base_color": "Invalid base color: {error}",
    "status.invalid_manual_color": "Invalid manual color: {error}",
    "status.preview_error": "Preview error: {error}",
    "status.logo_mask_created": "Logo mask created. This mask can be vectorized directly in step 2.",
    "msg.logo_mask_error": "Could not create logo mask:\n{error}",
    "msg.export_intermediate_title": "Save intermediate PNG",
    "status.intermediate_saved": "Intermediate PNG saved: {path}",
    "status.vector_source_ready_transferred": "Edited image is ready for step 2. Color/layer rules were imported from the intermediate PNG.",
    "status.vector_source_ready_autofill": "Edited image is ready for step 2. Color/layer rules were suggested automatically.",
    "status.profile_loaded": "Profile loaded: {profile}",
    "status.png_loaded": "PNG loaded: {name}",
    "status.no_path_selected": "No path selected.",
    "status.no_path_hit": "No path hit.",
    "status.no_contours_detected": "No contours detected yet.",
    "status.path_selection_changed": "Path selection changed. Del or the button removes selected paths.",
    "status.selection_mode_on": "Selection mode active: click in vector preview selects a path. CTRL adds, ALT removes directly.",
    "status.selection_mode_off": "Selection mode off: preview can be panned normally.",
    "status.path_selected_details": "Selected: path #{index} | layer {layer} | points {points} | area about {area:.0f}px²",
    "status.paths_selected_count": "{count} paths selected | Del or button removes all selected paths",
    "status.path_removed_details": "Removed: path #{index} | layer {layer} | points {points}",
    "status.paths_removed_count": "Removed: {count} paths",
    "status.path_removed": "Path removed. Remaining: {remaining} | Export active: {exported} | Points: {points}",
    "progress.read_vector_rules": "Reading vector rules...",
    "progress.detecting_contours": "Detecting contours...",
    "progress.filter_small_objects": "Filtering small objects...",
    "progress.detect_error": "Detection error",
    "progress.auto_prepare": "Preparing auto values...",
    "progress.auto_test": "Auto values: test {index}/{total}...",
    "progress.auto_applied": "Auto values applied | Score: {score:.3f} | Points: {points}",
    "progress.auto_error": "Auto values error",
    "progress.writing_file": "Writing file...",
    "progress.export_done": "Export complete: {out} | DXF {dxf_version} | duplicate-line cleanup: {cad_cleanup}",
}



def fallback_for_language(code: str) -> dict[str, str]:
    fallback = dict(FALLBACK_DE)
    if code == "en":
        fallback.update(FALLBACK_EN_PATCH)
    return fallback

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


def _normalize_german_texts(language_dict: dict[str, str]) -> None:
    """Gezielte Korrekturen für ältere DE-Dateien ohne Umlaute."""
    replacements = {
        "step2.live_preview": "Änderungen LIVE anzeigen",
        "step2.auto_expert_from_image": "Auto-Werte vorschlagen (optional)",
        "step2.hole_scale": "Lochgröße / Innenlöcher",
        "step2.bridge_tabs": "Intelligente Brücken setzen",
        "step2.bridge_width_mm": "Brückenbreite mm",
        "step2.bridge_width_percent": "Brückenbreite % vom Bild",
        "step2.bridge_count": "Brücken pro Teil",
        "step2.high_detail": "Hohe Detailtreue",
        "step2.smart_corner_angle": "Ecken schützen Grad",
        "step2.smart_curve_strength": "Kurven-Glättung",
        "step2.group_connected_paths": "Zusammenhängende Pfade gruppieren (SVG)",
        "step2.percent_area": "% Bildfläche",
        "msg.auto_expert_prompt_title": "Schritt 2 vorbereiten",
        "msg.auto_expert_prompt": "Möchten Sie passende Expertenwerte für dieses Bild automatisch vorschlagen und direkt anwenden lassen?\n\nJa: Werte werden automatisch gesetzt und die Vorschau neu berechnet.\nNein: Aktuelle Werte bleiben unverändert.",
        "msg.bridge_tabs_info_title": "Intelligente Brücken",
        "msg.bridge_tabs_info_body": "Brücken öffnen geschlossene Risikokonturen an kurzen Stellen. Dadurch bleiben Inneninseln und kleine ausgeschnittene Teile mit dem Material verbunden und fallen beim Schneiden weniger leicht heraus.\n\nBrückenbreite mm: Größere Werte erzeugen breitere Stege, kleinere Werte lassen mehr Kontur stehen.\nBrückenbreite % vom Bild: Alternative Breite abhängig von der Bildgröße. Wenn mm und Prozent gesetzt sind, wird der größere Wert verwendet.\nBrücken pro Teil: Mehr Brücken halten Teile stabiler, schneiden aber mehr Unterbrechungen in die Kontur.\n\nDie Vorschau Schnitt-/Fallteile zeigt, welche Teile ohne Brücken kritisch wären. Aktivierte Brücken werden auch in SVG/DXF exportiert.",
    }
    for key, value in replacements.items():
        if value:
            language_dict[key] = value


def _normalize_english_texts(language_dict: dict[str, str]) -> None:
    for key, value in FALLBACK_EN_PATCH.items():
        language_dict[key] = value


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
                merged, missing = validate_language_file(raw, fallback_for_language(code))
                if code == "de":
                    _normalize_german_texts(merged)
                elif code == "en":
                    _normalize_english_texts(merged)
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
