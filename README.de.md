<p align="center">
  <img src="assets/vektorrazor_icon.png" width="180" alt="Vektorrazor Icon">
</p>

<h1 align="center">Vektorrazor</h1>

<p align="center">
  <strong>PNG-Logo → KI-Hochskalierung → CAD-orientierte Vektorkonturen</strong>
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

## Kurzbeschreibung

**Vektorrazor** ist ein Desktop-Tool zur Vorbereitung und Vektorisierung von Logos, Scans und einfachen Bildvorlagen.

Das Ziel ist nicht eine möglichst schöne Grafik wie in einem klassischen Vektorprogramm, sondern eine möglichst kontrollierbare, CAD-freundliche Weiterverarbeitung:

```text
Bild vorbereiten → optional KI-hochskalieren → Farben technisch bereinigen → Konturen erkennen → Störungen entfernen → Punkte reduzieren → Layer exportieren
```

Die KI-Hochskalierung ist optional. Sie wird über **Real-ESRGAN ncnn Vulkan** eingebunden und kann kleine oder verpixelte Vorlagen vor der Vektorisierung verbessern.

## Schnellstart mit fertiger Datei

### Windows amd64

1. Auf GitHub unter **Releases** die Windows-Datei herunterladen:

```text
Vektorrazor-Windows-amd64-YYYY-MM-DD.zip
```

2. ZIP-Datei entpacken.
3. `Vektorrazor.exe` starten.
4. Falls Windows SmartScreen warnt: **Weitere Informationen → Trotzdem ausführen**.
5. Im Programm:

```text
Bild laden → optional KI-hochskalieren → Weiter zur Vektorisierung → Vorschau prüfen → DXF / SVG / STL / OBJ exportieren
```

### Ubuntu / Linux amd64

1. Auf GitHub unter **Releases** die Ubuntu/Linux-Datei herunterladen:

```text
Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz
```

2. Archiv entpacken:

```bash
tar -xzf Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz
cd Vektorrazor-Ubuntu-amd64-YYYY-MM-DD
```

3. Programm ausführbar machen und starten:

```bash
chmod +x Vektorrazor
./Vektorrazor
```

Hinweis: Unter Linux muss eine grafische Oberfläche vorhanden sein. Unter WSL funktioniert das mit Windows 11 meist über WSLg. Bei älteren WSL-Setups kann ein X-Server nötig sein.

### macOS

1. Auf GitHub unter **Releases** die macOS-Datei herunterladen:

```text
Vektorrazor-macOS-YYYY-MM-DD.zip
```

2. ZIP-Datei entpacken.
3. Vektorrazor starten.
4. Falls macOS den Start blockiert: Rechtsklick auf die App oder Datei → **Öffnen**.

Bei selbst entpackten oder manuell hinzugefügten Real-ESRGAN-Dateien kann macOS zusätzlich eine Quarantäne-Markierung setzen. Dann kann im Terminal im entpackten Release-Ordner helfen:

```bash
xattr -dr com.apple.quarantine .
```

## Installation

Für normale Benutzer ist keine Python-Installation nötig. Es gibt fertige Release-Dateien:

| System | Datei | Aktion |
|---|---|---|
| Windows amd64 | `Vektorrazor-Windows-amd64-YYYY-MM-DD.zip` | entpacken und `Vektorrazor.exe` starten |
| Ubuntu / Linux amd64 | `Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz` | entpacken, ausführbar machen und starten |
| macOS | `Vektorrazor-macOS-YYYY-MM-DD.zip` | entpacken und starten |

## Real-ESRGAN / Vulkan-Hochskalierung

Vektorrazor kann optional **Real-ESRGAN ncnn Vulkan** verwenden. Das läuft lokal und offline über eine mitgelieferte Kommandozeilen-Datei.

Die Hochskalierung ist vor allem für kleine, pixelige oder leicht unscharfe Vorlagen gedacht. Für CAD zählt am Ende aber weiterhin die bereinigte Kontur, nicht das optisch schönste Bild.

### Benötigte Ordnerstruktur

Empfohlene Struktur im Release-Paket:

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

Die Models liegen bewusst gemeinsam im Ordner `models/`. Die Plattformordner enthalten nur die jeweilige ausführbare Datei.

### Vulkan-Voraussetzung

Real-ESRGAN ncnn Vulkan benötigt eine funktionierende Vulkan-Unterstützung der Grafikkarte bzw. des Systems.

Typische Voraussetzungen:

- aktueller Grafiktreiber
- Vulkan-fähige GPU oder kompatible Vulkan-Laufzeit
- unter macOS die passende Real-ESRGAN-macOS-Version

Wenn kein Vulkan verfügbar ist oder die Real-ESRGAN-Datei fehlt, sollte Vektorrazor trotzdem ohne KI-Hochskalierung nutzbar bleiben.

### Testbefehle

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

Hinweis: Der Modellname ist hier `realesr-animevideov3`. Die Skalierung wird über `-s 2`, `-s 3` oder `-s 4` gewählt. Die Dateien im Model-Ordner heißen deshalb zusätzlich `-x2`, `-x3` oder `-x4`.

## Hinweise für Entwickler

Der Quellcode liegt im Repository. Wer selbst entwickeln oder eigene Builds erstellen möchte, kann Vektorrazor aus Source starten.

### Aus Source starten

```bash
pip install -r requirements.txt
python main.py
```

### Windows-EXE selbst bauen

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py
```

### Ubuntu/Linux-Binary selbst bauen

```bash
pyinstaller --onefile --windowed --clean \
  --name Vektorrazor \
  --add-data "assets/vektorrazor.ico:assets" \
  --add-data "assets/vektorrazor_icon.png:assets" \
  main.py
```

### macOS-Build selbst bauen

```bash
pyinstaller --onefile --windowed --clean \
  --name Vektorrazor \
  --add-data "assets/vektorrazor_icon.png:assets" \
  main.py
```

Wichtig: Die Real-ESRGAN-Dateien und Models sollten im Release-Ordner neben der App liegen, nicht zwingend in die PyInstaller-Onefile-Datei gepackt werden. Das macht Updates, Lizenztexte und Fehlersuche deutlich einfacher.

## Release-Pakete erstellen

Empfohlene Release-Dateien:

```text
release/Vektorrazor-Windows-amd64-YYYY-MM-DD.zip
release/Vektorrazor-Ubuntu-amd64-YYYY-MM-DD.tar.gz
release/Vektorrazor-macOS-YYYY-MM-DD.zip
release/SHA256SUMS-YYYY-MM-DD.txt
```

Der Ordner `vektorrazor_config/real_esrgan/` sollte im jeweiligen Release-Paket enthalten sein, wenn die KI-Hochskalierung direkt mitgeliefert werden soll.

## Sprachen nutzen und ergänzen

Die Anwendung lädt Sprachdateien aus dem Ordner `lang/`.

- Dateinamen: `lang/lang_de.json`, `lang/lang_en.json`
- Priorität bei PyInstaller: `lang/` neben der EXE/App hat Vorrang
- Entwicklung aus Source: `lang/` im Projektordner wird genutzt
- Fehlt `lang/` oder sind Dateien unvollständig, greift der harte Python-Fallback

Sprache in der App wechseln:

```text
App starten → Sprache im Header wählen → Oberfläche wird ohne Neustart aktualisiert
```

## Warum nicht einfach ein normales Vektorprogramm?

Programme wie Illustrator, CorelDRAW oder Inkscape können optisch sehr hochwertige Vektorergebnisse liefern. Für klassische Grafik ist das oft perfekt.

Für CAD, Schneidpfade, Plotter, Fräsen oder technische Weiterverarbeitung entstehen aber häufig Probleme:

- doppelte Linien
- lose Objektpfade
- lose Ankerpunkte
- sehr viele unnötige Punkte
- kleine Störflächen
- gefüllte Formen statt sauberer Konturen
- unklare Layer-Struktur
- Innenkonturen oder Löcher werden beim Füllen falsch interpretiert

**Vektorrazor** ist deshalb nicht auf schöne Grafik optimiert, sondern auf kontrollierbare, technische Konturen:

```text
Farbe erkennen → Fläche trennen → Kontur bilden → Störungen entfernen → Punkte reduzieren → Layer exportieren
```

## Programm-Infos

| Bereich | Info |
|---|---|
| Name | Vektorrazor |
| Typ | Desktop-Programm |
| Oberfläche | Tkinter |
| Fertige Downloads | Windows amd64, Ubuntu/Linux amd64, macOS |
| Optionaler KI-Upscaler | Real-ESRGAN ncnn Vulkan |
| Input | PNG, JPG, BMP, WEBP, TIFF |
| Zwischenformat | technisch bereinigtes PNG |
| Export | DXF, SVG, STL, OBJ |
| DXF-Kompatibilität | R2000, R2004, R2007, R2010, R2013, R2018 |
| Ziel | CAD-freundlichere Konturen aus vorbereiteten Logos und Bildvorlagen |
| Lizenz | GPL-3.0 |

## Aktuelle Hauptfunktionen

- Bildvorbereitung mit Helligkeit, Kontrast, Schwarzpunkt, Weißpunkt und Gamma
- optionale KI-Hochskalierung über Real-ESRGAN ncnn Vulkan
- automatische Farberkennung
- technische RGB-Kontrastfarben
- Logo-/Scan-Bereinigung für schwierige Vorlagen
- dynamische Farbtabelle
- Layernamen je Farbe
- Mindestfläche gegen Störungen
- Punktreduktion über Epsilon
- Glättung und Cleanup
- Vorschau-Modi für Konturlinien, Objektcheck und Farbmaske
- Pfade in der Vorschau auswählen und entfernen
- SVG-, DXF-, STL- und OBJ-naher Export-Workflow
- DXF-Kompatibilitätsauswahl für verschiedene Programme
- fertige Builds für Windows, Ubuntu/Linux und macOS über GitHub Releases

## Drittanbieter / Real-ESRGAN

Die optionale KI-Hochskalierung nutzt Drittanbieter-Komponenten:

- **Real-ESRGAN** von Xintao Wang / Tencent ARC Lab
- **Real-ESRGAN ncnn Vulkan** von Xintao Wang
- teilweise Komponenten/Code aus **realsr-ncnn-vulkan** von nihui

Wenn Real-ESRGAN-Dateien oder Models im Vektorrazor-Release mitgeliefert werden, müssen die zugehörigen Lizenztexte und Copyright-Hinweise im Release-Paket bleiben.

Vektorrazor ist nicht offiziell mit Real-ESRGAN, Xintao Wang oder Tencent ARC Lab verbunden und wird von diesen nicht beworben oder unterstützt.

## Copyright / Urheberrecht

Copyright (C) 2026 Andreas Rottmann

Die Urheberangabe ist in folgenden Stellen hinterlegt:

- `README.md`, `README.de.md`, `README.en.md`
- `AUTHORS.md`
- `NOTICE.md`
- Quellcode-Header mit SPDX-Lizenzhinweis
- `version_info.txt` für Windows-EXE-Metadaten
- `assets/vektorrazor.ico` als EXE- und Fenster-Icon

## Lizenz

Dieses Projekt steht unter der **GPL-3.0**.  
Details siehe [LICENSE](LICENSE).
