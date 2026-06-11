<p align="center">
  <img src="assets/vektorrazor_icon.png" width="180" alt="Vektorrazor Icon">
</p>

<h1 align="center">Vektorrazor</h1>

<p align="center">
  <strong>PNG logo preparation → AI upscale → CAD-oriented vector contours</strong>
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

---

## Overview

**Vektorrazor** is a desktop tool for preparing PNG logos and converting them into more CAD-oriented vector contours.

It includes optional **Real-ESRGAN ncnn Vulkan** support for AI-based upscaling on Windows, Ubuntu/Linux and macOS. The upscaling step is intended as a preparation aid for small or pixelated source images before vectorization.

## Languages

- Deutsch: [README.de.md](README.de.md)
- English: [README.en.md](README.en.md)

## Release platforms

| System | Package | AI upscaling backend |
|---|---|---|
| Windows amd64 | `Vektorrazor-Windows-amd64-YYYY-MM-DD.zip` | `realesrgan-ncnn-vulkan.exe` |
| Ubuntu / Linux amd64 | `Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz` | `realesrgan-ncnn-vulkan` |
| macOS | `Vektorrazor-macOS-YYYY-MM-DD.zip` | `realesrgan-ncnn-vulkan` |

## CAD workflow

```text
image preparation → optional AI upscale → technical color cleanup → contour detection → noise removal → point reduction → layer export
```

## Third-party note

The optional AI upscale backend uses Real-ESRGAN / Real-ESRGAN ncnn Vulkan. If the Real-ESRGAN executable files or models are shipped inside a Vektorrazor release, keep the corresponding third-party license texts and notices in the release package.

## License

Vektorrazor is licensed under **GPL-3.0**.  
See [LICENSE](LICENSE) for details.
