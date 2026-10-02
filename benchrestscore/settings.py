# -*- coding: utf-8 -*-
"""Persistente App-Settings als JSON im XDG-Config-Verzeichnis (headless testbar).

Der Config-Pfad ist injizierbar (z.B. Temp-Verzeichnis in Tests); der Default
folgt der XDG-Konvention (`$XDG_CONFIG_HOME/benchrestscore/settings.json`,
Fallback `~/.config/...`).
"""

import json
import os


def default_config_path():
    """Standard-Pfad der Config-Datei (XDG-Konvention)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "benchrestscore", "settings.json")


def default_config_dir():
    """Config-Verzeichnis der App (enthält `settings.json`).

    Reine Funktion, deployment-sicher (nutzerbeschreibbar, launcher-
    unabhängig); dient auch als Ablage für Kalibrier-Schnappschüsse
    (`last_calibration.png`/`.json`).
    """
    return os.path.dirname(default_config_path())


def load(path=None):
    """Settings-Dict laden.

    Fehlt die Datei oder ist sie kein gültiges JSON-Objekt, liefert `load()` ein
    leeres Dict (Erststart ohne gespeicherte Einstellungen). Die Datei wird hier
    nicht angelegt — erst `save()` schreibt sie.
    """
    path = path or default_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save(patch, path=None):
    """Einträge mergend speichern; legt Datei/Verzeichnis bei Bedarf an.

    Gibt das gespeicherte Settings-Dict zurück.
    """
    path = path or default_config_path()
    data = load(path)
    data.update(patch)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data