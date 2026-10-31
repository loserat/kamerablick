"""One-time migration of an existing managed installation to browser updates."""
import argparse
from pathlib import Path
import subprocess
import sys

import install
import maintenance
import release_info


def activate(root, home, image):
    if not (root/'.install.json').exists():
        raise ValueError('Verwaltete Installation fehlt. Für eine neue Installation pi/install.py verwenden.')
    if not image.startswith(release_info.IMAGE+':'):
        raise ValueError('Für Browser-Updates das offizielle Kamerablick-Image verwenden.')
    release_info.version(image.rsplit(':',1)[1])
    if not maintenance.persistent_user():
        raise ValueError('Zuerst einmalig ausführen: sudo loginctl enable-linger "$USER"')
    checks=install.preflight(root)
    if not all(item['ok'] for item in checks):
        raise ValueError('Voraussetzungen prüfen: python3 pi/install.py --check')
    settings=install.read_env(root/'.env')
    if settings.get('DEMO_MODE','true').lower()!='false' or settings.get('HOME_TEST_MODE','false').lower()=='true':
        raise ValueError('Heimtest und Pi-Installation bleiben getrennt. Echtbetrieb zuerst bewusst einrichten.')
    if settings.get('OMA_TV_IMAGE')!=image:
        subprocess.run([sys.executable,str(root/'pi/update.py'),image],check=True)
    install.install_project(root,home,image=image)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True,type=install.registry_image)
    args=parser.parse_args()
    try:
        activate(install.project_root(__file__),Path.home(),args.image)
    except (ValueError,subprocess.CalledProcessError) as error:
        raise SystemExit(str(error) if isinstance(error,ValueError) else 'Übergang nicht abgeschlossen. Vorhandene Installation und Wartungsprotokoll prüfen.')
    print('Browser-Updates eingerichtet. Kamera, Passwort und Einstellungen wurden erhalten. Die Oberfläche neu laden und unter Wartung die Version prüfen.')


if __name__=='__main__':
    main()
