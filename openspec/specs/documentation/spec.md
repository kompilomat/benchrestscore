## Purpose

Defines the project documentation: an organized `docs/` directory with maintained,
modular pages, plus consistent entry points from `README.md` and `AGENTS.md` so that
humans and coding agents can quickly orient themselves in the codebase.

## Requirements

### Requirement: Central docs directory with defined pages

The repository SHALL contain a `docs/` directory providing the primary project
documentation, organized into distinct pages: an index (entry point), an
architecture page, a measurement/calibration page, a GL/rendering-stack page, and a
workflow/development page.

#### Scenario: Index page exists and links to the other pages

- **WHEN** the docs directory is inspected
- **THEN** it contains `docs/index.md` that links to `architecture.md`, `measurement.md`, `gl-stack.md` and `workflow.md`

#### Scenario: Architecture content is available

- **WHEN** a developer opens `docs/architecture.md`
- **THEN** it documents the modules, the data flow and the threading model of the application

#### Scenario: Measurement content is available

- **WHEN** a developer opens `docs/measurement.md`
- **THEN** it documents the metric-versus-pixel model, calibration and the LUT rendering used for measurement precision

#### Scenario: GL stack content is available

- **WHEN** a developer opens `docs/gl-stack.md`
- **THEN** it documents the imgui-bundle/GLFW/PyOpenGL stack and the platform selection (`glx`/`egl`) performed before GL context creation

#### Scenario: Workflow content is available

- **WHEN** a developer opens `docs/workflow.md`
- **THEN** it documents the OpenSpec-driven workflow, the project `.venv` rule, the no-commit rule and how to run tests

### Requirement: Entry point from AGENTS.md

`AGENTS.md` SHALL point a coding agent to the documentation index so that project
conventions and architecture are discoverable without reading the whole codebase.

#### Scenario: Agent finds the docs

- **WHEN** a coding agent reads `AGENTS.md`
- **THEN** it encounters a documentation section that references `docs/index.md`

### Requirement: README links to detailed docs

`README.md` SHALL keep a concise quickstart and setup guide while delegating detailed
architecture explanation to the `docs/` directory rather than duplicating it.

#### Scenario: README refers to the documentation

- **WHEN** a reader opens `README.md`
- **THEN** the setup and architecture sections reference `docs/index.md` for the detailed documentation

### Requirement: Documentation stays current

The documentation in `docs/` SHALL reflect the current codebase state (module names,
threading model, dependency stack) so it remains a reliable orientation for a coding agent.

#### Scenario: Docs match current code structure

- **WHEN** the documented modules and threading model are checked against `benchrestscore/`
- **THEN** they are consistent with the current implementation

### Requirement: README dokumentiert Lizenz und privates Referenz-Dataset

`README.md` SHALL eine Lizenz-Sektion enthalten, die die Anwendung als
GPLv3-lizenziert ausweist, sowie einen Hinweis, dass die Referenz-Samples
unter `datasets/` nicht öffentlich sind: Die zugehörigen Tests skippen
ohne Samples automatisch, mit lokal abgelegten Samples oder gesetzter
Umgebungsvariable `BRS_REFERENCE_DATASET` laufen sie vollständig.

#### Scenario: Lizenz-Sektion vorhanden

- **WHEN** ein Leser `README.md` öffnet
- **THEN** findet er eine Sektion, die die Lizenz der Anwendung (GPLv3) benennt

#### Scenario: Hinweis auf private Referenz-Samples

- **WHEN** ein Leser `README.md` im Abschnitt Tests/Entwicklung liest
- **THEN** erfährt er, dass `datasets/` privat ist, Tests ohne Samples
  überspringen und `BRS_REFERENCE_DATASET` lokale Samples aktiviert