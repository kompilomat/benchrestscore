# Referenz-Samples (privat)

Die nummerierten Sample-Ordner (`sample_01/`, `sample_02/`, …) mit den im
App-Betrieb erfassten Referenz-Szenen (Roh-/Kalibrier-/Untergrundbilder,
Kalibrierung, Untergrundmodell, manuelle Messpunkte in `metrics.json`)
sind **nicht öffentlich** und daher nicht Teil dieses Repos.

Die Referenz-Tests (`benchrestscore/tests/test_reference_dataset.py`,
`test_reference_eval.py`, Teile von `test_controller.py`) vergleichen die
Klick-Automation mit der manuellen Bewertung eines Menschen und
überspringen sich automatisch (`skip`), wenn keine Samples gefunden
werden.

## Samples bereitstellen

Lege die Sample-Ordner an einem der beiden Orte ab:

- Repo-lokal in diesem Verzeichnis (`datasets/sample_NN/…`), oder
- an einem beliebigen Ort, den die Umgebungsvariable
  `BRS_REFERENCE_DATASET` auf das Dataset-Wurzelverzeichnis zeigt.

Sobald mindestens ein `sample_NN/`-Ordner gefunden wird, laufen die
Referenz-Tests wieder vollständig. Die Ordnerstruktur entsteht beim
Arbeiten der App im Referenz-Modus (siehe `docs/` bzw.
`openspec/specs/app/reference-eval`).
