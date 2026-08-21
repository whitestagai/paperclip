// Read-only-Mirror Claras SMB-Vault -> lokale Kopie, via node (hat SMB/FDA-Zugriff,
// im Gegensatz zu einem reinen zsh/rsync-launchd-Job). Nur *.md. Nie zurückschreiben.
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const SRC = '/Volumes/homes/cw/Obsidian/Clara-Vault/';
const DST = path.join(os.homedir(), '.paperclip/clara-vault-mirror/');
const LOG = path.join(os.homedir(), '.paperclip/logs/clara-mirror-sync.log');
const ts = () => new Date().toLocaleString('sv-SE', { timeZone: 'Europe/Berlin' });
const logline = (m) => { try { fs.appendFileSync(LOG, ts()+'  '+m+'\n'); } catch(e){} };
// Quelle lesbar? sonst abbrechen (Mirror unangetastet lassen)
try { fs.readdirSync(SRC + 'Kontakte'); }
catch (e) { logline('ABBRUCH: Quelle nicht lesbar ('+e.code+') — Mirror unveraendert.'); process.exit(0); }
const r = spawnSync('rsync', ['-a','--delete',
  '--include=*/','--include=*.md','--exclude=*',
  '--exclude=.obsidian/','--exclude=.trash/','--exclude=.git/','--exclude=.claude/','--exclude=.claudian/',
  SRC, DST], { encoding: 'utf8' });
let n = 0;
try { n = spawnSync('bash',['-c',"find '"+DST+"' -name '*.md' | wc -l"],{encoding:'utf8'}).stdout.trim(); } catch(e){}
if (r.status === 0) logline('OK (node): '+n+' .md gespiegelt.');
else logline('rsync rc='+r.status+' via node: '+((r.stderr||'').slice(0,300)));
