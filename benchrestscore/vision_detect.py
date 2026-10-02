# -*- coding: utf-8 -*-
"""OpenAI-kompatibler Vision-Client für die Anwendung.

Stellt die Konfiguration (`VisionConfig`) und den HTTP-Client (`VisionClient`)
für einen multimodalen Endpunkt bereit (OpenAI-kompatibel: z.B. Ollama,
vLLM, LM Studio). Der Client sendet ein Bild (base64-JPEG) mit
einem kurzen Prompt an `POST {base_url}/chat/completions` und liefert die rohe
Antwort; der defensive Parser (`parse_vision_json`) extrahiert normalisierte
0–1000-Koordinaten. Konfiguration kommt aus `settings.json` (`vision`-Block)
mit Env-Override und einem Key-Default aus der opencode-Konfiguration.

Reine, headless testbare Kernlogik (analog `automation.py`); Controller/UI
halten Zustand und Anzeige. Der HTTP-Client ist injizierbar (Tests ohne Netz).
"""

import base64
import json
import os
import re

import cv2
import numpy as np

try:
    from .settings import load as settings_load
except ImportError:
    from settings import load as settings_load

import httpx


# --- Konstanten ---

# Maximale Bildseite beim Senden an den Endpunkt (VLM-Größenbereich).
SEND_MAX_SIDE = 1280
# Timeout eines einzelnen HTTP-Calls. VLMs brauchen mehrere Sekunden bis > 30 s
# pro Bild (lokale kompakte Modelle ~30 s; größere Modelle bis 56 s) — 30 s
# wären zu eng, der UI-Thread wartet mit Busy-Anzeige.
REQUEST_TIMEOUT_S = 120.0
# Anzahl erneuter Versuche bei leerer/ungültiger Antwort oder HTTP-Fehler.
MAX_RETRIES = 1
# Generöses Token-Budget: reasoning-lastige Modelle „denken" mehrere hundert
# Tokens, bevor sie das JSON emittieren.
MAX_TOKENS = 2048
# Kurzer, bewährter Prompt: explizit normalisierte 0–1000-Koordinaten. Lange
# Prompts triggern bei Reasoning-Modellen leere Antworten (Thinking-Budget).
DETECT_PROMPT = (
    "Return hole centers as x and y normalized to 0-1000.\n"
    'Answer ONLY JSON: {"holes":[{"x":0-1000,"y":0-1000}]}.'
)

# Neutrale Defaults: leer. Ohne `vision`-Block (und ohne Env-Override) gilt
# die Vision-Erkennung damit als nicht konfiguriert (`configured=False`) und
# die Gruppenerkennung nutzt den reinen CV-Pfad. Ein getragener Endpunkt ist
# OpenAI-kompatibel (Base-URL + Modell in den Settings oder per
# `BRS_VISION_*`-Umgebungsvariablen); der API-Key wird dort oder — bei
# per Env-Var gesetzter Base-URL ohne Block — zur Laufzeit aus der
# opencode-Konfiguration gelesen (`_opencode_api_key`) und niemals im
# Code/Repo abgelegt.
DEFAULT_BASE_URL = ""
DEFAULT_MODEL = ""

# --- Etikett-Scan (BRSMatch) ---

# Schlichter, bewährter Prompt (ohne Layout-Erklärung — die triggert bei
# einigen Reasoning-Modellen leere Antworten). Die Typen erzwingt
# `response_format`.
STICKER_PROMPT = "Read the white sticker on the target. Extract the fields."

# JSON-Schema für die Etikett-Werte: `zeit` als Uhrzeit-String (HH:MM),
# `stand`/`dg`/`sch_nr` als Ganzzahlen. Der Endpunkt (vLLM) unterstützt
# `response_format` mit `json_schema` (guided decoding).
STICKER_SCHEMA = {
    "type": "object",
    "properties": {
        "zeit": {"type": "string",
                 "pattern": "^([01]?[0-9]|2[0-3]):[0-5][0-9]$"},
        "stand": {"type": "integer"},
        "dg": {"type": "integer"},
        "sch_nr": {"type": "integer"},
    },
    "required": ["zeit", "stand", "dg", "sch_nr"],
    "additionalProperties": False,
}


class VisionError(Exception):
    """Fehler beim Vision-Call (Netz, HTTP, leere/ungültige Antwort)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _opencode_config_paths():
    """Kandidaten-Pfade der opencode-Konfiguration (User + Projekt)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.expanduser("~/.config/opencode/opencode.json"),
        os.path.expanduser("~/.config/opencode/opencode.jsonc"),
        os.path.join(here, ".opencode", "opencode.json"),
        os.path.join(here, ".opencode", "opencode.jsonc"),
    ]
    return [p for p in candidates if os.path.exists(p)]


def _opencode_api_key(base_url, config_paths=None):
    """API-Key aus der opencode-Konfiguration übernehmen (Komfort-Fallback).

    Genutzt wird der Key des opencode-Providers, dessen `baseURL` zur
    konfigurierten Vision-Base-URL passt — der Fallback greift daher nur bei
    konfigurierter Base-URL. Der Key wird dadurch NICHT im Repo abgelegt;
    der Nutzer pflegt ihn in der opencode-Config oder über die Config-Maske
    (Settings). `config_paths` ist injizierbar (Tests); Default sind die
    üblichen opencode-Pfade (User + Projekt).
    """
    paths = config_paths if config_paths is not None \
        else _opencode_config_paths()
    base = (base_url or "").rstrip("/")
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            continue
        providers = cfg.get("provider") or {}
        for prov in providers.values():
            opts = prov.get("options") or {}
            key = (opts.get("apiKey") or "").strip()
            url = (opts.get("baseURL") or "").strip().rstrip("/")
            if key and url and url == base:
                return key
    return ""


class VisionConfig(object):
    """Konfiguration des OpenAI-kompatiblen Vision-Endpunkts.

    base_url   Base-URL des Endpunkts (z.B. `https://example.org/v1`).
    api_key    API-Key (bei per Env-Var gesetzter Base-URL ohne Block:
               Default aus der opencode-Konfiguration).
    model      Modell-Name des Endpunkts.

    Quelle: `settings.json` (`vision`-Block) mit Env-Override
    (`BRS_VISION_BASE_URL`/`BRS_VISION_API_KEY`/`BRS_VISION_MODEL`).
    Die Defaults sind leer: ohne (oder mit leerem) `vision`-Block ist die
    Vision-Erkennung nicht konfiguriert (`configured=False`).
    """

    __slots__ = ("base_url", "api_key", "model")

    ENV = {
        "base_url": "BRS_VISION_BASE_URL",
        "api_key": "BRS_VISION_API_KEY",
        "model": "BRS_VISION_MODEL",
    }

    def __init__(self, base_url="", api_key="", model=""):
        self.base_url = (base_url or "").strip()
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()

    @classmethod
    def from_settings(cls, path=None, data=None):
        """Config aus Settings laden (Env-Override hat Vorrang).

        Neutrale (leere) Defaults: ohne `vision`-Block und ohne Env-Override
        ist die Vision-Erkennung nicht konfiguriert. Nur wenn ohne Block
        eine Base-URL per Env-Var getragen wird, greift der API-Key-Fallback
        aus der opencode-Konfiguration (`_opencode_api_key`). Ein leerer
        Base-URL- oder Modellwert im Block = nicht konfiguriert.
        """
        if data is None:
            data = settings_load(path).get("vision")
        has_block = bool(data)
        if not has_block:
            data = {}
        env = {k: os.environ.get(v) for k, v in cls.ENV.items()}
        base_url = env["base_url"] or data.get("base_url") or DEFAULT_BASE_URL
        model = env["model"] or data.get("model") or DEFAULT_MODEL
        api_key = env["api_key"] or data.get("api_key") or ""
        if not api_key and not has_block and base_url:
            api_key = _opencode_api_key(base_url)
        return cls(base_url=base_url, api_key=api_key, model=model)

    @property
    def configured(self):
        """True, wenn der Endpunkt nutzbar ist (Base-URL + Modell gesetzt)."""
        return bool(self.base_url and self.model)


def _encode_jpeg(img, quality=85):
    """BGR-Bild als base64-JPEG-Daten-URL kodieren."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise VisionError("encode_failed", "image encoding failed")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _downscale(frame, max_side=SEND_MAX_SIDE):
    """Frame auf `max_side` (längste Seite) downscalen (INTER_AREA)."""
    fh, fw = frame.shape[:2]
    scale = max_side / max(fw, fh)
    if scale >= 1.0:
        return frame, fw, fh
    sw, sh = int(round(fw * scale)), int(round(fh * scale))
    small = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA)
    return small, sw, sh


def _endpoint_url(base_url):
    """Chat-Completions-Endpunkt-URL aus der Base-URL ableiten."""
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


class VisionClient(object):
    """OpenAI-kompatibler Chat-Completions-Client für Bild + kurzen Prompt.

    `transport` ist ein injizierbarer httpx-Transport (Tests mit Fake ohne Netz).
    """

    def __init__(self, config, transport=None):
        self.config = config
        self._transport = transport

    def _endpoint(self):
        return _endpoint_url(self.config.base_url)

    def detect(self, frame):
        """VLM-Call: liefert den rohen Antwort-String (nach 1 Retry).

        Raises `VisionError` bei leeren Antworten, HTTP-Fehlern oder Timeouts.
        """
        img, _sw, _sh = _downscale(frame)
        payload = {
            "model": self.config.model,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": _encode_jpeg(img)}},
                    {"type": "text", "text": DETECT_PROMPT},
                ],
            }],
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        last = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=REQUEST_TIMEOUT_S,
                                  transport=self._transport) as client:
                    resp = client.post(self._endpoint(), json=payload,
                                       headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = (data.get("choices") or [{}])[0] \
                    .get("message", {}).get("content", "") or ""
                if content.strip():
                    return content
                last = VisionError("empty_response",
                                   "model returned an empty response")
            except VisionError as e:
                last = e
            except Exception as e:  # noqa: BLE001 — Netz/HTTP/JSON, Retry
                last = VisionError("request_failed", str(e))
            if attempt < MAX_RETRIES:
                continue
        raise last


def extract_sticker(frame, config=None, transport=None):
    """Etikett-Metadaten per VLM aus einem Kamerabild lesen.

    Sendet das Bild (downscaled auf `SEND_MAX_SIDE`) mit `response_format:
    json_schema` (Schema `STICKER_SCHEMA`) und schlichtem Prompt an den
    konfigurierten Endpunkt und liefert die Werte als Dict:

        {"zeit": "HH:MM", "stand": int, "dg": int, "sch_nr": int}

    `config` ist ein `VisionConfig` (Default: `VisionConfig.from_settings()`);
    `transport` ist ein injizierbarer httpx-Transport (Tests ohne Netz).
    Raises `VisionError` bei leeren/ungültigen Antworten oder HTTP-Fehlern.
    """
    if config is None:
        config = VisionConfig.from_settings()
    if not config.configured:
        raise VisionError("not_configured", "vision endpoint not configured")
    img, _sw, _sh = _downscale(frame)
    payload = {
        "model": config.model,
        "temperature": 0,
        "max_tokens": 512,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "sticker", "strict": True,
                            "schema": STICKER_SCHEMA},
        },
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": _encode_jpeg(img)}},
                {"type": "text", "text": STICKER_PROMPT},
            ],
        }],
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = "Bearer " + config.api_key
    last = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_S,
                              transport=transport) as client:
                resp = client.post(_endpoint_url(config.base_url),
                                   json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = (data.get("choices") or [{}])[0] \
                .get("message", {}).get("content", "") or ""
            return _parse_sticker_json(content)
        except VisionError as e:
            last = e
        except Exception as e:  # noqa: BLE001 — Netz/HTTP/JSON, Retry
            last = VisionError("request_failed", str(e))
        if attempt < MAX_RETRIES:
            continue
    raise last


def _parse_sticker_json(raw):
    """VLM-Antwort des Etikett-Scans defensiv parsen → Dict.

    Toleriert Markdown-Codeblöcke und fehlende Keys; wandelt Werte in die
    erwarteten Typen (`zeit` string, übrige int). Wirft `VisionError` bei
    leerer Antwort oder fehlenden/ungültigen Feldern.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if not text:
        raise VisionError("empty_response", "model returned an empty response")
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        raise VisionError("invalid_response",
                          "model returned invalid JSON")
    if not isinstance(data, dict):
        raise VisionError("invalid_response",
                          "model response is not a JSON object")
    try:
        zeit = str(data["zeit"]).strip()
        stand = int(data["stand"])
        dg = int(data["dg"])
        sch_nr = int(data["sch_nr"])
    except (KeyError, TypeError, ValueError):
        raise VisionError("invalid_response",
                          "model response misses or mis-types sticker fields")
    return {"zeit": zeit, "stand": stand, "dg": dg, "sch_nr": sch_nr}


def _object_pairs_hook(pairs):
    """JSON-Hook: Objekte mit doppelten x/y-Keys in mehrere Punkte aufteilen.

    Kompakte Modelle „stottern" gelegentlich zwei (x,y)-Paare in EIN Objekt,
    z.B. `{"x":100,"y":100,"x":500,"y":500}`. Ohne Hook behielte `json.loads`
    nur den letzten Wert (ein verlorenes Loch); der Hook liefert dann eine
    Liste von `{"x":..,"y":..}`-Objekten pro Paar.
    """
    xs = [v for k, v in pairs if k == "x"]
    ys = [v for k, v in pairs if k == "y"]
    if len(xs) > 1 or len(ys) > 1:
        n = min(len(xs), len(ys))
        return [{"x": xs[i], "y": ys[i]} for i in range(n)]
    return dict(pairs)


def parse_vision_json(raw, sw, sh):
    """VLM-Antwort tolerant parsen → Liste (norm_x, norm_y) in 0–1000.

    Akzeptiert:
    - `{"holes": [{"x":.., "y":..}, ...]}`
    - `[{"bbox_2d": [x0, y0, x1, y1]}, ...]`
    - Objekte mit doppelten x/y-Keys (Modell-Stottern) → je Paar ein Punkt.
    - Skalen: 0–1000 (Primär), >1000 = Pixel der gesendeten Skala, ≤1 = Bruchteil.
    Out-of-Range-Werte (nach Normalisierung >1000) werden verworfen.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text, object_pairs_hook=_object_pairs_hook)
    except (ValueError, TypeError):
        return []
    items = []
    if isinstance(data, dict):
        holes = data.get("holes")
        items = holes if isinstance(holes, list) else []
    elif isinstance(data, list):
        items = data
    # Aufgeteilte Doppel-Keys-Objekte sind Listen von Punkten — eine Ebene
    # abflachen.
    flat = []
    for it in items:
        if isinstance(it, list):
            flat.extend(it)
        else:
            flat.append(it)
    out = []
    for h in flat:
        if not isinstance(h, dict):
            continue
        if "x" in h and "y" in h:
            try:
                x, y = float(h["x"]), float(h["y"])
            except (TypeError, ValueError):
                continue
        elif "bbox_2d" in h and len(h["bbox_2d"]) == 4:
            try:
                b = [float(v) for v in h["bbox_2d"]]
            except (TypeError, ValueError):
                continue
            x, y = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        else:
            continue
        nx, ny = _normalize_coord(x, sw), _normalize_coord(y, sh)
        if 0.0 <= nx <= 1000.0 and 0.0 <= ny <= 1000.0:
            out.append((nx, ny))
    return out


def _normalize_coord(value, side):
    """Eine Koordinate auf 0–1000 normalisieren (Skalen-Erkennung)."""
    v = float(value)
    if 0.0 <= v <= 1.0:
        return v * 1000.0
    if 1.0 < v <= 1000.0:
        return v
    if v > 1000.0 and side > 0:
        return v / side * 1000.0
    return v