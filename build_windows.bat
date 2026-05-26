@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
py -m pip install -r requirements_build.txt
pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py
echo.
echo Fertig. EXE liegt unter: dist\Vektorrazor.exe
echo Copyright-Metadaten: Andreas Rottmann
pause
