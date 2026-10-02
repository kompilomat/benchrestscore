# -*- coding: utf-8 -*-
"""Headless unit tests for the camera module (no window/GL, no real device).

Abgedeckt: GStreamer-Pipeline-Builder (feste rotate-180-Rotation),
Waiting-Screen-Größe, Preset-Probe (mit injizierbarem Mock-Opener: Filterung,
Fallback, keine leere Liste), Geräte-Enumeration und den View-Dimensionswechsel.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

from benchrestscore.camera import (
    BRSCamera,
    CAMERA_PRESETS,
    CAMERA_PRESET_FALLBACK,
    DEFAULT_CAMERA_DEVICE,
    build_waiting_screen,
    gst_pipeline_string,
    list_camera_devices,
    parse_v4l2_formats,
    probe_supported_presets,
)
from benchrestscore.view import BRSView, BRSScrollZoom


def _pipe(device=DEFAULT_CAMERA_DEVICE, w=1920, h=1080, fps=30, rotate=180):
    return gst_pipeline_string(device, w, h, fps, rotate)


def test_pipeline_string_has_rotate_180():
    s = _pipe(device="/dev/video9", w=3840, h=2160, fps=30)
    assert s.startswith("v4l2src device=/dev/video9 io-mode=2 ! ")
    assert "image/jpeg,width=3840,height=2160,framerate=30/1" in s
    assert "! videoflip method=rotate-180 ! appsink sync=false" in s
    assert s.endswith("! appsink sync=false")


def test_pipeline_string_rotate_0():
    s = _pipe(device="/dev/video0", w=1920, h=1080, fps=30, rotate=0)
    # GStreamer kennt kein rotate-0; 0° = method=none (Identität)
    assert "videoflip method=none" in s
    assert "rotate-0" not in s


def test_pipeline_string_rotate_default_is_180():
    s = gst_pipeline_string("/dev/video0", 1920, 1080, 30)
    assert "videoflip method=rotate-180" in s


def test_pipeline_string_rotate_invalid_raises():
    for bad in (90, 45, -180, 360, "rotate-90", None):
        try:
            gst_pipeline_string("/dev/video0", 1920, 1080, 30, rotate=bad)
        except ValueError:
            continue
        raise AssertionError(f"rotate={bad!r} sollte ValueError werfen")


def test_camera_worker_stores_rotate():
    cam = BRSCamera(device="/dev/videoX", width=1920, height=1080, fps=30,
                    rotate=0)
    assert cam.rotate == 0
    cam180 = BRSCamera(device="/dev/videoX", width=1920, height=1080, fps=30)
    assert cam180.rotate == 180


def test_waiting_screen_shape_matches_config():
    cam = BRSCamera(device="/dev/videoX", width=1920, height=1080, fps=30)
    assert cam.waiting_screen.shape == (1080, 1920, 3)
    cam4k = BRSCamera(device="/dev/videoX", width=3840, height=2160, fps=30)
    assert cam4k.waiting_screen.shape == (2160, 3840, 3)


def test_waiting_screen_text_fits_at_low_resolution():
    import cv2
    for w, h in [(3840, 2160), (1920, 1080), (1280, 720)]:
        screen = build_waiting_screen(w, h)
        # dunkle Text-Pixel sind innerhalb des Bildes (kein Overflow nach
        # rechts/unten) und das Bild ist in der Zielgröße
        assert screen.shape == (h, w, 3)
        dark = screen[:, :, 0] < 100
        assert dark.any()
        # dunkle Pixel dürfen nicht in der letzten Spalte/Zeile sitzen (rechte/
        # untere Kante würde abgeschnitten)
        assert not dark[:, -1].any(), f"{w}x{h}: Text ragt rechts über"
        assert not dark[-1, :].any(), f"{w}x{h}: Text ragt unten über"


class FakeCap(object):
    def __init__(self, supported):
        self._supported = supported

    def isOpened(self):
        return self._supported

    def release(self):
        return None


def _opener_rejects_all(pipe):
    return FakeCap(False)


def _v4l2_fixture(*caps):
    """Fake-v4l2ctl-Runner: liefert stdout mit den gegebenen (w, h, fps)-Caps."""
    def _runner(device):
        lines = ["[0]: 'MJPG' (Motion-JPEG, compressed)"]
        for w, h, fps in caps:
            lines.append(f"\tSize: Discrete {w}x{h}")
            lines.append(f"\t\tInterval: Discrete {1.0 / fps:.4f}s ({fps}.000 fps)")
        return "\n".join(lines) + "\n"
    return _runner


def test_parse_v4l2_formats():
    out = (
        "[0]: 'MJPG' (Motion-JPEG, compressed)\n"
        "\tSize: Discrete 3840x2160\n"
        "\t\tInterval: Discrete 0.033s (30.000 fps)\n"
        "\t\tInterval: Discrete 0.040s (25.000 fps)\n"
        "\tSize: Discrete 1920x1080\n"
        "\t\tInterval: Discrete 0.033s (30.000 fps)\n"
        "[1]: 'YUYV' (YUYV 4:2:2)\n"
        "\tSize: Discrete 1280x720\n"
        "\t\tInterval: Discrete 0.033s (30.000 fps)\n"
    )
    caps = parse_v4l2_formats(out)
    assert (3840, 2160, 30) in caps
    assert (3840, 2160, 25) in caps
    assert (1920, 1080, 30) in caps
    # YUYV wird ignoriert (App nutzt image/jpeg)
    assert (1280, 720, 30) not in caps


def test_parse_v4l2_formats_empty():
    assert parse_v4l2_formats("") == set()
    assert parse_v4l2_formats("keine Daten") == set()


def test_probe_filters_unsupported_via_v4l2():
    # v4l2ctl meldet nur 30-fps-Varianten -> 1080p30 und 4K30 bleiben übrig.
    runner = _v4l2_fixture((1920, 1080, 30), (3840, 2160, 30))
    supported = probe_supported_presets("/dev/video0", CAMERA_PRESETS,
                                        run_v4l2=runner)
    names = [p[0] for p in supported]
    assert names == ["1080p30", "4K30"]


def test_probe_fallback_when_v4l2_empty_and_opener_rejects():
    supported = probe_supported_presets(
        "/dev/video0", CAMERA_PRESETS, run_v4l2=_v4l2_fixture(),
        opener=_opener_rejects_all)
    assert supported == [CAMERA_PRESET_FALLBACK]


def test_probe_pipeline_fallback_uses_opener():
    def _opener_30(pipe):
        return FakeCap("framerate=30/1" in pipe)

    supported = probe_supported_presets(
        "/dev/video0", CAMERA_PRESETS, run_v4l2=_v4l2_fixture(),
        opener=_opener_30)
    names = [p[0] for p in supported]
    assert names == ["1080p30", "4K30"]


def test_probe_presets_are_valid_tuples():
    for preset in CAMERA_PRESETS:
        assert len(preset) == 4
        assert isinstance(preset[0], str)
        assert preset[1] > 0 and preset[2] > 0 and preset[3] > 0


def _fake_glob(*nodes):
    """glob.glob patchen, damit list_camera_devices headless testbar ist."""
    import benchrestscore.camera as cam
    real = cam.glob.glob
    cam.glob.glob = lambda pat: sorted(nodes) if pat == "/dev/video*" else []
    return real


def test_list_camera_devices_filters_metadata_nodes():
    import benchrestscore.camera as cam
    real_glob = _fake_glob("/dev/video0", "/dev/video1")
    try:
        def _runner(dev):
            # video0 liefert MJPG, video1 (Metadata-Node) keine Formate
            if dev == "/dev/video0":
                return _v4l2_fixture((1920, 1080, 30))(dev)
            return "ioctl: VIDIOC_ENUM_FMT\n\tType: Video Capture\n"
        devices = list_camera_devices(run_v4l2=_runner)
        assert devices == ["/dev/video0"]
    finally:
        cam.glob.glob = real_glob


def test_list_camera_devices_falls_back_when_v4l2_fails():
    import benchrestscore.camera as cam
    real_glob = _fake_glob("/dev/video0", "/dev/video1")
    try:
        devices = list_camera_devices(run_v4l2=lambda dev: "")
        # Enumeration komplett fehlgeschlagen -> ungefilterte Glob-Liste
        assert devices == ["/dev/video0", "/dev/video1"]
    finally:
        cam.glob.glob = real_glob


def test_list_camera_devices_returns_sorted_paths():
    import benchrestscore.camera as cam
    real_glob = _fake_glob("/dev/video1", "/dev/video0", "/dev/videoX")
    try:
        devices = list_camera_devices(run_v4l2=lambda dev: "")
        assert devices == ["/dev/video0", "/dev/video1", "/dev/videoX"]
        for d in devices:
            assert d.startswith("/dev/video")
    finally:
        cam.glob.glob = real_glob


def test_view_set_dimensions_updates_aspect():
    v = BRSView(3840, 2160)
    assert v.aspect_ratio == 3840 / 2160
    v.set_dimensions(1920, 1080)
    assert v.width == 1920
    assert v.height == 1080
    assert v.aspect_ratio == 1920 / 1080


def test_view_set_dimensions_resets_scale():
    v = BRSView(3840, 2160)
    # 16:9-Kamera auf 16:9-Viewport -> Skalierung 1:1
    v.set_dimensions(1280, 720, 1280, 720)
    assert v.current_zoom == 1.0
    assert np.allclose(v.view[0, 0], 1.0)
    # sx
    assert np.allclose(v.view[1, 1], 1.0)    # sy


def test_center_translation_centers_world_point():
    v = BRSView(3840, 2160)
    v.set_dimensions(1280, 720, 1280, 720)
    v.view[3, 0] = 0.3
    v.view[3, 1] = -0.2
    wx, wy = 0.5, -0.4
    tx, ty = v.center_translation(wx, wy)
    # Anwenden der Ziel-Translation -> Punkt liegt bei Screen-NDC (0,0)
    v.view[3, 0] = tx
    v.view[3, 1] = ty
    ndc = np.dot(np.array([wx, wy, 0., 1.]), v.view)
    assert np.allclose(ndc[:2], (0.0, 0.0), atol=1e-9)


def test_center_translation_keeps_zoom():
    v = BRSView(3840, 2160)
    v.set_dimensions(1280, 720, 1280, 720)
    v.zoom(640, 360, +2, 1280, 720)          # auf Zoom > 1 zoomen
    sx, sy = v.view[0, 0], v.view[1, 1]
    tx, ty = v.center_translation(0.2, -0.3)
    # Methode verändert die View nicht und liefert Zoom-konsistente Translation
    assert np.allclose((v.view[0, 0], v.view[1, 1]), (sx, sy))
    assert np.allclose(tx, -sx * 0.2)
    assert np.allclose(ty, -sy * -0.3)


def test_center_translation_world_center_is_zero():
    v = BRSView(3840, 2160)
    v.set_dimensions(1280, 720, 1280, 720)
    v.view[3, 0] = 0.4
    v.view[3, 1] = 0.4
    tx, ty = v.center_translation(0.0, 0.0)
    assert np.allclose((tx, ty), (0.0, 0.0))


def _apply_fit_target(v, target):
    """Fit-Ziel (zoom, tx, ty) in die View schreiben (wie render() es täte)."""
    zoom, tx, ty = target
    sx, sy = v.aspect_scale(1280, 720)
    v.view[0, 0] = zoom * sx
    v.view[1, 1] = zoom * sy
    v.view[3, 0] = tx
    v.view[3, 1] = ty


def test_fit_target_zooms_into_compact_points():
    v = BRSView(1280, 720)
    v.set_dimensions(1280, 720, 1280, 720)
    target = v.fit_target([(-0.1, 0.0), (0.1, 0.0)], 1280, 720, margin=0.1)
    assert target is not None
    zoom, tx, ty = target
    assert np.isclose(zoom, 9.0)          # 2·(1−0.1)/0.2
    assert np.allclose((tx, ty), (0.0, 0.0))
    # Nach Anwenden liegen beide Punkte im sichtbaren Bereich (±1 NDC).
    _apply_fit_target(v, target)
    for wx, wy in ((-0.1, 0.0), (0.1, 0.0)):
        sx, sy = v.aspect_scale(1280, 720)
        ndc = np.array([sx * zoom * wx + tx, sy * zoom * wy + ty])
        assert np.all(np.abs(ndc) <= 1.0 + 1e-9)


def test_fit_target_clamps_low_zoom_to_one():
    v = BRSView(1280, 720)
    v.set_dimensions(1280, 720, 1280, 720)
    target = v.fit_target([(-2.0, 0.0), (2.0, 0.0)], 1280, 720, margin=0.1)
    assert target is not None
    zoom, _, _ = target
    assert zoom == 1.0                     # nötiger Zoom < 1 -> auf 1 geklemmt


def test_fit_target_respects_max_zoom():
    v = BRSView(1280, 720)
    v.set_dimensions(1280, 720, 1280, 720)
    target = v.fit_target([(-0.0001, 0.0), (0.0001, 0.0)], 1280, 720, margin=0.1)
    assert target is not None
    zoom, _, _ = target
    assert zoom == v.max_zoom              # 9000 -> auf max_zoom geklemmt


def test_fit_target_single_point_is_degenerate():
    v = BRSView(1280, 720)
    v.set_dimensions(1280, 720, 1280, 720)
    assert v.fit_target([(0.3, 0.2)], 1280, 720) is None
    # identische Punkte (kollabierte Bounding-Box) ebenfalls degeneriert
    assert v.fit_target([(0.1, 0.1), (0.1, 0.1)], 1280, 720) is None


def test_fit_target_centers_bbox_center():
    v = BRSView(1280, 720)
    v.set_dimensions(1280, 720, 1280, 720)
    # Punkte um (0.2, -0.3) herum -> Ziel-Zentrum muss (0.2, -0.3) sein.
    target = v.fit_target([(0.1, -0.4), (0.3, -0.2)], 1280, 720, margin=0.1)
    assert target is not None
    zoom, tx, ty = target
    sx, sy = v.aspect_scale(1280, 720)
    assert np.isclose(tx, -zoom * sx * 0.2)
    assert np.isclose(ty, -zoom * sy * -0.3)


def test_fit_target_keeps_measurement_circle_visible():
    # Integration: fit_extent (Messpunkte + großer Kreis) + fit_target.
    # Der Kreis ragt über die Punkte hinaus; nach Anwenden des Ziels müssen
    # alle Kreis-BBox-Ecken im sichtbaren Bereich (±1 NDC) liegen.
    from benchrestscore.measurement import fit_extent
    v = BRSView(1280, 720)
    v.set_dimensions(1280, 720, 1280, 720)
    pts = np.array([[0.0, 0.0], [0.4, 0.0]])
    # Kreis um (0.2, 0) mit Radius 0.3 (dist/2 + Kaliberradius)
    circle = np.array([[0.2, 0.0], [0.5, 0.0], [0.2, -0.3], [0.2, 0.3]])
    ext = fit_extent(pts, circle)
    target = v.fit_target(ext, 1280, 720, margin=0.05)
    assert target is not None
    zoom, tx, ty = target
    sx, sy = v.aspect_scale(1280, 720)
    for wx, wy in ext:
        ndc = np.array([sx * zoom * wx + tx, sy * zoom * wy + ty])
        assert np.all(np.abs(ndc) <= 1.0 + 1e-9)


def _focus_ndc(x, y, w, h):
    return x / (w / 2.) - 1., 1.0 - y / (h / 2.)


def test_scroll_zoom_focus_invariance():
    # Weltpunkt unter dem Cursor bleibt über alle Smoothing-Schritte exakt an
    # derselben Bildposition (Fokus-Formel pro Schritt).
    v = BRSView(1280, 720)
    v.set_dimensions(1280, 720, 1280, 720)
    sx, sy = 1.0, 1.0
    cx, cy = 900, 200
    fx, fy = _focus_ndc(cx, cy, 1280, 720)
    sz = BRSScrollZoom()
    sz.on_scroll(+1, cx, cy, 1280, 720, current_zoom=1.0, max_zoom=18)
    z, tx, ty = 1.0, 0.0, 0.0
    done, steps = False, 0
    while not done and steps < 200:
        steps += 1
        z, tx, ty, done = sz.step(1 / 60.0, z, tx, ty)
        px = sx * z * fx + tx
        py = sy * z * fy + ty
        assert np.isclose(px, fx, atol=1e-6)
        assert np.isclose(py, fy, atol=1e-6)
    assert done
    assert np.isclose(z, sz.target_zoom)
    assert sz.active is False


def test_scroll_zoom_accumulates_and_clamps():
    sz = BRSScrollZoom()
    # Inaktiv: Ziel startet am aktuellen Zoom
    sz.on_scroll(+1, 640, 360, 1280, 720, current_zoom=5.0, max_zoom=18)
    assert sz.active
    assert np.isclose(sz.target_zoom, 5.0 + sz.STEP)
    sz.on_scroll(+1, 640, 360, 1280, 720, current_zoom=sz.target_zoom, max_zoom=18)
    sz.on_scroll(+1, 640, 360, 1280, 720, current_zoom=sz.target_zoom, max_zoom=18)
    assert np.isclose(sz.target_zoom, 5.0 + 3 * sz.STEP)  # n Rasten -> +n·STEP
    # Klemmung oben
    for _ in range(200):
        sz.on_scroll(+1, 640, 360, 1280, 720, current_zoom=sz.target_zoom,
                     max_zoom=18)
    assert np.isclose(sz.target_zoom, 18.0)
    # Klemmung unten
    for _ in range(200):
        sz.on_scroll(-1, 640, 360, 1280, 720, current_zoom=sz.target_zoom,
                     max_zoom=18)
    assert np.isclose(sz.target_zoom, 1.0)


def test_scroll_zoom_converges_without_overshoot():
    sz = BRSScrollZoom()
    sz.on_scroll(+3, 640, 360, 1280, 720, current_zoom=1.0, max_zoom=18)
    target = sz.target_zoom                      # 1 + 3·STEP
    z, tx, ty = 1.0, 0.0, 0.0
    done = False
    while not done:
        z, tx, ty, done = sz.step(1 / 60.0, z, tx, ty)
        assert z <= target + 1e-9                # kein Overshoot
    assert np.isclose(z, target, atol=1e-9)      # Snap exakt auf das Ziel
    assert sz.active is False


def _scroll_zoom_duration(dt, zoom=1.0, tx=0.0, ty=0.0, n_steps=+3):
    sz = BRSScrollZoom()
    sz.on_scroll(n_steps, 640, 360, 1280, 720, current_zoom=zoom, max_zoom=18)
    z, tx_, ty_ = zoom, tx, ty
    t, done = 0.0, False
    while not done and t < 10.0:
        z, tx_, ty_, done = sz.step(dt, z, tx_, ty_)
        t += dt
    return t


def test_scroll_zoom_is_framerate_independent():
    # Konvergenzzeit hängt nicht von der Frame-Rate ab (exponentielles Glätten).
    t60 = _scroll_zoom_duration(1 / 60.0)
    t120 = _scroll_zoom_duration(1 / 120.0)
    t30 = _scroll_zoom_duration(1 / 30.0)
    assert np.isclose(t60, t120, rtol=0.2)
    assert np.isclose(t60, t30, rtol=0.2)


def test_scroll_zoom_out_to_one_drives_translation_to_zero():
    # Ziel == 1: Translation fährt exponentiell gegen (0,0) aus, erst dann done.
    sz = BRSScrollZoom()
    sz.on_scroll(-2, 900, 200, 1280, 720, current_zoom=2.0, max_zoom=18)
    assert np.isclose(sz.target_zoom, 1.0)
    z, tx, ty = 2.0, 0.4, -0.3
    done = False
    while not done:
        z, tx, ty, done = sz.step(1 / 60.0, z, tx, ty)
        assert z >= 1.0 - 1e-9
    assert np.isclose(z, 1.0)
    assert np.isclose(tx, 0.0)
    assert np.isclose(ty, 0.0)
    assert sz.active is False


def test_scroll_zoom_cancel_disables_step():
    sz = BRSScrollZoom()
    sz.on_scroll(+2, 640, 360, 1280, 720, current_zoom=1.0, max_zoom=18)
    sz.cancel()
    assert sz.active is False
    z, tx, ty, done = sz.step(1 / 60.0, 3.0, 0.1, -0.1)
    assert (z, tx, ty, done) == (3.0, 0.1, -0.1, True)


if __name__ == "__main__":
    for fn in (test_pipeline_string_has_rotate_180,
               test_pipeline_string_rotate_0,
               test_pipeline_string_rotate_default_is_180,
               test_pipeline_string_rotate_invalid_raises,
               test_camera_worker_stores_rotate,
               test_waiting_screen_shape_matches_config,
               test_waiting_screen_text_fits_at_low_resolution,
               test_parse_v4l2_formats, test_parse_v4l2_formats_empty,
               test_probe_filters_unsupported_via_v4l2,
               test_probe_fallback_when_v4l2_empty_and_opener_rejects,
               test_probe_pipeline_fallback_uses_opener,
               test_probe_presets_are_valid_tuples,
               test_list_camera_devices_filters_metadata_nodes,
               test_list_camera_devices_falls_back_when_v4l2_fails,
               test_list_camera_devices_returns_sorted_paths,
               test_view_set_dimensions_updates_aspect,
               test_view_set_dimensions_resets_scale,
               test_center_translation_centers_world_point,
               test_center_translation_keeps_zoom,
               test_center_translation_world_center_is_zero,
               test_fit_target_zooms_into_compact_points,
               test_fit_target_clamps_low_zoom_to_one,
               test_fit_target_respects_max_zoom,
               test_fit_target_single_point_is_degenerate,
               test_fit_target_centers_bbox_center,
               test_fit_target_keeps_measurement_circle_visible,
               test_scroll_zoom_focus_invariance,
               test_scroll_zoom_accumulates_and_clamps,
               test_scroll_zoom_converges_without_overshoot,
               test_scroll_zoom_is_framerate_independent,
               test_scroll_zoom_out_to_one_drives_translation_to_zero,
               test_scroll_zoom_cancel_disables_step):
        fn()
        print(f"PASS {fn.__name__}")
    print("All camera tests passed")