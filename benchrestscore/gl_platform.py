# -*- coding: utf-8 -*-
"""Bestimmt die GL-Plattform (glx/egl) für PyOpenGL UND GLFW, BEVOR
`OpenGL.GL` importiert und das Fenster erstellt wird.

Hintergrund: PyOpenGL wählt die Plattform (glx/egl/...) beim Import anhand von
`PYOPENGL_PLATFORM`. GLFW entscheidet selbst, ob es GLX (X11) oder EGL nutzt.
Stimmen beide nicht überein, findet PyOpenGL den aktuellen GL-Kontext nicht und
schlägt fehl (z.B. "Attempt to retrieve context when no valid context").

WICHTIG (X11/X-Forwarding): Wählt GLFW von sich aus EGL (wie unter Weston/
XWayland häufig), erzeugt es KEINE sichtbare X11-Window -> das Fenster erscheint
nicht. Die Vorgänger-Version (pyglet) nutzte X11 + GLX und war sichtbar. Deshalb
zwingen wir GLFW auf die X11-Plattform (PLATFORM_X11 + GLX), sobald ein
`DISPLAY` vorhanden ist, damit Fenster sichtbar gemappt werden.
"""

import os


def resolve_gl_platform():
    """Ermittelt die GL-Plattform ('glx'|'egl'|None) anhand der Umgebung.

    - explizite `PYOPENGL_PLATFORM` gewinnt
    - X11-Display vorhanden -> 'glx' (sichtbare X11-Window über GLX)
    - sonst -> 'egl' (Wayland / headless)
    """
    if os.getenv("PYOPENGL_PLATFORM"):
        return os.getenv("PYOPENGL_PLATFORM")
    if os.getenv("DISPLAY"):
        return "glx"
    return "egl"


def set_glfw_platform():
    """GLFW zwingen, die passende Plattform zu nutzen (vor `glfw.init()`).

    Mit `DISPLAY` -> X11 (nutzt GLX, erzeugt sichtbare X11-Windows). Sonst
    unverändert (GLFW wählt Wayland/EGL selbst).
    """
    try:
        import glfw
    except ImportError:
        return
    if not os.getenv("DISPLAY"):
        return
    # GLFW 3.4: PLATFORM_HINT + PLATFORM_X11
    platform_x11 = getattr(glfw, "PLATFORM_X11", None)
    if platform_x11 is not None:
        try:
            glfw.init_hint(glfw.PLATFORM, platform_x11)
        except Exception:
            pass


def set_gl_platform():
    """Setzt PYOPENGL_PLATFORM + GLFW-Plattform passend. Ruft man VOR
    `OpenGL.GL`-Import und VOR `glfw.init()`/`create_window` auf."""
    # PYOPENGL_PLATFORM passend setzen
    if not os.getenv("PYOPENGL_PLATFORM"):
        os.environ["PYOPENGL_PLATFORM"] = resolve_gl_platform()
    # GLFW auf X11 zwingen (falls Display vorhanden)
    set_glfw_platform()
    return os.environ["PYOPENGL_PLATFORM"]