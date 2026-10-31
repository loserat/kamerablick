# Sicherheitsprobleme melden

Eine neue verwaltete Pi-Installation stellt das passwortgeschützte Dashboard im Heimnetz bereit (`BIND=0.0.0.0`). HTTP überträgt die Anmeldung und eingegebene Zugangsdaten unverschlüsselt; diesen direkten Weg nur in einem vertrauenswürdigen Heimnetz verwenden. Für ausschließlich lokalen Zugriff `BIND=127.0.0.1` setzen und einen SSH-Tunnel nutzen. Für Fernzugriff ist ein privater VPN-Zugang vorgesehen. Dashboard und Protect-Zentrale nicht durch öffentliche Portfreigaben erreichbar machen. Der interne TV-/GPIO-Dienst bleibt ausschließlich unter `127.0.0.1:8091` erreichbar. Bestehende Bindungen werden bei Installation und Updates erhalten.

Wenn GitHub im Reiter **Security → Advisories** die Schaltfläche **Report a vulnerability** anbietet, bitte diesen privaten Meldeweg verwenden. Falls er nicht verfügbar ist, ein Issue mit einer allgemeinen Bitte um einen privaten Kontaktweg öffnen. Dort noch keine Zugangswerte, ausnutzbaren Details, Stream-Adressen oder Kamerabilder veröffentlichen.

Browser-Updates benötigen die Dashboard-Anmeldung und eine ausdrückliche Bestätigung. Sie verwenden ausschließlich stabile Releases von `loserat/kamerablick`. Der unabhängige Wartungsdienst ist nur auf `127.0.0.1:8093` mit dem privaten lokalen Schlüssel erreichbar. Das Dashboard erhält keinen Docker-Socket. Eine zeitlich begrenzte Lesefreigabe zeigt den laufenden Auftrag nach einem Dashboard-Neustart weiter an; sie erlaubt keine Änderungen. Auch `.maintenance/`, dessen Statusfreigaben und alle Sicherungen privat halten. Der Ablauf und die Grenzen stehen unter [Browser-Updates](docs/BROWSER-UPDATES.md).

Für eine Untersuchung sind betroffene Version, Pi-/OS-Version, erwartetes Verhalten und eine Beschreibung mit anonymisierten Beispieldaten hilfreich. `.env`, Protect-API-Schlüssel und Sicherungen bleiben privat. Zugangswerte, die versehentlich veröffentlicht wurden, an der jeweiligen Quelle erneuern.

Es gibt derzeit keine zugesagte langfristige Pflege einzelner Versionen. Die aktuelle veröffentlichte Version und bekannte Grenzen stehen unter [Releases](https://github.com/loserat/kamerablick/releases) und [Geräteabnahme](docs/ABNAHME.md).
