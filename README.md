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

Version 2 focuses on a cleaner workflow, better usability and improved preview quality.

### New and improved

- Bugfixes and stability improvements
- Added Dark Mode
- Added Light Mode
- Added intelligent auto-detect expert option
- Reduced and improved UI for a smarter, more user-friendly workflow
- Added zoom for both original image and preview
- Added live changes / live preview while adjusting settings
- Added refresh button
- Improved UI inspired by typical graphics software, as far as possible with Tkinter
- Linux canvas fix
- Fixed German umlauts
- Preview image is now more vector-based and less pixelated when zooming

---

## Schnellstart

Deutsch: [README.de.md](README.de.md)  
English: [README.en.md](README.en.md)

## Build für Windows EXE

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\\vektorrazor.ico --add-data "assets\\vektorrazor.ico;assets" --add-data "assets\\vektorrazor_icon.png;assets" main.py

## Windows EXE

In den Relaeses zu finden