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

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![GUI](https://img.shields.io/badge/GUI-Tkinter-brightgreen)
![Export](https://img.shields.io/badge/Export-DXF%20%7C%20SVG-orange)
![License](https://img.shields.io/badge/License-GPLv3-blue)
![Status](https://img.shields.io/badge/Status-Prototype%20%2F%20CAD%20Workflow-yellow)

</p>

<p align="center"><strong>Copyright (C) 2026 Andreas Rottmann</strong></p>

## Kurzbeschreibung

**Vektorrazor** ist ein Python/Tkinter-Tool, das vorbereitete PNG-Logos in CAD-nähere Vektordaten umwandelt.

Der Workflow ist bewusst zweistufig:

```text
1. Bild vorbereiten / Farben technisch bereinigen
2. Vektorisieren / Konturen prüfen / DXF oder SVG exportieren
```

## Superkurzer Quickguide

### Windows

1. `python main.py` starten.
2. In **Schritt 1** das PNG laden.
3. Farben reduzieren oder technische Kontrastfarben erzeugen.
4. **Weiter zur Vektorisierung** klicken.
5. In **Schritt 2** **Erkennen / Vorschau** klicken.
6. Ungewollte Pfade bei Bedarf im Auswahlmodus entfernen.
7. DXF-Kompatibilität wählen, z. B. **Illustrator/CorelDRAW empfohlen**.
8. **Export DXF / SVG** klicken.

### Linux / WSL Ubuntu

1. Systempakete installieren:

```bash
sudo apt update
sudo apt install python3-tk python3-venv python3-pip
```

2. Virtuelle Umgebung erstellen:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Python-Abhängigkeiten installieren:

```bash
pip install -r requirements.txt
```

4. Programm starten:

```bash
python main.py
```

5. Workflow verwenden:

```text
PNG laden → Weiter zur Vektorisierung → Erkennen / Vorschau → Export
```

Hinweis: Unter WSL muss eine grafische Oberfläche verfügbar sein. Unter Windows 11 funktioniert das meist über WSLg. Bei älteren Setups kann ein X-Server nötig sein.

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

## Windows-EXE bauen

```bat
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py
```

Oder einfach:

```bat
build_windows.bat
```

Das Icon liegt unter:

```text
assets/vektorrazor.ico
```

Es wird mit `--icon` in die EXE eingebettet und zusätzlich mit `--add-data` für das Fenster-Icon mitgeliefert.

## Linux-amd64 Build bauen

Unter Linux / WSL Ubuntu:

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

Das Ergebnis liegt danach hier:

```text
dist/Vektorrazor
```

Starten:

```bash
chmod +x dist/Vektorrazor
./dist/Vektorrazor
```

Wichtig: Unter Linux verwendet PyInstaller bei `--add-data` einen Doppelpunkt `:`.  
Unter Windows wird ein Semikolon `;` verwendet.

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

Mit fixem Datum:

```bash
RELEASE_DATE=2026-05-26 ./pack_release.sh
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
| Sprache | Python |
| Oberfläche | Tkinter |
| Input | PNG, JPG, BMP, WEBP, TIFF |
| Zwischenformat | technisch bereinigtes PNG |
| Export | DXF, SVG |
| DXF-Kompatibilität | R2000, R2004, R2007, R2010, R2013, R2018 |
| Ziel | CAD-freundlichere Konturen aus vorbereiteten Logos |
| Windows Build | Windows amd64 EXE |
| Linux Build | Linux amd64 Binary |

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
- Windows- und Linux-amd64-Build möglich

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
