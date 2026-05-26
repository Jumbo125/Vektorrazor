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

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![GUI](https://img.shields.io/badge/GUI-Tkinter-brightgreen)
![Export](https://img.shields.io/badge/Export-DXF%20%7C%20SVG-orange)
![License](https://img.shields.io/badge/License-GPLv3-blue)
![Status](https://img.shields.io/badge/Status-Prototype%20%2F%20CAD%20Workflow-yellow)

</p>

<p align="center"><strong>Copyright (C) 2026 Andreas Rottmann</strong></p>

## Overview

**Vektorrazor** is a Python/Tkinter tool that turns prepared PNG logos into more CAD-oriented vector contours.

The workflow is intentionally split into two steps:

```text
1. Prepare the image / clean technical colors
2. Vectorize / inspect contours / export DXF or SVG
```

## Very short quick guide

### Windows

1. Start with `python main.py`.
2. Load your PNG in **Step 1**.
3. Reduce colors or create exact technical contrast colors.
4. Click **Continue to vectorization**.
5. In **Step 2**, click **Detect / Preview**.
6. Remove unwanted paths in selection mode if needed.
7. Select a DXF compatibility profile, for example **Illustrator/CorelDRAW recommended**.
8. Click **Export DXF / SVG**.

### Linux / WSL Ubuntu

1. Install system packages:

```bash
sudo apt update
sudo apt install python3-tk python3-venv python3-pip
```

2. Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install Python dependencies:

```bash
pip install -r requirements.txt
```

4. Start the program:

```bash
python main.py
```

5. Use the workflow:

```text
load PNG → continue to vectorization → detect / preview → export
```

Note: A graphical environment is required for Tkinter. On Windows 11, WSLg usually handles this. Older WSL setups may require an X server.

## Installation

### Windows

```bash
pip install -r requirements.txt
python main.py
```

### Linux / Ubuntu / WSL

```bash
sudo apt update
sudo apt install python3-tk python3-venv python3-pip

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

## Build a Windows EXE

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py
```

Or run:

```bat
build_windows.bat
```

The icon is stored here:

```text
assets/vektorrazor.ico
```

It is embedded into the EXE via `--icon` and also bundled via `--add-data` so it can be used as the Tkinter window icon.

## Build a Linux amd64 binary

On Linux / WSL Ubuntu:

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install pyinstaller

pyinstaller --onefile --windowed --clean \
  --name Vektorrazor \
  --add-data "assets/vektorrazor.ico:assets" \
  --add-data "assets/vektorrazor_icon.png:assets" \
  main.py
```

The result will be:

```text
dist/Vektorrazor
```

Run it with:

```bash
chmod +x dist/Vektorrazor
./dist/Vektorrazor
```

Important: On Linux, PyInstaller uses a colon `:` for `--add-data`.  
On Windows, PyInstaller uses a semicolon `;`.

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

To force a fixed release date:

```bash
RELEASE_DATE=2026-05-26 ./pack_release.sh
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
| Language | Python |
| GUI | Tkinter |
| Input | PNG, JPG, BMP, WEBP, TIFF |
| Intermediate format | technically cleaned PNG |
| Export | DXF, SVG |
| DXF compatibility | R2000, R2004, R2007, R2010, R2013, R2018 |
| Goal | more CAD-friendly contours from prepared logos |
| Windows build | Windows amd64 EXE |
| Linux build | Linux amd64 binary |

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
- Windows and Linux amd64 builds possible

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
