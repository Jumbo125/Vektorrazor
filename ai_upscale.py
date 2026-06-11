# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
import subprocess
import sys

from PIL import Image


@dataclass(frozen=True)
class AiUpscalePaths:
    user_config_dir: Path

    @property
    def root_dir(self) -> Path:
        return self.user_config_dir / "real_esrgan"

    @property
    def models_dir(self) -> Path:
        return self.root_dir / "models"

    @property
    def tmp_dir(self) -> Path:
        return self.user_config_dir / "tmp_upscale"

    def platform_dir(self) -> Optional[Path]:
        if sys.platform.startswith("win"):
            candidate = self.root_dir / "windows"
        elif sys.platform.startswith("linux"):
            candidate = self.root_dir / "linux"
        elif sys.platform.startswith("darwin"):
            candidate = self.root_dir / "mac"
        else:
            return None
        return candidate if candidate.exists() else None

    def executable_path(self) -> Optional[Path]:
        platform_dir = self.platform_dir()
        if platform_dir is None:
            return None
        if sys.platform.startswith("win"):
            exe = platform_dir / "realesrgan-ncnn-vulkan.exe"
        else:
            exe = platform_dir / "realesrgan-ncnn-vulkan"
        return exe if exe.exists() else None

    def default_output_path(self) -> Path:
        out = self.tmp_dir / "upscale.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    def default_model_dir(self) -> Optional[Path]:
        return self.models_dir if self.models_dir.is_dir() else None

    def default_model_file(self) -> Optional[Path]:
        if not self.models_dir.is_dir():
            return None
        for name in (
            "realesr-animevideov3-x4.bin",
            "realesr-animevideov3-x3.bin",
            "realesr-animevideov3-x2.bin",
            "realesrgan-x4plus.bin",
        ):
            candidate = self.models_dir / name
            if candidate.exists():
                return candidate
        for pattern in ("*.pth", "*.onnx", "*.bin", "*.param"):
            files = sorted(self.models_dir.glob(pattern))
            if files:
                return files[0]
        return None


def _model_name(model_path: Path) -> str:
    suffix = model_path.suffix.lower()
    if suffix in {".bin", ".param", ".pth", ".onnx"}:
        return model_path.stem
    return model_path.name


def resolve_model_dir(model_dir: Path) -> Path:
    if model_dir.is_file():
        model_dir = model_dir.parent
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Modellordner nicht gefunden: {model_dir}")
    return model_dir


def resolve_model_spec(model_dir: Path) -> tuple[Path, str, list[int]]:
    model_dir = resolve_model_dir(model_dir)

    anime_scales: list[int] = []
    for scale in (2, 3, 4):
        if (model_dir / f"realesr-animevideov3-x{scale}.bin").exists():
            anime_scales.append(scale)
    if anime_scales:
        return model_dir, "realesr-animevideov3", anime_scales

    if (model_dir / "realesrgan-x4plus.bin").exists():
        return model_dir, "realesrgan-x4plus", [4]

    # Fallback fuer andere Modellordner: exakt eine bekannte Modellbasis nutzen.
    candidates = sorted(p for p in model_dir.iterdir() if p.suffix.lower() in {".bin", ".pth", ".onnx", ".param"})
    if not candidates:
        raise FileNotFoundError(
            "Im gewählten Modellordner wurde kein passendes Real-ESRGAN-Modell gefunden. "
            "Erwartet werden z. B. realesr-animevideov3-x2/x3/x4 oder realesrgan-x4plus."
        )

    stem = candidates[0].stem
    if stem.startswith("realesr-animevideov3-x"):
        available_scales: list[int] = []
        for scale in (2, 3, 4):
            if (model_dir / f"realesr-animevideov3-x{scale}.bin").exists():
                available_scales.append(scale)
        if not available_scales:
            raise FileNotFoundError("Für realesr-animevideov3 wurden keine x2/x3/x4-Modelle gefunden.")
        return model_dir, "realesr-animevideov3", available_scales
    if stem == "realesrgan-x4plus":
        return model_dir, "realesrgan-x4plus", [4]
    return model_dir, _model_name(candidates[0]), [4]


def build_pass_scales(scale_factor: float, available_scales: list[int]) -> list[int]:
    scales = sorted({int(scale) for scale in available_scales if int(scale) >= 2}, reverse=True)
    if not scales:
        raise ValueError("Keine gültigen Upscale-Faktoren vorhanden.")
    if scale_factor <= 1.0:
        return []

    passes: list[int] = []
    remaining = float(scale_factor)
    max_scale = float(scales[0])
    while remaining > max_scale:
        passes.append(int(max_scale))
        remaining /= max_scale

    for scale in reversed(scales):
        if float(scale) >= remaining:
            passes.append(int(scale))
            break
    else:
        passes.append(int(scales[0]))
    return passes


def run_ai_upscale(
    *,
    base: Image.Image,
    width: int,
    height: int,
    model_dir: Path,
    output_path: Path,
    paths: AiUpscalePaths,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Path:
    exe_path = paths.executable_path()
    if exe_path is None:
        raise FileNotFoundError("Real-ESRGAN executable wurde nicht gefunden.")
    platform_dir = exe_path.parent
    resolved_model_dir, model_name, available_scales = resolve_model_spec(model_dir)
    paths.tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    working_input_path = paths.tmp_dir / "input.png"
    base.convert("RGBA").save(working_input_path, format="PNG")

    scale_factor = max(width / max(1, base.width), height / max(1, base.height))
    pass_scales = build_pass_scales(scale_factor, available_scales)
    total_passes = max(1, len(pass_scales))
    if not pass_scales:
        base.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS).save(output_path, format="PNG")
        return output_path

    for idx, cli_scale in enumerate(pass_scales, start=1):
        pass_output_path = paths.tmp_dir / f"upscale_pass_{idx}.png"
        if pass_output_path.exists():
            pass_output_path.unlink()
        if progress_callback is not None:
            progress_callback(
                8 + ((idx - 1) / total_passes) * 80,
                f"KI-Skalierung: Durchlauf {idx}/{total_passes} mit x{cli_scale}",
            )
        cmd = [
            str(exe_path),
            "-i", str(working_input_path),
            "-o", str(pass_output_path),
            "-n", model_name,
            "-s", str(cli_scale),
            "-m", str(resolved_model_dir),
            "-t", "0",
            "-j", "1:2:2",
            "-f", "png",
            "-v",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(platform_dir),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"Exit-Code {result.returncode}"
            raise RuntimeError(f"Real-ESRGAN fehlgeschlagen: {detail}")
        if not pass_output_path.exists():
            raise FileNotFoundError(f"Upscale-Ausgabe fehlt: {pass_output_path}")
        working_input_path = pass_output_path

    if progress_callback is not None:
        progress_callback(92, "KI-Skalierung: Zielgröße wird final angepasst")
    with Image.open(working_input_path) as upscaled_raw:
        final_image = upscaled_raw.convert("RGBA")
        if final_image.size != (width, height):
            final_image = final_image.resize((width, height), Image.Resampling.LANCZOS)
        final_image.save(output_path, format="PNG")
    if progress_callback is not None:
        progress_callback(100, f"KI-Skalierung abgeschlossen: {output_path}")
    return output_path
