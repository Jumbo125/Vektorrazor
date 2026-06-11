<p align="center">
  <img src="assets/vektorrazor_icon.png" width="180" alt="Vektorrazor Icon">
</p>

<h1 align="center">Vektorrazor</h1>

<p align="center">
  <strong>PNG logo → AI upscaling → CAD-oriented vector contours</strong>
</p>

<p align="center">
  <a href="README.de.md">🇩🇪 Deutsch</a> ·
  <a href="README.en.md">🇬🇧 English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/GUI-Tkinter-brightgreen" alt="GUI">
  <img src="https://img.shields.io/badge/Export-DXF%20%7C%20SVG%20%7C%20STL%20%7C%20OBJ-orange" alt="Export">
  <img src="https://img.shields.io/badge/AI%20Upscale-Real--ESRGAN%20Vulkan-purple" alt="Real-ESRGAN Vulkan">
  <img src="https://img.shields.io/badge/License-GPLv3-blue" alt="License">
  <img src="https://img.shields.io/badge/Status-Prototype%20%2F%20CAD%20Workflow-yellow" alt="Status">
</p>

<p align="center"><strong>Copyright (C) 2026 Andreas Rottmann</strong></p>

## Overview

**Vektorrazor** is a desktop tool for preparing and vectorizing logos, scans and simple image sources.

The goal is not to create beautiful graphic artwork first. The goal is to create controllable contours that are easier to use in CAD, cutting, plotting, milling or technical post-processing:

```text
prepare image → optional AI upscale → clean technical colors → detect contours → remove noise → reduce points → export layers
```

AI upscaling is optional. It is integrated through **Real-ESRGAN ncnn Vulkan** and can help with small or pixelated source images before vectorization.

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
load image → optionally AI upscale → continue to vectorization → inspect preview → export DXF / SVG / STL / OBJ
```

### Ubuntu / Linux amd64

1. Download the Ubuntu/Linux release asset from **GitHub Releases**:

```text
Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz
```

2. Extract the archive:

```bash
tar -xzf Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz
cd Vektorrazor-Ubuntu-amd64-YYYY-MM-DD
```

3. Make the binary executable and run it:

```bash
chmod +x Vektorrazor
./Vektorrazor
```

Note: Linux requires a graphical desktop environment. On Windows 11, WSL usually works through WSLg. Older WSL setups may require an X server.

### macOS

1. Download the macOS release asset from **GitHub Releases**:

```text
Vektorrazor-macOS-YYYY-MM-DD.zip
```

2. Extract the ZIP file.
3. Start Vektorrazor.
4. If macOS blocks the launch: right-click the app or file and choose **Open**.

If Real-ESRGAN files were extracted manually, macOS may add a quarantine attribute. From the extracted release folder, this can help:

```bash
xattr -dr com.apple.quarantine .
```

## Installation

Normal users do not need a Python installation. Ready-to-use release files are provided:

| System | File | Action |
|---|---|---|
| Windows amd64 | `Vektorrazor-Windows-amd64-YYYY-MM-DD.zip` | extract and start `Vektorrazor.exe` |
| Ubuntu / Linux amd64 | `Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz` | extract, make executable and run |
| macOS | `Vektorrazor-macOS-YYYY-MM-DD.zip` | extract and run |

## Real-ESRGAN / Vulkan upscaling

Vektorrazor can optionally use **Real-ESRGAN ncnn Vulkan**. It runs locally and offline through a bundled command-line executable.

Upscaling is mainly intended for small, pixelated or slightly blurry source images. For CAD usage, the final cleaned contour is more important than the most visually pleasing image.

### Required folder structure

Recommended release layout:

```text
Vektorrazor.exe / Vektorrazor / Vektorrazor.app
vektorrazor_config/
  real_esrgan/
    models/
      realesr-animevideov3-x2.bin
      realesr-animevideov3-x2.param
      realesr-animevideov3-x3.bin
      realesr-animevideov3-x3.param
      realesr-animevideov3-x4.bin
      realesr-animevideov3-x4.param
    windows/
      realesrgan-ncnn-vulkan.exe
    ubuntu/
      realesrgan-ncnn-vulkan
    macos/
      realesrgan-ncnn-vulkan
    THIRD_PARTY_NOTICES.md
    LICENSE-Real-ESRGAN-BSD-3-Clause.txt
    LICENSE-Real-ESRGAN-ncnn-vulkan-MIT.txt
```

The models are shared in the `models/` folder. The platform folders only contain the matching executable file.

### Vulkan requirement

Real-ESRGAN ncnn Vulkan requires working Vulkan support on the system.

Typical requirements:

- current graphics driver
- Vulkan-capable GPU or compatible Vulkan runtime
- on macOS, the matching Real-ESRGAN macOS build

If Vulkan is not available or the Real-ESRGAN executable is missing, Vektorrazor should still be usable without AI upscaling.

### Test commands

Windows:

```bat
vektorrazor_config\real_esrgan\windows\realesrgan-ncnn-vulkan.exe -i input.png -o output.png -n realesr-animevideov3 -s 4 -m vektorrazor_config\real_esrgan\models -f png
```

Ubuntu / Linux:

```bash
chmod +x vektorrazor_config/real_esrgan/ubuntu/realesrgan-ncnn-vulkan
./vektorrazor_config/real_esrgan/ubuntu/realesrgan-ncnn-vulkan -i input.png -o output.png -n realesr-animevideov3 -s 4 -m vektorrazor_config/real_esrgan/models -f png
```

macOS:

```bash
chmod +x vektorrazor_config/real_esrgan/macos/realesrgan-ncnn-vulkan
./vektorrazor_config/real_esrgan/macos/realesrgan-ncnn-vulkan -i input.png -o output.png -n realesr-animevideov3 -s 4 -m vektorrazor_config/real_esrgan/models -f png
```

Note: The model name is `realesr-animevideov3`. The scale is selected with `-s 2`, `-s 3` or `-s 4`. That is why the model files include `-x2`, `-x3` or `-x4` in their file names.

## Developer notes

The source code is included in the repository. Developers can run Vektorrazor from source or create custom builds.

### Run from source

```bash
pip install -r requirements.txt
python main.py
```

### Build a Windows EXE manually

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py
```

### Build an Ubuntu/Linux binary manually

```bash
pyinstaller --onefile --windowed --clean \
  --name Vektorrazor \
  --add-data "assets/vektorrazor.ico:assets" \
  --add-data "assets/vektorrazor_icon.png:assets" \
  main.py
```

### Build a macOS app manually

```bash
pyinstaller --onefile --windowed --clean \
  --name Vektorrazor \
  --add-data "assets/vektorrazor_icon.png:assets" \
  main.py
```

Important: Keep Real-ESRGAN executables and models next to the application in the release folder instead of forcing them into the PyInstaller onefile bundle. This makes updates, license notices and troubleshooting much easier.

## Create release packages

Recommended release assets:

```text
release/Vektorrazor-Windows-amd64-YYYY-MM-DD.zip
release/Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz
release/Vektorrazor-macOS-YYYY-MM-DD.zip
release/SHA256SUMS-YYYY-MM-DD.txt
```

Include `vektorrazor_config/real_esrgan/` in the release package if AI upscaling should work out of the box.

## Use and extend languages

The application loads language files from the `lang/` folder.

- File names: `lang/lang_de.json`, `lang/lang_en.json`
- PyInstaller priority: external `lang/` next to the EXE/app is preferred
- Source/development mode: project-local `lang/` is used
- If `lang/` is missing or files are incomplete, the hardcoded Python fallback is used

Change language in the app:

```text
start app → choose language in the header → UI updates without restart
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
| Ready-to-use downloads | Windows amd64, Ubuntu/Linux amd64, macOS |
| Optional AI upscaler | Real-ESRGAN ncnn Vulkan |
| Input | PNG, JPG, BMP, WEBP, TIFF |
| Intermediate format | technically cleaned PNG |
| Export | DXF, SVG, STL, OBJ |
| DXF compatibility | R2000, R2004, R2007, R2010, R2013, R2018 |
| Goal | more CAD-friendly contours from prepared logos and image sources |
| License | GPL-3.0 |

## Main features

- image preparation with brightness, contrast, black point, white point and gamma
- optional AI upscaling through Real-ESRGAN ncnn Vulkan
- automatic color detection
- exact technical RGB contrast colors
- logo/scan cleanup for difficult source images
- dynamic color table
- layer names per color
- minimum area filter for noise removal
- point reduction with epsilon
- smoothing and cleanup
- preview modes for contour lines, object check and color mask
- select and remove paths in the preview
- SVG, DXF, STL and OBJ-oriented export workflow
- DXF compatibility presets for different programs
- ready-to-use builds for Windows, Ubuntu/Linux and macOS via GitHub Releases

## Third-party / Real-ESRGAN

The optional AI upscaling feature uses third-party components:

- **Real-ESRGAN** by Xintao Wang / Tencent ARC Lab
- **Real-ESRGAN ncnn Vulkan** by Xintao Wang
- parts/components from **realsr-ncnn-vulkan** by nihui

If Real-ESRGAN executables or models are shipped inside a Vektorrazor release, keep the corresponding license texts and copyright notices inside the release package.

Vektorrazor is not officially affiliated with, endorsed by, or supported by Real-ESRGAN, Xintao Wang or Tencent ARC Lab.

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
