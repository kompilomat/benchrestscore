# -*- coding: utf-8 -*-
"""Headless unit tests for the BRSMatch API client (no window, no network)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import pytest

import numpy as np

from benchrestscore.brsmatch_api import (
    BrsmatchError,
    LookupResult,
    lookup,
    submit_measurement,
    encode_screenshot,
    SCREENSHOT_WIDTH,
    SCREENSHOT_HEIGHT,
    _event_id,
    _canonical_zeit,
)


def _config(**kw):
    defaults = dict(base_url="http://brs.test", api_key="secret",
                    event_id=7)
    defaults.update(kw)
    return defaults


class FakeTransport:
    """httpx.Transport-Fake: liefert vorgegebene Antworten, zeichnet Calls auf."""

    def __init__(self, responses, status=200):
        self.responses = list(responses)
        self.calls = 0
        self.requests = []

    def handle_request(self, request):
        from httpx import Response
        self.calls += 1
        self.requests.append(request)
        body = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(body, tuple):
            status, payload = body
            return Response(status, json=payload, request=request)
        if isinstance(body, int):
            return Response(body, text="error", request=request)
        return Response(200, json=body, request=request)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


LOOKUP_OK = {
    "participant": {
        "start_number": 12,
        "first_name": "Hans",
        "last_name": "Müller",
        "club": "SV Test",
        "caliber": ".243/6 mm",
    },
    "discipline": {
        "id": 3,
        "class_name": "100 m HV",
        "distance_m": 100,
        "matches": 10,
        "shots_per_match": 5,
    },
    "match_index": 2,
    "existing_scores": 0,
}


def test_lookup_success():
    transport = FakeTransport([LOOKUP_OK])
    result = lookup(_config(), 12, 2, 4, "09:15", transport=transport)
    assert isinstance(result, LookupResult)
    assert result.participant["last_name"] == "Müller"
    assert result.existing_scores == 0
    req = transport.requests[0]
    assert req.method == "GET"
    assert req.url.path == "/7/api/lookup"
    assert req.headers["authorization"] == "Bearer secret"
    assert "sch_nr=12" in str(req.url)
    assert "dg=2" in str(req.url)
    assert "stand=4" in str(req.url)
    assert "zeit=09%3A15" in str(req.url) or "zeit=09:15" in str(req.url)


def test_lookup_existing_scores_missing_defaults_zero():
    data = dict(LOOKUP_OK)
    data.pop("existing_scores")
    result = lookup(_config(), 12, 2, 4, "09:15",
                    transport=FakeTransport([data]))
    assert result.existing_scores == 0


def test_lookup_existing_scores_kept():
    data = dict(LOOKUP_OK, existing_scores=3)
    result = lookup(_config(), 12, 2, 4, "09:15",
                    transport=FakeTransport([data]))
    assert result.existing_scores == 3


@pytest.mark.parametrize("status,kind", [
    (401, "auth"),
    (404, "no_belegung"),
    (409, "mismatch"),
    (500, "http"),
])
def test_lookup_http_errors(status, kind):
    with pytest.raises(BrsmatchError) as exc:
        lookup(_config(), 12, 2, 4, "09:15",
               transport=FakeTransport([status]))
    assert exc.value.kind == kind


def test_lookup_network_error():
    class Boom:
        def handle_request(self, request):
            raise OSError("refused")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with pytest.raises(BrsmatchError) as exc:
        lookup(_config(), 12, 2, 4, "09:15", transport=Boom())
    assert exc.value.kind == "network"


def test_lookup_not_configured():
    with pytest.raises(BrsmatchError) as exc:
        lookup(_config(base_url=""), 12, 2, 4, "09:15")
    assert exc.value.kind == "not_configured"
    with pytest.raises(BrsmatchError) as exc:
        lookup(_config(event_id=0), 12, 2, 4, "09:15")
    assert exc.value.kind == "not_configured"


def test_submit_success_multipart():
    transport = FakeTransport([(201, {
        "id": 42, "event_id": 7, "discipline_id": 3, "participant_id": 9,
        "match_index": 2, "group_mm": 12.34, "source": "api",
    })])
    result = submit_measurement(_config(), 12, 2, 4, "09:15", 12.34,
                                screenshot_img=b"\xff\xd8\xff\xe0" + b"0" * 16,
                                transport=transport)
    assert result["id"] == 42
    req = transport.requests[0]
    assert req.method == "POST"
    assert req.url.path == "/7/api/measurements"
    body = req.read()
    assert b"wertung.jpg" in body
    assert b"\xff\xd8" in body
    assert b"group_mm" in body
    assert b"sch_nr" in body
    assert b"apply_penalty" in body


def test_submit_without_screenshot():
    transport = FakeTransport([(201, {
        "id": 1, "event_id": 7, "discipline_id": 3, "participant_id": 9,
        "match_index": 1, "group_mm": 5.0, "source": "api",
    })])
    result = submit_measurement(_config(), 12, 1, 4, "09:15", 5.0,
                                transport=transport)
    assert result["id"] == 1
    assert b"screenshot" not in transport.requests[0].read()


@pytest.mark.parametrize("status,kind", [
    (400, "validation"),
    (401, "auth"),
    (404, "no_belegung"),
    (409, "mismatch"),
    (500, "http"),
])
def test_submit_http_errors(status, kind):
    with pytest.raises(BrsmatchError) as exc:
        submit_measurement(_config(), 12, 2, 4, "09:15", 1.0,
                           transport=FakeTransport([status]))
    assert exc.value.kind == kind


def test_canonical_zeit_normalization():
    assert _canonical_zeit("9:05") == "09:05"
    assert _canonical_zeit("09:15") == "09:15"
    assert _canonical_zeit("19:00") == "19:00"
    assert _canonical_zeit("23:59") == "23:59"
    assert _canonical_zeit("0:00") == "00:00"


@pytest.mark.parametrize("bad", ["9:75", "24:00", "abc", "9",
                                 "09:15:00", ""])
def test_canonical_zeit_rejects_invalid(bad):
    with pytest.raises(ValueError):
        _canonical_zeit(bad)


def test_lookup_canonicalizes_zeit():
    transport = FakeTransport([LOOKUP_OK])
    lookup(_config(), 12, 2, 4, "9:05", transport=transport)
    url = str(transport.requests[0].url)
    assert "zeit=09%3A05" in url or "zeit=09:05" in url


def test_submit_canonicalizes_zeit():
    transport = FakeTransport([(201, {
        "id": 1, "event_id": 7, "discipline_id": 3, "participant_id": 9,
        "match_index": 1, "group_mm": 5.0, "source": "api",
    })])
    submit_measurement(_config(), 12, 1, 4, "9:05", 5.0, transport=transport)
    # Ohne Screenshot encodiert httpx die Form URL-encoded; mit Screenshot
    # ist der Body multipart (Wert als rohe Zeile) — beide decken wir ab.
    body = transport.requests[0].read()
    assert b"zeit=09%3A05" in body or b"09:05" in body


def test_lookup_rejects_invalid_zeit():
    transport = FakeTransport([LOOKUP_OK])
    with pytest.raises(BrsmatchError) as exc:
        lookup(_config(), 12, 2, 4, "9:75", transport=transport)
    assert exc.value.kind == "validation"
    assert transport.calls == 0


def test_submit_rejects_invalid_zeit():
    transport = FakeTransport([(201, {
        "id": 1, "event_id": 7, "discipline_id": 3, "participant_id": 9,
        "match_index": 1, "group_mm": 5.0, "source": "api",
    })])
    with pytest.raises(BrsmatchError) as exc:
        submit_measurement(_config(), 12, 1, 4, "9:75", 5.0,
                           transport=transport)
    assert exc.value.kind == "validation"
    assert transport.calls == 0


def test_event_id_parsing():
    assert _event_id({"event_id": 7}) == 7
    assert _event_id({"event_id": "7"}) == 7
    assert _event_id({"event_id": 0}) is None
    assert _event_id({"event_id": -1}) is None
    assert _event_id({"event_id": "abc"}) is None
    assert _event_id({"event_id": True}) is None
    assert _event_id({"event_id": None}) is None
    assert _event_id({}) is None


def test_encode_screenshot_scales_to_720p():
    img = np.zeros((2160, 3840, 3), dtype=np.uint8)
    img[:, :, 0] = 255
    jpg = encode_screenshot(img)
    assert jpg[:2] == b"\xff\xd8"
    import cv2
    decoded = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (SCREENSHOT_HEIGHT, SCREENSHOT_WIDTH, 3)
    # JPEG ist verlustbehaftet: leichte Abweichung vom Originalwert erlaubt.
    assert abs(int(decoded[0, 0, 0]) - 255) <= 4


def test_encode_screenshot_letterboxes_non_16x9():
    """Abweichendes Seitenverhältnis wird zentriert mit schwarzen Balken gefüllt."""
    import cv2
    # 4:3-Quelle (z.B. 1280x960) in 16:9-Leinwand -> links/rechts Balken.
    # JPEG ist verlustbehaftet: Grenzwerte mit Toleranz (DCT-Ringing an der
    # Balken/Bild-Grenze).
    img = np.full((960, 1280, 3), 77, dtype=np.uint8)
    jpg = encode_screenshot(img)
    decoded = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (SCREENSHOT_HEIGHT, SCREENSHOT_WIDTH, 3)
    # Schwarze Balken links und rechts (ca. 0), Bild mittig (ca. 77).
    assert int(decoded[0, 0, 0]) <= 4
    assert int(decoded[0, SCREENSHOT_WIDTH - 1, 0]) <= 4
    assert abs(int(decoded[SCREENSHOT_HEIGHT // 2, SCREENSHOT_WIDTH // 2, 0]) - 77) <= 4
    # Die Bildzeile selbst ist unverzerrt: Quelle 1280x960 skaliert auf
    # 960x720 (scale = 720/960 = 0.75) -> 960 breit, zentriert bei x=(1280-960)/2.
    row = decoded[SCREENSHOT_HEIGHT // 2]
    nonzero = np.where(row[:, 0] > 20)[0]
    x0 = (SCREENSHOT_WIDTH - 960) // 2
    assert abs(int(nonzero[0]) - x0) <= 3
    assert abs(int(nonzero[-1]) - (x0 + 959)) <= 3