# Privater Fernzugriff

Das Dashboard bleibt passwortgeschützt. Für unterwegs zuerst das private VPN verbinden, danach die Pi-Adresse im Browser öffnen. Für Kamerablick und SSH keine öffentliche Router-Portfreigabe einrichten.

## Vorhandenes VPN verwenden

Wenn bereits ein privates WireGuard- oder anderes Heimnetz-VPN vorhanden ist, dieses verwenden. Vom Laptop über ein fremdes Netz verbinden und prüfen, ob die Pi-Adresse erreichbar ist. Das VPN muss den Weg zum Heimnetz des Pi erlauben. Erst der erfolgreiche Dashboard-Aufruf und die SSH-Anmeldung bestätigen den Fernzugriff; eine aktive VPN-Anzeige allein reicht nicht.

## Alternative ohne vorhandenes VPN: Tailscale

Dies ist eine vorbereitete Option, noch keine eingerichtete Verbindung. Tailscale muss auf Pi und Wartungsgerät mit deinem Konto eingerichtet werden. Verwende nur eigene beziehungsweise ausdrücklich berechtigte Geräte. Verteile keine Anmeldelinks oder Zugangsschlüssel im Chat oder Repository.

Auf dem eingeschalteten Pi Tailscale nach der [offiziellen Linux-Anleitung](https://tailscale.com/docs/install/linux) installieren. Raspberry Pi OS wird unterstützt; dort sind auch die Paketquellen für eine manuelle Installation verlinkt. Anschließend:

```sh
sudo tailscale up
tailscale ip -4
tailscale status
```

Den angezeigten Anmeldelink selbst öffnen und den Pi dem eigenen privaten Netz hinzufügen. Auf dem Laptop oder Smartphone den [offiziellen Client](https://tailscale.com/download) installieren und dasselbe private Netz verwenden. Die Zugriffsregeln auf die vorgesehenen Wartungsgeräte und den Pi begrenzen. Für diesen Ablauf werden weder Subnetzfreigabe noch Exit Node oder Funnel benötigt.

Die von `tailscale ip -4` angezeigte Pi-Adresse im Browser mit Port 8088 öffnen, beispielsweise `http://100.x.y.z:8088`. Die Platzhalteradresse durch die tatsächliche Adresse ersetzen. Bei einem anderen Kamerablick-Port diesen verwenden. Der Zugriff funktioniert bei `BIND=0.0.0.0`; bei ausschließlich lokaler Bindung den vorhandenen SSH-Tunnel über die VPN-Adresse nutzen. Eine aktive Geräte-Firewall muss den vorgesehenen VPN-Zugriff zulassen.

Normaler SSH-Zugang mit dem vorhandenen Pi-Benutzer und eigenem Schlüssel bleibt möglich. Die zusätzliche Funktion Tailscale SSH ist dafür nicht erforderlich. VPN und Tailscale werden außerhalb des Dashboard-Containers betrieben und separat aktualisiert.

## Vom fremden Netz abnehmen

1. Laptop oder Smartphone vom Heim-WLAN trennen, zum Beispiel einen Mobilfunk-Hotspot verwenden.
2. VPN verbinden. Dashboard über die VPN-Adresse öffnen und mit dem vorhandenen Dashboard-Passwort anmelden.
3. Kamera- und Versionsstatus prüfen. Eine erfolgreiche Anmeldung beweist noch keine laufende Wiedergabe am TV.
4. SSH über die VPN-Adresse prüfen und im Projektordner `python3 pi/doctor.py` ausführen. Keine `.env` oder privaten Konfigurationsdateien übertragen.
5. Pi regulär neu starten und VPN, Dashboard und SSH erneut prüfen. Den Neustart nur durchführen, wenn gerade keine Installation oder Aktualisierung läuft.
6. Vor dem dauerhaften Einsatz die Gerätefreigaben und die erneute Anmeldung bei ablaufenden VPN-Geräteschlüsseln festlegen. [Hinweise des Herstellers zum Schlüsselablauf](https://tailscale.com/docs/install/linux#disable-key-expiry) beachten; das Abschalten des Ablaufs verändert den Schutz des Zugangs.

Ergebnis, Datum und verwendeten Zugang lokal festhalten. Der Fernzugriff gilt erst nach diesem Test als verifiziert. Zugangswerte und private Netzwerkdaten gehören nicht in öffentliche Issues.
