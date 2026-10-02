# Benchrestscore

OpenGL-basierte Anwendung (imgui-bundle/GLFW/PyOpenGL) zum Vermessen von Schusslöchern
an der Webcam in Echtzeit (Genauigkeit bis 0,01 mm).

## Setup

Apt-Pakete:

```bash
sudo apt-get install python3-opencv python3-scipy python3-numpy python3-pydantic \
    libglfw3 v4l-utils gstreamer1.0-plugins-bad
```

Python-Abhängigkeiten aus `requirements.txt` (in das Projekt-`.venv` installieren):

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```

`--system-site-packages` ist zwingend, damit das System-`cv2` aus `python3-opencv`
(mit GStreamer-Backend, das `camera.py` für die GStreamer-Pipeline braucht) im `.venv`
importierbar ist. **Nicht** `opencv-python` per pip installieren: die offiziellen
PyPI-Wheels haben kein GStreamer-Backend und shadowen das System-`cv2` — die Kamera
funktioniert dann nicht. `imgui-bundle`, `glfw` und `PyOpenGL` liefern den
GLFW + OpenGL (PyOpenGL)-Stack und werden über `requirements.txt` im `.venv` installiert.

## Start

```bash
.venv/bin/python benchrestscore/app.py            # Fullscreen
.venv/bin/python benchrestscore/app.py --windowed # Fenster (Debug/X-Forwarding)
```

## Tests

```bash
.venv/bin/python benchrestscore/tests/test_controller.py
```

Die Referenz-Samples unter `datasets/` (Bild-/Metrikdateien) sind privat
und nicht Teil dieses Repos: die zugehörigen Referenz-Tests überspringen
automatisch, wenn keine Samples vorhanden sind. Lokal abgelegte Samples
(Default `datasets/`, alternativ Umgebungsvariable `BRS_REFERENCE_DATASET`)
aktivieren sie vollständig.

## Lizenz

Benchrestscore ist lizenziert unter der **GNU General Public License v3**
(vollständiger Text in [LICENSE.md](LICENSE.md)). Beiträge an dieses
Projekt gelten damit ebenfalls unter der GPLv3.

## Dokumentation

Ausführliche Doku findet sich in [`docs/`](docs/index.md):

- **Architektur** (Module, Datenfluss, Thread-Modell) — `docs/architecture.md`
- **Vermessung & Kalibrierung** (Metrik vs. Pixel, LUT-Rendering) — `docs/measurement.md`
- **GL/Rendering-Stack** (imgui-bundle, GLFW, Plattformwahl) — `docs/gl-stack.md`
- **Entwicklungs-Workflow** (OpenSpec, Regeln, Tests) — `docs/workflow.md`