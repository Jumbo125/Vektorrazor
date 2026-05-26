<p align="center">
  <img src="assets/vektorrazor_icon.png" width="180" alt="Vektorrazor Icon">
</p>

<h1 align="center">Vektorrazor</h1>

<p align="center">
  <strong>PNG-Logo → CAD-orientierte Vektorkonturen</strong>
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

## Kurzbeschreibung

**Vektorrazor** ist ein Desktop-Tool, das vorbereitete PNG-Logos in CAD-nähere Vektordaten umwandelt.

Der Workflow ist bewusst zweistufig:

```text
1. Bild vorbereiten / Farben technisch bereinigen
2. Vektorisieren / Konturen prüfen / DXF oder SVG exportieren
```

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
PNG laden → Weiter zur Vektorisierung → Erkennen / Vorschau → Export DXF / SVG
```

### Linux amd64

1. Auf GitHub unter **Releases** die Linux-Datei herunterladen:

```text
Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
```

2. Archiv entpacken:

```bash
tar -xzf Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
cd Vektorrazor-Linux-amd64-YYYY-MM-DD
```

3. Datei ausführbar machen:

```bash
chmod +x Vektorrazor
```

4. Programm starten:

```bash
./Vektorrazor
```

Hinweis: Unter Linux muss eine grafische Oberfläche vorhanden sein. Unter WSL funktioniert das mit Windows 11 meist über WSLg. Bei älteren WSL-Setups kann ein X-Server nötig sein.

## Installation

Für normale Benutzer ist keine Python-Installation nötig. Es gibt fertige Release-Dateien:

| System | Datei | Aktion |
|---|---|---|
| Windows amd64 | `Vektorrazor-Windows-amd64-YYYY-MM-DD.zip` | entpacken und `Vektorrazor.exe` starten |
| Linux amd64 | `Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz` | entpacken, ausführbar machen und starten |

### Windows

```text
ZIP herunterladen → entpacken → Vektorrazor.exe starten
```

### Linux

```bash
tar -xzf Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
cd Vektorrazor-Linux-amd64-YYYY-MM-DD
chmod +x Vektorrazor
./Vektorrazor
```

## Hinweise für Entwickler

Der Quellcode liegt ebenfalls im Repository. Wer selbst entwickeln oder eigene Builds erstellen möchte, kann das weiterhin mit Python und PyInstaller tun.

### Aus Source starten

```bash
pip install -r requirements.txt
python main.py
```

### Windows-EXE selbst bauen

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py
```

### Linux-amd64 selbst bauen

```bash
pyinstaller --onefile --windowed --clean   --name Vektorrazor   --add-data "assets/vektorrazor.ico:assets"   --add-data "assets/vektorrazor_icon.png:assets"   main.py
```

## Release-Pakete erstellen

Wenn beide Builds vorhanden sind:

```text
dist/Vektorrazor.exe
dist/Vektorrazor
```

kann das Release-Script ausgeführt werden:

```bash
chmod +x pack_release.sh
./pack_release.sh
```

Es erzeugt z. B.:

```text
release/Vektorrazor-Windows-amd64-2026-05-26.zip
release/Vektorrazor-Linux-amd64-2026-05-26.tar.gz
release/SHA256SUMS-2026-05-26.txt
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
| Fertige Downloads | Windows amd64 EXE, Linux amd64 Binary |
| Input | PNG, JPG, BMP, WEBP, TIFF |
| Zwischenformat | technisch bereinigtes PNG |
| Export | DXF, SVG |
| DXF-Kompatibilität | R2000, R2004, R2007, R2010, R2013, R2018 |
| Ziel | CAD-freundlichere Konturen aus vorbereiteten Logos |
| Lizenz | GPL-3.0 |

## Aktuelle Hauptfunktionen

- Bildvorbereitung mit Helligkeit, Kontrast, Schwarzpunkt, Weißpunkt und Gamma
- automatische Farberkennung
- technische RGB-Kontrastfarben
- Logo-Maske für schwierige Vorlagen
- dynamische Farbtabelle
- Layernamen je Farbe
- Mindestfläche gegen Störungen
- Punktreduktion über Epsilon
- Glättung und Cleanup
- Vorschau-Modi für Konturlinien, Objektcheck und Farbmaske
- Pfade in der Vorschau auswählen und entfernen
- SVG- und DXF-Export
- DXF-Kompatibilitätsauswahl für verschiedene Programme
- fertige Windows-amd64- und Linux-amd64-Dateien über GitHub Releases

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
