# TV-Fernbedienung

Die Software nimmt Pfeile, OK und Zurück über HDMI-CEC entgegen. Der Fernseher empfängt weiterhin das Infrarotsignal und muss diese Tasten an den angeschlossenen Pi weitergeben. Ein eigener IR-Empfänger ist dafür zunächst nicht vorgesehen. Das tatsächliche TV-Modell und die Weitergabe sind noch ungeprüft.

## Bedienung

- Pfeile bewegen den hellen Auswahlrahmen.
- OK öffnet die ausgewählte Schaltfläche.
- Zurück schließt einen Dialog oder kehrt zur Übersicht zurück.
- Während des echten Kamerabilds schließen OK und Zurück den Player. Der Fernseher bleibt eingeschaltet. Das funktioniert im Pi-Dienst, auch wenn der Browser hinter dem Player liegt.
- „Fernseher aus“ öffnet eine Bestätigung. Zuerst ist „Zurück“ ausgewählt.

Lautstärke, Ziffern und die Einschalt-/Standbytaste der Fernbedienung werden nicht in Menüaktionen umgewandelt. Es gibt keine systemweite Tastatureinspeisung. Unbekannte CEC-Codes werden zur Diagnose angezeigt und lösen keine Aktion aus.

## Am Fernseher prüfen

1. HDMI-CEC im TV aktivieren und den HDMI-Eingang des Pi auswählen.
2. Die Kamerablick-TV-Anwendung auf dem Pi starten. Ein über das Dashboard geöffnetes zusätzliches TV-Fenster erhält keinen Fernbedienungsempfang.
3. Im geschützten Dashboard „Wartung → Tastenempfang prüfen“ öffnen. Adapterverbindung und TV-Empfänger müssen erkennbar sein.
4. Jede Pfeiltaste, OK und Zurück einzeln drücken. Angezeigte Taste und Auswahlrahmen vergleichen.
5. OK mehrere Sekunden halten: Es darf keine Folge unbeabsichtigter Aktionen geben. Nach Loslassen muss der nächste Druck funktionieren.
6. Kamerabild öffnen und mit Zurück verlassen. Der Player muss schließen, der TV eingeschaltet bleiben und das Menü wieder bedienbar sein.
7. Ausschalten mit „Zurück“ abbrechen, anschließend bewusst bestätigen und Standby am TV prüfen.
8. Pi-Dienst neu starten, während der TV aus ist: Der Dienst selbst fordert kein Einschalten an. Das Verhalten der Pi-Firmware beim Booten separat am Gerät prüfen.
9. HDMI-Verbindung trennen/wiederherstellen und prüfen, dass die Diagnose aktuell wird und keine alten Tastendrücke ausgeführt werden.

Kommt keine Taste an, zuerst TV-Einstellung, richtigen HDMI-Anschluss und Geräteberechtigungen des Desktop-Benutzers prüfen. `cec-client` nicht parallel zum Pi-Dienst starten: Der Pi-Dienst hält den CEC-Adapter für Empfang und Schaltbefehle geöffnet. Bei Bedarf den Dienst für externe Diagnosewerkzeuge vorher stoppen.

## Schutz und Wiederverbindung

Der lokale Kiosk erhält beim Start zusätzlich zum begrenzten TV-Zugang einen eigenen reinen Empfangsschlüssel. Er kann damit ausschließlich neue Tasten abholen; Dashboard-Einstellungen und Protect-Schlüssel bleiben geschützt. Schlüssel liegen privat im Datenvolume und im eigenen Chromium-Profil. Keine Schlüssel in GitHub oder Protokolle übernehmen.

Nur eine TV-Seite erhält gleichzeitig Eingaben. Nach Browserwechsel, Dienstneustart oder Verbindungsabbruch wird ein neuer Ausgangspunkt gesetzt; Tastendrücke werden nicht nachträglich wiederholt. Wartende Eingaben verfallen nach 1,5 Sekunden. Bei belegter Verbindung wartet ein zweites Fenster, bis der bisherige Empfänger seit zwei Sekunden nicht mehr abfragt. Wiederholte gedrückte CEC-Tasten zählen bis zum Loslassen nur einmal. Fehlt ein Loslassen-Signal des Fernsehers, muss dieses Verhalten am Gerät geprüft und gegebenenfalls angepasst werden.

„TV-Zugang zurücksetzen“ widerruft auch den Empfangsschlüssel. Danach die TV-Anwendung auf dem Pi neu starten, damit sie neue lokale Zugänge bekommt. Ein Adapterstatus „verbunden“ beweist weder die Tastenweitergabe noch den tatsächlichen Einschaltzustand des Fernsehers.

## Technische Grundlage und Nachweise

Die Anbindung verwendet einen dauerhaft geöffneten [cec-client von libCEC](https://github.com/Pulse-Eight/libcec/blob/master/src/cec-client/cec-client.cpp) aus `cec-utils`. Der Pi-Dienst liest die empfangenen CEC-Nachrichten und übergibt Einschalten/Standby an denselben Prozess. Es wird keine native Python-CEC-Bindung geladen.

Nur vom TV (CEC-Adresse 0) an die eigene erkannte Playback-Adresse gerichtete Nachrichten werden als Tasten angenommen. Gesendete Nachrichten, Broadcasts und Eingaben für andere Geräte werden ignoriert. Der Helfer wird nach Prozessende oder erfolglosem Verbindungsaufbau mit Abstand neu gestartet. Ein übergebener Schaltbefehl beweist keine Bestätigung durch den TV; die Diagnose unterscheidet dies ausdrücklich. Adapter- und Tastenerkennung basieren auf dem Ausgabeformat von libCEC, das bei späteren Paketupdates erneut zu prüfen ist.

Lokal geprüft: Tastenzuordnung, Halten/Loslassen, unbekannte Tasten, begrenzte Warteschlange, veraltete Eingaben, Empfängerwechsel, Dienstneustart, getrennte Zugänge, Widerruf und Rückkehr aus dem Player mit simuliertem Prozess. Im Browser wurden Navigation, Hilfe, Kameravorschau und sichere Ausschaltbestätigung mit simuliertem Empfang geprüft. Zusätzlich ist der echte Trixie-CEC-Hilfsprozess auf ARM64 ohne Adapter geprüft: Paketoptionen, Ablehnung von Befehlen ohne Adapter, keine falsche Verbindungsanzeige und sauberes Beenden. Reproduzierbar über `python3 tests/cec_acceptance.py` mit erreichbarer Docker-Engine. Echte IR-/CEC-Signale, tatsächliche Adapterberechtigungen, Playerfokus und TV-Reaktionen bleiben Bestandteil der Geräteabnahme.
