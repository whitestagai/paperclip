@echo off
REM ==========================================================================
REM  start_llms.bat - Fallback-Modelle auf WHITESTAG-AI nach einem Neustart
REM ==========================================================================
REM
REM  Warum: Nach einem Neustart laedt LM Studio die Modelle unter ihren
REM  Standard-Kennungen (gemma-4-31b-it, abiray/qwen3.6-35b-a3b). Die 37
REM  lmstudio-Agenten erwarten als Fallback aber gemma-4-31b-win und
REM  qwen3.6-35b-win - sonst zeigt ihr Fallback ins Leere (14.10.2026).
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
echo Entlade Instanzen unter Standard-Kennung (Fehler hier sind normal) ...
lms unload gemma-4-31b-it 2>nul
lms unload abiray/qwen3.6-35b-a3b 2>nul

echo.
echo Lade gemma-4-31b-win (Q4_K_M) ...
lms load "lmstudio-community/gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf" --identifier gemma-4-31b-win -c %CTX% --parallel %SLOTS% -y

echo.
echo Lade qwen3.6-35b-win (Q6_K) ...
lms load "Abiray/Qwen3.6-35B-A3B-Q6_K-GGUF/Qwen3.6-35B-A3B-Q6_K.gguf" --identifier qwen3.6-35b-win -c %CTX% --parallel %SLOTS% -y

echo.
echo Stand:
lms ps

:ende
echo.
echo Fenster schliesst in 60 Sekunden (Taste druecken zum Schliessen).
timeout /t 60 >nul
endlocal
