# n8n.sh — Start- und Preload-Skript

**Live liegt die Datei unter `~/Desktop/n8n.sh`** und wurde bis 23.08.2026 gar
nicht versioniert. Diese Kopie ist der Stand vom 23.08.2026.

Sie startet n8n und lädt das LM-Studio-Modellset pro Gerät vor. Enthält KEINE
Geheimnisse — die kommen zur Laufzeit aus `~/.whitestag.env` (chmod 600).

**Bei Änderungen beide Stellen pflegen**, sonst driftet der Live-Stand weg:

    cp ~/Desktop/n8n.sh <repo>/tools/n8n-start/n8n.sh
