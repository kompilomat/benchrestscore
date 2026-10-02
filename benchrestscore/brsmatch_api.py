# -*- coding: utf-8 -*-
"""HTTP-Client für die BRSMatch-Veranstaltungs-API (Lookup + Scoring).

Reine, headless testbare Kernlogik (analog `vision_detect.py`): Der Client
spricht die Veranstaltungs-API von BRSMatch an — `GET /{event_id}/api/lookup`
(Query-API) und `POST /{event_id}/api/measurements` (Scoring-API) — jeweils
mit `Authorization: Bearer <token>`. Die Etikett-Werte (sch_nr, dg, stand,
zeit) einer Scheibe werden serverseitig in Teilnehmer/Disziplin/Durchgang
 aufgelöst; die Query-Antwort liefert zusätzlich die Anzahl bereits
 vorhandener Wertungen (`existing_scores`). Fehler werden als `BrsmatchError`
 mit `kind` gehoben; der HTTP-Transport ist injizierbar (Tests ohne Netz).
 Der Zeit-Wert (`zeit`) wird vor jedem Call clientseitig auf null-gestütztes
 `HH:MM` kanonisiert (der Server vergleicht exakt); ungültige Werte werfen
 `BrsmatchError("validation", …)`.
 """

import httpx
import numpy as np

# Timeout der Query-API (ein einzelner Server-Call).
LOOKUP_TIMEOUT_S = 10.0
# Timeout der Scoring-API (inkl. Screenshot-Upload).
SUBMIT_TIMEOUT_S = 30.0
# Ziel-Auflösung des hochgeladenen Screenshots.
SCREENSHOT_WIDTH = 1280
SCREENSHOT_HEIGHT = 720
# JPEG-Qualität des hochgeladenen Screenshots.
SCREENSHOT_JPEG_QUALITY = 90


class BrsmatchError(Exception):
    """Fehler beim BRSMatch-API-Call.

    `kind` klassifiziert den Fehler (i18n-Mapping im Controller):
    ``not_configured`` | ``auth`` | ``no_belegung`` | ``mismatch`` |
    ``validation`` | ``http`` | ``network``.
    """

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind
        self.message = message


class LookupResult(object):
    """Ergebnis der Query-API-Auflösung."""

    def __init__(self, participant, discipline, match_index, existing_scores):
        self.participant = participant
        self.discipline = discipline
        self.match_index = match_index
        self.existing_scores = existing_scores

    def to_dict(self):
        return {
            "participant": dict(self.participant),
            "discipline": dict(self.discipline),
            "match_index": self.match_index,
            "existing_scores": self.existing_scores,
        }


def _event_id(config):
    """Event-ID aus der Config lesen; None bei fehlender/ungültiger Ganzzahl."""
    value = config.get("event_id", 0)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
    return None


def encode_screenshot(img, width=SCREENSHOT_WIDTH, height=SCREENSHOT_HEIGHT,
                      quality=SCREENSHOT_JPEG_QUALITY):
    """BGR-Bild auf (width, height) skalieren und als JPEG-Bytes encodieren.

    Erhält das Seitenverhältnis des Quellbilds: das Bild wird passend
    skaliert und bei abweichendem Seitenverhältnis zentriert auf eine
    schwarze Leinwand mit (width, height) gesetzt (Letterboxing). Reine
    Funktion (headless testbar); skaliert mit kantengetreuer Interpolation
    (`cv2.INTER_LANCZOS4`), damit UI-Text und Marker-Linien beim
    Downscaling scharf bleiben. `quality` ist die JPEG-Qualität (1–100).
    """
    import cv2

    if img is None:
        raise ValueError("kein Bild zum Encodieren")
    ih, iw = img.shape[:2]
    if iw <= 0 or ih <= 0:
        raise ValueError("ungültige Bildabmessungen")
    canvas = np.zeros((height, width, 3), dtype=img.dtype)
    scale = min(width / iw, height / ih)
    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    x0 = (width - nw) // 2
    y0 = (height - nh) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = resized
    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise ValueError("JPEG-Encoding fehlgeschlagen")
    return buf.tobytes()


def _endpoint_url(base_url, event_id, path):
    return f"{base_url.rstrip('/')}/{int(event_id)}/api/{path}"


def _configured(config):
    """Konfiguration prüfen; wirft `BrsmatchError("not_configured", …)`."""
    base = (config.get("base_url") or "").strip()
    key = (config.get("api_key") or "").strip()
    event_id = _event_id(config)
    if not base or not key or event_id is None:
        raise BrsmatchError("not_configured", "brsmatch API not configured")
    return base, key, event_id


def _canonical_zeit(zeit):
    """Etikett-Zeit auf null-gestütztes ``HH:MM`` kanonisieren.

    Die BRSMatch-API vergleicht ``zeit`` exakt gegen die abgelegte
    (immer null-gestützte) Startzeit; Werte mit einstelliger Stunde
    (``9:05``) werden daher auf ``09:05`` gebracht. Reine Funktion
    (headless testbar). Wirft ``ValueError`` für nicht interpretierbare
    Werte (kein ``H:MM``, Stunden- > 23, Minuten- > 59-Wert); defensiv, da
    manuelle Eingabe und VLM-Scan das ``STICKER_SCHEMA``-Muster durchlaufen.
    """
    parts = str(zeit).strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError("ungültiger Zeit-Wert: %r" % (zeit,))
    hour, minute = int(parts[0]), int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("ungültiger Zeit-Wert: %r" % (zeit,))
    return f"{hour:02d}:{minute:02d}"


def lookup(config, sch_nr, dg, stand, zeit, transport=None):
    """Query-API: Etikett-Werte in Teilnehmer/Disziplin/Durchgang auflösen.

    `config` ist ein Dict mit ``base_url``/``api_key``/``event_id`` (Muster von
    ``AppController.get_brsmatch_config``). Liefert ein ``LookupResult`` mit
    ``existing_scores`` (Integer; fehlt das Server-Feld, gilt 0). Der
    Zeit-Wert wird vor dem Call auf null-gestütztes ``HH:MM`` kanonisiert
    (``9:05`` → ``09:05``), da der Server exakt vergleicht; ein nicht
    interpretierbarer Wert wirft ``validation``. Fehler: ``BrsmatchError``
    mit ``kind`` (``not_configured``/``validation``/``auth``/
    ``no_belegung``/``mismatch``/``http``/``network``).
    """
    base, key, event_id = _configured(config)
    try:
        zeit = _canonical_zeit(zeit)
    except ValueError as exc:
        raise BrsmatchError("validation", str(exc))
    params = {
        "sch_nr": str(int(sch_nr)),
        "dg": str(int(dg)),
        "stand": str(int(stand)),
        "zeit": zeit,
    }
    headers = {"Authorization": "Bearer " + key}
    url = _endpoint_url(base, event_id, "lookup")
    try:
        with httpx.Client(timeout=LOOKUP_TIMEOUT_S,
                          transport=transport) as client:
            resp = client.get(url, params=params, headers=headers)
    except Exception as exc:  # noqa: BLE001 — Netzfehler klassifiziert
        raise BrsmatchError("network", str(exc))
    return _parse_lookup_response(resp)


def _parse_lookup_response(resp):
    """Antwort der Query-API defensiv parsen → `LookupResult`."""
    if resp.status_code == 401:
        raise BrsmatchError("auth", "unauthorized")
    if resp.status_code == 404:
        raise BrsmatchError("no_belegung", "no belegung for (stand, zeit)")
    if resp.status_code == 409:
        raise BrsmatchError("mismatch", "label does not match belegung")
    if resp.status_code != 200:
        raise BrsmatchError("http", f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise BrsmatchError("http", "invalid JSON response")
    try:
        participant = data["participant"]
        discipline = data["discipline"]
        match_index = int(data["match_index"])
    except (KeyError, TypeError, ValueError):
        raise BrsmatchError("http", "unexpected response shape")
    existing = data.get("existing_scores", 0)
    if isinstance(existing, bool) or not isinstance(existing, int):
        existing = 0
    return LookupResult(
        participant=participant,
        discipline=discipline,
        match_index=match_index,
        existing_scores=max(0, int(existing)),
    )


def submit_measurement(config, sch_nr, dg, stand, zeit, group_mm,
                       screenshot_img=None, apply_penalty=False,
                       transport=None):
    """Scoring-API: Messung samt optionalem Screenshot übermitteln.

    Multipart-Form mit ``sch_nr``, ``dg``, ``stand``, ``zeit``, ``group_mm``,
    ``apply_penalty`` und optional ``screenshot`` (JPEG-Bytes, Content-Type
    ``image/jpeg``). Der Zeit-Wert
    wird vor dem Call auf null-gestütztes ``HH:MM`` kanonisiert (``9:05`` →
    ``09:05``), da der Server exakt vergleicht; ein nicht interpretierbarer
    Wert wirft ``validation`` ohne HTTP-Call. Liefert die Messungs-JSON der
    Antwort. Fehler: ``BrsmatchError`` mit ``kind``
    (``validation``/``no_belegung``/``mismatch``/``auth``/``http``/
    ``network``).
    """
    base, key, event_id = _configured(config)
    try:
        zeit = _canonical_zeit(zeit)
    except ValueError as exc:
        raise BrsmatchError("validation", str(exc))
    data = {
        "sch_nr": str(int(sch_nr)),
        "dg": str(int(dg)),
        "stand": str(int(stand)),
        "zeit": zeit,
        "group_mm": f"{float(group_mm):g}",
        "apply_penalty": str(bool(apply_penalty)),
    }
    files = {}
    if screenshot_img is not None:
        files["screenshot"] = ("wertung.jpg", screenshot_img, "image/jpeg")
    headers = {"Authorization": "Bearer " + key}
    url = _endpoint_url(base, event_id, "measurements")
    try:
        with httpx.Client(timeout=SUBMIT_TIMEOUT_S,
                          transport=transport) as client:
            resp = client.post(url, data=data, files=files,
                               headers=headers)
    except Exception as exc:  # noqa: BLE001 — Netzfehler klassifiziert
        raise BrsmatchError("network", str(exc))
    return _parse_submit_response(resp)


def _parse_submit_response(resp):
    """Antwort der Scoring-API defensiv parsen → Messungs-JSON."""
    if resp.status_code == 401:
        raise BrsmatchError("auth", "unauthorized")
    if resp.status_code == 400:
        raise BrsmatchError("validation", resp.text or "invalid measurement")
    if resp.status_code == 404:
        raise BrsmatchError("no_belegung", "no belegung for (stand, zeit)")
    if resp.status_code == 409:
        raise BrsmatchError("mismatch", "label does not match belegung")
    if resp.status_code != 201:
        raise BrsmatchError("http", f"HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        raise BrsmatchError("http", "invalid JSON response")