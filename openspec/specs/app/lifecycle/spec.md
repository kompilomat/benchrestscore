## Purpose

Regelt den geordneten Shutdown der Anwendung: Signal-Handling für SIGINT/SIGTERM,
garantiertes Durchlaufen der Cleanup-Pipeline und Vermeidung harter Abbrüche
sowie Thread-Tracebacks beim Beenden.

## Requirements

### Requirement: SIGINT/SIGTERM lösen geordneten Shutdown aus
Das System SHALL die Signale SIGINT (Strg+C) und SIGTERM abfangen und einen
geordneten Shutdown auslösen, der alle Cleanup-Schritte (Persistieren des
UI-Zustands, Stoppen des Kamera-Threads, Stoppen des Hintergrund-Monitors,
Herunterfahren des ImGui/GLFW-Kontexts) durchläuft. Der Shutdown SHALL über
denselben Mechanismus wie die Q-Taste angestoßen werden und darf den Prozess
nicht mit einer unbehandelten Exception abbrechen.

#### Scenario: Strg+C bei laufender App
- **WHEN** der Nutzer bei laufender App im Terminal Strg+C drückt
- **THEN** startet die App einen geordneten Shutdown
- **AND** werden UI-Zustand, Kamera-Thread und Hintergrund-Monitor sauber
  beendet
- **AND** wird der GLFW/ImGui-Kontext heruntergefahren
- **AND** endet der Prozess ohne Exception- oder Traceback-Ausgabe

#### Scenario: SIGTERM bei laufender App
- **WHEN** der Prozess ein SIGTERM erhält (z.B. von einem Session-Manager)
- **THEN** startet die App denselben geordneten Shutdown wie bei Strg+C

#### Scenario: Q-Taste
- **WHEN** der Nutzer die Q-Taste drückt
- **THEN** beendet sich die App wie bisher über den normalen Shutdown-Pfad
- **AND** ändert das Signal-Handling daran nichts

### Requirement: Shutdown läuft auch bei unerwartetem Interrupt
Das System SHALL die Cleanup-Pipeline auch dann garantiert ausführen, wenn eine
`KeyboardInterrupt`-Exception nicht über den Signal-Handler, sondern direkt im
Haupt-Thread ankommt.

#### Scenario: Interrupt ohne Handler-Registrierung
- **WHEN** eine `KeyboardInterrupt`-Exception den Render-Loop verlässt
- **THEN** wird die Cleanup-Pipeline (Persistieren, Thread-Stopp, GLFW-Terminate)
  trotzdem ausgeführt
- **AND** endet der Prozess ohne unaufgeräumte Ressourcen

### Requirement: Kamera-Thread beendet sich ohne Traceback
Das System SHALL sicherstellen, dass der Kamera-Capture-Thread beim Beenden
keine unbehandelten Exceptions wirft. Wirft der Capture-Aufruf während des
Beendens eine Exception, SHALL diese abgefangen und ohne Traceback-Ausgabe
behandelt werden.

#### Scenario: Abbruch mitten im Capture
- **WHEN** der Kamera-Thread während des Beendens von `vid.read()` eine
  Exception wirft
- **THEN** wird die Exception abgefangen
- **AND** erscheint kein „Exception in thread"-Traceback beim Prozess-Exit

#### Scenario: Normales Beenden
- **WHEN** die App geordnet herunterfährt
- **THEN** wird die Capture-Ressource freigegeben (release) und der Thread
  beendet sich still