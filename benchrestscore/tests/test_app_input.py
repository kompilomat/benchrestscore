# -*- coding: utf-8 -*-
"""Headless tests for the app keyboard shortcut text-input guard (_on_key)."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import glfw

from benchrestscore.app import BRSCanvas


class FakeIO:
    def __init__(self, want_text_input):
        self.want_text_input = want_text_input


class FakeRenderer:
    def __init__(self, want_text_input):
        self.io = FakeIO(want_text_input)
        self.keyboard_callback = mock.Mock()
        self.char_callback = mock.Mock()


class FakeController:
    def __init__(self, manual_dialog_open=False):
        self.calls = []
        self.manual_dialog_open = manual_dialog_open

    def quit(self):
        self.calls.append("quit")

    def close_manual_dialog(self):
        self.calls.append("close_manual_dialog")

    def request_calibration(self):
        self.calls.append("request_calibration")

    def cancel_calibration(self):
        self.calls.append("cancel_calibration")

    def cycle_active_point(self):
        self.calls.append("cycle_active_point")

    def reset_points(self):
        self.calls.append("reset_points")

    def increment_caliber(self, direction):
        self.calls.append(("increment_caliber", direction))

    def adjust_point(self, direction):
        self.calls.append(("adjust_point", direction))

    def toggle_automation(self):
        self.calls.append("toggle_automation")

    def toggle_filters_active(self):
        self.calls.append("toggle_filters_active")

    def scan_sticker(self):
        self.calls.append("scan_sticker")


def make_canvas(want_text_input, manual_dialog_open=False):
    canvas = object.__new__(BRSCanvas)
    canvas.imgui_renderer = FakeRenderer(want_text_input)
    canvas.controller = FakeController(manual_dialog_open)
    # Instanz-Attribute schatten die echten GL-berührenden Methoden ab.
    canvas.start_fit_measurements = mock.Mock()
    canvas._start_center_anim = mock.Mock()
    return canvas


def press(canvas, key):
    canvas._on_key(None, key, 0, glfw.PRESS, 0)


SHORTCUT_KEYS = (
    glfw.KEY_Q, glfw.KEY_K, glfw.KEY_C, glfw.KEY_ESCAPE, glfw.KEY_SPACE,
    glfw.KEY_R, glfw.KEY_1, glfw.KEY_2, glfw.KEY_UP, glfw.KEY_M, glfw.KEY_F,
    glfw.KEY_E,
)


def test_shortcuts_suppressed_while_text_input_active():
    for key in SHORTCUT_KEYS:
        canvas = make_canvas(want_text_input=True)
        press(canvas, key)
        assert canvas.controller.calls == [], f"shortcut fired for key {key}"
        assert canvas.start_fit_measurements.call_count == 0
        assert canvas._start_center_anim.call_count == 0


def test_imgui_still_receives_key_during_text_input():
    canvas = make_canvas(want_text_input=True)
    press(canvas, glfw.KEY_K)
    canvas.imgui_renderer.keyboard_callback.assert_called_once_with(
        None, glfw.KEY_K, 0, glfw.PRESS, 0)


def test_shortcut_still_fires_without_text_input():
    canvas = make_canvas(want_text_input=False)
    press(canvas, glfw.KEY_K)
    assert canvas.controller.calls == ["request_calibration"]


def test_q_still_quits_without_text_input():
    canvas = make_canvas(want_text_input=False)
    press(canvas, glfw.KEY_Q)
    assert canvas.controller.calls == ["quit"]


def test_e_triggers_scan_sticker():
    canvas = make_canvas(want_text_input=False)
    press(canvas, glfw.KEY_E)
    assert canvas.controller.calls == ["scan_sticker"]


def test_e_suppressed_while_text_input_active():
    canvas = make_canvas(want_text_input=True)
    press(canvas, glfw.KEY_E)
    assert canvas.controller.calls == []


def test_escape_closes_manual_dialog_while_text_input_active():
    canvas = make_canvas(want_text_input=True, manual_dialog_open=True)
    press(canvas, glfw.KEY_ESCAPE)
    assert canvas.controller.calls == ["close_manual_dialog"]


def test_escape_closes_manual_dialog_without_text_input():
    canvas = make_canvas(want_text_input=False, manual_dialog_open=True)
    press(canvas, glfw.KEY_ESCAPE)
    assert canvas.controller.calls == ["close_manual_dialog"]
    assert "cancel_calibration" not in canvas.controller.calls


def test_escape_without_manual_dialog_cancels_calibration():
    canvas = make_canvas(want_text_input=False, manual_dialog_open=False)
    press(canvas, glfw.KEY_ESCAPE)
    assert canvas.controller.calls == ["cancel_calibration"]


def test_escape_release_and_repeat_do_not_close_manual_dialog():
    for action in (glfw.RELEASE, glfw.REPEAT):
        canvas = make_canvas(want_text_input=True, manual_dialog_open=True)
        canvas._on_key(None, glfw.KEY_ESCAPE, 0, action, 0)
        assert canvas.controller.calls == [], f"action {action}"
    canvas = make_canvas(want_text_input=False, manual_dialog_open=True)
    canvas._on_key(None, glfw.KEY_ESCAPE, 0, glfw.REPEAT, 0)
    assert canvas.controller.calls == []


def test_char_forwards_to_imgui_renderer():
    canvas = make_canvas(want_text_input=False)
    canvas._on_char(None, ord("A"))
    canvas.imgui_renderer.char_callback.assert_called_once_with(None, ord("A"))


if __name__ == "__main__":
    for fn in (test_shortcuts_suppressed_while_text_input_active,
               test_imgui_still_receives_key_during_text_input,
               test_shortcut_still_fires_without_text_input,
               test_q_still_quits_without_text_input,
               test_e_triggers_scan_sticker,
        test_e_suppressed_while_text_input_active,
        test_escape_closes_manual_dialog_while_text_input_active,
        test_escape_closes_manual_dialog_without_text_input,
        test_escape_without_manual_dialog_cancels_calibration,
        test_escape_release_and_repeat_do_not_close_manual_dialog,
        test_char_forwards_to_imgui_renderer):
        fn()
        print(f"PASS {fn.__name__}")
    print("All app input tests passed")