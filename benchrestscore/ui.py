# -*- coding: utf-8 -*-

import subprocess
import time

from imgui_bundle import imgui

try:
    from .controller import AppState
except ImportError:
    from controller import AppState

try:
    from .calibration import calibration_quality
except ImportError:
    from calibration import calibration_quality

# Dual-Import: als Script und als Paket ladbar (vgl. controller.py).
try:
    from .i18n import tr, SUPPORTED_LANGUAGES, LANGUAGE_ENDONYMS
except ImportError:
    from i18n import tr, SUPPORTED_LANGUAGES, LANGUAGE_ENDONYMS

try:
    from .camera import list_camera_devices
except ImportError:
    from camera import list_camera_devices

try:
    from .calibration_monitor import MonitorStatus
except ImportError:
    from calibration_monitor import MonitorStatus

try:
    from .calibration_recovery import has_valid_session
except ImportError:
    from calibration_recovery import has_valid_session

try:
    from .calibration_card_qc import QC_TOLERANCE_MM
except ImportError:  # pragma: no cover
    from calibration_card_qc import QC_TOLERANCE_MM


def calibration_step(state):
    """Kalibrier-Schritt (1..4) für einen App-State; None außerhalb des Workflows.

    Die Schritt-Zuordnung ist fest an die **sichtbaren** Dialog-Stationen des
    Workflows gekoppelt: IDLE=1 (Karte ausrichten/Start), RESULT=2 (Ergebnis),
    LEARN_PROMPT=3 (Untergrund lernen — Aufforderung), LEARN_RESULT=4
    (Lern-Ergebnis). CALIBRATING ist kein Schritt: die Kalibrierung läuft
    blockierend im GUI-Thread ohne eigenen sichtbaren Dialog. Der Messbetrieb
    ist kein Kalibrier-Schritt.
    """
    steps = {
        AppState.IDLE: 1,
        AppState.RESULT: 2,
        AppState.LEARN_PROMPT: 3,
        AppState.LEARN_RESULT: 4,
    }
    total = 4
    step = steps.get(state)
    return (step, total) if step is not None else None


def brsmatch_metadata_visible(enabled):
    """Sichtbarkeit des Metadaten-Abschnitts im Messung-Dialog.

    Der Abschnitt (Etikett-Scan + Ergebnis-Anzeige) erscheint nur, wenn der
    BRSMatch-Modus aktiviert ist. Reine Funktion (headless testbar).
    """
    return bool(enabled)


def manual_sticker_visible(enabled):
    """Sichtbarkeit der manuellen Etikett-Eingabe im Messung-Dialog.

    Die manuelle Eingabe (Fallback zum Scan) erscheint nur bei aktiviertem
    BRSMatch-Modus — gleiches Gate wie der Etikett-Scan. Reine Funktion
    (headless testbar).
    """
    return bool(enabled)


def truncate_text(text, max_len=15):
    """Text auf höchstens `max_len` Zeichen kürzen (Ende mit „…").

    Reine Funktion (headless testbar); `None` → leerer String.
    """
    if text is None:
        return ""
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max(0, max_len - 1)] + "…"


def calibration_step_title(state):
    """Übersetzter Dialog-Titel inkl. Schritt-Anzeige; None außerhalb des
    Kalibrier-Workflows (z.B. Messbetrieb)."""
    step = calibration_step(state)
    if step is None:
        return None
    return tr("dialog.calibration.title_step", step=step[0], total=step[1])


def workflow_dialog_center(vp):
    """Mittelpunkt der Arbeitsfläche (unterhalb der Menüleiste) eines Viewports.

    Die Kalibrier-Workflow-Dialoge erscheinen dort beim ersten Anzeigen, damit
    geöffnete Menü-Dropdowns der Menüleiste sie nicht überdecken. Reine
    Berechnung (headless testbar): `vp` ist ein Objekt mit `work_pos`/`work_size`
    (z.B. `imgui.get_main_viewport()`).
    """
    return imgui.ImVec2(vp.work_pos.x + vp.work_size.x * 0.5,
                        vp.work_pos.y + vp.work_size.y * 0.5)


def workflow_dialog_min_width(title_width, frame_padding_x, item_inner_spacing_x,
                              font_size, border_size, has_collapse_button):
    """Mindestbreite eines Workflow-Dialogs, damit der Titel nicht abgeschnitten
    wird (reine Berechnung, headless testbar).

    ImGui's `AlwaysAutoResize` rechnet die Titel-Textbreite nicht in die
    Fensterbreite ein; der Titel wird rechts geklippt, wenn er breiter als der
    Inhalt ist. Die Mindestbreite deckt die volle Titel-Zeile ab: Titeltext plus
    beidseitiges Frame-Padding, den Collapse-Button der Titelleiste (Breite =
    FontSize + ItemInnerSpacing) und den Rahmen.
    """
    pad_l = frame_padding_x
    if has_collapse_button:
        pad_l += font_size + item_inner_spacing_x
    pad_r = frame_padding_x
    return title_width + pad_l + pad_r + 2.0 * border_size


# Über-uns-Dialog: Logo-Breite als Faktor der Dialog-Inhaltsbreite
# (Layout-Entscheidung aus der Verifikation, design.md D2).
ABOUT_LOGO_SIZE_FACTOR = 0.35


def about_logo_size(font_px, aspect):
    """Größe (w, h) des Logos im „Über uns“-Dialog (reine Berechnung,
    headless testbar).

    Die Breite ist `ABOUT_LOGO_SIZE_FACTOR` × die Inhaltsbreite des
    40-Zeilen-Dialog-Layouts (`40 * font_px * 0.52 + 8`: 40 Zeichen ×
    0.52 × Schriftgröße plus 8 px). Die Höhe folgt dem Seitenverhältnis
    der Logodatei."""
    w = (40.0 * font_px * 0.52 + 8.0) * ABOUT_LOGO_SIZE_FACTOR
    return (w, w / aspect)


def position_workflow_dialog(state):
    """Startposition und Mindestbreite für einen Kalibrier-Workflow-Dialog setzen.

    - Position: beim Erscheinen (`Cond_.appearing`) zentriert in der
      Arbeitsfläche unterhalb der Menüleiste; danach frei verschiebbar
      (Persistenz über `imgui.ini` unverändert).
    - Breite: mindestens so breit wie die komplette Titel-Zeile, damit der
      Titel nie abgeschnitten wird. Die Obergrenze ist FLT_MAX, die Y-Achse
      bleibt bei −1/−1 (aktuelle Größe erhalten) — der Auto-Resize an den
      Inhalt bleibt also vollständig erhalten.
    """
    title = calibration_step_title(state)
    if title is not None:
        style = imgui.get_style()
        has_collapse = style.window_menu_button_position != imgui.Dir_.none
        min_w = workflow_dialog_min_width(
            imgui.calc_text_size(title).x,
            style.frame_padding.x,
            style.item_inner_spacing.x,
            imgui.get_font_size(),
            style.window_border_size,
            has_collapse)
        imgui.set_next_window_size_constraints(
            imgui.ImVec2(min_w, -1.0),
            imgui.ImVec2(imgui.FLT_MAX, -1.0),
            None,
        )
    imgui.set_next_window_pos(workflow_dialog_center(imgui.get_main_viewport()),
                              imgui.Cond_.appearing,
                              imgui.ImVec2(0.5, 0.5))


def valid_window_pos(x, y, work_w, work_h, margin=16.0):
    """True, wenn eine Fensterposition im sichtbaren Arbeitsbereich liegt.

    Positionen außerhalb (z.B. nach Bildschirmwechsel oder Auflösungsänderung)
    werden verworfen, damit ein Overlay-Fenster nie unauffindbar wird. `work_w`/
    `work_h` sind die Abmessungen des sichtbaren Arbeitsbereichs (work_size des
    Main-Viewports); der Rand hält die Titelleiste greifbar. Reine Berechnung
    (headless testbar).
    """
    return (margin <= x < work_w - margin
            and margin <= y < work_h - margin)


def config_dialog_field_width(max_text_w, min_width=480.0, padding=16.0,
                              max_w=None):
    """Breite eines Konfigurations-Dialog-Eingabefelds (reine Berechnung,
    headless testbar).

    `max_text_w` ist die größte Textbreite (px) der Feldinhalte des Dialogs,
    gemessen mit der aktuell aktiven Schrift (z.B. via `imgui.calc_text_size`)
    — wächst also mit Schriftgrößen-Präset und eingegebenem Text. Das Ergebnis
    ist mindestens `min_width` (Standard-Aussehen bei leeren/kurzen Werten)
    und wächst mit dem Inhalt: `max(min_width, max_text_w + padding)`;
    `padding` deckt Frame-Padding + Cursor-Spielraum des InputText-Rahmens ab.
    Ist `max_w` (Viewport-Obergrenze) gegeben, greift sie als Obergrenze — bei
    sehr kleinen Screens auch unterhalb der Mindestbreite.
    """
    w = max(float(min_width), float(max_text_w) + float(padding))
    if max_w is not None:
        w = min(w, float(max_w))
    return w


def measurement_dialog_content_width(*line_widths):
    """Definierte Breite des Messung-Dialogs (reine Berechnung, headless
    testbar).

    Das Maximum der Breiten (px) der stabilen Inhaltszeilen (Kaliber-Zeile,
    Messwert-Zeilen, Automatik-Checkbox, Messpunkt-Liste, Reset-Button,
    BRSMatch-Abschnitt-Zeilen). Flüchtige Status-/Fehlerzeilen gehören nicht
    dazu: Sie vergrößern den Dialog nur während ihrer Anzeige (Auto-Resize),
    bestimmen aber nicht die definierte Breite. Bei leeren Argumenten 0.0.
    """
    if not line_widths:
        return 0.0
    return max(float(w) for w in line_widths)


def measurement_point_label(i, active_idx, mx, my):
    """Zeilen-Text eines Messpunkts im Messung-Dialog (reine Berechnung,
    headless testbar).

    Marker („*" für den aktiven Punkt, sonst Leerzeichen), Punkte-Label und
    Koordinaten im bestehenden Format; ein Ursprung für Breiten-Berechnung
    und Rendering des Messung-Dialogs.
    """
    marker = "*" if i == active_idx else " "
    label = f"{marker} " + tr("dialog.measurement.point", n=i + 1)
    label += "  " + tr("dialog.measurement.coords",
                       x=f"{mx:+04.0f}", y=f"{my:+04.0f}")
    return label


def brsmatch_result_rows(result):
    """Teilnehmer-Zeilen eines BRSMatch-Lookup-Ergebnisses für den
    Messung-Dialog: `(name, caliber)` als anzuzeigende Strings.

    `name` ist der truncated „Nachname, Vorname", `caliber` die übersetzte
    Kaliber-Zeile. Reine Funktion (headless testbar); ein Ursprung für
    Breiten-Berechnung und Rendering im Messung-Dialog.
    """
    participant = result.get("participant") or {}
    name = (truncate_text(participant.get("last_name", "")) + ", "
            + truncate_text(participant.get("first_name", "")))
    caliber = tr("dialog.measurement.caliber_value",
                 caliber=participant.get("caliber", "?"))
    return (name, caliber)


def get_git_hash():
    """Aktuellen Git-Hash als Kurzform liefern; 'unknown' bei Fehler."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            short = out.stdout.strip()
            return short if short else "unknown"
    except Exception:
        pass
    return "unknown"


class BRSAppUI(object):
    """ImGui-Overlay: verdrahtet die App-State-Maschine funktional.

    Pro AppState werden die passenden Dialoge/Menüs gezeichnet und Aktionen
    je nach Zustand enabled/disabled. Die konkrete Gestaltung/Layout folgt in
    einem separaten UI-Proposal.
    """

    def __init__(self, controller):
        self.controller = controller
        self._font_pixel_size = 13.0
        self._git_hash = None
        self._show_about = False
        self._show_filters = False
        self._show_vision_config = False
        # Eingabepuffer des Vision-Konfigurations-Dialogs: über Frames halten,
        # damit getippte Werte nicht durch den gespeicherten Config-Stand
        # überschrieben werden (Muster `_manual_buf`).
        self._vision_config_buf = None
        self._show_brsmatch = False
        # Eingabepuffer des BRSMatch-Verbindungs-Dialogs: über Frames halten,
        # damit getippte Werte nicht durch den gespeicherten Config-Stand
        # überschrieben werden (Muster `_manual_buf`). None = beim Öffnen neu
        # aus der Konfiguration befüllen.
        self._brsmatch_buf = None
        self._show_camera = False
        self._font_large = None
        # Manuelle Etikett-Eingabe: Eingabe-Puffer der vier Felder (immer
        # initial leer, wird beim Öffnen des Dialogs zurückgesetzt).
        self._manual_buf = {"dg": "", "sch_nr": "", "stand": "", "zeit": ""}
        # Auto-Fokus-Statusmaschine (synthetisches Tab): Das Default-Fokus
        # setzen (`set_item_default_focus`) legt nur den Nav-Fokus im ersten
        # Feld an — die Texteingabe (sichtbarer Cursor, `want_text_input`)
        # wird erst durch eine Tab-Aktion aktiviert. Deshalb wird 2 Frames
        # nach dem Erscheinen (Nav-Fokus ist dann im DG-Feld gelandet) ein
        # Tab PRESS/RELEASE synthetisch über `io.add_key_event` injiziert.
        # None | "delay1" | "press" | "release".
        self._manual_autotab_state = None
        # Enter-Erkennung: ACTIVE-Status der vier Felder des vorherigen
        # Frames. Im Enter-Frame deaktiviert das InputText sich selbst
        # (Enter schließt die Texteingabe), daher ist der eigene Frame-
        # Status hier immer False.
        self._manual_field_active = {
            k: False for k in ("dg", "sch_nr", "stand", "zeit")}
        # Logo (Über-uns-Dialog): Textur-Referenz (ImTextureRef) +
        # Seitenverhältnis der Datei; None, wenn die Logodatei fehlt.
        self._logo_ref = None
        self._logo_aspect = None
        # UI-State-Persistenz: bekannte Fensterpositionen + Debounce-Flush
        self._window_pos_cache = {}
        for _name in ("measurement", "filters", "vision_config", "brsmatch", "camera"):
            _pos = self.controller.load_window_state(_name)
            if _pos is not None:
                self._window_pos_cache[_name] = (float(_pos[0]), float(_pos[1]))
        self._pos_dirty = False
        self._last_flush_time = 0.0

    _DEBOUNCE_S = 0.5
    # Sichtbarkeitsdauer der Referenz-Statusmeldungen im Messung-Dialog
    STATUS_DURATION_S = 5.0

    def set_font_pixel_size(self, px):
        self._font_pixel_size = px

    def set_large_font(self, font):
        self._font_large = font

    def set_logo(self, tex_ref, aspect):
        """Logo-Textur-Referenz und Seitenverhältnis für den Über-uns-Dialog."""
        self._logo_ref = tex_ref
        self._logo_aspect = aspect

    def draw(self):
        ctrl = self.controller

        # Schrift-Präset: gesamte UI mit der aktiven Basisgröße pushen.
        # imgui-bundle 1.92 skaliert über push_font(font, size) korrekt
        # (auch lazy für Größen jenseits der Back-Größe); ein Runtime-
        # Re-Rastern des Atlas funktioniert dort nicht zuverlässig.
        base_font = getattr(getattr(ctrl, "canvas", None), "font", None)
        if base_font is not None:
            imgui.push_font(base_font, float(self._font_pixel_size))

        # Semitransparente Fenster: window_bg (Fenster-Hintergrund) und
        # menu_bar_bg (Menüleiste) müssen beide Alpha haben, sonst opak.
        # Gilt für Menüleiste + alle modalen Dialoge gleichermaßen.
        imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(8, 6))
        imgui.push_style_color(imgui.Col_.window_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.35))
        imgui.push_style_color(imgui.Col_.menu_bar_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.35))
        imgui.push_style_color(imgui.Col_.popup_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.35))

        menu_spacing = max(8.0, self._font_pixel_size * 0.62)
        imgui.push_style_var(imgui.StyleVar_.item_spacing,
                             imgui.ImVec2(menu_spacing, imgui.get_style().item_spacing.y))

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("Benchrestscore", True):
                if imgui.menu_item(tr("menu.about"), "", False)[0]:
                    self._show_about = True
                if imgui.menu_item(tr("menu.quit"), "", False)[0]:
                    ctrl.quit()
                imgui.end_menu()
            # Kalibrier-Aktionen (Start, Wiederherstellung, Karten-QC)
            if imgui.begin_menu(tr("menu.calibration"), True):
                if imgui.menu_item(tr("menu.calibration.recalibrate"), "", False, True)[0]:
                    ctrl.request_calibration()
                recover_enabled = (
                    ctrl.state is AppState.IDLE and has_valid_session())
                if imgui.menu_item(tr("menu.calibration.recover"), "",
                                   False, recover_enabled)[0]:
                    ctrl.recover_calibration()
                # Karten-Qualitätscheck: nur im Messbetrieb und wenn kein
                # laufender Check / offenes Ergebnis den Start blockiert.
                qc_busy = (getattr(ctrl, "card_qc_running", False)
                           or getattr(ctrl, "card_qc_result", None) is not None
                           or getattr(ctrl, "card_qc_error", None) is not None)
                qc_enabled = (ctrl.state is AppState.MEASURING and not qc_busy)
                if imgui.menu_item(tr("menu.card_qc"), "", False, qc_enabled)[0]:
                    ctrl.run_card_qc()
                imgui.end_menu()

            # Mess-Aktionen (Automatik, Referenz-Modus)
            if imgui.begin_menu(tr("menu.measure"), True):
                if imgui.menu_item(tr("menu.automation"), "", ctrl.automation, True)[0]:
                    ctrl.toggle_automation()
                ref_enabled = ctrl.state is AppState.MEASURING
                if imgui.menu_item(tr("menu.reference_mode"), "",
                                   ctrl.reference_mode, ref_enabled)[0]:
                    ctrl.toggle_reference_mode()
                imgui.end_menu()

            # Anzeige-Optionen (Hintergrund einfärben, Crop Messung)
            if imgui.begin_menu(tr("menu.view"), True):
                # Anzeige-Option „Hintergrund einfärben": nur mit gelernter/
                # wiederhergestellter dichter Referenz verfügbar; rein
                # anzeigebezogen, kein Mess-Eingriff.
                tint_enabled = ctrl.background_model.has_reference
                if imgui.menu_item(tr("menu.background_tint"), "",
                                   ctrl.filters.tint, tint_enabled)[0]:
                    ctrl.toggle_background_tint()
                # Crop Messung (C): View animiert auf alle Messpunkte einpassen.
                # Nur mit mindestens einer Messung aktiv; Punktanzahl im Label.
                ruler = getattr(ctrl, "ruler", None)
                n_points = ruler.point_count if ruler is not None else 0
                crop_enabled = n_points >= 1
                if imgui.menu_item(tr("menu.crop_measurement", n=n_points), "C",
                                   False, crop_enabled)[0]:
                    ctrl.canvas.start_fit_measurements()
                imgui.end_menu()

            # Einstellungen (Kamera, Bildfilter, Vision, Schriftgröße)
            if imgui.begin_menu(tr("menu.settings"), True):
                if imgui.menu_item(tr("menu.camera_settings"), "",
                                   self._show_camera, True)[0]:
                    self._show_camera = not self._show_camera
                if imgui.menu_item(tr("menu.filters"), "", self._show_filters, True)[0]:
                    self._show_filters = not self._show_filters
                if imgui.menu_item(tr("menu.vision_config"), "",
                                   self._show_vision_config, True)[0]:
                    self._show_vision_config = not self._show_vision_config
                if imgui.begin_menu(tr("menu.font"), True):
                    for key, label in (("normal", tr("menu.font.normal")),
                                       ("large", tr("menu.font.large")),
                                       ("xlarge", tr("menu.font.xlarge"))):
                        selected = ctrl.font_scale == key
                        if imgui.menu_item(label, "", selected, True)[0]:
                            ctrl.set_font_scale(key)
                    imgui.end_menu()
                imgui.end_menu()

            # BRSMatch (Aktivieren + Verbindung + Etikett-Scan-Mock)
            if imgui.begin_menu(tr("menu.brsmatch"), True):
                # Aktivieren als Checkmark direkt im Menü — schaltet den
                # BRSMatch-Modus um (Etikett-Scan) und persistiert den Zustand.
                if imgui.menu_item(tr("menu.brsmatch.enabled"), "",
                                   ctrl.brsmatch_enabled, True)[0]:
                    ctrl.set_brsmatch_config(ctrl.brsmatch_base_url,
                                             ctrl.brsmatch_api_key,
                                             ctrl.brsmatch_event_id,
                                             not ctrl.brsmatch_enabled)
                if imgui.menu_item(tr("dialog.brsmatch.title"), "",
                                   self._show_brsmatch, True)[0]:
                    self._show_brsmatch = not self._show_brsmatch
                imgui.end_menu()

            # Sprache (Endonyme; Auswahl wirkt sofort und wird gespeichert)
            if imgui.begin_menu(tr("menu.language"), True):
                for lang in SUPPORTED_LANGUAGES:
                    selected = lang == ctrl.language
                    if imgui.menu_item(LANGUAGE_ENDONYMS[lang], "", selected, True)[0]:
                        ctrl.set_language(lang)
                imgui.end_menu()

            # Kalibrier-Status (Loss-of-Calibration-Monitor) rechtsbündig,
            # sichtbar ab gelerntem Modell. Die Kaliber-Auswahl liegt im
            # Messung-Dialog; der Indikator ist der letzte rechte Eintrag.
            right = imgui.get_window_width() - 12

            model = ctrl.background_model
            if model.learned:
                res = ctrl.last_background_check
                status_tip = None
                if res is None:
                    # Noch kein Check gelaufen (z.B. direkt nach Recovery)
                    status_text = tr("background.status.checking")
                    status_color = (0.80, 0.80, 0.80, 1.0)
                elif res.status == MonitorStatus.UNAVAILABLE:
                    status_text = tr("background.status.na")
                    status_color = (0.80, 0.80, 0.80, 1.0)
                    info = getattr(model, "last_check_info", {}) or {}
                    if info.get("reason"):
                        status_tip = tr("background.status.na_tip",
                                        reason=info.get("reason", ""),
                                        kps=info.get("frame_keypoints", 0),
                                        matches=info.get("matches", 0),
                                        ratio=info.get("inlier_ratio", "-"))
                elif res.status == MonitorStatus.SHIFTED:
                    status_text = tr("background.status.shifted",
                                     mm=f"{res.deviation_mm:.3f}")
                    status_color = (0.95, 0.60, 0.20, 1.0)
                else:
                    status_text = tr("background.status.ok")
                    status_color = (0.35, 0.85, 0.35, 1.0)
                status_w = imgui.calc_text_size(status_text).x
                imgui.set_cursor_pos_x(right - status_w)
                imgui.text_colored(imgui.ImVec4(*status_color), status_text)
                if status_tip is not None:
                    imgui.set_item_tooltip(status_tip)

            imgui.end_main_menu_bar()

        imgui.pop_style_var()

        self._draw_about()
        self._draw_filters()
        self._draw_vision_config()
        self._draw_brsmatch_config()
        self._draw_camera_dialog()
        self._draw_workflow()
        self._draw_result()
        self._draw_card_qc()
        self._draw_manual_sticker_dialog()
        self._draw_confirm_wertung_dialog()
        self._draw_automation_flash()

        # Gedebouncte Persistenz (Filter + Fensterpositionen) — pro Frame.
        self._flush_pending_saves()

        imgui.pop_style_color(3)
        imgui.pop_style_var()

        if base_font is not None:
            imgui.pop_font()

    def _restore_window_pos(self, name):
        """Gespeicherte Fensterposition für das nächste begin() anwenden.

        Nur gültige (im sichtbaren Arbeitsbereich liegende) Positionen werden
        mit `Cond_.once` gesetzt: genau einmal pro Session, danach ist das
        Fenster frei verschiebbar. Rückgabe: (x, y) oder None."""
        pos = self.controller.load_window_state(name)
        if pos is None:
            return None
        vp = imgui.get_main_viewport()
        if not valid_window_pos(pos[0], pos[1], vp.work_size.x, vp.work_size.y):
            return None
        imgui.set_next_window_pos(imgui.ImVec2(float(pos[0]), float(pos[1])),
                                  imgui.Cond_.once)
        return (float(pos[0]), float(pos[1]))

    def _capture_window_pos(self, name):
        """Aktuelle Fensterposition erfassen; bei Änderung dirty markieren.

        Muss zwischen begin()/end() des Fensters laufen (imgui.get_window_pos()
        bezieht sich auf das aktuelle Fenster)."""
        pos = imgui.get_window_pos()
        cur = (float(pos.x), float(pos.y))
        if self._window_pos_cache.get(name) != cur:
            self._window_pos_cache[name] = cur
            self._pos_dirty = True

    def _flush_pending_saves(self, force=False):
        """Gedebouncte Persistenz von Filter- und Fensterzustand.

        Slider feuern pro Drag-Frame; gespeichert wird erst nach ~0,5 s Ruhe.
        `force=True` (beim Beenden) schreibt sofort. Rückgabe: True, wenn
        geschrieben wurde."""
        if not force and (time.time() - self._last_flush_time) < self._DEBOUNCE_S:
            return False
        self.controller.flush_filters_if_dirty()
        if self._pos_dirty:
            for name, pos in self._window_pos_cache.items():
                if pos is not None:
                    self.controller.save_window_state(name, pos[0], pos[1])
            self._pos_dirty = False
        self._last_flush_time = time.time()
        return True

    def flush_ui_state(self):
        """Verbleibende UI-Persistenz sofort schreiben (bei App-Beenden)."""
        self._flush_pending_saves(force=True)

    def _draw_about(self):
        """Modales "Über uns"-Fenster mit Git-Hash und Urheberhinweis."""
        if self._show_about:
            imgui.open_popup(tr("dialog.about.title"))
            self._show_about = False
            if self._git_hash is None:
                self._git_hash = get_git_hash()

        self._push_dialog_style()
        # Reiner Auto-Resize (kein set_next_window_size-Hint): pro-Frame-Hint
        # hebt in imgui-bundle 1.92 AlwaysAutoResize auf (AutoFit-Frames -> -1)
        # -> fixierte Höhe, Scrollbar statt passender Größe (design.md D3;
        # gleiches Muster wie _draw_result).
        shown, _ = imgui.begin_popup_modal(tr("dialog.about.title"),
                                           flags=imgui.WindowFlags_.always_auto_resize)
        if shown:
            imgui.text(tr("dialog.about.version", hash=self._git_hash or get_git_hash()))
            imgui.text("© Harald Lampesberger")
            imgui.dummy(imgui.ImVec2(0, 8))
            # Logo unter dem Urheberhinweis: 50 % der Dialog-Inhaltsbreite,
            # vertikaler Spielraum (eine Schriftzeile) darunter (design.md D3).
            if self._logo_ref is not None:
                w, h = about_logo_size(self._font_pixel_size, self._logo_aspect)
                imgui.image(self._logo_ref, imgui.ImVec2(w, h))
                imgui.dummy(imgui.ImVec2(0, self._font_pixel_size))
            if imgui.button(tr("common.ok")):
                imgui.close_current_popup()
            imgui.end_popup()
        self._pop_dialog_style()

    @staticmethod
    def _push_dialog_style():
        """Höhere Deckkraft für modale Dialoge (bessere Lesbarkeit)."""
        imgui.push_style_color(imgui.Col_.window_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.60))

    @staticmethod
    def _pop_dialog_style():
        imgui.pop_style_color()

    def _draw_config_rows(self, rows, buf, label_w):
        """Eingabe-Zeilen eines Konfigurations-Dialogs zeichnen (Label links,
        `input_text` rechts, gemeinsame, inhalts-adaptive Breite).

        `rows` = Tuples `(field_id, buf_key, label, is_password)`; `buf` ist
        der über Frames gehaltene Puffer (`buf_key` → String); `label_w` die
        Breite der Label-Spalte. Die Feldbreite wächst pro Frame mit den
        Pufferwerten und der aktiven Schrift (`config_dialog_field_width`,
        Obergrenze 90 % der Viewport-Breite), alle Zeilen sind gleich breit.
        Rückgabe: Menge der geänderten `buf_key`s (leer bei keiner Änderung)."""
        changed_keys = set()
        max_text_w = max(imgui.calc_text_size(value).x
                         for value in buf.values())
        work_x = imgui.get_main_viewport().work_size.x
        max_field_w = max(160.0, 0.9 * work_x - label_w - 18.0)
        field_w = config_dialog_field_width(max_text_w, max_w=max_field_w)
        for field_id, buf_key, label, is_password in rows:
            imgui.text(label)
            imgui.same_line()
            imgui.set_cursor_pos_x(label_w)
            imgui.set_next_item_width(field_w)
            flags = imgui.InputTextFlags_.password if is_password \
                else imgui.InputTextFlags_.none
            changed, new_value = imgui.input_text(
                field_id, buf[buf_key], flags)
            buf[buf_key] = new_value
            if changed:
                changed_keys.add(buf_key)
        return changed_keys

    def _draw_filters(self):
        """Panel für Anzeige-Filter (per-Pixel, nur Anzeige). Sichtbar in allen
        App-States; Parameter wirken ausschließlich auf das Webcam-Bild."""
        if not self._show_filters:
            return
        ctrl = self.controller
        filt = ctrl.filters
        self._push_dialog_style()
        self._restore_window_pos("filters")
        if imgui.begin(tr("dialog.filters.title"), flags=imgui.WindowFlags_.always_auto_resize):
            # Aktivieren wie Automatik im Messung-Dialog: Checkbox mit grünem Text
            # bei aktivem Filter (Stil analog zu "Automatik (M)").
            imgui.push_style_color(
                imgui.Col_.text,
                imgui.ImVec4(0.35, 0.85, 0.35, 1.0)
                if filt.active
                else imgui.ImVec4(0.80, 0.80, 0.80, 1.0))
            changed, _ = imgui.checkbox(tr("dialog.filters.enable"), filt.active)
            imgui.pop_style_color()
            if changed:
                ctrl.toggle_filters_active()
            imgui.separator()
            changed, inv = imgui.checkbox(tr("filter.invert"), filt.invert)
            if changed:
                ctrl.set_filter_param("invert", inv)
            imgui.same_line()
            changed, gray = imgui.checkbox(tr("filter.gray"), filt.gray)
            if changed:
                ctrl.set_filter_param("gray", gray)
            changed, sat = imgui.slider_float(tr("filter.saturation"), filt.saturation,
                                              0.0, 2.0)
            if changed:
                ctrl.set_filter_param("saturation", sat)
            changed, con = imgui.slider_float(tr("filter.contrast"), filt.contrast,
                                              0.5, 3.0)
            if changed:
                ctrl.set_filter_param("contrast", con)
            changed, gam = imgui.slider_float(tr("filter.gamma"), filt.gamma, 0.5, 2.5)
            if changed:
                ctrl.set_filter_param("gamma", gam)
            changed, bri = imgui.slider_float(tr("filter.brightness"), filt.brightness,
                                              -0.5, 0.5)
            if changed:
                ctrl.set_filter_param("brightness", bri)
            imgui.dummy(imgui.ImVec2(0, 8))
            if imgui.button(tr("common.reset")):
                ctrl.reset_filters()
            imgui.same_line()
            if imgui.button(tr("common.close")):
                self._show_filters = False
            self._capture_window_pos("filters")
            imgui.end()
        self._pop_dialog_style()

    def _draw_vision_config(self):
        """Vision-Konfiguration (Einstellungen-Reiter): Base-URL/Modell/API-Key
        + Test.

        Persistiert via `settings.save({"vision": ...})`; der Test-Button führt
        einen Mini-Call mit dem aktuellen Kamerabild aus — asynchron im
        Hintergrund-Thread (`ctrl.start_vision_test`), damit die Render-Loop
        nicht blockiert wird. Ergebnis/Lauf-Status liest die UI pro Frame aus
        dem Controller; Feld-Änderungen und Schließen werfen den Test ab
        (`ctrl.clear_vision_test`).
        """
        if not self._show_vision_config:
            return
        ctrl = self.controller
        self._push_dialog_style()
        self._restore_window_pos("vision_config")
        cfg = ctrl.get_vision_config()
        if self._vision_config_buf is None:
            self._vision_config_buf = {
                "base_url": cfg["base_url"],
                "model": cfg["model"],
                "api_key": cfg["api_key"],
            }
        # Auto-Resize an den Inhalt (wie alle anderen Dialoge): Breite passt
        # bei jedem Schriftgrößen-Präset an, die Button-Reihe läuft nie über.
        if imgui.begin(tr("dialog.vision_config.title"),
                       flags=imgui.WindowFlags_.always_auto_resize):
            # Labels links, Eingabefelder rechts — einheitliche Label-Spalte.
            label_keys = ("dialog.vision_config.base_url",
                          "dialog.vision_config.model",
                          "dialog.vision_config.api_key")
            label_w = max(imgui.calc_text_size(tr(k)).x for k in label_keys) + 16.0
            rows = [
                ("##vision_base_url", "base_url",
                 tr(label_keys[0]), False),
                ("##vision_model", "model",
                 tr(label_keys[1]), False),
                ("##vision_api_key", "api_key",
                 tr(label_keys[2]), True),
            ]
            # Inhalts-adaptive Feldbreite: wächst mit eingegebenem Text und
            # aktiver Schrift, Cap bei 90 % der Viewport-Breite — lange
            # Base-URLs bleiben vollständig lesbar (design.md D1/D3).
            changed_keys = self._draw_config_rows(
                rows, self._vision_config_buf, label_w)
            if changed_keys:
                # Ein Testergebnis gilt nur für die getesteten Werte.
                ctrl.clear_vision_test()
            imgui.dummy(imgui.ImVec2(0, 6))
            if imgui.button(tr("dialog.vision_config.save")):
                ctrl.set_vision_config(self._vision_config_buf["base_url"],
                                       self._vision_config_buf["model"],
                                       self._vision_config_buf["api_key"])
                cfg = ctrl.get_vision_config()
            imgui.same_line()
            # Während des Laufs deaktiviert: der Call läuft asynchron im
            # Hintergrund-Thread, die Render-Loop bleibt frei.
            imgui.begin_disabled(ctrl.vision_test_running)
            if imgui.button(tr("dialog.vision_config.test")):
                # Die eingegebenen (ggf. noch ungespeicherten) Werte testen.
                ctrl.start_vision_test(self._vision_config_buf["base_url"],
                                       self._vision_config_buf["model"],
                                       self._vision_config_buf["api_key"])
            imgui.end_disabled()
            imgui.same_line()
            if imgui.button(tr("common.close")):
                self._show_vision_config = False
                self._vision_config_buf = None
                ctrl.clear_vision_test()
            if ctrl.vision_test_running:
                # Laufender Test: Hinweis in normaler Schrift (grau).
                imgui.text_colored(imgui.ImVec4(0.80, 0.80, 0.80, 1.0),
                                   tr("dialog.vision_config.testing"))
            elif ctrl.vision_test_status is not None:
                key = "dialog.vision_config." + ctrl.vision_test_status
                if ctrl.vision_test_status == "ok":
                    color = imgui.ImVec4(0.35, 0.85, 0.35, 1.0)
                else:
                    color = imgui.ImVec4(1.0, 0.45, 0.45, 1.0)
                # Prominente Statuszeile: große Schrift wie im Messung-Dialog.
                if self._font_large is not None:
                    imgui.push_font(self._font_large,
                                    self._font_pixel_size * 1.35)
                imgui.text_colored(color, tr(key))
                if self._font_large is not None:
                    imgui.pop_font()
            self._capture_window_pos("vision_config")
            imgui.end()
        self._pop_dialog_style()

    def _draw_brsmatch_config(self):
        """BRSMatch-Verbindungs-Dialog (Einstellungs-Dialog im BRSMatch-Reiter).

        Felder für Base-URL, API-Key und Event-ID sowie eine
        „Aktivieren"-Checkbox; die Konfiguration wird über
        `ctrl.set_brsmatch_config` persistent gespeichert. Der
        Aktivieren-Zustand gate-t den Etikett-Scan. Die Eingabewerte werden in
        `_brsmatch_buf` über Frames gehalten (beim Öffnen aus der Konfiguration
        befüllt), damit getippte Änderungen nicht durch den gespeicherten
        Config-Stand überschrieben werden.
        """
        if not self._show_brsmatch:
            return
        ctrl = self.controller
        self._push_dialog_style()
        self._restore_window_pos("brsmatch")
        cfg = ctrl.get_brsmatch_config()
        if self._brsmatch_buf is None:
            self._brsmatch_buf = {
                "base_url": cfg["base_url"],
                "api_key": cfg["api_key"],
                "event_id": "" if not cfg["event_id"] else str(cfg["event_id"]),
            }
        # Auto-Resize an den Inhalt (wie alle anderen Dialoge).
        if imgui.begin(tr("dialog.brsmatch.title"),
                       flags=imgui.WindowFlags_.always_auto_resize):
            label_keys = ("dialog.brsmatch.base_url",
                          "dialog.brsmatch.api_key",
                          "dialog.brsmatch.event_id")
            label_w = max(imgui.calc_text_size(tr(k)).x for k in label_keys) + 16.0
            rows = [
                ("##brsmatch_base_url", "base_url",
                 tr(label_keys[0]), False),
                ("##brsmatch_api_key", "api_key",
                 tr(label_keys[1]), True),
                ("##brsmatch_event_id", "event_id",
                 tr(label_keys[2]), False),
            ]
            # Inhalts-adaptive Feldbreite wie in der Vision-Konfiguration
            # (design.md D1/D3): lange Base-URLs bleiben vollständig lesbar,
            # Cap bei 90 % der Viewport-Breite.
            self._draw_config_rows(rows, self._brsmatch_buf, label_w)
            imgui.dummy(imgui.ImVec2(0, 6))
            changed, enabled = imgui.checkbox(tr("dialog.brsmatch.enabled"),
                                              cfg["enabled"])
            imgui.dummy(imgui.ImVec2(0, 6))
            if imgui.button(tr("dialog.vision_config.save")):
                ctrl.set_brsmatch_config(self._brsmatch_buf["base_url"],
                                         self._brsmatch_buf["api_key"],
                                         self._brsmatch_buf["event_id"],
                                         enabled)
            imgui.same_line()
            if imgui.button(tr("dialog.brsmatch.close")):
                self._show_brsmatch = False
                self._brsmatch_buf = None
            self._capture_window_pos("brsmatch")
            imgui.end()
        self._pop_dialog_style()

    def _draw_camera_dialog(self):
        """Kamera-Einstellungen (Einstellungen-Reiter): Gerät, Auflösung,
        Rotation als nicht-modaler Dialog. Jede Änderung wird sofort angewandt
        (`apply_camera_settings`) und persistiert."""
        if not self._show_camera:
            return
        ctrl = self.controller
        self._push_dialog_style()
        self._restore_window_pos("camera")
        if imgui.begin(tr("dialog.camera.title"),
                       flags=imgui.WindowFlags_.always_auto_resize):
            combo_w = 320.0
            # Geräte-Combo: aktuelles Gerät immer mitführen (auch wenn es
            # nicht mehr unter /dev/video* auftaucht -> Auswahl bleibt
            # bedienbar).
            devices = list_camera_devices()
            if ctrl.camera_device not in devices:
                devices.insert(0, ctrl.camera_device)
            device_idx = devices.index(ctrl.camera_device)
            imgui.text(tr("camera.device"))
            imgui.same_line()
            imgui.set_next_item_width(combo_w)
            changed, idx = imgui.combo("##camera_device", device_idx, devices)
            if changed:
                ctrl.apply_camera_settings(devices[idx], ctrl.camera_preset)

            # Auflösungs-Combo: nur unterstützte Presets des aktiven Geräts.
            presets = ctrl.supported_presets(ctrl.camera_device)
            preset_names = [p[0] for p in presets]
            current_name = ctrl.camera_preset[0]
            current_idx = (preset_names.index(current_name)
                           if current_name in preset_names else 0)
            imgui.text(tr("camera.resolution"))
            imgui.same_line()
            imgui.set_next_item_width(combo_w)
            changed, idx = imgui.combo("##camera_resolution", current_idx,
                                       preset_names)
            if changed:
                ctrl.apply_camera_settings(ctrl.camera_device, presets[idx])

            # Rotation (Montage: 0° aufrecht / 180° auf dem Kopf). Wirkt
            # sofort.
            rotate_options = [0, 180]
            rotate_labels = [tr("camera.rotate.0"), tr("camera.rotate.180")]
            current_rot = rotate_options.index(ctrl.camera_rotate)
            imgui.text(tr("camera.rotate"))
            imgui.same_line()
            imgui.set_next_item_width(combo_w)
            changed, ridx = imgui.combo("##camera_rotate", current_rot,
                                        rotate_labels)
            if changed:
                ctrl.apply_camera_settings(ctrl.camera_device,
                                           ctrl.camera_preset,
                                           rotate_options[ridx])
            imgui.dummy(imgui.ImVec2(0, 8))
            if imgui.button(tr("common.close")):
                self._show_camera = False
            self._capture_window_pos("camera")
            imgui.end()
        self._pop_dialog_style()

    def _measurement_dialog_width(self, ctrl, ruler):
        """Definierte Breite (px) des Messung-Dialogs.

        Maximum der Breiten der stabilen Inhaltszeilen, gemessen mit der
        jeweils aktiven Schrift (Kaliber-/Messwert-Zeilen in der 1,35x-
        Großschrift wie im Rendering). Flüchtige Status-/Fehlerzeilen
        (Scan, Lookup, Wertung, Referenz, Auto-Detektion) sind
        ausgeschlossen: Sie vergrößern den Dialog nur während ihrer Anzeige
        (AlwaysAutoResize), bestimmen aber nicht die definierte Breite.
        """
        style = imgui.get_style()
        pad_x = style.window_padding.x
        inner_x = style.item_inner_spacing.x
        widths = []
        # Kaliber-Zeile + Messwert-Zeilen (Großschrift wie im Rendering).
        if self._font_large is not None:
            imgui.push_font(self._font_large, self._font_pixel_size * 1.35)
        widths.append(imgui.calc_text_size(tr("measurement.caliber")).x
                      + inner_x
                      + (imgui.calc_text_size(
                          ctrl.mbox.cal[ctrl.caliber_index][0]).x
                          + imgui.get_font_size() * 2.0))
        for label, value in ctrl.mbox.value_rows():
            widths.append(imgui.calc_text_size(label).x + inner_x
                          + imgui.calc_text_size(value).x)
        if self._font_large is not None:
            imgui.pop_font()
        # Automatik-Checkbox: Quadrat + Spacing + Label.
        widths.append(imgui.get_frame_height() + inner_x
                      + imgui.calc_text_size(
                          tr("dialog.measurement.automation")).x)
        # Referenz-Modus: Button (nur im aktiven Modus sichtbar).
        if ctrl.reference_mode:
            widths.append(imgui.calc_text_size(
                tr("dialog.measurement.save_reference")).x + 2.0 * pad_x)
        # Messpunkt-Liste inkl. Lösch-Buttons (Label = Rendering-String).
        n = ruler.point_count
        if n > 0:
            del_w = imgui.calc_text_size("×").x + 2.0 * pad_x
            for i in range(n):
                label = measurement_point_label(
                    i, ruler.active_idx, ruler.metric[i, 0],
                    ruler.metric[i, 1])
                widths.append(imgui.calc_text_size(label).x + inner_x + del_w)
        # Reset-Button.
        widths.append(imgui.calc_text_size(
            tr("dialog.measurement.clear_points")).x + 2.0 * pad_x)
        # BRSMatch-Abschnitt: Buttons, Metadaten-Zeilen, Teilnehmer-Info.
        if brsmatch_metadata_visible(ctrl.brsmatch_enabled):
            scan_w = imgui.calc_text_size(
                tr("dialog.measurement.scan_sticker")).x + 2.0 * pad_x
            widths.append(scan_w)
            if manual_sticker_visible(ctrl.brsmatch_enabled):
                widths.append(scan_w + inner_x + imgui.calc_text_size(
                    tr("dialog.measurement.scan_manual")).x + 2.0 * pad_x)
            meta = ctrl.sticker_meta
            if meta is not None:
                for label, key in (("DG", "dg"), ("Sch-Nr", "sch_nr"),
                                   ("Stand", "stand"), ("Zeit", "zeit")):
                    widths.append(imgui.calc_text_size(
                        f"{label}: {meta.get(key, '?')}").x)
            result = ctrl.lookup_result
            if result is not None:
                name, caliber = brsmatch_result_rows(result)
                widths.append(imgui.calc_text_size(name).x)
                widths.append(imgui.calc_text_size(caliber).x)
                if ctrl.mbox.distance >= 0:
                    widths.append(imgui.calc_text_size(
                        tr("dialog.measurement.wertung")).x + 2.0 * pad_x)
        return measurement_dialog_content_width(*widths)

    def _draw_workflow(self):
        ctrl = self.controller
        if ctrl.state is AppState.IDLE:
            self._push_dialog_style()
            # Auto-Size: Fenster wächst mit Fehlermeldungen (kein Scrollen nötig).
            position_workflow_dialog(ctrl.state)
            if imgui.begin(calibration_step_title(ctrl.state),
                           flags=imgui.WindowFlags_.always_auto_resize):
                imgui.text(tr("dialog.calibration.align"))
                imgui.dummy(imgui.ImVec2(0, 8))
                if imgui.button(tr("dialog.calibration.start")):
                    ctrl.start_calibration()
                if has_valid_session():
                    imgui.same_line()
                    if imgui.button(tr("dialog.calibration.recover")):
                        ctrl.recover_calibration()
                err = getattr(ctrl.calibration, "error", None)
                if err:
                    imgui.dummy(imgui.ImVec2(0, 4))
                    imgui.text_colored(imgui.ImVec4(1.0, 0.45, 0.45, 1.0), err)
                rec_err = getattr(ctrl, "recovery_error", None)
                if rec_err:
                    text = tr("recovery.error.no_session")
                    if rec_err == "resolution":
                        text = tr("recovery.error.resolution")
                    elif rec_err == "corrupt":
                        text = tr("recovery.error.corrupt")
                    imgui.dummy(imgui.ImVec2(0, 4))
                    imgui.text_colored(imgui.ImVec4(1.0, 0.45, 0.45, 1.0), text)
                imgui.end()
            self._pop_dialog_style()
        elif ctrl.state is AppState.CALIBRATING:
            self._push_dialog_style()
            # Auto-Resize: eine Textzeile, wächst mit der Schrift (auch XLarge).
            position_workflow_dialog(ctrl.state)
            if imgui.begin(calibration_step_title(ctrl.state),
                           flags=imgui.WindowFlags_.always_auto_resize):
                imgui.text(tr("dialog.calibration.running"))
                imgui.end()
            self._pop_dialog_style()
        elif ctrl.state is AppState.LEARN_PROMPT:
            self._push_dialog_style()
            position_workflow_dialog(ctrl.state)
            if imgui.begin(calibration_step_title(ctrl.state),
                           flags=imgui.WindowFlags_.always_auto_resize):
                imgui.text(tr("background.learn_prompt"))
                imgui.dummy(imgui.ImVec2(0, 8))
                if imgui.button(tr("background.learn")):
                    ctrl.learn_background()
                imgui.same_line()
                if imgui.button(tr("background.abort")):
                    ctrl.cancel_calibration()
                if ctrl.background_learn_error:
                    imgui.dummy(imgui.ImVec2(0, 4))
                    imgui.text_colored(imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                                       tr("background.too_sparse"))
                imgui.end()
            self._pop_dialog_style()
        elif ctrl.state is AppState.LEARN_RESULT:
            self._push_dialog_style()
            position_workflow_dialog(ctrl.state)
            if imgui.begin(calibration_step_title(ctrl.state),
                           flags=imgui.WindowFlags_.always_auto_resize):
                imgui.text(tr("background.result_info",
                              n=ctrl.background_model.keypoint_count))
                imgui.dummy(imgui.ImVec2(0, 8))
                if imgui.button(tr("background.finish")):
                    ctrl.finish_background()
                imgui.same_line()
                if imgui.button(tr("background.abort")):
                    ctrl.cancel_calibration()
                imgui.end()
            self._pop_dialog_style()
        elif ctrl.state is AppState.MEASURING:
            if ctrl.mbox and ctrl.mbox.enabled:
                ruler = ctrl.ruler
                n = ruler.point_count
                # Definierte Dialog-Breite aus den stabilen Inhaltszeilen
                # (flüchtige Status-/Fehlerzeilen ausgeschlossen). Die
                # rechtsbündigen Zeilen ankeren daran statt an der aktuellen
                # Fensterbreite — dadurch kehrt der Dialog nach einer breiten
                # Fehlerzeile wieder in seine normale Größe zurück.
                dialog_w = self._measurement_dialog_width(ctrl, ruler)
                style = imgui.get_style()
                padding_x = style.window_padding.x
                # Stabile Fensterbreite = definierte Inhaltsbreite +
                # Fenster-Padding + Rahmen (Auto-Fit-Breite der stabilen
                # Zeilen). Rechtsbündigung und Breiten-Floor beziehen sich
                # auf sie statt auf die aktuelle Fensterbreite.
                stable_window_w = (dialog_w + 2.0 * padding_x
                                   + 2.0 * style.window_border_size)
                self._push_dialog_style()
                # Window auto-sizes to content -> kein Scrollbalken nötig.
                self._restore_window_pos("measurement")
                # Breite: Floor = stabile Fensterbreite; Obergrenze offen,
                # damit breite Status-/Fehlerzeilen den Dialog nur während
                # ihrer Anzeige vergrößern (Auto-Resize bleibt vollständig
                # aktiv).
                imgui.set_next_window_size_constraints(
                    imgui.ImVec2(stable_window_w, -1.0),
                    imgui.ImVec2(imgui.FLT_MAX, -1.0),
                    None,
                )
                if imgui.begin(tr("dialog.measurement.title"),
                               flags=imgui.WindowFlags_.always_auto_resize):
                    # Kaliber-Auswahl: Label links, Dropdown rechtsbündig in der
                    # definierten Dialog-Breite, in derselben großen Schrift wie
                    # die Messwerte. Breite an das aktuell gewählte Kaliber
                    # gekoppelt (nicht ans längste Label).
                    if self._font_large is not None:
                        imgui.push_font(self._font_large,
                                        self._font_pixel_size * 1.35)
                    labels = [c[0] for c in ctrl.mbox.cal]
                    combo_w = (imgui.calc_text_size(
                        labels[ctrl.caliber_index]).x
                        + imgui.get_font_size() * 2.0)
                    imgui.text(tr("measurement.caliber"))
                    imgui.same_line(stable_window_w - combo_w - padding_x)
                    imgui.set_next_item_width(combo_w)
                    changed, idx = imgui.combo("##kaliber_dialog",
                                               ctrl.caliber_index, labels)
                    if changed:
                        ctrl.set_caliber(idx)
                    # Messwerte: Label links, Wert rechtsbündig (gleiche Spalte).
                    rows = ctrl.mbox.value_rows()
                    if rows:
                        value_w = max(imgui.calc_text_size(v).x for _, v in rows)
                        for label, value in rows:
                            imgui.text(label)
                            imgui.same_line(stable_window_w - value_w - padding_x)
                            imgui.text(value)
                    if self._font_large is not None:
                        imgui.pop_font()
                    # Automation: Schalter (Label wird grün, wenn aktiv)
                    imgui.separator()
                    imgui.push_style_color(
                        imgui.Col_.text,
                        imgui.ImVec4(0.35, 0.85, 0.35, 1.0)
                        if ctrl.automation
                        else imgui.ImVec4(0.80, 0.80, 0.80, 1.0))
                    changed, _ = imgui.checkbox(tr("dialog.measurement.automation"),
                                                ctrl.automation)
                    imgui.pop_style_color()
                    if changed:
                        ctrl.toggle_automation()
                    # Referenz-Modus (Messen-Menü): Button nur im aktiven Modus.
                    if ctrl.reference_mode:
                        imgui.separator()
                        if imgui.button(tr("dialog.measurement.save_reference")):
                            ctrl.save_reference()
                        # Statuszeilen (Info/Fehler) nur innerhalb des Zeitfensters
                        status_visible = (
                            ctrl.reference_status_at is not None
                            and time.monotonic() - ctrl.reference_status_at
                            < BRSAppUI.STATUS_DURATION_S)
                        if status_visible and ctrl.reference_info is not None:
                            imgui.text_colored(
                                imgui.ImVec4(0.35, 0.85, 0.35, 1.0),
                                tr("dialog.measurement.reference_info",
                                   n=ctrl.reference_info,
                                   sample=ctrl.reference_sample or "?"))
                        elif status_visible and ctrl.reference_error == "no_points":
                            imgui.text_colored(
                                imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                                tr("dialog.measurement.reference_no_points"))
                        elif status_visible and ctrl.reference_error:
                            imgui.text_colored(
                                imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                                tr("dialog.measurement.reference_failed"))
                    if n > 0:
                        imgui.separator()
                        imgui.text(tr("dialog.measurement.points"))
                        for i in range(n):
                            label = measurement_point_label(
                                i, ruler.active_idx,
                                ruler.metric[i, 0], ruler.metric[i, 1])
                            imgui.text(label)
                            imgui.same_line()
                            if imgui.small_button(f"×##{i}"):
                                ctrl.remove_point(i)
                                break
                            imgui.set_item_tooltip(tr("common.delete"))
                        imgui.separator()
                    if ruler.auto_error_active():
                        imgui.text_colored(imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                                           tr("dialog.measurement.auto_failed"))
                    imgui.dummy(imgui.ImVec2(0, 8))
                    if imgui.button(tr("dialog.measurement.clear_points")):
                        ctrl.reset_points()
                    # BRSMatch-Etikett-Scan + manuelle Eingabe (nur bei
                    # aktiviertem BRSMatch): Buttons + Anzeige des letzten
                    # Ergebnisses bzw. des Scan-Status. Die Werte stehen
                    # untereinander, damit der Messung-Dialog nicht unnötig
                    # breit wird.
                    if brsmatch_metadata_visible(ctrl.brsmatch_enabled):
                        imgui.dummy(imgui.ImVec2(0, 8))
                        if imgui.button(tr("dialog.measurement.scan_sticker")):
                            ctrl.scan_sticker()
                        imgui.same_line()
                        if manual_sticker_visible(ctrl.brsmatch_enabled) \
                                and imgui.button(tr("dialog.measurement.scan_manual")):
                            self._manual_buf = {
                                "dg": "", "sch_nr": "", "stand": "",
                                "zeit": ""}
                            ctrl.open_manual_dialog()
                        meta = ctrl.sticker_meta
                        if meta is not None:
                            for label, key in (
                                    ("DG", "dg"),
                                    ("Sch-Nr", "sch_nr"),
                                    ("Stand", "stand"),
                                    ("Zeit", "zeit")):
                                imgui.text(f"{label}: {meta.get(key, '?')}")
                        elif ctrl.sticker_status == "running":
                            imgui.text_colored(
                                imgui.ImVec4(0.80, 0.80, 0.80, 1.0),
                                tr("dialog.measurement.scan_running"))
                        elif ctrl.sticker_status == "error":
                            imgui.text_colored(
                                imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                                tr("dialog.measurement.scan_error"))
                        self._draw_brsmatch_result(ctrl)
                    self._capture_window_pos("measurement")
                    imgui.end()
                self._pop_dialog_style()

    def _draw_automation_flash(self):
        """Kurzfristige Auto-Erkennungs-Visualisierung (Screen-Space): Suchradius
        um den Klickpunkt + Korrekturlinie roh->detektiert (grün), Fehlschlag rot."""
        ctrl = self.controller
        ruler = getattr(ctrl, "ruler", None)
        if ruler is None:
            return
        flash = ruler.flash()
        if flash is None:
            return
        dl = imgui.get_foreground_draw_list()
        if flash["ok"]:
            col = imgui.color_convert_float4_to_u32(
                imgui.ImVec4(0.30, 0.85, 0.35, 0.95))
        else:
            col = imgui.color_convert_float4_to_u32(
                imgui.ImVec4(0.95, 0.35, 0.35, 0.95))
        rx, ry = flash["raw_px"]
        cx, cy = flash["center_px"]
        radius = flash["search_radius_px"]
        if radius is not None and radius > 0:
            dl.add_circle(imgui.ImVec2(float(rx), float(ry)), float(radius),
                          col, 48, 2.0)
        if flash["ok"] and (abs(rx - cx) > 0.5 or abs(ry - cy) > 0.5):
            dl.add_line(imgui.ImVec2(float(rx), float(ry)),
                        imgui.ImVec2(float(cx), float(cy)), col, 2.0)

    def _draw_card_qc(self):
        """Karten-Qualitätscheck: Status/Ergebnis-/Fehler-Dialog
        (Kalibrierung-Menü)."""
        ctrl = self.controller
        running = getattr(ctrl, "card_qc_running", False)
        result = getattr(ctrl, "card_qc_result", None)
        error = getattr(ctrl, "card_qc_error", None)
        if not running and result is None and error is None:
            return
        self._push_dialog_style()
        imgui.set_next_window_pos(workflow_dialog_center(imgui.get_main_viewport()),
                                  imgui.Cond_.once,
                                  imgui.ImVec2(0.5, 0.5))
        if imgui.begin(tr("dialog.card_qc.title"),
                       flags=imgui.WindowFlags_.always_auto_resize):
            if running:
                imgui.text(tr("dialog.card_qc.running"))
            elif result is not None:
                if result["pass"]:
                    imgui.text_colored(imgui.ImVec4(0.35, 0.85, 0.35, 1.0),
                                       tr("dialog.card_qc.pass"))
                else:
                    imgui.text_colored(
                        imgui.ImVec4(0.95, 0.35, 0.35, 1.0),
                        tr("dialog.card_qc.fail", over=result["over_count"]))
                imgui.text(tr("dialog.card_qc.stats",
                              max=f"{result['max_um']:.1f}",
                              mean=f"{result['mean_um']:.1f}"))
                imgui.text(tr("dialog.card_qc.tolerance",
                              tol=f"{QC_TOLERANCE_MM}"))
            else:
                error_key = {
                    "not_measuring": "card_qc.error.not_measuring",
                    "no_calibration": "card_qc.error.no_calibration",
                    "no_reference": "card_qc.error.no_reference",
                    "no_frame": "card_qc.error.no_frame",
                    "no_grid": "card_qc.error.no_grid",
                }.get(error, "card_qc.error.no_grid")
                imgui.text_colored(imgui.ImVec4(0.95, 0.60, 0.20, 1.0),
                                   tr(error_key, count=ctrl.card_qc_circles))
            imgui.dummy(imgui.ImVec2(0, 8))
            if running:
                if imgui.button(tr("dialog.card_qc.abort")):
                    ctrl.dismiss_card_qc()
            elif imgui.button(tr("dialog.card_qc.dismiss")):
                ctrl.dismiss_card_qc()
            imgui.end()
        self._pop_dialog_style()

    def _draw_brsmatch_result(self, ctrl):
        """Lookup-Ergebnis + Wertung-Aktion im Messung-Dialog zeichnen.

        Läuft/Fehler des Query-API-Lookups, grüne truncated Teilnehmer-Zeile
        (Nachname, Vorname) mit dem Kaliber darunter bei `existing_scores == 0`,
        **orange** Name/Kaliber bei `existing_scores > 0` sowie der
        „Wertung"-Button (nur bei vorhandenem Messwert). Ohne aktiven
        Lookup wird nur ein ggf. laufender/beendeter Upload-Status gezeigt
        (z.B. nach erfolgreichem Upload, wenn die Metadaten bereits
        zurückgesetzt sind).
        """
        status = ctrl.lookup_status
        if status == "running":
            imgui.text_colored(imgui.ImVec4(0.80, 0.80, 0.80, 1.0),
                               tr("dialog.measurement.lookup_running"))
            return
        if status == "error":
            imgui.text_colored(
                imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                tr(ctrl.lookup_error or "dialog.measurement.lookup_server"))
            return
        result = ctrl.lookup_result
        if result is not None:
            existing = int(result.get("existing_scores", 0))
            name, caliber = brsmatch_result_rows(result)
            if existing <= 0:
                imgui.text_colored(imgui.ImVec4(0.35, 0.85, 0.35, 1.0), name)
                imgui.text_colored(imgui.ImVec4(0.35, 0.85, 0.35, 1.0), caliber)
            else:
                imgui.text_colored(imgui.ImVec4(0.95, 0.60, 0.20, 1.0), name)
                imgui.text_colored(imgui.ImVec4(0.95, 0.60, 0.20, 1.0), caliber)
            has_value = ctrl.mbox is not None and ctrl.mbox.distance >= 0
            if has_value:
                imgui.dummy(imgui.ImVec2(0, 4))
                if imgui.button(tr("dialog.measurement.wertung")):
                    ctrl.request_wertung()
            self._draw_wertung_status(ctrl)
            return
        # Kein aktiver Lookup (z.B. nach Erfolg): Upload-Status zeigen.
        self._draw_wertung_status(ctrl)

    def _draw_wertung_status(self, ctrl):
        """Upload-Status der Wertung zeichnen (läuft/Fehler/kurz Erfolg)."""
        status = ctrl.wertung_status
        if status == "running":
            imgui.text_colored(imgui.ImVec4(0.80, 0.80, 0.80, 1.0),
                               tr("dialog.measurement.wertung_running"))
        elif status == "error":
            imgui.text_colored(
                imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                tr(ctrl.wertung_error or "dialog.measurement.wertung_server"))
        elif status == "ok" and ctrl.wertung_ok_at is not None \
                and time.monotonic() - ctrl.wertung_ok_at \
                < BRSAppUI.STATUS_DURATION_S:
            imgui.text_colored(imgui.ImVec4(0.35, 0.85, 0.35, 1.0),
                               tr("dialog.measurement.wertung_ok"))

    def _draw_confirm_wertung_dialog(self):
        """Bestätigungsdialog für das Überschreiben eines Wertungsergebnisses.

        Öffnet sich über den „Wertung"-Button, wenn `existing_scores > 0`:
        zeigt Vor-/Nachname, Stand, Uhrzeit und Durchgang und lässt den Nutzer
        bestätigen, dass das vorhandene Wertungsergebnis überschrieben wird.
        Erst die Bestätigung löst die Framebuffer-Kopie und den Upload aus.
        """
        ctrl = self.controller
        if not getattr(ctrl, "confirm_dialog_open", False):
            return
        snapshot = ctrl.confirm_meta or {}
        result = ctrl.lookup_result or {}
        participant = result.get("participant") or {}
        self._push_dialog_style()
        imgui.set_next_window_pos(workflow_dialog_center(imgui.get_main_viewport()),
                                  imgui.Cond_.once,
                                  imgui.ImVec2(0.5, 0.5))
        if imgui.begin(tr("dialog.wertung_confirm.title"),
                       flags=imgui.WindowFlags_.always_auto_resize):
            imgui.text(tr("dialog.wertung_confirm.info"))
            imgui.dummy(imgui.ImVec2(0, 4))
            name = (truncate_text(participant.get("last_name", "")) + ", "
                    + truncate_text(participant.get("first_name", "")))
            for label, value in (
                    (tr("dialog.wertung_confirm.name"), name),
                    (tr("dialog.wertung_confirm.dg"),
                     snapshot.get("dg", "?")),
                    (tr("dialog.wertung_confirm.stand"),
                     snapshot.get("stand", "?")),
                    (tr("dialog.wertung_confirm.zeit"),
                     snapshot.get("zeit", "?"))):
                imgui.text(f"{label}: {value}")
            imgui.dummy(imgui.ImVec2(0, 8))
            if imgui.button(tr("dialog.wertung_confirm.confirm")):
                ctrl.confirm_overwrite()
            imgui.same_line()
            if imgui.button(tr("dialog.wertung_confirm.cancel")):
                ctrl.cancel_overwrite()
            imgui.end()
        self._pop_dialog_style()

    def _manual_save(self, ctrl):
        """Manuelle Etikett-Werte speichern („Speichern"-Button und Enter)."""
        error = ctrl.manual_sticker(
            self._manual_buf["zeit"],
            self._manual_buf["stand"],
            self._manual_buf["dg"],
            self._manual_buf["sch_nr"])
        ctrl.manual_dialog_error = error

    def _draw_manual_sticker_dialog(self):
        """Manuelle Etikett-Eingabe: modaler Dialog mit vier Feldern.

        Wird über `ctrl.manual_dialog_open` gesteuert. Bei „Speichern" werden
        die Werte über `ctrl.manual_sticker` strikt validiert und wie nach
        einem erfolgreichen Scan übernommen; bei Validierungsfehler bleibt der
        Dialog offen und zeigt den Fehlerhinweis. „Schließen" verwirft die
        Eingabe ohne Übernahme. Tastatur-UX: Auto-Fokus im ersten Feld
        (`set_item_default_focus` + synthetisches Tab, siehe
        `_manual_autotab_state`), Tab wechselt über das standardmäßige
        basic Tabbing, Enter speichert (nur wenn kurz zuvor ein Feld
        aktiv war, siehe `_manual_field_active`), Escape schließt
        (App-Schicht `_on_key`)."""
        ctrl = self.controller
        if not getattr(ctrl, "manual_dialog_open", False):
            self._manual_field_active = {
                k: False for k in self._manual_field_active}
            return
        self._push_dialog_style()
        imgui.set_next_window_pos(workflow_dialog_center(imgui.get_main_viewport()),
                                  imgui.Cond_.once,
                                  imgui.ImVec2(0.5, 0.5))
        field_active = {}
        if imgui.begin(tr("dialog.measurement.manual_dialog"),
                       flags=imgui.WindowFlags_.always_auto_resize):
            # Auto-Fokus-Statusmaschine (synthetisches Tab): auf dem
            # Erscheinen-Frame legt sich der Nav-Fokus im ersten Feld
            # nieder; das Tab 2 Frames danach aktiviert die Texteingabe
            # dort (sichtbarer Cursor, `want_text_input` aktiv).
            if imgui.is_window_appearing():
                self._manual_autotab_state = "delay1"
            elif self._manual_autotab_state == "delay1":
                self._manual_autotab_state = "press"
            elif self._manual_autotab_state == "press":
                imgui.get_io().add_key_event(imgui.Key.tab, True)
                self._manual_autotab_state = "release"
            elif self._manual_autotab_state == "release":
                imgui.get_io().add_key_event(imgui.Key.tab, False)
                self._manual_autotab_state = None
            # Gemeinsames Alignment: alle Felder starten bei der Breite des
            # längsten Labels (Muster `_draw_config_rows`) und sind gleich
            # breit (inhalts-adaptiv, wachst mit Schriftgrößen-Präset).
            fields = (("dg", "dialog.measurement.manual_dg"),
                      ("sch_nr", "dialog.measurement.manual_sch_nr"),
                      ("stand", "dialog.measurement.manual_stand"),
                      ("zeit", "dialog.measurement.manual_zeit"))
            label_w = max(imgui.calc_text_size(tr(k)).x for _, k in fields)
            label_w += 16.0
            field_w = max(
                120.0,
                max(imgui.calc_text_size(self._manual_buf[k]).x
                    for k, _ in fields) + 24.0)
            for idx, (key, label_key) in enumerate(fields):
                imgui.text(tr(label_key))
                imgui.same_line()
                imgui.set_cursor_pos_x(label_w)
                imgui.set_next_item_width(field_w)
                _changed, value = imgui.input_text(
                    f"##manual_{key}", self._manual_buf[key],
                    imgui.InputTextFlags_.none)
                self._manual_buf[key] = value
                field_active[key] = imgui.is_item_active()
                if idx == 0:
                    # Default-Fokus: beim Erscheinen liegt der Nav-Fokus
                    # im ersten Feld (Texteingabe-Aktivierung siehe oben).
                    imgui.set_item_default_focus()
            # Enter speichert — nur wenn eines der Felder im vorherigen
            # Frame aktiv war (im Enter-Frame deaktiviert sich das
            # InputText selbst, `field_active` wäre hier sonst immer leer).
            # Auf per Tab fokussierten Buttons aktiviert Enter nativ den
            # Button; dort ist kein Feld aktiv, also kein Doppel-Trigger.
            if ctrl.manual_dialog_open and imgui.is_key_pressed(
                    imgui.Key.enter, repeat=False) and any(
                    self._manual_field_active.values()):
                self._manual_save(ctrl)
            if ctrl.manual_dialog_error:
                imgui.text_colored(imgui.ImVec4(1.0, 0.45, 0.45, 1.0),
                                   tr(ctrl.manual_dialog_error))
            imgui.dummy(imgui.ImVec2(0, 8))
            if imgui.button(tr("dialog.measurement.manual_save")):
                self._manual_save(ctrl)
            imgui.same_line()
            if imgui.button(tr("dialog.measurement.manual_close")):
                ctrl.close_manual_dialog()
            imgui.end()
        # ACTIVE-Status dieses Frames ist für den nächsten der
        # „Vorherige-Frame"-Status der Enter-Erkennung.
        self._manual_field_active = field_active if field_active else \
            {k: False for k in self._manual_field_active}
        self._pop_dialog_style()

    def _draw_result(self):
        ctrl = self.controller
        if ctrl.state is AppState.RESULT and ctrl.calibration is not None:
            cal = ctrl.calibration
            self._push_dialog_style()
            # Auto-Resize statt fester `_next_window_size`: wächst mit dem
            # Text, damit bei großen Schrift-Präseten (XLarge) nichts
            # abgeschnitten wird.
            position_workflow_dialog(ctrl.state)
            if imgui.begin(calibration_step_title(ctrl.state),
                           flags=imgui.WindowFlags_.always_auto_resize):
                quality = calibration_quality(cal.mean)
                qcolors = {
                    "good": (0.35, 0.85, 0.35, 1.0),
                    "ok": (0.95, 0.85, 0.25, 1.0),
                    "poor": (0.95, 0.60, 0.20, 1.0),
                    "bad": (0.95, 0.35, 0.35, 1.0),
                }
                imgui.text_colored(
                    imgui.ImVec4(*qcolors[quality]),
                    tr("dialog.result.avgvar", avg=f"{cal.mean:.0f}",
                       var=f"{cal.sd:.0f}"))
                imgui.text(tr("dialog.result.correction",
                              a=cal.A_correction, b=cal.B_correction))
                if quality in ("poor", "bad"):
                    imgui.text_colored(imgui.ImVec4(0.95, 0.60, 0.20, 1.0),
                                       tr("dialog.result.poor_accuracy"))
                imgui.dummy(imgui.ImVec2(0, 8))
                if imgui.button(tr("dialog.result.accept")):
                    ctrl.accept_calibration()
                imgui.same_line()
                if imgui.button(tr("dialog.result.cancel")):
                    ctrl.cancel_calibration()
                imgui.end()
            self._pop_dialog_style()
