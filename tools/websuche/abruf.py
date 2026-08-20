"""Eine einzelne Seite holen und ihren Fließtext extrahieren.

Bewusst ohne Kenntnis der Suchquelle: was hier hereinkommt, ist eine URL, was
herausgeht, ist entweder Text oder eine Fehlermeldung — nie beides.

WAS DAS ZEITBUDGET WIRKLICH LEISTET
-----------------------------------
`hole_text(timeout=T)` deckelt Namensaufloesung, robots.txt, alle
Weiterleitungen, die Kopfzeilen und den Rumpf gemeinsam. Durchgesetzt wird
das an fuenf Stellen, und jede deckt einen Abschnitt ab, den die anderen
nicht erreichen:

1. eine eigene Frist fuer `getaddrinfo` (`_aufloesen_mit_frist`),
2. `min(Restbudget, SOCKET_FRIST)` als Timeout je Socket-Operation — EINMAL
   je Sprung berechnet, unmittelbar vor der Anfrage, und danach nicht
   nachgezogen (frueher stand hier "auf jeder einzelnen Socket-Operation";
   das war zu viel versprochen),
3. eine Fristpruefung nach jedem Leseschritt (`read1`, nicht `iter_content`
   — siehe `_lies_gedeckelt`),
4. der Socket-Waechter (`_Fristwaechter`): ein Timer ueber die Restfrist, der
   den Socket unter der laufenden Antwort zuklappt. Er ist der einzige
   Mechanismus, der auch dort greift, wo die wartende Schleife unterhalb von
   `read1` liegt — und er zieht die zu frueh berechnete Frist aus Punkt 2
   nachtraeglich wieder gerade,
5. der Kopf-Waechter (`_KopfWaechter`): derselbe Griff, eine Phase frueher.

Gemessen gegen echte Server bei 1,0 s Budget (Median aus drei Laeufen):

    troepfelnde Seite (8 Bytes/20 ms)      1,00 s   (vor 3.: 30,0 s)
    troepfelnde robots.txt                 1,01 s   (vor 3.: 30,0 s; in der
                                                     Praxis 81 s gemessen)
    Server schweigt nach den Kopfzeilen     1,01 s
    troepfelt bis kurz vor die Frist,
      dann Schweigen                        1,01 s   (vor 4.: Budget + volle
                                                     SOCKET_FRIST — gemessen
                                                     2,93 s bei 2,0 s Budget
                                                     und SOCKET_FRIST 1,0)
    gueltige, leer dekodierende
      gzip-Bloecke (Z_SYNC_FLUSH)           1,01 s   (vor 4.: 30,0 s)
    troepfelnde chunked-Groessenzeile       1,01 s   (vor 4.: 20,1 s)
    troepfelnde Kopfzeilen, 50 ms/Zeile     1,00 s   (vor 5.:  5,40 s)
    troepfelnde Kopfzeilen, 200 ms/Zeile    1,01 s   (vor 5.: 20,54 s)

Die Formen 5 bis 7 galten als unbehebbar, weil ihre wartende Schleife in
urllib3 bzw. `http.client` liegt — unterhalb jeder Stelle, an der dieser
Code eine Frist pruefen koennte. Das stimmt und war trotzdem der falsche
Schluss: es verwechselt Unterbrechen mit Schliessen. Der Lesevorgang laesst
sich nicht unterbrechen, der Socket darunter aber aus einem zweiten Faden
schliessen; danach kehrt jedes wartende `recv` sofort zurueck. Siehe
`_socket_zuklappen`.

Die Kopfzeilen-Form hielt sich dann noch eine Runde laenger, weil dort auch
das nicht reichte: sie laeuft, bevor es ein Antwortobjekt und damit einen
Socket zum Zuklappen gibt. Der Ausweg ist derselbe Gedanke, eine Ebene
tiefer angesetzt — nicht den Socket spaeter greifen, sondern die Verbindung
frueher. urllib3 gibt sie in `_get_conn` heraus; ein eigener Pool legt sie
dort in den `_Verbindungsschacht` des abrufenden Fadens, und der Kopf-
Waechter hat damit einen Griff, WAEHREND `requests` noch die Kopfzeilen
liest. Ohne das war der Deckel 100 x Tropfabstand (`http.client._MAXHEADERS`),
nach oben nur durch die Geduld des Angreifers begrenzt.

WAS WEITERHIN NICHT GEDECKELT IST
---------------------------------
Zwei Dinge, beide bewusst:

- Der Hilfsfaden der Namensaufloesung. `getaddrinfo` laesst sich nicht
  unterbrechen; der Aufrufer bekommt seine Frist zurueck, die Aufloesung
  laeuft im Daemon-Faden weiter, bis der System-Resolver aufgibt. Das kostet
  keinen Socket und keine Zeit im Abruf, nur einen schlafenden Faden.
- Der Zugriff auf urllib3-Interna (`_get_conn` und die Attributkette in
  `_socket_zuklappen`). Beides kann ein Update wegnehmen. Deshalb haelt je
  ein Test den Weg fest, und beide Waechter melden auf stderr, wenn sie ins
  Leere greifen — ein wirkungsloser Waechter, von dem niemand weiss, ist
  schlimmer als gar keiner.

Folge fuer `websuche.recherchiere`: die Annahme "ein aufgegebener Thread
endet von selbst kurz nach dem Seitenbudget" traegt jetzt fuer alle oben
gemessenen Formen. Der Zaehler fuer aufgegebene Abrufe bleibt trotzdem — er
kostet nichts und ist die einzige Stelle, an der ein doch haengender Thread
ueberhaupt sichtbar wuerde.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import sys
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.structures import CaseInsensitiveDict

USER_AGENT = ("WHITESTAG-Websuche/1.0 "
              "(Recherche-Agent; kontakt: ws@whitestag.ai)")

# Sagt dem Server, was wir verwerten koennen. Ersetzt keine Pruefung — viele
# Server ignorieren Accept —, spart aber die Uebertragung offensichtlicher
# Binaerformate.
ACCEPT = "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1"

# Alles ausserhalb dieser Liste ist kein Fliesstext. Ein PDF lieferte bisher
# 12.000 Zeichen "%PDF-1.4 ..." als `text`, zaehlte damit als verwertbare
# Quelle und unterdrueckte den Hinweis auf zu wenige Quellen.
TEXT_MIMES = {"text/html", "application/xhtml+xml", "text/plain",
              "application/xml", "text/xml", "text/markdown"}

# Weiterleitungen werden selbst gefahren, damit jedes Ziel vor dem Abruf
# geprueft werden kann. Fuenf Spruenge decken die ueblichen
# http->https->www->Sprachpfad-Ketten ab.
MAX_WEITERLEITUNGEN = 5
WEITERLEITUNGS_CODES = (301, 302, 303, 307, 308)

# Obergrenze fuer den gelesenen Rumpf. `timeout` von requests ist ein
# Lesetimeout ZWISCHEN Bytes, kein Gesamtdeckel: ohne diese Grenze landet eine
# 500-MB-Datei vollstaendig im Speicher. 2 MB HTML sind weit mehr, als fuer
# 12.000 Zeichen Fliesstext je gebraucht werden.
MAX_RUMPF_BYTES = 2_000_000

# Auch die robots.txt wird gedeckelt gelesen. RFC 9309, 2.5 verlangt von
# Crawlern, mindestens 500 KiB zu verarbeiten — mehr ist keine Regeldatei,
# sondern ein Speicherangriff unter freundlichem Namen.
MAX_ROBOTS_BYTES = 512_000

# Anteil des Seitenbudgets, das der robots.txt-Abruf hoechstens verbrauchen darf.
ROBOTS_TIMEOUT = 5.0

ROBOTS_ACCEPT = "text/plain,*/*;q=0.1"

# Groesse eines Leseschritts. Kein Deckel, sondern eine Obergrenze: gelesen
# wird mit `read1()`, das zurueckkehrt, sobald ueberhaupt etwas da ist.
LESE_STUECK = 16384

# Obergrenze fuer eine EINZELNE Socket-Operation (Verbinden bzw. ein recv).
# Sie begrenzt den Fall "Server schweigt": ohne sie stuende dort das volle
# Restbudget noch einmal. Ein Server, der laenger als 5 s gar nichts sendet,
# ist fuer eine Recherche ohnehin verloren.
#
# Sie wird je Sprung EINMAL berechnet und nicht nachgezogen — gegen einen
# Server, der bis kurz vor die Frist troepfelt und dann verstummt, hing
# dadurch eine volle SOCKET_FRIST hinten dran. Nachgezogen wird sie jetzt
# nicht rechnerisch, sondern durch die beiden Waechter, die bei Fristablauf
# zuklappen — in der Kopfzeilen-Phase ebenso wie im Rumpf.
SOCKET_FRIST = 5.0

# Name der Waechter-Faeden. Er ist Teil der Zusicherung, nicht Kosmetik: der
# Test, der das Abbestellen prueft, erkennt sie daran wieder.
WAECHTER_FADEN_NAME = "websuche-frist"

# Eigene Schranke fuer die Namensaufloesung: `socket.getaddrinfo` kennt kein
# timeout-Argument und haengt an einem stummen Resolver, bis das System
# aufgibt. Ohne diese Schranke laeuft die Zielpruefung selbst aus dem Budget.
DNS_FRIST = 3.0

# Alles, was auf jeder Seite steht und in keinem Zitat etwas verloren hat.
BEIWERK = ("script", "style", "nav", "header", "footer", "aside", "noscript",
           "form", "iframe")


@dataclass(frozen=True)
class AbrufErgebnis:
    text: str | None = None
    fehler: str | None = None


def _aufloesen(host: str) -> list[str]:
    """Namensaufloesung als eigene Funktion, damit Tests sie ersetzen koennen."""
    return [eintrag[4][0]
            for eintrag in socket.getaddrinfo(host, None,
                                              type=socket.SOCK_STREAM)]


def _aufloesen_mit_frist(host: str, sekunden: float) -> list[str]:
    """`_aufloesen` mit Zeitschranke.

    `socket.getaddrinfo` nimmt kein timeout entgegen und laesst sich nicht
    unterbrechen. Der Aufrufer bekommt seine Frist deshalb ueber einen
    Hilfsfaden zurueck; die Aufloesung selbst laeuft dort weiter, bis der
    System-Resolver aufgibt. Der Faden ist ein Daemon und haelt weder den
    Dienst noch das CLI beim Beenden auf.
    """
    ergebnis: dict = {}

    def arbeite():
        try:
            ergebnis["adressen"] = _aufloesen(host)
        except BaseException as e:  # noqa: BLE001 — wird unten weitergeworfen
            ergebnis["fehler"] = e

    faden = threading.Thread(target=arbeite, daemon=True,
                             name=f"dns-{host}")
    faden.start()
    faden.join(max(0.0, sekunden))
    if faden.is_alive():
        # TimeoutError ist ein OSError — der Aufrufer faengt beides gemeinsam.
        raise TimeoutError(f"Aufloesung ueberschritt {sekunden:.1f}s")
    if "fehler" in ergebnis:
        raise ergebnis["fehler"]
    return ergebnis.get("adressen", [])


def _adressen_des_ziels(url: str, aufloese_frist: float):
    """`(Adressen, Grund)` — genau eins von beiden ist gesetzt.

    Gemeinsamer Kern von `pruefe_ziel` und `pruefe_lokales_ziel`. Die beiden
    unterscheiden sich nur im Urteil ueber die Adressen; alles davor — Schema,
    Hostname, Aufloesung mit Frist, IPv4-in-IPv6 — ist dieselbe Logik. Zwei
    leicht abweichende Kopien davon waeren genau die Sorte Duplikat, an der
    sich in diesem Modul schon einmal eine Luecke aufgetan hat (siehe
    `_hole_gedeckelt`).
    """
    teile = urlparse(url)
    if teile.scheme not in ("http", "https"):
        return None, (f"Schema '{teile.scheme}' nicht erlaubt — abgerufen "
                      f"werden nur http und https")
    host = teile.hostname
    if not host:
        return None, f"URL ohne Hostnamen: {url}"

    try:
        adressen = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            adressen = [ipaddress.ip_address(a)
                        for a in _aufloesen_mit_frist(host, aufloese_frist)]
        except (OSError, ValueError) as e:
            return None, f"Hostname '{host}' nicht aufloesbar: {e}"
    if not adressen:
        return None, f"Hostname '{host}' liefert keine Adresse"
    # ::ffff:127.0.0.1 ist Loopback, auch wenn es als IPv6 daherkommt.
    return [getattr(a, "ipv4_mapped", None) or a for a in adressen], None


def pruefe_lokales_ziel(url: str,
                        aufloese_frist: float = DNS_FRIST) -> str | None:
    """`None`, wenn die URL auf einen Dienst auf DIESER Maschine zeigt.

    Das Gegenstueck zu `pruefe_ziel`, fuer den umgekehrten Fall: die
    Suchquelle IST ein Hausdienst auf Loopback, `pruefe_ziel` wuerde sie
    genau deshalb verweigern.

    Bewusst eine eigene Funktion und kein Schalter an `pruefe_ziel`: ein
    `pruefe_ziel(..., lokal_erlauben=True)` waere genau die Art Parameter,
    die eines Tages versehentlich am Seitenabruf steht — und dort ist er die
    ganze Abwehr. So laesst sich die Pruefung austauschen, aber nicht
    entfernen, und die hier ist strikt enger, nicht laxer.
    """
    adressen, grund = _adressen_des_ziels(url, aufloese_frist)
    if grund:
        return grund
    for adresse in adressen:
        if not adresse.is_loopback:
            return (f"Ziel '{urlparse(url).hostname}' zeigt auf {adresse} und "
                    f"damit nicht auf diese Maschine — als Suchquelle ist nur "
                    f"ein lokaler Dienst vorgesehen. Ein Ferndienst waere eine "
                    f"bewusste Entscheidung und soll nicht durch einen "
                    f"vertippten Parameter passieren")
    return None


def pruefe_ziel(url: str, aufloese_frist: float = DNS_FRIST) -> str | None:
    """`None`, wenn die URL abgerufen werden darf, sonst der Grund im Klartext.

    Hintergrund: auf dieser Maschine laufen mehrere auth-freie Dienste auf
    Loopback (vault-lookup :7788, Brain :7777/:7778, n8n :5678, Paperclip
    :3100, PII-Proxy :4711) — auth-frei genau deshalb, weil sie als nur lokal
    erreichbar gelten. Eine Trefferseite, die uns dorthin umleitet, wuerde
    deren Antwort als "Quelltext" ins Dossier tragen.

    Geprueft wird die aufgeloeste Adresse, nicht nur das URL-Literal: ein
    Hostname kann per DNS ebenso auf 127.0.0.1 zeigen. Gegen einen aktiven
    DNS-Rebinding-Angreifer (Antwort wechselt zwischen Pruefung und Verbindung)
    schuetzt das nicht — dafuer muesste die Verbindung auf die gepruefte IP
    festgenagelt werden. Der hier abgewehrte Fall ist die umleitende Fremdseite.
    """
    adressen, grund = _adressen_des_ziels(url, aufloese_frist)
    if grund:
        return grund
    host = urlparse(url).hostname
    for adresse in adressen:
        if (adresse.is_private or adresse.is_loopback or adresse.is_link_local
                or adresse.is_reserved or adresse.is_multicast
                or adresse.is_unspecified):
            return (f"Ziel '{host}' zeigt auf die lokale/private Adresse "
                    f"{adresse} — Abruf verweigert: dort laufen Hausdienste, "
                    f"deren Antwort keine Quelle ist")
    return None


def extrahiere_text(html) -> str:
    suppe = BeautifulSoup(html, "html.parser")
    for tag in suppe(BEIWERK):
        tag.decompose()
    text = suppe.get_text("\n")
    # Mehrfache Leerzeilen falten — sie kosten Kontext und tragen nichts.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()


def kappe(text: str, max_zeichen: int) -> str:
    if len(text) <= max_zeichen:
        return text
    # Die Marke muss sichtbar sein, sonst haelt das Modell die Seite fuer
    # zu Ende gelesen und zitiert einen abgeschnittenen Satz als Befund.
    return text[:max_zeichen] + f"… [gekappt bei {max_zeichen} Zeichen]"


ALLES_ERLAUBT = "alles erlaubt"
ALLES_VERBOTEN = "alles verboten"


def _hole_robots(url: str, timeout: float):
    """Holt die robots.txt einer Domain und gibt die Regel zurueck.

    Laeuft ueber denselben Kern wie der Seitenabruf. Vorher stand hier ein
    blankes `requests.get()`: Weiterleitungen wurden blind verfolgt, ohne
    Zielpruefung, ohne Deckel, ohne echte Zeitgrenze. Eine robots.txt, die
    auf einen Hausdienst umleitete, loeste dort eine echte Anfrage aus — der
    Rumpf landete zwar in keinem Ergebnis, aber bei auth-freien Diensten ist
    die ausgeloeste Anfrage selbst der Schaden (n8n-Webhook).
    """
    teile = urlparse(url)
    robots_url = urljoin(f"{teile.scheme}://{teile.netloc}", "/robots.txt")
    roh = _hole_gedeckelt(
        robots_url, time.monotonic() + timeout, accept=ROBOTS_ACCEPT,
        max_bytes=MAX_ROBOTS_BYTES,
        # Nur ein 200 hat einen Rumpf, der uns interessiert.
        kopf_pruefung=lambda a: (None if a.status_code == 200
                                 else f"HTTP {a.status_code}"))

    if roh.status >= 500:
        # RFC 9309, 2.3.1.4: ein "unreachable" robots.txt bedeutet komplettes
        # Verbot. Bisher galt jeder Status ausser 200 als Freibrief — genau
        # verkehrt herum fuer den Fall, dass der Server gerade taumelt.
        return ALLES_VERBOTEN
    if roh.status != 200:
        # Deckt auch status == 0 ab: Netzfehler, abgelaufene Zeit und das
        # verweigerte Umleitungsziel. Keine erreichbare robots.txt ist keine
        # Verbotsregel — und das verweigerte Ziel ist kein Schlupfloch, denn
        # wer die Weiterleitung setzt, ist der Seitenbetreiber selbst; der
        # koennte genauso gut eine leere robots.txt ausliefern.
        return ALLES_ERLAUBT
    parser = urllib.robotparser.RobotFileParser()
    # RFC 9309, 2.3: robots.txt ist UTF-8. `requests` haette hier ohne
    # charset-Angabe ISO-8859-1 geraten.
    parser.parse(roh.rumpf.decode("utf-8", "replace").splitlines())
    return parser


def _bewerte(regel, url: str) -> bool:
    if regel is ALLES_ERLAUBT:
        return True
    if regel is ALLES_VERBOTEN:
        return False
    return regel.can_fetch(USER_AGENT, url)


class RobotsSpeicher:
    """Merkt die robots.txt je Host fuer die Dauer EINES Laufs.

    Ohne das holt jede Seite ihre robots.txt neu — bei mehreren Seiten
    derselben Domain (--gleiche-domain-erlauben) und bei Weiterleitungen
    innerhalb einer Domain ist das reine Budgetverschwendung.

    Bewusst kein Prozess-Cache mit TTL: der Dienst laeuft wochenlang, und
    eine veraltete robots.txt waere ein leiser Regelbruch. Ein Lauf dauert
    Sekunden — so lange ist die Datei sicher gueltig.
    """

    def __init__(self):
        self._regeln = {}
        self._sperren = {}
        self._verwaltung = threading.Lock()

    def _sperre_fuer(self, host: str) -> threading.Lock:
        # Feingranular je Host: der Abruf laeuft parallel, und eine lahme
        # robots.txt darf nicht die Abrufe anderer Domains aufhalten.
        with self._verwaltung:
            return self._sperren.setdefault(host, threading.Lock())

    def darf(self, url: str, timeout: float = ROBOTS_TIMEOUT) -> bool:
        teile = urlparse(url)
        host = f"{teile.scheme}://{teile.netloc}".lower()
        with self._sperre_fuer(host):
            if host not in self._regeln:
                self._regeln[host] = _hole_robots(url, timeout)
            regel = self._regeln[host]
        return _bewerte(regel, url)


def darf_abrufen(url: str, timeout: float = ROBOTS_TIMEOUT) -> bool:
    """Einzelabfrage ohne Cache — fuer Aufrufer ausserhalb eines Laufs."""
    return _bewerte(_hole_robots(url, timeout), url)


def _formatfehler(content_type: str, rumpf: bytes) -> str | None:
    """Gibt eine Fehlermeldung zurueck, wenn der Inhalt kein Fliesstext ist."""
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime:
        if mime.startswith("text/") or mime in TEXT_MIMES:
            return None
        return (f"Kein auswertbarer Text, sondern {mime} — Inhalt nicht "
                f"zitierfaehig extrahierbar")
    # Ohne Content-Type entscheidet der Rumpf: Nullbytes und die bekannten
    # Dateisignaturen sind sichere Zeichen fuer Binaerinhalt.
    probe = rumpf[:1024]
    if b"\x00" in probe or probe.startswith((b"%PDF", b"\x89PNG", b"\xff\xd8\xff",
                                             b"PK\x03\x04", b"GIF8")):
        return "Binaerinhalt ohne Content-Type — nicht zitierfaehig extrahierbar"
    return None


def _socket_zuklappen(antwort) -> bool:
    """Klappt den Socket unter einer stroemenden Antwort zu. `True`, wenn ein
    Weg gegriffen hat.

    Der Punkt, an dem die frueher hier notierte Einschaetzung "nicht behebbar"
    falsch war: ein blockierender Lesevorgang laesst sich in Python zwar nicht
    UNTERBRECHEN, der Socket darunter aber aus einem zweiten Faden
    SCHLIESSEN. Danach kehrt jedes wartende `recv` sofort zurueck — egal, wie
    tief unter uns die Schleife sitzt, die darauf gewartet hat.

    Der Zugriff geht ueber Interna von urllib3, deshalb eine Kette mit
    Rueckfall und einem sauberen `False` am Ende:

    1. `raw.shutdown()` — seit urllib3 2.3 oeffentlich und genau dafuer
       gebaut. Wirft `ValueError`, wenn der Socket nicht mehr gehalten wird,
       und `RuntimeError`, wenn die Verbindung schon zurueck im Pool ist.
    2. `raw._fp.fp.raw._sock` — der Socket, den `http.client` haelt. Sein
       repr sagt "[closed]", weil urllib3 ihn abgeloest hat; `shutdown()`
       wirkt trotzdem.
    3. `raw._connection.sock` — der Weg aelterer urllib3-Staende. Unter 2.7.0
       ist er immer `None`, weil die Verbindung den Socket beim
       `getresponse()` an die Antwort abgibt; er steht deshalb hinten.

    Greift keine Stufe, wird das gemeldet statt verschluckt: der Waechter ist
    dann wirkungslos, und ein wirkungsloser Waechter, von dem niemand weiss,
    ist schlimmer als gar keiner.
    """
    roh = getattr(antwort, "raw", None)
    if roh is None:
        return False
    for weg in (lambda: roh.shutdown(),
                lambda: roh._fp.fp.raw._sock.shutdown(socket.SHUT_RDWR),
                lambda: roh._connection.sock.shutdown(socket.SHUT_RDWR)):
        try:
            weg()
            return True
        except (AttributeError, ValueError, RuntimeError, OSError):
            continue
    return False


class _Verbindungsschacht:
    """Ablage fuer die Verbindung des gerade laufenden Abrufs.

    Der Kopf-Waechter legt sie an, bevor er die Anfrage stellt; urllib3 legt
    die Verbindung hinein, sobald es sie aus dem Pool nimmt. Damit gibt es
    einen Griff an den Socket, WAEHREND `requests.get` noch die Kopfzeilen
    liest — vorher gab es den erst danach.
    """

    def __init__(self):
        self.verbindung = None


# Je Faden einer: die Abrufe laufen parallel, teilen sich aber die Pools.
# `_get_conn` laeuft immer im anfragenden Faden, deshalb traegt genau dieser
# Faden den richtigen Schacht.
_schacht = threading.local()


def _melde_verbindung(verbindung):
    schacht = getattr(_schacht, "aktuell", None)
    if schacht is not None:
        schacht.verbindung = verbindung
    return verbindung


class _MeldenderHTTPPool(urllib3.HTTPConnectionPool):
    """`_get_conn` ist die einzige Stelle, an der urllib3 die Verbindung in
    die Hand nimmt — fuer eine frische wie fuer eine wiederverwendete."""

    def _get_conn(self, timeout=None):
        return _melde_verbindung(super()._get_conn(timeout))


class _MeldenderHTTPSPool(urllib3.HTTPSConnectionPool):
    def _get_conn(self, timeout=None):
        return _melde_verbindung(super()._get_conn(timeout))


class _MeldenderAdapter(requests.adapters.HTTPAdapter):
    """Haengt die meldenden Pools in EINE Sitzung ein.

    `pool_classes_by_scheme` ist seit urllib3 2.x ein Instanzattribut des
    PoolManagers (poolmanager.py, `__init__`). Deshalb wirkt der Eingriff nur
    auf unsere eigene Sitzung — kein Monkeypatch, keine Fernwirkung auf
    anderen Code im selben Prozess.
    """

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _MeldenderHTTPPool, "https": _MeldenderHTTPSPool}


def _sitzung() -> requests.Session:
    """Eine Sitzung je Abruf — genau wie `requests.get` es intern auch tut.

    Damit stellt sich die Frage nach Faden-Sicherheit einer geteilten Sitzung
    gar nicht erst, und die Verbindungen der parallelen Abrufe koennen sich
    nicht gegenseitig in den Schacht legen.
    """
    sitzung = requests.Session()
    adapter = _MeldenderAdapter()
    sitzung.mount("http://", adapter)
    sitzung.mount("https://", adapter)
    return sitzung


def _verbindung_zuklappen(verbindung) -> bool:
    """Klappt den Socket einer noch nicht beantworteten Verbindung zu.

    Einfacher als `_socket_zuklappen`: hier halten wir das Verbindungsobjekt
    selbst, und dessen `sock` ist oeffentlich. `None` heisst, dass der
    Verbindungsaufbau noch laeuft — der ist durch die Socket-Frist gedeckelt
    und braucht den Waechter nicht.
    """
    stecker = getattr(verbindung, "sock", None)
    if stecker is None:
        return False
    try:
        stecker.shutdown(socket.SHUT_RDWR)
        return True
    except OSError:
        return False


class _Waechter:
    """Gemeinsames Geruest beider Waechter: ein Timer ueber die Restfrist.

    Der Timer wird in JEDEM Fall abbestellt — sonst haelt jeder Abruf bis zum
    Ende seines Budgets einen Faden am Leben.

    `cancel()` hilft aber nur gegen einen Timer, der noch wartet. Ein bereits
    LAUFENDES `_zuschlagen` erreicht es nicht mehr, und genau dieser Fall
    tritt auf, wenn Lesetimeout und Frist zusammenfallen (beobachtet bei der
    Form "Server schweigt nach den Kopfzeilen"). Ohne die Sperre unten hatte
    das zwei Folgen: die Meldung beschuldigte urllib3, obwohl der Socket nur
    regulaer geschlossen war, und `ausgeloest` stand hinterher auf True — was
    die Pruefung hinter dem `with`-Block aus einer FERTIG gelesenen Seite
    eine Zeitueberschreitung machte. Eine stumm verlorene Quelle.
    """

    KLAGE = ""

    def __init__(self, frist: float):
        self._frist = frist
        self._timer: threading.Timer | None = None
        self._sperre = threading.Lock()
        self._fertig = False
        self.ausgeloest = False

    def __enter__(self):
        rest = max(0.0, self._frist - time.monotonic())
        self._timer = threading.Timer(rest, self._zuschlagen)
        self._timer.name = WAECHTER_FADEN_NAME
        self._timer.daemon = True
        self._timer.start()
        return self

    def _zuklappen(self) -> bool:
        raise NotImplementedError

    def _zuschlagen(self) -> None:
        with self._sperre:
            if self._fertig:
                return
            # Zuerst merken, dann handeln: der Lesevorgang darf danach mit
            # einer beliebigen Ausnahme abbrechen — der Aufrufer muss sie als
            # abgelaufene Zeit lesen koennen, nicht als Serverfehler.
            self.ausgeloest = True
            gegriffen = self._zuklappen()
        # Ausserhalb der Sperre: ein wirkungsloser Waechter, von dem niemand
        # weiss, ist schlimmer als gar keiner.
        if not gegriffen:
            print(self.KLAGE, file=sys.stderr, flush=True)

    def __exit__(self, *_) -> bool:
        with self._sperre:
            self._fertig = True
        if self._timer is not None:
            self._timer.cancel()
        return False


class _KopfWaechter(_Waechter):
    """Der Waechter fuer die Phase VOR dem Antwortobjekt.

    `_Fristwaechter` haengt an der Antwort und kann deshalb erst greifen,
    wenn `requests.get` zurueckgekehrt ist. Genau davor sitzt die Luecke: ein
    Server, der gueltige Kopfzeilen troepfelt, laeuft in keine der
    Socket-Fristen (jedes einzelne `recv` kommt rechtzeitig) und wurde allein
    von `http.client._MAXHEADERS` begrenzt — 100 Zeilen mal Tropfabstand.
    """

    KLAGE = ("[websuche] Kopf-Waechter fand keinen Socket — entweder stand "
             "die Verbindung noch nicht, oder urllib3 reicht sie nicht mehr "
             "ueber _get_conn heraus; die Kopfzeilen-Phase ist dann nur noch "
             "weich gedeckelt")

    def __init__(self, frist: float):
        super().__init__(frist)
        self._vorheriger = None
        self.schacht = _Verbindungsschacht()

    def __enter__(self) -> "_KopfWaechter":
        # Den vorherigen Schacht merken statt ihn beim Austritt auf None zu
        # setzen: der robots-Abruf laeuft heute vor diesem Block, aber eine
        # spaetere Umstellung soll den aeusseren Waechter nicht entwaffnen.
        self._vorheriger = getattr(_schacht, "aktuell", None)
        _schacht.aktuell = self.schacht
        return super().__enter__()

    def _zuklappen(self) -> bool:
        return _verbindung_zuklappen(self.schacht.verbindung)

    def __exit__(self, *_) -> bool:
        super().__exit__()
        _schacht.aktuell = self._vorheriger
        return False


class _Fristwaechter(_Waechter):
    """Schliesst bei Fristablauf den Socket unter einem blockierten Lesevorgang.

    Damit wird das Seitenbudget fuer den Rumpf zu einer harten Grenze, statt
    zu einer, die nur der gutwillige Server einhaelt.
    """

    KLAGE = ("[websuche] Fristwaechter fand keinen Socket — die "
             "urllib3-Attributkette in _socket_zuklappen passt nicht mehr; "
             "das Seitenbudget ist nur noch weich")

    def __init__(self, antwort, frist: float):
        super().__init__(frist)
        self._antwort = antwort

    def _zuklappen(self) -> bool:
        return _socket_zuklappen(self._antwort)


def _lies_gedeckelt(antwort, frist: float,
                    max_bytes: int) -> tuple[bytes, str | None]:
    """Liest stroemend bis zur Groessen- oder Zeitgrenze.

    Gelesen wird mit `raw.read1()` statt mit `iter_content()`. Der
    Unterschied ist der ganze Punkt: `iter_content(n)` kehrt erst zurueck,
    wenn n Bytes beisammen sind — bei 8 Bytes alle 20 ms sind das fuer 16 KB
    ueber 40 Sekunden, und die Fristpruefung zwischen den Stuecken kommt in
    dieser Zeit kein einziges Mal an die Reihe (gemessen: 30 s bei 1 s
    Budget). `read1()` gibt zurueck, was da ist, sobald etwas da ist — erst
    damit wird die Fristpruefung wirksam.

    Der Groessendeckel kappt nur (die 12.000 Zeichen Fliesstext stecken laengst
    in den ersten Bytes); die Zeitgrenze ist ein Fehler, weil ein
    troepfelnder Server sonst das Budget aller anderen Quellen mitverbrennt.
    """
    rumpf = bytearray()
    while True:
        stueck = antwort.raw.read1(LESE_STUECK, decode_content=True)
        if not stueck:
            return bytes(rumpf), None
        rumpf.extend(stueck)
        if len(rumpf) >= max_bytes:
            return bytes(rumpf[:max_bytes]), None
        if time.monotonic() >= frist:
            return bytes(rumpf), "abgelaufen"


@dataclass(frozen=True)
class RohAntwort:
    """Was der gemeinsame Kern zurueckgibt. `status == 0` heisst: es kam gar
    keine Antwort zustande (Netzfehler, Zeit abgelaufen oder verweigertes
    Ziel) — was davon, steht in `fehler` bzw. `zeit_aus`."""
    status: int = 0
    # CaseInsensitiveDict, nicht dict — HTTP-Feldnamen sind case-insensitiv.
    kopf: "CaseInsensitiveDict | None" = None
    rumpf: bytes = b""
    fehler: str | None = None
    zeit_aus: bool = False


def hole_roh(url: str, timeout: float, *, accept: str, max_bytes: int,
             zielpruefung=None) -> RohAntwort:
    """Ein gedeckelter Abruf ohne Textextraktion.

    Fuer Aufrufer, die den rohen Rumpf brauchen statt Fliesstext — heute die
    JSON-Antwort der Suchquelle. Sie bekommen damit dasselbe harte
    Gesamtbudget, denselben Groessendeckel und dieselbe Sprungkontrolle wie
    der Seitenabruf, ohne dass die Logik ein zweites Mal entsteht.

    `zielpruefung` ist Pflicht in dem Sinne, dass ohne Angabe die strenge
    `pruefe_ziel` gilt. Wer einen Hausdienst abruft, gibt ausdruecklich
    `pruefe_lokales_ziel` an — abschalten laesst sie sich nicht.
    """
    return _hole_gedeckelt(url, time.monotonic() + timeout, accept=accept,
                           max_bytes=max_bytes, zielpruefung=zielpruefung)


def _hole_gedeckelt(url: str, frist: float, *, accept: str, max_bytes: int,
                    vor_abruf=None, kopf_pruefung=None,
                    zielpruefung=None) -> RohAntwort:
    """Gemeinsamer Kern von Seiten- und robots-Abruf.

    Es gab diese Logik einmal zweimal: streng fuer die Seite, mit blankem
    `requests.get()` fuer die robots.txt. Genau in der zweiten Kopie fehlten
    Zielpruefung, Sprungkontrolle und Deckel — eine robots.txt, die auf
    127.0.0.1:5678 umleitete, loeste eine echte Anfrage an n8n aus. Eine
    zweite, leicht abweichende Kopie derselben Sicherheitslogik ist der Grund,
    warum solche Luecken entstehen; deshalb steht sie jetzt nur noch hier.

    Zugesichert wird:
    - `pruefe_ziel()` vor jedem Verbindungsaufbau UND vor jedem Sprung,
    - `allow_redirects=False` mit eigener, gedeckelter Sprungkontrolle,
    - stroemendes Lesen mit Groessendeckel und Fristpruefung je Leseschritt,
    - ein Socket-Timeout von `min(Restbudget, SOCKET_FRIST)`, je Sprung
      einmal gesetzt,
    - ein Socket-Waechter ueber den Rumpf, der die Frist hart durchsetzt,
      auch wenn die wartende Schleife unter `read1` liegt,
    - ein Kopf-Waechter ueber die Kopfzeilen-Phase, der dasselbe eine Phase
      frueher leistet — dort gibt es noch kein Antwortobjekt, wohl aber die
      Verbindung (siehe `_Verbindungsschacht`).

    `vor_abruf(ziel)` darf jeden Sprung mit einem Grund ablehnen (die Seite
    haengt dort ihre robots.txt-Pruefung ein). `kopf_pruefung(antwort)` darf
    nach den Kopfzeilen entscheiden, dass der Rumpf gar nicht erst gelesen
    wird — so muss ein 500-MB-PDF nicht gelesen werden, um als PDF zu gelten.
    """
    with _sitzung() as sitzung:
        return _hole_ueber(sitzung, url, frist, accept=accept,
                           max_bytes=max_bytes, vor_abruf=vor_abruf,
                           kopf_pruefung=kopf_pruefung,
                           zielpruefung=zielpruefung or pruefe_ziel)


def _hole_ueber(sitzung, url: str, frist: float, *, accept: str,
                max_bytes: int, vor_abruf=None, kopf_pruefung=None,
                zielpruefung=None) -> RohAntwort:
    """Der Rumpf von `_hole_gedeckelt`, mit der Sitzung als Mittel.

    Eigene Funktion nur, damit die Sitzung genau einen `with`-Block hat und
    dieser Ablauf nicht um eine Einrueckungsebene wandert.
    """
    aktuell = url
    for _sprung in range(MAX_WEITERLEITUNGEN + 1):
        rest = frist - time.monotonic()
        if rest <= 0:
            return RohAntwort(zeit_aus=True)
        # Zuerst die Frist, dann die Aufloesung: die Zielpruefung loest Namen
        # auf und bekommt dafuer ausdruecklich nur das, was vom Budget uebrig
        # ist. Sie gilt auch fuer jedes Weiterleitungsziel.
        grund = zielpruefung(aktuell, aufloese_frist=min(rest, DNS_FRIST))
        if grund:
            return RohAntwort(fehler=grund)

        rest = frist - time.monotonic()
        if rest <= 0:
            return RohAntwort(zeit_aus=True)
        if vor_abruf is not None:
            grund = vor_abruf(aktuell)
            if grund:
                return RohAntwort(fehler=grund)

        rest = frist - time.monotonic()
        if rest <= 0:
            return RohAntwort(zeit_aus=True)
        schritt = min(rest, SOCKET_FRIST)
        with _KopfWaechter(frist) as kopfwaechter:
            try:
                antwort = sitzung.get(
                    aktuell, timeout=(schritt, schritt),
                    headers={"User-Agent": USER_AGENT, "Accept": accept},
                    allow_redirects=False, stream=True)
            except requests.exceptions.Timeout:
                return RohAntwort(zeit_aus=True)
            except requests.exceptions.RequestException as e:
                # Wie beim Rumpf: hat der Waechter zugeschlagen, ist der
                # abgerissene Socket unsere eigene Wirkung und kein
                # Serverfehler.
                if kopfwaechter.ausgeloest:
                    return RohAntwort(zeit_aus=True)
                return RohAntwort(fehler=f"Abruf fehlgeschlagen: {e}")
            # Ein zugeklappter Socket beendet den Kopfblock auch ohne
            # Ausnahme: `http.client` liest bis zum Dateiende und haelt die
            # bis dahin gelesenen Zeilen fuer den ganzen Kopf. Ohne diese
            # Pruefung ginge eine halbe Antwort als vollstaendige durch.
            if kopfwaechter.ausgeloest:
                antwort.close()
                return RohAntwort(zeit_aus=True)

        if antwort.status_code in WEITERLEITUNGS_CODES:
            ziel = antwort.headers.get("Location")
            antwort.close()
            if not ziel:
                return RohAntwort(
                    status=antwort.status_code,
                    fehler=f"Weiterleitung (HTTP {antwort.status_code}) "
                           f"ohne Zieladresse")
            # Jedes neue Ziel geht oben wieder durch pruefe_ziel().
            aktuell = urljoin(aktuell, ziel)
            continue
        break
    else:
        return RohAntwort(
            fehler=f"Mehr als {MAX_WEITERLEITUNGEN} Weiterleitungen — Kette "
                   f"abgebrochen (letztes Ziel: {aktuell})")

    # CaseInsensitiveDict statt dict: HTTP-Feldnamen sind case-insensitiv
    # (RFC 9110, 5.1), und `dict(antwort.headers)` warf genau diese Eigenschaft
    # weg. Ein Server, der `content-type:` klein schreibt — voellig legal und
    # verbreitet —, kam beim zweiten Formatdurchgang in `hole_text` als
    # "ohne Content-Type" an; bei UTF-16-Text hiess das "Binaerinhalt" und
    # kostete still eine Quelle.
    kopf = CaseInsensitiveDict(antwort.headers)
    if kopf_pruefung is not None:
        grund = kopf_pruefung(antwort)
        if grund:
            antwort.close()
            return RohAntwort(status=antwort.status_code, kopf=kopf,
                              fehler=grund)

    # `antwort.close()` steht AUSSERHALB des Waechter-Blocks. Innerhalb lag
    # ein Fenster zwischen dem regulaeren Schliessen des Sockets und dem
    # Abbestellen des Timers: feuerte der Waechter darin, fand er nichts mehr
    # zum Zuklappen, beschuldigte urllib3 in der Meldung — und setzte
    # `ausgeloest`, was die Pruefung unten aus einer FERTIG gelesenen Seite
    # eine Zeitueberschreitung machte. Beim Nachmessen der Form "Server
    # schweigt nach den Kopfzeilen" trat das in etwa jedem zwanzigsten Abruf
    # auf; die Sperre im Waechter allein reicht dagegen nicht.
    try:
        with _Fristwaechter(antwort, frist) as waechter:
            try:
                rumpf, zeitfehler = _lies_gedeckelt(antwort, frist, max_bytes)
            # `raw.read1()` geht an `requests` vorbei und wirft deshalb die
            # rohen urllib3-Ausnahmen, die `iter_content()` sonst uebersetzt
            # haette.
            except (requests.exceptions.Timeout,
                    urllib3.exceptions.TimeoutError):
                return RohAntwort(status=antwort.status_code, kopf=kopf,
                                  zeit_aus=True)
            except (requests.exceptions.RequestException,
                    urllib3.exceptions.HTTPError, OSError) as e:
                # Hat der Waechter zugeschlagen, ist dieser Fehler unsere
                # eigene Wirkung — ein abgerissener Socket. Ihn als
                # Serverfehler zu melden waere eine Falschaussage im Ergebnis.
                if waechter.ausgeloest:
                    return RohAntwort(status=antwort.status_code, kopf=kopf,
                                      zeit_aus=True)
                return RohAntwort(status=antwort.status_code, kopf=kopf,
                                  fehler=f"Abruf fehlgeschlagen: {e}")
    finally:
        antwort.close()
    # Der Waechter zaehlt auch dann als Zeitueberschreitung, wenn das
    # Zuklappen zu einem sauberen Dateiende statt zu einer Ausnahme fuehrt
    # (chunked): der Rumpf ist dann unvollstaendig, ohne dass es jemand saehe.
    if zeitfehler or waechter.ausgeloest:
        return RohAntwort(status=antwort.status_code, kopf=kopf, rumpf=rumpf,
                          zeit_aus=True)
    return RohAntwort(status=antwort.status_code, kopf=kopf, rumpf=rumpf)


def _seiten_kopf_pruefung(antwort) -> str | None:
    if antwort.status_code >= 400:
        return f"HTTP {antwort.status_code}"
    # Erst der Header — ein 500-MB-PDF muss nicht gelesen werden, um als
    # PDF erkannt zu werden.
    return _formatfehler(antwort.headers.get("Content-Type", ""), b"")


def hole_text(url: str, max_zeichen: int = 12000, timeout: float = 10.0,
              robots: "RobotsSpeicher | None" = None) -> AbrufErgebnis:
    """Holt eine Seite und gibt ihren Fliesstext zurueck.

    `timeout` ist das Budget dieser Seite — Namensaufloesung, robots.txt,
    alle Weiterleitungen und der Rumpf zusammen. Wie hart dieses Budget
    wirklich ist und wo es sich brechen laesst, steht im Modul-Docstring
    unter "WAS DAS ZEITBUDGET WIRKLICH LEISTET" — mit Messwerten.
    """
    frist = time.monotonic() + timeout
    zeit_aus = AbrufErgebnis(fehler=f"Zeit überschritten nach {timeout}s")

    def robots_tor(ziel: str) -> str | None:
        rest = frist - time.monotonic()
        budget = min(max(0.0, rest), ROBOTS_TIMEOUT)
        erlaubt = (robots.darf(ziel, budget) if robots is not None
                   else darf_abrufen(ziel, timeout=budget))
        return None if erlaubt else "Abruf laut robots.txt nicht erlaubt"

    roh = _hole_gedeckelt(url, frist, accept=ACCEPT,
                          max_bytes=MAX_RUMPF_BYTES, vor_abruf=robots_tor,
                          kopf_pruefung=_seiten_kopf_pruefung)
    if roh.zeit_aus:
        return zeit_aus
    if roh.fehler:
        return AbrufErgebnis(fehler=roh.fehler)

    typ = (roh.kopf or {}).get("Content-Type", "")
    rumpf = roh.rumpf
    # Zweiter Durchgang: ohne Content-Type entscheidet der Rumpf.
    fehler = _formatfehler(typ, rumpf)
    if fehler:
        return AbrufErgebnis(fehler=fehler)

    try:
        # Bytes statt str an bs4: dessen Encoding-Erkennung (UnicodeDammit)
        # trifft es besser als requests' ISO-8859-1-Default fuer text/html
        # ohne charset — sonst stehen deutsche Umlaute als Moji im Zitat.
        text = kappe(extrahiere_text(rumpf), max_zeichen)
    except Exception as e:
        return AbrufErgebnis(fehler=f"Text-Extraktion fehlgeschlagen: {e}")
    if not text:
        return AbrufErgebnis(fehler="Seite enthielt keinen lesbaren Text")
    return AbrufErgebnis(text=text)
