# -*- coding: utf-8 -*-
"""Headless unit tests for the measurement distance logic (no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np
import locale

from benchrestscore.measurement import max_pairwise_distance
from benchrestscore.measurement import fit_extent
from benchrestscore.measurement import BRSMeasurementBox
from benchrestscore.measurement import BRSRuler
from benchrestscore.i18n import current_language, set_language


def test_single_pair():
    m = np.array([[0., 0.], [3., 4.]])
    dist, (i, j) = max_pairwise_distance(m)
    assert abs(dist - 5.0) < 1e-9
    assert (i, j) == (0, 1)


def test_farthest_pair_selected():
    # Punkt 1 und 2 sind am weitesten auseinander
    m = np.array([[0., 0.], [1., 0.], [0., 3.]])
    dist, (i, j) = max_pairwise_distance(m)
    assert abs(dist - np.sqrt(10)) < 1e-9
    assert (i, j) == (1, 2)


def test_metric_3d_accepted():
    m = np.array([[0., 0., 0.], [2., 0., 0.], [0., 2., 0.]])
    dist, _ = max_pairwise_distance(m)
    assert abs(dist - 2.0 * np.sqrt(2)) < 1e-9


def test_fewer_than_two_points():
    m = np.array([[0., 0.]])
    dist, pair = max_pairwise_distance(m)
    assert dist == -1.0


def test_fit_extent_points_only():
    pts = np.array([[0.1, 0.2], [-0.3, 0.4]])
    ext = fit_extent(pts)
    assert ext.shape == (2, 2)
    assert np.allclose(ext, pts)
    # ohne Kreis (None oder leer) bleiben nur die Punkte
    assert np.allclose(fit_extent(pts, None), pts)
    assert np.allclose(fit_extent(pts, np.zeros((0, 2))), pts)


def test_fit_extent_includes_circle_bbox():
    pts = np.array([[0.0, 0.0], [1.0, 0.0]])
    # Kreis um (0.5, 0) mit Radius 1 -> BBox [0.5, 1.5] x [-1, 1]
    circle = np.array([[0.5, 0.0], [1.5, 0.0], [0.5, -1.0], [0.5, 1.0]])
    ext = fit_extent(pts, circle)
    # 2 Punkte + 2 BBox-Eckpunkte des Kreises
    assert ext.shape == (4, 2)
    assert np.allclose(ext[:2], pts)
    assert np.allclose(ext[2], (0.5, -1.0))
    assert np.allclose(ext[3], (1.5, 1.0))


def test_value_rows_german():
    save = current_language()
    try:
        set_language("de")
        box = BRSMeasurementBox(None)
        box.distance = 10.5
        rows = box.value_rows()
        assert len(rows) == 2
        labels = [label for label, _ in rows]
        assert labels == ["Mitte", "Außen"]
        # Werte gleich breit (%10.2f), damit die Zahlenspalte sauber ausgerichtet
        # wird (rechtsbündig per Layout, nicht per Leerzeichen-String).
        mid = locale.format_string("%10.2f", box.distance)
        outer = locale.format_string("%10.2f", box.distance + box.cal[box.ind][1])
        assert rows[0][1] == f"{mid} mm"
        assert rows[1][1] == f"{outer} mm"
        assert len(rows[0][1]) == len(rows[1][1])
        # ohne Distanz (distance < 0) leere Liste
        empty = BRSMeasurementBox(None)
        assert empty.value_rows() == []
    finally:
        set_language(save)


def test_value_rows_english():
    save = current_language()
    try:
        set_language("en")
        box = BRSMeasurementBox(None)
        box.distance = 10.5
        rows = box.value_rows()
        assert len(rows) == 2
        labels = [label for label, _ in rows]
        assert labels == ["Center", "Outside"]
        assert len(rows[0][1]) == len(rows[1][1])
    finally:
        set_language(save)


def test_auto_error_active():
    # BRSRuler.__init__ braucht GL-Kontext -> nur die Status-Attribute testen.
    ruler = object.__new__(BRSRuler)
    ruler.auto_error = False
    ruler.auto_error_at = None
    # ohne Fehler nie sichtbar
    assert ruler.auto_error_active(now=100.0) is False
    # Fehler gerade gesetzt -> sichtbar
    ruler.auto_error = True
    ruler.auto_error_at = 100.0
    assert ruler.auto_error_active(now=100.0) is True
    assert ruler.auto_error_active(now=100.0 + BRSRuler.AUTO_ERROR_DURATION - 0.01) is True
    # genau am Ende des Fensters -> nicht mehr sichtbar
    assert ruler.auto_error_active(now=100.0 + BRSRuler.AUTO_ERROR_DURATION) is False
    # ohne Zeitstempel unsichtbar
    ruler.auto_error_at = None
    assert ruler.auto_error_active(now=100.0) is False


if __name__ == "__main__":
    for fn in (test_single_pair, test_farthest_pair_selected,
               test_metric_3d_accepted, test_fewer_than_two_points,
               test_fit_extent_points_only, test_fit_extent_includes_circle_bbox,
               test_value_rows_german, test_value_rows_english,
               test_auto_error_active):
        fn()
        print(f"PASS {fn.__name__}")
    print("All measurement tests passed")
