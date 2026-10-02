# -*- coding: utf-8 -*-
"""Headless unit tests for the AppController FSM (no window)."""
import sys
import os
import tempfile
import threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Persistenz-Pfade (recovery-snapshots) in einem Temp-Config isolieren, damit
# finish/recover-Tests nie ins echte ~/.config schreiben.
_TEST_CFG = tempfile.mkdtemp(prefix="brs_ctrl_cfg_")
os.environ["XDG_CONFIG_HOME"] = _TEST_CFG
# Vision-Endpunkt in den Controller-Tests explizit deaktiviert (leere
# Base-URL im vision-Block): die Defaults sind zwar neutral (leer), die
# Datei fixiert den Zustand trotzdem hermetisch gegen evtl. getestete
# Settings/Env-Overrides — `test_vision_connection` darf niemals netzen.
# `make_ctrl()` zeigt auf diese Datei.
import json as _json
_VISION_OFF_SETTINGS = os.path.join(_TEST_CFG, "vision_off_settings.json")
with open(_VISION_OFF_SETTINGS, "w", encoding="utf-8") as _f:
    _json.dump({"vision": {"base_url": "", "model": "", "api_key": ""}}, _f)

import cv2
import numpy as np

from benchrestscore.controller import AppController, AppState
from benchrestscore.i18n import current_language
from benchrestscore.settings import load as settings_load, save as settings_save
from benchrestscore.camera import (
    CAMERA_PRESETS,
    CAMERA_PRESET_FALLBACK,
    DEFAULT_CAMERA_DEVICE,
)
from benchrestscore.calibration_monitor import (
    BackgroundModel,
    MonitorStatus,
    REFERENCE_SCALE,
)
from benchrestscore.reference_eval import (
    BACKGROUND_JSON,
    BACKGROUND_PNG,
    CALIBRATION_JSON,
    CALIBRATION_PNG,
    CALIBRATION_OVERLAY_PNG,
    EVALUATION_PNG,
    RAW_PNG,
    METRICS_JSON,
    list_reference_samples,
)
from benchrestscore import calibration_recovery as cr


class Canvas:
    wants_exit = False
    default_lut = "neutral"
    calls = []
    font_scale = "normal"
    def set_luts(self, luts): self.calls.append(tuple(luts))
    def request_font_scale(self, key):
        self.font_scale = key
        self.calls.append(("request_font_scale", key))
    def request_wertung_capture(self):
        self.calls.append("request_wertung_capture")


class Worker:
    paused = False
    current_frame = None
    waiting_screen = None
    def pause(self): self.paused = True
    def unpause(self): self.paused = False


class Cal:
    calibrated = False
    visual = None
    mean = 50
    A_correction = ""
    B_correction = ""
    def calibrate(self, frame):
        self.calibrated = True
        self.visual = "visual"
        return True
    def compute_lut_channels(self): return [None, None, None]


class MBox:
    enabled = False
    cal = [(".177", 4.5)]
    def set_index(self, i): pass
    def radius(self): return 2.25


class Ruler:
    enabled = False
    def update(self, circles=False): pass
    def reset_points(self): pass


class Ind:
    enabled = False
    automation = False


def make_ctrl():
    c = AppController(Canvas())
    c.settings_path = _VISION_OFF_SETTINGS
    c.capture_worker = Worker()
    c.calibration = Cal()
    c.mbox = MBox()
    c.ruler = Ruler()
    c.indicator = Ind()
    return c


class RestartCanvas(Canvas):
    def __init__(self):
        self.restarts = []

    def restart_camera(self, device, w, h, fps, rotate, rebuild_calibration=True):
        self.restarts.append((device, w, h, fps, rotate, rebuild_calibration))


def _v4l2_fixture(*caps):
    """Fake-v4l2ctl-Runner: liefert stdout mit den gegebenen (w, h, fps)-Caps."""
    def _runner(device):
        lines = ["[0]: 'MJPG' (Motion-JPEG, compressed)"]
        for w, h, fps in caps:
            lines.append(f"\tSize: Discrete {w}x{h}")
            lines.append(f"\t\tInterval: Discrete {1.0 / fps:.4f}s ({fps}.000 fps)")
        return "\n".join(lines) + "\n"
    return _runner


def _v4l2_all(device):
    return _v4l2_fixture(*((p[1], p[2], p[3]) for p in CAMERA_PRESETS))(device)


def make_camera_ctrl(td):
    c = AppController(RestartCanvas(), settings_path=os.path.join(td, "settings.json"))
    c.capture_worker = Worker()
    c.calibration = Cal()
    c.mbox = MBox()
    c.ruler = Ruler()
    c.indicator = Ind()
    c._v4l2_runner = _v4l2_all  # alle Presets unterstützt
    return c


def test_happy_path():
    ctrl = make_ctrl()
    assert ctrl.state is AppState.IDLE
    assert ctrl.start_calibration() is True
    assert ctrl.state is AppState.RESULT
    assert ctrl.accept_calibration() is True
    assert ctrl.state is AppState.LEARN_PROMPT
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.learn_background() is True
    assert ctrl.state is AppState.LEARN_RESULT
    assert ctrl.finish_background() is True
    assert ctrl.state is AppState.MEASURING
    assert ctrl.measuring_enabled is True
    # side effects
    assert ctrl.mbox.enabled is True
    assert ctrl.ruler.enabled is True


def test_forbidden_transitions():
    ctrl = make_ctrl()
    ctrl.reset()  # no-op from IDLE
    assert ctrl.state is AppState.IDLE
    assert ctrl.accept_calibration() is None  # not RESULT
    assert ctrl.cancel_calibration() is None  # not in cancel-able states
    assert ctrl.finish_background() is None   # not LEARN_RESULT
    assert ctrl.state is AppState.IDLE


def test_failed_calibration():
    class BadCal(Cal):
        def calibrate(self, frame): return False
    ctrl = make_ctrl()
    ctrl.calibration = BadCal()
    ok = ctrl.start_calibration()
    assert ok is False
    assert ctrl.state is AppState.IDLE
    assert ctrl.capture_worker.paused is False


def test_reset_from_measuring():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.learn_background() is True
    ctrl.finish_background()
    ctrl.reset()
    assert ctrl.state is AppState.IDLE
    assert ctrl.measuring_enabled is False
    assert ctrl.mbox.enabled is False


def test_request_calibration_resets_when_calibrated():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    assert ctrl.state is AppState.LEARN_PROMPT  # noch nicht MEASURING
    assert ctrl.calibration.calibrated is True
    ret = ctrl.request_calibration()
    assert ret is False
    assert ctrl.state is AppState.IDLE
    assert ctrl.calibration.calibrated is False
    assert ctrl.mbox.enabled is False
    assert ctrl.measuring_enabled is False


def test_request_calibration_start_when_not_calibrated():
    ctrl = make_ctrl()
    ret = ctrl.request_calibration()
    assert ret is True
    assert ctrl.state is AppState.RESULT


def test_start_calibration_resets_luts():
    ctrl = make_ctrl()
    ctrl.canvas.calls.clear()
    ctrl.start_calibration()
    # reset_luts ruft canvas.set_luts mit drei neutralen LUTs auf
    assert len(ctrl.canvas.calls) == 1
    assert ctrl.canvas.calls[0] == ("neutral", "neutral", "neutral")


def test_reset_calibration_state_resets_luts():
    ctrl = make_ctrl()
    ctrl.canvas.calls.clear()
    ctrl.state = AppState.MEASURING
    ctrl.calibration.calibrated = True
    ctrl.reset_calibration_state()
    assert ctrl.state is AppState.IDLE
    assert len(ctrl.canvas.calls) == 1
    assert ctrl.canvas.calls[0] == ("neutral", "neutral", "neutral")


def test_toggle_automation_syncs_indicator():
    ctrl = make_ctrl()
    assert ctrl.automation is False
    assert ctrl.indicator.automation is False
    ctrl.toggle_automation()
    assert ctrl.automation is True
    assert ctrl.indicator.automation is True
    ctrl.toggle_automation()
    assert ctrl.automation is False
    assert ctrl.indicator.automation is False


def test_language_loads_from_settings():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"language": "en"}, path=path)
        ctrl = AppController(Canvas(), settings_path=path)
        assert ctrl.language == "en"
        assert current_language() == "en"


def test_set_language_persists():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        ctrl = AppController(Canvas(), settings_path=path)
        ctrl.set_language("en")
        assert ctrl.language == "en"
        assert current_language() == "en"
        assert settings_load(path) == {"language": "en"}


def test_font_scale_loads_from_settings():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"font_scale": "xlarge"}, path=path)
        ctrl = AppController(Canvas(), settings_path=path)
        assert ctrl.font_scale == "xlarge"
        assert ("request_font_scale", "xlarge") in ctrl.canvas.calls


def test_font_scale_default_when_missing_or_invalid():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        ctrl = AppController(Canvas(), settings_path=path)
        assert ctrl.font_scale == "normal"
        assert ("request_font_scale", "normal") in ctrl.canvas.calls
        assert ("request_font_scale", "huge") not in ctrl.canvas.calls
    with tempfile.TemporaryDirectory() as td2:
        path = os.path.join(td2, "settings.json")
        settings_save({"font_scale": "huge"}, path=path)
        ctrl = AppController(Canvas(), settings_path=path)
        assert ctrl.font_scale == "normal"
        assert ("request_font_scale", "normal") in ctrl.canvas.calls


def test_set_font_scale_persists():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        ctrl = AppController(Canvas(), settings_path=path)
        ctrl.set_font_scale("large")
        assert ctrl.font_scale == "large"
        assert ("request_font_scale", "large") in ctrl.canvas.calls
        assert settings_load(path) == {"font_scale": "large"}
        try:
            ctrl.set_font_scale("huge")
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_window_state_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        ctrl = AppController(Canvas(), settings_path=path)
        assert ctrl.load_window_state("measurement") is None
        ctrl.save_window_state("measurement", 123.0, 456.0)
        assert ctrl.load_window_state("measurement") == (123.0, 456.0)
        # neuer Controller auf demselben Pfad liest die gespeicherte Position
        ctrl2 = AppController(Canvas(), settings_path=path)
        assert ctrl2.load_window_state("measurement") == (123.0, 456.0)


def test_window_state_keys_are_independent():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        ctrl = AppController(Canvas(), settings_path=path)
        ctrl.save_window_state("measurement", 1.0, 2.0)
        ctrl.save_window_state("filters", 3.0, 4.0)
        assert ctrl.load_window_state("measurement") == (1.0, 2.0)
        assert ctrl.load_window_state("filters") == (3.0, 4.0)


def test_window_state_tolerates_invalid():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"ui": {"window_pos": {"measurement": "kaputt"}}},
                      path=path)
        ctrl = AppController(Canvas(), settings_path=path)
        assert ctrl.load_window_state("measurement") is None
        settings_save({"ui": "not-a-dict"}, path=path)
        ctrl2 = AppController(Canvas(), settings_path=path)
        assert ctrl2.load_window_state("filters") is None
        settings_save({"ui": {"window_pos": {"filters": {"x": "abc"}}}},
                      path=path)
        ctrl3 = AppController(Canvas(), settings_path=path)
        assert ctrl3.load_window_state("filters") is None


def test_camera_settings_defaults():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        assert ctrl.camera_device == DEFAULT_CAMERA_DEVICE
        # ohne gespeichertes Preset: noch keine Wahl (None) bis normalize läuft
        assert ctrl.camera_preset is None


def test_camera_settings_loads_from_settings():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"camera_device": "/dev/video9", "camera_preset": "4K30"},
                      path=path)
        ctrl = AppController(RestartCanvas(), settings_path=path)
        assert ctrl.camera_device == "/dev/video9"
        assert ctrl.camera_preset == ("4K30", 3840, 2160, 30)


def test_normalize_prefers_4k_when_available():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        assert ctrl.camera_preset is None
        preset = ctrl.normalize_camera_preset()
        # alle Presets unterstützt -> 4K-Default (erste 4K-Variante: 4K30)
        assert preset == ("4K30", 3840, 2160, 30)
        assert settings_load(os.path.join(td, "settings.json"))["camera_preset"] == "4K30"


def test_normalize_uses_first_supported_without_4k():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        ctrl._v4l2_runner = _v4l2_fixture((1280, 720, 30))  # nur 720p
        preset = ctrl.normalize_camera_preset()
        assert preset == CAMERA_PRESET_FALLBACK


def test_apply_camera_settings_full_reset():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        ctrl.state = AppState.MEASURING
        ctrl.measuring_enabled = True
        ctrl.ruler.enabled = True
        ctrl.mbox.enabled = True
        # Auflösung 1080p30 -> 4K30: full reset + Neubau der Kalibrierung
        ctrl.apply_camera_settings(DEFAULT_CAMERA_DEVICE, CAMERA_PRESETS[2])
        assert ctrl.state is AppState.IDLE
        assert ctrl.measuring_enabled is False
        assert ctrl.ruler.enabled is False
        assert ctrl.mbox.enabled is False
        assert len(ctrl.canvas.restarts) == 1
        device, w, h, fps, rotate, rebuild = ctrl.canvas.restarts[0]
        assert (w, h, fps) == (3840, 2160, 30)
        assert rebuild is True


def test_apply_camera_settings_device_change_resets():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        ctrl.state = AppState.MEASURING
        ctrl.apply_camera_settings("/dev/video1", ctrl.camera_preset)
        assert ctrl.state is AppState.IDLE
        assert len(ctrl.canvas.restarts) == 1
        device, w, h, fps, rotate, rebuild = ctrl.canvas.restarts[0]
        assert device == "/dev/video1"
        assert rebuild is True


def test_apply_camera_settings_same_settings_keeps_state():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        ctrl.normalize_camera_preset()  # Preset wählen (4K30 bei 4K verfügbar)
        ctrl.state = AppState.MEASURING
        ctrl.ruler.enabled = True
        ctrl.apply_camera_settings(ctrl.camera_device, ctrl.camera_preset)
        assert ctrl.state is AppState.MEASURING
        assert ctrl.ruler.enabled is True
        assert len(ctrl.canvas.restarts) == 1
        device, w, h, fps, rotate, rebuild = ctrl.canvas.restarts[0]
        assert rebuild is False


def test_apply_camera_settings_persists():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        ctrl = AppController(RestartCanvas(), settings_path=path)
        ctrl._v4l2_runner = _v4l2_all
        ctrl.apply_camera_settings("/dev/video2", ("4K30", 3840, 2160, 30))
        data = settings_load(path)
        assert data["camera_device"] == "/dev/video2"
        assert data["camera_preset"] == "4K30"
        assert data["camera_rotate"] == 180
        assert "camera_flip" not in data


def test_camera_rotate_defaults_to_180():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        assert ctrl.camera_rotate == 180


def test_camera_rotate_loads_from_settings():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"camera_rotate": 0}, path=path)
        ctrl = AppController(RestartCanvas(), settings_path=path)
        assert ctrl.camera_rotate == 0


def test_camera_rotate_invalid_falls_back_to_180():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"camera_rotate": 90}, path=path)
        ctrl = AppController(RestartCanvas(), settings_path=path)
        assert ctrl.camera_rotate == 180


def test_apply_camera_settings_rotate_change_resets():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        ctrl.normalize_camera_preset()
        ctrl.state = AppState.MEASURING
        ctrl.ruler.enabled = True
        ctrl.apply_camera_settings(ctrl.camera_device, ctrl.camera_preset,
                                   rotate=0)
        assert ctrl.state is AppState.IDLE
        assert ctrl.ruler.enabled is False
        assert len(ctrl.canvas.restarts) == 1
        device, w, h, fps, rotate, rebuild = ctrl.canvas.restarts[0]
        assert rotate == 0
        assert rebuild is True


def test_apply_camera_settings_same_rotate_keeps_state():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        ctrl.normalize_camera_preset()
        ctrl.state = AppState.MEASURING
        ctrl.apply_camera_settings(ctrl.camera_device, ctrl.camera_preset,
                                   rotate=ctrl.camera_rotate)
        assert ctrl.state is AppState.MEASURING
        assert len(ctrl.canvas.restarts) == 1
        device, w, h, fps, rotate, rebuild = ctrl.canvas.restarts[0]
        assert rebuild is False


def test_supported_presets_cached_per_device():
    with tempfile.TemporaryDirectory() as td:
        ctrl = make_camera_ctrl(td)
        calls = []

        def _counting(device):
            calls.append(device)
            return _v4l2_all(device)

        ctrl._v4l2_runner = _counting
        p1 = ctrl.supported_presets("/dev/video0")
        p2 = ctrl.supported_presets("/dev/video0")
        assert p1 == p2
        assert len(calls) == 1  # genau einmal probed
        ctrl.supported_presets("/dev/video5")
        assert len(calls) == 2  # neues Gerät -> neu probed


def test_normalize_camera_preset_falls_back():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"camera_preset": "4K60"}, path=path)
        ctrl = AppController(RestartCanvas(), settings_path=path)
        ctrl._v4l2_runner = _v4l2_fixture((1280, 720, 30))  # kein 4K am Gerät
        preset = ctrl.normalize_camera_preset()
        assert preset == CAMERA_PRESET_FALLBACK
        assert ctrl.camera_preset == CAMERA_PRESET_FALLBACK
        assert settings_load(path)["camera_preset"] == CAMERA_PRESET_FALLBACK[0]


# --- Loss-of-Calibration-Monitor ---


def _structured_frame():
    rng = np.random.default_rng(7)
    img = np.full((240, 320), 128, dtype=np.uint8)
    for _ in range(300):
        x0 = int(rng.integers(0, 300))
        y0 = int(rng.integers(0, 220))
        x1 = int(rng.integers(x0 + 5, x0 + 30))
        y1 = int(rng.integers(y0 + 5, y0 + 30))
        img[y0:min(y1, 240), x0:min(x1, 320)] = int(rng.integers(0, 255))
    return img


def _shift_luts(h, w, dx):
    """Drei identische Verschiebe-LUTs (BGR-Reihenfolge) um `dx` Pixel."""
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    u = (xx + dx).astype(np.float32) / w
    v = yy.astype(np.float32) / h
    u16 = np.clip(np.round(u * 65280), 0, 65535).astype(np.int64)
    v16 = np.clip(np.round(v * 65280), 0, 65535).astype(np.int64)
    lut = np.dstack([(u16 // 256).astype(np.uint8),
                     (u16 % 256).astype(np.uint8),
                     (v16 // 256).astype(np.uint8),
                     (v16 % 256).astype(np.uint8)])
    return [lut, lut, lut]


class ShiftCal(Cal):
    """`Cal` mit echten Verschiebe-LUTs für `compute_lut_channels`."""

    def __init__(self, h, w, dx=3):
        super(ShiftCal, self).__init__()
        self._luts = _shift_luts(h, w, dx)

    def compute_lut_channels(self):
        return self._luts


def _expected_shift(frame, dx):
    """Frame um `dx` nach links verschieben (rechter Rand repliziert)."""
    exp = np.empty_like(frame)
    h, w = frame.shape[:2]
    for c in range(3):
        s = np.zeros((h, w), dtype=np.uint8)
        s[:, :w - dx] = frame[:, dx:, c]
        s[:, w - dx:] = frame[:, -1, c][:, None]
        exp[..., c] = s
    return exp


class MatiCal(Cal):
    """Kalibrierung mit NDC->Metrik-Matrix für die mm-Umrechnung."""

    def __init__(self):
        super(MatiCal, self).__init__()
        s = 20.0
        self.mat = np.diag([1.0 / s, 1.0 / s, 1.0])
        self.mati = np.diag([s, s, 1.0])


def _reach_measuring(ctrl, frame=None):
    """Vollständigen Kalibrier-Workflow bis MEASURING durchlaufen (mit Lernen)."""
    frame = _structured_frame() if frame is None else frame
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = frame
    assert ctrl.learn_background() is True
    assert ctrl.state is AppState.LEARN_RESULT
    assert ctrl.finish_background() is True
    assert ctrl.state is AppState.MEASURING
    ctrl.capture_worker.current_frame = frame
    return ctrl


def test_learn_background_requires_learn_prompt():
    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.state is AppState.IDLE
    assert ctrl.learn_background() is False
    assert ctrl.background_model.learned is False


def test_learn_background_sparse_frame_fails():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    assert ctrl.state is AppState.LEARN_PROMPT
    ctrl.capture_worker.current_frame = np.full((240, 320), 128, dtype=np.uint8)
    assert ctrl.learn_background() is False
    assert ctrl.state is AppState.LEARN_PROMPT  # bleibt im Lern-Schritt
    assert ctrl.background_model.learned is False
    assert ctrl.background_learn_error is True
    assert ctrl.capture_worker.paused is False  # Kamera wieder freigegeben


def test_learn_background_success():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.learn_background() is True
    assert ctrl.state is AppState.LEARN_RESULT
    assert ctrl.background_model.learned is True
    assert ctrl.background_learn_error is False
    assert ctrl.last_background_check is not None
    # Kamera eingefroren und zeigt die Keypoint-Visualisierung
    assert ctrl.capture_worker.paused is True
    assert ctrl.background_model.keypoint_count > 0


def test_learn_background_sets_reference():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.learn_background() is True
    assert ctrl.background_model.has_reference is True
    assert ctrl.background_model.reference_raw is not None


def test_vision_config_roundtrip(monkeypatch, tmp_path):
    from benchrestscore import controller as ctrl_mod
    from benchrestscore.vision_detect import (
        VisionConfig, DEFAULT_BASE_URL, DEFAULT_MODEL)

    ctrl = _reach_measuring(make_ctrl())
    # Eigener Settings-Pfad ohne vision-Block -> neutrale (leere) Defaults,
    # nicht konfiguriert.
    ctrl.settings_path = str(tmp_path / "settings.json")
    cfg0 = ctrl.get_vision_config()
    assert cfg0["base_url"] == DEFAULT_BASE_URL == ""
    assert cfg0["model"] == DEFAULT_MODEL == ""
    assert cfg0["configured"] is False
    # set_vision_config speichert in den Temp-Settings-Pfad.
    ctrl.set_vision_config("https://example.test/v1", "m/test", "sekret")
    data = settings_load(ctrl.settings_path)
    assert data["vision"]["base_url"] == "https://example.test/v1"
    assert data["vision"]["model"] == "m/test"
    assert data["vision"]["api_key"] == "sekret"
    cfg = ctrl.get_vision_config()
    assert cfg["base_url"] == "https://example.test/v1"
    assert cfg["model"] == "m/test"
    assert cfg["configured"] is True


def test_vision_connection_no_frame_and_not_configured(monkeypatch):
    ctrl = _reach_measuring(make_ctrl())
    # Kein Kamerabild (Worker.current_frame = None), nicht konfiguriert.
    status = ctrl.test_vision_connection()
    assert status in ("not_configured", "no_frame")


def test_vision_connection_overrides_not_configured():
    ctrl = make_ctrl()
    # Leere Overrides -> "nicht konfiguriert", unabhängig von den Settings
    # (Test-Settings: leerer vision-Block), kein Netzwerk-Call.
    status = ctrl.test_vision_connection(base_url="", model="", api_key="")
    assert status == "not_configured"


def test_vision_connection_overrides_ignore_settings():
    # Test-Settings sind "nicht konfiguriert": ohne Overrides ->
    # not_configured/no_frame; mit Overrides -> konfiguriert, also
    # "no_frame" (kein Kamerabild). Beweis, dass der Override-Pfad gilt.
    ctrl = make_ctrl()
    assert ctrl.test_vision_connection() in ("not_configured", "no_frame")
    status = ctrl.test_vision_connection(
        base_url="https://example.test/v1", model="m/test", api_key="sekret")
    assert status == "no_frame"


def test_vision_connection_override_ok(monkeypatch):
    from benchrestscore import vision_detect

    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    seen = []

    class _FakeClient:
        def __init__(self, config):
            seen.append((config.base_url, config.model, config.api_key))

        def detect(self, frame):
            return "  ok "

    monkeypatch.setattr(vision_detect, "VisionClient", _FakeClient)
    assert ctrl.test_vision_connection(" https://example.test/v1 ",
                                       "m/test", " sekret ") == "ok"
    assert seen == [("https://example.test/v1", "m/test", "sekret")]


def test_vision_connection_override_error(monkeypatch):
    from benchrestscore import vision_detect

    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()

    class _EmptyClient:
        def __init__(self, config):
            pass

        def detect(self, frame):
            return "   "

    class _RaisingClient:
        def __init__(self, config):
            pass

        def detect(self, frame):
            raise RuntimeError("boom")

    monkeypatch.setattr(vision_detect, "VisionClient", _EmptyClient)
    assert ctrl.test_vision_connection("https://example.test/v1",
                                       "m/test", "sekret") == "vision_error"
    monkeypatch.setattr(vision_detect, "VisionClient", _RaisingClient)
    assert ctrl.test_vision_connection("https://example.test/v1",
                                       "m/test", "sekret") == "vision_error"


def _slow_vision_client(monkeypatch, release):
    """Fake-VisionClient, der `detect` auf `release` blockiert (~1 Netz-Call)."""
    from benchrestscore import vision_detect

    class _SlowClient:
        def __init__(self, config):
            pass

        def detect(self, frame):
            release.wait(5.0)
            return "ok"

    monkeypatch.setattr(vision_detect, "VisionClient", _SlowClient)


def test_vision_test_async_running_then_ok(monkeypatch):
    release = threading.Event()
    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    _slow_vision_client(monkeypatch, release)
    ctrl.start_vision_test("https://example.test/v1", "m/test", "sekret")
    # Während des Laufs: Flag gesetzt, noch kein Ergebnis (UI zeigt
    # den Laufzeit-Hinweis).
    assert ctrl.vision_test_running is True
    assert ctrl.vision_test_status is None
    release.set()
    assert ctrl._vision_test_thread is not None
    ctrl._vision_test_thread.join(5.0)
    assert ctrl.vision_test_running is False
    assert ctrl.vision_test_status == "ok"


def test_vision_test_clear_invalidates_pending(monkeypatch):
    release = threading.Event()
    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    _slow_vision_client(monkeypatch, release)
    ctrl.start_vision_test("https://example.test/v1", "m/test", "sekret")
    # Feld-Änderung/Dialog-Schließen: laufender Test wird verworfen.
    ctrl.clear_vision_test()
    assert ctrl.vision_test_running is False
    assert ctrl.vision_test_status is None
    release.set()
    assert ctrl._vision_test_thread is not None
    ctrl._vision_test_thread.join(5.0)
    # Das (spät eintreffende) Ergebnis des invalidierten Tests darf
    # nicht übernommen werden.
    assert ctrl.vision_test_status is None
    assert ctrl.vision_test_running is False


def test_brsmatch_config_roundtrip(tmp_path):
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    # Defaults: leer, Event-ID 0, deaktiviert.
    cfg0 = ctrl.get_brsmatch_config()
    assert cfg0 == {"base_url": "", "api_key": "", "event_id": 0,
                    "enabled": False}
    # Speichern persistiert den brsmatch-Block.
    ctrl.set_brsmatch_config("https://brs.example/v1", "sekret", 7, True)
    data = settings_load(ctrl.settings_path)
    assert data["brsmatch"] == {
        "base_url": "https://brs.example/v1", "api_key": "sekret",
        "event_id": 7, "enabled": True}
    cfg = ctrl.get_brsmatch_config()
    assert cfg == {"base_url": "https://brs.example/v1",
                   "api_key": "sekret", "event_id": 7, "enabled": True}
    assert ctrl.brsmatch_enabled is True


def test_brsmatch_config_loads_from_settings(tmp_path):
    path = tmp_path / "settings.json"
    settings_save({"brsmatch": {"base_url": "https://b.test/v1",
                                "api_key": "k", "event_id": 7,
                                "enabled": True}}, path=path)
    ctrl = AppController(Canvas(), settings_path=str(path))
    assert ctrl.brsmatch_base_url == "https://b.test/v1"
    assert ctrl.brsmatch_api_key == "k"
    assert ctrl.brsmatch_event_id == 7
    assert ctrl.brsmatch_enabled is True


def test_brsmatch_config_invalid_event_id_defaults_zero(tmp_path):
    path = tmp_path / "settings.json"
    for bad in ("abc", -3, True, "", "7x"):
        settings_save({"brsmatch": {"base_url": "https://b.test/v1",
                                    "api_key": "k", "event_id": bad,
                                    "enabled": True}}, path=path)
        ctrl = AppController(Canvas(), settings_path=str(path))
        assert ctrl.brsmatch_event_id == 0, f"{bad!r} sollte auf 0 fallen"
    # String-Ganzzahl wird normalisiert.
    settings_save({"brsmatch": {"base_url": "https://b.test/v1",
                                "api_key": "k", "event_id": "42",
                                "enabled": True}}, path=path)
    ctrl = AppController(Canvas(), settings_path=str(path))
    assert ctrl.brsmatch_event_id == 42


def _wait_scan(ctrl):
    """Auf das Ende eines asynchronen Etikett-Scans warten (Thread-join)."""
    t = getattr(ctrl, "_scan_thread", None)
    if t is not None:
        t.join(timeout=5.0)


def test_brsmatch_scan_gated_by_enabled_and_state(monkeypatch, tmp_path):
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    calls = {"n": 0}
    def fake_extract_sticker(frame, config=None, transport=None):
        calls["n"] += 1
        return {"zeit": "09:15", "stand": 8, "dg": 1, "sch_nr": 6}
    monkeypatch.setattr("benchrestscore.controller._extract_sticker",
                        fake_extract_sticker)
    # Deaktiviert -> kein Scan.
    ctrl.set_brsmatch_config("https://b.test/v1", "k", 0, False)
    ctrl.scan_sticker()
    assert calls["n"] == 0
    assert ctrl.sticker_status is None
    # Aktiviert, MEASURING -> Scan startet async und Ergebnis landet in
    # sticker_meta, sobald der Thread fertig ist.
    ctrl.set_brsmatch_config("https://b.test/v1", "k", 0, True)
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.scan_sticker()
    assert ctrl.sticker_status == "running"
    _wait_scan(ctrl)
    assert calls["n"] == 1
    assert ctrl.sticker_status == "ok"
    assert ctrl.sticker_meta == {"zeit": "09:15", "stand": 8, "dg": 1,
                                 "sch_nr": 6}


def test_brsmatch_scan_no_frame_sets_error(monkeypatch, tmp_path):
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    ctrl.set_brsmatch_config("https://b.test/v1", "k", 0, True)
    ctrl.capture_worker.current_frame = None
    ctrl.scan_sticker()
    assert ctrl.sticker_status == "error"
    assert ctrl.sticker_meta is None
    assert ctrl._scan_thread is None


def test_brsmatch_scan_error_sets_error_status(monkeypatch, tmp_path):
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    ctrl.set_brsmatch_config("https://b.test/v1", "k", 0, True)
    ctrl.capture_worker.current_frame = _structured_frame()
    def boom(frame, config=None, transport=None):
        raise RuntimeError("vlm down")
    monkeypatch.setattr("benchrestscore.controller._extract_sticker", boom)
    ctrl.scan_sticker()
    assert ctrl.sticker_status == "running"
    _wait_scan(ctrl)
    assert ctrl.sticker_status == "error"
    assert ctrl.sticker_meta is None


def test_brsmatch_scan_ignored_while_running(monkeypatch, tmp_path):
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    ctrl.set_brsmatch_config("https://b.test/v1", "k", 0, True)
    calls = {"n": 0}
    started = threading.Event()
    release = threading.Event()
    def slow(frame, config=None, transport=None):
        calls["n"] += 1
        started.set()
        release.wait(timeout=5.0)
        return {"zeit": "09:15", "stand": 8, "dg": 1, "sch_nr": 6}
    monkeypatch.setattr("benchrestscore.controller._extract_sticker", slow)
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.scan_sticker()
    assert started.wait(timeout=1.0), "Worker-Thread wurde nicht gestartet"
    # Zweiter Aufruf während des laufenden Scans -> kein neuer Scan.
    ctrl.scan_sticker()
    assert calls["n"] == 1
    release.set()
    _wait_scan(ctrl)


def test_validate_sticker_fields():
    from benchrestscore.controller import validate_sticker_fields

    ok, err = validate_sticker_fields("09:15", 8, 1, 6)
    assert ok is True and err is None
    # Ganzzahl-Strings werden akzeptiert; einstellige Stunde erlaubt (Schema)
    ok, err = validate_sticker_fields("9:15", "8", "1", "6")
    assert ok is True and err is None
    # Zeit nicht HH:MM -> Fehler
    for bad_time in ("25:00", "09:61", "9:6", "", "abc"):
        ok, err = validate_sticker_fields(bad_time, 8, 1, 6)
        assert ok is False and err == "dialog.measurement.manual_error_time", \
            f"{bad_time!r} sollte ungültig sein"
    # Nicht-ganzzahlige Werte -> Fehler (auch bool/float)
    for bad in (8.5, True, "abc", ""):
        ok, err = validate_sticker_fields("09:15", bad, 1, 6)
        assert ok is False and err == "dialog.measurement.manual_error_int"
    ok, err = validate_sticker_fields("09:15", 8, "x", 6)
    assert ok is False and err == "dialog.measurement.manual_error_int"
    ok, err = validate_sticker_fields("09:15", 8, 1, None)
    assert ok is False and err == "dialog.measurement.manual_error_int"


def test_manual_sticker_adopts_meta(tmp_path):
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    err = ctrl.manual_sticker("09:15", 8, 1, 6)
    assert err is None
    assert ctrl.sticker_status == "ok"
    assert ctrl.sticker_meta == {"zeit": "09:15", "stand": 8, "dg": 1,
                                 "sch_nr": 6}
    # Dialog wird nach erfolgreicher Übernahme geschlossen.
    assert ctrl.manual_dialog_open is False


def test_manual_sticker_rejects_invalid(tmp_path):
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    err = ctrl.manual_sticker("25:00", 8, 1, 6)
    assert err == "dialog.measurement.manual_error_time"
    assert ctrl.sticker_meta is None
    assert ctrl.sticker_status is None
    err = ctrl.manual_sticker("09:15", "a", 1, 6)
    assert err == "dialog.measurement.manual_error_int"
    assert ctrl.sticker_meta is None


def test_scan_and_manual_share_adoption_point(monkeypatch, tmp_path):
    """Scan und manuelle Eingabe laufen über denselben Übernahme-Schritt."""
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = str(tmp_path / "settings.json")
    calls = {"adopt": 0}
    monkeypatch.setattr(
        "benchrestscore.controller._extract_sticker",
        lambda frame, config=None, transport=None: {
            "zeit": "09:15", "stand": 8, "dg": 1, "sch_nr": 6})

    def fake_adopt(self, meta):
        calls["adopt"] += 1
        self.sticker_meta = meta
        self.sticker_status = "ok"

    monkeypatch.setattr("benchrestscore.controller.AppController._adopt_sticker_meta",
                        fake_adopt)
    ctrl.set_brsmatch_config("https://b.test/v1", "k", 0, True)
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.scan_sticker()
    _wait_scan(ctrl)
    assert calls["adopt"] == 1
    assert ctrl.sticker_status == "ok"
    ctrl.manual_sticker("10:00", 3, 2, 4)
    assert calls["adopt"] == 2


def test_manual_dialog_state():
    ctrl = _reach_measuring(make_ctrl())
    assert ctrl.manual_dialog_open is False
    assert ctrl.manual_dialog_error is None
    ctrl.open_manual_dialog()
    assert ctrl.manual_dialog_open is True
    # Öffnen setzt einen ggf. alten Fehlerzustand zurück.
    ctrl.manual_dialog_error = "dialog.measurement.manual_error_time"
    ctrl.open_manual_dialog()
    assert ctrl.manual_dialog_error is None
    ctrl.close_manual_dialog()
    assert ctrl.manual_dialog_open is False
    # Schließen übernimmt keine Werte.
    assert ctrl.sticker_meta is None


def test_check_background_updates_reference_on_ok():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    model = ctrl.background_model
    assert model.has_reference
    ref0 = model.reference.copy()
    frame = _structured_frame()
    # leicht aufgehellter Frame, der weiterhin OK liefert (Belichtungs-Drift)
    bright = np.clip(frame.astype(np.float32) * 1.3, 0, 255).astype(np.uint8)
    ctrl.capture_worker.current_frame = bright
    res = ctrl.check_background()
    assert res is not None and res.status == MonitorStatus.OK
    assert not np.array_equal(model.reference, ref0)


def test_check_background_no_update_when_unavailable():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    model = ctrl.background_model
    ref0 = model.reference.copy()
    foreign = np.random.default_rng(99).integers(0, 255, (240, 320), dtype=np.uint8)
    ctrl.capture_worker.current_frame = foreign
    res = ctrl.check_background()
    assert res.status == MonitorStatus.UNAVAILABLE
    assert np.array_equal(model.reference, ref0)


def test_check_background_no_update_on_large_deviation():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    model = ctrl.background_model
    ref0 = model.reference.copy()
    frame = _structured_frame()
    M = np.float32([[1, 0, 6], [0, 1, 0]])
    shifted = cv2.warpAffine(frame, M, (320, 240), borderValue=128)
    ctrl.capture_worker.current_frame = shifted
    res = ctrl.check_background()
    # 1. Überschreitung -> OK (Hysterese), aber Abweichung > 0.5*Schwelle
    assert res.status == MonitorStatus.OK
    assert np.array_equal(model.reference, ref0)


def test_check_background_skips_reference_update_when_disabled():
    # `update_reference=False` (Sofort-Check nach Wiederherstellung): Status OK
    # darf die dichte Referenz NICHT nachführen (teures undistort im UI-Thread).
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    model = ctrl.background_model
    ref0 = model.reference.copy()
    frame = _structured_frame()
    bright = np.clip(frame.astype(np.float32) * 1.3, 0, 255).astype(np.uint8)
    ctrl.capture_worker.current_frame = bright
    res = ctrl.check_background(update_reference=False)
    assert res is not None and res.status == MonitorStatus.OK
    assert np.array_equal(model.reference, ref0)


def test_update_tint_mask():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    frame = _structured_frame()
    ctrl.capture_worker.current_frame = frame
    model = ctrl.background_model
    assert model.tint_mask is None and model.tint_tick == 0
    # Option aus -> No-op
    ctrl.filters.tint = False
    assert ctrl.update_tint_mask() is False
    assert model.tint_mask is None and model.tint_tick == 0
    # Option an -> Maske gesetzt (halbe Referenz-Skala, uint8 0/1), Tick inkrementiert
    ctrl.filters.tint = True
    assert ctrl.update_tint_mask() is True
    assert model.tint_tick == 1
    assert model.tint_mask is not None
    assert model.tint_mask.shape == (model.reference.shape[0] // 2,
                                     model.reference.shape[1] // 2)
    assert model.tint_mask.dtype == np.uint8
    assert set(np.unique(model.tint_mask)).issubset({0, 1})
    assert ctrl.update_tint_mask() is True
    assert model.tint_tick == 2


def test_update_tint_mask_noop_without_reference():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    ctrl.filters.tint = True
    ctrl.background_model = BackgroundModel()  # ungelernt, keine Referenz
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.update_tint_mask() is False
    assert ctrl.background_model.tint_mask is None
    assert ctrl.background_model.tint_tick == 0


def test_update_tint_mask_foreign_object_not_tinted():
    # Metall-Lineal (großer, solider Fremd-Block) liegt weit oberhalb der
    # statischen Distanz-Schwelle: der Block bleibt unverfärbt, die Tischfläche
    # wird eingefärbt.
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    frame = cv2.cvtColor(_structured_frame(), cv2.COLOR_GRAY2BGR)
    rng = np.random.default_rng(3)
    frame = np.clip(frame.astype(np.float32)
                    + rng.normal(0, 6, frame.shape), 0, 255).astype(np.uint8)
    foreign = frame.copy()
    x0, y0, x1, y1 = 80, 60, 160, 120
    foreign[y0:y1, x0:x1] = 250
    ctrl.capture_worker.current_frame = foreign
    ctrl.filters.tint = True
    assert ctrl.update_tint_mask() is True
    mask = ctrl.background_model.tint_mask
    assert mask is not None
    # Maske in halber Referenz-Skala; Fremd-Block entsprechend herunterskalieren
    scale = REFERENCE_SCALE * 2
    rh, rw = mask.shape[:2]
    r0, r1 = y0 // scale, y1 // scale
    c0, c1 = x0 // scale, x1 // scale
    assert r1 <= rh and c1 <= rw
    ruler = mask[r0:r1, c0:c1]
    table = np.zeros_like(mask, dtype=bool)
    table[r1:, :] = True
    table[:r0, c1:] = True
    # Nur Kanten-Artefakte der Downscaling-Kante dürfen eingefärbt sein
    assert (ruler > 0).mean() < 0.05
    assert (mask[table] > 0).mean() > 0.5


def test_finish_background_releases_camera():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.learn_background() is True
    ctrl.capture_worker.current_frame = _structured_frame()  # Simulation Live-Frame
    assert ctrl.finish_background() is True
    assert ctrl.state is AppState.MEASURING
    assert ctrl.capture_worker.paused is False
    assert ctrl.measuring_enabled is True


def test_abort_in_learn_prompt_goes_idle():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    assert ctrl.state is AppState.LEARN_PROMPT
    ctrl.cancel_calibration()
    assert ctrl.state is AppState.IDLE
    assert ctrl.background_model.learned is False


def test_request_calibration_in_learn_result_goes_idle():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.learn_background() is True
    assert ctrl.state is AppState.LEARN_RESULT
    assert ctrl.request_calibration() is False
    assert ctrl.state is AppState.IDLE
    assert ctrl.background_model.learned is False


def test_invalidate_background_on_reset():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.reset()
    assert ctrl.state is AppState.IDLE
    assert ctrl.background_model.learned is False
    assert ctrl.last_background_check is None


def test_invalidate_background_on_camera_change():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    ctrl.calibration.calibrated = True
    ctrl._reset_measurement_state()
    assert ctrl.background_model.learned is False
    assert ctrl.last_background_check is None


def test_check_background_once_and_result():
    ctrl = make_ctrl()
    ctrl.calibration = MatiCal()
    ctrl.calibration.calibrated = True
    _reach_measuring(ctrl)

    r1 = ctrl.check_background()
    assert r1 is not None
    assert r1.status == MonitorStatus.OK
    # ein weiterer Check (gleicher Frame) -> wieder OK
    r2 = ctrl.check_background()
    assert r2 is not None
    assert r2.status == MonitorStatus.OK
    # Ergebnis steht für die UI bereit
    assert ctrl.last_background_check is r2


def test_check_background_requires_learned_model():
    ctrl = make_ctrl()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.finish_background()  # ohne lernen -> None (Guard greift nicht am State)
    # ohne gelerntes Modell -> kein Check
    assert ctrl.background_model.learned is False
    ctrl.state = AppState.MEASURING
    assert ctrl.check_background() is None


def test_check_background_only_in_measuring():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.reset()
    assert ctrl.check_background() is None


def test_start_stop_background_monitor():
    import time as _time
    ctrl = make_ctrl()
    assert ctrl._background_monitor_thread is None
    ctrl.start_background_monitor()
    thread = ctrl._background_monitor_thread
    assert thread is not None and thread.is_alive()
    # idempotent: erneuter Start startet keinen zweiten Thread
    ctrl.start_background_monitor()
    assert ctrl._background_monitor_thread is thread
    _time.sleep(0.05)
    ctrl.stop_background_monitor()
    assert ctrl._background_monitor_thread is None
    assert not thread.is_alive()


# --- Kalibrier-Recovery (volles Set) ---


def test_finish_background_writes_full_set():
    ctrl = make_ctrl()
    frame = _structured_frame()
    ctrl.capture_worker.current_frame = frame
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = frame
    # Roh-Frame (Karte) + Visual für die Kalibrier-Schnappschüsse simulieren
    ctrl.calibration.frame = frame.copy()
    ctrl.calibration.visual = frame.copy()
    assert ctrl.learn_background() is True
    # noch kein Marker, bevor finalisiert
    assert cr.read_json(cr.session_marker_path()) is None
    assert ctrl.finish_background() is True
    # volles Set: Kalibrierung + Hintergrund + Marker
    assert cr.read_json(cr.session_marker_path()) is not None
    sidecar = cr.read_json(cr.calibration_json_path())
    assert sidecar is not None and sidecar.get("ok") is True
    assert sidecar.get("has_background") is True
    bg = cr.read_json(cr.background_json_path())
    assert bg is not None and len(bg["keypoints"]) > 0
    assert os.path.exists(cr.calibration_png_path())
    assert os.path.exists(cr.background_png_path())
    # nach Finish: Indikator steht sofort auf OK (kein n/a durch Overlay-Frame)
    assert ctrl.last_background_check is not None
    assert ctrl.last_background_check.status == MonitorStatus.OK


def test_finish_background_persists_undistorted_png():
    ctrl = make_ctrl()
    frame = _structured_frame()
    bgr = np.dstack([frame, frame, frame])  # 3-Kanal, wie der Kamera-Frame
    ctrl.calibration = ShiftCal(*bgr.shape[:2], dx=3)
    ctrl.capture_worker.current_frame = bgr
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = bgr
    ctrl.calibration.frame = bgr.copy()
    ctrl.calibration.visual = bgr.copy()
    assert ctrl.learn_background() is True
    assert ctrl.finish_background() is True
    import cv2 as _cv2
    saved = _cv2.imread(cr.background_png_path())
    assert saved is not None and saved.shape == bgr.shape
    # persistierte PNG = LUT-entzerrt (verschoben), nicht der Roh-Frame
    assert not np.array_equal(saved, bgr)
    assert np.array_equal(saved, _expected_shift(bgr, 3))


def test_finish_background_persists_undistorted_overlay():
    ctrl = make_ctrl()
    frame = _structured_frame()
    bgr = np.dstack([frame, frame, frame])
    ctrl.calibration = ShiftCal(*bgr.shape[:2], dx=3)
    ctrl.capture_worker.current_frame = bgr
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = bgr
    ctrl.calibration.frame = bgr.copy()
    ctrl.calibration.visual = bgr.copy()
    assert ctrl.learn_background() is True
    overlay = ctrl._pending_background_overlay
    assert overlay is not None and overlay.ndim == 3
    assert ctrl.finish_background() is True
    import cv2 as _cv2
    saved = _cv2.imread(cr.background_overlay_path())
    assert saved is not None and saved.shape == overlay.shape
    # Overlay-PNG ebenfalls entzerrt (Keypoints an der entzerrten Position)
    assert not np.array_equal(saved, overlay)
    assert np.array_equal(saved, _expected_shift(overlay, 3))


def test_monitor_skips_frozen_learn_overlay():
    ctrl = make_ctrl()
    frame = _structured_frame()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = frame
    assert ctrl.learn_background() is True
    assert ctrl.state is AppState.LEARN_RESULT
    assert ctrl._learn_overlay_frame is not None
    ctrl.calibration = MatiCal()
    ctrl.calibration.calibrated = True
    # Monitor-Check auf dem eingefrorenen Overlay -> kein Check, kein UNAVAILABLE
    ctrl.state = AppState.MEASURING
    assert ctrl.check_background() is ctrl.last_background_check  # Skip-Pfad
    # Live-Frame (neues Objekt) -> Check läuft normal
    ctrl.capture_worker.current_frame = frame.copy()
    res = ctrl.check_background()
    assert res is not None
    assert res.status == MonitorStatus.OK


def test_abort_removes_session_marker():
    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.start_calibration()
    ctrl.accept_calibration()
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.learn_background() is True
    assert cr.write_session_marker(320, 240, 10, "t") is True
    ctrl.cancel_calibration()
    assert cr.read_json(cr.session_marker_path()) is None


def _write_fake_session(width, height):
    """Volle Session (Sidecar+Background+Marker) direkt ins Temp-Config schreiben."""
    model = BackgroundModel()
    img = _structured_frame()
    assert model.learn(img) is True
    bg = model.to_dict()
    bg["width"] = width
    bg["height"] = height
    bg["keypoint_count"] = model.keypoint_count
    assert cr.write_json(cr.background_json_path(), bg)
    sidecar = {
        "ok": True, "width": width, "height": height,
        "has_background": True,
        "mean_um": 40.0, "sd_um": 8.0,
        "mat": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "mati": [[20.0, 0.0, 0.0], [0.0, 20.0, 0.0], [0.0, 0.0, 1.0]],
        "channel_params": [[0.0] * 16] * 3,
    }
    assert cr.write_json(cr.calibration_json_path(), sidecar)
    assert cr.write_session_marker(width, height, model.keypoint_count, "t")
    return model


def test_recover_calibration_success():
    model = _write_fake_session(320, 240)
    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    ctrl.calibration = MatiCal()
    assert ctrl.recover_calibration() is True
    assert ctrl.state is AppState.MEASURING
    assert ctrl.measuring_enabled is True
    assert ctrl.background_model.learned is True
    assert ctrl.background_model.keypoint_count == model.keypoint_count
    assert ctrl.recovery_error is None
    # Monitor hat sofort einen Status geliefert (synchroner Check)
    assert ctrl.last_background_check is not None


def test_recover_calibration_wrong_resolution():
    _write_fake_session(999, 240)
    ctrl = make_ctrl()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    ctrl.calibration = MatiCal()
    assert ctrl.recover_calibration() is False
    assert ctrl.state is AppState.IDLE
    assert ctrl.recovery_error == "resolution"


def test_recover_calibration_no_session():
    cr.remove_session_marker()
    ctrl = make_ctrl()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    assert ctrl.recover_calibration() is False
    assert ctrl.state is AppState.IDLE
    assert ctrl.recovery_error == "no_session"


def test_recover_requires_idle():
    _write_fake_session(320, 240)
    ctrl = make_ctrl()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    ctrl.calibration = MatiCal()
    ctrl.state = AppState.MEASURING
    assert ctrl.recover_calibration() is False


def test_recover_skips_check_on_waiting_screen():
    # Recovery gegen den initialen Warte-Bildschirm der Kamera: kein sofortiger
    # UNAVAILABLE-Check, der Status bleibt offen (None) bis zum ersten Live-Frame.
    _write_fake_session(320, 240)
    ctrl = make_ctrl()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    ctrl.calibration = MatiCal()
    waiting = np.full((240, 320, 3), 0, dtype=np.uint8)
    ctrl.capture_worker.waiting_screen = waiting
    ctrl.capture_worker.current_frame = waiting
    assert ctrl.recover_calibration() is True
    assert ctrl.state is AppState.MEASURING
    assert ctrl.last_background_check is None  # kein n/a vom Warte-Bildschirm


def test_recover_checks_on_live_frame():
    _write_fake_session(320, 240)
    ctrl = make_ctrl()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    ctrl.calibration = MatiCal()
    # Live-Frame (nicht Warte-Bildschirm) -> sofortiger Check liefert Status
    ctrl.capture_worker.current_frame = _structured_frame()
    assert ctrl.recover_calibration() is True
    assert ctrl.last_background_check is not None


def test_recover_calibration_sets_reference():
    _write_fake_session(320, 240)
    # PNG der Session schreiben (LUT-entzerrte Tisch-Referenz)
    frame = _structured_frame()
    bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    assert cv2.imwrite(cr.background_png_path(), bgr)
    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    ctrl.calibration = MatiCal()
    assert ctrl.recover_calibration() is True
    assert ctrl.background_model.learned is True
    assert ctrl.background_model.has_reference is True


def test_recover_calibration_without_reference_png():
    _write_fake_session(320, 240)
    # kein PNG (ggf. vom vorherigen Test aufgeräumt) -> Referenz fehlt,
    # Session bleibt gültig (Gruppenerkennung n/a)
    try:
        os.unlink(cr.background_png_path())
    except OSError:
        pass
    ctrl = make_ctrl()
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.capture_worker.width = 320
    ctrl.capture_worker.height = 240
    ctrl.calibration = MatiCal()
    assert ctrl.recover_calibration() is True
    assert ctrl.background_model.learned is True
    assert ctrl.background_model.has_reference is False


class _RefRuler(Ruler):
    """Ruler-Fake mit Messpunkten für `save_reference`."""

    def __init__(self, n=2):
        self.enabled = True
        self.point_count = n
        self.metric = np.zeros((n, 3), dtype=np.float32)
        for i in range(n):
            self.metric[i, 0] = float(i)
            self.metric[i, 1] = float(-i)


def test_toggle_reference_mode_clears_state():
    ctrl = make_ctrl()
    assert ctrl.toggle_reference_mode() is True
    assert ctrl.reference_mode is True
    ctrl.reference_info = 2
    assert ctrl.toggle_reference_mode() is False
    assert ctrl.reference_mode is False
    assert ctrl.reference_info is None


def test_save_reference_guards():
    # ausserhalb MEASURING
    ctrl = make_ctrl()
    ctrl.toggle_reference_mode()
    assert ctrl.save_reference() is False
    assert ctrl.reference_error == "not_measuring"
    # MEASURING, Modus aus
    ctrl2 = _reach_measuring(make_ctrl())
    assert ctrl2.save_reference() is False
    assert ctrl2.reference_error == "mode_off"
    # MEASURING, Modus an, keine Punkte
    ctrl3 = _reach_measuring(make_ctrl())
    ctrl3.toggle_reference_mode()
    ctrl3.ruler = _RefRuler(n=0)
    assert ctrl3.save_reference() is False
    assert ctrl3.reference_error == "no_points"


def test_reference_status_at_lifecycle():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.ruler = _RefRuler(n=0)
    ctrl.toggle_reference_mode()
    assert ctrl.reference_status_at is None
    # save_reference (auch bei Fehlschlag) startet das Zeitfenster
    ctrl.save_reference()
    assert ctrl.reference_status_at is not None
    # Ausschalten des Modus löscht das Zeitfenster
    ctrl.toggle_reference_mode()
    assert ctrl.reference_status_at is None
    # _reset_measurement_state löscht es ebenfalls
    ctrl.reference_status_at = 1.0
    ctrl._reset_measurement_state()
    assert ctrl.reference_status_at is None


def test_save_reference_writes_dataset(monkeypatch, tmp_path):
    monkeypatch.setenv("BRS_REFERENCE_DATASET", str(tmp_path))
    ctrl = _reach_measuring(make_ctrl())
    cal = MatiCal()
    cal.frame = _structured_frame()
    cal.visual = _structured_frame()
    ctrl.calibration = cal
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.ruler = _RefRuler(n=2)
    ctrl.toggle_reference_mode()
    assert ctrl.save_reference() is True
    assert ctrl.reference_info == 2
    assert ctrl.reference_error is None
    samples = list_reference_samples(str(tmp_path))
    assert len(samples) == 1
    assert ctrl.reference_sample == os.path.basename(samples[0])
    for name in (CALIBRATION_JSON, CALIBRATION_PNG, CALIBRATION_OVERLAY_PNG,
                 BACKGROUND_JSON, BACKGROUND_PNG, EVALUATION_PNG, RAW_PNG,
                 METRICS_JSON):
        assert os.path.exists(os.path.join(samples[0], name)), name


def test_save_reference_numbering_ascending(monkeypatch, tmp_path):
    monkeypatch.setenv("BRS_REFERENCE_DATASET", str(tmp_path))
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()
    ctrl.capture_worker.current_frame = _structured_frame()
    ctrl.ruler = _RefRuler(n=1)
    ctrl.toggle_reference_mode()
    assert ctrl.save_reference() is True
    first = ctrl.reference_sample
    assert ctrl.save_reference() is True
    second = ctrl.reference_sample
    assert first != second
    assert first < second  # aufsteigend (sample_01, sample_02)
    samples = [os.path.basename(s) for s in list_reference_samples(str(tmp_path))]
    assert samples == sorted(samples)


class _QcCal(Cal):
    """Kalibrierung mit Metrik-Matrix + Kanal-Params (für run_card_qc)."""

    def __init__(self):
        super(_QcCal, self).__init__()
        s = 20.0
        self.mat = np.diag([1.0 / s, 1.0 / s, 1.0])
        self.mati = np.diag([s, s, 1.0])
        self.channel_params = np.zeros((3, 20))


def _write_qc_sidecar(grid_metric):
    """Temporäre `last_calibration.json` (mit/ohne `grid_metric`)."""
    cfg = tempfile.mkdtemp(prefix="brs_qc_sidecar_")
    cam = os.path.join(cfg, "benchrestscore")
    os.makedirs(cam, exist_ok=True)
    path = os.path.join(cam, "last_calibration.json")
    data = {"ok": True}
    if grid_metric is not None:
        data["grid_metric"] = grid_metric
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(data, f)
    return path


def _wait_qc(ctrl, timeout=5.0):
    """Warten, bis der Card-QC-Hintergrund-Thread fertig ist."""
    import time as _t
    thread = getattr(ctrl, "card_qc_thread", None)
    if thread is not None:
        thread.join(timeout)
    deadline = _t.time() + timeout
    while getattr(ctrl, "card_qc_running", False) and _t.time() < deadline:
        _t.sleep(0.01)


def test_card_qc_requires_measuring():
    ctrl = make_ctrl()
    assert ctrl.run_card_qc() is False
    assert ctrl.card_qc_error == "not_measuring"


def test_card_qc_requires_calibration():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = MatiCal()  # ohne Kanal-Parameter
    assert ctrl.run_card_qc() is False
    assert ctrl.card_qc_error == "no_calibration"


def test_card_qc_requires_reference():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = _QcCal()
    path = _write_qc_sidecar(None)
    orig = cr.calibration_json_path
    try:
        cr.calibration_json_path = lambda: path
        assert ctrl.run_card_qc() is False
        assert ctrl.card_qc_error == "no_reference"
    finally:
        cr.calibration_json_path = orig


def test_card_qc_grid_not_detected():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = _QcCal()
    ctrl.capture_worker.current_frame = _structured_frame()

    import benchrestscore.controller as _c
    from benchrestscore.calibration_card_qc import GridResult
    orig_detect = _c.detect_grid_metric
    orig_path = _c.calibration_json_path
    _c.calibration_json_path = lambda: _write_qc_sidecar([[0.0, 0.0]])
    try:
        def _no_grid(frame, calibration):
            return GridResult(None, None, 37)
        _c.detect_grid_metric = _no_grid
        assert ctrl.run_card_qc() is True
        _wait_qc(ctrl)
        assert ctrl.card_qc_error == "no_grid"
        assert ctrl.card_qc_circles == 37
    finally:
        _c.detect_grid_metric = orig_detect
        _c.calibration_json_path = orig_path


def test_card_qc_success_persists():
    ctrl = _reach_measuring(make_ctrl())
    ctrl.calibration = _QcCal()
    ctrl.capture_worker.current_frame = np.full((60, 80, 3), 128, dtype=np.uint8)

    grid = np.zeros((2, 2, 2))
    saved = {}

    import benchrestscore.controller as _mod
    from benchrestscore.calibration_card_qc import GridResult

    def _fake_detect(frame, calibration):
        return GridResult(grid, np.zeros((2, 2, 2)), 0)

    def _fake_save(payload, overlay=None):
        saved["payload"] = payload
        return True

    orig_detect = _mod.detect_grid_metric
    orig_save = _mod._qc_save_result
    orig_path = _mod.calibration_json_path
    _mod.detect_grid_metric = _fake_detect
    _mod._qc_save_result = _fake_save
    try:
        # Sidecar mit exakt diesem Raster = identische Karte -> in Spec
        _mod.calibration_json_path = lambda: _write_qc_sidecar(grid.tolist())
        assert ctrl.run_card_qc() is True
        _wait_qc(ctrl)
        assert ctrl.card_qc_error is None
        assert ctrl.card_qc_result is not None
        assert ctrl.card_qc_result["pass"] is True
        assert saved["payload"]["pass"] is True
    finally:
        _mod.detect_grid_metric = orig_detect
        _mod._qc_save_result = orig_save
        _mod.calibration_json_path = orig_path


# ---- BRSMatch Query-API-Lookup + Wertung ----


def _brs_transport(responses):
    """httpx.Transport-Fake für den BRSMatch-API-Client (erste Antwort)."""
    import httpx

    class T:
        def __init__(self):
            self.request = None

        def handle_request(self, request):
            self.request = request
            body = responses[0]
            if isinstance(body, tuple):
                status, payload = body
                return httpx.Response(status, json=payload, request=request)
            if isinstance(body, int):
                return httpx.Response(body, text="error", request=request)
            return httpx.Response(200, json=body, request=request)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return T()


def _brs_config_ctrl():
    """Controller in MEASURING mit aktiviertem BRSMatch + Messwert."""
    ctrl = _reach_measuring(make_ctrl())
    ctrl.settings_path = _VISION_OFF_SETTINGS
    ctrl.set_brsmatch_config("https://brs.test", "k", 7, True)
    ctrl.mbox.distance = 12.34
    return ctrl


def _wait_lookup(ctrl):
    t = getattr(ctrl, "_lookup_thread", None)
    if t is not None:
        t.join(timeout=5.0)


def _wait_wertung(ctrl):
    t = getattr(ctrl, "_wertung_thread", None)
    if t is not None:
        t.join(timeout=5.0)


_BRS_LOOKUP_OK = {
    "participant": {
        "start_number": 12, "first_name": "Hans", "last_name": "Müller",
        "club": "SV Test", "caliber": ".243/6 mm",
    },
    "discipline": {
        "id": 3, "class_name": "100 m HV", "distance_m": 100,
        "matches": 10, "shots_per_match": 5,
    },
    "match_index": 2,
    "existing_scores": 0,
}


def test_lookup_runs_after_adopt(tmp_path):
    ctrl = _brs_config_ctrl()
    transport = _brs_transport([_BRS_LOOKUP_OK])
    ctrl._brs_transport = transport
    err = ctrl.manual_sticker("09:15", 4, 2, 12)
    assert err is None
    _wait_lookup(ctrl)
    assert ctrl.lookup_status == "ok"
    assert ctrl.lookup_result["participant"]["last_name"] == "Müller"
    assert ctrl.lookup_result["existing_scores"] == 0
    assert transport.request is not None
    assert transport.request.url.path == "/7/api/lookup"


def test_lookup_error_kinds(tmp_path):
    for status, key in (
            (404, "dialog.measurement.lookup_no_belegung"),
            (409, "dialog.measurement.lookup_mismatch"),
            (401, "dialog.measurement.lookup_auth"),
            (500, "dialog.measurement.lookup_server")):
        ctrl = _brs_config_ctrl()
        ctrl._brs_transport = _brs_transport([status])
        ctrl.manual_sticker("09:15", 4, 2, 12)
        _wait_lookup(ctrl)
        assert ctrl.lookup_status == "error", f"Status {status}"
        assert ctrl.lookup_error == key, f"Status {status}"
        assert ctrl.lookup_result is None


def test_lookup_discards_stale_result():
    import time as _time
    ctrl = _brs_config_ctrl()
    release = threading.Event()
    started = threading.Event()

    class SlowTransport:
        def handle_request(self, request):
            import httpx
            started.set()
            release.wait(timeout=5.0)
            return httpx.Response(200, json=_BRS_LOOKUP_OK, request=request)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    ctrl._brs_transport = SlowTransport()
    ctrl.manual_sticker("09:15", 4, 2, 12)   # A: hängt im Transport
    assert started.wait(timeout=1.0), "Lookup-Thread wurde nicht gestartet"
    # B: neue Werte mit schneller, unterschiedlicher Antwort.
    data = dict(_BRS_LOOKUP_OK)
    data["participant"] = dict(_BRS_LOOKUP_OK["participant"],
                               last_name="Schmidt", start_number=20)
    ctrl._brs_transport = _brs_transport([data])
    ctrl.manual_sticker("10:00", 5, 3, 20)
    _wait_lookup(ctrl)
    # Stale-Antwort von A freigeben; sie darf nichts mehr ändern.
    release.set()
    _wait_lookup(ctrl)
    assert ctrl.lookup_result["participant"]["last_name"] == "Schmidt"
    assert ctrl.lookup_result["participant"]["start_number"] == 20


def test_request_wertung_guards():
    ctrl = _brs_config_ctrl()
    # Ohne Lookup -> kein Upload-Stoß.
    assert ctrl.request_wertung() is False
    ctrl._brs_transport = _brs_transport([_BRS_LOOKUP_OK])
    ctrl.manual_sticker("09:15", 4, 2, 12)
    _wait_lookup(ctrl)
    # Ohne Messwert -> kein Upload-Stoß.
    ctrl.mbox.distance = -1.0
    assert ctrl.request_wertung() is False
    ctrl.mbox.distance = 12.34
    ctrl.canvas.calls.clear()
    # existing_scores == 0 -> sofortige Framebuffer-Kopie.
    assert ctrl.request_wertung() is True
    assert "request_wertung_capture" in ctrl.canvas.calls


def test_request_wertung_existing_scores_opens_confirm():
    ctrl = _brs_config_ctrl()
    data = dict(_BRS_LOOKUP_OK, existing_scores=2)
    ctrl._brs_transport = _brs_transport([data])
    ctrl.manual_sticker("09:15", 4, 2, 12)
    _wait_lookup(ctrl)
    ctrl.canvas.calls.clear()
    assert ctrl.request_wertung() is True
    assert ctrl.confirm_dialog_open is True
    assert "request_wertung_capture" not in ctrl.canvas.calls
    # Abbruch -> kein Upload.
    ctrl.cancel_overwrite()
    assert ctrl.confirm_dialog_open is False
    assert ctrl.confirm_meta is None
    assert "request_wertung_capture" not in ctrl.canvas.calls


def test_wertung_upload_success_resets_meta():
    ctrl = _brs_config_ctrl()
    ctrl._brs_transport = _brs_transport([_BRS_LOOKUP_OK])
    ctrl.manual_sticker("09:15", 4, 2, 12)
    _wait_lookup(ctrl)
    ctrl._brs_transport = _brs_transport([(201, {"id": 42})])
    assert ctrl.request_wertung() is True
    ctrl.on_wertung_capture(b"\x89PNG\x0d\x0a")
    _wait_wertung(ctrl)
    assert ctrl.wertung_status == "ok"
    assert ctrl.sticker_meta is None
    assert ctrl.lookup_status is None
    assert ctrl.lookup_result is None
    # Zweite Wertung ohne neue Übernahme ist nicht mehr möglich.
    assert ctrl.request_wertung() is False


def test_wertung_confirm_overwrite_uploads():
    ctrl = _brs_config_ctrl()
    data = dict(_BRS_LOOKUP_OK, existing_scores=1)
    ctrl._brs_transport = _brs_transport([data])
    ctrl.manual_sticker("09:15", 4, 2, 12)
    _wait_lookup(ctrl)
    ctrl._brs_transport = _brs_transport([(201, {"id": 7})])
    ctrl.canvas.calls.clear()
    assert ctrl.request_wertung() is True
    assert ctrl.confirm_overwrite() is True
    assert "request_wertung_capture" in ctrl.canvas.calls
    ctrl.on_wertung_capture(b"png")
    _wait_wertung(ctrl)
    assert ctrl.wertung_status == "ok"


def test_wertung_upload_error_keeps_meta():
    ctrl = _brs_config_ctrl()
    ctrl._brs_transport = _brs_transport([_BRS_LOOKUP_OK])
    ctrl.manual_sticker("09:15", 4, 2, 12)
    _wait_lookup(ctrl)
    ctrl._brs_transport = _brs_transport([(400, {"detail": "boom"})])
    ctrl.request_wertung()
    ctrl.on_wertung_capture(b"png")
    _wait_wertung(ctrl)
    assert ctrl.wertung_status == "error"
    assert ctrl.wertung_error == "dialog.measurement.wertung_validation"
    # Metadaten bleiben für einen erneuten Versuch erhalten.
    assert ctrl.sticker_meta == {"zeit": "09:15", "stand": 4, "dg": 2,
                                 "sch_nr": 12}
    assert ctrl.lookup_status == "ok"


if __name__ == "__main__":
    for fn in (test_happy_path, test_forbidden_transitions,
               test_failed_calibration, test_reset_from_measuring,
               test_request_calibration_resets_when_calibrated,
               test_request_calibration_start_when_not_calibrated,
test_start_calibration_resets_luts,
               test_reset_calibration_state_resets_luts,
               test_toggle_automation_syncs_indicator,
test_language_loads_from_settings,
                test_set_language_persists,
                test_font_scale_loads_from_settings,
                test_font_scale_default_when_missing_or_invalid,
                test_set_font_scale_persists,
                test_camera_settings_defaults,
               test_camera_settings_loads_from_settings,
               test_normalize_prefers_4k_when_available,
               test_normalize_uses_first_supported_without_4k,
               test_apply_camera_settings_full_reset,
               test_apply_camera_settings_device_change_resets,
               test_apply_camera_settings_same_settings_keeps_state,
               test_apply_camera_settings_persists,
               test_window_state_roundtrip,
               test_window_state_keys_are_independent,
               test_window_state_tolerates_invalid,
               test_camera_rotate_defaults_to_180,
               test_camera_rotate_loads_from_settings,
               test_camera_rotate_invalid_falls_back_to_180,
               test_apply_camera_settings_rotate_change_resets,
               test_apply_camera_settings_same_rotate_keeps_state,
               test_supported_presets_cached_per_device,
               test_normalize_camera_preset_falls_back,
test_learn_background_requires_learn_prompt,
                 test_learn_background_sparse_frame_fails,
                 test_learn_background_success,
                 test_learn_background_sets_reference,
                 test_check_background_updates_reference_on_ok,
                test_check_background_no_update_when_unavailable,
                test_check_background_no_update_on_large_deviation,
                test_check_background_skips_reference_update_when_disabled,
                test_finish_background_releases_camera,
               test_abort_in_learn_prompt_goes_idle,
               test_request_calibration_in_learn_result_goes_idle,
               test_invalidate_background_on_reset,
               test_invalidate_background_on_camera_change,
               test_check_background_once_and_result,
               test_check_background_requires_learned_model,
               test_check_background_only_in_measuring,
               test_start_stop_background_monitor,
               test_finish_background_writes_full_set,
               test_finish_background_persists_undistorted_png,
               test_finish_background_persists_undistorted_overlay,
               test_monitor_skips_frozen_learn_overlay,
               test_abort_removes_session_marker,
               test_recover_calibration_success,
               test_recover_calibration_wrong_resolution,
               test_recover_calibration_no_session,
               test_recover_requires_idle,
test_recover_skips_check_on_waiting_screen,
                 test_recover_checks_on_live_frame,
                 test_recover_calibration_sets_reference,
                 test_recover_calibration_without_reference_png,
                 test_toggle_reference_mode_clears_state,
                 test_save_reference_guards,
                 test_reference_status_at_lifecycle,
                 test_save_reference_writes_dataset,
                 test_save_reference_numbering_ascending,
                 test_card_qc_requires_measuring,
                 test_card_qc_requires_calibration,
                 test_card_qc_requires_reference,
                 test_card_qc_grid_not_detected,
                 test_card_qc_success_persists):
        fn()
        print(f"PASS {fn.__name__}")
    print("All FSM tests passed")