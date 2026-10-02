# -*- coding: utf-8 -*-

from enum import Enum, auto

import os
import re
import threading
import time
from datetime import datetime, timezone

import numpy as np
import cv2

# Dual-Import: als Script (`benchrestscore/` auf sys.path) und als Paket
# (`benchrestscore.controller` in Tests) ladbar.
try:
    from .camera import (
        DEFAULT_CAMERA_DEVICE,
        CAMERA_PRESETS,
        probe_supported_presets,
        default_camera_opener,
        _run_v4l2_ctl,
    )
    from .i18n import (
        SUPPORTED_LANGUAGES,
        set_language as _i18n_set_language,
        set_locale as _i18n_set_locale,
        language_from_locale,
    )
    from .fontconfig import FONT_SCALES, DEFAULT_FONT_SCALE_KEY
    from .settings import load as _settings_load, save as _settings_save
    from .calibration_monitor import (
        BackgroundModel,
        BackgroundMonitorThread,
        CheckResult,
        MonitorStatus,
        CHECK_CADENCE_S,
        DEVIATION_THRESHOLD_MM,
        REFERENCE_ALPHA,
        REFERENCE_UPDATE_EVERY,
        REFERENCE_UPDATE_DEVIATION_FACTOR,
        draw_keypoints,
        table_mask,
    )
    from .vision_detect import (
        VisionConfig as _VisionConfig,
        STICKER_SCHEMA as _STICKER_SCHEMA,
        extract_sticker as _extract_sticker,
    )
    from .calibration_recovery import (
        save_full_session,
        load_background,
        remove_session_marker,
        has_valid_session,
        read_json,
        calibration_json_path,
        background_json_path,
    )
    from .calibration import undistort_frame, downscale_luts
    from .reference_eval import (
        dataset_root as _reference_dataset_root,
        next_sample_dir as _reference_next_sample,
        save_sample as _reference_save_sample,
    )
    from .calibration_card_qc import (
        QC_SAMPLE_FRAMES,
        QC_TOLERANCE_MM,
        build_payload,
        check_card,
        detect_grid_metric,
        render_overlay,
        save_result as _qc_save_result,
    )
    from .brsmatch_api import (
        lookup as _brs_lookup,
        submit_measurement as _brs_submit_measurement,
        BrsmatchError as _BrsmatchError,
    )
except ImportError:
    from camera import (
        DEFAULT_CAMERA_DEVICE,
        CAMERA_PRESETS,
        probe_supported_presets,
        default_camera_opener,
        _run_v4l2_ctl,
    )
    from i18n import (
        SUPPORTED_LANGUAGES,
        set_language as _i18n_set_language,
        set_locale as _i18n_set_locale,
        language_from_locale,
    )
    from settings import load as _settings_load, save as _settings_save
    from fontconfig import FONT_SCALES, DEFAULT_FONT_SCALE_KEY
    from calibration_monitor import (
        BackgroundModel,
        BackgroundMonitorThread,
        CheckResult,
        MonitorStatus,
        CHECK_CADENCE_S,
        DEVIATION_THRESHOLD_MM,
        REFERENCE_ALPHA,
        REFERENCE_UPDATE_EVERY,
        REFERENCE_UPDATE_DEVIATION_FACTOR,
        draw_keypoints,
        table_mask,
    )
    from vision_detect import (
        VisionConfig as _VisionConfig,
        STICKER_SCHEMA as _STICKER_SCHEMA,
        extract_sticker as _extract_sticker,
    )
    from calibration_recovery import (
        save_full_session,
        load_background,
        remove_session_marker,
        has_valid_session,
        read_json,
        calibration_json_path,
        background_json_path,
    )
    from calibration import undistort_frame, downscale_luts
    from reference_eval import (
        dataset_root as _reference_dataset_root,
        next_sample_dir as _reference_next_sample,
        save_sample as _reference_save_sample,
    )
    from calibration_card_qc import (
        QC_SAMPLE_FRAMES,
        QC_TOLERANCE_MM,
        build_payload,
        check_card,
        detect_grid_metric,
        render_overlay,
        save_result as _qc_save_result,
    )
    from brsmatch_api import (
        lookup as _brs_lookup,
        submit_measurement as _brs_submit_measurement,
        BrsmatchError as _BrsmatchError,
    )


class AppState(Enum):
    IDLE = auto()
    CALIBRATING = auto()
    RESULT = auto()
    LEARN_PROMPT = auto()
    LEARN_RESULT = auto()
    MEASURING = auto()


def _collect_frames(capture_worker, n=QC_SAMPLE_FRAMES, timeout_s=1.0):
    """n aufeinanderfolgende Frames vom Capture-Worker einsammeln.

    Liest `current_frame` in kurzen Abständen, bis `n` unterschiedliche Frames
    vorliegen (oder `timeout_s` erreicht ist). Ist gar kein Frame verfügbar,
    wird sofort abgebrochen. Rückgabe: Liste von Frames (leer, wenn keins
    verfügbar ist).
    """
    frames = []
    seen = None
    deadline = time.monotonic() + timeout_s
    first = True
    while len(frames) < n and time.monotonic() < deadline:
        fr = getattr(capture_worker, "current_frame", None)
        if fr is None:
            if first:
                break
            time.sleep(1.0 / 60.0)
            continue
        first = False
        arr = np.asarray(fr)
        if seen is None or arr is not seen:
            frames.append(arr)
            seen = arr
        if len(frames) < n:
            time.sleep(1.0 / 60.0)
    return frames


# Zeit-Muster der Etikett-Werte: dieselbe Regel wie im `STICKER_SCHEMA`
# (vision_detect.py) — eine Quelle der Wahrheit für VLM-Scan und manuelle
# Eingabe.
_STICKER_TIME_RE = re.compile(_STICKER_SCHEMA["properties"]["zeit"]["pattern"])


def _is_integer_value(value):
    """True für Ganzzahlen (int, nicht bool) und Ganzzahl-Strings."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, str) and value.strip().lstrip("+-").isdigit()


def validate_sticker_fields(zeit, stand, dg, sch_nr):
    """Etikett-Werte strikt validieren (manuelle Eingabe).

    `zeit` SHALL eine Uhrzeit im Format `HH:MM` sein (Muster des
    `STICKER_SCHEMA`); `stand`, `dg`, `sch_nr` SHALL Ganzzahlen sein (int oder
    Ganzzahl-String). Rückgabe: (ok, error_key) mit dem i18n-Key des ersten
    Fehlers, bzw. (True, None) bei gültigen Werten. Reine Funktion (headless
    testbar).
    """
    if not isinstance(zeit, str) or not _STICKER_TIME_RE.fullmatch(zeit):
        return False, "dialog.measurement.manual_error_time"
    for value in (stand, dg, sch_nr):
        if not _is_integer_value(value):
            return False, "dialog.measurement.manual_error_int"
    return True, None


# Fehler-Kinds der BRSMatch-API → i18n-Keys (Lookup).
_BRSMATCH_LOOKUP_ERRORS = {
    "not_configured": "dialog.measurement.lookup_not_configured",
    "no_belegung": "dialog.measurement.lookup_no_belegung",
    "mismatch": "dialog.measurement.lookup_mismatch",
    "auth": "dialog.measurement.lookup_auth",
    "http": "dialog.measurement.lookup_server",
    "network": "dialog.measurement.lookup_network",
}

# Fehler-Kinds der BRSMatch-API → i18n-Keys (Wertung).
_BRSMATCH_WERTUNG_ERRORS = {
    "not_configured": "dialog.measurement.wertung_not_configured",
    "validation": "dialog.measurement.wertung_validation",
    "no_belegung": "dialog.measurement.wertung_no_belegung",
    "mismatch": "dialog.measurement.wertung_mismatch",
    "auth": "dialog.measurement.wertung_auth",
    "http": "dialog.measurement.wertung_server",
    "network": "dialog.measurement.wertung_network",
}


class BRSViewFilter(object):
    """Orthogonaler Anzeige-Filterzustand (kein Teil der App-FSM).

    Reine per-Pixel-Farbtransformations-Parameter. `active` schaltet die
    Filterkombination global ein/aus (Taste F); die Parameter bleiben beim
    Ausschalten gespeichert und gelten beim erneuten Aktivieren wieder.
    """

    def __init__(self, contrast=1.0, gamma=1.0, brightness=0.0,
                 saturation=1.0, invert=False, gray=False, active=True,
                 tint=False):
        self.contrast = contrast
        self.gamma = gamma
        self.brightness = brightness
        self.saturation = saturation
        self.invert = invert
        self.gray = gray
        self.active = active
        # Eigenständige Anzeige-Option „Hintergrund einfärben" (Ansicht-Menü):
        # unabhängig vom Filter-Aktiv (Taste F), eigener Shader-Uniform-Pfad.
        self.tint = tint

    def is_neutral(self):
        """True, wenn alle Parameter das Bild unverändert lassen."""
        return (self.contrast == 1.0 and self.gamma == 1.0
                and self.brightness == 0.0 and self.saturation == 1.0
                and not self.invert and not self.gray)

    def reset(self):
        self.contrast = 1.0
        self.gamma = 1.0
        self.brightness = 0.0
        self.saturation = 1.0
        self.invert = False
        self.gray = False
        self.tint = False

    def to_dict(self):
        """JSON-fähiges Dict des Filterzustands (alle 8 Parameter)."""
        return {
            "active": self.active,
            "invert": self.invert,
            "gray": self.gray,
            "saturation": self.saturation,
            "contrast": self.contrast,
            "gamma": self.gamma,
            "brightness": self.brightness,
            "tint": self.tint,
        }

    @classmethod
    def from_dict(cls, data):
        """Filterzustand aus einem Settings-Dict laden (value-tolerant).

        Fehlende oder untypisierte Einträge (falscher Typ, Wert außerhalb des
        einstellbaren Bereichs) fallen auf die neutralen Defaults zurück — ein
        beschädigtes `filters`-JSON darf den Start nie blockieren.
        """
        if not isinstance(data, dict):
            return cls()
        filt = cls()

        def _flag(key, default):
            value = data.get(key, default)
            return value if isinstance(value, bool) else default

        def _num(key, default, lo, hi):
            try:
                value = float(data[key])
            except (KeyError, TypeError, ValueError):
                return default
            return value if lo <= value <= hi else default

        filt.active = _flag("active", True)
        filt.invert = _flag("invert", False)
        filt.gray = _flag("gray", False)
        filt.tint = _flag("tint", False)
        filt.saturation = _num("saturation", 1.0, 0.0, 2.0)
        filt.contrast = _num("contrast", 1.0, 0.5, 3.0)
        filt.gamma = _num("gamma", 1.0, 0.5, 2.5)
        filt.brightness = _num("brightness", 0.0, -0.5, 0.5)
        return filt

    def uniforms(self):
        """Reihenfolge entspricht den Shader-Uniforms
        (contrast, gamma, brightness, saturation, invert, gray)."""
        return (self.contrast, self.gamma, self.brightness,
                self.saturation, float(self.invert), float(self.gray))


def filter_pixel(rgb, filt):
    """Reine Referenz der Shader-Filteroperation (CPU-Spiegel).

    Identisch zu `BRSCanvas.fragment` in app.py (siehe design.md D2):
    Sättigung, Negativ, Graustufen, Kontrast/Helligkeit, Gamma. Luma gewichtet
    die Kanäle in der BGR-Reihenfolge, wie sie der Shader aus der Webcam-
    Textur liest (`frag_color.r = texture(webcam, uvr).b`).

    rgb    letzte Achse sind RGB-(-äquivalente) bzw. BGR-Floats in [0,1];
           skaliert auf beliebige Batch-Formen.
    filt   BRSViewFilter mit den Parameterwerten.
    """
    c = np.asarray(rgb, dtype=np.float64)
    luma = c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114
    c = luma[..., None] * (1.0 - filt.saturation) + c * filt.saturation
    if filt.invert:
        c = 1.0 - c
    luma2 = c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114
    k = 0.0 if filt.gray else 1.0
    c = luma2[..., None] * (1.0 - k) + c * k
    c = (c - 0.5) * filt.contrast + 0.5 + filt.brightness
    return np.clip(c, 0.0, 1.0) ** filt.gamma


# Tint-Farbe der Hintergrund-Einfärbung in Shader-/CPU-Kanalreihenfolge.
# WICHTIG: Die Werte werden als **RGB** angewandt — der Fragment-Shader weist sie
# den Uniforms u_tint_r/g/b direkt zu (c ist dort physikalisch (R,G,B)), und der
# CPU-Spiegel `tint_pixel` behandelt Index 0 wie Rot (Konvention `filter_pixel`).
# Leichter Blauton (soft sky blue, #99BFE6), gut abgesetzt vom hellen Papier.
# Empirisch nachjustierbare Konstante (eine Quelle für Shader-Uniforms und
# CPU-Spiegel).
TINT_COLOR_RGB = (0.60, 0.75, 0.90)
# Deckkraft der Hintergrund-Einfärbung (0..1): 1 = opak (voll deckend),
# <1 = semitransparent — die Tisch-Struktur scheint durch die blaue Tönung
# hindurch. Wird als `u_tint`-Uniform angewandt (`mix(c, tint, u_tint*tm)`);
# der Shader macht damit die lineare Mischung bereits von Haus aus.
TINT_OPACITY = 0.5
# Statische Distanz-Schwelle für die Tint-Klassifikation (Skala von
# `similarity()` = abs + 0.5*Struktur-Distanz, Pixel-Werte 0..255). Pixel, deren
# Distanz zur gelernten Referenz unterhalb dieses festen Werts liegen, gelten als
# Tisch/Hintergrund und werden eingefärbt. Bewusst STATISCH (nicht datenabhängig):
# eine adaptive Schwelle wurde durch Glanz-Reflexionen (Metall-Lineal) oder
# Fremdkörper (Hand) aus dem Ruder gerissen. Papier und Fremdkörper liegen mit
# deutlich höherer Distanz sicher oberhalb. Empirisch nachjustierbare Konstante
# (eine Quelle für Shader-Uniforms und CPU-Spiegel).
TINT_THRESHOLD = 20.0
# Kadenz der Tint-Masken-Nachführung im Render-Loop (Sekunden). Die Berechnung
# läuft in Referenz-Skala (~18 ms @4K statt 640 ms Voll-Auflösung) und ist damit
# im 60-fps-Loop tragbar; 0.3 s fühlt sich live an (der ursprüngliche
# Monitor-Takt von 1.5 s wirkte träge).
TINT_UPDATE_S = 0.3


def tint_pixel(rgb, mask, tint, tint_color=TINT_COLOR_RGB):
    """Reine Referenz der Tint-Mischung (CPU-Spiegel des Shader-Blocks).

    Identisch zu `BRSCanvas.fragment` in app.py (design.md D3): Pixel, deren
    Tisch-Maske gesetzt ist, werden mit der homogenen Tint-Farbe gemischt —
    vor den Anzeige-Filtern, in derselben Kanalreihenfolge wie `filter_pixel`.

    rgb          letzte Achse sind RGB-Floats in [0,1]; beliebige Batch-Form.
    mask         Tisch-Maske in [0,1] (0 = Papier, 1 = Tisch/Hintergrund),
                 broadcast-bar gegen die Pixel-Achse (Form ohne letzte Achse).
    tint         Deckkraft-Skalar (0 = aus, 1 = opak, 0.5 = semitransparent) —
                 entspricht der `u_tint`-Uniform.
    tint_color   Tint-Farbe in RGB-Reihenfolge (Default `TINT_COLOR_RGB`).
    """
    c = np.asarray(rgb, dtype=np.float64)
    opacity = float(tint)
    if opacity <= 0.0:
        return c
    m = np.asarray(mask, dtype=np.float64)
    tc = np.asarray(tint_color, dtype=np.float64)
    a = np.clip(m * opacity, 0.0, 1.0)[..., None]
    return c * (1.0 - a) + tc * a


class AppController(object):
    """UI-agnostische, explizite App-State-Maschine (Kalibrier-Workflow)."""

    def __init__(self, canvas, settings_path=None):
        self.canvas = canvas
        self.settings_path = settings_path
        self.state = AppState.IDLE

        # orthogonale Modell-Eigenschaften (nicht Teil der FSM)
        self.measuring_enabled = False
        self.automation = False
        self.caliber_index = 0
        self.filters = self._load_filters()
        self._filters_need_save = False
        self.language = self._load_language()
        _i18n_set_language(self.language)
        _i18n_set_locale()

        # Schriftgrößen-Präset aus Settings geladen und beim Start angewendet
        # (fehlender/ungültiger Eintrag -> Default "normal"; der Canvas skaliert
        # pro Frame per push_font — kein Re-Bake nötig).
        self.font_scale = self._load_font_scale()
        self.canvas.request_font_scale(self.font_scale)

        # Kamera-Einstellungen (Gerät, Preset, Rotation) aus Settings geladen;
        # `_v4l2_runner`/`_preset_opener` sind injizierbar (Tests mocken die
        # Preset-Probe).
        self.camera_device, self.camera_preset, self.camera_rotate = \
            self._load_camera_settings()
        self._camera_presets_cache = {}
        self._v4l2_runner = None
        self._preset_opener = None

        # references set by app wiring
        self.calibration = None
        self.capture_worker = None
        self.ruler = None
        self.mbox = None
        self.indicator = None

        # Loss-of-Calibration-Monitor (orthogonale Modell-Eigenschaft, analog
        # automation): lernt den Tisch-Untergrund nach der Kalibrierung und
        # prüft periodisch gegen den Kameraframe. Der periodische Check läuft
        # in einem eigenen Thread (`_background_monitor_thread`), damit die
        # ORB/Matching/RANSAC-Arbeit den Render-Thread nicht blockiert.
        self.background_model = BackgroundModel()
        self.last_background_check = None
        self.background_learn_error = False
        self.recovery_error = None
        self._pending_background_raw = None
        self._pending_background_overlay = None
        # Referenz auf den eingefrorenen Lern-Overlay-Frame: der Monitor darf
        # ihn nicht als Check-Input verwenden (gezeichnete Keypoints → UNAVAILABLE),
        # bis die Kamera wieder Live-Frames liefert.
        self._learn_overlay_frame = None
        self._background_monitor_thread = None
        # LUTs für den Drift-Ausgleich (gecacht; identisch zu den angewendeten).
        self._background_luts = None
        # Downscaled LUTs für die Tint-Maske (gecacht nach (h, w)).
        self._background_luts_scaled = None
        # Vision-Konfiguration (Config-Maske/Verbindungstest; später genutzt).
        self._vision_config = None
        # Verbindungstest: Status (None | "ok" | "not_configured" |
        # "vision_error" | "no_frame") und Lauf-Flag. Der Test läuft
        # asynchron im Daemon-Thread `_vision_test_thread`;
        # `_vision_test_token` invalidiert veraltete Ergebnisse
        # (neuer Test / `clear_vision_test`) — Muster wie `_lookup_token`.
        self.vision_test_status = None
        self.vision_test_running = False
        self._vision_test_thread = None
        self._vision_test_token = 0

        # BRSMatch: Verbindungskonfiguration (Base-URL/API-Key/Event-ID/
        # Aktivieren) aus Settings geladen; `brsmatch_enabled` gate-t den
        # Etikett-Scan.
        (self.brsmatch_base_url, self.brsmatch_api_key,
         self.brsmatch_event_id, self.brsmatch_enabled) = \
            self._load_brsmatch_config()
        # Letztes Etikett-Scan-Ergebnis (None solange keins) und -Status
        # (None | "running" | "ok" | "error"). Der Scan läuft asynchron in
        # einem Daemon-Thread (`_scan_thread`), damit der UI-/Video-Thread
        # nicht für die VLM-Latenz (~2-3 s) blockiert; Ergebnis- und
        # Status-Zuweisungen sind atomar (GIL) — Muster wie
        # `last_background_check`.
        self.sticker_meta = None
        self.sticker_status = None
        self._scan_thread = None
        # Query-API-Lookup: Status (None | "running" | "ok" | "error"),
        # Ergebnis (LookupResult-Dict) und Fehler (i18n-Key). Der Lookup läuft
        # asynchron im Daemon-Thread `_lookup_thread`; `_lookup_token`
        # invalidiert veraltete Antworten (neuer Scan / Reset).
        self.lookup_status = None
        self.lookup_result = None
        self.lookup_error = None
        self._lookup_thread = None
        self._lookup_token = 0
        # Injizierbarer httpx-Transport für Tests (sonst None).
        self._brs_transport = None
        # Wertung (Scoring-API): Status (None | "running" | "ok" | "error"),
        # Fehler (i18n-Key) und Zeitstempel des letzten Erfolgs. `confirm_*`
        # steuert den Bestätigungsdialog bei vorhandenen Wertungen
        # (existing_scores > 0); `_pending_wertung` hält den Upload-Snapshot
        # zwischen Framebuffer-Kopie und Upload.
        self.wertung_status = None
        self.wertung_error = None
        self.wertung_ok_at = None
        self.confirm_dialog_open = False
        self.confirm_meta = None
        self._pending_wertung = None
        self._wertung_thread = None
        # Manuelle Etikett-Eingabe (Fallback): Dialog-Zustand — offen (bool)
        # und letzter Validierungsfehler (i18n-Key oder None). Über
        # `open_manual_dialog`/`close_manual_dialog` gesteuert.
        self.manual_dialog_open = False
        self.manual_dialog_error = None

        # Referenz-Modus (Messen-Reiter): manuelle Bewertung als Sample
        # speichern (`save_reference`); Info/Fehler im Messung-Fenster.
        self.reference_mode = False
        self.reference_info = None
        self.reference_sample = None
        self.reference_error = None
        self.reference_status_at = None

        # Karten-Qualitätscheck (Kalibrierung-Reiter): Ergebnis/Fehler für den
        # Ergebnis-Dialog; `card_qc_overlay` = Overlay-Frame (eingefroren
        # am Kamera-Frame), `card_qc_circles` = gefundene Kreise bei
        # fehlgeschlagener Rastererkennung. Die Erfassung läuft in einem
        # Daemon-Thread (`card_qc_running`), damit der GL/Render-Thread nicht
        # blockiert; `card_qc_cancel` bricht eine laufende Erfassung ab.
        self.card_qc_result = None
        self.card_qc_error = None
        self.card_qc_overlay = None
        self.card_qc_circles = 0
        self.card_qc_running = False
        self.card_qc_thread = None
        self._card_qc_cancel = False

    # ---- Sprache (orthogonale Modell-Eigenschaft) ----

    def _load_language(self):
        """Sprache aus Settings laden; ohne gespeicherte Wahl aus der
        System-Locale ableiten (deutsche Locales -> de, sonst en)."""
        data = _settings_load(self.settings_path)
        lang = data.get("language")
        if lang in SUPPORTED_LANGUAGES:
            return lang
        return language_from_locale()

    def set_language(self, lang):
        """Sprache sofort wechseln, global setzen und persistent speichern."""
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"unknown language {lang!r}; expected one of {SUPPORTED_LANGUAGES}")
        self.language = lang
        _i18n_set_language(lang)
        _i18n_set_locale()
        _settings_save({"language": lang}, path=self.settings_path)
        return lang

    # ---- Schriftgrößen-Präset (orthogonale Modell-Eigenschaft) ----

    def _load_font_scale(self):
        """Präset-Key aus Settings laden; ohne/ungültigen Eintrag -> Default."""
        data = _settings_load(self.settings_path)
        key = data.get("font_scale")
        if key in FONT_SCALES:
            return key
        return DEFAULT_FONT_SCALE_KEY

    def set_font_scale(self, key):
        """Präset sofort wechseln, an den Canvas durchreichen und persistent
        speichern."""
        if key not in FONT_SCALES:
            raise ValueError(
                f"unknown font scale key {key!r}; expected one of {sorted(FONT_SCALES)}")
        self.font_scale = key
        self.canvas.request_font_scale(key)
        _settings_save({"font_scale": key}, path=self.settings_path)
        return key

    # ---- Kamera (orthogonale Modell-Eigenschaft) ----

    @staticmethod
    def _preset_by_name(name):
        """Preset-Tupel per Namen suchen; None wenn unbekannt."""
        for preset in CAMERA_PRESETS:
            if preset[0] == name:
                return preset
        return None

    @staticmethod
    def _default_preset_for(supported):
        """Default-Preset aus einer unterstützten Liste wählen.

        Bevorzugt 4K (erste unterstützte 4K-Variante), sonst das erste
        unterstützte Preset — 4K ist immer der Default, wenn verfügbar.
        """
        for preset in supported:
            if preset[0].startswith("4K"):
                return preset
        return supported[0]

    def _load_camera_settings(self):
        """Kamera-Einstellungen aus Settings laden; ungültige Werte -> Defaults.

        Device-Default: `/dev/video0`. Ist kein gültiges Preset gespeichert,
        bleibt `camera_preset` None — die eigentliche Wahl (4K bevorzugt,
        sonst erstes unterstütztes) trifft `normalize_camera_preset()` gegen
        das aktive Gerät. Die Rotation ist 0 oder 180 (Montage-Optionen);
        fehlender/ungültiger Wert fällt auf 180 zurück (bisheriges Verhalten).
        """
        data = _settings_load(self.settings_path)
        device = data.get("camera_device", DEFAULT_CAMERA_DEVICE)
        if not isinstance(device, str) or not device:
            device = DEFAULT_CAMERA_DEVICE
        name = data.get("camera_preset")
        preset = self._preset_by_name(name) if isinstance(name, str) else None
        rotate = data.get("camera_rotate", 180)
        if rotate not in (0, 180):
            rotate = 180
        return device, preset, rotate

    def _load_brsmatch_config(self):
        """BRSMatch-Verbindungskonfiguration aus Settings laden.

        Fehlender/ungültiger `brsmatch`-Block -> Defaults (leere Werte,
        Event-ID 0, deaktiviert). Beim ersten Start ohne Block ist der
        Schalter aus. Die Event-ID wird als positive Ganzzahl normalisiert
        (0 = nicht gesetzt).
        """
        data = _settings_load(self.settings_path)
        block = data.get("brsmatch")
        if not isinstance(block, dict):
            return "", "", 0, False
        url = block.get("base_url", "")
        key = block.get("api_key", "")
        event_id = block.get("event_id", 0)
        enabled = bool(block.get("enabled", False))
        if not isinstance(url, str):
            url = ""
        if not isinstance(key, str):
            key = ""
        if isinstance(event_id, bool):
            event_id = 0
        elif isinstance(event_id, int):
            event_id = event_id if event_id > 0 else 0
        elif isinstance(event_id, str) and event_id.strip().isdigit():
            event_id = int(event_id.strip())
            if event_id <= 0:
                event_id = 0
        else:
            event_id = 0
        return url.strip(), key.strip(), event_id, enabled

    def supported_presets(self, device=None):
        """Unterstützte Presets eines Geräts (pro Gerät gecacht).

        Nutzt `probe_supported_presets` mit dem injizierbaren `_v4l2_runner`
        (Default: echter `v4l2-ctl`) und `_preset_opener` (cv2-Fallback). Das
        Ergebnis wird pro Gerät gecacht; ein Gerätewechsel invalidiert den
        Eintrag des alten Geräts implizit (neuer Cache-Key).
        """
        device = device or self.camera_device
        cached = self._camera_presets_cache.get(device)
        if cached is None:
            runner = self._v4l2_runner or _run_v4l2_ctl
            opener = self._preset_opener or default_camera_opener
            cached = probe_supported_presets(device, CAMERA_PRESETS,
                                             run_v4l2=runner, opener=opener)
            self._camera_presets_cache[device] = cached
        return list(cached)

    def normalize_camera_preset(self):
        """Gespeichertes Preset gegen das aktive Gerät prüfen; Fallback falls nötig.

        Ist kein gültiges Preset gesetzt oder wird es am aktuellen Gerät nicht
        unterstützt, wird ein Default gewählt (4K bevorzugt, sonst erstes
        unterstütztes) und persistiert. Rückgabe: aktives Preset-Tupel.
        """
        supported = self.supported_presets(self.camera_device)
        if self.camera_preset not in supported:
            self.camera_preset = self._default_preset_for(supported)
            _settings_save({"camera_preset": self.camera_preset[0]},
                           path=self.settings_path)
        return self.camera_preset

    def apply_camera_settings(self, device, preset, rotate=None):
        """Kamera-Einstellungen sofort anwenden (Neustart der Kamera).

        Wechsel von Gerät, Auflösung oder Rotation setzt Kalibrierung/
        Messzustand zurück (Kalibrierung ist an Auflösung und Bildorientierung
        gebunden). Nicht unterstützte Presets am Ziel-Gerät fallen auf den
        Default (4K bevorzugt, sonst erstes unterstütztes) zurück. `rotate=None`
        behält den aktuellen Wert (abwärtskompatibel). Änderungen werden
        persistent gespeichert.
        """
        if preset is None:
            preset = self.camera_preset
        if rotate is None:
            rotate = self.camera_rotate
        supported = self.supported_presets(device)
        if preset not in supported:
            preset = self._default_preset_for(supported)

        device_changed = device != self.camera_device
        res_changed = (self.camera_preset is None
                       or preset[1] != self.camera_preset[1]
                       or preset[2] != self.camera_preset[2])
        rotate_changed = rotate != self.camera_rotate
        full_reset = device_changed or res_changed or rotate_changed

        self.camera_device = device
        self.camera_preset = preset
        self.camera_rotate = rotate
        _settings_save({
            "camera_device": device,
            "camera_preset": preset[0],
            "camera_rotate": rotate,
        }, path=self.settings_path)

        if self.canvas is not None:
            w, h, fps = preset[1], preset[2], preset[3]
            self.canvas.restart_camera(device, w, h, fps, rotate,
                                       rebuild_calibration=full_reset)
        if full_reset:
            self._reset_measurement_state()
        return self.camera_preset

    def _reset_measurement_state(self):
        """Kalibrier-/Messzustand auf IDLE zurücksetzen (nach Auflösungswechsel)."""
        self.state = AppState.IDLE
        self.measuring_enabled = False
        if self.mbox:
            self.mbox.enabled = False
        if self.ruler:
            self.ruler.enabled = False
            self.ruler.reset_points()
        if self.indicator:
            self.indicator.enabled = False
        self.invalidate_background()
        self.recovery_error = None
        self._pending_background_raw = None
        self._pending_background_overlay = None
        self.reference_status_at = None
        try:
            remove_session_marker()
        except Exception:  # pragma: no cover
            pass
        self.reset_luts()
        self._reset_brsmatch_meta()

    # ---- Transitions (Guards + Side-Effects zentral) ----

    def request_calibration(self):
        """C-Taste/Menü: Bestehende Kalibrierung zurücksetzen (IDLE, Dialog
        erscheint), neuen Kalibriervorgang starten oder aus den Learn-States
        abgebrochen zurück zum IDLE."""
        if self.calibration and self.calibration.calibrated:
            self.reset_calibration_state()
            return False
        if self.state in (AppState.LEARN_PROMPT, AppState.LEARN_RESULT):
            self.cancel_calibration()
            return False
        return self.start_calibration()

    def reset_calibration_state(self):
        """Bestehende Kalibrierung zurücksetzen -> IDLE (Start-Dialog wieder da)."""
        if self.state is not AppState.IDLE:
            self.state = AppState.IDLE
        if self.capture_worker:
            self.capture_worker.paused = False
        if self.calibration:
            self.calibration.calibrated = False
        self.measuring_enabled = False
        if self.mbox:
            self.mbox.enabled = False
        if self.ruler:
            self.ruler.enabled = False
            self.ruler.reset_points()
        if self.indicator:
            self.indicator.enabled = False
        self.invalidate_background()
        self.reset_luts()
        self.dismiss_card_qc()

    def reset_luts(self):
        """Neutrale (unverzerrte) LUTs setzen, damit bei neuer Kalibrierung der
        korrigierte Zustand der vorherigen Kalibrierung nicht mehr sichtbar ist."""
        canvas = self.canvas
        if canvas is None or self.calibration is None:
            return
        default_lut = getattr(canvas, "default_lut", None)
        if default_lut is None:
            default_lut = self.calibration.default_lut_channels()
        # set_luts erwartet [b, g, r]; neutral sind alle drei identisch
        canvas.set_luts([default_lut, default_lut, default_lut])

    def start_calibration(self):
        """IDLE -> CALIBRATING"""
        if self.state is not AppState.IDLE:
            return
        self.reset_luts()
        self.recovery_error = None
        self.capture_worker.paused = False
        if self.calibration and self.calibration.calibrated:
            self.calibration.calibrated = False
            if self.indicator:
                self.indicator.enabled = False
        # Kamera-Kontext fürs Sidecar-Snapshot aktuell setzen
        self.calibration.device = self.camera_device
        self.calibration.preset_name = self.camera_preset[0] if self.camera_preset else None
        self.calibration.rotate = self.camera_rotate
        self.capture_worker.pause()
        # 3 aufeinanderfolgende Frames einsammeln (Kamera kurz laufen lassen),
        # dann wieder einfrieren und kalibrieren (Rauschreduktion √N).
        self.capture_worker.unpause()
        frames = _collect_frames(self.capture_worker, QC_SAMPLE_FRAMES)
        self.capture_worker.pause()
        ret = self.calibration.calibrate(frames)
        if ret:
            self.capture_worker.current_frame = self.calibration.visual
            self.state = AppState.RESULT
            return True
        else:
            self.capture_worker.unpause()
            self.state = AppState.IDLE
            return False

    def calibration_succeeded(self):
        """CALIBRATING -> RESULT"""
        if self.state is not AppState.CALIBRATING:
            return
        self.state = AppState.RESULT

    def calibration_failed(self):
        """CALIBRATING -> IDLE"""
        if self.state is not AppState.CALIBRATING:
            return
        self.state = AppState.IDLE
        self.capture_worker.unpause()

    def accept_calibration(self):
        """RESULT -> LEARN_PROMPT"""
        if self.state is not AppState.RESULT:
            return
        luts = self.calibration.compute_lut_channels()
        if luts is not None:
            self.canvas.set_luts(luts)
        self.capture_worker.paused = False
        self.state = AppState.LEARN_PROMPT
        self.background_learn_error = False
        return True

    def cancel_calibration(self):
        """RESULT/LEARN_PROMPT/LEARN_RESULT -> IDLE (Abbruch des Workflows)"""
        if self.state not in (AppState.RESULT, AppState.LEARN_PROMPT,
                              AppState.LEARN_RESULT):
            return
        self.state = AppState.IDLE
        self.capture_worker.paused = False
        if self.calibration:
            self.calibration.calibrated = False
        self.measuring_enabled = False
        if self.mbox:
            self.mbox.enabled = False
        if self.ruler:
            self.ruler.enabled = False
            self.ruler.reset_points()
        if self.indicator:
            self.indicator.enabled = False
        self.invalidate_background()
        self.recovery_error = None
        self._pending_background_raw = None
        self._pending_background_overlay = None
        try:
            remove_session_marker()
        except Exception:  # pragma: no cover
            pass
        self.dismiss_card_qc()

    def reset(self):
        """MEASURING -> IDLE"""
        if self.state is not AppState.MEASURING:
            return
        self.state = AppState.IDLE
        self.capture_worker.paused = False
        self.calibration.calibrated = False
        self.measuring_enabled = False
        self.mbox.enabled = False
        self.ruler.enabled = False
        self.ruler.reset_points()
        self.indicator.enabled = False
        self.invalidate_background()
        self.recovery_error = None
        self._pending_background_raw = None
        self._pending_background_overlay = None
        try:
            remove_session_marker()
        except Exception:  # pragma: no cover
            pass
        self.dismiss_card_qc()
        self._reset_brsmatch_meta()

    # ---- Vision-Konfiguration (Config-Maske) ----

    def get_vision_config(self):
        """Aktuelle Vision-Konfiguration als Dict (für die Config-Maske)."""
        cfg = _VisionConfig.from_settings(
            path=getattr(self, "settings_path", None))
        return {
            "base_url": cfg.base_url,
            "api_key": cfg.api_key,
            "model": cfg.model,
            "configured": cfg.configured,
        }

    def set_vision_config(self, base_url, model, api_key):
        """Vision-Konfiguration persistieren (`settings.json` → `vision`-Block)."""
        _settings_save({"vision": {
            "base_url": (base_url or "").strip(),
            "model": (model or "").strip(),
            "api_key": (api_key or "").strip(),
        }}, path=getattr(self, "settings_path", None))
        self._vision_config = _VisionConfig(
            base_url=base_url, model=model, api_key=api_key)

    def test_vision_connection(self, base_url=None, model=None, api_key=None):
        """Verbindung zum konfigurierten Endpunkt testen (Mini-Call, synchron).

        Nutzt das aktuelle Kamerabild; Rückgabe: Status-String aus
        `("ok" | "not_configured" | "vision_error" | "no_frame")`.

        Werden `base_url`/`model`/`api_key` übergeben, gilt genau diese
        (ge-stripte) Konfiguration — ohne Persistierung. Andernfalls die
        gespeicherte Konfiguration (Settings + Env-Prezedenz). Blockiert
        den aufrufenden Thread für die Dauer des Netzwerk-Calls; die UI
        nutzt dafür `start_vision_test`.
        """
        return self._run_vision_test(self._vision_test_config(
            base_url, model, api_key))

    def _vision_test_config(self, base_url, model, api_key):
        """Test-Konfiguration: übergebene Werte oder die gespeicherte."""
        if base_url is None and model is None and api_key is None:
            return _VisionConfig.from_settings(
                path=getattr(self, "settings_path", None))
        return _VisionConfig(base_url=base_url, model=model,
                             api_key=api_key)

    def _run_vision_test(self, cfg):
        """Synchronen Test-Call ausführen (Status-String, siehe
        `test_vision_connection`)."""
        if not cfg.configured:
            return "not_configured"
        frame = None
        if self.capture_worker is not None:
            frame = self.capture_worker.current_frame
        if frame is None:
            return "no_frame"
        try:
            from .vision_detect import VisionClient
        except ImportError:  # als Script (app.py): keine Paket-Relativ-Imports
            from vision_detect import VisionClient
        try:
            client = VisionClient(cfg)
            raw = client.detect(frame)
            if raw.strip():
                return "ok"
            return "vision_error"
        except Exception:  # pragma: no cover
            return "vision_error"

    def start_vision_test(self, base_url, model, api_key):
        """Asynchronen Verbindungstest starten (siehe `_start_lookup`).

        Der Netzwerk-Call läuft in einem Daemon-Thread; der UI-Thread wird
        nicht blockiert. Ein laufender Test wird über einen Token-Stoß
        invalidiert, sodass veraltete Ergebnisse verworfen werden.
        `vision_test_running` ist während des Laufs True;
        `vision_test_status` hält das Ergebnis-String, nur falls der Token
        noch aktuell ist.
        """
        self._vision_test_token += 1
        token = self._vision_test_token
        self.vision_test_running = True
        self.vision_test_status = None
        thread = threading.Thread(
            target=self._vision_test_worker,
            args=(token, base_url, model, api_key), daemon=True)
        self._vision_test_thread = thread
        thread.start()

    def _vision_test_worker(self, token, base_url, model, api_key):
        """Verbindungstest im Hintergrund-Thread (siehe `start_vision_test`).

        Ergebnis- und Status-Zuweisungen sind atomar (GIL) und werden nur
        übernommen, wenn der Token noch aktuell ist.
        """
        try:
            status = self._run_vision_test(self._vision_test_config(
                base_url, model, api_key))
        except Exception:  # noqa: BLE001 — defensiv als Verbindungsfehler
            status = "vision_error"
        finally:
            if token == self._vision_test_token:
                self.vision_test_status = status
                self.vision_test_running = False
                self._vision_test_thread = None

    def clear_vision_test(self):
        """Verbindungstest-Zustand zurücksetzen (Feld-Änderung,
        Dialog-Schließen).

        Invalidiert einen laufenden Test über einen Token-Stoß: dessen
        Ergebnis wird nicht mehr übernommen.
        """
        self._vision_test_token += 1
        self.vision_test_status = None
        self.vision_test_running = False

    # ---- BRSMatch (Mock: Konfiguration + Etikett-Scan) ----

    def get_brsmatch_config(self):
        """Aktuelle BRSMatch-Konfiguration als Dict (für die Config-Maske)."""
        return {
            "base_url": self.brsmatch_base_url,
            "api_key": self.brsmatch_api_key,
            "event_id": self.brsmatch_event_id,
            "enabled": self.brsmatch_enabled,
        }

    def set_brsmatch_config(self, base_url, api_key, event_id, enabled):
        """BRSMatch-Konfiguration setzen und persistent speichern.

        Persistiert den `brsmatch`-Block in den Settings; der Aktivieren-Zustand
        steuert das Gate für den Etikett-Scan. Die Event-ID wird als positive
        Ganzzahl normalisiert (0 = nicht gesetzt).
        """
        url = (base_url or "").strip()
        key = (api_key or "").strip()
        if isinstance(event_id, bool):
            event_id = 0
        elif isinstance(event_id, int):
            event_id = event_id if event_id > 0 else 0
        elif isinstance(event_id, str) and event_id.strip().isdigit():
            event_id = int(event_id.strip())
            if event_id <= 0:
                event_id = 0
        else:
            event_id = 0
        self.brsmatch_base_url = url
        self.brsmatch_api_key = key
        self.brsmatch_event_id = event_id
        self.brsmatch_enabled = bool(enabled)
        _settings_save({"brsmatch": {
            "base_url": url,
            "api_key": key,
            "event_id": event_id,
            "enabled": bool(enabled),
        }}, path=self.settings_path)

    def _adopt_sticker_meta(self, meta):
        """Etikett-Werte übernehmen — gemeinsamer Übernahme-Schritt.

        Einzige Stelle, die `sticker_meta` setzt und `sticker_status` auf "ok"
        stellt. VLM-Scan und manuelle Eingabe laufen hier zusammen; anschließend
        wird der asynchrone Query-API-Lookup gestartet (`_start_lookup`).
        """
        self.sticker_meta = meta
        self.sticker_status = "ok"
        self._start_lookup(meta)

    # ---- BRSMatch Query-API (Lookup) ----

    def _start_lookup(self, meta):
        """Asynchronen Query-API-Lookup für die übernommenen Etikett-Werte starten.

        Nur bei aktiviertem BRSMatch; ohne Konfiguration schlägt der Lookup
        mit `not_configured` fehl (im Messung-Dialog angezeigt). Ein laufender
        Lookup wird über einen Token-Stoß invalidiert, sodass veraltete
        Antworten verworfen werden. Ergebnis/Fehler landen atomar (GIL) in
        `lookup_result`/`lookup_error`/`lookup_status`; der UI-/Video-Thread
        wird nicht blockiert.
        """
        if not self.brsmatch_enabled:
            return
        self._lookup_token += 1
        token = self._lookup_token
        self.lookup_status = "running"
        self.lookup_result = None
        self.lookup_error = None
        self.confirm_dialog_open = False
        self.confirm_meta = None
        thread = threading.Thread(
            target=self._lookup_worker, args=(token, meta), daemon=True)
        self._lookup_thread = thread
        thread.start()

    def _lookup_worker(self, token, meta):
        """Query-API-Call im Hintergrund-Thread ausführen (siehe `_start_lookup`)."""
        try:
            result = _brs_lookup(
                self.get_brsmatch_config(),
                meta["sch_nr"], meta["dg"], meta["stand"], meta["zeit"],
                transport=self._brs_transport)
            self._apply_lookup_result(token, meta, result)
        except _BrsmatchError as exc:
            self._apply_lookup_error(token, meta, exc.kind)
        except Exception:  # noqa: BLE001 — defensiv als Server-Fehler
            self._apply_lookup_error(token, meta, "http")
        finally:
            if token == self._lookup_token:
                self._lookup_thread = None

    def _apply_lookup_result(self, token, meta, result):
        """Lookup-Ergebnis übernehmen, falls die Antwort noch aktuell ist."""
        if not self._lookup_current(token, meta):
            return
        self.lookup_result = result.to_dict()
        self.lookup_status = "ok"
        self.lookup_error = None

    def _apply_lookup_error(self, token, meta, kind):
        """Lookup-Fehler übernehmen, falls die Antwort noch aktuell ist."""
        if not self._lookup_current(token, meta):
            return
        self.lookup_result = None
        self.lookup_status = "error"
        self.lookup_error = _BRSMATCH_LOOKUP_ERRORS.get(
            kind, "dialog.measurement.lookup_server")

    def _lookup_current(self, token, meta):
        """True, wenn die Antwort noch zum aktuellen Lookup gehört.

        Antworten sind veraltet, wenn seit Auslösung ein neuer Lookup
        gestartet oder die Etikett-Werte ersetzt/zurückgesetzt wurden.
        """
        return token == self._lookup_token and self.sticker_meta == meta

    # ---- BRSMatch Scoring-API (Wertung) ----

    def request_wertung(self):
        """„Wertung"-Button: Bestätigung anfordern oder Framebuffer-Kopie auslösen.

        Guards: BRSMatch aktiv, Lookup erfolgreich, Messwert vorhanden, kein
        laufender Upload. Bei `existing_scores > 0` öffnet sich der
        Bestätigungsdialog (Upload erst nach Bestätigung); sonst wird sofort
        die Framebuffer-Kopie angefordert (`canvas.request_wertung_capture`).
        Rückgabe: True, wenn eine Aktion gestartet wurde.
        """
        if not self.brsmatch_enabled:
            return False
        if self.lookup_status != "ok" or self.lookup_result is None:
            return False
        if self.mbox is None or self.mbox.distance < 0:
            return False
        if self.wertung_status == "running":
            return False
        if self.lookup_result["existing_scores"] > 0:
            self.confirm_meta = self._wertung_snapshot()
            self.confirm_dialog_open = True
            return True
        self._pending_wertung = self._wertung_snapshot()
        if self.canvas is not None:
            self.canvas.request_wertung_capture()
        return True

    def confirm_overwrite(self):
        """Überschreiben bestätigen: Bestätigungsdialog schließen, Upload anstoßen."""
        if not self.confirm_dialog_open or self.confirm_meta is None:
            return False
        self._pending_wertung = self.confirm_meta
        self.confirm_dialog_open = False
        self.confirm_meta = None
        if self.canvas is not None:
            self.canvas.request_wertung_capture()
        return True

    def cancel_overwrite(self):
        """Überschreiben verwerfen: Bestätigungsdialog ohne Upload schließen."""
        self.confirm_dialog_open = False
        self.confirm_meta = None

    def _wertung_snapshot(self):
        """Upload-Snapshot aus dem aktuellen Lookup-/Messzustand bauen.

        Enthält Etikett-Werte, Gruppenmaß (`Mitte`) und `existing_scores` aus
        dem Lookup-Ergebnis. Der Snapshot entkoppelt den Upload von späteren
        Zustandsänderungen (neuer Scan, Reset) zwischen Klick und Framebuffer-
        Kopie.
        """
        meta = self.sticker_meta or {}
        result = self.lookup_result or {}
        return {
            "sch_nr": meta.get("sch_nr"),
            "dg": meta.get("dg"),
            "stand": meta.get("stand"),
            "zeit": meta.get("zeit", ""),
            "group_mm": self.mbox.distance if self.mbox is not None else -1.0,
            "existing_scores": result.get("existing_scores", 0),
        }

    def on_wertung_capture(self, png_bytes):
        """Framebuffer-Kopie (JPEG) aus dem Render-Loop entgegennehmen und uploaden.

        Prüft die Guards erneut (Lookup ok, Messwert vorhanden, kein laufender
        Upload) und startet den Upload in einem Daemon-Thread. Bei Erfolg
        werden die BRSMatch-Metadaten zurückgesetzt und der Erfolg kurz
        angezeigt; bei Fehler bleiben die Metadaten für einen erneuten Versuch
        erhalten.
        """
        if not self.brsmatch_enabled:
            return
        if self.lookup_status != "ok" or self.lookup_result is None:
            return
        if self.mbox is None or self.mbox.distance < 0:
            return
        if self.wertung_status == "running":
            return
        snapshot = self._pending_wertung or self._wertung_snapshot()
        self._pending_wertung = None
        self.wertung_status = "running"
        self.wertung_error = None
        thread = threading.Thread(
            target=self._wertung_worker,
            args=(snapshot, png_bytes), daemon=True)
        self._wertung_thread = thread
        thread.start()

    def _wertung_worker(self, snapshot, png_bytes):
        """Scoring-API-Call im Hintergrund-Thread ausführen (siehe `on_wertung_capture`)."""
        try:
            _brs_submit_measurement(
                self.get_brsmatch_config(),
                snapshot["sch_nr"], snapshot["dg"], snapshot["stand"],
                snapshot["zeit"], snapshot["group_mm"],
                screenshot_img=png_bytes,
                transport=self._brs_transport)
            self.wertung_status = "ok"
            self.wertung_ok_at = time.monotonic()
            self.wertung_error = None
            self._reset_brsmatch_meta()
        except _BrsmatchError as exc:
            self.wertung_status = "error"
            self.wertung_error = _BRSMATCH_WERTUNG_ERRORS.get(
                exc.kind, "dialog.measurement.wertung_server")
        except Exception:  # noqa: BLE001 — defensiv als Server-Fehler
            self.wertung_status = "error"
            self.wertung_error = "dialog.measurement.wertung_server"
        finally:
            self._wertung_thread = None

    def _reset_brsmatch_meta(self):
        """BRSMatch-Metadaten im Messung-Dialog zurücksetzen.

        Setzt Etikett-Werte, Lookup-Ergebnis/-Status und Wertung-Status zurück
        (auch nach erfolgreichem Upload), damit nicht irrtümlich eine zweite
        Wertung für dieselben Etikett-Werte hochgeladen wird. Ein laufender
        Lookup wird über den Token-Stoß invalidiert.
        """
        self._lookup_token += 1
        self.sticker_meta = None
        self.sticker_status = None
        self.lookup_status = None
        self.lookup_result = None
        self.lookup_error = None
        self.wertung_error = None
        self.confirm_dialog_open = False
        self.confirm_meta = None
        self._pending_wertung = None

    def open_manual_dialog(self):
        """Manuellen Etikett-Eingabe-Dialog öffnen (Fehlerzustand zurücksetzen)."""
        self.manual_dialog_open = True
        self.manual_dialog_error = None

    def close_manual_dialog(self):
        """Manuellen Etikett-Eingabe-Dialog schließen (ohne Übernahme)."""
        self.manual_dialog_open = False
        self.manual_dialog_error = None

    def manual_sticker(self, zeit, stand, dg, sch_nr):
        """Etikett-Werte manuell übernehmen (Fallback zum VLM-Scan).

        Validiert strikt; bei ungültigen Werten wird nichts übernommen und der
        i18n-Key des Fehlers zurückgegeben (der Dialog zeigt ihn an). Bei
        Erfolg laufen die Werte über `_adopt_sticker_meta` — denselben
        Übernahme-Schritt wie der VLM-Scan. Rückgabe: Fehler-Key oder None.
        """
        ok, error = validate_sticker_fields(zeit, stand, dg, sch_nr)
        if not ok:
            return error
        self._adopt_sticker_meta({
            "zeit": str(zeit),
            "stand": int(stand),
            "dg": int(dg),
            "sch_nr": int(sch_nr),
        })
        self.close_manual_dialog()
        return None

    def scan_sticker(self):
        """Etikett-Scan asynchron auslösen (BRSMatch-Mock).

        Guard: nur bei aktiviertem BRSMatch und im Messbetrieb (`MEASURING`),
        und nur wenn kein Scan läuft. Setzt `sticker_status` sofort auf
        "running", friert den aktuellen Kameraframe ein (Kopie) und startet
        einen Daemon-Thread, der `extract_sticker` (VLM) aufruft. Der Thread
        schreibt das Ergebnis atomar in `sticker_meta`/`sticker_status`
        ("ok"/"error"); der UI-/Video-Thread wird nicht blockiert. Wirft
        keine Exception nach außen.
        """
        if not self.brsmatch_enabled:
            return
        if self.state is not AppState.MEASURING:
            return
        if self.sticker_status == "running" or self._scan_thread is not None:
            return
        frame = None
        if self.capture_worker is not None:
            frame = self.capture_worker.current_frame
        if frame is None:
            self.sticker_status = "error"
            return
        # Frame einfrieren (der Kamera-Thread ersetzt current_frame weiter).
        frozen = frame.copy() if hasattr(frame, "copy") else frame
        self.sticker_status = "running"
        thread = threading.Thread(
            target=self._scan_sticker_worker, args=(frozen,), daemon=True)
        self._scan_thread = thread
        thread.start()

    def _scan_sticker_worker(self, frame):
        """VLM-Scan im Hintergrund-Thread ausführen (siehe `scan_sticker`)."""
        try:
            meta = _extract_sticker(
                frame, config=_VisionConfig.from_settings(
                    path=getattr(self, "settings_path", None)))
            self._adopt_sticker_meta(meta)
        except Exception:  # noqa: BLE001 — VLM-Fehler als Status, kein Crash
            self.sticker_meta = None
            self.sticker_status = "error"
        finally:
            self._scan_thread = None

    # ---- Modell-Aktionen ----

    def set_caliber(self, index):
        self.caliber_index = index
        if self.mbox:
            self.mbox.set_index(index)
        if self.ruler:
            self.ruler.update(circles=True)

    def increment_caliber(self, direction):
        """Kaliber zyklisch weiter-/zurückschalten (Tasten 1/2)."""
        n = len(self.mbox.cal)
        self.caliber_index = (self.caliber_index + direction) % n
        if self.mbox:
            self.mbox.set_index(self.caliber_index)
        if self.ruler:
            self.ruler.update(circles=True)

    def toggle_automation(self):
        self.automation = not self.automation
        if self.indicator:
            self.indicator.automation = self.automation
        return self.automation

    # ---- Loss-of-Calibration-Monitor (orthogonal) ----

    def learn_background(self):
        """Untergrund (freie Tischfläche) lernen — Workflow-Schritt 3.

        LEARN_PROMPT -> LEARN_RESULT: friert die Kamera ein, lernt den Frame und
        zeigt die Keypoint-Visualisierung. Bei Fehlschlag (zu strukturarm) bleibt
        der Zustand LEARN_PROMPT mit gesetztem Fehler. Rückgabe: True/False.
        """
        if self.state is not AppState.LEARN_PROMPT:
            return False
        if self.capture_worker is None:
            return False
        self.capture_worker.pause()
        try:
            frame = self.capture_worker.current_frame
            # Dichte Referenz = LUT-entzerrter Frame (identische Geometrie wie
            # die Gruppenerkennung); ohne gültige LUTs bleibt der Roh-Frame.
            undist = undistort_frame(frame, self._get_background_luts())
            ok = self.background_model.learn(frame, reference=undist)
        except Exception:
            ok = False
            frame = None
        if not ok:
            # Kamera wieder freigeben, im Lern-Schritt bleiben (erneut versuchbar)
            self.capture_worker.unpause()
        self.background_learn_error = not ok
        if ok:
            vis = draw_keypoints(frame, self.background_model.keypoints)
            if vis is not None:
                self.capture_worker.current_frame = vis
            # Hintergrund-Frames für das volle Set zwischenspeichern (Persistenz
            # erst bei `finish_background` — immer das komplette Set).
            self._pending_background_raw = frame
            self._pending_background_overlay = vis
            self._learn_overlay_frame = vis
            self.last_background_check = CheckResult(MonitorStatus.OK, 0.0)
            self.state = AppState.LEARN_RESULT
        return ok

    def finish_background(self):
        """LEARN_RESULT -> MEASURING (Workflow-Schritt 4 abschließen).

        Persistiert erst hier das **volle Set** (Kalibrierung + Hintergrund +
        Marker) — eine Kalibrierung wird nur gespeichert, wenn auch der
        Hintergrund mit Keypoints vorliegt.
        """
        if self.state is not AppState.LEARN_RESULT:
            return
        self.mbox.enabled = True
        self.ruler.enabled = True
        self.ruler.reset_points()
        self.indicator.enabled = True
        self.capture_worker.paused = False
        self.measuring_enabled = True
        self.state = AppState.MEASURING
        # Bis zum ersten Live-Check zeigt der Indikator "ok" (sofort nach dem
        # Abschließen), statt das eingefrorene Overlay-Bild zu prüfen.
        self.last_background_check = CheckResult(MonitorStatus.OK, 0.0)
        # Volles Set schreiben (fehlertolerant; blockiert Messung nie) — Fehler
        # werden gemeldet, damit ein fehlgeschlagener Snapshot nicht still ist.
        try:
            # Hintergrund-PNGs LUT-entzerrt persistieren (Geometrie wie der
            # Shader); ohne gültige LUTs bleibt der Roh-Frame erhalten.
            luts = None
            try:
                luts = self.calibration.compute_lut_channels()
            except Exception:  # pragma: no cover
                luts = None
            bg_raw = undistort_frame(self._pending_background_raw, luts)
            bg_overlay = undistort_frame(self._pending_background_overlay, luts)
            save_full_session(self.calibration, self.background_model,
                              bg_raw, bg_overlay)
        except Exception as exc:  # pragma: no cover
            print(f"[recovery] finish save_full_session failed: {exc}", flush=True)
        self._pending_background_raw = None
        self._pending_background_overlay = None
        self.recovery_error = None
        return True

    def invalidate_background(self):
        """Gelerntes Untergrund-Modell verwerfen (Kalibrierung ungültig)."""
        self.background_model = BackgroundModel()
        self.last_background_check = None
        self.background_learn_error = False
        self._learn_overlay_frame = None
        self._background_luts = None
        self._background_luts_scaled = None

    def _get_background_luts(self):
        """LUTs für den Drift-Ausgleich liefern (gecacht).

        Identisch zu den im Shader angewendeten LUTs; ohne Kalibrierung None
        (undistort_frame bleibt dann ein No-op).
        """
        if self._background_luts is None:
            try:
                self._background_luts = self.calibration.compute_lut_channels()
            except Exception:  # pragma: no cover
                self._background_luts = None
        return self._background_luts

    def _get_background_luts_scaled(self, h, w):
        """Voll aufgelöste LUTs auf eine Ziel-Auflösung herunterskaliert (gecacht).

        `undistort_frame` verlangt LUTs in Frame-Shape; die GPU-LUTs sind
        Vollauflösung. `downscale_luts` dekodiert die 16-Bit-Koordinaten,
        skaliert die Koordinatenfelder per INTER_AREA und kodiert sie wieder —
        korrekt für Koordinaten, nicht für Bytes. Gecacht nach (h, w); ohne
        gültige Kalibrierung None (`undistort_frame` bleibt dann No-op).
        """
        key = (int(h), int(w))
        if self._background_luts_scaled is not None \
                and self._background_luts_scaled[0] == key:
            return self._background_luts_scaled[1]
        luts = self._get_background_luts()
        scaled = downscale_luts(luts, h, w)
        self._background_luts_scaled = (key, scaled)
        return scaled

    def start_background_monitor(self):
        """Periodischen Check-Thread starten (idempotent).

        Vom App-Loop nach dem Wiring aufgerufen; der Thread taktet sich selbst
        mit `CHECK_CADENCE_S` und ruft `check_background()` auf.
        """
        if (self._background_monitor_thread is not None
                and self._background_monitor_thread.is_alive()):
            return
        self._background_monitor_thread = BackgroundMonitorThread(
            check_cb=self.check_background, cadence=CHECK_CADENCE_S)
        self._background_monitor_thread.start()

    def stop_background_monitor(self, timeout=2.0):
        """Check-Thread stoppen (Setzen des Stop-Events, kurzer Join)."""
        thread = self._background_monitor_thread
        self._background_monitor_thread = None
        if thread is not None and thread.is_alive():
            thread.stop()
            thread.join(timeout=timeout)

    def check_background(self, update_reference=True):
        """Ein einzelner Loss-of-Calibration-Check (vom Monitor-Thread getaktet).

        Läuft nur bei gelerntem Modell, im Zustand MEASURING und mit vorhandenem
        Kamera-Frame; sonst None (überspringen). Schreibt `last_background_check`
        und liefert das aktuelle `CheckResult`. Der Thread ist der einzige
        Aufrufer; die Punkte werden über den Roh-Frame aus `current_frame`
        (kein GPU-Roundtrip) ausgewertet.

        `update_reference=False` unterdrückt den Drift-Ausgleich der dichten
        Referenz — für den synchronen Sofort-Check nach der Wiederherstellung,
        der im UI-Thread läuft (das teure `undistort_frame`/LUT-Rechen würde
        die GUI blockieren). Der periodische Monitor-Tick macht den Ausgleich.
        """
        if self.state is not AppState.MEASURING:
            return None
        model = self.background_model
        if not model.learned:
            return None
        if self.capture_worker is None or self.calibration is None:
            return None
        frame = self.capture_worker.current_frame
        if frame is None:
            return None
        # Eingefrorener Lern-Overlay (Keypoints eingezeichnet): kein gültiger
        # Check-Input — bis die Kamera wieder Live-Frames schreibt überspringen.
        if self._learn_overlay_frame is not None and frame is self._learn_overlay_frame:
            return self.last_background_check
        result = model.check(frame, self.calibration)
        # Nur zurückschreiben, solange Modell und Zustand unverändert sind
        # (Invalidierung im UI-Thread tauscht `background_model` aus).
        if self.background_model is model and self.state is AppState.MEASURING:
            prev = getattr(self.last_background_check, "status", None)
            self.last_background_check = result
            if (result.status == MonitorStatus.UNAVAILABLE
                    and prev != MonitorStatus.UNAVAILABLE):
                info = getattr(model, "last_check_info", {})
                print(f"[monitor] UNAVAILABLE: {info}", flush=True)
        # Drift-Ausgleich der dichten Referenz: nur bei Status OK und geringer
        # Verschiebung — exakt die Phasen zwischen Messungen, in denen der
        # Tisch frei sichtbar und die Kamera stabil ist. Wird für den
        # synchronen Sofort-Check nach der Wiederherstellung unterdrückt.
        if (update_reference
                and result.status == MonitorStatus.OK
                and model.has_reference
                and result.deviation_mm
                < REFERENCE_UPDATE_DEVIATION_FACTOR * DEVIATION_THRESHOLD_MM):
            self._update_background_reference(model, frame)
        return result

    def _update_background_reference(self, model, frame):
        """Dichte Referenz per EMA nachführen + periodisch ORB neu ableiten.

        Läuft im Monitor-Thread. Verwendet die LUT-entzerrte Ansicht für die
        konservative Tisch-Maske (nur sichere Tisch-Pixel) und aktualisiert
        die Referenz; alle `REFERENCE_UPDATE_EVERY` Ticks werden die
        ORB-Keypoints aus der nachgeführten Roh-Referenz neu abgeleitet.
        """
        try:
            undist = undistort_frame(frame, self._get_background_luts())
            mask = table_mask(model.reference, undist, tight=True)
            model.update_reference(frame, undist, mask, alpha=REFERENCE_ALPHA)
            model.reference_ticks += 1
            if model.reference_ticks >= REFERENCE_UPDATE_EVERY:
                model.relearn_from_reference()
        except Exception as exc:  # pragma: no cover
            print(f"[monitor] background reference update failed: {exc}",
                  flush=True)

    def update_tint_mask(self):
        """Tisch-Maske für die Tint-Anzeige nachführen (Render-Loop, gedrosselt).

        Berechnet die Maske in **halber Referenz-Skala** (kein Voll-Auflösungs-
        undistort): Downscale von Frame und Referenz auf ~1/8 der Pixel, dann
        `undistort_frame` mit downscaled (gecachten) LUTs und `table_mask`.
        Das ist ~30x billiger als der ursprüngliche Pfad (~18 ms @4K statt
        640 ms) und damit im 60-fps-Loop tragbar; die Maske ist eine reine
        Anzeige-Hilfe (GL_LINEAR glättet die Kante). Compute und Textur-Upload
        laufen im selben Render-Pass (race-frei, kein Monitor-Thread).

        Die Klassifikation verwendet einen **statischen** Distanz-Schwellwert
        (`TINT_THRESHOLD`) auf der pixelweisen Distanz zur gelernten Referenz —
        kein datenabhängiger Cut, keine Schwellen-Schätzung aus Live-Frames.
        Dadurch ist das Verhalten deterministisch und stabil: Papier,
        Fremdkörper (Hand) und Glanz-Reflexionen (Metall-Lineal) liegen weit
        oberhalb der Schwelle und werden nie eingefärbt. Ergebnis wird auf dem
        Modell abgelegt (`tint_mask`/`tint_tick`). Rückgabe: True wenn eine
        neue Maske berechnet wurde.
        """
        if not self.filters.tint:
            return False
        model = self.background_model
        if not model.has_reference:
            return False
        if self.capture_worker is None:
            return False
        frame = self.capture_worker.current_frame
        if frame is None:
            return False
        waiting = getattr(self.capture_worker, "waiting_screen", None)
        if waiting is not None and frame is waiting:
            return False
        if self._learn_overlay_frame is not None and frame is self._learn_overlay_frame:
            return False
        try:
            rh, rw = model.reference.shape[:2]
            hh, hw = max(1, rh // 2), max(1, rw // 2)
            if frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            ref = cv2.resize(model.reference, (hw, hh),
                             interpolation=cv2.INTER_AREA)
            small = cv2.resize(frame, (hw, hh),
                               interpolation=cv2.INTER_AREA)
            luts = self._get_background_luts_scaled(hh, hw)
            undist = undistort_frame(small, luts)
            mask = table_mask(ref, undist, tight=False, threshold=TINT_THRESHOLD)
            model.tint_mask = np.asarray(mask, dtype=np.uint8)
            model.tint_tick += 1
            return True
        except Exception as exc:  # pragma: no cover
            print(f"[app] tint mask update failed: {exc}", flush=True)
            return False

    # ---- Referenz-Modus (manuelle Bewertung als Sample speichern) ----

    def toggle_reference_mode(self):
        """Referenz-Modus umschalten (Messen-Reiter)."""
        self.reference_mode = not self.reference_mode
        if not self.reference_mode:
            self.reference_info = None
            self.reference_sample = None
            self.reference_error = None
            self.reference_status_at = None
        return self.reference_mode

    def save_reference(self):
        """Manuelle Bewertung als neues Sample speichern (`datasets/sample_NN/`).

        Schreibt ein aufsteigend nummeriertes `sample_NN/`-Verzeichnis in die
        Dataset-Wurzel (`BRS_REFERENCE_DATASET` oder Repo-`datasets/`) mit
        allem Selbst-enthaltenen: rohes + LUT-entzerrtes Bild, Kalibrierung
        (Sidecar + Karten-Bilder), Untergrund (Keypoints + dichte Referenz)
        und die manuellen Messpunkte in Weltmetrik.

        Voraussetzungen: Messmodus, aktiver Referenz-Modus, mindestens ein
        Messpunkt, gültige Kalibrierung, Kamera-Frame und gelernte Referenz.
        Rückgabe: True/False; Fehlercode über `reference_error`.
        """
        self.reference_status_at = time.monotonic()
        if self.state is not AppState.MEASURING:
            self.reference_info = None
            self.reference_error = "not_measuring"
            return False
        if not self.reference_mode:
            self.reference_info = None
            self.reference_error = "mode_off"
            return False
        if self.ruler is None or self.ruler.point_count == 0:
            self.reference_info = None
            self.reference_error = "no_points"
            return False
        cal = self.calibration
        if self.capture_worker is None or cal is None \
                or getattr(cal, "mat", None) is None \
                or getattr(cal, "mati", None) is None:
            self.reference_info = None
            self.reference_error = "no_calibration"
            return False
        frame = self.capture_worker.current_frame
        if frame is None:
            self.reference_info = None
            self.reference_error = "no_frame"
            return False
        if not self.background_model.has_reference:
            self.reference_info = None
            self.reference_error = "no_background"
            return False
        points = [{"x": float(self.ruler.metric[i, 0]),
                   "y": float(self.ruler.metric[i, 1])}
                  for i in range(self.ruler.point_count)]
        mbox = self.mbox
        try:
            luts = self._get_background_luts()
            undist = undistort_frame(frame, luts)
            metrics = {
                "schema": 1,
                "width": int(undist.shape[1]),
                "height": int(undist.shape[0]),
                "caliber_name": mbox.cal[self.caliber_index][0]
                if mbox is not None else "",
                "caliber_radius_mm": float(mbox.radius())
                if mbox is not None else 0.0,
                "points": points,
                "mat": np.asarray(cal.mat, dtype=np.float64).tolist(),
                "mati": np.asarray(cal.mati, dtype=np.float64).tolist(),
                "timestamp": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
            }
            sample_dir = _reference_next_sample(_reference_dataset_root())
            ok = _reference_save_sample(
                sample_dir, cal, self.background_model, undist, metrics,
                cal_frame=getattr(cal, "frame", None),
                cal_visual=getattr(cal, "visual", None),
                frame_raw=frame)
            sample_name = os.path.basename(sample_dir)
        except Exception as exc:  # pragma: no cover
            print(f"[reference] save failed: {exc}", flush=True)
            ok = False
            sample_name = None
        if ok:
            self.reference_info = len(points)
            self.reference_sample = sample_name
            self.reference_error = None
        else:
            self.reference_info = None
            self.reference_sample = None
            self.reference_error = "write_failed"
        return ok

    def run_card_qc(self):
        """Karten-Qualitätscheck (Kalibrierung-Reiter) asynchron starten.

        Misst die eingelegte Kalibrierkarte über ein **einzelnes Frame** und
        vergleicht sie gegen die Referenzkarte (`grid_metric` des
        Kalibrier-Sidecars). Die Messung läuft in einem **Daemon-Thread**
        (`_card_qc_worker`) — der GL/Render-Thread bleibt flüssig, die
        UI zeigt einen Status-Dialog. Ergebnis/Overlay/Fehler werden nach
        Abschluss gesetzt (`card_qc_result`/`card_qc_error`/`card_qc_overlay`).

        Gültigkeitsprüfungen laufen synchron (Fehlercodes sind sofort da);
        danach wird nur der Thread gestartet. Rückgabe: True, wenn gestartet.
        """
        if self.card_qc_running:
            return False
        self.card_qc_result = None
        self.card_qc_error = None
        self.card_qc_overlay = None
        self.card_qc_circles = 0
        self._card_qc_cancel = False

        if self.state is not AppState.MEASURING:
            self.card_qc_error = "not_measuring"
            return False
        cal = self.calibration
        if self.capture_worker is None or cal is None \
                or getattr(cal, "mati", None) is None \
                or getattr(cal, "channel_params", None) is None:
            self.card_qc_error = "no_calibration"
            return False

        sidecar = read_json(calibration_json_path())
        reference = sidecar.get("grid_metric") if sidecar else None
        if reference is None:
            self.card_qc_error = "no_reference"
            return False
        reference = np.asarray(reference, dtype=np.float64)

        self.card_qc_running = True
        thread = threading.Thread(target=self._card_qc_worker,
                                  args=(reference, cal),
                                  name="card-qc", daemon=True)
        self.card_qc_thread = thread
        thread.start()
        return True

    def _card_qc_worker(self, reference, calibration):
        """Hintergrund-Messung: Frames sammeln, mitteln, auswerten, persistieren.

        Es werden `QC_SAMPLE_FRAMES` (3) aufeinanderfolgende Frames erfasst und
        in `detect_grid_metric` gemittelt (Rauschreduktion). Der letzte Frame
        dient als Basis für das Overlay.
        """
        try:
            if self._card_qc_cancel:
                return
            if self.capture_worker is not None:
                self.capture_worker.unpause()
            frames = _collect_frames(self.capture_worker, QC_SAMPLE_FRAMES)
            if not frames:
                self.card_qc_error = "no_frame"
                return
            frame = frames[-1]

            result = detect_grid_metric(frames, calibration)
            if result.metric_grid is None:
                if self._card_qc_cancel:
                    return
                self.card_qc_error = "no_grid"
                self.card_qc_circles = int(result.circle_count or 0)
                return
            if self._card_qc_cancel:
                return

            metric_grid = result.metric_grid
            check = check_card(reference, metric_grid, QC_TOLERANCE_MM)
            if check is None:
                self.card_qc_error = "no_grid"
                return
            self.card_qc_result = check
            self._save_card_qc_result(reference, metric_grid, frame,
                                      result.pixel_grid, check)
        except Exception as exc:  # pragma: no cover — darf den GL-Thread nie blockieren
            print(f"[card_qc] failed: {exc}", flush=True)
            if not self._card_qc_cancel:
                self.card_qc_error = "no_grid"
        finally:
            self.card_qc_running = False
            self.card_qc_thread = None

    def _save_card_qc_result(self, reference, metric_grid, frame,
                             pixel_grid, result):
        """Ergebnis-JSON + Overlay-PNG schreiben und das Overlay anzeigen.

        `frame` ist der **Roh-Frame**, auf dem die Detektion lief; das Overlay
        wird in Roh-Koordinaten darauf gezeichnet (siehe `detect_grid_metric`)
        und der komplette Frame wird anschließend LUT-entzerrt angezeigt.
        """
        overlay = None
        if frame is not None and pixel_grid is not None:
            try:
                overlay = render_overlay(
                    frame, pixel_grid, result["deviations_um"], result["pass"])
            except Exception as exc:  # pragma: no cover
                print(f"[card_qc] overlay failed: {exc}", flush=True)
                overlay = None
        payload = build_payload(reference, metric_grid, result)
        _qc_save_result(payload, overlay)

        # Ergebnis am eingefrorenen Kamera-Frame anzeigen (wie Kalibrier-Ergebnis).
        self.capture_worker.pause()
        if overlay is not None:
            self.capture_worker.current_frame = overlay
            self.card_qc_overlay = overlay
        return overlay

    def dismiss_card_qc(self):
        """Card-QC beenden: Abbruch einer laufenden Erfassung oder Schließen
        eines Ergebnisses — Kamera freigeben, Zustand räumen."""
        self._card_qc_cancel = True
        if self.capture_worker is not None and not self.card_qc_running:
            self.capture_worker.unpause()
        self.card_qc_result = None
        self.card_qc_error = None
        self.card_qc_overlay = None
        self.card_qc_circles = 0

    def recover_calibration(self):
        """Letzte finalisierte Session (Volles Set) wiederherstellen.

        Nur aus `IDLE` und nur wenn `has_valid_session()` + Sidecar `ok=true` +
        passende Kamera-Auflösung. Befüllt die Kalibrierung (mat/mati/
        channel_params, LUTs), lädt den Hintergrund und erreicht `MEASURING`.
        Rückgabe: True bei Erfolg; Fehlercode über `recovery_error`.
        """
        if self.state is not AppState.IDLE:
            self.recovery_error = "no_session"
            return False
        if self.capture_worker is None or self.calibration is None or self.canvas is None:
            self.recovery_error = "corrupt"
            return False
        if not has_valid_session():
            self.recovery_error = "no_session"
            return False
        sidecar = read_json(calibration_json_path())
        if sidecar is None or not sidecar.get("ok"):
            self.recovery_error = "corrupt"
            return False
        # Auflösungs-Validierung
        cam_w = int(getattr(self.capture_worker, "width", 0) or 0)
        cam_h = int(getattr(self.capture_worker, "height", 0) or 0)
        if int(sidecar.get("width") or 0) != cam_w or int(sidecar.get("height") or 0) != cam_h:
            self.recovery_error = "resolution"
            return False
        try:
            cal = self.calibration
            cal.mat = np.array(sidecar["mat"], dtype=np.float64)
            cal.mati = np.array(sidecar["mati"], dtype=np.float64)
            cal.channel_params = np.array(sidecar["channel_params"], dtype=np.float64)
            cal.calibrated = True
            frame = self.capture_worker.current_frame
            if frame is not None:
                cal.frame = frame
            # `_get_background_luts` statt `cal.compute_lut_channels()`: der
            # Cache wird gefüllt und die spätere (Monitor-)Nachführung ruft
            # die teure 4K-LUT-Berechnung nicht ein zweites Mal auf.
            luts = self._get_background_luts()
            if luts is not None:
                self.canvas.set_luts(luts)
        except Exception as exc:  # pragma: no cover
            print(f"[recovery] calibrate restore failed: {exc}", flush=True)
            self.recovery_error = "corrupt"
            return False

        loaded = load_background(background_json_path())
        if not getattr(loaded, "learned", False):
            self.recovery_error = "corrupt"
            return False
        self.background_model = loaded
        self.last_background_check = None
        self.background_learn_error = False

        self.mbox.enabled = True
        self.ruler.enabled = True
        self.ruler.reset_points()
        self.indicator.enabled = True
        self.capture_worker.paused = False
        self.measuring_enabled = True
        self.state = AppState.MEASURING
        self.recovery_error = None
        # Sofort-Warnung nur, wenn bereits ein Live-Frame vorliegt (nicht der
        # initiale Warte-Bildschirm der Kamera — der würde fälschlich UNAVAILABLE
        # liefern). Sonst bleibt der Status bis zum ersten echten Frame offen.
        # `update_reference=False`: das teure Drift-Update (undistort/LUT) läuft
        # hier im UI-Thread und würde die GUI blockieren — der periodische
        # Monitor-Tick übernimmt den Drift-Ausgleich.
        try:
            cur = self.capture_worker.current_frame
            waiting = getattr(self.capture_worker, "waiting_screen", None)
            if waiting is None or cur is not waiting:
                self.check_background(update_reference=False)
        except Exception:  # pragma: no cover
            pass
        return True

    # ---- Anzeige-Filter (orthogonal) ----

    def _load_filters(self):
        """Filterzustand aus Settings laden; fehlend/ungültig -> neutral.

        Beim App-Start sind die Aktiv-Schalter der Bildfilter (`active`) und
        der Option „Hintergrund einfärben" (`tint`) generell deaktiviert; die
        eingestellten Parameterwerte bleiben erhalten.
        """
        data = _settings_load(self.settings_path)
        filt = BRSViewFilter.from_dict(data.get("filters"))
        filt.active = False
        filt.tint = False
        return filt

    def save_filters(self):
        """Aktuellen Filterzustand persistent speichern (settings.json)."""
        _settings_save({"filters": self.filters.to_dict()},
                       path=self.settings_path)
        return self.filters

    def _mark_filters_dirty(self):
        """Filterzustand als 'zu speichern' markieren (Debounce im Flush)."""
        self._filters_need_save = True

    def flush_filters_if_dirty(self):
        """Filterzustand speichern, wenn seit dem letzten Save geändert.

        Debounce-Einstiegspunkt für UI/Render-Loop: schreibt nur bei
        tatsächlicher Änderung, nie pro Slider-Drag-Frame.
        """
        if self._filters_need_save:
            self._filters_need_save = False
            self.save_filters()
            return True
        return False

    def effective_uniforms(self):
        """Shader-Uniform-Werte für die Anzeige: Neutralzustand bzw. deaktivierter
        Filter liefert die Identität (Bild unverändert). Aufruf pro Frame."""
        if not self.filters.active or self.filters.is_neutral():
            return (1.0, 1.0, 0.0, 1.0, 0.0, 0.0)
        return self.filters.uniforms()

    def set_filter_param(self, name, value):
        """Anzeige-Filterparameter setzen (wandelt nur den Filterzustand,
        nie die App-FSM und nie Messwerte)."""
        if name in ("contrast", "gamma", "brightness", "saturation"):
            setattr(self.filters, name, float(value))
        elif name in ("invert", "gray"):
            setattr(self.filters, name, bool(value))
        else:
            raise ValueError(f"unknown filter param: {name}")
        self._mark_filters_dirty()
        return value

    def toggle_filters_active(self):
        """Taste F: Filterkombination global umschalten (Parameter bleiben)."""
        self.filters.active = not self.filters.active
        self._mark_filters_dirty()
        return self.filters.active

    def toggle_background_tint(self):
        """Anzeige-Option „Hintergrund einfärben" umschalten (Ansicht-Menü).

        Eigenständige Option unabhängig von `filters.active` (Taste F); wirkt
        ausschließlich auf die Anzeige, nie auf Messung/Erkennung.
        """
        self.filters.tint = not self.filters.tint
        self._mark_filters_dirty()
        return self.filters.tint

    def effective_tint(self):
        """Shader-Uniform-Werte der Hintergrund-Einfärbung.

        Liefert das Tupel (u_tint, r, g, b) — die Uniforms u_tint_r/g/b werden
        im Shader direkt als RGB angewandt (Kanalreihenfolge wie
        `tint_pixel`/`filter_pixel`). Ohne aktive Option oder ohne gelernte
        Referenz ist `u_tint = 0` -> No-op im Shader (Maske bleibt leer).
        """
        if not self.filters.tint or not self.background_model.has_reference:
            return (0.0, 0.0, 0.0, 0.0)
        return (TINT_OPACITY, TINT_COLOR_RGB[0], TINT_COLOR_RGB[1],
                TINT_COLOR_RGB[2])

    def reset_filters(self):
        """Alle Filterparameter auf den neutralen Ausgangszustand setzen."""
        self.filters.reset()
        self._mark_filters_dirty()
        return self.filters

    # ---- UI-State (Fensterpositionen, orthogonal) ----

    def load_window_state(self, name):
        """Gespeicherte Fensterposition (x, y) eines Overlay-Fensters laden.

        Liefert ein (x, y)-Tupel oder None, wenn keine gültige Position
        gespeichert ist (fehlender/ungültiger Eintrag -> Standardposition).
        """
        data = _settings_load(self.settings_path)
        ui_state = data.get("ui")
        if not isinstance(ui_state, dict):
            return None
        entry = ui_state.get("window_pos", {}).get(name)
        if not isinstance(entry, dict):
            return None
        try:
            x = float(entry["x"])
            y = float(entry["y"])
        except (KeyError, TypeError, ValueError):
            return None
        return (x, y)

    def save_window_state(self, name, x, y):
        """Fensterposition persistent speichern (Key `ui.window_pos.<name>`)."""
        data = _settings_load(self.settings_path)
        ui_state = data.get("ui")
        if not isinstance(ui_state, dict):
            ui_state = {}
        window_pos = ui_state.get("window_pos")
        if not isinstance(window_pos, dict):
            window_pos = {}
        window_pos[name] = {"x": float(x), "y": float(y)}
        ui_state["window_pos"] = window_pos
        _settings_save({"ui": ui_state}, path=self.settings_path)
        return window_pos[name]

    def cycle_active_point(self):
        if self.ruler:
            self.ruler.cycle_active()

    def select_point(self, index):
        if self.ruler:
            self.ruler.set_active(index)

    def remove_point(self, index):
        if self.ruler:
            self.ruler.remove_point(index)

    def reset_points(self):
        if self.ruler:
            self.ruler.reset_points()
        self.reference_info = None
        self.reference_sample = None
        self.reference_error = None

    def adjust_point(self, direction):
        if self.ruler:
            self.ruler.adjust(direction)

    def quit(self):
        self.canvas.wants_exit = True