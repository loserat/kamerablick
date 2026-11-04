# Updates in der Oberfläche

Auf dem Pi unter **Wartung** zeigt Kamerablick die installierte und die aktuelle stabile GitHub-Version. **Jetzt aktualisieren → Sichern und aktualisieren** startet den bestätigten Auftrag auf dem Pi. Die Kameraeinrichtung und Zugangswerte bleiben erhalten.

## Vorhandene Installation einmalig umstellen

Versionen bis einschließlich v0.1.3 haben noch keinen Updateknopf und keinen unabhängigen Wartungsdienst. Deshalb ist für den Übergang einmalig SSH nötig. Es wird keine zweite Installation angelegt.

Als bisheriger Kamerablick-Benutzer auf dem Pi:

```sh
cd ~/kamerablick
git fetch origin --tags
git checkout v0.1.8
sudo loginctl enable-linger "$USER"
python3 pi/activate_browser_updates.py --image ghcr.io/loserat/kamerablick:v0.1.8
```

Git erhält lokale Daten und verweigert einen Wechsel, der geänderte Quelldateien überschreiben würde. Bei einer solchen Meldung die eigenen Änderungen zuerst prüfen. Kein `git reset --hard` und keine Neuinstallation mit gelöschten Daten verwenden.

Der Übergang aktualisiert eine ältere verwaltete Installation über ihren Sicherungs- und Rückweg, übernimmt die zur Image-Version gehörenden Pi-Dateien und aktiviert anschließend `oma-tv-maintenance.service`. Passwort, Kamera, Datenvolume und die bestehende LAN-/Localhost-Einstellung bleiben erhalten. Die dauerhafte Benutzerfreigabe sorgt dafür, dass Updateaufträge auch ohne aktive SSH- oder Desktop-Anmeldung weiterlaufen.

Danach die Oberfläche neu laden und mit dem bisherigen Dashboard-Passwort anmelden. Unter **Wartung** muss „Bereit für Updates aus der Oberfläche“ stehen. Ist ein Fehler aufgetreten, dessen Meldung prüfen und den Übergang erneut ausführen; keine Konfiguration löschen.

## Vorhandene Installation erneut einrichten

Wenn ein älterer Updateversuch nicht abgeschlossen wurde, kann der Neuinstallationshelfer aus dem aktuellen `main`-Quellstand die vorhandene Installation erneut einrichten:

```sh
sudo loginctl enable-linger "$USER"
python3 pi/reinstall.py --image ghcr.io/loserat/kamerablick:v0.1.4
```

Für einen anschließenden Browser-Updatetest ist v0.1.4 als Ausgangsversion vorgesehen; danach die neuere angebotene Version unter Wartung installieren. Für eine direkte Einrichtung auf v0.1.8 diese Image-Version angeben.

Der Helfer benötigt einen erreichbaren bisherigen Dashboard-Container für die Datensicherung. Er sichert Einstellungen, Zugangswerte, bisherige Dienstdateien und das tatsächlich verwendete Image unter `backups/neuinstallation-…`. Einen offenen Updatezustand und den letzten Auftrag verschiebt er in diese private Sicherung. Danach richtet er Container und verwaltete Pi-Dienste aus dem gewählten offiziellen Image erneut ein. Das bestehende Docker-Datenvolume, Passwort und die Kameraeinrichtung bleiben erhalten. Er löscht keine Datenvolumes und räumt keine alten Sicherungen auf.

Der Vorgang meldet Erfolg erst nach der Prüfung von Dashboard, Wartungsdienst und Pi-Dienst. Schlägt diese Prüfung fehl, bleibt die Sicherung erhalten und die Neuinstallation gilt als unvollständig; es wird keine automatische Rückkehr aus diesem Neuinstallationsweg zugesagt. Die Fehlermeldung und den ausgegebenen Sicherungspfad zur weiteren Diagnose aufbewahren. Raspberry Pi OS und eigene fremde Dienstdateien werden nicht ersetzt.

## Neue Pi-Installation

Vor dem normalen Installer einmalig ausführen:

```sh
sudo loginctl enable-linger "$USER"
```

Der Installer richtet den eigenen Wartungsdienst automatisch ein. Er läuft unabhängig von den grafischen Diensten und ist ausschließlich auf `127.0.0.1:8093` erreichbar. Das Dashboard bleibt ein unprivilegierter Container ohne Docker-Socket.

## Korrektur des Dienststarts bis v0.1.5

Die bisherigen Installer haben den Pfad in `EnvironmentFile=` fälschlich in Anführungszeichen geschrieben. systemd interpretiert diese Einstellung als einzelnen absoluten Pfad und ignoriert die so zitierte Datei. Dadurch fehlen `AGENT_TOKEN` und weitere Einstellungen beim regulären Start; Meldungen wie „Lokaler Wartungsschlüssel fehlt“ sind die Folge. Ein direkt über `systemd-run` mit unzitiertem Pfad gestarteter Dienst konnte hingegen funktionieren. Ab v0.1.6 erzeugt der Installer den korrekten Ladepfad für Wartung, Pi-Dienst und TV-Browser. Die Tests prüfen die alten und neuen Dateien zusätzlich mit dem echten systemd-Parser.

Bei einem bereits laufenden v0.1.4-Dashboard den korrigierten Installer aus v0.1.8 verwenden, um die Dienstdateien erneut einzurichten. Dabei kann das vorhandene Image beibehalten werden:

```sh
cd ~/kamerablick
git fetch origin --tags
git checkout v0.1.8
python3 pi/install.py --install --image ghcr.io/loserat/kamerablick:v0.1.4
systemctl --user start oma-tv-session.target
```

Anschließend Dienstbereitschaft im Dashboard prüfen und die angebotene neuere Version über Wartung installieren. Vorhandener Schlüssel, Dashboard-Passwort, Datenvolume und Kameraeinrichtung bleiben erhalten. Es ist keine Erzeugung oder Veröffentlichung neuer Zugangswerte erforderlich.

## Eine neue Version installieren

1. **Wartung** öffnen. Die Versionsprüfung läuft dort automatisch beziehungsweise über **Version prüfen**. Versionshinweise stehen unter **Versionshinweise**.
2. **Jetzt aktualisieren** wählen. Der Dialog nennt die installierte und die angebotene Version.
3. **Sichern und aktualisieren** bestätigen. Nur veröffentlichte stabile Kamerablick-Versionen werden akzeptiert.
4. Den Fortschritt abwarten. Der Auftrag läuft als eigener Pi-Prozess auch dann weiter, wenn der Browser geschlossen oder das Dashboard neu gestartet wird.
5. Nach dem Neustart bei Bedarf erneut mit dem bisherigen Dashboard-Passwort anmelden. Kamera, TV und Taster zusätzlich am Gerät prüfen.

Der sichtbare Fortschritt zeigt die tatsächlichen Schritte: Herunterladen, Sicherung, Installation, Startprüfung oder Wiederherstellung. Er zeigt keine geschätzten Download-Prozentwerte. Eine begrenzte Lesefreigabe erhält den Statuszugriff nach einem Dashboard-Neustart; sie erlaubt keine Einstellungen oder weiteren Updates.

Ab v0.1.5 zeigt **Letzter Updateversuch** nach Abschluss zusätzlich den Versionswechsel, das Ergebnis und den Zeitpunkt in deutscher Zeit an. Die Anzeige stammt aus dem gespeicherten Pi-Auftrag und bleibt nach erneuter Anmeldung oder Neuladen erhalten. Ein fehlgeschlagenes Update wird ausdrücklich als Fehler oder Wiederherstellung angezeigt. Sobald ein neuer Auftrag läuft, wird dessen Fortschritt angezeigt; es wird keine Liste älterer Aufträge geführt.

Im Laptop-Heimtest werden keine Pi-Updates installiert. Auch Vorschauversionen, andere Containerquellen und ein Zurücksetzen auf beliebige alte Versionen sind über diesen Knopf nicht vorgesehen. Für den normalen Updateweg gilt die feste Quelle `loserat/kamerablick`.

## Sicherung, Fehler und Stromausfall

Vor dem Umschalten werden `.env`, die JSON-Einstellungen im Datenvolume, der lokale Pi-Zustand und die bisherige Laufzeit gesichert. Das tatsächlich bisherige Container-Image bleibt als Rückfallimage erhalten. Die Startprüfung kontrolliert Dashboard und Wartungsdienst sowie bei aktiver TV-Sitzung zusätzlich den Pi-Dienst.

Schlägt der Start fehl, werden alte Laufzeit, tatsächliches altes Image und gesicherte Daten wiederhergestellt. Nach einer Unterbrechung erkennt der Wartungsdienst einen offenen Auftrag und versucht die Wiederherstellung. Parallele Browser- und SSH-Updates werden durch dieselbe Dateisperre verhindert. Änderungen an Kamera- und Grundeinstellungen warten während eines laufenden Updates.

Sicherungen unter `backups/` und der private Auftragszustand unter `.maintenance/` bleiben auf dem Pi. Sie enthalten private Informationen und gehören nicht in GitHub. Es erfolgt keine automatische Löschung vorhandener Sicherungen.

Wenn eine Wiederherstellung Hilfe benötigt, bleibt der manuelle Wartungsweg verfügbar:

```sh
cd ~/kamerablick
./pi/update.sh --recover
systemctl --user status oma-tv-maintenance.service
journalctl --user -u oma-tv-maintenance.service -n 50
```

Der dauerhafte Wartungsdienst und grafischer Autostart sind unterschiedliche Dinge. Für die TV-Ansicht bleibt Desktop-Autologin erforderlich. Updates von Raspberry Pi OS, Docker, Firmware und VPN erfolgen separat.

## Prüfstand

Automatische Tests prüfen Anmeldung und Bestätigung, feste Releasequelle, Image-Zuordnung, Geheimnistrennung, parallele Aufträge und Wiederherstellung. Ein ergänzendes Docker-Labor prüft den tatsächlichen Container- und Laufzeitwechsel einschließlich Sicherung und Rückkehr mit erzeugten Testdaten. GitHub-/Download-Transport und der systemd-Prozessstarter werden darin durch Testgegenstellen ersetzt. Das ist keine Abnahme des echten Pi oder der TV-Hardware; die Geräteschritte stehen in [ABNAHME.md](ABNAHME.md).
