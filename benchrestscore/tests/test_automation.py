# -*- coding: utf-8 -*-
"""Headless unit tests for the automatic shot-hole detection (no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import cv2
import numpy as np

from benchrestscore.automation import (
    find_center, pixel_to_metric, metric_to_pixel,
    _ring_start, _adaptive_binary, _ring_kernel)


class FakeView:
    aspect_ratio = 1.0

    def __init__(self):
        self.view = np.eye(4)

    def glndc_location(self, x, y, w, h):
        inv = np.linalg.inv(self.view)
        gx = x / (w / 2.) - 1.
        gy = 1. - y / (h / 2.)
        return np.dot(np.array([gx, gy, 0., 1.]), inv)

    def glndc2pix(self, x, y, w, h):
        return (x + 1.) / 2. * w, (1. - y) / 2. * h


class FakeCalibration:
    """Map: 1 mm == 1 px (metric = ndc*300; ndc 1 unit == 300 px)."""
    calibrated = True

    def __init__(self):
        s = 300.0
        self.mat = np.diag([1.0 / s, 1.0 / s, 1.0])   # Metrik -> NDC
        self.mati = np.diag([s, s, 1.0])              # NDC -> Metrik


SIZE = (600, 600)


def test_finds_circle_center():
    # weisse Fläche mit dunklem Loch (Kreis) + Fake-View/Kalibrierung
    buf = np.full((600, 600, 3), 255, dtype=np.uint8)
    cv2.circle(buf, (400, 300), 10, (0, 0, 0), -1)

    res = find_center(buf, FakeView(), (403, 300), SIZE, FakeCalibration(), radius=8.0)

    assert res.ok is True
    assert res.center_metric is not None
    cx, cy = round(res.center_metric[0]), round(res.center_metric[1])
    assert abs(cx - 100) <= 2, f"center x {cx} != 100"      # 100 mm == Pixel 400
    assert abs(cy - 0) <= 2, f"center y {cy} != 0"          # 0 mm  == Pixel 300
    assert res.offset_mm is not None and 1.0 <= res.offset_mm <= 6.0


def test_empty_region_is_failure():
    buf = np.zeros((600, 600, 3), dtype=np.uint8)
    res = find_center(buf, FakeView(), (400, 300), SIZE, FakeCalibration(), radius=8.0)
    assert res.ok is False
    assert res.center_metric is None
    assert res.offset_mm is None


def test_out_of_bounds_region_is_failure():
    buf = np.full((600, 600, 3), 255, dtype=np.uint8)
    # Suchbereich läge teils außerhalb des Bildes -> keine Erkennung
    res = find_center(buf, FakeView(), (5, 5), SIZE, FakeCalibration(), radius=8.0)
    assert res.ok is False
    # Rohpunkt bleibt trotzdem rekonstruierbar (für Punkt-am-Rohklick)
    assert res.raw_metric is not None


def test_pixel_metric_roundtrip():
    view = FakeView()
    cal = FakeCalibration()
    px = (403, 297)
    metric = pixel_to_metric(view, px, SIZE, cal)
    back = metric_to_pixel(view, metric, SIZE, cal)
    assert abs(back[0] - px[0]) < 1e-6
    assert abs(back[1] - px[1]) < 1e-6


def test_metric_offset_direction():
    # 1 mm == 1 px: ein 3 px rechts liegender Punkt ist 3 mm versetzt
    view = FakeView()
    cal = FakeCalibration()
    a = pixel_to_metric(view, (400, 300), SIZE, cal)
    b = pixel_to_metric(view, (403, 300), SIZE, cal)
    assert abs(np.linalg.norm(b[:2] - a[:2]) - 3.0) < 1e-6


def test_ring_kernel_is_annulus():
    # Annulus-Kernel: aktiv nur auf einem Ring im Abstand R, nicht innen/außen
    k = _ring_kernel(41, R=10.0, thick=1.0)
    c = 20
    assert k[c, c] == 0                      # Zentrum: nicht aktiv
    assert k[c + 10, c] == 1                 # genau auf dem Ring: aktiv
    assert k[c + 5, c] == 0                  # innerhalb: nicht aktiv
    assert k[c + 15, c] == 0                 # außerhalb: nicht aktiv


def test_ring_start_finds_hole_center():
    # Dunkler Kreis auf weißem Grund: Ring-Kernel-Peak liegt im Lochzentrum.
    buf = np.full((600, 600, 3), 255, dtype=np.uint8)
    cv2.circle(buf, (400, 300), 10, (0, 0, 0), -1)
    res = find_center(buf, FakeView(), (403, 300), SIZE, FakeCalibration(), radius=8.0)
    assert res.ok is True
    cx, cy = round(res.center_metric[0]), round(res.center_metric[1])
    assert abs(cx - 100) <= 2   # Pixel 400 -> 100 mm
    assert abs(cy - 0) <= 2     # Pixel 300 -> 0 mm


def test_scheibenaufdruck_verzerrt_nicht():
    # Dunkle Aufdruck-Pixel weit außerhalb des Lochs (kein Ring im Kaliberradius)
    # dürfen das Zentrum nicht verziehen: der Ring-Kernel ignoriert sie.
    buf = np.full((600, 600, 3), 255, dtype=np.uint8)
    cv2.circle(buf, (400, 300), 10, (0, 0, 0), -1)
    # Aufdruck-Flecken bei 2.5r Abstand (dunkle, kleine Kreise ohne Lochring)
    for dx, dy in [(150, 0), (-150, 0), (0, 150), (0, -150),
                   (106, 106), (-106, -106), (106, -106), (-106, 106)]:
        cv2.circle(buf, (400 + dx, 300 + dy), 6, (0, 0, 0), -1)
    res = find_center(buf, FakeView(), (403, 300), SIZE, FakeCalibration(), radius=8.0)
    assert res.ok is True
    cx, cy = round(res.center_metric[0]), round(res.center_metric[1])
    assert abs(cx - 100) <= 3, f"center x {cx} != 100 (Aufdruck verzerrt)"
    assert abs(cy - 0) <= 3, f"center y {cy} != 0 (Aufdruck verzerrt)"


def test_klick_zu_ungenau_schlaegt_fehl():
    # Klick deutlich außerhalb des Lochs (z.B. 2r entfernt): der Fit läuft an
    # die harte Bound -> Fail-fast statt falschem Zentrum.
    buf = np.full((600, 600, 3), 255, dtype=np.uint8)
    cv2.circle(buf, (400, 300), 10, (0, 0, 0), -1)
    res = find_center(buf, FakeView(), (400 + 32, 300), SIZE, FakeCalibration(),
                      radius=8.0)
    assert res.ok is False
    assert res.center_metric is None


if __name__ == "__main__":
    for fn in (test_finds_circle_center, test_empty_region_is_failure,
               test_out_of_bounds_region_is_failure, test_pixel_metric_roundtrip,
               test_metric_offset_direction,
               test_ring_kernel_is_annulus, test_ring_start_finds_hole_center,
               test_scheibenaufdruck_verzerrt_nicht,
               test_klick_zu_ungenau_schlaegt_fehl):
        fn()
        print(f"PASS {fn.__name__}")
    print("All automation tests passed")