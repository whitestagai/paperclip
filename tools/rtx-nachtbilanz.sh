#!/bin/bash
# Nachtbilanz nach der RTX-Umstellung vom 22.08.2026.
#
# Beantwortet drei Fragen:
#   1. Sind die naechtlichen PII-Classifier-Timeouts verschwunden?
#      (vorher 45-67 % zwischen 20 und 2 Uhr, tagsueber 2-5 %)
#   2. Wie hat sich die Fehlerquote der Flotte entwickelt?
#   3. Laufen die Modelle noch da, wo sie hingehoeren?
#
# Aufruf: bash ~/.paperclip/scripts/rtx-nachtbilanz.sh
set -uo pipefail
PSQL=(psql -h localhost -p 54329 -U paperclip -d paperclip)
export PGPASSWORD=paperclip
LMS="$HOME/.lmstudio/bin/lms"

echo "================================================================"
echo " RTX-NACHTBILANZ   $(date '+%Y-%m-%d %H:%M')"
echo " Umstellung war: 2026-08-22 ca. 10:15"
echo "================================================================"

echo
echo "1. PII-CLASSIFIER — Anteil im 60-s-Timeout, nach Stunde"
echo "   (Primaer = gemma-4-12b-qat auf der RTX. Nachts frueher 45-67 %.)"
python3 - <<'EOF'
import json, datetime, collections, os
p = os.path.expanduser('~/Library/Logs/pii-proxy/out.log')
if not os.path.exists(p):
    print("   Log nicht gefunden:", p); raise SystemExit
grenze = datetime.datetime.now() - datetime.timedelta(hours=24)
b = collections.defaultdict(lambda: [0, 0, 0.0])
with open(p, errors='ignore') as f:
    for line in f:
        if '"request completed"' not in line: continue
        try: d = json.loads(line)
        except Exception: continue
        t = datetime.datetime.fromtimestamp(d['time'] / 1000)
        if t < grenze: continue
        r = d.get('responseTime', 0)
        e = b[t.hour]; e[0] += 1; e[2] += r
        if r > 50000: e[1] += 1
if not b:
    print("   keine Anfragen in den letzten 24 h")
else:
    print(f"   {'Std':>4} {'Reqs':>6} {'>50s':>6} {'Anteil':>8} {'Ø ms':>9}   Nacht?")
    for h in sorted(b):
        c, s, tot = b[h]
        nacht = "NACHT" if (h >= 20 or h < 2) else ""
        print(f"   {h:02d}:00 {c:6} {s:6} {s/c*100:7.1f}% {tot/c:9.0f}   {nacht}")
    nacht = [(c, s) for h, (c, s, _) in b.items() if h >= 20 or h < 2]
    tag   = [(c, s) for h, (c, s, _) in b.items() if 2 <= h < 20]
    for label, rows in (("NACHT (20-02)", nacht), ("Tag  (02-20)", tag)):
        if rows:
            C = sum(c for c, _ in rows); S = sum(s for _, s in rows)
            print(f"   => {label}: {S}/{C} = {S/C*100:.1f} % im Timeout")
EOF

echo
echo "2. FLOTTE — Fehlerklassen seit der Umstellung"
"${PSQL[@]}" -tAF' | ' -c "
select case when error is null then 'ok'
            when error like '%Context size%'   then 'CTX ueberschritten'
            when error like '%unloaded%'       then 'Modell entladen'
            when error like '%keepalive%'      then 'LM-Link keepalive'
            when error like '%timed out%'      then 'Timeout'
            when error like '%nicht erreichbar%' then 'LM Studio weg'
            when error like '%ax iterations%'  then 'max_iterations'
            when error like '%Cancelled%'      then 'abgebrochen (kein LLM-Fehler)'
            else left(replace(error,chr(10),' '),40) end as klasse,
       count(*)
from heartbeat_runs
where created_at > timestamp '2026-08-22 10:15:00'
group by 1 order by 2 desc;" 2>&1 | sed 's/^/   /'

echo
echo "   Quote pro Tag zum Vergleich (Fehler/Laeufe):"
"${PSQL[@]}" -tAF' | ' -c "
select to_char(created_at,'MM-DD') as tag,
       count(*) filter (where error is not null)||'/'||count(*) as fehler_von,
       round(100.0*count(*) filter (where error is not null)/greatest(count(*),1),1)||' %' as quote
from heartbeat_runs where created_at > now() - interval '5 days'
group by 1 order by 1;" 2>&1 | sed 's/^/   /'

echo
echo "3. NACHTLAEUFE — lief die Flotte zwischen 22 und 8 Uhr durch?"
"${PSQL[@]}" -tAF' | ' -c "
select to_char(hr.created_at,'HH24:MI') as t, a.name,
       case when hr.error is null then 'ok' else left(replace(hr.error,chr(10),' '),45) end
from heartbeat_runs hr join agents a on a.id=hr.agent_id
where hr.created_at > now() - interval '16 hours'
  and (extract(hour from hr.created_at) >= 22 or extract(hour from hr.created_at) < 8)
order by hr.created_at desc limit 20;" 2>&1 | sed 's/^/   /'

echo
echo "4. MODELLE — liegen sie noch richtig?"
if [ -x "$LMS" ]; then
  "$LMS" ps 2>/dev/null | grep -iE "IDENT|31b|12b|qwen3.6" | sed 's/^/   /'
  echo "   Erwartet: gemma4-31b-it + gemma-4-12b-qat auf RTX Pro 6000 (beide ohne TTL),"
  echo "             gemma-4-31b-it-mlx auf MacbookM5Mx128 als Fallback (ohne TTL)."
else
  echo "   lms CLI nicht gefunden unter $LMS"
fi

echo
echo "5. AGENTEN — Zuordnung unveraendert?"
"${PSQL[@]}" -tAF' | ' -c "
select 'Primaer auf RTX: '||count(*) from agents where coalesce(adapter_config->>'model',adapter_config->>'defaultModel')='gemma4-31b-it'
union all select 'cheap auf RTX:   '||count(*) from agents where adapter_config->'modelProfiles'->'cheap'->'adapterConfig'->>'model'='gemma4-31b-it'
union all select 'Fallback MLX:    '||count(*) from agents where adapter_config->>'fallbackModel'='gemma-4-31b-it-mlx';" 2>&1 | sed 's/^/   /'
echo "   Erwartet: 22 / 24 / 14"
echo
echo "================================================================"
