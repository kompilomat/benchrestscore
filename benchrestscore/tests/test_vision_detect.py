# -*- coding: utf-8 -*-
"""Headless unit tests for the vision config/client/parser (no window/GL, no network)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np

from benchrestscore.vision_detect import (
    VisionConfig,
    VisionClient,
    VisionError,
    parse_vision_json,
    _normalize_coord,
    _downscale,
    _opencode_api_key,
    _parse_sticker_json,
    extract_sticker,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
)


class FakeTransport:
    """httpx.Transport-Fake: liefert vorgegebene Antworten, zählt Calls."""

    def __init__(self, responses, status=200):
        self.responses = list(responses)
        self.calls = 0
        self.status = status

    def handle_request(self, request):
        self.calls += 1
        if self.status != 200:
            from httpx import Response
            return Response(self.status, text="error",
                            request=request)
        body = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        from httpx import Response
        return Response(200, json={"choices": [
            {"message": {"content": body}}]}, request=request)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _cfg(**kw):
    defaults = dict(base_url="https://example.test/v1", api_key="k",
                    model="m/test")
    defaults.update(kw)
    return VisionConfig(**defaults)


def test_config_configured():
    assert _cfg().configured is True
    assert _cfg(base_url="").configured is False
    assert _cfg(model="").configured is False


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("BRS_VISION_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("BRS_VISION_MODEL", "env-model")
    monkeypatch.setenv("BRS_VISION_API_KEY", "env-key")
    cfg = VisionConfig.from_settings(data={"base_url": "https://file.test/v1",
                                           "model": "file-model",
                                           "api_key": "file-key"})
    assert cfg.base_url == "https://env.test/v1"
    assert cfg.model == "env-model"
    assert cfg.api_key == "env-key"


def test_config_from_settings_uses_vision_block(monkeypatch):
    monkeypatch.delenv("BRS_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("BRS_VISION_MODEL", raising=False)
    monkeypatch.delenv("BRS_VISION_API_KEY", raising=False)
    cfg = VisionConfig.from_settings(data={"base_url": "https://f.test/v1",
                                           "model": "fm", "api_key": "fk"})
    assert cfg.base_url == "https://f.test/v1"
    assert cfg.model == "fm"
    assert cfg.api_key == "fk"


def test_config_defaults_without_vision_block(monkeypatch, tmp_path):
    # Kein vision-Block in den Settings -> neutrale (leere) Defaults:
    # nicht konfiguriert, Gruppenerkennung fällt auf den CV-Pfad zurück.
    monkeypatch.delenv("BRS_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("BRS_VISION_MODEL", raising=False)
    monkeypatch.delenv("BRS_VISION_API_KEY", raising=False)
    monkeypatch.setattr("benchrestscore.vision_detect._opencode_api_key",
                        lambda *a, **k: "")
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    cfg = VisionConfig.from_settings(path=str(p))
    assert cfg.base_url == DEFAULT_BASE_URL == ""
    assert cfg.model == DEFAULT_MODEL == ""
    assert cfg.api_key == ""
    assert cfg.configured is False


def test_config_defaults_missing_settings_file(monkeypatch, tmp_path):
    # Fehlende Settings-Datei (Erststart) -> ebenfalls neutrale Defaults.
    monkeypatch.delenv("BRS_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("BRS_VISION_MODEL", raising=False)
    monkeypatch.delenv("BRS_VISION_API_KEY", raising=False)
    monkeypatch.setattr("benchrestscore.vision_detect._opencode_api_key",
                        lambda *a, **k: "")
    cfg = VisionConfig.from_settings(path=str(tmp_path / "fehlend.json"))
    assert cfg.configured is False
    assert cfg.base_url == ""


def test_config_default_api_key_from_opencode_config(monkeypatch, tmp_path):
    # Der API-Key-Fallback greift nur bei konfigurierter Base-URL: ohne
    # vision-Block mit per Env-Var getragener Base-URL wird der Key des
    # opencode-Providers übernommen, dessen baseURL passt.
    monkeypatch.setenv("BRS_VISION_BASE_URL", "https://gpu.test/v1")
    monkeypatch.setenv("BRS_VISION_MODEL", "gpu-test-model")
    monkeypatch.delenv("BRS_VISION_API_KEY", raising=False)
    cfg_file = tmp_path / "opencode.json"
    cfg_file.write_text(json.dumps({
        "provider": {
            "gpu": {"options": {
                "baseURL": "https://gpu.test/v1",
                "apiKey": "sk-test-abc",
            }},
            "other": {"options": {
                "baseURL": "https://anders.example/v1",
                "apiKey": "sk-falsch",
            }},
        }
    }), encoding="utf-8")
    key = _opencode_api_key("https://gpu.test/v1", [str(cfg_file)])
    assert key == "sk-test-abc"
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "benchrestscore.vision_detect._opencode_api_key",
        lambda base_url, config_paths=None: _opencode_api_key(
            base_url, [str(cfg_file)]))
    cfg = VisionConfig.from_settings(path=str(p))
    assert cfg.api_key == "sk-test-abc"
    assert cfg.configured is True


def test_config_no_api_key_fallback_without_base_url(monkeypatch, tmp_path):
    # Ohne konfigurierte Base-URL greift der opencode-Key-Fallback nicht
    # (neutrale Defaults -> nicht konfiguriert, kein Key-Zugriff).
    monkeypatch.delenv("BRS_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("BRS_VISION_MODEL", raising=False)
    monkeypatch.delenv("BRS_VISION_API_KEY", raising=False)

    def _boom(*a, **k):
        raise AssertionError("Key-Fallback darf ohne Base-URL nicht ziehen")

    monkeypatch.setattr("benchrestscore.vision_detect._opencode_api_key",
                        _boom)
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    cfg = VisionConfig.from_settings(path=str(p))
    assert cfg.api_key == ""
    assert cfg.configured is False


def test_config_explicit_empty_disables_vision(monkeypatch):
    # Explizit leere Werte im vision-Block = Vision aus (reiner CV-Pfad).
    monkeypatch.delenv("BRS_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("BRS_VISION_MODEL", raising=False)
    monkeypatch.delenv("BRS_VISION_API_KEY", raising=False)
    cfg = VisionConfig.from_settings(data={"base_url": "", "model": "",
                                           "api_key": ""})
    assert cfg.configured is False
    cfg = VisionConfig.from_settings(data={"base_url": "https://f.test/v1",
                                           "model": "", "api_key": ""})
    assert cfg.configured is False


def test_config_env_override_beats_defaults(monkeypatch, tmp_path):
    # Env-Override schlägt die Defaults (kein vision-Block).
    monkeypatch.setenv("BRS_VISION_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("BRS_VISION_MODEL", "env-model")
    monkeypatch.delenv("BRS_VISION_API_KEY", raising=False)
    monkeypatch.setattr("benchrestscore.vision_detect._opencode_api_key",
                        lambda *a, **k: "")
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    cfg = VisionConfig.from_settings(path=str(p))
    assert cfg.base_url == "https://env.test/v1"
    assert cfg.model == "env-model"
    assert cfg.configured is True


def test_parse_holes_schema():
    raw = '{"holes":[{"x":123,"y":456}]}'
    pts = parse_vision_json(raw, 1000, 1000)
    assert pts == [(123.0, 456.0)]


def test_parse_bbox_schema():
    raw = '[{"bbox_2d":[100,200,300,400]}]'
    pts = parse_vision_json(raw, 1000, 1000)
    assert len(pts) == 1
    assert abs(pts[0][0] - 200.0) < 1e-9
    assert abs(pts[0][1] - 300.0) < 1e-9


def test_parse_duplicate_xy_keys_split_into_points():
    # Modell-Stottern: zwei (x,y)-Paare in einem Objekt (doppelte Keys) ->
    # je Paar ein Punkt, kein verlorenes Loch.
    raw = '```json\n{"holes": [{"x": 100, "y": 100, "x": 500, "y": 500}]}\n```'
    pts = parse_vision_json(raw, 1000, 1000)
    assert pts == [(100.0, 100.0), (500.0, 500.0)]


def test_parse_duplicate_xy_keys_top_level_list():
    # Gleiche Aufteilung bei Top-Level-Liste ohne "holes"-Wrapper.
    raw = '[{"x": 10, "y": 20, "x": 30, "y": 40}, {"x": 500, "y": 500}]'
    pts = parse_vision_json(raw, 1000, 1000)
    assert pts == [(10.0, 20.0), (30.0, 40.0), (500.0, 500.0)]


def test_parse_fenced_json():
    raw = '```json\n{"holes":[{"x":50,"y":60}]}\n```'
    pts = parse_vision_json(raw, 1000, 1000)
    assert pts == [(50.0, 60.0)]


def test_parse_normalizes_pixel_scale():
    # Werte >1000 werden als Pixel der gesendeten Skala interpretiert.
    # (Werte <=1000 sind bereits 0-1000-normalisiert und bleiben unverändert.)
    pts = parse_vision_json('{"holes":[{"x":1280,"y":960}]}', 1280, 960)
    assert len(pts) == 1
    assert abs(pts[0][0] - 1000.0) < 1e-9
    assert abs(pts[0][1] - 960.0) < 1e-9
    pts2 = parse_vision_json('{"holes":[{"x":640,"y":480}]}', 1280, 960)
    assert pts2 == [(640.0, 480.0)]


def test_parse_normalizes_fraction_scale():
    pts = parse_vision_json('{"holes":[{"x":0.25,"y":0.5}]}', 1000, 1000)
    assert pts == [(250.0, 500.0)]


def test_parse_invalid_and_empty():
    assert parse_vision_json("not json", 1000, 1000) == []
    assert parse_vision_json("", 1000, 1000) == []
    assert parse_vision_json('{"holes":[]}', 1000, 1000) == []


def test_parse_out_of_range_dropped():
    pts = parse_vision_json('{"holes":[{"x":1500,"y":500}]}', 1000, 1000)
    assert pts == []


def test_normalize_coord():
    assert _normalize_coord(0.5, 1000) == 500.0
    assert _normalize_coord(500, 1000) == 500.0
    assert _normalize_coord(500, 0) == 500.0


def test_downscale_identity_and_shrink():
    frame = np.zeros((720, 1280, 3), np.uint8)
    img, sw, sh = _downscale(frame, max_side=1280)
    assert (sw, sh) == (1280, 720)
    img2, sw2, sh2 = _downscale(frame, max_side=640)
    assert (sw2, sh2) == (640, 360)


def test_client_payload_and_endpoint():
    cfg = _cfg(base_url="https://example.test/v1", model="m/test")
    transport = FakeTransport(['{"holes":[]}'])
    client = VisionClient(cfg, transport=transport)
    frame = np.zeros((720, 1280, 3), np.uint8)
    client.detect(frame)
    assert transport.calls == 1


def test_client_retry_on_empty():
    cfg = _cfg()
    transport = FakeTransport(["", '{"holes":[]}'])
    client = VisionClient(cfg, transport=transport)
    frame = np.zeros((100, 100, 3), np.uint8)
    raw = client.detect(frame)
    assert raw == '{"holes":[]}'
    assert transport.calls == 2


def test_client_raises_after_all_empty():
    cfg = _cfg()
    transport = FakeTransport(["", ""])
    client = VisionClient(cfg, transport=transport)
    frame = np.zeros((100, 100, 3), np.uint8)
    try:
        client.detect(frame)
        assert False, "expected VisionError"
    except VisionError as e:
        assert e.code == "empty_response"


def _frame(h=720, w=1280):
    return np.zeros((h, w, 3), np.uint8)


def test_parse_sticker_json_valid():
    raw = '{"zeit":"09:15","stand":8,"dg":1,"sch_nr":6}'
    out = _parse_sticker_json(raw)
    assert out == {"zeit": "09:15", "stand": 8, "dg": 1, "sch_nr": 6}
    assert isinstance(out["stand"], int)


def test_parse_sticker_json_fenced():
    raw = '```json\n{"zeit":"09:15","stand":8,"dg":1,"sch_nr":6}\n```'
    assert _parse_sticker_json(raw)["zeit"] == "09:15"


def test_parse_sticker_json_numeric_strings_convert():
    # Der Parser soll Werte, die als Strings kommen, konvertieren (int()).
    raw = '{"zeit":"09:15","stand":"8","dg":"1","sch_nr":"6"}'
    out = _parse_sticker_json(raw)
    assert out == {"zeit": "09:15", "stand": 8, "dg": 1, "sch_nr": 6}


def test_parse_sticker_json_empty_raises():
    for raw in ("", "   ", "```json\n```"):
        try:
            _parse_sticker_json(raw)
            assert False, f"expected VisionError for {raw!r}"
        except VisionError as e:
            assert e.code == "empty_response"


def test_parse_sticker_json_invalid_raises():
    for raw in ("not json", "[1,2,3]", '{"zeit":"09:15"}'):
        try:
            _parse_sticker_json(raw)
            assert False, f"expected VisionError for {raw!r}"
        except VisionError as e:
            assert e.code == "invalid_response"


def test_extract_sticker_ok():
    cfg = _cfg()
    transport = FakeTransport(
        ['{"zeit":"09:15","stand":8,"dg":1,"sch_nr":6}'])
    out = extract_sticker(_frame(), config=cfg, transport=transport)
    assert out == {"zeit": "09:15", "stand": 8, "dg": 1, "sch_nr": 6}
    assert transport.calls == 1


def test_extract_sticker_retry_then_ok():
    cfg = _cfg()
    transport = FakeTransport(
        ["", '{"zeit":"09:15","stand":8,"dg":1,"sch_nr":6}'])
    out = extract_sticker(_frame(), config=cfg, transport=transport)
    assert out["dg"] == 1
    assert transport.calls == 2


def test_extract_sticker_empty_raises():
    cfg = _cfg()
    transport = FakeTransport(["", ""])
    try:
        extract_sticker(_frame(), config=cfg, transport=transport)
        assert False, "expected VisionError"
    except VisionError as e:
        assert e.code == "empty_response"


def test_extract_sticker_not_configured_raises():
    cfg = _cfg(base_url="", model="")
    try:
        extract_sticker(_frame(), config=cfg, transport=FakeTransport([]))
        assert False, "expected VisionError"
    except VisionError as e:
        assert e.code == "not_configured"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            traceback.print_exc()
            raise