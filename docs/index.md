# Benchrestscore — Dokumentation

Benchrestscore ist eine OpenGL-basierte Anwendung (imgui-bundle/GLFW/PyOpenGL) zum
Vermessen von Schusslöchern an der Webcam in Echtzeit (Genauigkeit bis 0,01 mm).

## Einstieg

- **Setup & Quickstart** → [`README.md`](../README.md)
- **Architektur** (Modulübersicht, Datenfluss, Thread-Modell) → [`architecture.md`](architecture.md)
- **Vermessung & Kalibrierung** (Metrik vs. Pixel, LUT-Rendering, Genauigkeit) → [`measurement.md`](measurement.md)
- **GL/Rendering-Stack** (imgui-bundle, GLFW, PyOpenGL, Plattformwahl) → [`gl-stack.md`](gl-stack.md)
- **Auto-Detektion** (Exploration VLM & YOLOE, Befunde, Entscheidung) → [`auto-detection.md`](auto-detection.md)
- **Entwicklungs-Workflow** (OpenSpec, `.venv`, Regeln, Tests) → [`workflow.md`](workflow.md)

## Aufteilung README vs. docs

- `README.md` = Quickstart + Setup (venv/apt).
- `docs/` = Architektur, Details, Konzepte, Workflow — die gepflegte Wissensquelle.

## Konventionen auf einen Blick

- Code lebt in `benchrestscore/` (siehe [`architecture.md`](architecture.md)).
- Geplante Änderungen laufen über **OpenSpec-Changes** (siehe [`workflow.md`](workflow.md)).
- Python-Pakete gehören ins Projekt-`.venv`, nie ins System-Python.