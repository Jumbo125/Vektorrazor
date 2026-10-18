# Vektorrazor

Tkinter-Desktop-App (Windows), die PNG-Logos/Bilder in CAD-taugliche Vektordaten
umwandelt (SVG, DXF, optional STL). Zweistufiger Workflow:

1. **Schritt 1 – Bild vorbereiten**: Helligkeit/Kontrast/Tonwert, Rotation,
   automatische oder manuelle Farbumsetzung, Logo-Masken-Modus, Foto-/Scan-
   Bereinigung, Radierer, KI-Upscaling. Ziel: ein Zwischen-PNG mit exakten,
   technischen RGB-Flächenfarben.
2. **Schritt 2 – Vektorisieren**: Aus dem Zwischen-PNG werden per Farbregeln
   (RGB + Toleranz) Konturen erkannt, vereinfacht/geglättet und als SVG/DXF
   (und optional STL per Extrusion) exportiert.

Alle Texte sind i18n-fähig, Deutsch ist die feste Fallback-Sprache.

## Datei-Übersicht (Top-Level)

- **main.py** – Minimaler Einstiegspunkt, startet `workflow_app.main()`. Bleibt
  bewusst leer, damit andere Module importierbar sind ohne GUI-Start.

- **workflow_app.py** (sehr groß, >300KB) – Zentrale `WorkflowApp(tk.Tk)`-Klasse:
  gesamter Anwendungszustand (tk-Variablen, Bilddaten, erkannte Konturen),
  Event-Handler, Preview-Rendering, Undo/Reset, Export-Orchestrierung. Ruft die
  UI-Aufbaufunktionen aus `ui_step1.py`/`ui_step2.py` per Delegation auf
  (`self._build_step1()` → `ui_step1._build_step1(self)` usw.). Wegen der
  Dateigröße: gezielt mit Grep/Offset lesen statt komplett laden.
  - Wichtige Preview-Modi in Schritt 2 (`preview_mode_var`: `object` / `contour`
    / `mask` / `cut_risk`), gerendert über `render_vector_preview()`.
  - `build_filled_mask_preview_image()` = "Farbmaske"-Ansicht: reine Raster-
    Farbmaske je Regel-RGB (`rule.rgb`), **vor** Vektor-/Lochlogik.
  - `build_object_check_preview_image()` = "Objektcheck"-Ansicht: nutzt
    tatsächliche Vektorpfade (`detected_contours`) mit eigener Palette
    (nicht identisch mit den echten Ziel-RGBs).
  - Export läuft über `export_vector_file()` / `_export_contours_to_file()`,
    die `vector.export_svg(...)` bzw. `vector.export_dxf(...)` aufrufen.

- **ui_step1.py** – Reiner UI-Aufbau für Schritt 1 (Frames, Tabs, Scales,
  Buttons). Modi: Bildvorbereitung, Basis-Farberkennung, manuelle Umsetzung,
  Radierer, Logo-Maske, Foto-/Scan-Bereinigung, KI-Skalierung. Keine
  Bildverarbeitungslogik hier – nur Widget-Aufbau, delegiert an Methoden von
  `WorkflowApp`.

- **ui_step2.py** – Reiner UI-Aufbau für Schritt 2: Export-/DXF-Kompatibilitäts-
  Auswahl, Farben/Layer-Modal, Vektor-Optionen (sehr viele Scales/Spinboxes für
  Glättung, Ankerpunkte, Brücken/Bridge-Tabs, CAD-Bereinigung), Vorschau-Canvas
  mit Pfad-Auswahl, Export-Aktionsleiste. Enthält u. a. den Checkbutton
  **"SVG-Flächen füllen (Export)"** (`fill_closed_shapes_var`), der beim SVG-
  Export Flächen mit der jeweiligen Regel-RGB-Farbe füllt.

- **vector_engine.py** (sehr groß) – Die eigentliche Geometrie-/Export-Engine,
  ohne Kenntnis der Tk-App-Instanz:
  - Farbmasken (`make_color_mask`), Vorverarbeitung, Rauschunterdrückung,
    Skelettierung/Zentrallinien (Zhang-Suen-Thinning) für den Mittellinien-
    Modus.
  - Konturvereinfachung: `approximate_points` (cv2.approxPolyDP), Glättung
    (`smooth_contours`, `smart_smooth_contours` = eckenschützendes CAD-
    Smoothing), Ellipsen-Regularisierung für runde Formen.
  - "Bridge Tabs" (`apply_bridge_tabs`): öffnet Risikokonturen (Löcher,
    kleine Inseln) mit kurzen Stegen, damit beim Schneiden nichts herausfällt.
  - Export: `export_svg()`, `export_dxf()` (ezdxf), `export_stl_extruded()`
    (weiter unten in der Datei, nicht gelesen in dieser Session).
  - `ColorRule`/`DetectedContour`-Dataclasses sind das zentrale Datenmodell,
    das durch die ganze Pipeline gereicht wird (rule.rgb, rule.export,
    rule.layer, closed/is_hole/points).

- **recolor_engine.py** (sehr groß) – Zwei Dinge in einer Datei:
  1. Wiederverwendbare Tk-Widgets, die in `workflow_app.py`/`ui_step*.py`
     genutzt werden: `ZoomImageCanvas` (Zoom/Pan-Vorschau mit Farbpicker- und
     Overlay-Callbacks) und `ScrollableFrame`.
  2. Eine ältere eigenständige `RecolorApp(tk.Tk)` ("Bild-Umfärber GUI v4.5")
     mit eigenem Basis-/Erweitert-Modus – historischer Vorläufer von Schritt 1,
     scheint kein aktiver Einstiegspunkt der Hauptanwendung mehr zu sein,
     bleibt aber als Quelle für Hilfsfunktionen (`apply_image_preparation`,
     `parse_rgb`, `mask_for_rgb` etc.) bestehen.

- **dialogs_scale_export.py** – Ausgelagerte Toplevel-Dialoge, die den
  `WorkflowApp`-State als `app`-Parameter bekommen:
  - `open_scaled_export_dialog()`: Vorschau/Vereinfachung vor dem finalen
    Export (Ziel-mm, Toleranz-%, Ankerpunkt-Vorschau, Live-Preview).
  - `open_stl_export_dialog()`: Flächen-/Loch-Auswahl für STL-Extrusion mit
    klickbarer Vorschau (Löcher = Aussparung vs. Extrusion).

- **ai_upscale.py** – Kapselt den Aufruf der externen Real-ESRGAN-ncnn-Vulkan-
  Binary (`AiUpscalePaths`, `resolve_model_spec`, `run_ai_upscale`). Reine
  Subprocess-Integration, kein Tk-Code. Unterstützt mehrstufige Upscale-Pässe,
  wenn der gewünschte Faktor über dem größten verfügbaren Modell-Faktor liegt.

- **i18n.py** – `tr(key, **kwargs)` als zentrale Übersetzungsfunktion, JSON-
  Sprachdateien mit Deutsch (`FALLBACK_DE`, riesiges Dict direkt im Code) als
  Fallback, Tracking fehlender Keys.

## Bekannte Lücke / offener Punkt

**Export soll optional exakt so eingefärbt werden wie die "Farbmaske"-Vorschau
(Schritt 2 → Vorschau-Ansicht → Farbmaske).** Aktuell existiert in
`ui_step2.py` der Checkbutton "SVG-Flächen füllen (Export)"
(`fill_closed_shapes_var`), der beim SVG-Export Flächen mit `rule.rgb` je
Kontur füllt (`vector_engine.export_svg`, Zweig `fill_closed_shapes=True`,
ab Zeile ~1837). Das ist konzeptionell nah dran, aber:

- Die "Farbmaske"-Vorschau (`build_filled_mask_preview_image` in
  `workflow_app.py`) rendert direkt aus der Rastermaske pro Regel (`rule.rgb`
  über alle Pixel, die die Farbregel matchen), **vor** Vektorisierung/
  Lochlogik/Bridge-Tabs.
- Der SVG-Export mit `fill_closed_shapes` füllt dagegen die bereits
  vektorisierten/vereinfachten/ggf. mit Brücken aufgeschnittenen Konturen.

Bei komplexeren Bildern (überlappende Farbregeln, viele Löcher, aktive
Bridge-Tabs) kann das export-seitige Ergebnis optisch von der Farbmaske-
Vorschau abweichen. Gewünscht ist ein eigener, klar benannter Toggle
("Export wie Farbmaske einfärben" o. ä.), der die Farbzuordnung 1:1 an
`build_filled_mask_preview_image()`/`rule.rgb` je Fläche anlehnt, statt nur
die generische Flächenfüllung zu aktivieren. Ansatzpunkte für eine Umsetzung:

- Neuer `tk.BooleanVar` in `workflow_app.py` (analog `fill_closed_shapes_var`)
  + Checkbutton in `ui_step2.py` (Bereich um Zeile 364, neben
  "SVG-Flächen füllen (Export)").
  - Beim Export müsste sichergestellt werden, dass jede exportierte Fläche mit
    der Farbe der Regel eingefärbt wird, die tatsächlich in der Farbmaske für
    diesen Bereich sichtbar ist (d. h. dieselbe Regel-Reihenfolge/Priorität
    wie in `build_filled_mask_preview_image()`, nicht nur `item.rule.rgb` aus
    der bereits vektorisierten Kontur).
