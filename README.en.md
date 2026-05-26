<p align="center">
  <img src="assets/vektorrazor_icon.png" width="180" alt="Vektorrazor Icon">
</p>

<h1 align="center">Vektorrazor</h1>

<p align="center">
  <strong>PNG logo → CAD-oriented vector contours</strong>
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

## Overview

**Vektorrazor** is a desktop tool that turns prepared PNG logos into more CAD-oriented vector contours.

The workflow is intentionally split into two steps:

```text
1. Prepare the image / clean technical colors
2. Vectorize / inspect contours / export DXF or SVG
```

## Quick start with a ready-to-use file

### Windows amd64

1. Download the Windows release asset from **GitHub Releases**:

```text
Vektorrazor-Windows-amd64-YYYY-MM-DD.zip
```

2. Extract the ZIP file.
3. Start `Vektorrazor.exe`.
4. If Windows SmartScreen warns you: click **More info → Run anyway**.
5. In the program:

```text
load PNG → continue to vectorization → detect / preview → export DXF / SVG
```

### Linux amd64

1. Download the Linux release asset from **GitHub Releases**:

```text
Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
```

2. Extract the archive:

```bash
tar -xzf Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
cd Vektorrazor-Linux-amd64-YYYY-MM-DD
```

3. Make the binary executable:

```bash
chmod +x Vektorrazor
```

4. Start the program:

```bash
./Vektorrazor
```

Note: Linux requires a graphical desktop environment. On Windows 11, WSL usually works through WSLg. Older WSL setups may require an X server.

## Installation

Normal users do not need a Python installation. Ready-to-use release files are provided:

| System | File | Action |
|---|---|---|
| Windows amd64 | `Vektorrazor-Windows-amd64-YYYY-MM-DD.zip` | extract and start `Vektorrazor.exe` |
| Linux amd64 | `Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz` | extract, make executable and run |

### Windows

```text
download ZIP → extract → start Vektorrazor.exe
```

### Linux

```bash
tar -xzf Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
cd Vektorrazor-Linux-amd64-YYYY-MM-DD
chmod +x Vektorrazor
./Vektorrazor
```

## Developer notes

The source code is still included in the repository. Developers can run from source or create custom builds with Python and PyInstaller.

### Run from source

```bash
pip install -r requirements.txt
python main.py
```

### Build a Windows EXE manually

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py
```

### Build a Linux amd64 binary manually

```bash
pyinstaller --onefile --windowed --clean   --name Vektorrazor   --add-data "assets/vektorrazor.ico:assets"   --add-data "assets/vektorrazor_icon.png:assets"   main.py
```

## Create release packages

If both builds exist:

```text
dist/Vektorrazor.exe
dist/Vektorrazor
```

run:

```bash
chmod +x pack_release.sh
./pack_release.sh
```

This creates for example:

```text
release/Vektorrazor-Windows-amd64-2026-05-26.zip
release/Vektorrazor-Linux-amd64-2026-05-26.tar.gz
release/SHA256SUMS-2026-05-26.txt
```

## Why not just use a regular vector program?

Tools like Illustrator, CorelDRAW or Inkscape can produce visually excellent vector artwork. For graphic design, that is often exactly what you want.

For CAD, cutting paths, plotting, milling or technical post-processing, however, those results can introduce problems:

- duplicate lines
- loose object paths
- loose anchor points
- too many unnecessary points
- tiny noise objects
- filled shapes instead of clean contours
- unclear layer structure
- inner contours or holes may be interpreted incorrectly

**Vektorrazor** is not primarily optimized for beautiful artwork. It is optimized for controllable technical contours:

```text
detect color → separate area → build contour → remove noise → reduce points → export layers
```

## Program information

| Area | Info |
|---|---|
| Name | Vektorrazor |
| Type | Desktop application |
| GUI | Tkinter |
| Ready-to-use downloads | Windows amd64 EXE, Linux amd64 binary |
| Input | PNG, JPG, BMP, WEBP, TIFF |
| Intermediate format | technically cleaned PNG |
| Export | DXF, SVG |
| DXF compatibility | R2000, R2004, R2007, R2010, R2013, R2018 |
| Goal | more CAD-friendly contours from prepared logos |
| License | GPL-3.0 |

## Main features

- image preparation with brightness, contrast, black point, white point and gamma
- automatic color detection
- exact technical RGB contrast colors
- logo mask mode for difficult sources
- dynamic color table
- layer names per color
- minimum area filter for noise removal
- point reduction with epsilon
- smoothing and cleanup
- preview modes for contour lines, object check and color mask
- select and remove paths in the preview
- SVG and DXF export
- DXF compatibility presets for different programs
- ready-to-use Windows amd64 and Linux amd64 downloads via GitHub Releases

## Copyright / Ownership

Copyright (C) 2026 Andreas Rottmann

The copyright notice is included in:

- `README.md`, `README.de.md`, `README.en.md`
- `AUTHORS.md`
- `NOTICE.md`
- source file headers with SPDX license identifiers
- `version_info.txt` for Windows EXE metadata
- `assets/vektorrazor.ico` as EXE and window icon

## License

This project is licensed under **GPL-3.0**.  
See [LICENSE](LICENSE) for details.
