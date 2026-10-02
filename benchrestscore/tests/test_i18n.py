# -*- coding: utf-8 -*-
"""Headless unit tests for the i18n module (no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from benchrestscore.i18n import (
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
    LANGUAGE_ENDONYMS,
    TRANSLATIONS,
    current_language,
    set_language,
    tr,
    language_from_locale,
)


def test_default_is_german():
    assert DEFAULT_LANGUAGE == "de"
    assert "de" in SUPPORTED_LANGUAGES
    assert "en" in SUPPORTED_LANGUAGES
    assert current_language() == "de"


def test_tr_returns_active_language():
    save = current_language()
    try:
        set_language("en")
        assert tr("menu.view") == "View"
        assert tr("menu.filters") == "Image filters"
        set_language("de")
        assert tr("menu.view") == "Ansicht"
        assert tr("menu.filters") == "Bildfilter"
    finally:
        set_language(save)


def test_fallback_to_german_when_lang_missing():
    save = current_language()
    try:
        set_language("en")
        TRANSLATIONS["test.only_de"] = {"de": "nur deutsch"}
        try:
            assert tr("test.only_de") == "nur deutsch"
        finally:
            del TRANSLATIONS["test.only_de"]
    finally:
        set_language(save)


def test_unknown_msg_id_raises():
    try:
        tr("menu.does_not_exist")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown msg id")


def test_no_german_variant_raises():
    save = current_language()
    try:
        TRANSLATIONS["test.no_de"] = {"en": "only english"}
        try:
            set_language("en")
            assert tr("test.no_de") == "only english"
            set_language("de")
            try:
                tr("test.no_de")
            except KeyError:
                pass
            else:
                raise AssertionError("expected KeyError without de variant")
        finally:
            del TRANSLATIONS["test.no_de"]
    finally:
        set_language(save)


def test_unknown_language_raises():
    try:
        set_language("fr")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown language")


def test_placeholders_formatted():
    save = current_language()
    try:
        set_language("de")
        assert tr("dialog.measurement.point", n=3) == "Punkt 3"
        assert tr("dialog.about.version", hash="abc123") == "Version: abc123"
        assert tr("dialog.result.avgvar", avg="10", var="2") == "AVG 10µm, VAR 2µm"
        assert tr("dialog.calibration.title_step", step=1, total=4) == "Kalibrierung — Schritt 1/4"
        set_language("en")
        assert tr("dialog.calibration.title_step", step=3, total=4) == "Calibration — Step 3/4"
    finally:
        set_language(save)


def test_measurement_caliber_label():
    save = current_language()
    try:
        set_language("de")
        assert tr("measurement.caliber") == "Kal."
        set_language("en")
        assert tr("measurement.caliber") == "Cal."
    finally:
        set_language(save)


def test_crop_measurement_label_placeholder():
    save = current_language()
    try:
        set_language("de")
        assert tr("menu.crop_measurement", n=3) == "Crop Messung (3)"
        assert tr("menu.crop_measurement", n=0) == "Crop Messung (0)"
        set_language("en")
        assert tr("menu.crop_measurement", n=2) == "Crop measurement (2)"
    finally:
        set_language(save)


def test_settings_menu_keys():
    save = current_language()
    try:
        set_language("de")
        assert tr("menu.calibration") == "Kalibrierung"
        assert tr("menu.measure") == "Messen"
        assert tr("menu.settings") == "Einstellungen"
        assert tr("menu.font") == "Schriftgröße"
        assert tr("menu.camera_settings") == "Kamera"
        assert tr("dialog.camera.title") == "Kamera"
        assert tr("common.close") == "Schließen"
        set_language("en")
        assert tr("menu.calibration") == "Calibration"
        assert tr("menu.measure") == "Measure"
        assert tr("menu.settings") == "Settings"
        assert tr("menu.font") == "Font size"
        assert tr("menu.camera_settings") == "Camera"
        assert tr("dialog.camera.title") == "Camera"
        assert tr("common.close") == "Close"
    finally:
        set_language(save)


def test_removed_menu_keys_absent():
    assert "menu.extras" not in TRANSLATIONS
    assert "menu.camera" not in TRANSLATIONS


def test_calibration_shortcut_is_k():
    save = current_language()
    try:
        set_language("de")
        assert tr("menu.calibration.recalibrate") == "Neu kalibrieren (K)"
        assert tr("dialog.calibration.start") == "Kalibrieren (K)"
        set_language("en")
        assert tr("menu.calibration.recalibrate") == "Recalibrate (K)"
        assert tr("dialog.calibration.start") == "Calibrate (K)"
    finally:
        set_language(save)


def test_sticker_scan_button_label():
    save = current_language()
    try:
        set_language("de")
        assert tr("dialog.measurement.scan_sticker") == "Etikett (E)"
        set_language("en")
        assert tr("dialog.measurement.scan_sticker") == "Sticker (E)"
    finally:
        set_language(save)


def test_manual_sticker_labels():
    save = current_language()
    try:
        set_language("de")
        assert tr("dialog.measurement.scan_manual") == "Manuell"
        assert tr("dialog.measurement.manual_dialog") == \
            "Etikett manuell eingeben"
        assert tr("dialog.measurement.manual_sch_nr") == "Sch-Nr"
        assert tr("dialog.measurement.manual_dg") == "DG"
        assert tr("dialog.measurement.manual_stand") == "Stand"
        assert tr("dialog.measurement.manual_zeit") == "Zeit"
        assert tr("dialog.measurement.manual_save") == "Speichern"
        assert tr("dialog.measurement.manual_close") == "Schließen"
        assert tr("dialog.measurement.manual_error_time") == \
            "Zeit muss im Format HH:MM sein"
        assert tr("dialog.measurement.manual_error_int") == \
            "Sch-Nr, DG und Stand müssen ganze Zahlen sein"
        set_language("en")
        assert tr("dialog.measurement.scan_manual") == "Manual"
        assert tr("dialog.measurement.manual_dialog") == \
            "Enter sticker manually"
        assert tr("dialog.measurement.manual_sch_nr") == "Sticker no."
        assert tr("dialog.measurement.manual_save") == "Save"
        assert tr("dialog.measurement.manual_close") == "Close"
        assert tr("dialog.measurement.manual_error_time") == \
            "Time must be in HH:MM format"
    finally:
        set_language(save)


def test_brsmatch_api_keys():
    save = current_language()
    try:
        set_language("de")
        assert tr("dialog.brsmatch.event_id") == "Event-ID"
        assert tr("dialog.measurement.lookup_running") == "Suche Teilnehmer…"
        assert tr("dialog.measurement.lookup_no_belegung") == "Keine Standbelegung"
        assert tr("dialog.measurement.caliber_value", caliber=".243/6 mm") == \
            "Kaliber: .243/6 mm"
        assert tr("dialog.measurement.wertung") == "Wertung"
        assert tr("dialog.measurement.wertung_running") == "Übertrage Wertung…"
        assert tr("dialog.measurement.wertung_ok") == "Wertung gespeichert"
        assert tr("dialog.wertung_confirm.title") == "Wertung überschreiben"
        assert tr("dialog.wertung_confirm.confirm") == "Überschreiben"
        set_language("en")
        assert tr("dialog.brsmatch.event_id") == "Event ID"
        assert tr("dialog.measurement.lookup_running") == "Looking up participant…"
        assert tr("dialog.measurement.wertung") == "Score"
        assert tr("dialog.wertung_confirm.title") == "Overwrite score"
    finally:
        set_language(save)


def test_language_endonyms():
    assert LANGUAGE_ENDONYMS["de"] == "Deutsch"
    assert LANGUAGE_ENDONYMS["en"] == "English"


def test_language_from_locale():
    import locale as _locale
    orig_getlocale = _locale.getlocale
    orig_getdefault = _locale.getdefaultlocale
    try:
        _locale.getlocale = lambda: ("de_DE", "UTF-8")
        assert language_from_locale() == "de"
        _locale.getlocale = lambda: ("en_US", "UTF-8")
        assert language_from_locale() == "en"
        _locale.getlocale = lambda: (None, None)
        _locale.getdefaultlocale = lambda: ("de_AT", "UTF-8")
        assert language_from_locale() == "de"
        _locale.getdefaultlocale = lambda: ("C", None)
        assert language_from_locale() == "en"
        _locale.getdefaultlocale = lambda: (None, None)
        assert language_from_locale() == "en"
    finally:
        _locale.getlocale = orig_getlocale
        _locale.getdefaultlocale = orig_getdefault


def test_every_entry_has_default_language():
    for msg_id, entry in TRANSLATIONS.items():
        assert DEFAULT_LANGUAGE in entry, f"{msg_id} fehlt {DEFAULT_LANGUAGE}"


def test_every_entry_covers_all_languages():
    for msg_id, entry in TRANSLATIONS.items():
        for lang in SUPPORTED_LANGUAGES:
            assert lang in entry, f"{msg_id} fehlt {lang}"


def test_all_used_msg_ids_exist():
    import re
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src_files = ("ui.py", "measurement.py", "calibration.py", "controller.py", "app.py")
    pattern = re.compile(r'\btr\(\s*["\']([a-zA-Z0-9_.]+)["\']')
    used = set()
    for fn in src_files:
        path = os.path.join(root, "benchrestscore", fn)
        with open(path, encoding="utf-8") as f:
            used.update(pattern.findall(f.read()))
    missing = used - set(TRANSLATIONS)
    assert not missing, f"verwendete Msg-IDs fehlen in TRANSLATIONS: {sorted(missing)}"


if __name__ == "__main__":
    for fn in (test_default_is_german, test_tr_returns_active_language,
               test_fallback_to_german_when_lang_missing, test_unknown_msg_id_raises,
               test_no_german_variant_raises, test_unknown_language_raises,
               test_placeholders_formatted, test_measurement_caliber_label,
                test_crop_measurement_label_placeholder,
                test_settings_menu_keys, test_removed_menu_keys_absent,
                test_calibration_shortcut_is_k,
                test_sticker_scan_button_label, test_manual_sticker_labels,
               test_language_endonyms, test_language_from_locale,
               test_every_entry_has_default_language, test_every_entry_covers_all_languages,
               test_all_used_msg_ids_exist):
        fn()
        print(f"PASS {fn.__name__}")
    print("All i18n tests passed")