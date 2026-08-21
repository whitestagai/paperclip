#!/bin/zsh
# DMARC-Wächter für oubifb.hostedoffice.ag (WHI-2857)
# Prüft alle 15 Min; meldet EINMAL per Telegram (JARVIS) und schaltet sich dann ab.
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin

DIR="$HOME/.paperclip/scripts/dmarc-watch"
MARKER="$DIR/.done"
LOG="$DIR/watch.log"
DOMAIN="_dmarc.oubifb.hostedoffice.ag"
CHAT="8311805232"
ENVF="$HOME/.paperclip/voice-echo-bot.env"

[ -f "$MARKER" ] && exit 0

# Gegen mehrere öffentliche Resolver prüfen (Propagation-tolerant)
REC=""
for NS in 1.1.1.1 8.8.8.8 9.9.9.9; do
  R=$(dig +short TXT "$DOMAIN" @"$NS" 2>/dev/null | tr -d '"' | tr '\n' ' ')
  [ -n "$R" ] && REC="$R" && break
done

echo "$(date '+%Y-%m-%d %H:%M:%S') check -> ${REC:-<leer>}" >> "$LOG"

if print -r -- "$REC" | grep -qi "v=DMARC1"; then
  TOKEN=$(python3 -c "import os;print([l.split('=',1)[1].strip().strip('\"').strip(chr(39)) for l in open(os.path.expanduser('$ENVF')) if l.strip().replace('export ','').startswith('TELEGRAM_BOT_TOKEN=')][0])")
  MSG="✅ DMARC ist jetzt LIVE für oubifb.hostedoffice.ag

$REC

Deine Mails über die HostedOffice-Adresse passieren ab jetzt die DMARC-Prüfung (die wfbb.de-Ablehnung sollte weg sein).

— automatischer DMARC-Wächter, WHI-2857"
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" \
       --data-urlencode "chat_id=${CHAT}" \
       --data-urlencode "text=${MSG}" >> "$LOG" 2>&1
  echo "$(date '+%Y-%m-%d %H:%M:%S') >>> GEFUNDEN, Telegram gesendet, Wächter deaktiviert." >> "$LOG"
  touch "$MARKER"
  launchctl bootout gui/$(id -u)/de.whitestag.dmarc-watch 2>/dev/null \
    || launchctl unload "$HOME/Library/LaunchAgents/de.whitestag.dmarc-watch.plist" 2>/dev/null
fi
exit 0
