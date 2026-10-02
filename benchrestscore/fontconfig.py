# -*- coding: utf-8 -*-
"""GL-freie Schriftgrößen-Präsete der ImGui-Oberfläche.

Die Berechnung hängt nur von der Framebuffer-Höhe und dem Präset-Key ab und
bleibt damit headless testbar (kein Import von imgui/GLFW/OpenGL).
"""

FONT_SCALES = {
    "normal": 1.0,
    "large": 1.25,
    "xlarge": 1.5,
}

DEFAULT_FONT_SCALE_KEY = "normal"

# 4K-Referenz: ~28 px Basis bei 2160 Framebuffer-Höhe -> proportionaler Faktor
_BASE_RATIO = 28 / 2160

# Untergrenze der Basis-Pixelgröße
_MIN_PIXEL_SIZE = 16


def compute_font_pixel_size(fb_h, scale_key):
    """Basis-Pixelgröße für ein Präset berechnen.

    fb_h       Framebuffer-(DPI-)Höhe in Pixel.
    scale_key  Key aus `FONT_SCALES` (`normal`/`large`/`xlarge`).

    Liefert `max(16*scale, int(fb_h * 28/2160 * scale))`. Die Untergrenze
    skaliert mit dem Präset-Faktor, damit die Stufen bei jeder Fensterhöhe
    sichtbar unterscheidbar bleiben (z.B. 1080p: 16/20/24 statt 16/17/21).
    Unbekannte Keys werfen einen `ValueError`, damit fehlerhafte Aufrufe
    sofort auffallen.
    """
    try:
        scale = FONT_SCALES[scale_key]
    except KeyError:
        raise ValueError(
            f"unknown font scale key {scale_key!r}; "
            f"expected one of {sorted(FONT_SCALES)}"
        )
    return max(int(_MIN_PIXEL_SIZE * scale), int(fb_h * _BASE_RATIO * scale))