# MLX-Fallback-Wächter

Läuft **auf dem MacBook M5 Max**, nicht auf dem Studio.

## Wozu

`gemma-4-31b-it-mlx` ist das Fallback-Modell von 14 Agenten und des
Wake-Satelliten. Es wird gelegentlich verdrängt und danach per JIT mit dem
Standard-TTL von 1 h nachgeladen. Weil es als Fallback selten aufgerufen wird,
läuft dieses TTL ab und das Netz verschwindet unbemerkt — am 22.08.2026 hat
genau das eine Fehlerwelle ausgelöst („Model unloaded", 61 Läufe).

Der Wächter prüft alle 15 Minuten und lädt bei gesetztem TTL oder fehlendem
Modell **ohne `--ttl`** nach. Das ergibt `ttlMs = null`, also dauerhaft.

## Installation auf dem MacBook

    scp mlx-fallback-waechter.sh walterschonenbrocher@192.168.2.40:~/.paperclip-scripts/
    scp de.whitestag.mlx-fallback-waechter.plist walterschonenbrocher@192.168.2.40:~/Library/LaunchAgents/
    ssh walterschonenbrocher@192.168.2.40 \
      'launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.whitestag.mlx-fallback-waechter.plist'

Log: `~/.paperclip-logs/mlx-fallback-waechter.log` auf dem MacBook.

## Fallen, die beim Bau zugebissen haben

**Der Kurzname des MacBook ist `walterschonenbrocher`** — ohne „e" nach „Sch",
ohne „oe". Nicht wie auf dem Studio.

**`$HOME` in einem SSH-Kommando wird LOKAL aufgelöst.** Eine plist, die per
`ssh host "cat > … <<EOF … $HOME …"` geschrieben wird, bekommt den Pfad der
*Quellmaschine*. Ergebnis war eine syntaktisch gültige plist, die auf ein
nicht existierendes Skript zeigte — launchd meldete nur Exit 78. Pfade in
plists deshalb **wörtlich** schreiben, nie über Variablen.

**Nie entladen, solange das Modell rechnet.** Der Wächter setzt bei
`generating`/`processingPrompt` aus und versucht es im nächsten Zyklus — sonst
bricht er einen laufenden Agentenlauf ab.

**Vollen Pfad zu `lms` nutzen** (`~/.lmstudio/bin/lms`). Im PATH liegt ein
npx-Wrapper aus nvm, der jedes Kommando mit einer „Invalid usage"-Box quittiert,
ohne etwas zu tun.
