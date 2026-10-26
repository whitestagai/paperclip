#!/bin/bash
# Wrapper für die tägliche Arbeitszeit-Mail (launchd de.whitestag.claude-arbeitszeit)
cd "$(dirname "$0")" || exit 1
exec /usr/bin/python3 arbeitszeit.py "$@"
