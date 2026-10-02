# Auto-Detektion von Schusslöchern — Exploration (VLM & YOLOE)

> **Status:** Abgeschlossene Machbarkeits-Exploration, **kein aktiver Ansatz**.
> Entscheidung: VLM (zu langsam, Recall-Lücke) und YOLOE Zero-Shot (zu viele
> Falsch-Positives) werden **nicht weiterverfolgt**. Stattdessen wird über die
> realen Messungen (Match-Daten) ein **eigenes YOLO-Fine-Tuning** aufgebaut.

## Ziel & Vorgehen

Die Idee: Schusslöcher automatisch auf dem Kamerabild detektieren, damit die
Messung nicht mehr auf manuelle Klicks angewiesen ist. Getestet wurden zwei
Wege (explorativ, ohne OpenSpec-Change):

- **VLM** (Vision-Language-Modell, OpenAI-kompatible API eines gehosteten
  Vision-Modells): Structured-Output-JSON mit `bbox_2d`.
- **YOLOE** (Ultralytics, Open-Vocabulary): Text-Prompt, Visual-Prompt,
  Fine-Tuning.

Evaluationsbasis: die 10 Dataset-Samples (`datasets/sample_01..10`) mit
manuellen Referenzpunkten als Ground Truth. Matching gierig (nächster
Nachbar, 1:1) mit **3-mm-Schwelle**. Metriken: Recall (gefundene GT),
Precision (korrekte Detektionen), Lokalisierungsfehler in mm.

## VLM-Ansatz

### Befunde

| Konfiguration | Recall | Precision | mean | Latenz |
|---|---|---|---|---|
| Einstufig Box @1280px | 50 % | 74 % | 0.8 mm | ~20 s |
| Einstufig Box @2048px | 54 % | 86 % | 1.27 mm | ~20 s |
| Connected-Prompt @1280 | 52 % | 77 % | 0.79 mm | ~20 s |
| Zweistufig (Box → Crop) | 65 % | 81 % | 0.99 mm | ~40 s |
| Gruppen-Box (2-stufig) | 31 % | 83 % | 1.25 mm | — |

- **Recall-Wand:** Das Modell findet intrinsisch nur ~2–3 von 5 Löchern
  (max. 54–65 %), unabhängig von Prompt, Auflösung (1280/2048) und
  Image-Tokens. Berührende Löcher werden zu einer Box zusammengefasst.
- **Leere Antworten:** Lange/detaillierte Prompts triggern deterministisch
  leere Antworten; `temperature=0` macht Retries nutzlos. Das `group`-Schema
  scheiterte systematisch (6/10 leer).
- **Latenz:** ~6,5 s/Sample (gemessen in der finalen Pipeline), frühe Läufe
  bis ~20–40 s. Der VLM-Call ist die externe Abhängigkeit und der Zeitfresser.

### VLM + `find_center`-Pipeline (letzter Messlauf)

VLM-Kandidaten → Automatik-`find_center` (Zentrumsverfeinerung) → GT-Matching:

- Recall **50 %** (23/46), Precision **74 %** (23/31).
- Mittlere Abweichung: **0.66 mm** verfeinert vs. 1.14 mm roh (−42 %),
  max 2.98 mm.
- Timing: VLM median **6.5 s**, `find_center` median **0.24 s**, gesamt ~7 s.

→ `find_center` halbiert den Lokalisierungsfehler, ändert aber Recall/Precision
nicht. Der VLM-Call dominiert die Latenz.

## YOLOE-Ansatz (Zero-Shot, Text-Prompt)

`yoloe-26n-seg.pt` (kleinstes Modell), Text-Prompt via MobileCLIP-Embedding
(`set_classes`), CPU.

### Prompt-/Auflösungs-Sweep

| Konfiguration | Recall | mean | det |
|---|---|---|---|
| `bullet hole,shot hole` @1280, conf 0.25 | 30 % | 0.89 mm | 48 |
| `bullet hole` @1280, conf 0.05 | 61 % | 1.1 mm | 189 |
| `dark bullet hole` @1920, conf 0.05 | 78 % | 1.20 mm | 360 |
| 6-Klassen @1920, conf 0.05 | **85 %** | 1.26 mm | 371 |

- **Einfache Prompts schlagen detaillierte** (Loch-Erkennung ist an
  Alltagsbegriffe gekoppelt). Multi-Class (6 Synonyme parallel) gibt +7 pp
  (78 → 85 %).
- **Höhere Auflösung hilft** (1280 → 1920: 61 → 78 %), da Löcher klein sind.
- **Größere Modelle sind schlechter:** 26s 46 %, 26m 72 %, 26l 57 % bei
  conf 0.05 — die `n`-Skala hat die günstigste Konfidenz-Charakteristik.
- **Latenz:** 0,4–0,6 s/Sample auf CPU — der große Vorteil gegenüber VLM.

### Fehldetektionen & Filter

Der Preis des niedrigen conf: bei 85 % Recall sind 360 Detektionen auf 46 GT
(Precision ~10 %). Analysierte Filtermöglichkeiten:

- **Bildmerkmale** (dunkles Zentrum, Boxgröße, kompakter Kern):
  - balanced (`g≤120, area≥8000, diff≤60`): Recall 72 %, **Precision 41 %**.
  - strict (`g≤105, area≥10000, diff≤40`): Recall 67 %, **Precision 50 %**.
- **Tisch-Ähnlichkeit** (`_frame_context`-Distanz, niedrig = Tisch sichtbar):
  trennt bei YOLOE gut (echte Löcher med 18.7 vs. Fehldetektionen med 57.4),
  beim VLM nicht (dort sind FPs andere dunkle Stellen).
- **Top-5-Szenario** (Messung nutzt max. 5 Detektionen): beste Precision
  52 % (balanced), 60 % nur bei conf>0.3 mit starkem Recall-Verlust.
- **Visual-Prompt** (Referenz-Crop als Beispiel): Recall 100 % nur bei
  conf 0.001 (Modell detektiert praktisch alles, Precision 1.6 %) — nicht
  nutzbar. Zweistufig (Scheibe → Crop) mit 33 % Recall ebenfalls schlechter.

### Fine-Tuning (Machbarkeit)

Pipeline (YOLO-Format aus GT-Punkten, `YOLOEPETrainer`, Detect-Architektur)
ist technisch vollständig durchgespielt und läuft. Aber: **1–2 Scheiben mit
5–10 Objekten reichen nicht** — über 30 Epochen bleiben val-precision/recall
durchgehend 0, das Modell findet nichts (keine Konvergenz). Ab ~50–100
Scheiben wäre Fine-Tuning die stärkste Option.

## `find_center`-Genauigkeit (Automatik-Modus)

Auf den idealen GT-Klickpunkten über alle Samples (aktueller Pfad:
Ring-Kernel-Vorlokalisierung + schrumpfende Scheiben-Maske, keine Tisch-Referenz):

| Pfad | mean | max | 0 Latches |
|---|---|---|---|
| Ring-Kernel + Scheiben-Maske | 0.28 mm | 0.83 mm | ✓ (46/46 gefunden) |
| früher: Referenz-Pfad (`_center_from_reference`) | 0.10 mm | 0.27 mm | ✓ |
| früher: Legacy (adaptive Schwelle + Radial-Fit) | 0.24 mm | 0.83 mm | ~50 % |

Der frühere Referenz-Pfad war präziser bei exaktem Klick, aber ohne unabhängige
Information (Fehler mit Legacy nahezu perfekt korreliert) und bei Klick-Versatz
schlechter. Der aktuelle Pfad verzichtet auf die Tisch-Referenz, ist robust
gegen Scheibenaufdruck (Ring-Kernel am bekannten Kaliberradius) und schlägt bei
zu ungenauem Klick explizit fehl statt ein ungenaues Zentrum zu liefern. Die
eigentliche Mess-Präzision (0.01 mm) liefert ohnehin die Kalibrierung;
`find_center` ist für die Zentrumsbestimmung im Suchfenster ausreichend.

## Entscheidung

- **VLM fällt raus:** 6–7 s/Sample bei 50 % Recall — langsamer und unzuver-
  lässiger als der manuelle Klick mit Automatik (5 Klicks in gleicher Zeit).
- **YOLOE Zero-Shot fällt raus:** Recall 85 % roh, aber Precision nur ~10 %
  (max ~50 % mit Filtern). Für die Messung zählen die *gelieferten*
  Detektionen — jedes zweite wäre ein Fehlalarm. Das wäre mehr Hindernis
  als Hilfe.
- **Künftige Richtung:** Bei den realen Messungen (Matches) Daten sammeln
  (Bild + GT-Zentrum) und damit ein **eigenes YOLO-Modell trainieren**
  (Fine-Tuning). Das übertrifft jede Zero-Shot-Methode, sobald genug Daten
  vorliegen. Die hier validierte Trainings-Pipeline (GT-Punkte → YOLO-Format,
  `YOLOEPETrainer`) ist dafür die Basis.