@echo off
REM ==========================================================================
REM  start_llms.bat - Modelle auf WHITESTAG-AI nach einem Neustart
REM
REM  STAND 21.10.2026: qwen Q4_K_M gehoert allein auf die RTX 5090, gemma
REM  Q4_K_M allein auf die RTX 3090. Das kann lms NICHT (keine GPU-Auswahl).
REM  Dieses Skript laedt beide nur, damit nach einem Neustart ueberhaupt
REM  etwas laeuft - verteilt ueber beide Karten und damit LANGSAM.
REM  RICHTIG geht es nur in der GUI (Ctrl+Shift+H, Hardware):
REM    1. beide Modelle entladen
REM    2. 3090 aus  -> qwen laden (Identifier qwen3.6-35b-a3b, 262144, parallel 4)
REM       In den Modell-Einstellungen MUSS "Number of layers ... MoE weights onto
REM       CPU" auf 0 stehen (stand am 21.10. auf 40 -> alles auf der CPU).
REM       262144 statt 98304, weil "Unified KV Cache" alle Slots EIN Fenster
REM       teilen laesst (4 x 27k scheiterten mit 98304).
REM    3. 5090 aus, 3090 an -> gemma laden (gemma-4-31b-it, 98304, parallel 2)
REM    4. beide GPUs wieder an
REM  Vorher "Limit Model Offload to Dedicated GPU Memory" einschalten.
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
REM  - qwen ist seit 21.10. Q4_K_M (lmstudio-community), nicht mehr Q6_K
REM    (abiray). Die RTX Pro 6000 traegt seit 21.10. keine Modelle mehr.
REM  - gemma-4-31b-it@q8_0 ist ein 1,26-GB-Fragment - nicht laden.
REM
REM  Autostart: Verknuepfung auf diese Datei in  shell:startup  ablegen.
REM ==========================================================================

setlocal
set CTX=98304
set SLOTS=2
set QSLOTS=4
set QCTX=262144

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
lms unload qwen3.6-35b-a3b 2>nul
lms unload abiray/qwen3.6-35b-a3b 2>nul
REM Altlast bis 19.10.2026
lms unload gemma-4-31b-win 2>nul
lms unload qwen3.6-35b-win 2>nul

echo.
echo Lade gemma-4-31b-it (Q4_K_M) ...
lms load "lmstudio-community/gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf" --identifier gemma-4-31b-it -c %CTX% --parallel %SLOTS% -y

echo.
echo Lade qwen3.6-35b-a3b (Q4_K_M) ...
lms load qwen3.6-35b-a3b --identifier qwen3.6-35b-a3b -c %QCTX% --parallel %QSLOTS% --gpu max -y

echo.
echo ACHTUNG: Beide Modelle liegen jetzt auf BEIDEN Karten verteilt (langsam).
echo Kartenzuordnung per GUI nachziehen, siehe Kopf dieser Datei.

echo.
echo Stand:
lms ps

:ende
echo.
echo Fenster schliesst in 60 Sekunden (Taste druecken zum Schliessen).
timeout /t 60 >nul
endlocal
