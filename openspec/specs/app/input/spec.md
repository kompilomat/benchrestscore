# Input Specification

## Purpose

Regelt die Tastatur-Interaktion der App: Wie globale App-Shortcuts gegenüber
ImGui-Eingabewidgets (Textfelder, später Datenbankmasken) abgegrenzt werden.

## Requirements

### Requirement: Shortcuts bei aktiver Text-Eingabe unterdrücken
Das System SHALL globale App-Shortcuts unterdrücken, solange ein ImGui-
Eingabewidget (z. B. ein Textfeld) eine Text-Eingabe verarbeitet. Das
Eingabewidget selbst SHALL die Tasteneingaben weiterhin vollständig erhalten.
Ausnahme: Escape schließt einen geöffneten manuellen Etikett-Eingabe-Dialog
trotz aktiver Texteingabe (Anforderung „Escape schließt den manuellen
Etikett-Eingabe-Dialog").

#### Scenario: K beim Tippen in ein Textfeld
- **WHEN** der Nutzer in einem fokussierten Textfeld die Taste K drückt
- **THEN** wird das Zeichen in das Textfeld eingefügt
- **AND** wird keine Kalibrierung gestartet

#### Scenario: C beim Tippen in ein Textfeld
- **WHEN** der Nutzer in einem fokussierten Textfeld die Taste C drückt
- **THEN** wird das Zeichen in das Textfeld eingefügt
- **AND** wird keine Fit-Messung gestartet

#### Scenario: Q beim Tippen in ein Textfeld
- **WHEN** der Nutzer in einem fokussierten Textfeld die Taste Q drückt
- **THEN** wird das Zeichen in das Textfeld eingefügt
- **AND** beendet die Anwendung nicht

#### Scenario: Pfeiltasten in einem Textfeld
- **WHEN** der Nutzer in einem fokussierten Textfeld eine Pfeiltaste drückt
- **THEN** bewegt sich der Cursor im Textfeld
- **AND** wird kein Messpunkt justiert

#### Scenario: Shortcuts ohne Text-Eingabe
- **WHEN** kein ImGui-Eingabewidget eine Text-Eingabe verarbeitet und der Nutzer
  eine Shortcut-Taste (z. B. K) drückt
- **THEN** wird der zugehörige Shortcut ausgelöst (z. B. Kalibrierung)

#### Scenario: Escape bei offenem manuellen Etikett-Dialog
- **WHEN** der manuelle Etikett-Eingabe-Dialog offen ist, ein Textfeld des
  Dialogs fokussiert ist und der Nutzer Escape drückt
- **THEN** wird der Dialog ohne Übernahme der Werte geschlossen
- **AND** wird keine weitere App-Aktion (z. B. Kalibrier-Abbruch) ausgelöst

### Requirement: Etikett-Scan-Shortcut E
Das System SHALL die Taste **E** als globalen Shortcut für den Etikett-Scan
bereitstellen. Der Shortcut SHALL nur auslösen, wenn der BRSMatch-Modus aktiviert
ist; andernfalls SHALL die Taste keine Wirkung haben. Der Shortcut SHALL denselben
Guard-Regeln folgen wie andere globale Shortcuts (keine Auslösung bei aktiver
Text-Eingabe, keine Wiederholung bei Gedrückthalten).

#### Scenario: E bei aktivem BRSMatch
- **WHEN** der BRSMatch-Modus aktiviert ist und der Nutzer die Taste E drückt
- **THEN** wird der Etikett-Scan ausgelöst

#### Scenario: E bei inaktivem BRSMatch
- **WHEN** der BRSMatch-Modus nicht aktiviert ist und der Nutzer die Taste E drückt
- **THEN** wird kein Etikett-Scan ausgelöst

#### Scenario: E bei aktiver Text-Eingabe
- **WHEN** ein ImGui-Eingabewidget eine Text-Eingabe verarbeitet und der Nutzer die Taste E drückt
- **THEN** wird das Zeichen in das Textfeld eingefügt und kein Etikett-Scan ausgelöst

#### Scenario: Gedrückt gehaltenes E
- **WHEN** der Nutzer die Taste E gedrückt hält
- **THEN** wird der Etikett-Scan nicht wiederholt ausgelöst

### Requirement: Escape schließt den manuellen Etikett-Eingabe-Dialog
Das System SHALL die Taste Escape als Abbruch der manuellen Etikett-Eingabe
bereitstellen: Ist der manuelle Etikett-Eingabe-Dialog offen, schließt Escape
ihn ohne Übernahme der Werte — identisch zur Schließen-Funktion — sowohl bei
aktiver Texteingabe in einem seiner Felder (Ausnahme zur Unterdrückung der
Shortcuts, siehe Anforderung „Shortcuts bei aktiver Text-Eingabe
unterdrücken") als auch ohne aktiver Texteingabe (z. B. Fokus auf einem
Button). Escape ohne geöffneten Dialog behält das bestehende Verhalten bei.

#### Scenario: Escape mit aktiver Texteingabe
- **WHEN** der manuelle Etikett-Eingabe-Dialog offen ist, die Tastatur in einem
  seiner Eingabefelder fokussiert ist und der Nutzer Escape drückt
- **THEN** wird der Dialog geschlossen und es werden keine Werte übernommen

#### Scenario: Escape ohne aktive Texteingabe
- **WHEN** der manuelle Etikett-Eingabe-Dialog offen ist und die Tastatur nicht
  in einem seiner Eingabefelder fokussiert ist (z. B. Fokus auf einem Button
  des Dialogs) und der Nutzer Escape drückt
- **THEN** wird der Dialog geschlossen und es werden keine Werte übernommen

#### Scenario: Escape ohne geöffneten Dialog
- **WHEN** der manuelle Etikett-Eingabe-Dialog geschlossen ist und der Nutzer
  Escape drückt
- **THEN** verhält sich Escape wie zuvor: Abbruch des Kalibrier-Workflows in den
  dafür vorgesehenen States, sonst keine Wirkung