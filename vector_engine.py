# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""
Vektorisierungs-Engine für CAD-nahe Konturen.

Diese Datei enthält die eigentliche Geometrie- und Exportlogik. Aus einem
technisch vorbereiteten Rasterbild werden Konturen extrahiert, aufbereitet,
vereinfacht und anschließend für Vorschau oder Export bereitgestellt.

Zentrale Aufgaben:
- Detektion zusammenhängender Flächen und Konturen
- Approximation und Vereinfachung der Polygonzüge
- Umrechnung in SVG-, DXF- oder weiterverarbeitbare Geometriedaten
- Hilfsfunktionen für Bounding-Boxen, Skalierung und Export-Kompatibilität

Die Trennung zu Schritt 1 ist bewusst klar:
- Schritt 1 macht das Bild technisch sauber
- vector_engine.py macht daraus verwertbare Vektorgeometrie
"""

from __future__ import annotations

# Diese Engine arbeitet bewusst auf Basis bereits vorbereiteter Zwischenbilder.
# Je sauberer Schritt 1 arbeitet, desto stabiler und CAD-näher wird die spätere
# Konturvereinfachung und der Export.

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import cv2
from PIL import Image, ImageTk, ImageDraw

import ezdxf
import svgwrite


@dataclass
class ColorRule:
    name: str
    rgb: Tuple[int, int, int]
    tolerance: float
    layer: str
    export: bool
    min_area: int
    epsilon: float


@dataclass
class DetectedContour:
    rule: ColorRule
    points: List[Tuple[float, float]]
    area: float
    closed: bool = True
    is_hole: bool = False
    raw_points: Optional[List[Tuple[float, float]]] = None


PROFILE_ROWS: Dict[str, List[Tuple[str, str, str, str, bool, str, str]]] = {
    "Standard": [
        ("Schwarz", "0,0,0", "12", "CUT_BLACK", True, "2", "0.350"),
        ("Blau", "0,0,255", "12", "CUT_BLUE", True, "2", "0.350"),
        ("Grün", "0,255,0", "10", "IGNORE", False, "20", "1.2"),
    ],
    "Schwarz/Weiß": [
        ("Schwarz", "0,0,0", "12", "CUT_BLACK", True, "2", "0.350"),
        ("Weiß", "255,255,255", "8", "IGNORE_WHITE", False, "50", "1.5"),
    ],
    "Schwarze Linien": [
        ("Schwarz", "0,0,0", "14", "CUT_BLACK", True, "2", "0.300"),
    ],
    "Primärfarben": [
        ("Rot", "255,0,0", "12", "CUT_RED", True, "2", "0.350"),
        ("Grün", "0,255,0", "10", "CUT_GREEN", True, "30", "1.2"),
        ("Blau", "0,0,255", "12", "CUT_BLUE", True, "2", "0.350"),
    ],
    "CMYK": [
        ("Cyan", "0,255,255", "12", "CUT_CYAN", True, "2", "0.350"),
        ("Magenta", "255,0,255", "12", "CUT_MAGENTA", True, "2", "0.350"),
        ("Gelb", "255,255,0", "12", "CUT_YELLOW", True, "2", "0.350"),
        ("Schwarz", "0,0,0", "12", "CUT_BLACK", True, "2", "0.350"),
    ],
    "RGB + Schwarz": [
        ("Rot", "255,0,0", "12", "CUT_RED", True, "2", "0.350"),
        ("Grün", "0,255,0", "10", "CUT_GREEN", True, "30", "1.2"),
        ("Blau", "0,0,255", "12", "CUT_BLUE", True, "2", "0.350"),
        ("Schwarz", "0,0,0", "12", "CUT_BLACK", True, "2", "0.350"),
    ],
}


INFO_TEXTS: Dict[str, str] = {
    "input": (
        "PNG-Datei auswählen, die analysiert werden soll.\n\n"
        "Gut geeignet sind vorbereitete Logos mit klaren, flächigen Farben."
    ),
    "output": (
        "Zieldatei für den Export.\n\n"
        "Unterstützt werden .dxf für CAD und .svg für Vektorprogramme."
    ),
    "pixel_to_mm": (
        "Umrechnung von Bildpixeln in Millimeter.\n\n"
        "1 bedeutet: 1 Pixel wird als 1 mm exportiert.\n"
        "0,5 bedeutet: 1 Pixel wird als 0,5 mm exportiert."
    ),
    "profile": (
        "Lädt typische Farbtabellen, damit du Farben nicht jedes Mal neu eintragen musst.\n\n"
        "Wähle ein Profil und klicke auf Anwenden. Bestehende Farbzeilen werden ersetzt."
    ),
    "vector_mode": (
        "Legt fest, welche Art Vektor erzeugt wird.\n\n"
        "Flächenkontur zeichnet die Außenkanten der Farbflächen nach. Mittellinie / Gravur reduziert dicke Linien auf eine einzelne Mittellinie."
    ),
    "centerline_merge": (
        "Nur für Mittellinie / Gravur.\n\n"
        "Führt nahe schwarze Linien oder kleine Lücken vor dem Mittellinien-Schritt zusammen. Der Wert ist ein Abstand in Pixeln. 0 deaktiviert die Zusammenführung. Komma ist erlaubt."
    ),
    "detect_preview": (
        "Startet die Analyse und zeigt das Ergebnis in der Vorschau.\n\n"
        "Dabei werden Farbregeln, Toleranz, Mindestfläche, Punktreduktion und die Zusatzfilter angewendet."
    ),
    "auto_settings": (
        "Testet mehrere Einstellungen und wählt die Kombination, deren gerenderte Vektorform der ursprünglichen Farbmaske am nächsten kommt.\n\n"
        "Das ist eine erste automatische Suche, keine KI. Sie ist reproduzierbar und eignet sich als Startpunkt für weitere manuelle Feinjustierung."
    ),
    "export": (
        "Speichert die aktuell erkannten Konturen als DXF oder SVG.\n\n"
        "Wenn noch keine Konturen erkannt wurden, wird die Erkennung vorher automatisch gestartet."
    ),
    "closed_paths": (
        "Wenn aktiv, bleiben nur Pfade übrig, die als geschlossene Kontur nutzbar sind.\n\n"
        "Für Schneidpfade meist aktiv lassen. Deaktivieren, wenn offene Linien absichtlich exportiert werden sollen."
    ),
    "fill_closed_shapes": (
        "Füllt geschlossene Pfade in Vorschau und SVG-Export.\n\n"
        "Für schwarze Plot-/Drucklinien aktiv lassen. Für reine Schneidkonturen kannst du es deaktivieren."
    ),
    "bezier_curves": (
        "Zeichnet Kurven in der Vorschau geglättet und exportiert SVG mit Cubic-Bezier-Kurven.\n\n"
        "Das kann runde Formen mit weniger sichtbaren Ecken erzeugen. DXF bleibt weiterhin Polyline, weil Plotter/CAD das meist zuverlässiger lesen."
    ),
    "loose_points": (
        "Entfernt doppelte oder fast deckungsgleiche Punkte und sehr kleine Ausreißer in der Kontur.\n\n"
        "Aktivieren, wenn der Export unnötige Einzelpunkte oder kurze Spitzen enthält."
    ),
    "smooth_contours": (
        "Glättet erkannte Konturen vor der Punktreduktion.\n\n"
        "Das macht Rundungen weicher. Danach reduziert Epsilon die Punktezahl wieder."
    ),
    "smooth_strength": (
        "Stärke der Rundungsglättung.\n\n"
        "0 deaktiviert die Glättung. 1 ist leicht, 2 ist meist ein guter Wert, 3 glättet stärker."
    ),
    "min_object_size": (
        "Löscht kleine erkannte Pfadobjekte.\n\n"
        "Aus deaktiviert den Filter. mm² nutzt reale Ausgabegröße. % Bildfläche nutzt einen relativen Faktor und ist robuster bei unterschiedlich großen PNGs. Komma ist erlaubt."
    ),
    "preview": (
        "Zeigt zwei Ansichten nebeneinander.\n\n"
        "Links steht das originale PNG. Rechts stehen die erkannten Vektorlinien ohne Bildhintergrund.\n"
        "Mit dem Mausrad kannst du die Ansicht unter dem Mauszeiger zoomen. Den Trenner zwischen beiden Vorschauen kannst du verschieben."
    ),
    "color_name": "Interner Name der Farbe. Dient zur Orientierung in der Tabelle.",
    "color_rgb": (
        "Zielfarbe als RGB-Wert im Format R,G,B.\n\n"
        "Beispiele: 0,0,0 für Schwarz oder 255,0,0 für Rot."
    ),
    "color_tolerance": (
        "Erlaubte Farbabweichung zur RGB-Zielfarbe.\n\n"
        "Kleiner Wert = strenger. Größerer Wert = erkennt auch Anti-Aliasing oder leichte Farbabweichungen."
    ),
    "color_layer": (
        "Layername für den Export.\n\n"
        "In DXF wird daraus ein CAD-Layer, in SVG eine Gruppe."
    ),
    "color_export": (
        "Legt fest, ob die erkannte Farbe exportiert wird.\n\n"
        "Deaktivieren, wenn die Farbe nur erkannt oder ignoriert werden soll."
    ),
    "color_min_area": (
        "Mindestfläche in Pixeln vor der Konturbildung.\n\n"
        "Höhere Werte entfernen kleine Farbstörungen früher."
    ),
    "color_epsilon": (
        "Punktreduktion für die Kontur.\n\n"
        "0 behält mehr Details. Größere Werte erzeugen einfachere Pfade mit weniger Punkten.\n\n"
        "Für runde Formen meist mit Glättung kombinieren: Glättung macht die Kurve weich, Epsilon hält die Punktzahl klein."
    ),
}


def clamp_rgb(value: int) -> int:
    return max(0, min(255, int(value)))


def parse_rgb(text: str) -> Tuple[int, int, int]:
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    if len(parts) != 3:
        raise ValueError("RGB muss im Format R,G,B eingegeben werden, z. B. 0,0,0")
    return tuple(clamp_rgb(int(p)) for p in parts)  # type: ignore[return-value]


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def load_rgb_image(path: str) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    return np.array(image)


def make_color_mask(image_rgb: np.ndarray, rgb: Tuple[int, int, int], tolerance: float) -> np.ndarray:
    target = np.array(rgb, dtype=np.float32)
    tol = max(0.0, float(tolerance))

    # Für Graustufen-Ziele (insb. Schwarz/Weiß) ist Kanal-euklidische Distanz
    # oft zu streng für Anti-Aliasing-Pixel. Luma-Distanz liefert stabilere
    # Ergebnisse bei ähnlich kontrastreichen Linien.
    if abs(float(rgb[0]) - float(rgb[1])) <= 2.0 and abs(float(rgb[1]) - float(rgb[2])) <= 2.0:
        gray = image_rgb.astype(np.float32).mean(axis=2)
        target_gray = float(target.mean())
        dist = np.abs(gray - target_gray)
        mask = (dist <= tol).astype(np.uint8) * 255
        return mask

    diff = image_rgb.astype(np.float32) - target
    dist = np.sqrt(np.sum(diff * diff, axis=2))
    mask = (dist <= tol).astype(np.uint8) * 255
    return mask


def preprocess_vector_image(
    image_rgb: np.ndarray,
    enabled: bool = False,
    blur_radius: float = 0.0,
    edge_smoothing: float = 0.0,
) -> np.ndarray:
    if not enabled:
        return image_rgb

    result = image_rgb.copy()
    blur = max(0.0, float(blur_radius))
    if blur > 0.0:
        sigma = min(3.0, blur)
        result = cv2.GaussianBlur(result, (0, 0), sigmaX=sigma, sigmaY=sigma)

    calm = max(0.0, min(5.0, float(edge_smoothing)))
    if calm > 0.0:
        sigma_edge = 0.25 + calm * 0.55
        result = cv2.GaussianBlur(result, (0, 0), sigmaX=sigma_edge, sigmaY=sigma_edge)

    return result


def upscale_vector_image(image_rgb: np.ndarray, scale: int = 1) -> np.ndarray:
    factor = max(1, min(3, int(scale)))
    if factor <= 1:
        return image_rgb
    height, width = image_rgb.shape[:2]
    return cv2.resize(image_rgb, (width * factor, height * factor), interpolation=cv2.INTER_CUBIC)


def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    if min_area <= 0:
        return mask

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cleaned = np.zeros_like(mask)

    for label_id in range(1, num_labels):
        area = stats[label_id, cv2.CC_STAT_AREA]
        if area >= min_area:
            cleaned[labels == label_id] = 255

    return cleaned


def calm_mask_edges(
    mask: np.ndarray,
    edge_smoothing: float = 0.0,
    min_noise_area: float = 0.0,
) -> np.ndarray:
    result = mask

    noise_area = max(0, int(round(float(min_noise_area))))
    if noise_area > 0:
        result = remove_small_components(result, noise_area)

    calm = max(0.0, min(5.0, float(edge_smoothing)))
    if calm <= 0.0:
        return result

    kernel_size = max(3, int(round(calm * 2.0)) * 2 + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, kernel)
    if calm >= 2.0:
        result = cv2.morphologyEx(result, cv2.MORPH_OPEN, kernel)
    result = cv2.GaussianBlur(result, (0, 0), sigmaX=max(0.5, calm * 0.35))
    _, result = cv2.threshold(result, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return result.astype(np.uint8)


def merge_nearby_mask_lines(mask: np.ndarray, merge_distance_px: float) -> np.ndarray:
    if merge_distance_px <= 0:
        return mask

    radius = max(1, int(math.ceil(merge_distance_px / 2.0)))
    kernel_size = radius * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def zhang_suen_thinning(mask: np.ndarray, max_iterations: int = 180) -> np.ndarray:
    try:
        ximgproc = getattr(cv2, "ximgproc", None)
        thinning = getattr(ximgproc, "thinning", None) if ximgproc is not None else None
        if thinning is not None:
            return thinning((mask > 0).astype(np.uint8) * 255)
    except Exception:
        pass

    image = (mask > 0).astype(np.uint8)
    if image.size == 0:
        return mask

    changed = True
    iterations = 0
    while changed and iterations < max(1, int(max_iterations)):
        changed = False
        iterations += 1
        for step in (0, 1):
            padded = np.pad(image, 1, mode="constant")
            p2 = padded[:-2, 1:-1]
            p3 = padded[:-2, 2:]
            p4 = padded[1:-1, 2:]
            p5 = padded[2:, 2:]
            p6 = padded[2:, 1:-1]
            p7 = padded[2:, :-2]
            p8 = padded[1:-1, :-2]
            p9 = padded[:-2, :-2]

            neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
            transitions = np.zeros_like(image)
            for current, next_value in zip(neighbors, neighbors[1:] + neighbors[:1]):
                transitions += ((current == 0) & (next_value == 1)).astype(np.uint8)

            neighbor_count = sum(neighbors)
            base = (
                (image == 1)
                & (neighbor_count >= 2)
                & (neighbor_count <= 6)
                & (transitions == 1)
            )

            if step == 0:
                removable = base & ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
            else:
                removable = base & ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)

            if np.any(removable):
                image[removable] = 0
                changed = True

    return (image * 255).astype(np.uint8)


def skeleton_neighbors(pixel: Tuple[int, int], pixels: set[Tuple[int, int]]) -> List[Tuple[int, int]]:
    x, y = pixel
    result = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            neighbor = (x + dx, y + dy)
            if neighbor in pixels:
                result.append(neighbor)
    return result


def trace_skeleton_paths(skeleton: np.ndarray) -> List[Tuple[List[Tuple[float, float]], bool]]:
    coords = np.argwhere(skeleton > 0)
    pixels = {(int(x), int(y)) for y, x in coords}
    if not pixels:
        return []

    neighbor_map = {pixel: skeleton_neighbors(pixel, pixels) for pixel in pixels}
    node_pixels = {pixel for pixel, neighbors in neighbor_map.items() if len(neighbors) != 2}
    visited_edges: set[frozenset[Tuple[int, int]]] = set()
    paths: List[Tuple[List[Tuple[float, float]], bool]] = []

    def edge_key(a: Tuple[int, int], b: Tuple[int, int]) -> frozenset[Tuple[int, int]]:
        return frozenset((a, b))

    for node in node_pixels:
        for neighbor in neighbor_map[node]:
            key = edge_key(node, neighbor)
            if key in visited_edges:
                continue

            path = [node]
            previous = node
            current = neighbor
            visited_edges.add(key)

            while True:
                path.append(current)
                if current in node_pixels and current != node:
                    break

                next_candidates = [item for item in neighbor_map[current] if item != previous]
                if not next_candidates:
                    break

                next_pixel = next_candidates[0]
                next_key = edge_key(current, next_pixel)
                if next_key in visited_edges:
                    break

                visited_edges.add(next_key)
                previous, current = current, next_pixel

            if len(path) >= 2:
                paths.append(([(float(x), float(y)) for x, y in path], False))

    for pixel in pixels:
        if any(edge_key(pixel, neighbor) not in visited_edges for neighbor in neighbor_map[pixel]):
            start = pixel
            neighbor = neighbor_map[start][0]
            path = [start]
            previous = start
            current = neighbor
            visited_edges.add(edge_key(start, neighbor))

            while current != start:
                path.append(current)
                next_candidates = [item for item in neighbor_map[current] if item != previous]
                if not next_candidates:
                    break
                next_pixel = next_candidates[0]
                next_key = edge_key(current, next_pixel)
                if next_key in visited_edges and next_pixel != start:
                    break
                visited_edges.add(next_key)
                previous, current = current, next_pixel

            if len(path) >= 3:
                paths.append(([(float(x), float(y)) for x, y in path], True))

    return paths


def point_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return float(math.hypot(a[0] - b[0], a[1] - b[1]))


def polygon_area(points: List[Tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0

    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) / 2.0


def remove_loose_anchor_points(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if len(points) < 3:
        return points

    cleaned: List[Tuple[float, float]] = []
    for point in points:
        if not cleaned or point_distance(cleaned[-1], point) > 0.5:
            cleaned.append(point)

    if len(cleaned) > 1 and point_distance(cleaned[0], cleaned[-1]) <= 0.5:
        cleaned.pop()

    changed = True
    while changed and len(cleaned) >= 3:
        changed = False
        filtered: List[Tuple[float, float]] = []

        for index, point in enumerate(cleaned):
            prev_point = cleaned[index - 1]
            next_point = cleaned[(index + 1) % len(cleaned)]

            if point_distance(prev_point, next_point) <= 0.75:
                changed = True
                continue

            filtered.append(point)

        cleaned = filtered

    changed = True
    while changed and len(cleaned) >= 3:
        changed = False
        filtered = []
        for index, point in enumerate(cleaned):
            prev_point = cleaned[index - 1]
            next_point = cleaned[(index + 1) % len(cleaned)]
            span = point_distance(prev_point, next_point)
            if span > 1.0:
                numerator = abs(
                    (next_point[0] - prev_point[0]) * (prev_point[1] - point[1])
                    - (prev_point[0] - point[0]) * (next_point[1] - prev_point[1])
                )
                distance = numerator / max(1e-9, span)
                if distance <= 0.25:
                    changed = True
                    continue
            filtered.append(point)
        cleaned = filtered

    return cleaned


def remove_neighbor_anchor_points(
    points: List[Tuple[float, float]],
    min_distance_px: float,
    closed: bool = True,
) -> List[Tuple[float, float]]:
    threshold = max(0.0, float(min_distance_px))
    if threshold <= 0.0 or len(points) < 2:
        return points

    if closed:
        if len(points) < 3:
            return points
        cleaned: List[Tuple[float, float]] = []
        for point in points:
            if not cleaned or point_distance(cleaned[-1], point) >= threshold:
                cleaned.append(point)
        if len(cleaned) > 1 and point_distance(cleaned[0], cleaned[-1]) < threshold:
            cleaned.pop()
        return cleaned if len(cleaned) >= 3 else points

    cleaned = [points[0]]
    for point in points[1:-1]:
        if point_distance(cleaned[-1], point) >= threshold:
            cleaned.append(point)
    if len(points) > 1:
        if point_distance(cleaned[-1], points[-1]) >= threshold:
            cleaned.append(points[-1])
        else:
            cleaned[-1] = points[-1]
    return cleaned if len(cleaned) >= 2 else points


def remove_neighbor_anchor_points_from_contours(
    contours: List[DetectedContour],
    min_distance_px: float,
) -> List[DetectedContour]:
    threshold = max(0.0, float(min_distance_px))
    if threshold <= 0.0:
        return contours

    cleaned_contours: List[DetectedContour] = []
    for contour in contours:
        cleaned_points = remove_neighbor_anchor_points(contour.points, threshold, closed=contour.closed)
        cleaned_contours.append(
            DetectedContour(
                rule=contour.rule,
                points=cleaned_points,
                area=contour.area,
                closed=contour.closed,
                is_hole=contour.is_hole,
                raw_points=contour.raw_points,
            )
        )
    return cleaned_contours


def smooth_closed_points(
    points: List[Tuple[float, float]],
    iterations: int
) -> List[Tuple[float, float]]:
    if iterations <= 0 or len(points) < 3:
        return points

    smoothed = points
    for _ in range(iterations):
        next_points: List[Tuple[float, float]] = []
        for index, point in enumerate(smoothed):
            next_point = smoothed[(index + 1) % len(smoothed)]
            q = (
                point[0] * 0.75 + next_point[0] * 0.25,
                point[1] * 0.75 + next_point[1] * 0.25
            )
            r = (
                point[0] * 0.25 + next_point[0] * 0.75,
                point[1] * 0.25 + next_point[1] * 0.75
            )
            next_points.extend((q, r))
        smoothed = next_points

    return smoothed


def smooth_open_points(
    points: List[Tuple[float, float]],
    iterations: int
) -> List[Tuple[float, float]]:
    if iterations <= 0 or len(points) < 3:
        return points

    smoothed = points
    for _ in range(iterations):
        next_points = [smoothed[0]]
        for index in range(len(smoothed) - 1):
            point = smoothed[index]
            next_point = smoothed[index + 1]
            q = (
                point[0] * 0.75 + next_point[0] * 0.25,
                point[1] * 0.75 + next_point[1] * 0.25
            )
            r = (
                point[0] * 0.25 + next_point[0] * 0.75,
                point[1] * 0.25 + next_point[1] * 0.75
            )
            next_points.extend((q, r))
        next_points.append(smoothed[-1])
        smoothed = next_points

    return smoothed


def smooth_contours(
    contours: List[DetectedContour],
    iterations: int,
) -> List[DetectedContour]:
    if iterations <= 0:
        return contours

    result: List[DetectedContour] = []
    for contour in contours:
        if contour.closed:
            points = smooth_closed_points(contour.points, iterations)
        else:
            points = smooth_open_points(contour.points, iterations)
        result.append(
            DetectedContour(
                rule=contour.rule,
                points=points,
                area=contour.area,
                closed=contour.closed,
                is_hole=contour.is_hole,
                raw_points=contour.raw_points,
            )
        )
    return result


def _ellipse_points(
    center: Tuple[float, float],
    axes: Tuple[float, float],
    angle_deg: float,
    count: int,
) -> List[Tuple[float, float]]:
    cx, cy = center
    rx = max(0.1, float(axes[0]) * 0.5)
    ry = max(0.1, float(axes[1]) * 0.5)
    angle = math.radians(float(angle_deg))
    ca = math.cos(angle)
    sa = math.sin(angle)
    points: List[Tuple[float, float]] = []
    for index in range(max(12, int(count))):
        t = (2.0 * math.pi * index) / max(12, int(count))
        x = math.cos(t) * rx
        y = math.sin(t) * ry
        points.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return points


def _ellipse_fit_error(points: List[Tuple[float, float]], ellipse: Any) -> float:
    (cx, cy), (major, minor), angle_deg = ellipse
    rx = max(0.1, float(major) * 0.5)
    ry = max(0.1, float(minor) * 0.5)
    angle = math.radians(float(angle_deg))
    ca = math.cos(-angle)
    sa = math.sin(-angle)
    errors: List[float] = []
    for x, y in points:
        dx = float(x) - float(cx)
        dy = float(y) - float(cy)
        lx = dx * ca - dy * sa
        ly = dx * sa + dy * ca
        radius = math.sqrt((lx / rx) ** 2 + (ly / ry) ** 2)
        errors.append(abs(radius - 1.0))
    if not errors:
        return 999.0
    return float(sum(errors) / len(errors))


def regularize_circular_contours(
    contours: List[DetectedContour],
    min_area: float = 80.0,
    circularity_threshold: float = 0.70,
    max_fit_error: float = 0.075,
) -> List[DetectedContour]:
    """Replace clean round/elliptic closed contours with stable ellipse samples."""
    regularized: List[DetectedContour] = []
    for contour in contours:
        points = contour.points
        if not contour.closed or len(points) < 12 or abs(float(contour.area)) < float(min_area):
            regularized.append(contour)
            continue

        pts = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
        perimeter = float(cv2.arcLength(pts, True))
        area = abs(float(cv2.contourArea(pts)))
        if perimeter <= 1e-6 or area <= 1e-6:
            regularized.append(contour)
            continue

        circularity = (4.0 * math.pi * area) / (perimeter * perimeter)
        x, y, w, h = cv2.boundingRect(pts.astype(np.int32))
        aspect = float(w) / max(1.0, float(h))
        if circularity < circularity_threshold or aspect < 0.45 or aspect > 2.20 or len(points) < 5:
            regularized.append(contour)
            continue

        try:
            ellipse = cv2.fitEllipse(pts)
        except Exception:
            regularized.append(contour)
            continue

        fit_error = _ellipse_fit_error(points, ellipse)
        if fit_error > max_fit_error:
            regularized.append(contour)
            continue

        (_center, axes, _angle) = ellipse
        longest_axis = max(float(axes[0]), float(axes[1]))
        sample_count = int(max(24, min(128, round(longest_axis * 0.75))))
        new_points = _ellipse_points(ellipse[0], axes, ellipse[2], sample_count)
        regularized.append(
            DetectedContour(
                rule=contour.rule,
                points=new_points,
                area=contour.area,
                closed=True,
                is_hole=contour.is_hole,
                raw_points=contour.raw_points,
            )
        )
    return regularized


def approximate_points(
    points: List[Tuple[float, float]],
    epsilon: float,
    closed: bool = True
) -> List[Tuple[float, float]]:
    if epsilon <= 0 or len(points) < 3:
        return points

    contour = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
    approximated = cv2.approxPolyDP(contour, epsilon, closed=closed)
    pts = approximated.reshape(-1, 2)
    return [(float(x), float(y)) for x, y in pts]


def _point_line_distance(
    point: Tuple[float, float],
    start: Tuple[float, float],
    end: Tuple[float, float],
) -> float:
    length = point_distance(start, end)
    if length <= 1e-9:
        return point_distance(point, start)
    return abs(
        (end[0] - start[0]) * (start[1] - point[1])
        - (start[0] - point[0]) * (end[1] - start[1])
    ) / length


def _turn_angle_deg(
    previous: Tuple[float, float],
    current: Tuple[float, float],
    next_point: Tuple[float, float],
) -> float:
    ax = current[0] - previous[0]
    ay = current[1] - previous[1]
    bx = next_point[0] - current[0]
    by = next_point[1] - current[1]
    la = math.hypot(ax, ay)
    lb = math.hypot(bx, by)
    if la <= 1e-9 or lb <= 1e-9:
        return 0.0
    dot = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
    return math.degrees(math.acos(dot))


def _dedupe_consecutive_points(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    cleaned: List[Tuple[float, float]] = []
    for point in points:
        if not cleaned or point_distance(cleaned[-1], point) > 0.01:
            cleaned.append(point)
    if len(cleaned) > 1 and point_distance(cleaned[0], cleaned[-1]) <= 0.01:
        cleaned.pop()
    return cleaned


def _split_smart_sections(
    points: List[Tuple[float, float]],
    protected: set[int],
    closed: bool,
) -> List[List[int]]:
    count = len(points)
    if count == 0:
        return []

    if not protected:
        return [list(range(count))]

    sections: List[List[int]] = []
    ordered = sorted(protected)
    if closed:
        for pos, start in enumerate(ordered):
            end = ordered[(pos + 1) % len(ordered)]
            section = [start]
            idx = (start + 1) % count
            while idx != end:
                section.append(idx)
                idx = (idx + 1) % count
            section.append(end)
            if len(section) >= 2:
                sections.append(section)
        return sections

    boundaries = sorted({0, count - 1, *protected})
    for start, end in zip(boundaries, boundaries[1:]):
        if end > start:
            sections.append(list(range(start, end + 1)))
    return sections


def _smooth_section_points(
    section_points: List[Tuple[float, float]],
    strength: int,
) -> List[Tuple[float, float]]:
    if strength <= 0 or len(section_points) < 4:
        return section_points

    smoothed = section_points[:]
    for _ in range(max(0, min(5, int(strength)))):
        next_points = [smoothed[0]]
        for index in range(1, len(smoothed) - 1):
            prev_point = smoothed[index - 1]
            point = smoothed[index]
            next_point = smoothed[index + 1]
            next_points.append(
                (
                    point[0] * 0.50 + (prev_point[0] + next_point[0]) * 0.25,
                    point[1] * 0.50 + (prev_point[1] + next_point[1]) * 0.25,
                )
            )
        next_points.append(smoothed[-1])
        smoothed = next_points
    return smoothed


def _section_is_straight(
    section_points: List[Tuple[float, float]],
    line_tolerance_px: float,
) -> bool:
    if len(section_points) <= 2:
        return True
    start = section_points[0]
    end = section_points[-1]
    if point_distance(start, end) <= 1e-9:
        return False
    max_deviation = max(_point_line_distance(point, start, end) for point in section_points[1:-1])
    return max_deviation <= max(0.0, float(line_tolerance_px))


def _section_has_continuous_direction_change(section_points: List[Tuple[float, float]]) -> bool:
    if len(section_points) < 4:
        return False

    signed_turns: List[float] = []
    for index in range(1, len(section_points) - 1):
        prev_point = section_points[index - 1]
        point = section_points[index]
        next_point = section_points[index + 1]
        ax = point[0] - prev_point[0]
        ay = point[1] - prev_point[1]
        bx = next_point[0] - point[0]
        by = next_point[1] - point[1]
        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la <= 1e-9 or lb <= 1e-9:
            continue
        cross = ax * by - ay * bx
        dot = ax * bx + ay * by
        turn = math.degrees(math.atan2(cross, dot))
        if abs(turn) >= 2.0:
            signed_turns.append(turn)

    if len(signed_turns) < 2:
        return False

    positive = sum(1 for turn in signed_turns if turn > 0)
    negative = sum(1 for turn in signed_turns if turn < 0)
    dominant = max(positive, negative)
    total_turn = sum(abs(turn) for turn in signed_turns)
    return dominant >= 2 and dominant / len(signed_turns) >= 0.60 and total_turn >= 8.0


def smart_smooth_contour(
    points: List[Tuple[float, float]],
    closed: bool,
    corner_angle_deg: float,
    line_tolerance_px: float,
    curve_smoothing_strength: int,
) -> List[Tuple[float, float]]:
    """Preserve CAD corners/lines and smooth only curved or noisy sections."""
    if len(points) < 4 or curve_smoothing_strength <= 0:
        return points

    pts = _dedupe_consecutive_points([(float(x), float(y)) for x, y in points])
    count = len(pts)
    if count < 4:
        return pts

    protected: set[int] = set()
    threshold = max(1.0, min(175.0, float(corner_angle_deg)))
    start = 0 if closed else 1
    end = count if closed else count - 1
    for index in range(start, end):
        prev_point = pts[(index - 1) % count]
        point = pts[index]
        next_point = pts[(index + 1) % count]
        if _turn_angle_deg(prev_point, point, next_point) >= threshold:
            protected.add(index)

    if closed and not protected:
        return smooth_closed_points(pts, curve_smoothing_strength)

    sections = _split_smart_sections(pts, protected, closed=closed)
    if not sections:
        return pts

    result: List[Tuple[float, float]] = []
    for section in sections:
        section_points = [pts[index] for index in section]
        if len(section_points) <= 2 or _section_is_straight(section_points, line_tolerance_px):
            processed = [section_points[0], section_points[-1]]
        elif _section_has_continuous_direction_change(section_points):
            processed = _smooth_section_points(section_points, curve_smoothing_strength)
        else:
            processed = section_points

        if result and processed and point_distance(result[-1], processed[0]) <= 0.01:
            result.extend(processed[1:])
        else:
            result.extend(processed)

    return _dedupe_consecutive_points(result)


def smart_smooth_contours(
    contours: List[DetectedContour],
    corner_angle_deg: float,
    line_tolerance_px: float,
    curve_smoothing_strength: int,
) -> List[DetectedContour]:
    if curve_smoothing_strength <= 0:
        return contours

    smoothed: List[DetectedContour] = []
    for contour in contours:
        if len(contour.points) < 4:
            smoothed.append(contour)
            continue
        new_points = smart_smooth_contour(
            contour.points,
            closed=contour.closed,
            corner_angle_deg=corner_angle_deg,
            line_tolerance_px=line_tolerance_px,
            curve_smoothing_strength=curve_smoothing_strength,
        )
        smoothed.append(
            DetectedContour(
                rule=contour.rule,
                points=new_points,
                area=contour.area,
                closed=contour.closed,
                is_hole=contour.is_hole,
                raw_points=contour.raw_points,
            )
        )
    return smoothed


def scale_hole_contours(
    contours: List[DetectedContour],
    hole_scale: float
) -> List[DetectedContour]:
    """Skaliert nur Innenlöcher um ihren Schwerpunkt.

    hole_scale < 1.0: Loch kleiner
    hole_scale > 1.0: Loch größer
    """
    factor = max(0.20, min(2.50, float(hole_scale)))
    if abs(factor - 1.0) < 1e-6:
        return contours

    scaled: List[DetectedContour] = []
    for contour in contours:
        if not contour.closed or not contour.is_hole or len(contour.points) < 3:
            scaled.append(contour)
            continue

        points = [(float(x), float(y)) for x, y in contour.points]
        cx = sum(x for x, _y in points) / len(points)
        cy = sum(y for _x, y in points) / len(points)
        new_points = [
            (cx + (x - cx) * factor, cy + (y - cy) * factor)
            for x, y in points
        ]
        new_area = max(0.0, float(contour.area) * factor * factor)
        scaled.append(
            DetectedContour(
                rule=contour.rule,
                points=new_points,
                area=new_area,
                closed=contour.closed,
                is_hole=contour.is_hole,
                raw_points=contour.raw_points,
            )
        )
    return scaled


def _closed_polyline_perimeter(points: List[Tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        total += point_distance(point, next_point)
    return total


def _point_at_closed_distance(
    points: List[Tuple[float, float]],
    target_distance: float,
    perimeter: float,
) -> Tuple[float, float]:
    if not points:
        return (0.0, 0.0)
    if perimeter <= 0:
        return points[0]

    target = target_distance % perimeter
    walked = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        segment_length = point_distance(point, next_point)
        if segment_length <= 1e-9:
            continue
        if walked + segment_length >= target:
            ratio = (target - walked) / segment_length
            return (
                point[0] + (next_point[0] - point[0]) * ratio,
                point[1] + (next_point[1] - point[1]) * ratio,
            )
        walked += segment_length
    return points[-1]


def _distance_in_gap(distance_value: float, gaps: List[Tuple[float, float]], perimeter: float) -> bool:
    if perimeter <= 0:
        return False
    value = distance_value % perimeter
    for start, end in gaps:
        start %= perimeter
        end %= perimeter
        if start <= end:
            if start <= value <= end:
                return True
        elif value >= start or value <= end:
            return True
    return False


def _split_closed_contour_with_gaps(
    points: List[Tuple[float, float]],
    bridge_width_px: float,
    bridge_count: int,
) -> List[List[Tuple[float, float]]]:
    if len(points) < 4:
        return [points]

    clean_points = [(float(x), float(y)) for x, y in points]
    perimeter = _closed_polyline_perimeter(clean_points)
    if perimeter <= 0:
        return [points]

    gap_width = max(0.5, min(float(bridge_width_px), perimeter * 0.20))
    max_count = max(1, int(perimeter / max(gap_width * 2.5, 1.0)))
    count = max(1, min(int(bridge_count), max_count))

    gaps: List[Tuple[float, float]] = []
    for index in range(count):
        center = ((index + 0.5) / count) * perimeter
        gaps.append((center - gap_width / 2.0, center + gap_width / 2.0))

    sample_step = max(0.5, min(2.0, gap_width / 4.0))
    sample_count = max(len(clean_points), int(math.ceil(perimeter / sample_step)))
    sample_count = max(12, min(sample_count, 12000))
    samples = [
        _point_at_closed_distance(clean_points, perimeter * index / sample_count, perimeter)
        for index in range(sample_count)
    ]
    kept = [
        not _distance_in_gap(perimeter * index / sample_count, gaps, perimeter)
        for index in range(sample_count)
    ]

    if all(kept) or not any(kept):
        return [points]

    start_index = 0
    for index, is_kept in enumerate(kept):
        if is_kept and not kept[index - 1]:
            start_index = index
            break

    segments: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    for offset in range(sample_count):
        index = (start_index + offset) % sample_count
        if kept[index]:
            current.append(samples[index])
        elif current:
            if len(current) >= 2:
                segments.append(current)
            current = []
    if len(current) >= 2:
        segments.append(current)

    return segments or [points]


def apply_bridge_tabs(
    contours: List[DetectedContour],
    bridge_width_px: float,
    bridge_count: int = 2,
    image_size: Optional[Tuple[int, int]] = None,
    include_holes: bool = True,
    include_small_islands: bool = True,
) -> List[DetectedContour]:
    """Öffnet Fallteil-Risikokonturen mit kurzen Stegen.

    Die Funktion erzeugt keine neuen Formen, sondern setzt echte Lücken in
    geschlossene Konturen. Dadurch sind Vorschau, SVG und DXF deckungsgleich.
    """
    width = max(0.0, float(bridge_width_px))
    if width <= 0 or bridge_count <= 0:
        return contours

    closed_areas = [abs(float(c.area)) for c in contours if c.closed and not c.is_hole and c.rule.export]
    max_area = max(closed_areas) if closed_areas else 0.0
    if image_size:
        image_area = max(1.0, float(image_size[0] * image_size[1]))
    else:
        image_area = max(max_area, 1.0)
    small_limit = max(16.0, min(image_area * 0.015, max_area * 0.20 if max_area else image_area * 0.015))

    result: List[DetectedContour] = []
    for contour in contours:
        if not contour.rule.export or not contour.closed or len(contour.points) < 4:
            result.append(contour)
            continue

        is_risk = (include_holes and contour.is_hole) or (
            include_small_islands and not contour.is_hole and abs(float(contour.area)) <= small_limit
        )
        if not is_risk:
            result.append(contour)
            continue

        segments = _split_closed_contour_with_gaps(contour.points, width, bridge_count)
        if len(segments) == 1 and segments[0] == contour.points:
            result.append(contour)
            continue
        for segment in segments:
            result.append(
                DetectedContour(
                    rule=contour.rule,
                    points=segment,
                    area=0.0,
                    closed=False,
                    is_hole=False,
                    raw_points=segment,
                )
            )
    return result


def is_closed_path(points: List[Tuple[float, float]]) -> bool:
    return len(points) >= 3 and polygon_area(points) > 0.0


def contour_area_mm2(points: List[Tuple[float, float]], pixel_to_mm: float) -> float:
    if not points:
        return 0.0

    return polygon_area(points) * pixel_to_mm * pixel_to_mm


def contour_filter_area_mm2(contour: DetectedContour, pixel_to_mm: float) -> float:
    if contour.closed:
        return contour_area_mm2(contour.points, pixel_to_mm)

    if not contour.points:
        return 0.0

    xs = [point[0] for point in contour.points]
    ys = [point[1] for point in contour.points]
    return (max(xs) - min(xs)) * (max(ys) - min(ys)) * pixel_to_mm * pixel_to_mm


def contour_filter_area_px(contour: DetectedContour) -> float:
    if contour.closed:
        return polygon_area(contour.points)

    if not contour.points:
        return 0.0

    xs = [point[0] for point in contour.points]
    ys = [point[1] for point in contour.points]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def contour_bbox(contour: DetectedContour) -> Tuple[float, float, float, float]:
    if not contour.points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [point[0] for point in contour.points]
    ys = [point[1] for point in contour.points]
    return (min(xs), min(ys), max(xs), max(ys))


def _bboxes_touch(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
    tolerance_px: float,
) -> bool:
    tol = max(0.0, float(tolerance_px))
    return not (
        a[2] + tol < b[0]
        or b[2] + tol < a[0]
        or a[3] + tol < b[1]
        or b[3] + tol < a[1]
    )


def group_connected_contours(
    contours: List[DetectedContour],
    tolerance_px: float = 2.0,
) -> List[List[DetectedContour]]:
    exported = [contour for contour in contours if contour.rule.export and contour.points]
    count = len(exported)
    if count <= 1:
        return [exported] if exported else []

    bboxes = [contour_bbox(contour) for contour in exported]
    visited = [False] * count
    groups: List[List[DetectedContour]] = []
    for start in range(count):
        if visited[start]:
            continue
        stack = [start]
        visited[start] = True
        group: List[DetectedContour] = []
        while stack:
            current = stack.pop()
            group.append(exported[current])
            for candidate in range(count):
                if visited[candidate]:
                    continue
                if _bboxes_touch(bboxes[current], bboxes[candidate], tolerance_px):
                    visited[candidate] = True
                    stack.append(candidate)
        groups.append(group)
    return groups


def sanitize_dxf_layer_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_-$" else "_" for ch in (name or "Layer"))
    cleaned = cleaned.strip("_") or "Layer"
    return cleaned[:240]


def color_layer_for_rule(rule: ColorRule, force_color_layers: bool = True) -> str:
    base = sanitize_dxf_layer_name(rule.layer or rule.name)
    if not force_color_layers:
        return base
    rgb_suffix = f"RGB_{int(rule.rgb[0]):03d}_{int(rule.rgb[1]):03d}_{int(rule.rgb[2]):03d}"
    if rgb_suffix in base:
        return base
    return sanitize_dxf_layer_name(f"{base}_{rgb_suffix}")


def dxf_layer_for_rule(rule: ColorRule, force_color_layers: bool = True) -> str:
    return color_layer_for_rule(rule, force_color_layers=force_color_layers)


def _keep_hole_contour(contour: DetectedContour, preserve_tiny_holes: bool = True) -> bool:
    """Innenloecher moeglichst erhalten, nur echte Kleinstartefakte verwerfen."""
    if not preserve_tiny_holes:
        return False
    if not getattr(contour, "is_hole", False):
        return False
    return contour_filter_area_px(contour) >= 1.5


def remove_contours_smaller_than_mm2(
    contours: List[DetectedContour],
    min_area_mm2: float,
    pixel_to_mm: float,
    preserve_tiny_holes: bool = True
) -> List[DetectedContour]:
    if min_area_mm2 <= 0:
        return contours

    return [
        contour
        for contour in contours
        if _keep_hole_contour(contour, preserve_tiny_holes) or contour_filter_area_mm2(contour, pixel_to_mm) >= min_area_mm2
    ]


def remove_contours_smaller_than_percent(
    contours: List[DetectedContour],
    min_percent: float,
    image_size: Tuple[int, int],
    preserve_tiny_holes: bool = True
) -> List[DetectedContour]:
    if min_percent <= 0:
        return contours

    width, height = image_size
    min_area_px = max(0.0, width * height * (min_percent / 100.0))
    return [
        contour
        for contour in contours
        if _keep_hole_contour(contour, preserve_tiny_holes) or contour_filter_area_px(contour) >= min_area_px
    ]


def filter_small_contours(
    contours: List[DetectedContour],
    mode: str,
    min_area_mm2: float,
    min_percent: float,
    image_size: Tuple[int, int],
    pixel_to_mm: float,
    preserve_tiny_holes: bool = False
) -> List[DetectedContour]:
    if mode in ("mm²", "mm2"):
        return remove_contours_smaller_than_mm2(contours, min_area_mm2, pixel_to_mm, preserve_tiny_holes)
    if mode in ("% Bildfläche", "percent"):
        return remove_contours_smaller_than_percent(contours, min_percent, image_size, preserve_tiny_holes)
    return contours


def build_polyline_path(points: List[Tuple[float, float]], closed: bool) -> str:
    if not points:
        return ""

    d = [f"M {points[0][0]:.4f},{points[0][1]:.4f}"]
    for x, y in points[1:]:
        d.append(f"L {x:.4f},{y:.4f}")
    if closed:
        d.append("Z")
    return " ".join(d)


def build_bezier_path(points: List[Tuple[float, float]], closed: bool) -> str:
    if len(points) < 3:
        return build_polyline_path(points, closed)

    path_points = points if closed else points[:]
    d = [f"M {path_points[0][0]:.4f},{path_points[0][1]:.4f}"]
    count = len(path_points)

    segment_count = count if closed else count - 1
    for index in range(segment_count):
        p0 = path_points[index - 1] if index > 0 else (path_points[-1] if closed else path_points[0])
        p1 = path_points[index]
        p2 = path_points[(index + 1) % count]
        p3 = path_points[(index + 2) % count] if (index + 2 < count or closed) else path_points[-1]

        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append(
            f"C {c1[0]:.4f},{c1[1]:.4f} "
            f"{c2[0]:.4f},{c2[1]:.4f} "
            f"{p2[0]:.4f},{p2[1]:.4f}"
        )

    if closed:
        d.append("Z")
    return " ".join(d)



def iter_contour_segments(
    contours: List[DetectedContour],
    exported_only: bool = True
) -> List[Tuple[DetectedContour, Tuple[float, float], Tuple[float, float]]]:
    """Gibt alle Kontursegmente als Einzelsegmente zurück.

    CAD-Hintergrund:
    Wenn zwei Farbflächen dieselbe Grenze erzeugen, entstehen sonst zwei Linien
    übereinander bzw. knapp parallel nebeneinander. Für CAD/CAM/Plotter ist das
    problematisch, daher können diese Segmente anschließend entdoppelt werden.
    """
    segments: List[Tuple[DetectedContour, Tuple[float, float], Tuple[float, float]]] = []
    for contour in contours:
        if exported_only and not contour.rule.export:
            continue
        pts = contour.points
        if len(pts) < 2:
            continue
        limit = len(pts) if contour.closed and len(pts) >= 3 else len(pts) - 1
        for index in range(limit):
            a = pts[index]
            b = pts[(index + 1) % len(pts)]
            if point_distance(a, b) <= 0.01:
                continue
            segments.append((contour, a, b))
    return segments


def _segment_angle_bin(a: Tuple[float, float], b: Tuple[float, float], bin_count: int = 36) -> int:
    """Orientierung eines Segments, modulo 180 Grad."""
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    if angle < 0:
        angle += math.pi
    if angle >= math.pi:
        angle -= math.pi
    return int(round(angle / math.pi * bin_count)) % bin_count


def _sample_segment_keys(
    a: Tuple[float, float],
    b: Tuple[float, float],
    tolerance_px: float,
    bin_count: int = 36
) -> set[Tuple[int, int, int]]:
    """Rastert ein Segment robust ein."""
    tol = max(0.25, float(tolerance_px))
    length = point_distance(a, b)
    if length <= 0.01:
        return set()
    steps = max(2, int(math.ceil(length / max(0.5, tol * 0.5))))
    angle_bin = _segment_angle_bin(a, b, bin_count=bin_count)
    keys: set[Tuple[int, int, int]] = set()
    for i in range(steps + 1):
        t = i / steps
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        gx = int(round(x / tol))
        gy = int(round(y / tol))
        keys.add((angle_bin, gx, gy))
    return keys


def unique_line_segments_from_contours(
    contours: List[DetectedContour],
    tolerance_px: float = 1.25,
    exported_only: bool = True,
    match_ratio: float = 0.72
) -> List[Tuple[ColorRule, Tuple[float, float], Tuple[float, float]]]:
    """Entfernt doppelte oder fast deckungsgleiche CAD-Liniensegmente.

    tolerance_px:
        Abstand in Bildpixeln, innerhalb dessen Linien als doppelt gelten.
        1.0 bis 2.0 ist meist passend für PNG-Konturen.
    """
    tol = max(0.25, float(tolerance_px))
    bin_count = 36
    occupied: dict[Tuple[int, int, int], set[int]] = {}
    result: List[Tuple[ColorRule, Tuple[float, float], Tuple[float, float]]] = []
    for contour_index, contour in enumerate(contours):
        if exported_only and not contour.rule.export:
            continue
        pts = contour.points
        if len(pts) < 2:
            continue
        limit = len(pts) if contour.closed and len(pts) >= 3 else len(pts) - 1
        for point_index in range(limit):
            a = pts[point_index]
            b = pts[(point_index + 1) % len(pts)]
            if point_distance(a, b) <= 0.01:
                continue
            keys = _sample_segment_keys(a, b, tol, bin_count=bin_count)
            if not keys:
                continue
            matched = 0
            for angle_bin, gx, gy in keys:
                found = False
                for db in (-1, 0, 1):
                    nb = (angle_bin + db) % bin_count
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            owners = occupied.get((nb, gx + dx, gy + dy), set())
                            if any(owner != contour_index for owner in owners):
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    matched += 1
            if matched / max(1, len(keys)) >= match_ratio:
                continue
            result.append((contour.rule, a, b))
            for angle_bin, gx, gy in keys:
                for db in (-1, 0, 1):
                    nb = (angle_bin + db) % bin_count
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            occupied.setdefault((nb, gx + dx, gy + dy), set()).add(contour_index)
    return result


def count_export_line_segments(contours: List[DetectedContour]) -> int:
    return len(iter_contour_segments(contours, exported_only=True))


def render_contours_to_mask(
    contours: List[DetectedContour],
    image_size: Tuple[int, int],
    stroke_width: int = 3
) -> np.ndarray:
    width, height = image_size
    mask = np.zeros((height, width), dtype=np.uint8)

    # Konturen in erkannter Reihenfolge rendern.
    # So bleiben verschachtelte Formen stabil:
    # Außenform -> Loch -> Inneninsel.
    for contour in contours:
        if not contour.points:
            continue

        pts = np.array(
            [[int(round(x)), int(round(y))] for x, y in contour.points],
            dtype=np.int32
        )

        if contour.closed and len(pts) >= 3:
            fill_value = 0 if getattr(contour, "is_hole", False) else 255
            cv2.fillPoly(mask, [pts], int(fill_value))
        elif len(pts) >= 2:
            cv2.polylines(mask, [pts], isClosed=False, color=255, thickness=max(1, stroke_width))

    return mask

def score_vector_result(
    image_rgb: np.ndarray,
    rules: List[ColorRule],
    contours: List[DetectedContour],
    centerline_mode: bool
) -> float:
    target = np.zeros(image_rgb.shape[:2], dtype=np.uint8)
    for rule in rules:
        if not rule.export:
            continue
        mask = make_color_mask(image_rgb, rule.rgb, rule.tolerance)
        mask = remove_small_components(mask, rule.min_area)
        target = cv2.bitwise_or(target, mask)

    stroke_width = 3 if centerline_mode else 1
    rendered = render_contours_to_mask(
        contours,
        (image_rgb.shape[1], image_rgb.shape[0]),
        stroke_width=stroke_width
    )

    target_bool = target > 0
    rendered_bool = rendered > 0
    intersection = np.logical_and(target_bool, rendered_bool).sum()
    union = np.logical_or(target_bool, rendered_bool).sum()
    if union == 0:
        return 0.0

    point_penalty = min(0.25, sum(len(contour.points) for contour in contours) / 250000.0)
    return float(intersection / union) - point_penalty


def find_contours_for_rule(
    image_rgb: np.ndarray,
    rule: ColorRule,
    closed_paths_only: bool = False,
    remove_loose_points: bool = False,
    smooth_iterations: int = 0,
    mask_edge_smoothing: float = 0.0,
    mask_noise_area: float = 0.0,
) -> List[DetectedContour]:
    mask = make_color_mask(image_rgb, rule.rgb, rule.tolerance)
    mask = remove_small_components(mask, rule.min_area)
    mask = calm_mask_edges(mask, mask_edge_smoothing, mask_noise_area)

    contours, hierarchy = cv2.findContours(
        mask,
        cv2.RETR_CCOMP,
        cv2.CHAIN_APPROX_NONE
    )

    result: List[DetectedContour] = []
    hierarchy_view = hierarchy[0] if hierarchy is not None and len(hierarchy) > 0 else None

    for contour_index, contour in enumerate(contours):
        parent = -1
        if hierarchy_view is not None and contour_index < len(hierarchy_view):
            parent = int(hierarchy_view[contour_index][3])
        is_hole = parent != -1
        area = abs(cv2.contourArea(contour))
        if is_hole:
            if area < 0.5:
                continue
        else:
            if area < rule.min_area:
                continue

        pts = contour.reshape(-1, 2)
        if len(pts) < 3:
            continue

        points = [(float(x), float(y)) for x, y in pts]
        if smooth_iterations > 0:
            points = smooth_closed_points(points, smooth_iterations)
        raw_points = list(points)

        epsilon = max(0.0, float(rule.epsilon))
        points = approximate_points(points, epsilon)

        if remove_loose_points:
            points = remove_loose_anchor_points(points)

        if len(points) < 3:
            continue

        if closed_paths_only and not is_closed_path(points):
            continue

        result.append(DetectedContour(rule=rule, points=points, area=area, is_hole=is_hole, raw_points=raw_points))

    return result


def find_centerlines_for_rule(
    image_rgb: np.ndarray,
    rule: ColorRule,
    remove_loose_points: bool = False,
    merge_distance_px: float = 0.0,
    mask_edge_smoothing: float = 0.0,
    mask_noise_area: float = 0.0,
) -> List[DetectedContour]:
    mask = make_color_mask(image_rgb, rule.rgb, rule.tolerance)
    mask = merge_nearby_mask_lines(mask, merge_distance_px)
    mask = remove_small_components(mask, rule.min_area)
    mask = calm_mask_edges(mask, mask_edge_smoothing, mask_noise_area)
    point_scale = 1.0
    height, width = mask.shape[:2]
    max_dim = max(height, width)
    if max_dim > 1400:
        point_scale = max_dim / 1400.0
        new_width = max(1, int(round(width / point_scale)))
        new_height = max(1, int(round(height / point_scale)))
        mask = cv2.resize(mask, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
    skeleton = zhang_suen_thinning(mask)
    paths = trace_skeleton_paths(skeleton)

    result: List[DetectedContour] = []
    epsilon = max(0.0, float(rule.epsilon))

    for points, closed in paths:
        if len(points) < 2:
            continue

        if point_scale != 1.0:
            points = [(float(x) * point_scale, float(y) * point_scale) for x, y in points]
        raw_points = list(points)
        points = approximate_points(points, epsilon, closed=closed)
        if remove_loose_points and closed:
            points = remove_loose_anchor_points(points)

        if len(points) < 2:
            continue

        result.append(
            DetectedContour(
                rule=rule,
                points=points,
                area=float(len(points)),
                closed=closed,
                is_hole=False,
                raw_points=raw_points,
            )
        )

    return result


def detect_all_contours(
    image_rgb: np.ndarray,
    rules: List[ColorRule],
    closed_paths_only: bool = False,
    remove_loose_points: bool = False,
    smooth_iterations: int = 0,
    centerline_mode: bool = False,
    centerline_merge_px: float = 0.0,
    preprocess_enabled: bool = False,
    preprocess_blur: float = 0.0,
    preprocess_edge_smoothing: float = 0.0,
    preprocess_noise_area: float = 0.0,
    internal_scale: int = 1,
    progress_callback=None
) -> List[DetectedContour]:
    all_contours: List[DetectedContour] = []
    scale = 1 if centerline_mode else max(1, min(3, int(internal_scale)))
    work_image = preprocess_vector_image(
        image_rgb,
        enabled=preprocess_enabled,
        blur_radius=preprocess_blur,
        edge_smoothing=preprocess_edge_smoothing,
    )
    work_image = upscale_vector_image(work_image, scale)
    area_scale = scale * scale
    scaled_rules = [
        ColorRule(
            name=rule.name,
            rgb=rule.rgb,
            tolerance=rule.tolerance,
            layer=rule.layer,
            export=rule.export,
            min_area=max(0, int(round(rule.min_area * area_scale))),
            epsilon=max(0.0, float(rule.epsilon) * scale),
        )
        for rule in rules
    ]
    original_rule_by_scaled_id = {
        id(scaled_rule): original_rule
        for scaled_rule, original_rule in zip(scaled_rules, rules)
    }
    mask_noise_area = max(0.0, float(preprocess_noise_area) * area_scale) if preprocess_enabled else 0.0
    mask_edge_smoothing = max(0.0, min(5.0, float(preprocess_edge_smoothing))) if preprocess_enabled else 0.0
    merge_px = centerline_merge_px * scale
    total_rules = max(1, len(rules))
    for index, rule in enumerate(scaled_rules):
        if progress_callback is not None:
            progress_callback(index / total_rules)

        if centerline_mode:
            all_contours.extend(
                find_centerlines_for_rule(
                    work_image,
                    rule,
                    remove_loose_points=remove_loose_points,
                    merge_distance_px=merge_px,
                    mask_edge_smoothing=mask_edge_smoothing,
                    mask_noise_area=mask_noise_area,
                )
            )
        else:
            all_contours.extend(
                find_contours_for_rule(
                    work_image,
                    rule,
                    closed_paths_only=closed_paths_only,
                    remove_loose_points=remove_loose_points,
                    smooth_iterations=smooth_iterations,
                    mask_edge_smoothing=mask_edge_smoothing,
                    mask_noise_area=mask_noise_area,
                )
            )

        if progress_callback is not None:
            progress_callback((index + 1) / total_rules)

    restored: List[DetectedContour] = []
    for contour in all_contours:
        original_rule = original_rule_by_scaled_id.get(id(contour.rule), contour.rule)
        restored.append(
            DetectedContour(
                rule=original_rule,
                points=[(x / scale, y / scale) for x, y in contour.points],
                area=contour.area / area_scale,
                closed=contour.closed,
                is_hole=contour.is_hole,
                raw_points=[(x / scale, y / scale) for x, y in contour.raw_points] if contour.raw_points else None,
            )
        )
    return restored


def export_svg(
    output_path: str,
    image_size: Tuple[int, int],
    contours: List[DetectedContour],
    pixel_to_mm: float,
    fill_closed_shapes: bool = False,
    use_bezier: bool = False,
    group_connected_paths: bool = False,
    force_color_layers: bool = False
) -> None:
    width_px, height_px = image_size
    width_mm = width_px * pixel_to_mm
    height_mm = height_px * pixel_to_mm

    dwg = svgwrite.Drawing(
        output_path,
        size=(f"{width_mm}mm", f"{height_mm}mm"),
        viewBox=f"0 0 {width_mm} {height_mm}"
    )

    groups: Dict[str, Any] = {}

    if fill_closed_shapes:
        # Gefüllte SVGs brauchen bei Innenlöchern eine zusammengesetzte Pfadstruktur.
        # Mehrere getrennt gefüllte Einzelpfade würden Löcher wieder zufüllen.
        # evenodd ist nicht perfekt für alle überlappenden Sonderfälle, aber deutlich
        # robuster als jedes Polygon einzeln zu füllen.
        layer_paths: Dict[str, list[str]] = {}
        layer_colors: Dict[str, str] = {}

        for item in contours:
            if not item.rule.export:
                continue
            layer = color_layer_for_rule(item.rule, force_color_layers=force_color_layers)
            if layer not in groups:
                groups[layer] = dwg.g(id=layer)
                dwg.add(groups[layer])
            scaled = [(x * pixel_to_mm, y * pixel_to_mm) for x, y in item.points]
            if not scaled:
                continue
            path_data = build_bezier_path(scaled, item.closed) if use_bezier else build_polyline_path(scaled, item.closed)
            if item.closed and len(scaled) >= 3:
                layer_paths.setdefault(layer, []).append(path_data)
                layer_colors[layer] = rgb_to_hex(item.rule.rgb)
            elif not group_connected_paths:
                groups[layer].add(
                    dwg.path(
                        d=path_data,
                        fill="none",
                        stroke=rgb_to_hex(item.rule.rgb),
                        stroke_width=max(0.05, pixel_to_mm)
                    )
                )

        if group_connected_paths:
            for group_index, group_contours in enumerate(group_connected_contours(contours)):
                parts_by_layer: Dict[str, list[str]] = {}
                colors_by_layer: Dict[str, str] = {}
                for item in group_contours:
                    layer = color_layer_for_rule(item.rule, force_color_layers=force_color_layers)
                    scaled = [(x * pixel_to_mm, y * pixel_to_mm) for x, y in item.points]
                    if not scaled:
                        continue
                    path_data = build_bezier_path(scaled, item.closed) if use_bezier else build_polyline_path(scaled, item.closed)
                    parts_by_layer.setdefault(layer, []).append(path_data)
                    colors_by_layer[layer] = rgb_to_hex(item.rule.rgb)
                for layer, parts in parts_by_layer.items():
                    if layer not in groups:
                        groups[layer] = dwg.g(id=layer)
                        dwg.add(groups[layer])
                    object_group = dwg.g(id=f"{layer}_object_{group_index + 1}")
                    object_group.add(
                        dwg.path(
                            d=" ".join(parts),
                            fill=colors_by_layer.get(layer, "#000000"),
                            stroke=colors_by_layer.get(layer, "#000000"),
                            stroke_width=max(0.05, pixel_to_mm),
                            **{"fill-rule": "evenodd"}
                        )
                    )
                    groups[layer].add(object_group)
        else:
            for layer, parts in layer_paths.items():
                groups[layer].add(
                    dwg.path(
                        d=" ".join(parts),
                        fill=layer_colors.get(layer, "#000000"),
                        stroke=layer_colors.get(layer, "#000000"),
                        stroke_width=max(0.05, pixel_to_mm),
                        **{"fill-rule": "evenodd"}
                    )
                )

        dwg.save()
        return

    if group_connected_paths:
        for group_index, group_contours in enumerate(group_connected_contours(contours)):
            layer_names = sorted({color_layer_for_rule(item.rule, force_color_layers=force_color_layers) for item in group_contours})
            layer = layer_names[0] if len(layer_names) == 1 else "CONNECTED_OBJECTS"
            if layer not in groups:
                groups[layer] = dwg.g(id=layer)
                dwg.add(groups[layer])
            object_group = dwg.g(id=f"{layer}_object_{group_index + 1}")
            for item in group_contours:
                scaled = [(x * pixel_to_mm, y * pixel_to_mm) for x, y in item.points]
                if not scaled:
                    continue
                path_data = build_bezier_path(scaled, item.closed) if use_bezier else build_polyline_path(scaled, item.closed)
                object_group.add(
                    dwg.path(
                        d=path_data,
                        fill="none",
                        stroke=rgb_to_hex(item.rule.rgb),
                        stroke_width=max(0.05, pixel_to_mm)
                    )
                )
            groups[layer].add(object_group)
        dwg.save()
        return

    for item in contours:
        if not item.rule.export:
            continue

        layer = color_layer_for_rule(item.rule, force_color_layers=force_color_layers)
        if layer not in groups:
            groups[layer] = dwg.g(id=layer)
            dwg.add(groups[layer])

        scaled = [(x * pixel_to_mm, y * pixel_to_mm) for x, y in item.points]
        if not scaled:
            continue

        if use_bezier:
            path_data = build_bezier_path(scaled, item.closed)
        else:
            path_data = build_polyline_path(scaled, item.closed)

        groups[layer].add(
            dwg.path(
                d=path_data,
                fill="none",
                stroke=rgb_to_hex(item.rule.rgb),
                stroke_width=max(0.05, pixel_to_mm)
            )
        )

    dwg.save()


def export_dxf(
    output_path: str,
    image_size: Tuple[int, int],
    contours: List[DetectedContour],
    pixel_to_mm: float,
    invert_y: bool = True,
    dxf_version: str = "R2000",
    dedupe_segments: bool = True,
    dedupe_tolerance_px: float = 1.25,
    force_color_layers: bool = True,
    object_layers: bool = False
) -> None:
    width_px, height_px = image_size
    # Viele Grafikprogramme öffnen neuere DXF-Versionen nicht zuverlässig.
    # R2000 ist ein guter Kompatibilitätsmodus für Illustrator/CorelDraw,
    # R2007 ist ebenfalls bis zur offiziellen Illustrator-Grenze.
    allowed_versions = {"R2000", "R2004", "R2007", "R2010", "R2013", "R2018"}
    if dxf_version not in allowed_versions:
        dxf_version = "R2000"
    doc = ezdxf.new(dxf_version)
    msp = doc.modelspace()

    existing_layers = set()

    if dedupe_segments:
        unique_segments = unique_line_segments_from_contours(
            contours,
            tolerance_px=dedupe_tolerance_px,
            exported_only=True
        )

        for rule, a_px, b_px in unique_segments:
            layer = dxf_layer_for_rule(rule, force_color_layers=force_color_layers)
            if layer not in existing_layers:
                if layer not in doc.layers:
                    doc.layers.new(name=layer)
                existing_layers.add(layer)

            def convert(point: Tuple[float, float]) -> Tuple[float, float]:
                x_px, y_px = point
                x = x_px * pixel_to_mm
                if invert_y:
                    y = (height_px - y_px) * pixel_to_mm
                else:
                    y = y_px * pixel_to_mm
                return (x, y)

            msp.add_line(
                convert(a_px),
                convert(b_px),
                dxfattribs={"layer": layer}
            )

        doc.saveas(output_path)
        return

    object_index = 0
    for item in contours:
        if not item.rule.export:
            continue

        layer = dxf_layer_for_rule(item.rule, force_color_layers=force_color_layers)
        if object_layers:
            object_index += 1
            layer = sanitize_dxf_layer_name(f"{layer}_OBJ_{object_index:04d}")
        if layer not in existing_layers:
            if layer not in doc.layers:
                doc.layers.new(name=layer)
            existing_layers.add(layer)

        points = []
        for x_px, y_px in item.points:
            x = x_px * pixel_to_mm
            if invert_y:
                y = (height_px - y_px) * pixel_to_mm
            else:
                y = y_px * pixel_to_mm
            points.append((x, y))

        if len(points) >= 3:
            msp.add_lwpolyline(
                points,
                close=item.closed,
                dxfattribs={"layer": layer}
            )
        elif len(points) == 2:
            msp.add_line(
                points[0],
                points[1],
                dxfattribs={"layer": layer}
            )

    doc.saveas(output_path)


# -----------------------------------------------------------------------------
# STL-Export: geschlossene Flächen als einfache Extrusion
# -----------------------------------------------------------------------------

def _stl_clean_loop(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    cleaned: List[Tuple[float, float]] = []
    for x, y in points:
        point = (float(x), float(y))
        if not cleaned or point_distance(cleaned[-1], point) > 1e-6:
            cleaned.append(point)
    if len(cleaned) > 1 and point_distance(cleaned[0], cleaned[-1]) <= 1e-6:
        cleaned.pop()
    return cleaned


def _stl_signed_area(points: List[Tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return area / 2.0


def _stl_as_ccw(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = _stl_clean_loop(points)
    return pts if _stl_signed_area(pts) >= 0 else list(reversed(pts))


def _stl_as_cw(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = _stl_clean_loop(points)
    return pts if _stl_signed_area(pts) <= 0 else list(reversed(pts))


def _stl_point_in_triangle(
    point: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    cx, cy = c
    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay
    dot00 = v0x * v0x + v0y * v0y
    dot01 = v0x * v1x + v0y * v1y
    dot02 = v0x * v2x + v0y * v2y
    dot11 = v1x * v1x + v1y * v1y
    dot12 = v1x * v2x + v1y * v2y
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) <= 1e-12:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return u >= -1e-9 and v >= -1e-9 and (u + v) <= 1.0 + 1e-9


def _stl_triangulate_simple_polygon(points: List[Tuple[float, float]]) -> List[Tuple[int, int, int]]:
    pts = _stl_as_ccw(points)
    count = len(pts)
    if count < 3:
        return []
    if count == 3:
        return [(0, 1, 2)]

    remaining = list(range(count))
    triangles: List[Tuple[int, int, int]] = []
    guard = 0
    while len(remaining) > 3 and guard < count * count:
        guard += 1
        ear_found = False
        for pos, current in enumerate(remaining):
            prev_index = remaining[(pos - 1) % len(remaining)]
            next_index = remaining[(pos + 1) % len(remaining)]
            a = pts[prev_index]
            b = pts[current]
            c = pts[next_index]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross <= 1e-12:
                continue
            contains_other = False
            for test_index in remaining:
                if test_index in (prev_index, current, next_index):
                    continue
                if _stl_point_in_triangle(pts[test_index], a, b, c):
                    contains_other = True
                    break
            if contains_other:
                continue
            triangles.append((prev_index, current, next_index))
            del remaining[pos]
            ear_found = True
            break
        if not ear_found:
            break

    if len(remaining) == 3:
        triangles.append((remaining[0], remaining[1], remaining[2]))

    if not triangles:
        # Fallback für Sonderfälle: Dreiecks-Fächer ab Punkt 0.
        triangles = [(0, index, index + 1) for index in range(1, count - 1)]
    return triangles


def _stl_normal(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
    c: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def _stl_write_facet(
    handle: Any,
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
    c: Tuple[float, float, float],
) -> None:
    nx, ny, nz = _stl_normal(a, b, c)
    handle.write(f"  facet normal {nx:.8g} {ny:.8g} {nz:.8g}\n")
    handle.write("    outer loop\n")
    for x, y, z in (a, b, c):
        handle.write(f"      vertex {x:.8g} {y:.8g} {z:.8g}\n")
    handle.write("    endloop\n")
    handle.write("  endfacet\n")


def _stl_loop_side_facets(
    handle: Any,
    loop: List[Tuple[float, float]],
    extrusion_mm: float,
) -> int:
    facets = 0
    if len(loop) < 3:
        return facets
    for index, a2 in enumerate(loop):
        b2 = loop[(index + 1) % len(loop)]
        a0 = (a2[0], a2[1], 0.0)
        b0 = (b2[0], b2[1], 0.0)
        b1 = (b2[0], b2[1], extrusion_mm)
        a1 = (a2[0], a2[1], extrusion_mm)
        _stl_write_facet(handle, a0, b0, b1)
        _stl_write_facet(handle, a0, b1, a1)
        facets += 2
    return facets


def _stl_triangles_from_shapely(
    shell: List[Tuple[float, float]],
    holes: List[List[Tuple[float, float]]],
) -> Optional[List[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]]]:
    try:
        from shapely.geometry import Polygon
        from shapely.ops import triangulate
    except Exception:
        return None

    try:
        polygon = Polygon(shell, holes if holes else None)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            return []
        polygons = [polygon]
        if getattr(polygon, "geom_type", "") == "MultiPolygon":
            polygons = list(polygon.geoms)
        result: List[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = []
        for poly in polygons:
            for tri in triangulate(poly):
                probe = tri.representative_point()
                if not poly.contains(probe) and not poly.touches(probe):
                    continue
                coords = list(tri.exterior.coords)[:3]
                if len(coords) != 3:
                    continue
                tri_pts = [(float(x), float(y)) for x, y in coords]
                tri_pts = _stl_as_ccw(tri_pts)
                if len(tri_pts) == 3:
                    result.append((tri_pts[0], tri_pts[1], tri_pts[2]))
        return result
    except Exception:
        return None


def _stl_contour_centroid(contour: DetectedContour) -> Tuple[float, float]:
    pts = [(float(x), float(y)) for x, y in contour.points]
    if not pts:
        return (0.0, 0.0)
    return (sum(x for x, _y in pts) / len(pts), sum(y for _x, y in pts) / len(pts))


def _stl_point_inside_contour(contour: DetectedContour, point: Tuple[float, float]) -> bool:
    pts = [(float(x), float(y)) for x, y in contour.points]
    if len(pts) < 3:
        return False
    try:
        poly = np.array(pts, dtype=np.float32).reshape(-1, 1, 2)
        return bool(cv2.pointPolygonTest(poly, (float(point[0]), float(point[1])), False) >= 0)
    except Exception:
        return False



def _stl_write_mask_grid_fallback(
    handle: Any,
    image_size: Tuple[int, int],
    solid: DetectedContour,
    hole_contours: List[DetectedContour],
    pixel_to_mm: float,
    extrusion_mm: float,
    invert_y: bool = True,
) -> int:
    """Robuster STL-Fallback ohne Shapely: extrudiert eine Rastermaske mit echten Löchern.

    Dieser Weg wird nur verwendet, wenn Innenlöcher vorhanden sind und keine
    Polygon-Triangulation mit Shapely verfügbar ist. Die Geometrie bleibt dadurch
    in der Draufsicht korrekt ausgespart, auch wenn die STL an den Rändern etwas
    pixeliger sein kann.
    """
    width_px, height_px = image_size
    width_px = max(1, int(round(width_px)))
    height_px = max(1, int(round(height_px)))
    scale = max(1e-9, float(pixel_to_mm))
    height = max(0.001, float(extrusion_mm))

    mask = np.zeros((height_px, width_px), dtype=np.uint8)

    def _pts_to_cv(points: List[Tuple[float, float]]) -> Optional[np.ndarray]:
        if len(points) < 3:
            return None
        pts = []
        for x, y in points:
            xi = int(round(float(x)))
            yi = int(round(float(y)))
            xi = max(0, min(width_px - 1, xi))
            yi = max(0, min(height_px - 1, yi))
            pts.append([xi, yi])
        if len(pts) < 3:
            return None
        return np.array(pts, dtype=np.int32)

    solid_pts = _pts_to_cv([(float(x), float(y)) for x, y in solid.points])
    if solid_pts is None:
        return 0
    cv2.fillPoly(mask, [solid_pts], 255)
    for hole in hole_contours:
        hole_pts = _pts_to_cv([(float(x), float(y)) for x, y in hole.points])
        if hole_pts is not None:
            cv2.fillPoly(mask, [hole_pts], 0)

    filled = mask > 0
    if not bool(np.any(filled)):
        return 0

    def pxy(x: float, y: float, z: float) -> Tuple[float, float, float]:
        yy = (float(height_px) - float(y)) if invert_y else float(y)
        return (float(x) * scale, yy * scale, float(z))

    def write_quad(a, b, c, d, flip: bool = False) -> int:
        if flip:
            _stl_write_facet(handle, a, c, b)
            _stl_write_facet(handle, a, d, c)
        else:
            _stl_write_facet(handle, a, b, c)
            _stl_write_facet(handle, a, c, d)
        return 2

    facets = 0

    # Top-/Bottom-Flächen als horizontale Runs zusammenfassen.
    for y in range(height_px):
        x = 0
        while x < width_px:
            if not filled[y, x]:
                x += 1
                continue
            x0 = x
            while x < width_px and filled[y, x]:
                x += 1
            x1 = x
            # Pixelzelle: [x0, x1] x [y, y+1]
            a_top = pxy(x0, y, height)
            b_top = pxy(x1, y, height)
            c_top = pxy(x1, y + 1, height)
            d_top = pxy(x0, y + 1, height)
            facets += write_quad(a_top, b_top, c_top, d_top, flip=False)
            a_bot = pxy(x0, y, 0.0)
            b_bot = pxy(x1, y, 0.0)
            c_bot = pxy(x1, y + 1, 0.0)
            d_bot = pxy(x0, y + 1, 0.0)
            facets += write_quad(a_bot, b_bot, c_bot, d_bot, flip=True)

    # Seitenwände an allen Maskenkanten. Segmente werden pro Kante zusammengefasst.
    # Vertikale Kanten x = konstant.
    for x in range(width_px + 1):
        y = 0
        while y < height_px:
            left = filled[y, x - 1] if x > 0 else False
            right = filled[y, x] if x < width_px else False
            if left == right:
                y += 1
                continue
            y0 = y
            while y < height_px:
                left2 = filled[y, x - 1] if x > 0 else False
                right2 = filled[y, x] if x < width_px else False
                if left2 == right2:
                    break
                y += 1
            y1 = y
            a = pxy(x, y0, 0.0)
            b = pxy(x, y1, 0.0)
            c = pxy(x, y1, height)
            d = pxy(x, y0, height)
            facets += write_quad(a, b, c, d, flip=bool(right and not left))

    # Horizontale Kanten y = konstant.
    for y in range(height_px + 1):
        x = 0
        while x < width_px:
            top = filled[y - 1, x] if y > 0 else False
            bottom = filled[y, x] if y < height_px else False
            if top == bottom:
                x += 1
                continue
            x0 = x
            while x < width_px:
                top2 = filled[y - 1, x] if y > 0 else False
                bottom2 = filled[y, x] if y < height_px else False
                if top2 == bottom2:
                    break
                x += 1
            x1 = x
            a = pxy(x0, y, 0.0)
            b = pxy(x1, y, 0.0)
            c = pxy(x1, y, height)
            d = pxy(x0, y, height)
            facets += write_quad(a, b, c, d, flip=bool(top and not bottom))

    return facets


def export_stl_extruded(
    output_path: str,
    image_size: Tuple[int, int],
    contours: List[DetectedContour],
    pixel_to_mm: float,
    extrusion_mm: float,
    selected_indices: Optional[set[int]] = None,
    invert_y: bool = True,
) -> int:
    """Exportiert ausgewählte geschlossene Konturen als einfache extrudierte ASCII-STL.

    Die STL-Datei verwendet Millimeter als Modellmaß. Geschlossene Nicht-Loch-Konturen
    werden als Volumenkörper extrudiert. Aktiv ausgewählte Innenloch-Konturen innerhalb einer ausgewählten
    Außenkontur werden, falls Shapely verfügbar ist, in der Deckfläche berücksichtigt;
    Seitenwände der Löcher werden immer geschrieben.
    """
    _width_px, height_px = image_size
    scale = max(1e-9, float(pixel_to_mm))
    height = max(0.001, float(extrusion_mm))
    selected = set(selected_indices) if selected_indices is not None else set(range(len(contours)))

    def convert_loop(points: List[Tuple[float, float]], clockwise: bool = False) -> List[Tuple[float, float]]:
        converted: List[Tuple[float, float]] = []
        for x_px, y_px in points:
            x_mm = float(x_px) * scale
            y_source = (float(height_px) - float(y_px)) if invert_y else float(y_px)
            y_mm = y_source * scale
            converted.append((x_mm, y_mm))
        return _stl_as_cw(converted) if clockwise else _stl_as_ccw(converted)

    solids: List[tuple[int, DetectedContour]] = []
    holes = [
        item for index, item in enumerate(contours)
        if index in selected
        and getattr(item.rule, "export", True)
        and bool(getattr(item, "closed", False))
        and bool(getattr(item, "is_hole", False))
        and len(getattr(item, "points", []) or []) >= 3
    ]

    for index, item in enumerate(contours):
        if index not in selected:
            continue
        if not getattr(item.rule, "export", True):
            continue
        if not bool(getattr(item, "closed", False)) or bool(getattr(item, "is_hole", False)):
            continue
        if len(getattr(item, "points", []) or []) < 3:
            continue
        solids.append((index, item))

    if not solids:
        raise ValueError("Keine geschlossene Fläche für STL ausgewählt.")

    facet_count = 0
    with open(output_path, "w", encoding="ascii", newline="\n") as handle:
        handle.write("solid vektorrazor_extrusion\n")
        for _index, solid in solids:
            shell = convert_loop(solid.points, clockwise=False)
            if len(shell) < 3 or abs(_stl_signed_area(shell)) <= 1e-9:
                continue

            matching_holes: List[List[Tuple[float, float]]] = []
            matching_hole_contours: List[DetectedContour] = []
            for hole in holes:
                centroid = _stl_contour_centroid(hole)
                if _stl_point_inside_contour(solid, centroid):
                    hole_loop = convert_loop(hole.points, clockwise=True)
                    if len(hole_loop) >= 3 and abs(_stl_signed_area(hole_loop)) > 1e-9:
                        matching_holes.append(hole_loop)
                        matching_hole_contours.append(hole)

            shapely_triangles = _stl_triangles_from_shapely(shell, matching_holes)
            if shapely_triangles is not None:
                for a2, b2, c2 in shapely_triangles:
                    top = (a2[0], a2[1], height), (b2[0], b2[1], height), (c2[0], c2[1], height)
                    bottom = (c2[0], c2[1], 0.0), (b2[0], b2[1], 0.0), (a2[0], a2[1], 0.0)
                    _stl_write_facet(handle, *top)
                    _stl_write_facet(handle, *bottom)
                    facet_count += 2
                facet_count += _stl_loop_side_facets(handle, shell, height)
                for hole_loop in matching_holes:
                    facet_count += _stl_loop_side_facets(handle, hole_loop, height)
            elif matching_hole_contours:
                # Ohne Shapely wurde früher nur die Außenfläche trianguliert; dadurch war
                # das Loch in der STL-Oberfläche sichtbar umrandet, aber nicht ausgespart.
                # Dieser Raster-Fallback erzeugt die Deck-/Bodenfläche aus einer echten
                # Maske und lässt gewählte Innenlöcher zuverlässig offen.
                facet_count += _stl_write_mask_grid_fallback(
                    handle,
                    image_size,
                    solid,
                    matching_hole_contours,
                    scale,
                    height,
                    invert_y=invert_y,
                )
            else:
                # Fallback ohne optionale Geometrie-Bibliothek und ohne Löcher: Außenkontur triangulieren.
                triangles = _stl_triangulate_simple_polygon(shell)
                for ia, ib, ic in triangles:
                    a2, b2, c2 = shell[ia], shell[ib], shell[ic]
                    _stl_write_facet(handle, (a2[0], a2[1], height), (b2[0], b2[1], height), (c2[0], c2[1], height))
                    _stl_write_facet(handle, (c2[0], c2[1], 0.0), (b2[0], b2[1], 0.0), (a2[0], a2[1], 0.0))
                    facet_count += 2
                facet_count += _stl_loop_side_facets(handle, shell, height)

        handle.write("endsolid vektorrazor_extrusion\n")

    if facet_count <= 0:
        raise ValueError("STL konnte nicht erzeugt werden: keine gültigen Flächen.")
    return facet_count


class ColorRow:
    def __init__(
        self,
        parent: ttk.Frame,
        row_index: int,
        name: str,
        rgb: str,
        tolerance: str,
        layer: str,
        export: bool,
        min_area: str,
        epsilon: str,
        remove_callback
    ) -> None:
        self.frame = parent
        self.row_index = row_index
        self.remove_callback = remove_callback

        self.name_var = tk.StringVar(value=name)
        self.rgb_var = tk.StringVar(value=rgb)
        self.tolerance_var = tk.StringVar(value=tolerance)
        self.layer_var = tk.StringVar(value=layer)
        self.export_var = tk.BooleanVar(value=export)
        self.min_area_var = tk.StringVar(value=min_area)
        self.epsilon_var = tk.StringVar(value=epsilon)

        self.widgets = []
        self._syncing_tolerance = False

        self._add_entry(self.name_var, 14)
        self._add_entry(self.rgb_var, 13)
        self._add_tolerance_control()
        self._add_entry(self.layer_var, 14)

        check = ttk.Checkbutton(parent, variable=self.export_var)
        check.grid(row=row_index, column=4, padx=2, pady=2)
        self.widgets.append(check)

        self._add_entry(self.min_area_var, 8)
        self._add_entry(self.epsilon_var, 8)

        btn = ttk.Button(parent, text="X", width=3, command=self.remove)
        btn.grid(row=row_index, column=7, padx=2, pady=2)
        self.widgets.append(btn)

    def _add_entry(self, variable: tk.StringVar, width: int) -> None:
        col = len(self.widgets)
        entry = ttk.Entry(self.frame, textvariable=variable, width=width)
        entry.grid(row=self.row_index, column=col, padx=2, pady=2, sticky="ew")
        self.widgets.append(entry)

    @staticmethod
    def _clamp_tolerance(value: float) -> float:
        return max(0.0, min(255.0, float(value)))

    def _on_tolerance_scale_changed(self, value: str) -> None:
        if self._syncing_tolerance:
            return
        try:
            number = self._clamp_tolerance(float(str(value).replace(",", ".")))
        except Exception:
            return
        self._syncing_tolerance = True
        try:
            self.tolerance_var.set(str(int(round(number))))
        finally:
            self._syncing_tolerance = False

    def _on_tolerance_text_changed(self, *_args: object) -> None:
        if self._syncing_tolerance:
            return
        try:
            number = self._clamp_tolerance(float(str(self.tolerance_var.get()).replace(",", ".")))
        except Exception:
            return
        self._syncing_tolerance = True
        try:
            self.tolerance_scale_var.set(number)
        finally:
            self._syncing_tolerance = False

    def _add_tolerance_control(self) -> None:
        col = len(self.widgets)
        cell = ttk.Frame(self.frame)
        cell.grid(row=self.row_index, column=col, padx=2, pady=2, sticky="ew")
        cell.columnconfigure(0, weight=1)

        try:
            initial = self._clamp_tolerance(float(str(self.tolerance_var.get()).replace(",", ".")))
        except Exception:
            initial = 12.0
            self.tolerance_var.set("12")
        self.tolerance_scale_var = tk.DoubleVar(value=initial)

        scale = ttk.Scale(
            cell,
            from_=0,
            to=255,
            variable=self.tolerance_scale_var,
            orient="horizontal",
            command=self._on_tolerance_scale_changed,
        )
        scale.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        spin = ttk.Spinbox(cell, from_=0, to=255, increment=1, textvariable=self.tolerance_var, width=6)
        spin.grid(row=0, column=1, sticky="e")

        self.tolerance_var.trace_add("write", self._on_tolerance_text_changed)
        self.widgets.append(cell)

    def remove(self) -> None:
        self.remove_callback(self)

    def destroy(self) -> None:
        for widget in self.widgets:
            widget.destroy()

    def to_rule(self) -> ColorRule:
        return ColorRule(
            name=self.name_var.get().strip() or "Farbe",
            rgb=parse_rgb(self.rgb_var.get()),
            tolerance=float(self.tolerance_var.get().replace(",", ".")),
            layer=self.layer_var.get().strip() or self.name_var.get().strip() or "LAYER",
            export=bool(self.export_var.get()),
            min_area=int(float(self.min_area_var.get().replace(",", "."))),
            epsilon=float(self.epsilon_var.get().replace(",", "."))
        )


class VektorGenApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Vektor Gen - PNG zu CAD-Konturen")
        self.geometry("1180x760")
        self.minsize(980, 620)

        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.pixel_to_mm_var = tk.StringVar(value="1.0")
        self.status_var = tk.StringVar(value="Bereit")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.profile_var = tk.StringVar(value="Standard")
        self.vector_mode_var = tk.StringVar(value="Flächenkontur")
        self.centerline_merge_px_var = tk.StringVar(value="0")
        self.closed_paths_only_var = tk.BooleanVar(value=True)
        self.fill_closed_shapes_var = tk.BooleanVar(value=True)
        self.use_bezier_var = tk.BooleanVar(value=False)
        self.remove_loose_points_var = tk.BooleanVar(value=False)
        self.smooth_contours_var = tk.BooleanVar(value=True)
        self.smooth_strength_var = tk.StringVar(value="2")
        self.cleanup_mode_var = tk.StringVar(value="% Bildfläche")
        self.min_object_area_mm2_var = tk.StringVar(value="0")
        self.min_object_percent_var = tk.StringVar(value="0,01")

        self.color_rows: List[ColorRow] = []
        self.image_rgb: np.ndarray | None = None
        self.last_rules: List[ColorRule] = []
        self.detected_contours: List[DetectedContour] = []
        self.original_photo = None
        self.vector_photo = None
        self.original_preview_image: Image.Image | None = None
        self.vector_preview_image: Image.Image | None = None
        self.original_preview_zoom = 1.0
        self.vector_preview_zoom = 1.0
        self.original_preview_offset = (0, 0)
        self.vector_preview_offset = (0, 0)
        self.drag_start: Tuple[int, int] | None = None
        self.drag_start_offset: Tuple[int, int] | None = None

        self._build_ui()
        self._add_default_rows()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=8)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Input PNG:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(top, textvariable=self.input_path_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(top, text="Auswählen", command=self.choose_input).grid(row=0, column=2, padx=4)
        self.add_info_button(top, "input", row=0, column=3)

        ttk.Label(top, text="Output:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        ttk.Entry(top, textvariable=self.output_path_var).grid(row=1, column=1, sticky="ew", pady=(4, 0))
        ttk.Button(top, text="Speichern als", command=self.choose_output).grid(row=1, column=2, padx=4, pady=(4, 0))
        self.add_info_button(top, "output", row=1, column=3)

        ttk.Label(top, text="Pixel zu mm:").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        ttk.Entry(top, textvariable=self.pixel_to_mm_var, width=10).grid(row=2, column=1, sticky="w", pady=(4, 0))
        self.add_info_button(top, "pixel_to_mm", row=2, column=2)

        main_panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main_panes.grid(row=1, column=0, columnspan=2, sticky="nsew")

        left = ttk.Frame(self, padding=8)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Farben / Layer", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")

        table_outer = ttk.Frame(left)
        table_outer.grid(row=1, column=0, sticky="nsew", pady=(6, 6))

        self.table = ttk.Frame(table_outer)
        self.table.grid(row=0, column=0, sticky="nsew")

        headers = [
            ("Name", "color_name"),
            ("RGB", "color_rgb"),
            ("Tol.", "color_tolerance"),
            ("Layer", "color_layer"),
            ("Export", "color_export"),
            ("Min.", "color_min_area"),
            ("Epsilon", "color_epsilon"),
            ("", ""),
        ]
        for col, (header, info_key) in enumerate(headers):
            header_frame = ttk.Frame(self.table)
            header_frame.grid(row=0, column=col, padx=2, pady=2, sticky="w")
            ttk.Label(header_frame, text=header).grid(row=0, column=0, sticky="w")
            if info_key:
                self.add_info_button(header_frame, info_key, row=0, column=1, padx=(1, 0))

        controls = ttk.Frame(left)
        controls.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(controls, text="+ Farbe", command=self.add_empty_row).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(controls, text="Erkennen / Vorschau", command=self.detect_and_preview).grid(row=0, column=1, padx=4)
        self.add_info_button(controls, "detect_preview", row=0, column=2)
        ttk.Button(controls, text="Auto-Werte", command=self.auto_optimize_settings).grid(row=0, column=3, padx=4)
        self.add_info_button(controls, "auto_settings", row=0, column=4)
        ttk.Button(controls, text="Export", command=self.export_file).grid(row=0, column=5, padx=4)
        self.add_info_button(controls, "export", row=0, column=6)

        profile_controls = ttk.Frame(left)
        profile_controls.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(profile_controls, text="Profil:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.add_info_button(profile_controls, "profile", row=0, column=1)
        profile_box = ttk.Combobox(
            profile_controls,
            textvariable=self.profile_var,
            values=list(PROFILE_ROWS.keys()),
            state="readonly",
            width=18
        )
        profile_box.grid(row=0, column=2, sticky="w")
        ttk.Button(profile_controls, text="Anwenden", command=self.apply_selected_profile).grid(
            row=0,
            column=3,
            padx=(4, 0)
        )

        mode_controls = ttk.Frame(left)
        mode_controls.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(mode_controls, text="Vektorart:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.add_info_button(mode_controls, "vector_mode", row=0, column=1)
        mode_box = ttk.Combobox(
            mode_controls,
            textvariable=self.vector_mode_var,
            values=["Flächenkontur", "Mittellinie / Gravur"],
            state="readonly",
            width=20
        )
        mode_box.grid(row=0, column=2, sticky="w")
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self.options_changed())
        ttk.Label(mode_controls, text="Linien zusammenführen px:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.add_info_button(mode_controls, "centerline_merge", row=1, column=1)
        merge_entry = ttk.Entry(mode_controls, textvariable=self.centerline_merge_px_var, width=8)
        merge_entry.grid(row=1, column=2, sticky="w", pady=(6, 0))
        merge_entry.bind("<KeyRelease>", lambda _event: self.options_changed())

        options = ttk.Frame(left)
        options.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(
            options,
            text="Nur geschlossene Pfade",
            variable=self.closed_paths_only_var,
            command=self.options_changed
        ).grid(row=0, column=0, sticky="w")
        self.add_info_button(options, "closed_paths", row=0, column=1)
        ttk.Checkbutton(
            options,
            text="Geschlossene Flächen füllen",
            variable=self.fill_closed_shapes_var,
            command=self.options_changed
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.add_info_button(options, "fill_closed_shapes", row=1, column=1)
        ttk.Checkbutton(
            options,
            text="Bezier für SVG",
            variable=self.use_bezier_var,
            command=self.options_changed
        ).grid(row=3, column=0, sticky="w", pady=(2, 0))
        self.add_info_button(options, "bezier_curves", row=2, column=1)
        ttk.Checkbutton(
            options,
            text="Lose Ankerpunkte suchen und entfernen",
            variable=self.remove_loose_points_var,
            command=self.options_changed
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))
        self.add_info_button(options, "loose_points", row=3, column=1)
        ttk.Checkbutton(
            options,
            text="Rundungen glätten",
            variable=self.smooth_contours_var,
            command=self.options_changed
        ).grid(row=4, column=0, sticky="w", pady=(2, 0))
        self.add_info_button(options, "smooth_contours", row=4, column=1)
        ttk.Label(options, text="Glättung:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.add_info_button(options, "smooth_strength", row=5, column=1)
        smooth_entry = ttk.Entry(options, textvariable=self.smooth_strength_var, width=8)
        smooth_entry.grid(row=5, column=2, sticky="w", padx=(4, 0), pady=(6, 0))
        smooth_entry.bind("<KeyRelease>", lambda _event: self.options_changed())
        ttk.Label(options, text="Kleine Objekte löschen:").grid(
            row=5,
            column=0,
            sticky="w",
            pady=(6, 0)
        )
        self.add_info_button(options, "min_object_size", row=5, column=1)
        cleanup_box = ttk.Combobox(
            options,
            textvariable=self.cleanup_mode_var,
            values=["Aus", "mm²", "% Bildfläche"],
            state="readonly",
            width=12
        )
        cleanup_box.grid(row=6, column=2, sticky="w", padx=(4, 0), pady=(6, 0))
        cleanup_box.bind("<<ComboboxSelected>>", lambda _event: self.options_changed())
        ttk.Label(options, text="mm²:").grid(row=7, column=0, sticky="w", pady=(4, 0))
        min_size_entry = ttk.Entry(options, textvariable=self.min_object_area_mm2_var, width=8)
        min_size_entry.grid(
            row=6,
            column=2,
            sticky="w",
            padx=(4, 0),
            pady=(4, 0)
        )
        min_size_entry.bind("<KeyRelease>", lambda _event: self.options_changed())
        ttk.Label(options, text="% Bildfläche:").grid(row=8, column=0, sticky="w", pady=(4, 0))
        min_percent_entry = ttk.Entry(options, textvariable=self.min_object_percent_var, width=8)
        min_percent_entry.grid(row=8, column=2, sticky="w", padx=(4, 0), pady=(4, 0))
        min_percent_entry.bind("<KeyRelease>", lambda _event: self.options_changed())

        help_text = (
            "RGB z. B. 0,0,0\\n"
            "Tol. = Farbtoleranz\\n"
            "Min. = kleine Störungen entfernen\\n"
            "Epsilon = Punktreduktion\\n"
            "Cleanup akzeptiert Komma\\n"
            "Mausrad = Vorschau zoomen"
        )
        ttk.Label(left, text=help_text, foreground="#555").grid(row=6, column=0, sticky="w", pady=(10, 0))

        right = ttk.Frame(self, padding=8)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Vorschau", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.add_info_button(right, "preview", row=0, column=1)

        preview_area = ttk.Panedwindow(right, orient=tk.HORIZONTAL)
        preview_area.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))

        original_pane = ttk.Frame(preview_area)
        original_pane.rowconfigure(1, weight=1)
        original_pane.columnconfigure(0, weight=1)
        vector_pane = ttk.Frame(preview_area)
        vector_pane.rowconfigure(1, weight=1)
        vector_pane.columnconfigure(0, weight=1)

        ttk.Label(original_pane, text="Original PNG").grid(row=0, column=0, sticky="w")
        ttk.Label(vector_pane, text="Vektorlinien").grid(row=0, column=0, sticky="w")

        self.original_canvas = tk.Canvas(original_pane, bg="#f5f5f5", highlightthickness=1, highlightbackground="#cccccc")
        self.original_canvas.grid(row=1, column=0, sticky="nsew")
        self.vector_canvas = tk.Canvas(vector_pane, bg="#f5f5f5", highlightthickness=1, highlightbackground="#cccccc")
        self.vector_canvas.grid(row=1, column=0, sticky="nsew")

        preview_area.add(original_pane, weight=1)
        preview_area.add(vector_pane, weight=1)

        for canvas in (self.original_canvas, self.vector_canvas):
            canvas.bind("<MouseWheel>", self.on_preview_zoom)
            canvas.bind("<Button-4>", self.on_preview_zoom)
            canvas.bind("<Button-5>", self.on_preview_zoom)
            canvas.bind("<ButtonPress-1>", self.on_preview_drag_start)
            canvas.bind("<B1-Motion>", self.on_preview_drag)
            canvas.bind("<ButtonRelease-1>", self.on_preview_drag_end)
        self.original_canvas.bind("<Configure>", lambda _event: self._render_preview_image(self.original_canvas, "original"))
        self.vector_canvas.bind("<Configure>", lambda _event: self._render_preview_image(self.vector_canvas, "vector"))

        main_panes.add(left, weight=0)
        main_panes.add(right, weight=1)

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Progressbar(
            bottom,
            variable=self.progress_var,
            maximum=100,
            mode="determinate"
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

    def add_info_button(self, parent: tk.Widget, info_key: str, row: int, column: int, **grid_options: Any) -> None:
        options = {"padx": (2, 0), "pady": 0, "sticky": "w"}
        options.update(grid_options)
        ttk.Button(
            parent,
            text="?",
            width=2,
            command=lambda: self.show_info(info_key)
        ).grid(row=row, column=column, **options)

    def show_info(self, info_key: str) -> None:
        message = INFO_TEXTS.get(info_key, "Keine Beschreibung vorhanden.")
        messagebox.showinfo("Info", message)

    def set_progress(self, value: float, status: str | None = None) -> None:
        self.progress_var.set(max(0.0, min(100.0, value)))
        if status is not None:
            self.status_var.set(status)
        self.update_idletasks()

    def _add_default_rows(self) -> None:
        for row_data in PROFILE_ROWS["Standard"]:
            self.add_row(*row_data)

    def options_changed(self) -> None:
        self.detected_contours = []
        self.status_var.set("Option geändert. Bitte Erkennung neu starten.")

    def clear_color_rows(self) -> None:
        for row in self.color_rows:
            row.destroy()
        self.color_rows.clear()

    def load_profile(self, profile_name: str) -> None:
        rows = PROFILE_ROWS.get(profile_name)
        if rows is None:
            raise ValueError(f"Unbekanntes Profil: {profile_name}")

        self.clear_color_rows()
        for row_data in rows:
            self.add_row(*row_data)

        self.options_changed()

    def apply_selected_profile(self) -> None:
        try:
            profile_name = self.profile_var.get()
            self.load_profile(profile_name)
            self.status_var.set(f"Profil geladen: {profile_name}")
        except Exception as exc:
            messagebox.showerror("Fehler beim Profil", str(exc))

    def add_row(
        self,
        name: str,
        rgb: str,
        tolerance: str,
        layer: str,
        export: bool,
        min_area: str,
        epsilon: str
    ) -> None:
        row_index = len(self.color_rows) + 1
        row = ColorRow(
            self.table,
            row_index,
            name,
            rgb,
            tolerance,
            layer,
            export,
            min_area,
            epsilon,
            remove_callback=self.remove_row
        )
        self.color_rows.append(row)

    def add_empty_row(self) -> None:
        self.add_row("Neue Farbe", "255,0,0", "10", "CUT_LAYER", True, "20", "1.5")

    def remove_row(self, row: ColorRow) -> None:
        row.destroy()
        self.color_rows.remove(row)
        self._redraw_color_table()

    def _redraw_color_table(self) -> None:
        saved = []
        for row in self.color_rows:
            saved.append((
                row.name_var.get(),
                row.rgb_var.get(),
                row.tolerance_var.get(),
                row.layer_var.get(),
                row.export_var.get(),
                row.min_area_var.get(),
                row.epsilon_var.get()
            ))
            row.destroy()

        self.color_rows.clear()

        for data in saved:
            self.add_row(*data)

    def choose_input(self) -> None:
        path = filedialog.askopenfilename(
            title="PNG auswählen",
            filetypes=[("PNG-Dateien", "*.png"), ("Alle Dateien", "*.*")]
        )
        if not path:
            return

        self.input_path_var.set(path)

        if not self.output_path_var.get():
            default_out = str(Path(path).with_suffix(".dxf"))
            self.output_path_var.set(default_out)

        self.load_image()

    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Output speichern",
            defaultextension=".dxf",
            filetypes=[
                ("DXF-Datei", "*.dxf"),
                ("SVG-Datei", "*.svg"),
                ("Alle Dateien", "*.*")
            ]
        )
        if path:
            self.output_path_var.set(path)

    def load_image(self) -> None:
        path = self.input_path_var.get().strip()
        if not path:
            return

        try:
            self.image_rgb = load_rgb_image(path)
            h, w = self.image_rgb.shape[:2]
            self.status_var.set(f"Bild geladen: {w} x {h}px")
            self.show_image_only()
        except Exception as exc:
            messagebox.showerror("Fehler beim Laden", str(exc))

    def get_rules(self) -> List[ColorRule]:
        rules: List[ColorRule] = []
        for row in self.color_rows:
            rules.append(row.to_rule())
        return rules

    def has_exported_white_rule(self) -> bool:
        for row in self.color_rows:
            try:
                if row.export_var.get() and parse_rgb(row.rgb_var.get()) == (255, 255, 255):
                    return True
            except Exception:
                continue
        return False

    def get_pixel_to_mm(self) -> float:
        value = float(self.pixel_to_mm_var.get().replace(",", "."))
        if value <= 0:
            raise ValueError("Pixel zu mm muss größer als 0 sein.")
        return value

    def get_min_object_area_mm2(self) -> float:
        text = self.min_object_area_mm2_var.get().strip()
        if not text:
            return 0.0

        value = float(text.replace(",", "."))
        if value < 0:
            raise ValueError("Minimale Objektfläche darf nicht kleiner als 0 sein.")
        return value

    def get_min_object_percent(self) -> float:
        text = self.min_object_percent_var.get().strip()
        if not text:
            return 0.0

        value = float(text.replace(",", "."))
        if value < 0:
            raise ValueError("Minimaler Bildflächen-Prozentwert darf nicht kleiner als 0 sein.")
        return value

    def get_smooth_iterations(self) -> int:
        if not self.smooth_contours_var.get():
            return 0

        text = self.smooth_strength_var.get().strip()
        if not text:
            return 0

        value = int(float(text.replace(",", ".")))
        if value < 0:
            raise ValueError("Glättung darf nicht kleiner als 0 sein.")
        return min(value, 5)

    def get_centerline_merge_px(self) -> float:
        text = self.centerline_merge_px_var.get().strip()
        if not text:
            return 0.0

        value = float(text.replace(",", "."))
        if value < 0:
            raise ValueError("Linien-Zusammenführung darf nicht kleiner als 0 sein.")
        return value

    def detect_and_preview(self) -> None:
        self.set_progress(0, "Erkennung wird vorbereitet...")
        if self.image_rgb is None:
            self.load_image()

        if self.image_rgb is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein PNG auswählen.")
            self.set_progress(0, "Bereit")
            return

        try:
            self.set_progress(5, "Regeln und Optionen werden gelesen...")
            rules = self.get_rules()
            self.last_rules = rules
            pixel_to_mm = self.get_pixel_to_mm()
            min_object_area_mm2 = self.get_min_object_area_mm2()
            min_object_percent = self.get_min_object_percent()
            smooth_iterations = self.get_smooth_iterations()
            centerline_mode = self.vector_mode_var.get() == "Mittellinie / Gravur"
            centerline_merge_px = self.get_centerline_merge_px()
            self.set_progress(10, "Konturen werden erkannt...")
            self.detected_contours = detect_all_contours(
                self.image_rgb,
                rules,
                closed_paths_only=self.closed_paths_only_var.get() and not centerline_mode,
                remove_loose_points=self.remove_loose_points_var.get(),
                smooth_iterations=smooth_iterations,
                centerline_mode=centerline_mode,
                centerline_merge_px=centerline_merge_px,
                progress_callback=lambda fraction: self.set_progress(
                    10 + fraction * 65,
                    "Konturen werden erkannt..."
                )
            )
            self.set_progress(80, "Kleine Objekte werden gefiltert...")
            before_size_filter = len(self.detected_contours)
            self.detected_contours = filter_small_contours(
                self.detected_contours,
                self.cleanup_mode_var.get(),
                min_object_area_mm2,
                min_object_percent,
                (self.image_rgb.shape[1], self.image_rgb.shape[0]),
                pixel_to_mm
            )
            self.set_progress(90, "Vorschau wird gezeichnet...")
            self.show_preview()

            exported = sum(1 for c in self.detected_contours if c.rule.export)
            points = sum(len(c.points) for c in self.detected_contours if c.rule.export)
            removed = before_size_filter - len(self.detected_contours)
            self.set_progress(100)
            warning = " | Hinweis: Weiß wird exportiert" if self.has_exported_white_rule() else ""
            self.status_var.set(
                f"Konturen erkannt: {len(self.detected_contours)} | Export aktiv: {exported} | "
                f"Punkte: {points} | Modus: {self.vector_mode_var.get()} | Cleanup entfernt: {removed}{warning}"
            )
        except Exception as exc:
            self.set_progress(0, "Fehler bei Erkennung")
            messagebox.showerror("Fehler bei Erkennung", str(exc))

    def auto_optimize_settings(self) -> None:
        self.set_progress(0, "Auto-Werte werden vorbereitet...")
        if self.image_rgb is None:
            self.load_image()

        if self.image_rgb is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein PNG auswählen.")
            self.set_progress(0, "Bereit")
            return

        try:
            rules = self.get_rules()
            pixel_to_mm = self.get_pixel_to_mm()
            min_object_area_mm2 = self.get_min_object_area_mm2()
            min_object_percent = self.get_min_object_percent()
            centerline_mode = self.vector_mode_var.get() == "Mittellinie / Gravur"

            if centerline_mode:
                candidates = [
                    {"epsilon": 0.8, "smooth": 0, "merge": 0.0},
                    {"epsilon": 1.2, "smooth": 0, "merge": 1.0},
                    {"epsilon": 1.8, "smooth": 0, "merge": 2.0},
                    {"epsilon": 2.4, "smooth": 0, "merge": 3.0},
                    {"epsilon": 3.0, "smooth": 0, "merge": 4.0},
                ]
            else:
                candidates = [
                    {"epsilon": 0.4, "smooth": 0, "merge": 0.0},
                    {"epsilon": 0.6, "smooth": 1, "merge": 0.0},
                    {"epsilon": 0.8, "smooth": 1, "merge": 0.0},
                    {"epsilon": 1.0, "smooth": 1, "merge": 0.0},
                    {"epsilon": 1.2, "smooth": 2, "merge": 0.0},
                    {"epsilon": 1.6, "smooth": 2, "merge": 0.0},
                ]

            original_epsilons = [row.epsilon_var.get() for row in self.color_rows]
            best_score = -1.0
            best_candidate = candidates[0]
            best_contours: List[DetectedContour] = []

            for index, candidate in enumerate(candidates):
                self.set_progress(
                    index / max(1, len(candidates)) * 90,
                    f"Auto-Werte: Test {index + 1}/{len(candidates)}..."
                )

                for row in self.color_rows:
                    row.epsilon_var.set(str(candidate["epsilon"]).replace(".", ","))
                    if parse_rgb(row.rgb_var.get()) == (255, 255, 255):
                        row.export_var.set(False)
                rules = self.get_rules()

                contours = detect_all_contours(
                    self.image_rgb,
                    rules,
                    closed_paths_only=self.closed_paths_only_var.get() and not centerline_mode,
                    remove_loose_points=self.remove_loose_points_var.get(),
                    smooth_iterations=int(candidate["smooth"]),
                    centerline_mode=centerline_mode,
                    centerline_merge_px=float(candidate["merge"])
                )
                contours = filter_small_contours(
                    contours,
                    self.cleanup_mode_var.get(),
                    min_object_area_mm2,
                    min_object_percent,
                    (self.image_rgb.shape[1], self.image_rgb.shape[0]),
                    pixel_to_mm
                )
                score = score_vector_result(self.image_rgb, rules, contours, centerline_mode)

                if score > best_score:
                    best_score = score
                    best_candidate = candidate
                    best_contours = contours

            for row in self.color_rows:
                row.epsilon_var.set(str(best_candidate["epsilon"]).replace(".", ","))
            self.smooth_contours_var.set(bool(best_candidate["smooth"]))
            self.smooth_strength_var.set(str(best_candidate["smooth"]).replace(".", ","))
            self.centerline_merge_px_var.set(str(best_candidate["merge"]).replace(".", ","))
            self.last_rules = self.get_rules()

            self.detected_contours = best_contours
            self.show_preview()
            self.set_progress(100)
            points = sum(len(contour.points) for contour in self.detected_contours if contour.rule.export)
            self.status_var.set(
                f"Auto-Werte gesetzt | Score: {best_score:.3f} | "
                f"Epsilon: {best_candidate['epsilon']} | Glättung: {best_candidate['smooth']} | "
                f"Zusammenführen: {best_candidate['merge']} px | Punkte: {points}"
            )

        except Exception as exc:
            for row, epsilon in zip(self.color_rows, original_epsilons if 'original_epsilons' in locals() else []):
                row.epsilon_var.set(epsilon)
            self.set_progress(0, "Fehler bei Auto-Werten")
            messagebox.showerror("Fehler bei Auto-Werten", str(exc))

    def show_image_only(self) -> None:
        if self.image_rgb is None:
            return

        image = Image.fromarray(self.image_rgb)
        self._show_pil_on_canvas(self.original_canvas, image, "original")
        self.vector_canvas.delete("all")
        self.vector_preview_image = None

    def show_preview(self) -> None:
        if self.image_rgb is None:
            return

        original = Image.fromarray(self.image_rgb)
        self._show_pil_on_canvas(self.original_canvas, original, "original")
        self.vector_preview_image = Image.new("RGB", original.size, (255, 255, 255))
        self.vector_preview_zoom = 1.0
        self.vector_preview_offset = (0, 0)
        self._render_preview_image(self.vector_canvas, "vector")

    def _show_pil_on_canvas(self, canvas: tk.Canvas, image: Image.Image, preview_kind: str) -> None:
        if preview_kind == "original":
            self.original_preview_image = image
            self.original_preview_zoom = 1.0
            self.original_preview_offset = (0, 0)
        else:
            self.vector_preview_image = image
            self.vector_preview_zoom = 1.0
            self.vector_preview_offset = (0, 0)

        self._render_preview_image(canvas, preview_kind)

    def _render_preview_image(self, canvas: tk.Canvas, preview_kind: str) -> None:
        if preview_kind == "original":
            image = self.original_preview_image
            zoom = self.original_preview_zoom
            offset_x, offset_y = self.original_preview_offset
        else:
            image = self.vector_preview_image
            zoom = self.vector_preview_zoom
            offset_x, offset_y = self.vector_preview_offset

        if image is None:
            return

        canvas.update_idletasks()

        canvas_w = max(100, canvas.winfo_width())
        canvas_h = max(100, canvas.winfo_height())

        img_w, img_h = image.size
        fit_scale = canvas_w / img_w
        scale = fit_scale * zoom

        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        if preview_kind == "vector":
            self._render_vector_lines_on_canvas(canvas, canvas_w, canvas_h, new_w, new_h, scale, offset_x, offset_y)
            return

        shown = image.resize((new_w, new_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(shown)
        self.original_photo = photo

        canvas.delete("all")
        x = (canvas_w - new_w) // 2 + offset_x
        y = (canvas_h - new_h) // 2 + offset_y
        canvas.create_image(x, y, anchor="nw", image=photo)

    def _render_vector_lines_on_canvas(
        self,
        canvas: tk.Canvas,
        canvas_w: int,
        canvas_h: int,
        image_w: int,
        image_h: int,
        scale: float,
        offset_x: int,
        offset_y: int
    ) -> None:
        if self.should_render_filled_mask_preview():
            self._render_filled_mask_preview_on_canvas(
                canvas,
                canvas_w,
                canvas_h,
                image_w,
                image_h,
                offset_x,
                offset_y
            )
            return

        canvas.delete("all")
        x0 = (canvas_w - image_w) // 2 + offset_x
        y0 = (canvas_h - image_h) // 2 + offset_y
        canvas.create_rectangle(x0, y0, x0 + image_w, y0 + image_h, fill="white", outline="#dddddd")
        line_width = max(1, int(round(1.5)))

        for item in self.detected_contours:
            if len(item.points) < 2:
                continue

            draw_points = item.points + [item.points[0]] if item.closed else item.points
            coords: List[float] = []
            for x, y in draw_points:
                coords.extend((x0 + x * scale, y0 + y * scale))

            if self.fill_closed_shapes_var.get() and item.closed and len(item.points) >= 3:
                canvas.create_polygon(
                    *coords,
                    fill=rgb_to_hex(item.rule.rgb),
                    outline=rgb_to_hex(item.rule.rgb)
                )
                continue

            canvas.create_line(
                *coords,
                fill=rgb_to_hex(item.rule.rgb),
                width=line_width,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND
            )

    def should_render_filled_mask_preview(self) -> bool:
        return (
            self.fill_closed_shapes_var.get()
            and self.vector_mode_var.get() == "Flächenkontur"
            and self.image_rgb is not None
        )

    def build_filled_mask_preview_image(self) -> Image.Image:
        if self.image_rgb is None:
            return Image.new("RGB", (1, 1), (255, 255, 255))

        h, w = self.image_rgb.shape[:2]
        preview = Image.new("RGB", (w, h), (255, 255, 255))
        rules = self.last_rules or self.get_rules()

        for rule in rules:
            if not rule.export:
                continue

            mask = make_color_mask(self.image_rgb, rule.rgb, rule.tolerance)
            mask = remove_small_components(mask, rule.min_area)
            color_layer = Image.new("RGB", (w, h), rule.rgb)
            preview.paste(color_layer, mask=Image.fromarray(mask))

        return preview

    def _render_filled_mask_preview_on_canvas(
        self,
        canvas: tk.Canvas,
        canvas_w: int,
        canvas_h: int,
        image_w: int,
        image_h: int,
        offset_x: int,
        offset_y: int
    ) -> None:
        image = self.build_filled_mask_preview_image()
        shown = image.resize((image_w, image_h), Image.LANCZOS)
        self.vector_photo = ImageTk.PhotoImage(shown)

        canvas.delete("all")
        x0 = (canvas_w - image_w) // 2 + offset_x
        y0 = (canvas_h - image_h) // 2 + offset_y
        canvas.create_rectangle(x0, y0, x0 + image_w, y0 + image_h, fill="white", outline="#dddddd")
        canvas.create_image(x0, y0, anchor="nw", image=self.vector_photo)

    def get_preview_kind_for_canvas(self, canvas: tk.Widget) -> str | None:
        if canvas == self.original_canvas:
            return "original"
        if canvas == self.vector_canvas:
            return "vector"
        return None

    def on_preview_drag_start(self, event: tk.Event) -> str:
        preview_kind = self.get_preview_kind_for_canvas(event.widget)
        if preview_kind is None:
            return "break"

        self.drag_start = (int(event.x), int(event.y))
        if preview_kind == "original":
            self.drag_start_offset = self.original_preview_offset
        else:
            self.drag_start_offset = self.vector_preview_offset
        return "break"

    def on_preview_drag(self, event: tk.Event) -> str:
        preview_kind = self.get_preview_kind_for_canvas(event.widget)
        if preview_kind is None or self.drag_start is None or self.drag_start_offset is None:
            return "break"

        dx = int(event.x) - self.drag_start[0]
        dy = int(event.y) - self.drag_start[1]
        new_offset = (self.drag_start_offset[0] + dx, self.drag_start_offset[1] + dy)

        if preview_kind == "original":
            self.original_preview_offset = new_offset
        else:
            self.vector_preview_offset = new_offset

        self._render_preview_image(event.widget, preview_kind)
        return "break"

    def on_preview_drag_end(self, _event: tk.Event) -> str:
        self.drag_start = None
        self.drag_start_offset = None
        return "break"

    def on_preview_zoom(self, event: tk.Event) -> str:
        canvas = event.widget
        preview_kind = self.get_preview_kind_for_canvas(canvas)
        if preview_kind == "original":
            if self.original_preview_image is None:
                return "break"
        elif preview_kind == "vector":
            if self.vector_preview_image is None:
                return "break"
        else:
            return "break"

        delta = getattr(event, "delta", 0)
        button = getattr(event, "num", None)

        if delta > 0 or button == 4:
            if preview_kind == "original":
                self.original_preview_zoom = min(8.0, self.original_preview_zoom * 1.15)
            else:
                self.vector_preview_zoom = min(8.0, self.vector_preview_zoom * 1.15)
        elif delta < 0 or button == 5:
            if preview_kind == "original":
                self.original_preview_zoom = max(0.2, self.original_preview_zoom / 1.15)
            else:
                self.vector_preview_zoom = max(0.2, self.vector_preview_zoom / 1.15)

        self._render_preview_image(canvas, preview_kind)
        return "break"

    def export_file(self) -> None:
        self.set_progress(0, "Export wird vorbereitet...")
        if self.image_rgb is None:
            self.load_image()

        if self.image_rgb is None:
            messagebox.showwarning("Kein Bild", "Bitte zuerst ein PNG auswählen.")
            self.set_progress(0, "Bereit")
            return

        if not self.detected_contours:
            self.detect_and_preview()

        out = self.output_path_var.get().strip()
        if not out:
            self.choose_output()
            out = self.output_path_var.get().strip()

        if not out:
            self.set_progress(0, "Bereit")
            return

        try:
            self.set_progress(25, "Exportdaten werden vorbereitet...")
            pixel_to_mm = self.get_pixel_to_mm()

            h, w = self.image_rgb.shape[:2]
            suffix = Path(out).suffix.lower()

            self.set_progress(60, "Datei wird geschrieben...")
            if suffix == ".svg":
                export_svg(
                    out,
                    (w, h),
                    self.detected_contours,
                    pixel_to_mm,
                    fill_closed_shapes=self.fill_closed_shapes_var.get()
                )
            elif suffix == ".dxf":
                export_dxf(out, (w, h), self.detected_contours, pixel_to_mm, invert_y=True)
            else:
                raise ValueError("Output muss .dxf oder .svg sein.")

            self.set_progress(100)
            self.status_var.set(f"Export fertig: {out}")
            messagebox.showinfo("Export fertig", f"Datei wurde gespeichert:\\n{out}")

        except Exception as exc:
            self.set_progress(0, "Fehler beim Export")
            messagebox.showerror("Fehler beim Export", str(exc))


def main() -> None:
    app = VektorGenApp()
    app.mainloop()


if __name__ == "__main__":
    main()
