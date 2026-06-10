# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Andreas Rottmann
#
# This file is part of Vektorrazor.

"""Programmeinstieg für Vektorrazor.

Die Datei bleibt absichtlich sehr klein. Sie kapselt lediglich den Startpunkt,
importiert die Hauptanwendung und startet sie. Dadurch bleibt der Einstieg klar
und andere Dateien können die App-Funktionalität importieren, ohne dass beim
Import automatisch sofort die GUI geöffnet wird.
"""

from workflow_app import main


# Start nur bei direktem Programmaufruf. Bei reinem Import bleibt die
# Datei passiv, sodass Tests und Teilimporte keine GUI unbeabsichtigt öffnen.
if __name__ == "__main__":
    main()
