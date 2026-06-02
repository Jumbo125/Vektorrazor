<p align="center">
  <img src="assets/vektorrazor_icon.png" width="180" alt="Vektorrazor Icon">
</p>

<h1 align="center">Vektorrazor</h1>

<p align="center">
  <strong>PNG logo preparation → CAD-oriented vector contours</strong>
</p>

<p align="center">
  <a href="README.de.md">🇩🇪 Deutsch</a> ·
  <a href="README.en.md">🇬🇧 English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/GUI-Tkinter-brightgreen" alt="GUI">
  <img src="https://img.shields.io/badge/Export-DXF%20%7C%20SVG-orange" alt="Export">
  <img src="https://img.shields.io/badge/License-GPLv3-blue" alt="License">
  <img src="https://img.shields.io/badge/Status-Prototype%20%2F%20CAD%20Workflow-yellow" alt="Status">
</p>

<p align="center"><strong>Copyright (C) 2026 Andreas Rottmann</strong></p>

---

## Version 2 – Update

Dieses Release verbessert den gesamten Workflow, die Bedienbarkeit und die Vorschauqualität von Vektorrazor.

### Highlights

- Dark Mode hinzugefügt
- Light Mode hinzugefügt
- Intelligente Auto-Ermittlung für Expertenwerte hinzugefügt
- UI reduziert und verbessert für einen einfacheren, übersichtlicheren Workflow
- Vorschau-Layer / Vorschau-Modi erweitert, unter anderem für Objektcheck, Konturen, Masken und Schnitt-/Fallteil-Risiko
- Parameter-Infos ergänzt, damit Vorverarbeitung, Smart CAD Smoothing und intelligente Brücken direkt im Programm erklärt werden
- Intelligente Brücken hinzugefügt, damit Inneninseln und kleine ausgeschnittene Teile beim Schneiden besser mit dem Material verbunden bleiben können
- Zoom für Originalbild und Vektorvorschau hinzugefügt
- Gemeinsame Zoom-Funktion für Original und Vorschau verbessert
- Live-Vorschau beim Ändern von Einstellungen hinzugefügt
- Manueller Refresh-Button für die Vorschau hinzugefügt
- UI stärker an bekannte Grafik- und Zeichenprogramme angelehnt, soweit mit Tkinter sinnvoll möglich
- Vektorbasierte Vorschauqualität verbessert, dadurch weniger verpixelt beim Zoomen
- Multilanguage-System erweitert
- Deutsche Umlaute korrigiert
- Linux-Canvas-Probleme behoben
- Allgemeine Bugfixes und Stabilitätsverbesserungen
- Mac OS Build
### Hinweise

Vektorrazor ist weiterhin ein Prototyp mit Fokus auf CAD-orientierte Vektorvorbereitung und Export-Workflows.


## Vektorrazor v2

This release improves the overall workflow, usability and preview quality of Vektorrazor.

### Highlights

- Added Dark Mode
- Added Light Mode
- Added intelligent auto-detect expert option
- Reduced and improved UI for a smarter and more user-friendly workflow
- Added extended preview layers / preview modes, including object check, contours, masks and cut/dropout risk
- Added parameter info dialogs so preprocessing, Smart CAD Smoothing and intelligent bridges are explained directly inside the program
- Added intelligent bridges to help keep inner islands and small cutout parts connected to the material during cutting
- Added zoom for both original image and vector preview
- Improved shared zoom behavior for original image and preview
- Added live preview while changing settings
- Added manual refresh button
- Improved graphics-program-style UI as far as possible with Tkinter
- Improved vector-based preview quality, less pixelated when zooming
- Extended multilingual support
- Fixed German umlauts
- Fixed Linux canvas issues
- General bugfixes and stability improvements
- Mac OS Build

### Notes

Vektorrazor is still a prototype focused on CAD-oriented vector preparation and export workflows.

---

## Schnellstart

Deutsch: [README.de.md](README.de.md)  
English: [README.en.md](README.en.md)

## Build für Windows EXE

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\\vektorrazor.ico --add-data "assets\\vektorrazor.ico;assets" --add-data "assets\\vektorrazor_icon.png;assets" main.py

## Windows EXE

In den Relaeses zu finden