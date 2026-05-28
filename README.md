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
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![GUI](https://img.shields.io/badge/GUI-Tkinter-brightgreen)
![Export](https://img.shields.io/badge/Export-DXF%20%7C%20SVG-orange)
![License](https://img.shields.io/badge/License-GPLv3-blue)
![Status](https://img.shields.io/badge/Status-Prototype%20%2F%20CAD%20Workflow-yellow)

</p>

<p align="center"><strong>Copyright (C) 2026 Andreas Rottmann</strong></p>

## Schnellstart

Deutsch: [README.de.md](README.de.md)  
English: [README.en.md](README.en.md)

## Build für Windows EXE

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\\vektorrazor.ico --add-data "assets\\vektorrazor.ico;assets" --add-data "assets\\vektorrazor_icon.png;assets" main.py
```

Das Icon liegt unter `assets/vektorrazor.ico` und wird mit `--icon` in die EXE eingebettet.  
Für das Tkinter-Fenster wird dasselbe Icon zusätzlich per `--add-data` mitgeliefert.

## Lizenz

GPL-3.0, siehe [LICENSE](LICENSE).
