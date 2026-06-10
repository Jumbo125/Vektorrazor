# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""Sprachverwaltung und Textauflösung für die Benutzeroberfläche.

Diese Datei bündelt alle Hilfsfunktionen, die für Mehrsprachigkeit nötig sind.
Sie lädt Sprachdateien, verwaltet die aktuelle Sprache, liefert Fallbacks und
stellt mit ``tr(...)`` die zentrale Übersetzungsfunktion für den Rest des
Programms bereit.

Wichtige Aufgaben:
- Laden von JSON-Sprachdateien
- Verwalten verfügbarer Sprachbezeichnungen
- Nachverfolgen fehlender Übersetzungsschlüssel
- Bereitstellen deutscher Fallback-Texte
- Vereinheitlichung aller UI-Texte über eine zentrale Stelle
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# Deutsch bleibt die sichere Rückfallebene, damit auch bei unvollständigen
# Sprachdateien jederzeit verwertbare UI-Texte angezeigt werden können.
FALLBACK_LANGUAGE = "de"
_current_language = FALLBACK_LANGUAGE
_languages: dict[str, dict[str, str]] = {}
_language_names: dict[str, str] = {}
_missing_keys: dict[str, list[str]] = {}
_last_status_message = ""


FALLBACK_DE: dict[str, str] = {'app.header': 'PNG-Logo -> CAD-nahe Vektordaten',
 'app.title': 'Vektorrazor - PNG Logo zu CAD-tauglichen Vektordaten',
 'button.apply': 'Anwenden',
 'button.cancel': 'Abbrechen',
 'button.choose': 'wählen',
 'button.close': 'Schliessen',
 'button.reset': 'Zurücksetzen',
 'canvas.edited': 'Bearbeitet / technische Zwischenstufe',
 'canvas.original': 'Original',
 'canvas.step2_original': 'Zwischen-PNG',
 'canvas.vector_preview': 'Vektor-Vorschau',
 'cleanup.mm2': 'mm2',
 'cleanup.off': 'Aus',
 'cleanup.percent': '% Bildflaeche',
 'dxf.compat.autocad': 'AutoCAD / CAD modern',
 'dxf.compat.coreldraw': 'CorelDRAW',
 'dxf.compat.coreldraw_modern': 'CorelDRAW modern',
 'dxf.compat.default': 'Illustrator / CorelDRAW (empfohlen)',
 'dxf.compat.freecad': 'FreeCAD / LibreCAD / CAM',
 'dxf.compat.illustrator': 'Adobe Illustrator',
 'dxf.compat.manual': 'Manuell',
 'internal_scale.1x': '1x',
 'internal_scale.2x': '2x',
 'internal_scale.3x': '3x',
 'label.tolerance_short': 'Tol.',
 'language.fallback_name': 'Deutsch (Fallback)',
 'language.incomplete': 'Sprachdatei unvollständig, Fallback für fehlende Texte verwendet.',
 'motif_profile.logo': 'Logo / CAD / klare Formen',
 'motif_profile.mixed': 'Gemischt',
 'motif_profile.organic': 'Bild / organisch',
 'msg.accepted': 'Das bearbeitete Bild wurde für Schritt 2 übernommen.',
 'msg.accepted_title': 'Uebernommen',
 'msg.auto_expert_prompt': 'Möchten Sie passende Expertenwerte für dieses Bild automatisch vorschlagen und direkt '
                           'anwenden lassen?\n'
                           '\n'
                           'Ja: Werte werden automatisch gesetzt und die Vorschau neu berechnet.\n'
                           'Nein: Aktuelle Werte bleiben unverändert.',
 'msg.auto_expert_prompt_details': 'Smart CAD Smoothing: Hält gerade Bereiche (z. B. Hauskanten) eher gerade, glättet '
                                   'runde Bereiche (z. B. Augen/Kurven) und lässt organische Formen (z. B. Baumstämme) '
                                   'natürlicher wirken.\n'
                                   'Kanten beruhigen: Hilft bei verpixelten Vorlagen, damit Linien ruhiger und '
                                   'technischer erfasst werden.',
 'msg.auto_expert_prompt_title': 'Schritt 2 vorbereiten',
 'msg.auto_values_error_title': 'Fehler bei Auto-Werten',
 'msg.bridge_tabs_info_body': 'Brücken öffnen geschlossene Risikokonturen an kurzen Stellen. Dadurch bleiben '
                              'Inneninseln und kleine ausgeschnittene Teile mit dem Material verbunden und fallen beim '
                              'Schneiden weniger leicht heraus.\n'
                              '\n'
                              'Brückenbreite mm: Größere Werte erzeugen breitere Stege, kleinere Werte lassen mehr '
                              'Kontur stehen.\n'
                              'Brückenbreite % vom Bild: Alternative Breite abhängig von der Bildgröße. Wenn mm und '
                              'Prozent gesetzt sind, wird der größere Wert verwendet.\n'
                              'Brücken pro Teil: Mehr Brücken halten Teile stabiler, schneiden aber mehr '
                              'Unterbrechungen in die Kontur.\n'
                              '\n'
                              'Die Vorschau Schnitt-/Fallteile zeigt, welche Teile ohne Brücken kritisch wären. '
                              'Aktivierte Brücken werden auch in SVG/DXF exportiert.',
 'msg.bridge_tabs_info_title': 'Intelligente Brücken',
 'msg.busy_detect_colors_body': 'Farben und Flächen werden analysiert...\n\nBitte kurz warten.',
 'msg.busy_detect_colors_title': 'Farben werden erkannt',
 'msg.busy_load_image_body': 'Bild wird geladen und analysiert...\n'
                             '\n'
                             'Bitte kurz warten. Währenddessen sind Klicks blockiert.',
 'msg.busy_load_image_title': 'Bild wird geladen',
 'msg.busy_vector_body': 'Konturen und Vorschau werden berechnet.\n'
                         '\n'
                         'Währenddessen sind Klicks im Hauptfenster gesperrt.',
 'msg.busy_vector_title': 'Vektorisierung läuft',
 'msg.detect_colors_error': 'Farben konnten nicht erkannt werden:\n{error}',
 'msg.error': 'Fehler',
 'msg.export_done_title': 'Export fertig',
 'msg.export_error': 'Exportfehler',
 'msg.export_intermediate_title': 'Zwischen-PNG speichern',
 'msg.lineart_choice_contour': 'zeigt die echten Vektorpfade und ist für CAD-Kontrolle meist besser',
 'msg.lineart_choice_mask': 'zeigt die reine Raster-Farberkennung vor der Konturfindung',
 'msg.lineart_expert_hint': "Du kannst diese Ansicht später im Expertenmodus jederzeit unter 'Vorschau-Ansicht' "
                            'wechseln.',
 'msg.lineart_recommend_intro': 'Dieses Zwischenbild wirkt wie Schwarzweiß-Lineart. Empfohlen werden detailfreundliche '
                                'Werte: keine automatische Weichzeichnung, keine kleinen Objektlöschungen und '
                                'Schwarz/Weiß-Regeln aus dem Zwischen-PNG.\n'
                                '\n'
                                'Wähle, welche Vorschau direkt geöffnet werden soll:',
 'msg.lineart_recommend_title': 'Schwarzweiß-Lineart erkannt',
 'msg.load_error': 'Fehler beim Laden',
 'msg.logo_mask_error': 'Logo-Maske konnte nicht erzeugt werden:\n{error}',
 'msg.motif_recalculate_body': 'Soll Vektorrazor die Auto-Werte mit dem neuen Motivtyp neu berechnen?\n'
                               '\n'
                               'Ja: Auto-Check wird erneut ausgeführt und die Vorschau aktualisiert.\n'
                               'Nein: Nur das Profil wird gesetzt, du kannst die Werte manuell weiter ändern.',
 'msg.motif_recalculate_title': 'Motivtyp geändert',
 'msg.no_bbox_body': 'Die aktuelle Kontur hat keine gültige Größe.',
 'msg.no_bbox_title': 'Keine Bounding Box',
 'msg.no_contours_title': 'Keine Konturen',
 'msg.no_image_edit': 'Bitte zuerst ein Bild bearbeiten.',
 'msg.no_image_load': 'Bitte zuerst ein Bild laden.',
 'msg.no_image_title': 'Kein Bild',
 'msg.no_intermediate_load_first': 'Bitte zuerst ein Bild laden oder bearbeiten.',
 'msg.no_intermediate_step': 'Bitte zuerst Schritt 1 übernehmen oder ein PNG direkt laden.',
 'msg.no_intermediate_title': 'Kein Zwischenbild',
 'msg.perfect_bw_body': 'Dieses Bild ist bereits ein sauberes Schwarz/Weiß-Bild.\n'
                        '\n'
                        'Es wird 1:1 übernommen. Beim Wechsel zu Schritt 2 verwendet Vektorrazor automatisch '
                        'Schwarz/Weiß-Regeln.',
 'msg.perfect_bw_title': 'Schwarz/Weiß-Bild erkannt',
 'msg.photo_scan_error': 'Foto-/Scan-Bereinigung konnte nicht erstellt werden:\n{error}',
 'msg.photo_scan_timeout': 'Ein Foto-/Scan-Maskenschritt hat zu lange gedauert und wurde abgebrochen.\n'
                           'Bitte weniger Ziel-Farben wählen, Rauschen stärker bereinigen oder schwache Details '
                           'niedriger einstellen.',
 'msg.preprocess_info_body': 'Vorverarbeitung verändert nur das Arbeitsbild für die Vektorerkennung, nicht das '
                             'Originalbild.\n'
                             '\n'
                             'Weichzeichnen / Blur: Mehr beruhigt Pixelkanten stärker, kann aber feine Details '
                             'verlieren. Weniger erhält Details, lässt aber mehr Treppchen stehen.\n'
                             'Kanten beruhigen: Gehört zur Vorverarbeitung. Mehr glättet verpixelte Konturen stärker, '
                             'damit Linien gerader und CAD-tauglicher werden. Weniger bleibt näher am Rasterbild.\n'
                             'Mindeststörung px: Mehr entfernt mehr kleine Flecken und Punkte. Weniger erhält mehr '
                             'Kleindetails.\n'
                             'Interne Skalierung: Höher rechnet die Erkennung feiner und kann Kurven sauberer machen, '
                             'ist aber langsamer.',
 'msg.preprocess_info_title': 'Vorverarbeitung',
 'msg.preview_base_body': 'Die aktuelle Vorschau ist jetzt die neue Grundlage in Schritt 1. Du kannst nun in einem '
                          'anderen Reiter weiterarbeiten.',
 'msg.preview_base_title': 'Neue Grundlage übernommen',
 'msg.profile_apply_body': 'Das betrifft nur das ausgewählte Profil und ersetzt die Farb-/Layer-Regeln. Änderungen an '
                           "einzelnen Farben werden über 'Vorschau aktualisieren' neu berechnet.",
 'msg.profile_apply_title': 'Profil angewendet',
 'msg.profile_title': 'Profil',
 'msg.profile_unknown': 'Unbekanntes Profil: {profile}',
 'msg.recognize_error_title': 'Fehler bei Erkennung',
 'msg.smart_smoothing_info_body': 'Smart CAD Smoothing analysiert die bereits erkannten Vektorkonturen, also nach der '
                                  'Vorverarbeitung.\n'
                                  '\n'
                                  'Gerade Bereiche wie Hauskanten bleiben eher gerade. Runde Bereiche wie Augen, '
                                  'Blüten oder Ornamente werden geglättet. Organische Formen wie Baumstämme sollen '
                                  'nicht perfekt technisch wirken, sondern ihre natürliche Unregelmäßigkeit behalten.\n'
                                  '\n'
                                  'Ecken schützen Grad: Höher schützt mehr Winkel als Ecke, niedriger glättet mehr '
                                  'Übergänge.\n'
                                  'Gerade Linien Toleranz px: Höher erkennt mehr Bereiche als gerade Linie, niedriger '
                                  'bleibt strenger.\n'
                                  'Kurven-Glättung: Höher macht Kurven runder und ruhiger, niedriger erhält mehr '
                                  'originale Unruhe.',
 'msg.smart_smoothing_info_title': 'Smart CAD Smoothing',
 'msg.step1_auto_prompt_body': 'Soll Vektorrazor das Bild nach dem Laden analysieren und passende Werte vorschlagen?\n'
                               '\n'
                               'Ja: Auto-Erkennung startet nach dem Laden.\n'
                               'Nein: Bild nur laden, du stellst selbst ein.',
 'msg.step1_auto_prompt_title': 'Automatik für dieses Bild?',
 'msg.step1_recommend_bw': 'Dieses Bild wirkt wie kontrastreiches Schwarz/Weiß-Lineart.\n'
                           '\n'
                           'Empfehlung: Schwarz/Weiß-Maske erzeugen, statt viele Restfarben aus Kantenpixeln zu '
                           'übernehmen.\n'
                           'Vorschlag:\n'
                           '- Logo-Schwelle: {threshold}\n'
                           '- Hintergrund-Radius: {blur}\n'
                           '- feine Details bleiben ohne zusätzliche Pixelglättung erhalten\n'
                           '- später in Schritt 2 Konturlinien prüfen\n'
                           '\n'
                           'Jetzt anwenden?\n'
                           '\n'
                           'Nein = nur im passenden Tab bleiben, Werte werden nicht geändert.',
 'msg.step1_recommend_color': 'Dieses Bild enthält mehrere echte Farben.\n'
                              '\n'
                              'Empfehlung: Farben reduzieren und technische Ziel-RGBs zuweisen.\n'
                              'Vorschlag:\n'
                              '- Schwelle: {threshold}\n'
                              '- Max. Farben: {suggested_colors}\n'
                              '- Mindestfläche: {min_area}\n'
                              '- Rauschen unterdrücken: {noise}\n'
                              'Danach die Farbtabelle prüfen.\n'
                              '\n'
                              'Jetzt anwenden?\n'
                              '\n'
                              'Nein = nur im passenden Tab bleiben, Werte werden nicht geändert.',
 'msg.step1_recommend_existing_bw': 'Dieses Bild wirkt bereits sehr sauber und kontrastreich. Eine Bearbeitung in Schritt 1 ist wahrscheinlich nicht nötig.\n\nVorhandenes Bild unverändert verwenden?\n\nJa: 1:1 als Zwischenbild übernehmen und in Schritt 2 Schwarz/Weiß-Regeln nutzen.\nNein: manuelle Bearbeitung öffnen.',
 'msg.step1_recommend_manual': 'Das Bild passt zu keinem eindeutigen Automatikmodus.\n'
                               '\n'
                               'Empfehlung: Manuelle Farbumsetzung.\n'
                               'Du kannst im Originalbild eine Farbe anklicken und die Ziel-RGB-Farbe gezielt setzen.\n'
                               '\n'
                               'Der passende Tab wurde bereits geöffnet.',
 'msg.step1_recommend_mask': 'Dieses Bild wirkt wie ein helles/graues Logo auf hellem oder verlaufendem Hintergrund.\n'
                             '\n'
                             'Empfehlung: Logo-Maske erzeugen.\n'
                             'Die Werte wurden aus dem Bild berechnet, nicht fix gesetzt.\n'
                             '\n'
                             'Vorschlag:\n'
                             '- Logo-Schwelle: {threshold}\n'
                             '- Hintergrund-Radius: {blur}\n'
                             '- geschätzte Maskenfläche: ca. {coverage:.1f}%\n'
                             '- Zielbereich laut Analyse: ca. {target:.1f}%\n'
                             '\n'
                             'Jetzt anwenden?\n'
                             '\n'
                             'Nein = nur im passenden Tab bleiben, Werte werden nicht geändert.',
 'msg.step1_recommend_photo_scan': 'Dieses Bild wirkt schwierig oder wie ein Foto/Scan eines Logos.\n'
                                   '\n'
                                   'Problem-Score: {score}\n'
                                   '- viele Farbabstufungen: etwa {colors}\n'
                                   '- Hintergrundrauschen: {noise:.1f}\n'
                                   '- kleine Flecken/Kanteninseln: {specks}\n'
                                   '\n'
                                   'Empfehlung: Foto-/Scan-Auto-Modus starten. Er berechnet mehrere Varianten und '
                                   'übernimmt automatisch die technisch ruhigste Zwischenstufe. Bei sehr schwierigen '
                                   'Bildern kann manuelle Farbauswahl mit hoher Toleranz weiterhin besser sein.\n'
                                   '\n'
                                   'Auto-Modus jetzt anwenden?',
 'msg.step1_recommend_photo_scan_bw': 'Dieses Bild wirkt wie ein farbiges Logo, für CAD ist aber eine ruhige '
                                      'Schwarz/Weiß-Zwischenstufe meist sinnvoller als eine farbige '
                                      'Cluster-Aufteilung.\n'
                                      '\n'
                                      'Empfehlung: Foto-/Scan-Modus „schwarz/weiß“ verwenden.\n'
                                      'Dadurch werden Farbverläufe, Anti-Aliasing und kleine Farbschwankungen eher zu '
                                      'klaren Schwarz/Weiß-Flächen zusammengefasst.\n'
                                      '\n'
                                      'Problem-Score: {score}\n'
                                      '- Farbabstufungen: etwa {colors}\n'
                                      '- Hintergrundrauschen: {noise:.1f}\n'
                                      '- kleine Flecken/Kanteninseln: {specks}\n'
                                      '\n'
                                      'Schwarz/Weiß-Modus jetzt anwenden?',
 'step1.photo_scan_preserve_accents': 'Farbige Akzente kontrastierend erhalten',
 'tooltip.step1.photo_scan_preserve_accents': 'Erhält kleine farbige Details wie Sterne. Die Ziel-Farbe wird lokal gewählt: auf schwarzem Umfeld weiss, auf hellem Umfeld schwarz.',
 'msg.step1_recommend_preserve_accents': 'Kleine farbige Akzente wurden erkannt. Sie werden im Schwarz/Weiss-Modus lokal kontrastierend gesetzt.',
 'msg.step1_recommend_photo_scan_bw': 'Dieses Bild wirkt wie ein farbiges Logo/Abzeichen mit Verläufen oder vielen Zwischenfarben. Für CAD ist hier meistens eine Schwarz/Weiß-Maske besser als Farbumfärben.\n\nProblem-Score: {score}\n- viele Farbabstufungen: etwa {colors}\n- Hintergrundrauschen: {noise:.1f}\n- kleine Flecken/Kanteninseln: {specks}\n\nEmpfehlung: Foto-/Scan-Modus Schwarz/Weiß verwenden. Farbige Akzente können bei Bedarf geschützt werden.\n\nJetzt anwenden?',
 'msg.step1_recommend_title': 'Empfehlung für Schritt 1',
 'msg.stl_export_done': 'STL wurde gespeichert:\n'
                        '{out}\n'
                        '\n'
                        'Flächen: {surfaces}\n'
                        'Extrusion: {extrusion:.2f} mm\n'
                        'Facetten: {facets}',
 'msg.stl_invalid_extrusion': 'Bitte einen Extrusionswert größer 0 mm eingeben.',
 'msg.stl_no_selection_body': 'Bitte mindestens eine Fläche für den STL-Export markieren.',
 'msg.stl_no_selection_title': 'Keine Fläche gewählt',
 'msg.stl_no_surfaces_body': 'Für STL werden geschlossene exportierbare Flächen benötigt. Bitte zuerst eine passende '
                             'Vorschau erzeugen.',
 'msg.stl_no_surfaces_title': 'Keine STL-Flächen',
 'msg.target_size_body': 'Bitte Zielbreite oder Zielhöhe in mm eingeben.',
 'msg.target_size_title': 'Zielgröße fehlt',
 'msg.welcome_body': 'Vektorrazor arbeitet in zwei Schritten:\n'
                     '\n'
                     '1. Bild vorbereiten\n'
                     'Bild laden und bei Bedarf Farben bearbeiten, damit ein klarer Kontrast entsteht.\n'
                     'Beim Laden schlägt der Automodus passende Werte vor. Wenn du selbst einstellen möchtest, klicke '
                     'einfach auf Nein.\n'
                     '\n'
                     '2. Vektorisieren\n'
                     'Wenn das Zwischenbild passt, gehe weiter zu Schritt 2.\n'
                     'Dort erkennt Vektorrazor die Formen und erstellt Vorschau und Export.',
 'msg.welcome_title': 'Herzlich willkommen',
 'nav.back': '<- Zurück',
 'nav.back_to_step1': '<- Zurück zu Schritt 1',
 'nav.export': 'Export DXF / SVG ->',
 'nav.next': 'Weiter ->',
 'nav.next_vectorize': 'Weiter zur Vektorisierung ->',
 'nav.scale_export': 'Skalieren und DXF / SVG / STL exportieren',
 'preview_mode.contour': 'Konturlinien',
 'preview_mode.cut_risk': 'Schnitt-/Fallteile',
 'preview_mode.mask': 'Farbmaske',
 'preview_mode.object': 'Objektcheck',
 'progress.auto_applied': 'Auto-Werte gesetzt | Score: {score:.3f} | Punkte: {points}',
 'progress.auto_error': 'Fehler bei Auto-Werten',
 'progress.auto_prepare': 'Auto-Werte werden vorbereitet...',
 'progress.auto_test': 'Auto-Werte: Test {index}/{total}...',
 'progress.build_color_table': 'Farbtabelle wird aufgebaut...',
 'progress.detect_colors': 'Farben werden analysiert...',
 'progress.detect_colors_fallback': 'Farben werden erneut geprüft...',
 'progress.detect_error': 'Fehler bei Erkennung',
 'progress.detecting_contours': 'Konturen werden erkannt...',
 'progress.export_done': 'Export fertig: {out} | DXF {dxf_version} | Doppellinien-Cleanup: {cad_cleanup}',
 'progress.filter_small_objects': 'Kleine Objekte werden gefiltert...',
 'progress.load_image': 'Bild wird geladen...',
 'progress.photo_scan_auto_candidate': 'Auto-Variante {index}/{total}: {variant} wird geprüft...',
 'progress.photo_scan_background': 'Hintergrundmaske wird erzeugt...',
 'progress.photo_scan_cleanup': 'Masken werden bereinigt...',
 'progress.photo_scan_cluster': 'Farben werden geclustert...',
 'progress.photo_scan_detail_masks': 'Detailmasken werden erzeugt...',
 'progress.photo_scan_faded_background': 'Papier-/Lichtverlauf wird geschätzt...',
 'progress.photo_scan_faded_contrast': 'Schwacher Druck wird verstärkt...',
 'progress.photo_scan_faded_threshold': 'Lokale Druckspuren werden gesucht...',
 'progress.photo_scan_hysteresis': 'Schwache Pixel werden verbunden...',
 'progress.photo_scan_main_masks': 'Hauptmasken werden erzeugt...',
 'progress.photo_scan_masks': 'Masken werden erzeugt...',
 'progress.prepare_image': 'Bild wird vorbereitet...',
 'progress.read_vector_rules': 'Vektor-Regeln werden gelesen...',
 'progress.render_preview': 'Vorschau wird erstellt...',
 'progress.writing_file': 'Datei wird geschrieben...',
 'startup_preset.choose': 'Welcher Ausgangstyp passt am besten? Du kannst die Auswahl später in Schritt 2 jederzeit '
                          'ändern.',
 'startup_preset.logo.desc': 'Klare Kanten, ruhigere gerade Linien, weniger Punkte und Smart CAD Smoothing eher aktiv.',
 'startup_preset.logo.title': 'Logo / CAD / klare Formen',
 'startup_preset.mixed.desc': 'Mittelweg zwischen klaren Formen und organischen Motiven.',
 'startup_preset.mixed.title': 'Gemischt',
 'startup_preset.organic.desc': 'Mehr Details erhalten, weniger harte Begradigung und organische Konturen vorsichtig '
                                'behandeln.',
 'startup_preset.organic.title': 'Bild / organisch',
 'status.analysis_cancel_requested': 'Abbruch angefordert...',
 'status.analysis_cancelled': 'Analyse abgebrochen.',
 'status.auto_expert_done': 'Expertenwerte automatisch aus Bild gesetzt.',
 'status.auto_from_image_done': 'Auto-Einstellungen aus Bild gesetzt.',
 'status.auto_from_image_textlogo': 'Auto-Einstellungen: Text/Logo-Modus (Feindetails priorisiert).',
 'status.cad_cleanup_applied': 'CAD-Punktreduktion angewendet: {value}px',
 'status.cad_points': 'Punkte: {before} → {after}',
 'status.color_copied_to_row': 'Farbe {rgb} in Zeile #{row} übernommen.',
 'status.detected_color_regions': '{count} Farbbereiche erkannt. Ziel-RGB kann direkt in der Tabelle angepasst werden.',
 'status.epsilon_applied_all': 'CAD-Abweichung auf alle Farben angewendet: {value}px',
 'status.eraser_painted': 'Radierer angewendet bei x={x}, y={y}.',
 'status.eraser_ready': 'Aktuelle Vorschau ist als Radier-Grundlage übernommen.',
 'status.existing_image_skipped': 'Vorhandenes Bild nicht automatisch übernommen. Manuelle Bearbeitung geöffnet.',
 'status.existing_image_used': 'Vorhandenes Bild unverändert übernommen. Schritt 2 nutzt passende Schwarz/Weiß-Regeln.',
 'status.high_detail_applied': 'Hohe Detailtreue aktiviert.',
 'status.image_loaded': 'Bild geladen: {name} | {width} x {height}px',
 'status.intermediate_saved': 'Zwischen-PNG gespeichert: {path}',
 'status.invalid_base_color': 'Ungültige Basis-Farbe: {error}',
 'status.invalid_manual_color': 'Ungültige manuelle Farbe: {error}',
 'status.language_changed': 'Sprache geändert.',
 'status.lineart_preset_applied': 'Schwarzweiß-Lineart-Vorschlag angewendet.',
 'status.logo_mask_created': 'Logo-Maske erzeugt. Diese Maske kann direkt in Schritt 2 vektorisiert werden.',
 'status.manual_row_selected': 'Selektierte Zeile: #{row} | Klick ins Original übernimmt die Farbe.',
 'status.no_contours_detected': 'Noch keine Konturen erkannt.',
 'status.no_intermediate': 'Noch kein Zwischenbild übernommen',
 'status.no_path_hit': 'Kein Pfad getroffen.',
 'status.no_path_selected': 'Kein Pfad ausgewählt.',
 'status.path_removed': 'Pfad entfernt. Verbleibend: {remaining} | Export aktiv: {exported} | Punkte: {points}',
 'status.path_removed_details': 'Entfernt: Pfad #{index} | Layer {layer} | Punkte {points}',
 'status.path_selected_details': 'Ausgewählt: Pfad #{index} | Layer {layer} | Punkte {points} | Fläche ca. '
                                 '{area:.0f}px²',
 'status.path_selection_changed': 'Pfad-Auswahl geändert. Entf oder Button entfernt die ausgewählten Pfade.',
 'status.paths_removed_count': 'Entfernt: {count} Pfade',
 'status.paths_selected_count': '{count} Pfade ausgewählt | Entf oder Button entfernt alle ausgewählten Pfade',
 'status.perfect_bw_ready': 'Perfektes Schwarz/Weiß-Bild erkannt: 1:1 übernommen, Schritt 2 nutzt Schwarz/Weiß-Regeln.',
 'status.photo_scan_done': 'Foto-/Scan-Bereinigung erstellt: {variant}, {count} Zielfarben, Problem-Score {score}, '
                           'Rauschen {noise:.1f}, Technik-Score {tech:.1f}.',
 'status.photo_scan_mode_auto': 'Auto-Modus: mehrere technische Varianten werden bewertet.',
 'status.photo_scan_mode_bw': 'Modus „schwarz/weiß“: adaptive Hell/Dunkel-Maske für Lineart und Schrift.',
 'status.photo_scan_mode_clean': 'Modus „eher sauber“: stärkere Glättung und Störungsentfernung.',
 'status.photo_scan_mode_color': 'Modus „farbig“: mehrere Hauptfarben bleiben erhalten.',
 'status.photo_scan_mode_detail': 'Modus „eher detailreich“: feine Linien und schwache Details werden stärker '
                                  'geschützt.',
 'status.photo_scan_mode_faded': 'Modus „verblasster Druck“: Papier-/Lichtverlauf wird abgezogen und schwache '
                                 'Druckspuren werden als Schwarz/Weiß-Maske gesucht.',
 'status.pixel_color_at': 'Pixel-Farbe bei x={x}, y={y}: {rgb}',
 'status.png_loaded': 'PNG geladen: {name}',
 'status.preview_base_ready': 'Aktuelle Vorschau als neue Grundlage übernommen.',
 'status.preview_error': 'Vorschaufehler: {error}',
 'status.problem_hint_high_tolerance': 'Hohe Toleranz für manuelle Farbumsetzung gesetzt.',
 'status.problem_hint_manual_opened': 'Manuelle Farbauswahl geöffnet. Klicke Hauptfarben im Originalbild an.',
 'status.problem_hint_shown': 'Hinweis: Für dieses schwierige Bild kann manuelle Farbauswahl mit höherer Toleranz '
                              'bessere Flächen erzeugen.',
 'status.profile_loaded': 'Profil geladen: {profile}',
 'status.progress_percent': '{percent} % - {status}',
 'status.ready': 'Bereit',
 'status.scale_calculated': 'Maßstab gesetzt: {pixel_to_mm} mm/px. CAD-Abweichung entspricht {tolerance_px}px.',
 'status.scale_export_points': 'Punkte: {before} → {after} | Abweichung {px}px / {mm} mm',
 'status.selection_mode_off': 'Auswahl-Modus aus: Vorschau kann normal verschoben werden.',
 'status.selection_mode_on': 'Auswahl-Modus aktiv: Klick in die Vektor-Vorschau wählt einen Pfad. STRG fügt hinzu, ALT '
                             'entfernt direkt.',
 'status.startup_preset_logo': 'Startprofil gesetzt: Logo / CAD / klare Formen.',
 'status.startup_preset_mixed': 'Startprofil gesetzt: Gemischt.',
 'status.startup_preset_organic': 'Startprofil gesetzt: Bild / organisch.',
 'status.step1_auto_skipped': 'Bild geladen. Auto-Erkennung wurde übersprungen.',
 'status.step1_recommend_bw_applied': 'Empfehlung angewendet: Schwarz/Weiß-Maske erzeugt.',
 'status.step1_recommend_bw_skipped': 'Empfehlung: Schwarz/Weiß-Maske. Werte wurden nicht geändert.',
 'status.step1_recommend_color_applied': 'Empfehlung angewendet: Farben reduzieren.',
 'status.step1_recommend_color_skipped': 'Empfehlung: Farben reduzieren. Werte wurden nicht geändert.',
 'status.step1_recommend_manual': 'Keine eindeutige Automatik erkannt: Manuelle Farbumsetzung empfohlen.',
 'status.step1_recommend_mask_applied': 'Empfehlung angewendet: Logo-Maske mit Schwelle {threshold}, Radius {blur}.',
 'status.step1_recommend_mask_skipped': 'Empfehlung: Logo-Maske. Werte wurden nicht geändert.',
 'status.step1_recommend_photo_scan_applied': 'Empfehlung angewendet: Foto-/Scan-Bereinigung mit Problem-Score '
                                              '{score}.',
 'status.step1_recommend_photo_scan_bw_applied': 'Empfehlung angewendet: Foto-/Scan-Schwarzweiß-Modus gestartet. '
                                                 'Problem-Score {score}.',
 'status.step1_recommend_photo_scan_bw_skipped': 'Empfehlung: Foto-/Scan-Schwarzweiß-Modus. Werte wurden nicht '
                                                 'geändert. Problem-Score {score}.',
 'status.step1_recommend_photo_scan_skipped': 'Empfehlung: Foto-/Scan-Bereinigung mit Problem-Score {score}. Werte '
                                              'wurden nicht geändert.',
 'status.stl_export_done': 'STL exportiert: {facets} Facetten | {out}',
 'status.stl_selected_surfaces': 'STL-Flächen gewählt: {selected}/{total}',
 'status.stl_selected_surfaces_holes': 'STL: extrudierte Flächen {selected}/{total} | ausgesparte Löcher '
                                       '{holes}/{total_holes}',
 'status.tolerance_applied_all': 'Toleranz auf alle Farben angewendet: {value}',
 'status.vector_source_ready_autofill': 'Bearbeitetes Bild ist für Schritt 2 bereit. Farb-/Layer-Regeln wurden '
                                        'automatisch vorgeschlagen.',
 'status.vector_source_ready_transferred': 'Bearbeitetes Bild ist für Schritt 2 bereit. Farb-/Layer-Regeln wurden aus '
                                           'dem Zwischen-PNG übernommen.',
 'status.workflow_reset': 'Workflow zurückgesetzt. Bitte neues Bild laden.',
 'step1.actions': 'Workflow / Abschluss Schritt 1',
 'step1.add_mapping': '+ Farbumsetzung',
 'step1.alpha_from': 'Alpha ab',
 'step1.apply_high_tolerance': 'Mit hoher Toleranz anwenden',
 'step1.apply_preprocess': 'Vorschau aktualisieren',
 'step1.auto_from_image': 'Auto aus Bild',
 'step1.background_rgb': 'Hintergrund RGB',
 'step1.basic_hint': 'Tipp: Schritt 1 schreibt exakte RGB-Farben ins Zwischen-PNG. Diese RGB-Werte werden in Schritt 2 '
                     'automatisch als Layer-Regeln übernommen.',
 'step1.black_point': 'Schwarzpunkt',
 'step1.brightness': 'Helligkeit',
 'step1.clean_pixels': 'kleine Pixelstörungen glätten',
 'step1.clear_mask': 'Maske entfernen / normale Vorschau',
 'step1.contrast': 'Kontrast',
 'step1.create_mask': 'Logo-Maske erzeugen',
 'step1.delete_selected': '- selektierte löschen',
 'step1.detect': '2) Automatische Farberkennung',
 'step1.detect_colors': 'Farben erkennen',
 'step1.detected_ranges': '3) Erkannte Farbbereiche',
 'step1.eraser_color': 'Ersatzfarbe RGB',
 'step1.eraser_color_choose': 'Ersatzfarbe wählen',
 'step1.eraser_hint': 'Radierer für die rechte Vorschau: Klicke oder ziehe direkt im bearbeiteten Bild, um störende '
                      'Pixel/Flächen mit der gewählten Farbe zu überschreiben. Ideal nach Foto-/Scan-, Basis- oder '
                      'manueller Farbbearbeitung.',
 'step1.eraser_shape': 'Form',
 'step1.eraser_shape_round': 'Rund',
 'step1.eraser_shape_square': 'Eckig',
 'step1.eraser_size': 'Radierer-Größe px',
 'step1.eraser_status_idle': 'Radierer bereit. Wähle Größe, Form und Ersatzfarbe, dann male in der rechten Vorschau.',
 'step1.eraser_take_current': 'Aktuelle Vorschau für Radierer übernehmen',
 'step1.fill_solid_areas': 'Flächen/Löcher schließen',
 'step1.gamma': 'Gamma',
 'step1.input_image': 'Input-Bild:',
 'step1.label': 'Schritt 1 von 2: Bild bearbeiten / Farben exakt vorbereiten',
 'step1.load_image': 'Bild laden',
 'step1.logo_accent_rgb': 'Akzent RGB',
 'step1.logo_accent_contrast_hint': 'Akzentfarbe wird nicht mehr fix gesetzt: Vektorrazor prüft die direkte Umgebung und nimmt automatisch die Gegenfarbe. Auf schwarzem Ring wird der Akzent weiss, auf hellem Umfeld schwarz.',
 'step1.logo_hint': 'Für graue Logos, Schatten oder Verläufe: Maske über lokalen Kontrast erzeugen.',
 'step1.logo_preserve_accents': 'Farbige Akzente kontrastierend erhalten',
 'step1.logo_radius': 'Hintergrund-Radius',
 'step1.logo_radius_hint': 'größer = Schatten/Verläufe werden eher ignoriert',
 'step1.logo_rgb': 'Logo RGB',
 'step1.logo_threshold': 'Logo-Schwelle',
 'step1.logo_threshold_hint': 'höher = weniger wird schwarz',
 'step1.logo_direct_black': 'Motivfarbe technisch auf Schwarz umsetzen',
 'status.logo_direct_black_created': 'Motivfarbe technisch auf Schwarz umgesetzt.',
 'msg.logo_direct_black_error': 'Motivfarbe konnte nicht technisch auf Schwarz umgesetzt werden:\n{error}',
 'step1.manual_mappings': 'Manuelle Farbumsetzungen',
 'step1.manual_status': 'Kurzer Klick ins Originalbild übernimmt Farbe in die selektierte Zeile. Ziehen verschiebt die '
                        'Vorschau.',
 'step1.max_colors': 'Max. Farben',
 'step1.methods_intro': 'Jeder Arbeitsmodus ist ein eigener Weg zur technischen Zwischenstufe.\n'
                        'Du kannst die aktuelle Vorschau unten als neue Grundlage übernehmen und danach in einem '
                        'anderen Modus weiterarbeiten.die aktuelle Vorschau kann bei Bedarf als neue Grundlage '
                        'übernommen werden.',
 'step1.min_area': 'Min. Fläche',
 'step1.mode.basic': 'Basis: Farben erkennen',
 'step1.mode.eraser': 'Farb-Radierer',
 'step1.mode.logo': 'Logo-Maske',
 'step1.mode.manual': 'Erweitert: manuell',
 'step1.mode.photo_scan': 'Foto-/Scan-Logo bereinigen',
 'step1.mode.prep': 'Bildvorbereitung',
 'step1.mode_choose': 'Methode:',
 'step1.mode_hint.basic': 'Automatische Farberkennung für bereits vorbereitete, klare technische Farben.\n'
                          'Für normale farbige Logos ist Schwarz/Weiß oder Grau oft CAD-freundlicher.',
 'step1.mode_hint.eraser': 'Manuelle Nachbearbeitung der rechten Vorschau.\n'
                           'Mit dem Radierer kannst du Rauschen oder falsche Flächen direkt mit einer Ziel-RGB-Farbe '
                           'übermalen.',
 'step1.mode_hint.logo': 'Lokale Kontrastmaske für graue Logos, Schatten oder leichte Verläufe.\n'
                         'Gut für einfache Logos, die vom Hintergrund getrennt werden sollen.',
 'step1.mode_hint.manual': 'Manuelle Farbauswahl mit Pipette und eigener Toleranz.\n'
                           'Gut, wenn du genau weißt, welche Hauptfarben erhalten oder ersetzt werden sollen.',
 'step1.mode_hint.photo_scan': 'Technischer Auto-Modus für schwierige Fotos und Scans.\n'
                               'Papier/Hintergrund beruhigen, Rauschen entfernen, schwache Details finden und wenige '
                               'klare Zielfarben erzeugen.',
 'step1.mode_hint.prep': 'Helligkeit, Kontrast, Tonwerte, Gamma und Rotation vorbereiten.\n'
                         'Danach kannst du die Vorschau als neue Grundlage übernehmen oder in einem anderen Modus '
                         'weiterarbeiten.',
 'step1.mode_selector': 'Arbeitsmodus',
 'step1.noise_suppression': 'Rauschen unterdrücken',
 'step1.open_manual_colors': 'Manuelle Farben öffnen',
 'step1.photo_scan_apply': 'Foto-/Scan-Bereinigung anwenden',
 'step1.photo_scan_apply_auto': 'Auto: beste technische Fläche finden',
 'step1.photo_scan_apply_current': 'Aktuelle Einstellungen testen',
 'step1.photo_scan_close_lines': 'Linienlücken schließen',
 'step1.photo_scan_despeckle': 'Punkt-Rauschen entfernen',
 'step1.photo_scan_despeckle_area': 'Entpunkten / Mindestinsel',
 'step1.photo_scan_fill_small_holes': 'Kleine Löcher in Flächen füllen',
 'step1.photo_scan_foreground_distance': 'Farbabstand zum Hintergrund',
 'step1.photo_scan_hint': 'Technischer Auto-Modus für schwierige Fotos und Scans: Papier/Hintergrund erkennen, mehrere '
                          'Varianten berechnen, Flecken reduzieren, feine Linien schützen und wenige klare '
                          'Ziel-RGB-Farben erzeugen. Keine KI, kein Training, keine Modellabhängigkeit.',
 'step1.photo_scan_max_colors': 'Ziel-Farben',
 'step1.photo_scan_min_area': 'Min. Fläche',
 'step1.photo_scan_mode': 'Foto-/Scan-Modus',
 'step1.photo_scan_mode_auto': 'Auto',
 'step1.photo_scan_mode_balanced': 'Ausgewogen',
 'step1.photo_scan_mode_bw': 'schwarz/weiß',
 'step1.photo_scan_mode_clean': 'eher sauber',
 'step1.photo_scan_mode_color': 'farbig',
 'step1.photo_scan_mode_detail': 'eher detailreich',
 'step1.photo_scan_mode_faded': 'verblasster Druck',
 'step1.photo_scan_noise': 'Rauschen bereinigen',
 'step1.photo_scan_object_mask_first': 'Objektmaske zuerst erstellen',
 'step1.photo_scan_optional': 'Optionale Feinwerte',
 'step1.photo_scan_protect_background': 'Hintergrund/Papierstruktur schützen',
 'step1.photo_scan_protect_thin_lines': 'Dünne Linien schützen',
 'step1.photo_scan_weak_contrast': 'Schwache / feine Details erkennen',
 'step1.prep': '1) Bildvorbereitung',
 'step1.prep_detect': 'Vorbereitung + Farben neu erkennen',
 'step1.preprocess_hint': 'Hier wird nur das Bild vorbereitet: Helligkeit, Kontrast, Tonwerte, Gamma und Rotation. Die '
                          'automatische Farberkennung ist jetzt im eigenen Reiter „Basis: Farben erkennen“. Mit '
                          '„Aktuelle Vorschau als neue Grundlage“ kannst du das vorbereitete Bild dauerhaft als neue '
                          'Arbeitsbasis für weitere Reiter übernehmen.',
 'step1.problem_hint_body': 'Bei schwierigen Bildern ist oft die manuelle Farbauswahl besser:\n'
                            'Hauptfarben wählen, hohe Toleranz verwenden und mit klaren technischen Farben ersetzen. '
                            'Dadurch werden Farbschwankungen und Rauschen eher eingesammelt und es entstehen ruhigere '
                            'Flächen für die spätere Vektorisierung.',
 'step1.problem_hint_title': 'Alternative für schwierige Bilder',
 'step1.reassign': 'Kontrast neu färben',
 'step1.reset': 'Zurücksetzen',
 'step1.reset_workflow': 'Neu starten',
 'step1.rotate_left': '↺ Links drehen',
 'step1.rotate_right': '↻ Rechts drehen',
 'step1.rotation': 'Rotation °',
 'step1.rows_header': 'Aktiv  Quelle / Anteil  → Ziel-RGB',
 'step1.save_png': 'PNG speichern',
 'step1.tab_basic': 'Basis: Farben erkennen',
 'step1.tab_eraser': 'Farb-Radierer',
 'step1.tab_logo': 'Logo-Maske',
 'step1.tab_manual': 'Erweitert: manuell',
 'step1.tab_photo_scan': 'Foto-/Scan-Logo bereinigen',
 'step1.tab_preprocess': 'Bildvorbereitung',
 'step1.threshold': 'Schwelle',
 'step1.tools': 'Weitere Aktionen',
 'step1.update_colors': 'Farben aktualisieren',
 'step1.update_hint': "Hinweis: 'Weiter zur Vektorisierung' übernimmt die aktuelle Vorschau automatisch und wechselt "
                      "zu Schritt 2. 'Aktuelle Vorschau als neue Grundlage' bleibt in Schritt 1 und macht die Vorschau "
                      'zum neuen Ausgangsbild.',
 'step1.update_intermediate': 'Aktuelle Vorschau als neue Grundlage',
 'step1.use_preview_as_base': 'Aktuelle Vorschau als neue Grundlage',
 'step1.white_point': 'Weißpunkt',
 'step2.actions': 'Vorexport / Export',
 'step2.actions_hint': 'Auto-Werte ist optional und berechnet selbst eine Vorschau. Danach Vorschau prüfen oder direkt '
                       'exportieren.',
 'step2.add_color': '+ Farbe',
 'step2.anchor_cleanup': 'Nahe Ankerpunkte entfernen',
 'step2.anchor_min_distance': 'Mindestabstand px',
 'step2.anchor_point_size': 'Ankerpunktgröße',
 'step2.apply': 'Anwenden',
 'step2.apply_all_colors': 'Epsilon auf alle Farben anwenden',
 'step2.auto': '1  Optional: Auto-Werte testen',
 'step2.auto_expert_from_image': 'Auto-Werte vorschlagen (optional)',
 'step2.bbox': 'Bounding Box:',
 'step2.bbox_px_line': 'Bounding Box: {width_px:.0f} × {height_px:.0f} px',
 'step2.bezier_svg': 'Bezier für SVG',
 'step2.bridge_count': 'Brücken pro Teil',
 'step2.bridge_tabs': 'Intelligente Brücken setzen',
 'step2.bridge_width_mm': 'Brückenbreite mm',
 'step2.bridge_width_percent': 'Brückenbreite % vom Bild',
 'step2.cad_cleanup_after': 'Nachher: vereinfacht',
 'step2.cad_cleanup_before': 'Aktuelles Ergebnis',
 'step2.cad_cleanup_title': 'Punkte/Pfade vereinfachen',
 'step2.cad_deviation': 'CAD-Abweichung / Konturgenauigkeit px',
 'step2.cad_tolerance_mm': 'CAD-Abweichung mm',
 'step2.calculate_scale': 'Maßstab aus Zielgröße berechnen',
 'step2.choose_output': 'Speicherort festlegen',
 'step2.clear_selection': 'Auswahl aufheben',
 'step2.closed_only': 'Nur geschlossene Pfade',
 'step2.colors_layer': 'Farben / Layer',
 'step2.compatibility': 'Kompatibilität:',
 'step2.dedupe': 'Doppelte Linien entfernen (CAD)',
 'step2.dedupe_tolerance': 'Doppellinien-Toleranz px',
 'step2.delete_small': 'Kleine Objekte löschen',
 'step2.detect_colors_from_image': 'Farben aus Bild erkennen',
 'step2.detect_preview': '2  Erkennen / Vorschau',
 'step2.dxf_format': 'DXF-Format:',
 'step2.dynamic_table': 'Dynamische Farbtabelle',
 'step2.edit_colors': 'Farben / Layer bearbeiten',
 'step2.export': '3  Export DXF / SVG',
 'step2.export_size_line': 'Exportgröße: {width_mm:.2f} × {height_mm:.2f} mm',
 'step2.export_stl': 'Als STL exportieren',
 'step2.fill_svg': 'SVG-Flächen füllen (Export)',
 'step2.force_color_layers': 'Export-Layer pro Farbe',
 'step2.global_epsilon': 'CAD-Abweichung / Konturgenauigkeit px',
 'step2.group_connected_paths': 'Zusammenhaengende Pfade gruppieren (SVG)',
 'step2.high_detail': 'Hohe Detailtreue',
 'step2.hole_scale': 'Lochgröße / Innenlöcher',
 'step2.internal_scale': 'Interne Skalierung',
 'step2.keep_proportions': 'Proportionen beibehalten',
 'step2.label': 'Schritt 2 von 2: Vektorisieren / DXF oder SVG exportieren',
 'step2.live_preview': 'Änderungen LIVE anzeigen',
 'step2.load_png': 'PNG direkt laden',
 'step2.loose_points': 'Lose Ankerpunkte entfernen',
 'step2.manual_refresh': 'Vorschau manuell aktualisieren',
 'step2.merge_lines': 'Linien zusammenführen px',
 'step2.motif_profile': 'Motivtyp:',
 'step2.motif_profile_group': 'Motiv / automatische Werte',
 'step2.object_layers_dxf': 'Objekte in Layer erstellen (DXF)',
 'step2.open_cad_cleanup': 'Punkte/Pfade vereinfachen',
 'step2.preexport_cleanup': '1  Feinschliff/Vorexport: Pfade vereinfachen',
 'step2.export_final': '2  Export DXF / SVG',
 'step2.export_scaled': '2.1  Skalieren / DXF / SVG / STL',
 'step2.options': 'Vektor-Optionen',
 'step2.output': 'Output:',
 'step2.path_selection': 'Pfad-Auswahl',
 'step2.percent_area': '% Bildflaeche',
 'step2.pixel_to_mm': 'Pixel zu mm:',
 'step2.preprocess_blur': 'Weichzeichnen / Blur',
 'step2.preprocess_edges': 'Kanten beruhigen',
 'step2.preprocess_enabled': 'Vorverarbeitung aktiv',
 'step2.preprocess_noise': 'Mindeststoerung px',
 'step2.preview_mode': 'Vorschau-Ansicht',
 'step2.profile': 'Profil:',
 'step2.quick_colors': 'Farben...',
 'step2.quick_export': 'Export',
 'step2.quick_preview': 'Vorschau',
 'step2.refresh_preview': 'Vorschau aktualisieren',
 'step2.remove_selected_paths': 'Ausgewaehlte Pfade entfernen',
 'step2.save_as': 'Speichern als',
 'step2.save_options': 'Speicheroptionen',
 'step2.scale_default_hint': 'Standard: 1 px = 1 mm. Ein 500 × 500 px Bild wird ohne Skalierung als 500 × 500 mm '
                             'exportiert.',
 'step2.scale_export_after': 'Export-Vorschau',
 'step2.scale_export_before': 'Aktuelles Ergebnis',
 'step2.scale_export_enable': 'Konturen vor Export vereinfachen',
 'step2.scale_export_title': 'Skalieren und DXF / SVG / STL exportieren',
 'step2.scale_export_tolerance_percent': 'Konturgenauigkeit % Bildgröße',
 'step2.scale_line': 'Maßstab: 1 px = {pixel_to_mm:.3f} mm',
 'step2.selection_help': 'Auswahl-Modus EIN: Klick = Pfad wählen, STRG+Klick = hinzufügen/umschalten, ALT+Klick = '
                         'direkt entfernen. Auswahl-Modus AUS: Klick/Ziehen verschiebt die Vorschau; nur STRG+Klick '
                         'wählt temporär.',
 'step2.selection_mode': 'Auswahl-Modus',
 'step2.show_anchor_points': 'Ankerpunkte anzeigen',
 'step2.smart_corner_angle': 'Ecken schützen Grad',
 'step2.smart_curve_strength': 'Kurven-Glaettung',
 'step2.smart_line_tolerance': 'Gerade Linien Toleranz px',
 'step2.smart_smoothing': 'Smart CAD Smoothing',
 'step2.smooth': 'Rundungen glaetten',
 'step2.source': 'Zwischenbild:',
 'step2.stl_export_title': 'STL-Flächen auswählen und extrudieren',
 'step2.stl_extrusion_mm': 'Extrusion mm:',
 'step2.stl_holes_all_cutout': 'Alle Löcher aussparen',
 'step2.stl_holes_none_cutout': 'Keine Löcher aussparen',
 'step2.stl_preview': 'STL-Auswahl / aktuelle Export-Vorschau',
 'step2.stl_preview_note': 'STL-Vorschau: Rot markierte Löcher werden wirklich ausgespart. Ist die Option deaktiviert, '
                           'werden Innenlöcher gefüllt/extrudiert.',
 'step2.stl_save_button': 'Markierte Flächen als STL speichern',
 'step2.stl_save_dialog_title': 'STL speichern',
 'step2.stl_select_all': 'Alle Flächen wählen',
 'step2.stl_select_hint': 'Klick in die Vorschau schaltet Außenflächen oder Innenlöcher um. Violette Außenflächen '
                          'werden extrudiert. Rote Innenlöcher werden ausgespart und dadurch NICHT extrudiert. Orange '
                          'Innenlöcher werden gefüllt/extrudiert. STRG ist nicht nötig.',
 'step2.stl_select_none': 'Keine Fläche wählen',
 'step2.stl_selection_legend': 'Markierung: Violett = wird extrudiert | Grau = Außenfläche wird nicht extrudiert | Rot '
                               'mit Kreuz = Loch wird ausgespart/nicht extrudiert | Orange mit Kreuz = Loch wird '
                               'gefüllt/extrudiert.',
 'step2.stl_use_holes_as_cutout': 'Innenlöcher als Aussparung verwenden',
 'step2.target_height_mm': 'Zielhöhe mm:',
 'step2.target_width_mm': 'Zielbreite mm:',
 'step2.use_percent_values': 'Werte in % der Bildgröße',
 'step2.vector_type': 'Vektorart',
 'tooltip.step1.alpha_from': 'Weniger = mehr transparente Pixel zählen. Mehr = Transparenz stärker ignorieren.',
 'tooltip.step1.black_point': 'Weniger = mehr Schatten. Mehr = dunkle Bereiche werden schneller schwarz.',
 'tooltip.step1.brightness': 'Weniger = dunkler. Mehr = heller.',
 'tooltip.step1.contrast': 'Weniger = flacher. Mehr = stärkere Trennung.',
 'tooltip.step1.eraser_color': 'Diese RGB-Farbe wird in das Zwischenbild geschrieben. Für Rauschen meist '
                               'Hintergrundweiß oder eine klare technische Zielfarbe verwenden.',
 'tooltip.step1.eraser_size': 'Durchmesser/Kantenlänge des Radierers in Bildpixeln. Größer entfernt schneller, kleiner '
                              'ist genauer.',
 'tooltip.step1.gamma': 'Weniger = Mitteltöne heller. Mehr = Mitteltöne dunkler.',
 'tooltip.step1.logo_radius': 'Weniger = lokale Details. Mehr = Schatten/Verläufe stärker ignorieren.',
 'tooltip.step1.logo_threshold': 'Weniger = mehr wird Logo. Mehr = nur stärkere Striche.',
 'tooltip.step1.max_colors': 'Weniger = wenige Hauptfarben. Mehr = mehr Farbabstufungen.',
 'tooltip.step1.min_area': 'Weniger = kleine Details behalten. Mehr = kleine Störungen ignorieren.',
 'tooltip.step1.noise_suppression': 'Weniger = mehr Details. Mehr = mehr Rauschen entfernen.',
 'tooltip.step1.photo_scan_close_lines': 'Ein = kleine Unterbrechungen in Linien und Kreisen vorsichtig schließen.',
 'tooltip.step1.photo_scan_despeckle': 'Aus = Mini-Inseln behalten. Ein = sehr kleine Fremdpunkte je Farbmaske '
                                       'entfernen.',
 'tooltip.step1.photo_scan_despeckle_area': 'Weniger = mehr kleine Details bleiben. Mehr = kleine Punktinseln stärker '
                                            'entfernen.',
 'tooltip.step1.photo_scan_fill_small_holes': 'Ein = kleine Löcher innerhalb echter Flächen reduzieren.',
 'tooltip.step1.photo_scan_foreground_distance': 'Weniger = schwache Farben eher Motiv. Mehr = Hintergrund strenger '
                                                 'trennen.',
 'tooltip.step1.photo_scan_max_colors': 'Weniger = grobe Farbgruppen. Mehr = mehr Motivfarben.',
 'tooltip.step1.photo_scan_min_area': 'Weniger = feine Teile behalten. Mehr = kleine Flecken entfernen.',
 'tooltip.step1.photo_scan_noise': 'Weniger = mehr Textur behalten. Mehr = Rauschen stärker glätten.',
 'tooltip.step1.photo_scan_object_mask_first': 'Ein = zuerst wahrscheinliche Motivbereiche suchen. Hilft bei '
                                               'Papierstruktur und fleckigem Hintergrund.',
 'tooltip.step1.photo_scan_protect_background': 'Aus = normal. Ein = Papier/Hintergrund sperren, damit er keine '
                                                'Zielfarbe wird.',
 'tooltip.step1.photo_scan_weak_contrast': 'Mehr = kontrastarme dünne Details, schwache Schrift und feine Linien '
                                           'werden stärker gerettet.',
 'tooltip.step1.rotation': 'Dreht das Zwischenbild. Diese Rotation wird für Schritt 2 und Export übernommen.',
 'tooltip.step1.threshold': 'Weniger = Farben strenger trennen. Mehr = ähnliche Farben zusammenfassen.',
 'tooltip.step1.white_point': 'Weniger = helle Bereiche werden schneller weiß. Mehr = mehr helle Details.',
 'tooltip.step2.anchor_min_distance': 'Entfernt benachbarte Punkte desselben Pfads, wenn sie näher als dieser Abstand '
                                      'liegen. Andere Pfade bleiben unberührt.',
 'tooltip.step2.bridge_count': 'Weniger = weniger Unterbrechungen. Mehr = Teile stabiler verbunden.',
 'tooltip.step2.bridge_width_mm': 'Weniger = schmale Stege. Mehr = breite Stege.',
 'tooltip.step2.bridge_width_percent': 'Weniger = feste mm wichtiger. Mehr = Breite abhängig vom Bild.',
 'tooltip.step2.cad_deviation': 'Douglas-Peucker-Abweichung in Pixeln. 0.10 sehr genau, 0.80 ruhiger, 3.00 stark '
                                'vereinfacht.',
 'tooltip.step2.dedupe_tolerance': 'Weniger = strenger. Mehr = ähnliche Doppellinien entfernen.',
 'tooltip.step2.delete_small': 'Aus = nichts löschen. mm/% = kleine Konturen filtern.',
 'tooltip.step2.delete_small_mm': 'Weniger = mehr kleine Teile. Mehr = mehr kleine Teile löschen.',
 'tooltip.step2.delete_small_percent': 'Weniger = mehr Details. Mehr = nur größere Objekte behalten.',
 'tooltip.step2.global_epsilon': 'Maximale erlaubte Abweichung in Pixeln. Weniger = mehr Punkte/Details. Mehr = '
                                 'weniger Punkte/CAD-freundlicher.',
 'tooltip.step2.hole_scale': 'Weniger = Innenlöcher kleiner. Mehr = Innenlöcher größer.',
 'tooltip.step2.internal_scale': 'Weniger = schneller. Mehr = feinere Erkennung, langsamer.',
 'tooltip.step2.merge_lines': 'Weniger = Linien getrennt. Mehr = nahe Linien verbinden.',
 'tooltip.step2.pixel_to_mm': 'Weniger = kleinerer Export. Mehr = größerer Export.',
 'tooltip.step2.preprocess_blur': 'Weniger = schärfer. Mehr = Pixelkanten ruhiger.',
 'tooltip.step2.preprocess_edges': 'Weniger = rastertreuer. Mehr = Kanten beruhigter.',
 'tooltip.step2.preprocess_noise': 'Weniger = Kleindetails behalten. Mehr = kleine Störungen löschen.',
 'tooltip.step2.scale_export_tolerance_percent': 'Weniger = genauer und mehr Punkte. Mehr = stärker vereinfacht, '
                                                 'bezogen auf die aktuelle Bildgröße.',
 'tooltip.step2.smart_corner_angle': 'Weniger = mehr glätten. Mehr = mehr Ecken schützen.',
 'tooltip.step2.smart_curve_strength': 'Weniger = originaler. Mehr = Kurven ruhiger.',
 'tooltip.step2.smart_line_tolerance': 'Weniger = streng gerade. Mehr = mehr Linien als gerade behandeln.',
 'tooltip.step2.smooth_strength': 'Weniger = kantiger. Mehr = runder/glatter.',
 'tooltip.step2.zoom': 'Weniger = rauszoomen. Mehr = reinzoomen.',
 'ui.dark_mode': 'Dark-Mode',
 'ui.mode': 'Bearbeitungs-Modus:',
 'ui.mode.expert': 'Experte',
 'ui.mode.simple': 'Einfach',
 'ui.theme.classic': 'Klassisch (Illustrator/Corel-Style)',
 'ui.theme.modern': 'Modern',
 'vector_mode.area': 'Flächenkontur',
 'vector_mode.centerline': 'Mittellinie / Gravur'}


FALLBACK_EN_PATCH: dict[str, str] = {'button.apply': 'Apply',
 'button.cancel': 'Cancel',
 'button.reset': 'Reset',
 'motif_profile.logo': 'Logo / CAD / clear shapes',
 'motif_profile.mixed': 'Mixed',
 'motif_profile.organic': 'Image / organic',
 'msg.auto_expert_prompt': 'Do you want Vektorrazor to suggest suitable expert values for this image and apply them '
                           'now?\n'
                           '\n'
                           'Yes: values are set automatically and the preview is recalculated.\n'
                           'No: current values stay unchanged.',
 'msg.auto_expert_prompt_title': 'Prepare Step 2',
 'msg.auto_values_error_title': 'Auto Values Error',
 'msg.bridge_tabs_info_body': 'Bridges open closed risk contours at short positions. This keeps inner islands and '
                              'small cutout parts connected to the material so they are less likely to fall out while '
                              'cutting.\n'
                              '\n'
                              'Bridge width mm: Higher values create wider bridges, lower values keep more of the '
                              'original contour.\n'
                              'Bridge width % of image: Alternative width based on image size. If mm and percent are '
                              'set, the larger value is used.\n'
                              'Bridges per part: More bridges hold parts more securely, but add more interruptions to '
                              'the contour.\n'
                              '\n'
                              'The Cut/dropout risk preview shows which parts would be critical without bridges. '
                              'Enabled bridges are exported to SVG/DXF.',
 'msg.bridge_tabs_info_title': 'Intelligent Bridges',
 'msg.busy_detect_colors_body': 'Colors and areas are being analyzed...\n\nPlease wait a moment.',
 'msg.busy_detect_colors_title': 'Detecting colors',
 'msg.busy_load_image_body': 'Image is being loaded and analyzed...\n'
                             '\n'
                             'Please wait a moment. Clicks are blocked during this process.',
 'msg.busy_load_image_title': 'Loading image',
 'msg.busy_vector_body': 'Contours and preview are being calculated.\n'
                         '\n'
                         'Clicks in the main window are blocked while this is running.',
 'msg.busy_vector_title': 'Vectorization running',
 'msg.preview_base_body': 'The current preview is now the new base image in step 1. You can continue editing in another tab.',
 'msg.preview_base_title': 'New base applied',
 'msg.cad_cleanup_needs_redetect': 'Für dieses Fenster fehlen Rohkonturen. Bitte die Vektorisierung einmal neu '
                                   'aktualisieren.',
 'msg.detect_colors_error': 'Could not detect colors:\n{error}',
 'msg.export_intermediate_title': 'Save intermediate PNG',
 'msg.lineart_choice_contour': 'shows the actual vector paths and is usually best for CAD checking',
 'msg.lineart_choice_mask': 'shows raw raster color detection before contour finding',
 'msg.lineart_expert_hint': "You can change this later in Expert mode under 'Preview view'.",
 'msg.lineart_recommend_intro': 'This intermediate image looks like black/white line art. Detail-friendly values are '
                                'recommended: no automatic blur, no small-object deletion, and black/white rules from '
                                'the intermediate PNG.\n'
                                '\n'
                                'Choose which preview should open now:',
 'msg.lineart_recommend_title': 'Black/White Line Art Detected',
 'msg.logo_mask_error': 'Could not create logo mask:\n{error}',
 'step1.logo_direct_black': 'Convert motif color technically to black',
 'status.logo_direct_black_created': 'Motif color converted technically to black.',
 'msg.logo_direct_black_error': 'Motif color could not be converted technically to black:\n{error}',
 'msg.motif_recalculate_body': 'Should Vektorrazor recalculate the auto values using the new source type?\n'
                               '\n'
                               'Yes: Auto check runs again and the preview is updated.\n'
                               'No: Only the profile is set; you can keep adjusting values manually.',
 'msg.motif_recalculate_title': 'Source type changed',
 'msg.no_bbox_body': 'The current contour has no valid size.',
 'msg.no_bbox_title': 'No bounding box',
 'msg.no_contours_title': 'No contours',
 'msg.no_intermediate_load_first': 'Please load or edit an image first.',
 'msg.perfect_bw_body': 'This image is already a clean black/white image.\n'
                        '\n'
                        'It is kept 1:1. When switching to step 2, Vektorrazor automatically uses black/white rules.',
 'msg.perfect_bw_title': 'Black/white image detected',
 'msg.photo_scan_error': 'Could not create photo/scan cleanup:\n{error}',
 'msg.photo_scan_timeout': 'A photo/scan mask step took too long and was cancelled.\n'
                           'Try fewer target colors, stronger noise cleanup, or a lower weak-detail setting.',
 'msg.preprocess_info_body': 'Preprocessing changes only the working image used for vector detection, not the original '
                             'image.\n'
                             '\n'
                             'Blur: Higher values calm pixel edges more strongly, but can remove fine detail. Lower '
                             'values preserve detail, but keep more stair-stepping.\n'
                             'Edge calming: This belongs to preprocessing. Higher values smooth pixelated contours '
                             'more strongly so lines become straighter and more CAD-friendly. Lower values stay closer '
                             'to the raster image.\n'
                             'Minimum noise px: Higher values remove more small specks and dots. Lower values preserve '
                             'more tiny details.\n'
                             'Internal scaling: Higher values run detection at a finer working size and can clean '
                             'curves, but are slower.',
 'msg.preprocess_info_title': 'Preprocessing',
 'msg.profile_apply_body': 'This only applies the selected profile and replaces the color/layer rules. Changes to '
                           "individual colors are recalculated with 'Update preview'.",
 'msg.profile_apply_title': 'Profile applied',
 'msg.profile_title': 'Profile',
 'msg.profile_unknown': 'Unknown profile: {profile}',
 'msg.recognize_error_title': 'Detection Error',
 'msg.smart_smoothing_info_body': 'Smart CAD Smoothing analyzes the detected vector contours, after preprocessing.\n'
                                  '\n'
                                  'Straight areas such as building edges stay straighter. Round areas such as eyes, '
                                  'flowers, or ornaments are smoothed. Organic shapes such as tree trunks should not '
                                  'become perfectly technical, but keep their natural irregularity.\n'
                                  '\n'
                                  'Protect corners deg: Higher values protect more angles as corners, lower values '
                                  'smooth more transitions.\n'
                                  'Straight line tolerance px: Higher values classify more regions as straight lines, '
                                  'lower values are stricter.\n'
                                  'Curve smoothing: Higher values make curves rounder and calmer, lower values '
                                  'preserve more original irregularity.',
 'msg.smart_smoothing_info_title': 'Smart CAD Smoothing',
 'msg.step1_auto_prompt_body': 'Should Vektorrazor analyze the image after loading and suggest suitable values?\n'
                               '\n'
                               'Yes: auto detection starts after loading.\n'
                               'No: only load the image; you adjust values yourself.',
 'msg.step1_auto_prompt_title': 'Use auto mode for this image?',
 'msg.step1_recommend_bw': 'This image looks like high-contrast black/white line art.\n'
                           '\n'
                           'Recommendation: create a black/white mask instead of carrying many residual edge colors '
                           'into vectorization.\n'
                           'Suggestion:\n'
                           '- Logo threshold: {threshold}\n'
                           '- Background radius: {blur}\n'
                           '- fine details are preserved without extra pixel cleanup\n'
                           '- then check contour lines in step 2\n'
                           '\n'
                           'Apply now?\n'
                           '\n'
                           'No = stay on the matching tab only, values are not changed.',
 'msg.step1_recommend_color': 'This image contains multiple real colors.\n'
                              '\n'
                              'Recommendation: reduce colors and assign technical target RGB values.\n'
                              'Suggestion:\n'
                              '- Threshold: {threshold}\n'
                              '- Max. colors: {suggested_colors}\n'
                              '- Min. area: {min_area}\n'
                              '- Suppress noise: {noise}\n'
                              'Then review the color table.\n'
                              '\n'
                              'Apply now?\n'
                              '\n'
                              'No = stay on the matching tab only, values are not changed.',
 'msg.step1_recommend_existing_bw': 'This image already looks very clean and high-contrast. Editing in step 1 is probably not necessary.\n\nUse the existing image unchanged?\n\nYes: keep it 1:1 as the intermediate image and use black/white rules in step 2.\nNo: open manual editing.',
 'msg.step1_recommend_manual': 'This image does not match a clear automatic mode.\n'
                               '\n'
                               'Recommendation: manual color mapping.\n'
                               'You can click a color in the original image and assign the target RGB directly.\n'
                               '\n'
                               'The matching tab has already been opened.',
 'msg.step1_recommend_mask': 'This image looks like a bright/gray logo on a bright or gradient background.\n'
                             '\n'
                             'Recommendation: create a logo mask.\n'
                             'The values were derived from the image, not fixed defaults.\n'
                             '\n'
                             'Suggestion:\n'
                             '- Logo threshold: {threshold}\n'
                             '- Background radius: {blur}\n'
                             '- estimated mask area: about {coverage:.1f}%\n'
                             '- target range from analysis: about {target:.1f}%\n'
                             '\n'
                             'Apply now?\n'
                             '\n'
                             'No = stay on the matching tab only, values are not changed.',
 'msg.step1_recommend_photo_scan': 'This image looks difficult or like a photo/scan of a logo.\n'
                                   '\n'
                                   'Problem score: {score}\n'
                                   '- many color gradations: about {colors}\n'
                                   '- background noise: {noise:.1f}\n'
                                   '- small specks/edge islands: {specks}\n'
                                   '\n'
                                   'Recommendation: run photo/scan auto mode. It calculates several variants and '
                                   'automatically applies the technically calmest intermediate image. For very '
                                   'difficult images, manual color selection with high tolerance can still be better.\n'
                                   '\n'
                                   'Apply auto mode now?',
 'msg.step1_recommend_title': 'Recommendation for Step 1',
 'msg.stl_export_done': 'STL was saved:\n'
                        '{out}\n'
                        '\n'
                        'Surfaces: {surfaces}\n'
                        'Extrusion: {extrusion:.2f} mm\n'
                        'Facets: {facets}',
 'msg.stl_invalid_extrusion': 'Enter an extrusion value greater than 0 mm.',
 'msg.stl_no_selection_body': 'Please select at least one surface for STL export.',
 'msg.stl_no_selection_title': 'No surface selected',
 'msg.stl_no_surfaces_body': 'STL export needs closed exportable surfaces. Please generate a suitable preview first.',
 'msg.stl_no_surfaces_title': 'No STL surfaces',
 'msg.target_size_body': 'Enter a target width or target height in mm.',
 'msg.target_size_title': 'Target size missing',
 'msg.welcome_body': 'Vektorrazor works in two steps:\n'
                     '\n'
                     '1. Prepare image\n'
                     'Load an image and adjust colors if needed so the contrast is clear.\n'
                     'When loading an image, Auto mode suggests suitable values. If you want to adjust things '
                     'yourself, choose No.\n'
                     '\n'
                     '2. Vectorize\n'
                     'When the intermediate image looks right, continue to step 2.\n'
                     'There Vektorrazor detects the shapes and creates the preview and export.',
 'msg.welcome_title': 'Welcome',
 'nav.scale_export': 'Scale and export DXF / SVG / STL',
 'preview_mode.cut_risk': 'Cut/dropout risk',
 'progress.auto_applied': 'Auto values applied | Score: {score:.3f} | Points: {points}',
 'progress.auto_error': 'Auto values error',
 'progress.auto_prepare': 'Preparing auto values...',
 'progress.auto_test': 'Auto values: test {index}/{total}...',
 'progress.build_color_table': 'Building color table...',
 'progress.detect_colors': 'Analyzing colors...',
 'progress.detect_colors_fallback': 'Checking colors again...',
 'progress.detect_error': 'Detection error',
 'progress.detecting_contours': 'Detecting contours...',
 'progress.export_done': 'Export complete: {out} | DXF {dxf_version} | duplicate-line cleanup: {cad_cleanup}',
 'progress.filter_small_objects': 'Filtering small objects...',
 'progress.load_image': 'Loading image...',
 'progress.photo_scan_auto_candidate': 'Auto variant {index}/{total}: checking {variant}...',
 'progress.photo_scan_background': 'Creating background mask...',
    'progress.photo_scan_faded_background': 'Estimating paper/lighting variation...',
    'progress.photo_scan_faded_contrast': 'Enhancing weak print...',
    'progress.photo_scan_faded_threshold': 'Finding local print traces...',
 'progress.photo_scan_cleanup': 'Cleaning masks...',
 'progress.photo_scan_cluster': 'Clustering colors...',
 'progress.photo_scan_detail_masks': 'Creating detail masks...',
 'progress.photo_scan_hysteresis': 'Connecting weak pixels...',
 'progress.photo_scan_main_masks': 'Creating main masks...',
 'progress.photo_scan_masks': 'Creating masks...',
 'progress.prepare_image': 'Preparing image...',
 'progress.read_vector_rules': 'Reading vector rules...',
 'progress.render_preview': 'Rendering preview...',
 'progress.writing_file': 'Writing file...',
 'startup_preset.choose': 'Which source type fits best? You can change this anytime later in step 2.',
 'startup_preset.logo.desc': 'Clear edges, calmer straight lines, fewer points and Smart CAD Smoothing more likely '
                             'enabled.',
 'startup_preset.logo.title': 'Logo / CAD / clear shapes',
 'startup_preset.mixed.desc': 'Balanced preset between clear shapes and organic subjects.',
 'startup_preset.mixed.title': 'Mixed',
 'startup_preset.organic.desc': 'Preserve more detail, avoid hard straightening and treat organic contours carefully.',
 'startup_preset.organic.title': 'Image / organic',
 'status.analysis_cancel_requested': 'Cancel requested...',
 'status.analysis_cancelled': 'Analysis cancelled.',
 'status.cad_cleanup_applied': 'CAD point reduction applied: {value}px',
 'status.cad_points': 'Points: {before} → {after}',
 'status.color_copied_to_row': 'Color {rgb} copied to row #{row}.',
 'status.detected_color_regions': '{count} color regions detected. Target RGB can be adjusted directly in the table.',
 'status.epsilon_applied_all': 'CAD deviation applied to all colors: {value}px',
 'status.existing_image_skipped': 'Existing image was not applied automatically. Manual editing opened.',
 'status.existing_image_used': 'Existing image kept unchanged. Step 2 uses matching black/white rules.',
 'status.high_detail_applied': 'High detail fidelity enabled.',
 'status.image_loaded': 'Image loaded: {name} | {width} x {height}px',
 'status.intermediate_saved': 'Intermediate PNG saved: {path}',
 'status.invalid_base_color': 'Invalid base color: {error}',
 'status.invalid_manual_color': 'Invalid manual color: {error}',
 'status.lineart_preset_applied': 'Black/white line-art preset applied.',
 'status.logo_mask_created': 'Logo mask created. This mask can be vectorized directly in step 2.',
 'status.manual_row_selected': 'Selected row: #{row} | click in original image copies the color.',
 'status.no_contours_detected': 'No contours detected yet.',
 'status.no_path_hit': 'No path hit.',
 'status.no_path_selected': 'No path selected.',
 'status.path_removed': 'Path removed. Remaining: {remaining} | Export active: {exported} | Points: {points}',
 'status.path_removed_details': 'Removed: path #{index} | layer {layer} | points {points}',
 'status.path_selected_details': 'Selected: path #{index} | layer {layer} | points {points} | area about {area:.0f}px²',
 'status.path_selection_changed': 'Path selection changed. Del or the button removes selected paths.',
 'status.paths_removed_count': 'Removed: {count} paths',
 'status.paths_selected_count': '{count} paths selected | Del or button removes all selected paths',
 'status.perfect_bw_ready': 'Perfect black/white image detected: kept 1:1, step 2 uses black/white rules.',
 'status.preview_base_ready': 'Current preview applied as new base image.',
 'status.photo_scan_done': 'Photo/scan cleanup created: {variant}, {count} target colors, problem score {score}, noise '
                           '{noise:.1f}, technical score {tech:.1f}.',
 'status.photo_scan_mode_auto': 'Auto mode: multiple technical variants will be scored.',
 'status.photo_scan_mode_bw': 'Black/white mode: adaptive light/dark mask for line art and text.',
    'status.photo_scan_mode_faded': 'Faded print mode: paper/lighting variation is removed and weak print traces are extracted as a black/white mask.',
 'status.photo_scan_mode_clean': 'Cleaner mode: stronger smoothing and speck removal.',
 'status.photo_scan_mode_color': 'Color mode: several main colors are preserved.',
 'status.photo_scan_mode_detail': 'Detail mode: fine lines and weak details are protected more strongly.',
 'status.pixel_color_at': 'Pixel color at x={x}, y={y}: {rgb}',
 'status.png_loaded': 'PNG loaded: {name}',
 'status.preview_error': 'Preview error: {error}',
 'status.problem_hint_high_tolerance': 'High tolerance set for manual color mapping.',
 'status.problem_hint_manual_opened': 'Manual color selection opened. Click the main colors in the original image.',
 'status.problem_hint_shown': 'Hint: For this difficult image, manual color selection with higher tolerance may create '
                              'better areas.',
 'status.profile_loaded': 'Profile loaded: {profile}',
 'status.progress_percent': '{percent}% - {status}',
 'status.scale_calculated': 'Scale set: {pixel_to_mm} mm/px. CAD deviation equals {tolerance_px}px.',
 'status.scale_export_points': 'Points: {before} -> {after} | deviation {px}px / {mm} mm',
 'status.selection_mode_off': 'Selection mode off: preview can be panned normally.',
 'status.selection_mode_on': 'Selection mode active: click in vector preview selects a path. CTRL adds, ALT removes '
                             'directly.',
 'status.startup_preset_logo': 'Startup preset applied: Logo / CAD / clear shapes.',
 'status.startup_preset_mixed': 'Startup preset applied: Mixed.',
 'status.startup_preset_organic': 'Startup preset applied: Image / organic.',
 'status.step1_auto_skipped': 'Image loaded. Auto detection was skipped.',
 'status.step1_recommend_bw_applied': 'Recommendation applied: black/white mask created.',
 'status.step1_recommend_bw_skipped': 'Recommendation: black/white mask. Values were not changed.',
 'status.step1_recommend_color_applied': 'Recommendation applied: reduce colors.',
 'status.step1_recommend_color_skipped': 'Recommendation: reduce colors. Values were not changed.',
 'status.step1_recommend_manual': 'No clear automatic mode detected: manual color mapping recommended.',
 'status.step1_recommend_mask_applied': 'Recommendation applied: logo mask with threshold {threshold}, radius {blur}.',
 'status.step1_recommend_mask_skipped': 'Recommendation: logo mask. Values were not changed.',
 'status.step1_recommend_photo_scan_applied': 'Recommendation applied: photo/scan cleanup with problem score {score}.',
 'status.step1_recommend_photo_scan_skipped': 'Recommendation: photo/scan cleanup with problem score {score}. Values '
                                              'were not changed.',
 'status.stl_export_done': 'STL exported: {facets} facets | {out}',
 'status.stl_selected_surfaces': 'STL surfaces selected: {selected}/{total}',
 'status.stl_selected_surfaces_holes': 'STL: extruded surfaces {selected}/{total} | cut-out holes '
                                       '{holes}/{total_holes}',
 'status.tolerance_applied_all': 'Tolerance applied to all colors: {value}',
 'status.vector_source_ready_autofill': 'Edited image is ready for step 2. Color/layer rules were suggested '
                                        'automatically.',
 'status.vector_source_ready_transferred': 'Edited image is ready for step 2. Color/layer rules were imported from the '
                                           'intermediate PNG.',
 'status.workflow_reset': 'Workflow reset. Please load a new image.',
 'step1.apply_high_tolerance': 'Apply high tolerance',
 'step1.methods_intro': 'Each working mode is a separate way to create the technical intermediate image.\nYou can use the current preview below as a new base and then continue in another mode.'
                        'the current preview can be used as a new base if needed.',
 'step1.mode_selector': 'Working mode',
 'step1.mode_choose': 'Method:',
 'step1.mode.prep': 'Image preparation',
 'step1.mode.basic': 'Basic: detect colors',
 'step1.mode.manual': 'Advanced: manual',
 'step1.mode.logo': 'Logo mask',
 'step1.mode.photo_scan': 'Clean photo/scan logo',
 'step1.mode_hint.prep': 'Prepare brightness, contrast, levels, gamma, and rotation.\nAfterwards you can use the preview as a new base or continue in another mode.',
 'step1.mode_hint.basic': 'Automatic color detection for already fairly clear logos.\nSimilar colors are collected and converted into exact technical RGB target colors.',
 'step1.mode_hint.manual': 'Manual color selection with picker and custom tolerance.\nUseful when you know exactly which main colors should be kept or replaced.',
 'step1.mode_hint.logo': 'Local contrast mask for gray logos, shadows, or slight gradients.\nUseful for simple logos that need to be separated from the background.',
 'step1.mode_hint.photo_scan': 'Technical auto mode for difficult photos and scans.\nCalm paper/background, remove noise, find weak details, and create a few clear target colors.',
 'step1.open_manual_colors': 'Open manual colors',
 'step1.photo_scan_apply': 'Apply photo/scan cleanup',
 'step1.photo_scan_apply_auto': 'Auto: find best technical area',
 'step1.photo_scan_apply_current': 'Test current settings',
 'step1.photo_scan_close_lines': 'Close line gaps',
 'step1.photo_scan_despeckle': 'Remove point noise',
 'step1.photo_scan_despeckle_area': 'Despeckle / min island',
 'step1.photo_scan_fill_small_holes': 'Fill small holes in areas',
 'step1.photo_scan_foreground_distance': 'Color distance from background',
 'step1.photo_scan_hint': 'Technical auto mode for difficult photos and scans: detects paper/background, calculates '
                          'several variants, reduces specks, protects fine lines, and creates a few clean target RGB '
                          'colors. No AI, no training, no model dependency.',
 'step1.photo_scan_max_colors': 'Target colors',
 'step1.photo_scan_min_area': 'Min. area',
 'step1.photo_scan_mode': 'Photo/scan mode',
 'step1.photo_scan_mode_auto': 'Auto',
 'step1.photo_scan_mode_balanced': 'Balanced',
 'step1.photo_scan_mode_bw': 'black/white',
    'step1.photo_scan_mode_faded': 'faded print',
 'step1.photo_scan_mode_clean': 'cleaner',
 'step1.photo_scan_mode_color': 'color',
 'step1.photo_scan_mode_detail': 'more detail',
 'step1.photo_scan_noise': 'Clean noise',
 'step1.photo_scan_object_mask_first': 'Create object mask first',
 'step1.photo_scan_optional': 'Optional fine tuning',
 'step1.photo_scan_protect_background': 'Protect background/paper texture',
 'step1.photo_scan_protect_thin_lines': 'Protect thin lines',
 'step1.photo_scan_weak_contrast': 'Detect weak / fine details',
 'step1.problem_hint_body': 'For difficult images, manual color selection is often better:\n'
                            'choose the main colors, use high tolerance, and replace them with clear technical colors. '
                            'This collects color variation and noise more reliably and creates calmer areas for later '
                            'vectorization.',
 'step1.problem_hint_title': 'Alternative for difficult images',
 'step1.reset_workflow': 'Start over',
 'step1.update_hint': "Note: 'Continue to vectorizing' imports the current preview and switches to step 2. 'Use preview as new base' stays in step 1 and turns the preview into the new source image.",
 'step1.update_intermediate': 'Use preview as new base',
 'step1.use_preview_as_base': 'Use preview as new base',
 'step1.rotate_left': '↺ Rotate left',
 'step1.rotate_right': '↻ Rotate right',
 'step1.rotation': 'Rotation °',
 'step1.tab_photo_scan': 'Clean photo/scan logo',
 'step2.anchor_cleanup': 'Remove nearby anchor points',
 'step2.anchor_min_distance': 'Minimum distance px',
 'step2.anchor_point_size': 'Anchor point size',
 'step2.auto_expert_from_image': 'Suggest Auto Values (Optional)',
 'step2.bbox': 'Bounding box:',
 'step2.bridge_count': 'Bridges per part',
 'step2.bridge_tabs': 'Add intelligent bridges',
 'step2.bridge_width_mm': 'Bridge width mm',
 'step2.bridge_width_percent': 'Bridge width % of image',
 'step2.cad_cleanup_after': 'After: simplified',
 'step2.cad_cleanup_before': 'Current result',
 'step2.cad_cleanup_title': 'Simplify points/paths',
 'step2.cad_deviation': 'CAD deviation / contour accuracy px',
 'step2.cad_tolerance_mm': 'CAD deviation mm',
 'step2.calculate_scale': 'Calculate scale from target size',
 'step2.choose_output': 'Set save location',
 'step2.export_stl': 'Export as STL',
 'step2.global_epsilon': 'CAD deviation / contour accuracy px',
 'step2.high_detail': 'High Detail Fidelity',
 'step2.hole_scale': 'Hole size / inner holes',
 'step2.keep_proportions': 'Keep proportions',
 'step2.motif_profile': 'Source type:',
 'step2.motif_profile_group': 'Source type / automatic values',
 'step2.open_cad_cleanup': 'Simplify points/paths',
 'step2.preexport_cleanup': '1  Pre-export polish: simplify paths',
 'step2.export_final': '2  Export DXF / SVG',
 'step2.export_scaled': '2.1  Scale / DXF / SVG / STL',
 'step2.pixel_to_mm': 'Pixels to mm:',
 'step2.save_options': 'Save options',
 'step2.scale_export_after': 'Export preview',
 'step2.scale_export_before': 'Current result',
 'step2.scale_export_enable': 'Simplify contours before export',
 'step2.scale_export_title': 'Scale and export DXF / SVG / STL',
 'step2.scale_export_tolerance_percent': 'Contour accuracy % of image size',
 'step2.show_anchor_points': 'Show anchor points',
 'step2.stl_export_title': 'Select STL surfaces and extrude',
 'step2.stl_extrusion_mm': 'Extrusion mm:',
 'step2.stl_holes_all_cutout': 'Cut out all holes',
 'step2.stl_holes_none_cutout': 'Cut out no holes',
 'step2.stl_preview': 'STL selection / current export preview',
 'step2.stl_save_button': 'Save selected surfaces as STL',
 'step2.stl_save_dialog_title': 'Save STL',
 'step2.stl_select_all': 'Select all surfaces',
 'step2.stl_select_hint': 'Click the preview to toggle outer surfaces or inner holes. Purple outer surfaces are '
                          'extruded. Red inner holes are cut out and therefore NOT extruded. Orange inner holes are '
                          'filled/extruded. CTRL is not required.',
 'step2.stl_select_none': 'Select none',
 'step2.stl_selection_legend': 'Legend: purple = extruded | gray = outer surface not extruded | red with cross = hole '
                               'is cut out/not extruded | orange with cross = hole is filled/extruded.',
 'step2.target_height_mm': 'Target height mm:',
 'step2.target_width_mm': 'Target width mm:',
 'step2.use_percent_values': 'Use % of image size',
 'tooltip.step1.alpha_from': 'Less = count more transparent pixels. More = ignore transparency more.',
 'tooltip.step1.black_point': 'Less = more shadows. More = dark areas become black sooner.',
 'tooltip.step1.brightness': 'Less = darker. More = brighter.',
 'tooltip.step1.contrast': 'Less = flatter. More = stronger separation.',
 'tooltip.step1.gamma': 'Less = brighter midtones. More = darker midtones.',
 'tooltip.step1.logo_radius': 'Less = local detail. More = ignore shadows/gradients more.',
 'tooltip.step1.logo_threshold': 'Less = more becomes logo. More = only stronger strokes.',
 'tooltip.step1.max_colors': 'Less = few main colors. More = more color shades.',
 'tooltip.step1.min_area': 'Less = keep tiny details. More = ignore small noise.',
 'tooltip.step1.noise_suppression': 'Less = more detail. More = remove more noise.',
 'tooltip.step1.photo_scan_close_lines': 'On = carefully close small gaps in lines and circles.',
 'tooltip.step1.photo_scan_despeckle': 'Off = keep mini islands. On = remove very small foreign specks per color mask.',
 'tooltip.step1.photo_scan_despeckle_area': 'Less = keep more small details. More = remove small speck islands more '
                                            'strongly.',
 'tooltip.step1.photo_scan_fill_small_holes': 'On = reduce small holes inside real filled areas.',
 'tooltip.step1.photo_scan_foreground_distance': 'Less = weak colors become subject sooner. More = stricter background '
                                                 'split.',
 'tooltip.step1.photo_scan_max_colors': 'Less = coarse color groups. More = more subject colors.',
 'tooltip.step1.photo_scan_min_area': 'Less = keep fine parts. More = remove small specks.',
 'tooltip.step1.photo_scan_noise': 'Less = keep more texture. More = clean noise harder.',
 'tooltip.step1.photo_scan_object_mask_first': 'On = detect likely subject areas first. Helps with paper texture and '
                                               'blotchy backgrounds.',
 'tooltip.step1.photo_scan_protect_background': 'Off = normal. On = lock paper/background so it does not become a '
                                                'target color.',
 'tooltip.step1.photo_scan_weak_contrast': 'More = recover low-contrast fine details, weak text, and thin lines more '
                                           'strongly.',
 'tooltip.step1.rotation': 'Rotates the intermediate image. This rotation is used for step 2 and export.',
 'tooltip.step1.threshold': 'Less = stricter color split. More = merge similar colors.',
 'tooltip.step1.white_point': 'Less = bright areas become white sooner. More = more bright detail.',
 'tooltip.step2.anchor_min_distance': 'Removes neighboring points from the same path if they are closer than this '
                                      'distance. Other paths are not touched.',
 'tooltip.step2.bridge_count': 'Less = fewer interruptions. More = parts are held more securely.',
 'tooltip.step2.bridge_width_mm': 'Less = narrow bridges. More = wider bridges.',
 'tooltip.step2.bridge_width_percent': 'Less = fixed mm matters more. More = width follows image size.',
 'tooltip.step2.cad_deviation': 'Douglas-Peucker deviation in pixels. 0.10 very accurate, 0.80 calmer, 3.00 strongly '
                                'simplified.',
 'tooltip.step2.dedupe_tolerance': 'Less = stricter. More = remove similar duplicate lines.',
 'tooltip.step2.delete_small': 'Off = delete nothing. mm/% = filter small contours.',
 'tooltip.step2.delete_small_mm': 'Less = keep more small parts. More = delete more small parts.',
 'tooltip.step2.delete_small_percent': 'Less = more detail. More = keep only larger objects.',
 'tooltip.step2.global_epsilon': 'Maximum allowed deviation in pixels. Less = more points/detail. More = fewer '
                                 'points/more CAD-friendly.',
 'tooltip.step2.hole_scale': 'Less = smaller inner holes. More = larger inner holes.',
 'tooltip.step2.internal_scale': 'Less = faster. More = finer detection, slower.',
 'tooltip.step2.merge_lines': 'Less = keep lines separate. More = connect nearby lines.',
 'tooltip.step2.pixel_to_mm': 'Less = smaller export. More = larger export.',
 'tooltip.step2.preprocess_blur': 'Less = sharper. More = calmer pixel edges.',
 'tooltip.step2.preprocess_edges': 'Less = closer to raster. More = calmer edges.',
 'tooltip.step2.preprocess_noise': 'Less = keep tiny detail. More = delete small noise.',
 'tooltip.step2.scale_export_tolerance_percent': 'Less = more accurate and more points. More = stronger simplification '
                                                 'relative to image size.',
 'tooltip.step2.smart_corner_angle': 'Less = smooth more. More = protect more corners.',
 'tooltip.step2.smart_curve_strength': 'Less = more original. More = calmer curves.',
 'tooltip.step2.smart_line_tolerance': 'Less = stricter straight lines. More = treat more lines as straight.',
 'tooltip.step2.smooth_strength': 'Less = more angular. More = rounder/smoother.',
 'tooltip.step2.zoom': 'Less = zoom out. More = zoom in.'}


def fallback_for_language(code: str) -> dict[str, str]:
    fallback = dict(FALLBACK_DE)
    if code == "en":
        fallback.update(FALLBACK_EN_PATCH)
    return fallback

def _source_dir() -> Path:
    return Path(__file__).resolve().parent


def _runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _source_dir()


def _external_lang_dirs() -> list[Path]:
    """Mögliche Ordner für externe Sprachdateien.

    Standard ist jetzt derselbe Benutzerordner wie für settings.json:
    ``vektorrazor_config/lang`` direkt neben der EXE bzw. im Quellordner.
    ``config/lang`` und ``Config/lang`` werden bewusst nicht mehr durchsucht,
    damit Sprache und Einstellungen eindeutig an einer Stelle liegen.
    """
    base = _runtime_dir()
    source = _source_dir()
    dirs = [
        base / "vektorrazor_config" / "lang",
        base / "lang",
        source / "vektorrazor_config" / "lang",
        source / "lang",
        source,
    ]
    result: list[Path] = []
    seen: set[str] = set()
    for item in dirs:
        try:
            key = str(item.resolve()).lower()
        except Exception:
            key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def validate_language_file(language_dict: dict[str, Any], fallback_dict: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    clean = {str(k): str(v) for k, v in language_dict.items() if isinstance(k, str) and isinstance(v, str)}
    missing = sorted(k for k in fallback_dict if k not in clean)
    merged = dict(fallback_dict)
    merged.update(clean)
    return merged, missing


def _normalize_german_texts(language_dict: dict[str, str]) -> None:
    """Gezielte Korrekturen für ältere DE-Dateien ohne Umlaute."""
    replacements = {
        "language.incomplete": "Sprachdatei unvollständig, Fallback für fehlende Texte verwendet.",
        "nav.back": "<- Zurück",
        "nav.next_vectorize": "Weiter zur Vektorisierung ->",
        "nav.back_to_step1": "<- Zurück zu Schritt 1",
        "nav.scale_export": "Skalieren und DXF / SVG / STL exportieren",
        "step1.white_point": "Weißpunkt",
        "step1.reset": "Zurücksetzen",
        "step1.min_area": "Min. Fläche",
        "step1.reassign": "Kontrast neu färben",
        "step1.rows_header": "Aktiv  Quelle / Anteil  → Ziel-RGB",
        "step1.delete_selected": "- selektierte löschen",
        "step1.clean_pixels": "kleine Pixelstörungen glätten",
        "step1.methods_intro": "Jeder Arbeitsmodus ist ein eigener Weg zur technischen Zwischenstufe.\nDu kannst die aktuelle Vorschau unten als neue Grundlage übernehmen und danach in einem anderen Modus weiterarbeiten.",
        "step2.compatibility": "Kompatibilität:",
        "step2.merge_lines": "Linien zusammenführen px",
        "step2.fill_svg": "SVG-Flächen füllen (Export)",
        "step2.group_connected_paths": "Zusammenhängende Pfade gruppieren (SVG)",
        "step2.bezier_svg": "Bezier für SVG",
        "step2.smart_corner_angle": "Ecken schützen Grad",
        "step2.smart_curve_strength": "Kurven-Glättung",
        "step2.bridge_tabs": "Intelligente Brücken setzen",
        "step2.bridge_width_mm": "Brückenbreite mm",
        "step2.bridge_width_percent": "Brückenbreite % vom Bild",
        "step2.bridge_count": "Brücken pro Teil",
        "step2.percent_area": "% Bildfläche",
        "button.choose": "wählen",
        "button.reset": "Zurücksetzen",
        "status.scale_export_points": "Punkte: {before} → {after} | Abweichung {px}px / {mm} mm",
        "msg.step1_recommend_existing_bw": "Dieses Bild wirkt bereits sehr sauber und kontrastreich. Eine Bearbeitung in Schritt 1 ist wahrscheinlich nicht nötig.\n\nVorhandenes Bild unverändert verwenden?\n\nJa: 1:1 als Zwischenbild übernehmen und in Schritt 2 Schwarz/Weiß-Regeln nutzen.\nNein: manuelle Bearbeitung öffnen.",
        "step1.logo_direct_black": "Motivfarbe technisch auf Schwarz umsetzen",
        "status.logo_direct_black_created": "Motivfarbe technisch auf Schwarz umgesetzt.",
        "msg.logo_direct_black_error": "Motivfarbe konnte nicht technisch auf Schwarz umgesetzt werden:\n{error}",
    }
    for key, value in replacements.items():
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
