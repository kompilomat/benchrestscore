import glob
import os
import re
import subprocess
import time

import numpy as np
# suppress subnormal warnings from -ffast_math 
# https://stackoverflow.com/questions/70612364/numpy-warning-with-django-4-numpy-float64-type-is-zero
np.finfo(np.dtype("float32"))
np.finfo(np.dtype("float64"))


# make sure it is installed >= 4.5.x
import cv2


from threading import Thread


DEFAULT_CAMERA_DEVICE = "/dev/video0"

# Auflösungs-Presets (Name, Breite, Höhe, fps). Reihenfolge = Auswahlpräferenz.
CAMERA_PRESETS = (
    ("1080p30", 1920, 1080, 30),
    ("1080p60", 1920, 1080, 60),
    ("4K30", 3840, 2160, 30),
    ("4K60", 3840, 2160, 60),
)

# Fallback-Preset, falls ein Gerät keines der höheren Presets unterstützt
# (die Auswahl darf nie leer sein).
CAMERA_PRESET_FALLBACK = ("720p30", 1280, 720, 30)


# Referenz-Skalierung des Waiting-Screen-Texts (bei 4K/2160px Höhe)
_WAITING_FONT_SCALE_REF = 4.0


def build_waiting_screen(width, height):
    """Waiting-Screen in Kamera-Auflösung (reine Funktion, headless testbar).

    Der Text wird proportional zur Auflösung skaliert und zentriert, damit er
    bei niedrigen Auflösungen nicht über den Bildrand läuft (feste Skalierung
    würde bei 1080p/720p rechts abgeschnitten).
    """
    waiting = np.zeros((height, width, 3), dtype=np.uint8)
    waiting[:] = 128
    text = "Warte auf Kamera ..."
    font_scale = _WAITING_FONT_SCALE_REF * height / 2160.0
    thickness = max(1, round(7 * height / 2160.0))
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                         font_scale, thickness)
    # horizontale und vertikale Zentrierung inkl. Baseline
    org = ((width - tw) // 2, (height + th - baseline) // 2)
    cv2.putText(waiting, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                (0, 0, 0), thickness, cv2.LINE_AA)
    return waiting


def gst_pipeline_string(device, width, height, fps, rotate=180):
    """GStreamer-Pipeline-String für die Webcam (reine Funktion, headless testbar).

    `rotate` in {0, 180} steuert `videoflip`: 0° → `method=none` (Identität),
    180° → `method=rotate-180` (Kamera hängt auf dem Kopf). `rotate-0` gibt es
    in GStreamer nicht. Jeder andere Wert wirft ValueError.
    """
    if rotate not in (0, 180):
        raise ValueError(f"rotate must be 0 or 180, got {rotate!r}")
    method = "rotate-180" if rotate == 180 else "none"
    return (f"v4l2src device={device} io-mode=2 ! "
            f"image/jpeg,width={width},height={height},framerate={fps}/1 ! "
            f"jpegparse ! jpegdec ! videoconvert ! videoflip method={method} "
            f"! appsink sync=false")


def default_camera_opener(pipeline_string):
    """Standard-Opener für die Preset-Probe: cv2 mit GStreamer-Backend."""
    return cv2.VideoCapture(pipeline_string, cv2.CAP_GSTREAMER)


def _silence_fd(fd=2):
    """Fd nach /dev/null umleiten (cv2-Warnungen bei fehlgeschlagenen Probes)."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(fd)
    os.dup2(devnull, fd)
    os.close(devnull)
    return saved


def _restore_fd(saved, fd=2):
    os.dup2(saved, fd)
    os.close(saved)


def _run_v4l2_ctl(device):
    """v4l2-ctl --list-formats-ext ausführen (stdout als String).

    Enumertiert Formate OHNE exklusiven Zugriff und funktioniert damit auch,
    wenn die App selbst die Kamera bereits geöffnet hält. `v4l2-ctl` kommt aus
    v4l-utils (apt-Abhängigkeit des Projekts).
    """
    try:
        out = subprocess.run(
            ["v4l2-ctl", "--device", device, "--list-formats-ext"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return ""
    return out.stdout or ""


def parse_v4l2_formats(output):
    """MJPG-Formate aus `v4l2-ctl --list-formats-ext` parsen (reine Funktion).

    Rückgabe: Menge von `(width, height, fps)` mit ganzzahligem fps. Nur MJPG
    wird berücksichtigt, da die App `image/jpeg` verwendet. Leere/unbrauchbare
    Ausgabe -> leere Menge.
    """
    caps = set()
    in_mjpg = False
    cur_size = None
    for line in output.splitlines():
        m = re.match(r"\s*\[\d+\]: '(\w+)'", line)
        if m:
            in_mjpg = (m.group(1) == "MJPG")
            cur_size = None
            continue
        if not in_mjpg:
            continue
        m = re.match(r"\s*Size: Discrete (\d+)x(\d+)", line)
        if m:
            cur_size = (int(m.group(1)), int(m.group(2)))
            continue
        m = re.match(r"\s*Interval: Discrete [\d.]+s \(([\d.]+) fps\)", line)
        if m and cur_size is not None:
            caps.add((cur_size[0], cur_size[1], round(float(m.group(1)))))
    return caps


def list_camera_devices(run_v4l2=_run_v4l2_ctl):
    """Verfügbare Video-Capture-Geräte (`/dev/video*`) sortiert liefern.

    Nur Nodes mit nutzbaren MJPG-Capture-Formaten werden gelistet; reine
    Metadata-/Control-Nodes (z.B. zweiter UVC-Node einer Kamera) werden
    gefiltert. Schlägt die v4l2-Enumeration komplett fehl (leere Ausgabe für
    alle Kandidaten, z.B. kein v4l2-ctl installiert), wird die ungefilterte
    Glob-Liste zurückgegeben, damit keine echten Kameras verschwinden.
    """
    candidates = sorted(glob.glob("/dev/video*"))
    if not candidates:
        return []
    outputs = {}
    for dev in candidates:
        try:
            outputs[dev] = run_v4l2(dev) or ""
        except Exception:
            outputs[dev] = ""
    usable = [dev for dev in candidates if parse_v4l2_formats(outputs[dev])]
    if not usable and all(not outputs[dev] for dev in candidates):
        # Enumeration für alle fehlgeschlagen -> best effort unfiltered
        return candidates
    return usable


def _probe_pipeline(device, preset, opener):
    """Einzelnen Kandidaten per Pipeline-Probe prüfen (Fallback, Gerät frei)."""
    name, width, height, fps = preset
    pipe = gst_pipeline_string(device, width, height, fps)
    saved = _silence_fd()
    try:
        cap = opener(pipe)
        try:
            return bool(cap.isOpened())
        finally:
            cap.release()
    except Exception:
        return False
    finally:
        _restore_fd(saved)


def probe_supported_presets(device, candidates=CAMERA_PRESETS,
                            run_v4l2=_run_v4l2_ctl,
                            opener=default_camera_opener):
    """Unterstützte Presets eines Geräts ermitteln.

    Primär über `v4l2-ctl --list-formats-ext` (MJPG-Größen/Frame-Raten) — das
    funktioniert auch, während die App die Kamera selbst geöffnet hält. Scheitert
    die Enumeration (kein v4l2-ctl oder keine MJPG-Daten), wird per Pipeline-
    Probe (`opener`, injizierbar) geprüft — das braucht ein freies Gerät. Bleibt
    die Liste leer, wird `CAMERA_PRESET_FALLBACK` geliefert (nie leer).
    """
    caps = parse_v4l2_formats(run_v4l2(device) or "")
    if caps:
        supported = [p for p in candidates if (p[1], p[2], p[3]) in caps]
    else:
        supported = [p for p in candidates if _probe_pipeline(device, p, opener)]
    if not supported:
        supported = [CAMERA_PRESET_FALLBACK]
    return supported


class BRSCamera(Thread):
   
    def __init__(self, device=DEFAULT_CAMERA_DEVICE, width=3840, height=2160,
                 fps=30, rotate=180, *args, **kwargs):
        super(BRSCamera, self).__init__(*args, **kwargs)
        self.daemon = True
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.rotate = rotate
        self.calib = None
        self.frame_time = 1. / fps

        # waiting screen (auflösungsabhängig, Text skaliert proportional)
        self.waiting_screen = build_waiting_screen(width, height)
        self.current_frame = self.waiting_screen
        # self.queue.put(self.waiting_screen)

        self.running = True
        self.paused = False
        self.confirmed = False

    
    def run(self):
        gstr = gst_pipeline_string(self.device, self.width, self.height,
                                   self.fps, self.rotate)
        vid = None
        try:
            vid = cv2.VideoCapture(gstr, cv2.CAP_GSTREAMER)
            if not vid.isOpened():
                raise Exception("There's no available camera.")

            while self.running:
                frame_ts = time.time()
                target_ts = frame_ts + self.frame_time - 0.001

                ret, frame = vid.read()
                if ret:
                    if not self.paused:
                        self.current_frame = frame
                    else:
                        # report outside that pause is active
                        self.confirmed = True

                while time.time() < target_ts:
                    time.sleep(0.001)
        except Exception:
            # Beim Beenden (z.B. Abriss in vid.read()) still abbrechen statt
            # einem "Exception in thread"-Traceback beim Interpreter-Exit.
            pass
        finally:
            if vid is not None:
                vid.release()    

    def pause(self):
        self.confirmed = False
        self.paused = True
        # Ein bereits vorhandenes Frame gilt sofort als eingefroren; sonst
        # warten, bis der Kamera-Thread das nächste Frame bestätigt.
        if self.current_frame is not None:
            self.confirmed = True
        while not self.confirmed:
            time.sleep(0.001)
        return self.confirmed

    def unpause(self):
        self.paused = False
        return True


    def stop(self):
        self.running = False
