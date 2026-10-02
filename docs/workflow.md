# Entwicklungs-Workflow

## Repo-Überblick

```
benchrestscore/          # Quellcode (Python, GLFW/OpenGL/imgui-bundle)
  app.py, controller.py, ui.py, camera.py, calibration.py,
  view.py, measurement.py, automation.py, gl_platform.py,
  data/, tests/
docs/                    # Diese Dokumentation (siehe index.md)
openspec/                # OpenSpec: specs/, changes/, config.yaml
```

## OpenSpec-getriebene Änderungen

Größere Arbeiten (Bugfixes, neue Funktionen, Refactoring) laufen über **OpenSpec**-
`changes` statt über direkte ungeplante Code-Änderungen.

- Planungs-Artefakte: `proposal.md`, `specs/<capability>/spec.md` (Delta),
  `design.md`, `tasks.md` unter `openspec/changes/<change-name>/`.
- Nach Abschluss: Delta-Specs in die Haupt-Specs übernehmen (`sync-specs`), Change
  archivieren (`archive-change`).
- Verfügbare Skills (`.opencode/skills/`):
  - **explore** – Ideen durchdenken.
  - **propose** – Change mit allen Artifakten anlegen.
  - **apply-change** – Tasks eines Changes implementieren.
  - **update-change** – Planungs-Artifakte revidieren.
  - **sync-specs** – Delta-Specs in die Haupt-Specs übernehmen.
  - **archive-change** – abgeschlossenen Change finalisieren.

## Regeln (aus AGENTS.md)

- **`.venv`**: Python-pip-Pakete immer mit dem Projekt-`.venv` installieren (`.venv/`
  stattdessen bei Bedarf `python3 -m venv .venv`). Nie pip ins System-Python.
- **Niemals committen**: Git-Commits, -Stages und -Pushes macht ausschließlich der User.
- **Kein direktes Umschreiben** an spec-getriebener Arbeit — dem `openspec-apply-change`-
  Skill folgen (bzw. vorher per `openspec-propose` einen Change anlegen).
- Specs/Changes leben in `openspec/` (`specs/`, `changes/`, `config.yaml`).

## Installation & Start

Siehe [`README.md`](../README.md) für Setup (venv + apt). Kurz:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo apt-get install python3-opencv python3-scipy python3-numpy libglfw3 \
    v4l-utils gstreamer1.0-plugins-bad

.venv/bin/python benchrestscore/app.py            # Fullscreen
.venv/bin/python benchrestscore/app.py --windowed # Fenster (Debug/X-Forwarding)
```

## Tests

Es gibt **Headless-Unit-Tests** für die App-State-Maschine (kein Fenster/GL):

```bash
.venv/bin/python benchrestscore/tests/test_controller.py
.venv/bin/python benchrestscore/tests/test_i18n.py      # Übersetzungssystem
.venv/bin/python benchrestscore/tests/test_settings.py  # Settings-Persistenz
.venv/bin/python benchrestscore/tests/test_measurement.py
.venv/bin/python benchrestscore/tests/test_calibration.py
.venv/bin/python benchrestscore/tests/test_fontconfig.py
.venv/bin/python benchrestscore/tests/test_automation.py
.venv/bin/python benchrestscore/tests/test_calibration_monitor.py  # Loss-of-Calibration-Monitor
.venv/bin/python benchrestscore/tests/test_filters.py
.venv/bin/python benchrestscore/tests/test_reference_eval.py       # Referenz-Snapshot + Auswertung
.venv/bin/python -m pytest benchrestscore/tests/test_reference_dataset.py  # reale Datasets (siehe unten)
```

Zusätzlich gibt es **Datasets-basierte Regressionstests** gegen die reale
Bewertung: `test_reference_dataset.py` lädt alle `datasets/sample_*`
(`BRS_REFERENCE_DATASET` übersteuert die Wurzel) und prüft die Klick-Automation
gegen die manuellen Messpunkte. Ohne vorhandene Samples werden die Tests
übersprungen. Zwei Ebenen:

- **No-Regression-Guard** (grün): alle Punkte gefunden, Max-Fehler < 3 mm.
- **Ziel-Tests** (grün): Sub-mm-Genauigkeit (max < 1 mm), keine Latch-Ereignisse
  (Zentrum springt auf ein Nachbarloch), Robustheit gegen Klick-Versatz bis 10 px
  (max < 1 mm) und bis 25 px (max < 2 mm; 25 px ≈ 1 mm Versatz, physische
  Grenze). Werden sie verletzt, färben sie rot — keine `xfail`-Marker mehr auf
  den Regressions-fähigen Zielen.

Die Klick-Automation lokalisiert das Lochzentrum über eine **Ring-Kernel-
Konvolution** am bekannten Kaliberradius (zirkulärer Matched-Filter auf dem
adaptiv geschwellten Binaerbild) und verfeinert es mit einer **schrumpfenden
Scheiben-Maske** (1,2r → 1,05r → 0,95r) unter harten Klick-Bounds. Liegt das
verfeinerte Zentrum weiter als 0,3 Kaliberradien vom Klick entfernt, schlägt
die Erkennung explizit fehl (Klick zu ungenau → Nutzer positioniert per
Drag&Drop) statt ein ungenaues Zentrum zu liefern.

Diagnose der Automation ohne pytest-Output:

```bash
.venv/bin/python benchrestscore/evaluate_dataset.py --per-point
```

Die Tests prüfen die FSM-Transitions (`AppController`) inkl. Guards und Side-Effects
(Start → CALIBRATING → RESULT → MEASURING; verbotene Übergänge; Fehler-Kalibrierung;
LUT-Reset), die Sprachwahl (`i18n`, `settings`, DE/EN-Ausgabe von Messwerttext und
Kalibrier-Fehlern) sowie die Filter- und Messwert-Logik. Grafik/GL-Pfad ist
manuell/End-to-End zu verifizieren (Start + Kalibrieren + Messen).

## Doku pflegen

- Ausführliche Architektur/Details → `docs/` (update bei Architektur-Änderungen).
- `README.md` = Quickstart/Setup; repräsentiert keine Details duplizieren.
- Coding-Agents finden den Einstieg über `AGENTS.md` → `docs/index.md`.