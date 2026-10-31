"""Restore a local settings backup inside the dashboard container."""
import json, sys
sys.path.insert(0,'/app')
import server
backup=json.load(sys.stdin)
# Read all input before writing. Not a schema migration tool.
config=backup['config'];protect=backup.get('protect',{})
if not isinstance(config,dict) or not isinstance(protect,dict): raise SystemExit('Ungültiges Backup')
server.save('config.json',config)
server.save('protect.json',protect)
print('Lokale Einstellungen wiederhergestellt. Im Dashboard erneut speichern, um den Pi-Dienst abzugleichen.')
