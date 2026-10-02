# -*- coding: utf-8 -*-
"""Headless unit tests for the UI module (no window/GL, no imgui calls)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from imgui_bundle import imgui

from benchrestscore.controller import AppState
from benchrestscore.i18n import current_language, set_language
from benchrestscore.ui import (
    calibration_step,
    calibration_step_title,
    workflow_dialog_center,
    workflow_dialog_min_width,
    valid_window_pos,
    about_logo_size,
    config_dialog_field_width,
    brsmatch_metadata_visible,
    manual_sticker_visible,
    truncate_text,
    measurement_dialog_content_width,
    measurement_point_label,
    brsmatch_result_rows,
    ABOUT_LOGO_SIZE_FACTOR,
)


class FakeViewport:
    def __init__(self, work_pos, work_size):
        self.work_pos = work_pos
        self.work_size = work_size


def test_calibration_step_mapping():
    assert calibration_step(AppState.IDLE) == (1, 4)
    assert calibration_step(AppState.CALIBRATING) is None
    assert calibration_step(AppState.RESULT) == (2, 4)
    assert calibration_step(AppState.LEARN_PROMPT) == (3, 4)
    assert calibration_step(AppState.LEARN_RESULT) == (4, 4)


def test_calibration_step_outside_workflow():
    assert calibration_step(AppState.MEASURING) is None
    assert calibration_step(None) is None


def test_calibration_step_title_de():
    save = current_language()
    try:
        set_language("de")
        assert calibration_step_title(AppState.IDLE) == "Kalibrierung — Schritt 1/4"
        assert calibration_step_title(AppState.RESULT) == "Kalibrierung — Schritt 2/4"
        assert calibration_step_title(AppState.LEARN_PROMPT) == "Kalibrierung — Schritt 3/4"
        assert calibration_step_title(AppState.LEARN_RESULT) == "Kalibrierung — Schritt 4/4"
        assert calibration_step_title(AppState.CALIBRATING) is None
        assert calibration_step_title(AppState.MEASURING) is None
    finally:
        set_language(save)


def test_calibration_step_title_en():
    save = current_language()
    try:
        set_language("en")
        assert calibration_step_title(AppState.RESULT) == "Calibration — Step 2/4"
        assert calibration_step_title(AppState.LEARN_PROMPT) == "Calibration — Step 3/4"
        assert calibration_step_title(AppState.CALIBRATING) is None
        assert calibration_step_title(AppState.MEASURING) is None
    finally:
        set_language(save)


def test_workflow_dialog_center():
    vp = FakeViewport(imgui.ImVec2(10, 20), imgui.ImVec2(1920, 1080))
    center = workflow_dialog_center(vp)
    assert center.x == 10 + 960
    assert center.y == 20 + 540
    # Menüleiste ausgeschlossen: work_pos.y > 0 -> Zentrum darunter
    vp2 = FakeViewport(imgui.ImVec2(0, 40), imgui.ImVec2(800, 600))
    center2 = workflow_dialog_center(vp2)
    assert center2.x == 400
    assert center2.y == 40 + 300


def test_workflow_dialog_min_width():
    # Ohne Collapse-Button: Titel + beidseitiges Frame-Padding + Rahmen
    assert workflow_dialog_min_width(150.0, 4.0, 8.0, 13.0, 1.0, False) \
        == 150.0 + 8.0 + 2.0
    assert workflow_dialog_min_width(0.0, 4.0, 8.0, 13.0, 1.0, False) == 8.0 + 2.0
    assert workflow_dialog_min_width(100.0, 0.0, 0.0, 0.0, 0.0, False) == 100.0
    # Mit Collapse-Button links: zusätzlich FontSize + ItemInnerSpacing
    assert workflow_dialog_min_width(150.0, 4.0, 8.0, 13.0, 1.0, True) \
        == 150.0 + 4.0 + (13.0 + 8.0) + 4.0 + 2.0
    # Mit Collapse-Button ist das Fenster breiter als ohne
    assert workflow_dialog_min_width(150.0, 4.0, 8.0, 13.0, 1.0, True) > \
        workflow_dialog_min_width(150.0, 4.0, 8.0, 13.0, 1.0, False)


def test_valid_window_pos():
    w, h = 1920.0, 1080.0
    # mittig und Rand-kompatibel sind gültig
    assert valid_window_pos(100.0, 100.0, w, h)
    assert valid_window_pos(w - 100.0, h - 100.0, w, h)
    # außerhalb des Arbeitsbereichs sind ungültig
    assert not valid_window_pos(-5.0, 100.0, w, h)
    assert not valid_window_pos(100.0, -5.0, w, h)
    assert not valid_window_pos(w + 10.0, 100.0, w, h)
    assert not valid_window_pos(100.0, h + 10.0, w, h)
    # direkt am Rand (innerhalb margin) wird verworfen
    assert not valid_window_pos(1.0, 100.0, w, h)
    assert not valid_window_pos(100.0, h - 1.0, w, h)


def test_about_logo_size():
    # Breite = 25 % der Inhaltsbreite des 40-Zeilen-Layouts
    # ((40 * font_px * 0.52 + 8) * ABOUT_LOGO_SIZE_FACTOR)
    w, h = about_logo_size(20.0, 5.2)
    assert ABOUT_LOGO_SIZE_FACTOR == 0.35
    assert w == (40.0 * 20.0 * 0.52 + 8.0) * ABOUT_LOGO_SIZE_FACTOR
    assert h == w / 5.2


def test_about_logo_size_scales_with_font():
    # Höheres Schrift-Präset -> größeres Logo, gleicher Aspekt (nicht strikt
    # proportional wegen der +8-px-Konstante der Dialog-Inhaltsbreite)
    w_small, h_small = about_logo_size(16.0, 2.0)
    w_large, h_large = about_logo_size(24.0, 2.0)
    assert w_large > w_small
    assert h_large > h_small
    assert h_large / w_large == h_small / w_small == 0.5


def test_brsmatch_metadata_visible_only_when_enabled():
    assert brsmatch_metadata_visible(True) is True
    assert brsmatch_metadata_visible(False) is False


def test_truncate_text():
    assert truncate_text(None) == ""
    assert truncate_text("") == ""
    assert truncate_text("Kurz") == "Kurz"
    assert truncate_text("Müller") == "Müller"
    assert truncate_text("Müller-Langnachname") == "Müller-Langnac…"
    assert truncate_text("X" * 15) == "X" * 15
    assert truncate_text("X" * 16) == "X" * 14 + "…"
    assert truncate_text("Lang", 3) == "La…"


def test_manual_sticker_visible_only_when_enabled():
    assert manual_sticker_visible(True) is True
    assert manual_sticker_visible(False) is False


def test_config_dialog_field_width_min_width():
    # Leerer bzw. kurzer Inhalt -> Mindestbreite (Standard-Aussehen)
    assert config_dialog_field_width(0.0) == 480.0
    assert config_dialog_field_width(100.0) == 480.0


def test_config_dialog_field_width_scales_with_content():
    # Längerer Inhalt -> Inhaltsbreite + Padding
    assert config_dialog_field_width(500.0) == 516.0
    assert config_dialog_field_width(1000.0, padding=20.0) == 1020.0
    assert config_dialog_field_width(1000.0, min_width=1200.0) == 1200.0


def test_config_dialog_field_width_max_cap():
    # Viewport-Obergrenze greift über der Inhaltsbreite
    assert config_dialog_field_width(1000.0, max_w=400.0) == 400.0
    assert config_dialog_field_width(500.0, max_w=500.0) == 500.0


def test_config_dialog_field_width_cap_below_min():
    # Obergrenze kleiner als Mindestbreite (kleiner Screen) -> Obergrenze gewinnt
    assert config_dialog_field_width(0.0, max_w=300.0) == 300.0


def test_config_dialog_field_width_monotonic():
    # Monotonie: mehr Text -> nie schmaleres Feld (ohne Obergrenze)
    prev = 0.0
    for w in (0.0, 100.0, 500.0, 1000.0, 5000.0):
        cur = config_dialog_field_width(w)
        assert cur >= prev
        prev = cur


def test_measurement_dialog_content_width_max():
    # Definierte Breite = breitestes stabiles Inhalts-Zeilen-Maß
    assert measurement_dialog_content_width(100.0, 250.0, 180.0) == 250.0
    assert measurement_dialog_content_width(42.0) == 42.0


def test_measurement_dialog_content_width_empty():
    # Keine Zeilen -> 0.0
    assert measurement_dialog_content_width() == 0.0


def test_measurement_point_label_de():
    save = current_language()
    try:
        set_language("de")
        assert (measurement_point_label(0, 0, 12.0, -3.0)
                == "* Punkt 1  X+012 Y-003")
        assert (measurement_point_label(1, 0, -45.0, 999.0)
                == "  Punkt 2  X-045 Y+999")
    finally:
        set_language(save)


def test_measurement_point_label_en():
    save = current_language()
    try:
        set_language("en")
        assert (measurement_point_label(2, 2, 1.0, 2.0)
                == "* Point 3  X+001 Y+002")
    finally:
        set_language(save)


def test_brsmatch_result_rows_de():
    save = current_language()
    try:
        set_language("de")
        name, caliber = brsmatch_result_rows(
            {"participant": {"last_name": "Muster", "first_name": "Max",
                             "caliber": ".243/6 mm"},
             "existing_scores": 0})
        assert name == "Muster, Max"
        assert caliber == "Kaliber: .243/6 mm"
    finally:
        set_language(save)


def test_brsmatch_result_rows_truncates_names():
    save = current_language()
    try:
        set_language("de")
        name, _ = brsmatch_result_rows(
            {"participant": {"last_name": "x" * 20, "first_name": "y" * 20,
                             "caliber": "9x19"}})
        assert name == "x" * 14 + "…, " + "y" * 14 + "…"
    finally:
        set_language(save)


def test_brsmatch_result_rows_missing_fields():
    save = current_language()
    try:
        set_language("de")
        name, caliber = brsmatch_result_rows({"participant": {}})
        assert name == ", "
        assert caliber == "Kaliber: ?"
    finally:
        set_language(save)


if __name__ == "__main__":
    for fn in (test_calibration_step_mapping, test_calibration_step_outside_workflow,
                test_calibration_step_title_de, test_calibration_step_title_en,
                test_workflow_dialog_center, test_workflow_dialog_min_width,
                test_valid_window_pos, test_about_logo_size,
                test_about_logo_size_scales_with_font,
                test_config_dialog_field_width_min_width,
                test_config_dialog_field_width_scales_with_content,
                test_config_dialog_field_width_max_cap,
                test_config_dialog_field_width_cap_below_min,
                test_config_dialog_field_width_monotonic,
                test_brsmatch_metadata_visible_only_when_enabled,
                test_truncate_text,
                test_manual_sticker_visible_only_when_enabled,
                test_measurement_dialog_content_width_max,
                test_measurement_dialog_content_width_empty,
                test_measurement_point_label_de,
                test_measurement_point_label_en,
                test_brsmatch_result_rows_de,
                test_brsmatch_result_rows_truncates_names,
                test_brsmatch_result_rows_missing_fields):
        fn()
        print(f"PASS {fn.__name__}")
    print("All UI tests passed")
