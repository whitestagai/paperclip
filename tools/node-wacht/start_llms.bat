@echo off
REM ==========================================================================
REM  start_llms.bat - Fallback-Modelle auf WHITESTAG-AI nach einem Neustart
REM ==========================================================================
REM
REM  Warum: Nach einem Neustart laedt LM Studio die Modelle unter ihren
REM  Standard-Kennungen (gemma-4-31b-it, abiray/qwen3.6-35b-a3b), aber mit
REM  Default-Preset. Seit 19.10.2026 erwarten die 38 lmstudio-Agenten genau
REM  diese Standard-Kennungen als Fallback (vorher -win, das nach jedem
REM  Neustart ins Leere zeigte). Dieses Skript laedt sie nur neu, damit
REM  Kontext 98304 und 2 Slots sicher stimmen - die Kennung bleibt gleich.
REM
REM  VORSICHT beim Aendern:
REM  - qwen wird ueber den PFAD geladen, nicht ueber den Key. Der Key
REM    "qwen3.6-35b-a3b" gibt es zweimal (hier Q6_K und auf der RTX Q8_0).
REM  - NIE "lms unload qwen3.6-35b-a3b": das ist die Kennung des
REM    RTX-Primaermodells der C-Suite.
REM  - gemma-4-31b-it@q8_0 ist ein 1,26-GB-Fragment - nicht laden.
REM
REM  Autostart: Verknuepfung auf diese Datei in  shell:startup  ablegen.
REM ==========================================================================

setlocal
set CTX=98304
set SLOTS=2

echo Warte auf LM Studio ...
set /a VERSUCH=0
:warten
lms ps >nul 2>&1
if not errorlevel 1 goto bereit
set /a VERSUCH+=1
if %VERSUCH% geq 60 (
  echo FEHLER: LM Studio antwortet nach 5 Minuten nicht.
  goto ende
)
timeout /t 5 /nobreak >nul
goto warten

:bereit
echo.
echo Entlade vorhandene Instanzen (Fehler hier sind normal) ...
lms unload gemma-4-31b-it 2>nul
lms unload abiray/qwen3.6-35b-a3b 2>nul
REM Altlast bis 19.10.2026
lms unload gemma-4-31b-win 2>nul
lms unload qwen3.6-35b-win 2>nul

echo.
echo Lade gemma-4-31b-it (Q4_K_M) ...
lms load "lmstudio-community/gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf" --identifier gemma-4-31b-it -c %CTX% --parallel %SLOTS% -y

echo.
echo Lade abiray/qwen3.6-35b-a3b (Q6_K) ...
lms load "Abiray/Qwen3.6-35B-A3B-Q6_K-GGUF/Qwen3.6-35B-A3B-Q6_K.gguf" --identifier abiray/qwen3.6-35b-a3b -c %CTX% --parallel %SLOTS% -y

echo.
echo Stand:
lms ps

:ende
echo.
echo Fenster schliesst in 60 Sekunden (Taste druecken zum Schliessen).
timeout /t 60 >nul
endlocal
