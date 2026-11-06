# Betrieb, Sicherungen und Speicher

## Installation prüfen

Als bisheriger Installationsbenutzer auf dem Pi:

```sh
cd ~/kamerablick
python3 .runtime/current/doctor.py --root "$PWD"
docker compose ps
systemctl --user is-active oma-tv-agent.service oma-tv-kiosk.service oma-tv-maintenance.service
```

Die Diagnose liest den Zustand und gibt keine Zugangswerte aus. Sie sendet keine TV-Schaltbefehle. Der Container muss gesund sein, die drei Dienste aktiv und Browser-Updates bereit. Das prüft weder das echte Livebild noch einen GPIO-Taster oder den Zugriff von unterwegs.

Die installierte App-Version steht unter **Wartung**. `git describe` zeigt dagegen nur den ausgecheckten Quellstand: Browser-Updates wechseln das Docker-Image und die verwaltete Pi-Laufzeit, ohne dafür den Git-Checkout wechseln zu müssen.

## Updates

Unter **Wartung → Version prüfen → Jetzt aktualisieren → Sichern und aktualisieren** eine veröffentlichte Version installieren. Währenddessen den Pi eingeschaltet lassen. Danach bei Bedarf neu anmelden, das Dashboard neu laden und die installierte Version prüfen. [Updateablauf und Wiederherstellung](BROWSER-UPDATES.md).

Bei einer früher abgebrochenen Installation kann ein bereits laufender Wartungsdienst intern noch als nicht fertig eingerichtet gelten. Das fällt im Diagnoseprogramm auf. Den Einrichtungshelfer aus dem passenden veröffentlichten Quellstand erneut erfolgreich abschließen, statt Konfiguration oder Datenvolumes zu löschen. Ein laufender Dienst allein bestätigt keine vollständige Installation.

## Welche Daten erhalten bleiben müssen

| Speicherort | Inhalt |
| --- | --- |
| `.env` | Dashboard-Passwort, Dienstschlüssel, Bindung, Port und gewähltes Image. |
| Docker-Datenvolume | Kamerakonfiguration, Protect-Zugang, eigene Kameras, TV-Kopplung und Ereigniszustand. |
| `~/.config/oma-tv/` | Lokale Diensteinstellungen und Pi-Konfiguration. |
| `.install.json`, `.runtime/` | Installationszuordnung und versionierte Pi-Laufzeiten. |
| `.maintenance/`, `backups/update-state.json` | Laufender oder letzter Updateauftrag und Wiederherstellungszustand. |
| `backups/`, `oma-tv-rollback:*`, `oma-tv-reinstall:*` | Sicherungen und zugehörige lokale Rückfallimages. |

Diese Dateien können Geheimnisse enthalten und gehören nicht in GitHub. Eine Dateisicherung ohne das zugehörige Rückfallimage und die Laufzeit ist nicht automatisch eine vollständige Wiederherstellung. Bei manuellen Sicherungen immer zusammengehörige Versionen und den geprüften Wiederherstellungsweg festhalten.

## Speicher kontrolliert aufräumen

Zuerst den Bestand messen:

```sh
df -h .
docker system df
docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}'
docker image ls
du -sh backups .runtime /var/cache/apt/archives
```

Heruntergeladene, bereits installierte Betriebssystempakete lassen sich erneut beziehen. Deren Downloadcache kann bei Bedarf geleert werden:

```sh
sudo apt-get clean
```

Das entfernt keine installierten Programme. Quellcode, Kameraeinstellungen und Rückfallsicherungen werden damit nicht gelöscht.

Alte, öffentliche Kamerablick-Images nur einzeln mit ihrem vollständigen Namen entfernen, wenn kein Container sie verwendet und sie zu keiner benötigten Sicherung gehören. Zuerst das laufende Image, das letzte funktionsfähige Rückfallimage und alle Verweise in den aufbewahrten Sicherungen prüfen. Gemeinsam verwendete Docker-Schichten bedeuten, dass die angezeigten Imagegrößen nicht als tatsächlicher Platzgewinn addiert werden können.

Für Entwicklungsrechner lassen sich eindeutig zugeordnete, ungenutzte Kamerablick-Buildcaches und erzeugte Python-Dateien erneut aufbauen. Quellen, Versionsarchive, Berichte und Testnachweise behalten. Eine entfernte virtuelle Testumgebung wird nach [Entwicklung](ENTWICKLUNG.md) neu erstellt.

Kein pauschales `docker system prune -a --volumes`, kein Löschen von Docker.raw und kein Entfernen kompletter Projekt-/Sicherungsordner verwenden. Andere Projekte, Datenvolumes und aktive Container benötigen eine eigene Bestandsprüfung. Docker beschreibt die gezielte Auswahl von Buildcache-Einträgen über [Filter für buildx prune](https://docs.docker.com/reference/cli/docker/buildx/prune/#filter).
