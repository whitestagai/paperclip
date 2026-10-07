# node-wacht — Erreichbarkeit der WHITESTAG-AI

Protokolliert alle 15 Minuten, ob der LM-Link-Node WHITESTAG-AI verbunden
ist und ob seine beiden Fallback-Modelle über die API auflösen.

    ~/.paperclip/logs/node-erreichbarkeit.log
    2026-10-07 08:46:42 | connected | gemma-4-31b-win=200 qwen3.6-35b-win=200

**Reine Beobachtung — es alarmiert nicht.** Ein Ausfall fällt erst beim
nächsten Lauf der Modell-Aufsicht auf (einmal täglich). Der
15-Minuten-Takt ist Aufzeichnungsdichte, keine Reaktionszeit.

**Warum es das gibt:** Seit dem 06.10.2026 ist der Node Fallback-Gerät von
37 Agenten. Ein Fallback auf eine Maschine, die zeitweise fehlt, ist
schlechter als der vorherige auf das dauerhaft laufende
`google/gemma-4-12b` am Studio. Dieses Log ist der Beleg, ob der Node
durchläuft. Siehe
`docs/superpowers/specs/2026-10-06-whitestag-ai-node-farm-einbindung-design.md`.

## Zum Drift-Test

`diff -rq ~/.paperclip/scripts/node-wacht tools/node-wacht` meldet für
dieses Verzeichnis **immer** einen Unterschied: die plist gehört nach
`~/Library/LaunchAgents/` und liegt im Repo nur als Kopie zur
Nachvollziehbarkeit. Geprüft wird sie so:

    diff ~/Library/LaunchAgents/ai.whitestag.node-erreichbarkeit.plist \
         tools/node-wacht/ai.whitestag.node-erreichbarkeit.plist

## Tests

    cd ~/.paperclip/scripts/node-wacht && /usr/bin/python3 -m pytest -q

Die Tests setzen `LMS_BIN`, `CURL_BIN` und `LOG_FILE` auf Attrappen; diese
drei Variablen existieren im Skript nur dafür. Der wichtigste Fall ist
`test_getrennter_node_mit_folgendem_geraet_wird_nicht_als_connected_gemeldet`:
ein getrennter Node hat keine `Loaded Models Instances`, sein Block in
`lms link status` ist also kürzer — eine Blockbildung mit fester
Zeilenzahl (`grep -A4`) liest in das nächste Gerät hinein und findet dort
`Status: connected`. Das Skript würde den Node dann als verbunden
protokollieren, obwohl er weg ist.
