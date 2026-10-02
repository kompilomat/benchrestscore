# -*- coding: utf-8 -*-
"""Leichtgewichtiges, dict-basiertes Übersetzungssystem (headless testbar).

Neue Sprachen ergänzen sich rein über `SUPPORTED_LANGUAGES` + `TRANSLATIONS`;
Aufrufstellen rufen nur `tr()` auf. Fehlende aktive Sprache fällt auf
`DEFAULT_LANGUAGE` (de) zurück, unbekannte Msg-IDs werfen einen KeyError.
"""

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"

# Endonyme der unterstützten Sprachen (für das Sprach-Menü)
LANGUAGE_ENDONYMS = {
    "de": "Deutsch",
    "en": "English",
}

TRANSLATIONS = {
    # --- Menüleiste ---
    "menu.about": {"de": "Über uns", "en": "About"},
    "menu.quit": {"de": "Beenden (Q)", "en": "Quit (Q)"},
    "menu.calibration": {"de": "Kalibrierung", "en": "Calibration"},
    "menu.measure": {"de": "Messen", "en": "Measure"},
    "menu.settings": {"de": "Einstellungen", "en": "Settings"},
    "menu.calibration.recalibrate": {
        "de": "Neu kalibrieren (K)", "en": "Recalibrate (K)",
    },
    "menu.calibration.recover": {
        "de": "Kalibrierung wiederherstellen",
        "en": "Restore calibration",
    },
    "recovery.error.no_session": {
        "de": "Keine wiederherstellbaren Ergebnisse",
        "en": "No recoverable results",
    },
    "recovery.error.resolution": {
        "de": "Kamera-Auflösung geändert — neu kalibrieren",
        "en": "Camera resolution changed — recalibrate",
    },
    "recovery.error.corrupt": {
        "de": "Gespeicherte Ergebnisse beschädigt",
        "en": "Stored results corrupted",
    },
    "menu.automation": {"de": "Automatik (M)", "en": "Automation (M)"},
    "menu.reference_mode": {"de": "Referenz-Modus", "en": "Reference mode"},
    "menu.card_qc": {
        "de": "Karten-Qualitätscheck", "en": "Card quality check",
    },
    "menu.vision_config": {"de": "Vision-Konfiguration", "en": "Vision configuration"},
    "menu.filters": {"de": "Bildfilter", "en": "Image filters"},
    "menu.background_tint": {
        "de": "Hintergrund einfärben", "en": "Tint background",
    },
    "menu.view": {"de": "Ansicht", "en": "View"},
    "menu.crop_measurement": {
        "de": "Crop Messung ({n})", "en": "Crop measurement ({n})",
    },
    "menu.font": {"de": "Schriftgröße", "en": "Font size"},
    "menu.font.normal": {"de": "Normal", "en": "Normal"},
    "menu.font.large": {"de": "Groß", "en": "Large"},
    "menu.font.xlarge": {"de": "Sehr groß", "en": "XLarge"},
    "menu.language": {"de": "Sprache", "en": "Language"},
    "menu.camera_settings": {"de": "Kamera", "en": "Camera"},
    # --- Dialoge ---
    "dialog.about.title": {"de": "Über Benchrestscore", "en": "About Benchrestscore"},
    "dialog.about.version": {"de": "Version: {hash}", "en": "Version: {hash}"},
    "dialog.camera.title": {"de": "Kamera", "en": "Camera"},
    "dialog.filters.title": {"de": "Bildfilter", "en": "Image filters"},
    "dialog.filters.enable": {"de": "Bildfilter aktivieren (F)", "en": "Enable image filters (F)"},
    "dialog.calibration.title": {"de": "Kalibrierung", "en": "Calibration"},
    "dialog.calibration.title_step": {
        "de": "Kalibrierung — Schritt {step}/{total}",
        "en": "Calibration — Step {step}/{total}",
    },
    "dialog.calibration.align": {
        "de": "Kalibrierkarte ausrichten und mit K starten",
        "en": "Align calibration card and start with K",
    },
    "dialog.calibration.start": {"de": "Kalibrieren (K)", "en": "Calibrate (K)"},
    "dialog.calibration.recover": {"de": "Wiederherstellen", "en": "Restore"},
    "dialog.calibration.running": {
        "de": "Berechne Linsengeometrie...",
        "en": "Computing lens geometry...",
    },
    "dialog.measurement.title": {"de": "Messung", "en": "Measurement"},
    "dialog.measurement.automation": {"de": "Automatik (M)", "en": "Automation (M)"},
    "dialog.vision_config.title": {
        "de": "Vision-Konfiguration", "en": "Vision configuration",
    },
    "dialog.vision_config.base_url": {
        "de": "Base-URL", "en": "Base URL",
    },
    "dialog.vision_config.model": {
        "de": "Modell", "en": "Model",
    },
    "dialog.vision_config.api_key": {
        "de": "API-Key", "en": "API key",
    },
    "dialog.vision_config.save": {
        "de": "Speichern", "en": "Save",
    },
    "dialog.vision_config.test": {
        "de": "Verbindung testen", "en": "Test connection",
    },
    "dialog.vision_config.ok": {
        "de": "Verbindung ok", "en": "Connection OK",
    },
    "dialog.vision_config.not_configured": {
        "de": "Nicht konfiguriert (Base-URL + Modell fehlen)",
        "en": "Not configured (base URL + model required)",
    },
    "dialog.vision_config.vision_error": {
        "de": "Verbindung fehlgeschlagen — ungültige Antwort",
        "en": "Connection failed — invalid response",
    },
    "dialog.vision_config.no_frame": {
        "de": "Kein Kamerabild verfügbar",
        "en": "No camera frame available",
    },
    "dialog.vision_config.testing": {
        "de": "Test läuft…",
        "en": "Testing…",
    },
    "menu.brsmatch": {"de": "BRSMatch", "en": "BRSMatch"},
    "menu.brsmatch.enabled": {"de": "Aktivieren", "en": "Enable"},
    "dialog.brsmatch.title": {
        "de": "BRSMatch-Verbindung", "en": "BRSMatch connection",
    },
    "dialog.brsmatch.base_url": {
        "de": "Base-URL", "en": "Base URL",
    },
    "dialog.brsmatch.api_key": {
        "de": "API-Key", "en": "API key",
    },
    "dialog.brsmatch.event_id": {
        "de": "Event-ID", "en": "Event ID",
    },
    "dialog.brsmatch.enabled": {
        "de": "Aktivieren", "en": "Enable",
    },
    "dialog.brsmatch.close": {
        "de": "Schließen", "en": "Close",
    },
    "dialog.measurement.scan_sticker": {
        "de": "Etikett (E)", "en": "Sticker (E)",
    },
    "dialog.measurement.scan_manual": {
        "de": "Manuell", "en": "Manual",
    },
    "dialog.measurement.manual_dialog": {
        "de": "Etikett manuell eingeben", "en": "Enter sticker manually",
    },
    "dialog.measurement.manual_sch_nr": {
        "de": "Sch-Nr", "en": "Sticker no.",
    },
    "dialog.measurement.manual_dg": {
        "de": "DG", "en": "DG",
    },
    "dialog.measurement.manual_stand": {
        "de": "Stand", "en": "Stand",
    },
    "dialog.measurement.manual_zeit": {
        "de": "Zeit", "en": "Time",
    },
    "dialog.measurement.manual_save": {
        "de": "Speichern", "en": "Save",
    },
    "dialog.measurement.manual_close": {
        "de": "Schließen", "en": "Close",
    },
    "dialog.measurement.manual_error_time": {
        "de": "Zeit muss im Format HH:MM sein",
        "en": "Time must be in HH:MM format",
    },
    "dialog.measurement.manual_error_int": {
        "de": "Sch-Nr, DG und Stand müssen ganze Zahlen sein",
        "en": "Sticker no., DG and stand must be whole numbers",
    },
    "dialog.measurement.scan_running": {
        "de": "Scanne Etikett…", "en": "Scanning sticker…",
    },
    "dialog.measurement.scan_ok": {
        "de": "Scan erfolgreich", "en": "Scan successful",
    },
    "dialog.measurement.scan_error": {
        "de": "Scan fehlgeschlagen", "en": "Scan failed",
    },
    "dialog.measurement.lookup_running": {
        "de": "Suche Teilnehmer…", "en": "Looking up participant…",
    },
    "dialog.measurement.lookup_not_configured": {
        "de": "BRSMatch nicht konfiguriert (Base-URL, API-Key, Event-ID)",
        "en": "BRSMatch not configured (base URL, API key, event ID)",
    },
    "dialog.measurement.lookup_no_belegung": {
        "de": "Keine Standbelegung", "en": "No stand assignment",
    },
    "dialog.measurement.lookup_mismatch": {
        "de": "Sch-Nr oder Durchgang passt nicht zur Belegung",
        "en": "Sticker no. or DG does not match the assignment",
    },
    "dialog.measurement.lookup_auth": {
        "de": "API-Token ungültig", "en": "Invalid API token",
    },
    "dialog.measurement.lookup_server": {
        "de": "Serverfehler", "en": "Server error",
    },
    "dialog.measurement.lookup_network": {
        "de": "Keine Verbindung zum Server", "en": "No connection to the server",
    },
    "dialog.measurement.caliber_value": {
        "de": "Kaliber: {caliber}", "en": "Caliber: {caliber}",
    },
    "dialog.measurement.wertung": {
        "de": "Wertung", "en": "Score",
    },
    "dialog.measurement.wertung_running": {
        "de": "Übertrage Wertung…", "en": "Uploading score…",
    },
    "dialog.measurement.wertung_ok": {
        "de": "Wertung gespeichert", "en": "Score saved",
    },
    "dialog.measurement.wertung_not_configured": {
        "de": "BRSMatch nicht konfiguriert",
        "en": "BRSMatch not configured",
    },
    "dialog.measurement.wertung_validation": {
        "de": "Wertung abgelehnt (Messwert unplausibel)",
        "en": "Score rejected (implausible measurement)",
    },
    "dialog.measurement.wertung_no_belegung": {
        "de": "Keine Standbelegung", "en": "No stand assignment",
    },
    "dialog.measurement.wertung_mismatch": {
        "de": "Sch-Nr oder Durchgang passt nicht zur Belegung",
        "en": "Sticker no. or DG does not match the assignment",
    },
    "dialog.measurement.wertung_auth": {
        "de": "API-Token ungültig", "en": "Invalid API token",
    },
    "dialog.measurement.wertung_server": {
        "de": "Serverfehler", "en": "Server error",
    },
    "dialog.measurement.wertung_network": {
        "de": "Keine Verbindung zum Server", "en": "No connection to the server",
    },
    "dialog.wertung_confirm.title": {
        "de": "Wertung überschreiben", "en": "Overwrite score",
    },
    "dialog.wertung_confirm.info": {
        "de": "Für diese Scheibe liegt bereits ein Wertungsergebnis vor. Bestätigen, dass es überschrieben wird:",
        "en": "A score already exists for this target. Confirm that it will be overwritten:",
    },
    "dialog.wertung_confirm.name": {
        "de": "Name", "en": "Name",
    },
    "dialog.wertung_confirm.stand": {
        "de": "Stand", "en": "Stand",
    },
    "dialog.wertung_confirm.zeit": {
        "de": "Uhrzeit", "en": "Time",
    },
    "dialog.wertung_confirm.dg": {
        "de": "Durchgang", "en": "DG",
    },
    "dialog.wertung_confirm.confirm": {
        "de": "Überschreiben", "en": "Overwrite",
    },
    "dialog.wertung_confirm.cancel": {
        "de": "Abbrechen", "en": "Cancel",
    },
    "dialog.measurement.save_reference": {
        "de": "Referenz speichern", "en": "Save reference",
    },
    "dialog.measurement.reference_info": {
        "de": "Gespeichert: {n} Punkte ({sample})",
        "en": "Saved: {n} points ({sample})",
    },
    "dialog.measurement.reference_no_points": {
        "de": "Erst Messpunkte auf den Löchern setzen",
        "en": "Set measurement points on the holes first",
    },
    "dialog.measurement.reference_failed": {
        "de": "Referenz konnte nicht gespeichert werden",
        "en": "Could not save reference",
    },
    "dialog.measurement.points": {"de": "Messpunkte", "en": "Measurement points"},
    "dialog.measurement.point": {"de": "Punkt {n}", "en": "Point {n}"},
    "dialog.measurement.coords": {
        "de": "X{x} Y{y}",
        "en": "X{x} Y{y}",
    },
    "dialog.measurement.auto_failed": {
        "de": "Auto-Erkennung fehlgeschlagen",
        "en": "Auto-detection failed",
    },
    "dialog.measurement.clear_points": {
        "de": "Alle Punkte löschen (R)",
        "en": "Clear all points (R)",
    },
    "background.learn_prompt": {
        "de": "Kalibrierkarte entfernen, damit der Untergrund gelernt werden kann",
        "en": "Remove the calibration card so the background can be learned",
    },
    "background.learn": {"de": "Hintergrund lernen (Enter)", "en": "Learn background (Enter)"},
    "background.finish": {"de": "Abschließen (Enter)", "en": "Finish (Enter)"},
    "background.abort": {"de": "Abbruch", "en": "Abort"},
    "background.result_info": {
        "de": "{n} Keypoints gelernt",
        "en": "{n} keypoints learned",
    },
    "background.too_sparse": {
        "de": "Untergrund zu strukturarm — neu versuchen",
        "en": "Background too sparse — try again",
    },
    "background.status.ok": {
        "de": "Kalibrierung ok",
        "en": "Calibration ok",
    },
    "background.status.shifted": {
        "de": "Kalibrierung verschoben ({mm} mm)",
        "en": "Calibration shifted ({mm} mm)",
    },
    "background.status.na": {
        "de": "Kalibrierung n/a",
        "en": "Calibration n/a",
    },
    "background.status.checking": {
        "de": "Kalibrierung prüft…",
        "en": "Calibration checking…",
    },
    "background.status.na_tip": {
        "de": "Grund: {reason} (Frame-Keypoints {kps}, Matches {matches}, Inlier {ratio})",
        "en": "Reason: {reason} (frame keypoints {kps}, matches {matches}, inlier {ratio})",
    },
    "dialog.result.title": {"de": "Kalibrier-Ergebnis", "en": "Calibration result"},
    "dialog.result.avgvar": {
        "de": "AVG {avg}µm, VAR {var}µm",
        "en": "AVG {avg}µm, VAR {var}µm",
    },
    "dialog.result.correction": {
        "de": "Korrektur A:{a} / B:{b}",
        "en": "Correction A:{a} / B:{b}",
    },
    "dialog.result.poor_accuracy": {
        "de": "Geringe Genauigkeit — erneut kalibrieren",
        "en": "Low accuracy — calibrate again",
    },
    "dialog.result.accept": {"de": "Übernehmen (Enter)", "en": "Accept (Enter)"},
    "dialog.result.cancel": {"de": "Abbruch (Esc)", "en": "Cancel (Esc)"},
    # --- Filterparameter ---
    "filter.invert": {"de": "Negativ", "en": "Negative"},
    "filter.gray": {"de": "Graustufen", "en": "Grayscale"},
    "filter.saturation": {"de": "Sättigung", "en": "Saturation"},
    "filter.contrast": {"de": "Kontrast", "en": "Contrast"},
    "filter.gamma": {"de": "Gamma", "en": "Gamma"},
    "filter.brightness": {"de": "Helligkeit", "en": "Brightness"},
    # --- Kamera-Einstellungen ---
    "camera.device": {"de": "Gerät", "en": "Device"},
    "camera.resolution": {"de": "Auflösung", "en": "Resolution"},
    "camera.rotate": {"de": "Rotation", "en": "Rotation"},
    "camera.rotate.0": {"de": "0°", "en": "0°"},
    "camera.rotate.180": {"de": "180°", "en": "180°"},
    # --- Messwerttext ---
    "measurement.caliber": {"de": "Kal.", "en": "Cal."},
    "measurement.center_label": {"de": "Mitte", "en": "Center"},
    "measurement.outer_label": {"de": "Außen", "en": "Outside"},
    # --- Kalibrier-Fehler ---
    "calibration.card_not_found": {
        "de": "Kalibrierkarte nicht erkannt ({count} Kreise)",
        "en": "Calibration card not found ({count} circles)",
    },
    "card_qc.error.not_measuring": {
        "de": "Im Messbetrieb starten", "en": "Start from measurement mode",
    },
    "card_qc.error.no_calibration": {
        "de": "Zuerst kalibrieren", "en": "Calibrate first",
    },
    "card_qc.error.no_reference": {
        "de": "Referenzkarte fehlt — neu kalibrieren",
        "en": "Reference card missing — recalibrate",
    },
    "card_qc.error.no_frame": {
        "de": "Kein Kamerabild verfügbar", "en": "No camera frame available",
    },
    "card_qc.error.no_grid": {
        "de": "Raster nicht erkannt ({count} Kreise)",
        "en": "Grid not detected ({count} circles)",
    },
    "dialog.card_qc.title": {
        "de": "Karten-Qualitätscheck", "en": "Card quality check",
    },
    "dialog.card_qc.running": {
        "de": "Messe Kalibrierkarte…", "en": "Measuring calibration card…",
    },
    "dialog.card_qc.pass": {
        "de": "In Spec", "en": "In spec",
    },
    "dialog.card_qc.fail": {
        "de": "Nicht in Spec ({over} Punkte)",
        "en": "Not in spec ({over} points)",
    },
    "dialog.card_qc.stats": {
        "de": "Max {max} µm, Ø {mean} µm", "en": "Max {max} µm, mean {mean} µm",
    },
    "dialog.card_qc.tolerance": {
        "de": "Toleranz ±{tol} mm pro Punkt", "en": "Tolerance ±{tol} mm per point",
    },
    "dialog.card_qc.dismiss": {"de": "Schließen", "en": "Close"},
    "dialog.card_qc.abort": {"de": "Abbrechen", "en": "Abort"},
    "calibration.channel_not_found": {
        "de": "Kanal {channel} nicht erkannt ({count} Kreise)",
        "en": "Channel {channel} not found ({count} circles)",
    },
    # --- Gemeinsam ---
    "common.ok": {"de": "OK", "en": "OK"},
    "common.reset": {"de": "Zurücksetzen", "en": "Reset"},
    "common.delete": {"de": "Löschen", "en": "Delete"},
    "common.close": {"de": "Schließen", "en": "Close"},
}

# Best-effort-Locale-Kandidaten für die Zahlenformatierung pro Sprache
_LOCALE_CANDIDATES = {
    "de": ("de_DE.UTF-8", "de_DE.utf8", "de_DE"),
    "en": ("en_US.UTF-8", "en_US.utf8", "en_US", "C.UTF-8", "C"),
}

_current_language = DEFAULT_LANGUAGE


def current_language():
    """Aktive Sprache als Code aus `SUPPORTED_LANGUAGES`."""
    return _current_language


def set_language(lang):
    """Aktive Sprache global setzen; unbekannte Codes werfen ValueError."""
    global _current_language
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"unknown language {lang!r}; expected one of {SUPPORTED_LANGUAGES}")
    _current_language = lang


def set_locale():
    """Numerik-Locale best effort an die aktive Sprache angleichen.

    Setzt nur LC_NUMERIC (Zahlenformatierung), lässt Kollation/Messages
    unangetastet. Ist keine passende Locale installiert, bleibt die bisherige
    Locale aktiv — kein App-Fehler.
    """
    import locale
    for name in _LOCALE_CANDIDATES.get(_current_language, ()):
        try:
            locale.setlocale(locale.LC_NUMERIC, name)
            return
        except locale.Error:
            continue


def language_from_locale():
    """System-Locale auf eine unterstützte Sprache abbilden.

    Deutsche Locales (Beginn mit `de`) -> `de`, alle anderen/keine -> `en`.
    """
    import locale
    code = None
    try:
        code = locale.getlocale()[0]
    except Exception:
        code = None
    if not code:
        try:
            code = locale.getdefaultlocale()[0]
        except Exception:
            code = None
    if code and str(code).lower().startswith("de"):
        return "de"
    return "en"


def tr(msg_id, **kwargs):
    """Übersetzten String für die aktive Sprache liefern.

    Fehlt die aktive Sprache im Eintrag, fällt auf `DEFAULT_LANGUAGE` (de)
    zurück. Unbekannte Msg-IDs und Strings ohne deutsche Variante werfen einen
    KeyError, damit fehlende Übersetzungen sofort auffallen. Platzhalter
    `{name}` werden über `**kwargs` mit `.format()` gefüllt.
    """
    entry = TRANSLATIONS.get(msg_id)
    if entry is None:
        raise KeyError(f"unknown message id: {msg_id!r}")
    text = entry.get(_current_language)
    if text is None:
        text = entry.get(DEFAULT_LANGUAGE)
    if text is None:
        raise KeyError(f"no translation for {msg_id!r} in {DEFAULT_LANGUAGE!r}")
    if kwargs:
        text = text.format(**kwargs)
    return text