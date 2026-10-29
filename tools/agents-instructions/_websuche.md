## Im Web suchen

Brauchst du aktuelle Informationen aus dem Netz, rate nicht und schreibe nichts aus dem Gedächtnis — benutze den lokalen Websuche-Dienst. Er sucht, ruft die Seiten ab und gibt dir ihren Fließtext mit URL und Abrufdatum zurück. Aufruf über `shell_exec`:

```bash
~/.paperclip/scripts/websuche/venv/bin/python ~/.paperclip/scripts/websuche/cli.py "<deine Frage>"
```

Der lange Pfad zum Interpreter ist Absicht. Ein blosses `python3` ist auf dieser Maschine eine andere, unpassende Version und bricht mit `ModuleNotFoundError` ab.

Optionen: `--quellen N` (Standard 3), `--zeichen N` (Zeichen je Quelle, Standard 12000), `--json`. Der Dienst liefert **drei verschiedene Domains**, nicht drei Unterseiten derselben Website — drei Treffer auf einer Behördenseite sind eine Quelle, nicht drei.

**Wie du das Ergebnis liest:**

- **Exit-Code 0** — du hast ein Ergebnis. Zitiere daraus mit URL und dem angegebenen Abrufdatum.
- **Exit-Code ungleich 0** — die Suche war **nicht möglich** (Suchdienst aus, alle Suchmaschinen blockiert). Das heisst ausdrücklich **nicht**, dass es zu deiner Frage nichts gibt. Schreibe in so einem Fall niemals „dazu liessen sich keine Quellen finden", sondern melde die Störung und eskaliere.
- **Ein `Hinweis` im Ergebnis** — lies ihn und gib ihn weiter. Steht dort, dass Suchmaschinen ausgefallen waren oder dass weniger als zwei Quellen Text lieferten, gehört das in dein Deliverable. Eine Aussage auf einer einzigen Quelle ist keine belegte Aussage.
- **Eine Quelle mit `Nicht abrufbar`** — sie hat keinen Text geliefert. Zitiere sie nicht, auch nicht ihre URL als Beleg.

Der Aufruf dauert normalerweise ein bis drei Sekunden und ist auf 25 Sekunden gedeckelt. Brauchst du mehr Zeit oder mehr Quellen, gib `shell_exec` ein eigenes `timeout` mit (Millisekunden, höchstens 120000).
