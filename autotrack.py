#!/usr/bin/env python3
"""
PTZOptics Auto-Tracker  —  with Control Panel UI
-------------------------------------------------
Video source  : RTSP stream over camera LAN port
Camera control: VISCA over IP (TCP 5678)
Detection     : MediaPipe Pose

Left panel = live controls (no file editing needed)
Right panel = camera preview with overlay

Run: python autotrack.py
"""

import socket
import time
import threading
import sys
import math
import os
import json
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import cv2
except ImportError:
    sys.exit("ERROR: pip install opencv-python")

try:
    import mediapipe as mp
except ImportError:
    sys.exit("ERROR: pip install mediapipe")

import numpy as np
from PIL import Image, ImageTk  # pip install Pillow


# ─────────────────────────────────────────────────────────────
# Shared live settings (read by tracker thread, written by UI)
# ─────────────────────────────────────────────────────────────

class Settings:
    def __init__(self):
        self.camera_ip    = "192.168.1.10"
        self.rtsp_user    = "admin"
        self.rtsp_pass    = "admin"
        self.rtsp_stream  = "2"
        self.visca_port   = 5678
        self.home_preset  = 5

        # Pan / Tilt
        self.pan_dead     = 0.15
        self.pan_near     = 0.30
        self.pan_slow     = 3
        self.pan_fast     = 7
        self.tilt_dead    = 0.15
        self.tilt_near    = 0.30
        self.tilt_slow    = 2
        self.tilt_fast    = 5

        # Zoom
        self.zoom_enabled = True
        self.zoom_target  = 0.45
        self.zoom_dead    = 0.20
        self.zoom_speed   = 1     # 0-7

        # Prediction
        self.latency_comp = 0.4

        # Lost timeout
        self.lost_timeout = 3.0

        # Tracking focus: always upper body (nose, shoulders, elbows, hips)
        self.track_focus   = 'upper'
        # Vertical offset: -5 to +5. Negative = aim higher, Positive = aim lower
        self.track_offset  = 0

    # ── Persistence ─────────────────────────────────────────

    @staticmethod
    def _config_path():
        """Store config next to the exe or script."""
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "trackmind_config.json")

    def save(self):
        data = {
            "camera_ip":    self.camera_ip,
            "rtsp_user":    self.rtsp_user,
            "rtsp_pass":    self.rtsp_pass,
            "rtsp_stream":  self.rtsp_stream,
            "home_preset":  self.home_preset,
            "pan_dead":     self.pan_dead,
            "pan_slow":     self.pan_slow,
            "pan_fast":     self.pan_fast,
            "tilt_dead":    self.tilt_dead,
            "tilt_slow":    self.tilt_slow,
            "tilt_fast":    self.tilt_fast,
            "zoom_enabled": self.zoom_enabled,
            "zoom_target":  self.zoom_target,
            "zoom_dead":    self.zoom_dead,
            "zoom_speed":   self.zoom_speed,
            "latency_comp": self.latency_comp,
            "lost_timeout": self.lost_timeout,
            "track_offset": self.track_offset,
        }
        try:
            with open(self._config_path(), "w") as f:
                json.dump(data, f, indent=2)
            print(f"[CFG] Settings saved to {self._config_path()}")
        except Exception as e:
            print(f"[CFG] Could not save settings: {e}")

    def load(self):
        path = self._config_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            for key, val in data.items():
                if hasattr(self, key):
                    setattr(self, key, val)
            # Recompute derived values
            self.pan_near  = self.pan_dead  + 0.15
            self.tilt_near = self.tilt_dead + 0.15
            print(f"[CFG] Settings loaded from {path}")
        except Exception as e:
            print(f"[CFG] Could not load settings: {e}")


SETTINGS = Settings()
SETTINGS.load()   # Load saved settings on startup


# ─────────────────────────────────────────────────────────────
# User Profiles
# ─────────────────────────────────────────────────────────────

class ProfileManager:
    def __init__(self):
        self.profiles      = {}   # name -> settings dict
        self.current       = None
        self._load()

    @staticmethod
    def _path():
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "trackmind_profiles.json")

    def _settings_dict(self):
        s = SETTINGS
        return {
            "camera_ip":    s.camera_ip,
            "rtsp_user":    s.rtsp_user,
            "rtsp_pass":    s.rtsp_pass,
            "rtsp_stream":  s.rtsp_stream,
            "home_preset":  s.home_preset,
            "pan_dead":     s.pan_dead,
            "pan_slow":     s.pan_slow,
            "pan_fast":     s.pan_fast,
            "tilt_dead":    s.tilt_dead,
            "tilt_slow":    s.tilt_slow,
            "tilt_fast":    s.tilt_fast,
            "zoom_enabled": s.zoom_enabled,
            "zoom_target":  s.zoom_target,
            "zoom_dead":    s.zoom_dead,
            "zoom_speed":   s.zoom_speed,
            "latency_comp": s.latency_comp,
            "lost_timeout": s.lost_timeout,
            "track_offset": s.track_offset,
        }

    def save_profile(self, name):
        self.profiles[name] = self._settings_dict()
        self.current = name
        self._persist()
        print(f"[PROFILE] Saved profile: {name}")

    def load_profile(self, name):
        if name not in self.profiles:
            return False
        data = self.profiles[name]
        for key, val in data.items():
            if hasattr(SETTINGS, key):
                setattr(SETTINGS, key, val)
        SETTINGS.pan_near  = SETTINGS.pan_dead  + 0.15
        SETTINGS.tilt_near = SETTINGS.tilt_dead + 0.15
        self.current = name
        print(f"[PROFILE] Loaded profile: {name}")
        return True

    def delete_profile(self, name):
        if name in self.profiles:
            del self.profiles[name]
            if self.current == name:
                self.current = None
            self._persist()

    def _persist(self):
        try:
            data = {"current": self.current, "profiles": self.profiles}
            with open(self._path(), "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[PROFILE] Save failed: {e}")

    def _load(self):
        p = self._path()
        if not os.path.exists(p):
            return
        try:
            with open(p, "r") as f:
                data = json.load(f)
            self.profiles = data.get("profiles", {})
            self.current  = data.get("current", None)
            print(f"[PROFILE] Loaded {len(self.profiles)} profiles")
        except Exception as e:
            print(f"[PROFILE] Load failed: {e}")


PROFILE_MANAGER = ProfileManager()


# ─────────────────────────────────────────────────────────────
# VISCA Controller
# ─────────────────────────────────────────────────────────────

class VISCAController:
    def __init__(self):
        self._sock       = None
        self._lock       = threading.Lock()
        self._connected  = False

    @property
    def ip(self):
        return SETTINGS.camera_ip

    @property
    def port(self):
        return SETTINGS.visca_port

    def connect(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((self.ip, self.port))
            self._sock      = s
            self._connected = True
            print(f"[VISCA] Connected to {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"[VISCA] Connection failed: {e}")
            self._connected = False
            return False

    def disconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._connected = False

    def _send(self, cmd: bytes) -> bool:
        with self._lock:
            for attempt in range(2):
                if not self._connected:
                    if not self.connect():
                        return False
                try:
                    self._sock.sendall(cmd)
                    return True
                except Exception as e:
                    print(f"[VISCA] Send error: {e}")
                    self._connected = False
                    try:
                        self._sock.close()
                    except Exception:
                        pass
        return False

    def pan_tilt(self, pan_speed, tilt_speed, pan_dir, tilt_dir):
        ps  = max(1, min(24, abs(pan_speed)))
        ts  = max(1, min(24, abs(tilt_speed)))
        cmd = bytes([0x81, 0x01, 0x06, 0x01, ps, ts, pan_dir, tilt_dir, 0xFF])
        return self._send(cmd)

    def stop(self):
        return self.pan_tilt(1, 1, 3, 3)

    def move(self, pan_vel: int, tilt_vel: int):
        pd = 1 if pan_vel > 0 else (2 if pan_vel < 0 else 3)
        td = 1 if tilt_vel > 0 else (2 if tilt_vel < 0 else 3)
        ps = abs(pan_vel) if pan_vel != 0 else 1
        ts = abs(tilt_vel) if tilt_vel != 0 else 1
        return self.pan_tilt(ps, ts, pd, td)

    def zoom_in(self, speed=1):
        s = max(0, min(7, speed))
        return self._send(bytes([0x81, 0x01, 0x04, 0x07, 0x20 | s, 0xFF]))

    def zoom_out(self, speed=1):
        s = max(0, min(7, speed))
        return self._send(bytes([0x81, 0x01, 0x04, 0x07, 0x30 | s, 0xFF]))

    def zoom_stop(self):
        return self._send(bytes([0x81, 0x01, 0x04, 0x07, 0x00, 0xFF]))

    def recall_preset(self, preset: int):
        p = max(0, min(89, preset))
        return self._send(bytes([0x81, 0x01, 0x04, 0x3F, 0x02, p, 0xFF]))

    def home(self):
        return self._send(bytes([0x81, 0x01, 0x06, 0x04, 0xFF]))


# ─────────────────────────────────────────────────────────────
# Zone speed helper
# ─────────────────────────────────────────────────────────────

def zone_speed(pos, dead, near, slow, fast) -> int:
    err = pos - 0.5
    mag = abs(err)
    if mag < dead:
        return 0
    speed = slow if mag < near else fast
    return speed if err > 0 else -speed


# ─────────────────────────────────────────────────────────────
# Person Detector (MediaPipe Pose + lock-on)
# ─────────────────────────────────────────────────────────────

class PersonDetector:
    BODY_LANDMARKS = [0, 11, 12, 13, 14, 23, 24]  # nose, shoulders, elbows, hips

    def __init__(self):
        self.mp_pose     = mp.solutions.pose
        self.pose        = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.55,
            min_tracking_confidence=0.5,
        )
        self._locked_cx  = None
        self._locked_cy  = None
        self._lock_dist  = 0.25

    # Landmark sets
    UPPER_LANDMARKS = [0, 11, 12, 13, 14, 23, 24]          # nose, shoulders, elbows, hips
    FULL_LANDMARKS  = [0, 11, 12, 13, 14, 23, 24, 25, 26]  # upper + knees
    LOWER_LANDMARKS = [23, 24, 25, 26, 27, 28]             # hips, knees, ankles

    def _landmarks_to_bbox(self, lms):
        focus  = SETTINGS.track_focus
        offset = SETTINGS.track_offset  # -5 to +5, negative = higher, positive = lower

        if focus == 'lower':
            indices = self.LOWER_LANDMARKS
        elif focus == 'upper':
            indices = self.UPPER_LANDMARKS
        else:  # full
            indices = self.FULL_LANDMARKS

        visible = [lms[i] for i in indices if lms[i].visibility > 0.4]
        if len(visible) < 2:
            visible = [lms[i] for i in self.UPPER_LANDMARKS if lms[i].visibility > 0.4]
        if len(visible) < 3:
            return None

        xs = [l.x for l in visible]
        ys = [l.y for l in visible]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        pad_x = (x1 - x0) * 0.15
        pad_y = (y1 - y0) * 0.15
        x0 = max(0.0, x0 - pad_x)
        x1 = min(1.0, x1 + pad_x)
        y0 = max(0.0, y0 - pad_y)
        y1 = min(1.0, y1 + pad_y)

        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        # Base vertical adjustment per mode
        h = y1 - y0
        if focus == 'upper':
            cy -= h * 0.15   # shift up toward chest
        # full and lower stay centered naturally

        # Apply manual offset: each step = 5% of bbox height
        # negative offset = move aim point up (camera tilts up)
        # positive offset = move aim point down (camera tilts down)
        cy += (offset / 7.0) * h * 0.7
        cy = max(0.0, min(1.0, cy))

        return cx, cy, x1 - x0, y1 - y0

    def detect(self, frame_rgb, hard_lock=False):
        """
        hard_lock=False (default): follows most prominent person,
                                   updates lock position each frame freely.
        hard_lock=True:  strictly ignores anyone too far from locked position.
        """
        results = self.pose.process(frame_rgb)
        if not results.pose_landmarks:
            return None
        bbox = self._landmarks_to_bbox(results.pose_landmarks.landmark)
        if bbox is None:
            return None
        cx, cy, w, h = bbox

        if not hard_lock:
            # Unlocked — follow whoever MediaPipe sees, update position freely
            self._locked_cx = cx
            self._locked_cy = cy
            return bbox

        # Hard lock mode — only follow if close to last known position
        if self._locked_cx is None:
            print(f"[LOCK] Acquired at ({cx:.2f}, {cy:.2f})")
            self._locked_cx = cx
            self._locked_cy = cy
            return bbox
        dist = math.sqrt((cx - self._locked_cx)**2 + (cy - self._locked_cy)**2)
        if dist < self._lock_dist:
            self._locked_cx = cx
            self._locked_cy = cy
            return bbox
        return None

    def release_lock(self):
        self._locked_cx = None
        self._locked_cy = None
        print("[LOCK] Released — will reacquire")

    def close(self):
        self.pose.close()


# ─────────────────────────────────────────────────────────────
# Auto-Tracker
# ─────────────────────────────────────────────────────────────

class AutoTracker:
    CMD_INTERVAL = 0.15

    def __init__(self, visca: VISCAController):
        self.visca         = visca
        self._last_seen    = None
        self._at_home      = False
        self._prev_pan     = 0
        self._prev_tilt    = 0
        self._prev_zoom    = 0
        self._last_cmd_t   = 0.0
        self._last_cx      = None
        self._last_cy      = None
        self._vx           = 0.0
        self._vy           = 0.0

    def process(self, detection):
        if detection is None:
            self._handle_lost()
            return

        s   = SETTINGS
        now = time.monotonic()
        self._at_home = False

        cx, cy, bbox_w, bbox_h = detection

        # Velocity prediction
        dt = max(0.01, min(0.5, (now - self._last_seen) if self._last_seen else 0.1))
        if self._last_cx is not None:
            vx = (cx - self._last_cx) / dt
            vy = (cy - self._last_cy) / dt
            self._vx = 0.85 * self._vx + 0.15 * vx
            self._vy = 0.85 * self._vy + 0.15 * vy
        self._last_cx   = cx
        self._last_cy   = cy
        self._last_seen = now

        max_v  = 0.3
        self._vx = max(-max_v, min(max_v, self._vx))
        self._vy = max(-max_v, min(max_v, self._vy))

        pred_cx = max(0.0, min(1.0, cx + self._vx * s.latency_comp))
        pred_cy = max(0.0, min(1.0, cy + self._vy * s.latency_comp))

        pan_vel  = -zone_speed(pred_cx, s.pan_dead,  s.pan_near,  s.pan_slow,  s.pan_fast)
        tilt_vel = -zone_speed(pred_cy, s.tilt_dead, s.tilt_near, s.tilt_slow, s.tilt_fast)

        if pan_vel != self._prev_pan or tilt_vel != self._prev_tilt:
            self.visca.move(pan_vel, tilt_vel)
            self._prev_pan   = pan_vel
            self._prev_tilt  = tilt_vel
            self._last_cmd_t = now

        # Zoom
        if s.zoom_enabled:
            fill = bbox_h
            if fill < (s.zoom_target - s.zoom_dead):
                zoom_dir = 1
            elif fill > (s.zoom_target + s.zoom_dead):
                zoom_dir = -1
            else:
                zoom_dir = 0
            if zoom_dir != self._prev_zoom:
                if zoom_dir == 1:
                    self.visca.zoom_in(speed=s.zoom_speed)
                elif zoom_dir == -1:
                    self.visca.zoom_out(speed=s.zoom_speed)
                else:
                    self.visca.zoom_stop()
                self._prev_zoom = zoom_dir
        else:
            if self._prev_zoom != 0:
                self.visca.zoom_stop()
                self._prev_zoom = 0

    def _handle_lost(self):
        if self._prev_pan != 0 or self._prev_tilt != 0:
            self.visca.stop()
            self._prev_pan  = 0
            self._prev_tilt = 0
        if self._prev_zoom != 0:
            self.visca.zoom_stop()
            self._prev_zoom = 0
        self._vx = 0.0
        self._vy = 0.0
        self._last_cx = None
        self._last_cy = None
        if self._at_home:
            return
        elapsed = (time.monotonic() - self._last_seen) if self._last_seen else 999
        if elapsed >= SETTINGS.lost_timeout:
            print(f"[TRACKER] Lost — recalling preset {SETTINGS.home_preset}")
            self.visca.recall_preset(SETTINGS.home_preset)
            self._at_home = True

    def reset(self):
        self._vx = self._vy = 0.0
        self._last_cx = self._last_cy = None
        self._prev_pan = self._prev_tilt = self._prev_zoom = 0


# ─────────────────────────────────────────────────────────────
# Tracker Thread
# ─────────────────────────────────────────────────────────────

class TrackerThread(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app              = app
        self.running          = False
        self.tracking         = False
        self._stop_event      = threading.Event()
        self.latest_frame     = None
        self.latest_detection = None
        self.status           = "STOPPED"
        self._frame_lock      = threading.Lock()
        # Buffer thread state
        self._buf_frame       = None
        self._buf_lock        = threading.Lock()
        self._buf_ready       = threading.Event()

    def stop(self):
        self._stop_event.set()

    def _buffer_reader(self, cap, stop_event):
        """
        Dedicated thread that reads frames as fast as possible and
        keeps only the LATEST one. This drains the RTSP buffer
        continuously so the tracker always gets a fresh frame
        instead of a frame that is seconds old.
        """
        while not stop_event.is_set():
            ret, frame = cap.read()
            if ret and frame is not None:
                with self._buf_lock:
                    self._buf_frame = frame
                self._buf_ready.set()
            else:
                time.sleep(0.005)

    def run(self):
        s   = SETTINGS
        url = f"rtsp://{s.rtsp_user}:{s.rtsp_pass}@{s.camera_ip}/{s.rtsp_stream}"
        print(f"[CAP] Connecting: rtsp://{s.rtsp_user}:***@{s.camera_ip}/{s.rtsp_stream}")

        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"

        def open_rtsp():
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"
            c = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return c

        cap = open_rtsp()

        if not cap.isOpened():
            self.status = "ERROR: Cannot open stream"
            print(f"[CAP] {self.status}")
            return

        visca    = VISCAController()
        visca.connect()
        detector = PersonDetector()
        tracker  = AutoTracker(visca)

        self.app.visca    = visca
        self.app.detector = detector
        self.app.tracker  = tracker

        self.running = True
        self.status  = "PAUSED"
        frame_count  = 0

        # Start the dedicated buffer-draining reader thread
        buf_stop = threading.Event()
        buf_thread = threading.Thread(
            target=self._buffer_reader,
            args=(cap, buf_stop),
            daemon=True
        )
        buf_thread.start()

        while not self._stop_event.is_set():
            # Wait up to 3s for a fresh frame
            if not self._buf_ready.wait(timeout=3.0):
                print("[CAP] No frame received — reconnecting...")
                buf_stop.set()
                buf_thread.join(timeout=2.0)
                cap.release()
                time.sleep(1.0)
                cap = open_rtsp()
                buf_stop.clear()
                self._buf_ready.clear()
                buf_thread = threading.Thread(
                    target=self._buffer_reader,
                    args=(cap, buf_stop),
                    daemon=True
                )
                buf_thread.start()
                continue

            # Grab latest frame and immediately clear ready flag
            self._buf_ready.clear()
            with self._buf_lock:
                frame = self._buf_frame
                self._buf_frame = None

            if frame is None:
                continue

            frame_count += 1
            if frame_count == 1:
                print("[CAP] Stream live!")
                self.status = "PAUSED"
                try:
                    self.app.canvas.delete("nosignal")
                except Exception:
                    pass

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if self.tracking:
                hard_lock = getattr(self.app, '_lock_active', False)
                detection = detector.detect(rgb, hard_lock=hard_lock)
                tracker.process(detection)
                self.latest_detection = detection
                self.status = "TRACKING"
            else:
                detection = None
                self.latest_detection = None
                if self.status == "TRACKING":
                    visca.stop()
                    visca.zoom_stop()
                self.status = "PAUSED"

            with self._frame_lock:
                self.latest_frame = frame.copy()

        # Cleanup
        buf_stop.set()
        buf_thread.join(timeout=2.0)
        visca.stop()
        visca.zoom_stop()
        visca.disconnect()
        detector.close()
        cap.release()
        self.running = False
        print("[INFO] Tracker thread stopped")


# ─────────────────────────────────────────────────────────────
# Control Panel UI
# ─────────────────────────────────────────────────────────────

class App:
    PANEL_W   = 300
    PREVIEW_W = 720
    PREVIEW_H = 405

    # ── Palette ──
    BG        = "#0c0c0f"
    BG2       = "#13131a"
    BG3       = "#1c1c27"
    BORDER    = "#2a2a3a"
    AMBER     = "#f5a623"
    AMBER_DIM = "#7a5210"
    RED       = "#e03c3c"
    GREEN     = "#2ecc71"
    FG        = "#d4d4d8"
    FG_DIM    = "#6b6b7a"
    FONT      = "Courier New"

    def __init__(self, root):
        self.root = root
        self.root.title("TrackMind — Intelligent PTZ Auto-Tracking")
        self.root.resizable(True, True)
        self.root.configure(bg=self.BG)
        self._fullscreen = False
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", self._exit_fullscreen)

        self.visca    = None
        self.detector = None
        self.tracker  = None
        self._thread  = None

        # Set window icon — works both as .py script and compiled .exe
        try:
            import sys, os
            if getattr(sys, 'frozen', False):
                # Running as PyInstaller exe — files are in sys._MEIPASS
                base = sys._MEIPASS
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base, "trackmind_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self._build_ui()
        self._refresh_profile_dropdown()
        self._update_preview()
        # Auto-connect on launch
        self.root.after(500, self._on_start)

    # ── UI Build ────────────────────────────────────────────

    def _build_ui(self):

        # ── Tooltip helper ──────────────────────────────────
        class Tooltip:
            def __init__(self, widget, text):
                self.tip = None
                self.text = text
                widget.bind("<Enter>", self._show)
                widget.bind("<Leave>", self._hide)
            def _show(self, e=None):
                w = e.widget if e else None
                if w is None: return
                x = w.winfo_rootx() + 20
                y = w.winfo_rooty() + w.winfo_height() + 4
                self.tip = tk.Toplevel(w)
                self.tip.wm_overrideredirect(True)
                self.tip.wm_geometry(f"+{x}+{y}")
                tk.Label(self.tip, text=self.text,
                         bg="#1e1a0e", fg="#f5a623",
                         font=("Courier New", 8),
                         relief=tk.FLAT, padx=8, pady=4,
                         wraplength=230, justify=tk.LEFT).pack()
            def _hide(self, e=None):
                if self.tip:
                    self.tip.destroy()
                    self.tip = None

        def tip(widget, text):
            Tooltip(widget, text)

        # ═══ Header ═══════════════════════════════════════════
        header = tk.Frame(self.root, bg=self.BG2, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        # Logo canvas — mini version of the TrackMind lens icon
        logo_c = tk.Canvas(header, width=36, height=36,
                           bg=self.BG2, highlightthickness=0)
        logo_c.pack(side=tk.LEFT, padx=(16, 6), pady=6)

        def draw_logo(c):
            cx, cy, r = 18, 18, 14
            # Outer ring
            c.create_oval(cx-r, cy-r, cx+r, cy+r,
                          outline=self.AMBER, width=1)
            # Lens glass
            c.create_oval(cx-10, cy-10, cx+10, cy+10,
                          outline=self.AMBER, fill="#08080f", width=1)
            # Crosshair
            for x1,y1,x2,y2 in [(cx,cy-14,cx,cy-4),(cx,cy+4,cx,cy+14),
                                  (cx-14,cy,cx-4,cy),(cx+4,cy,cx+14,cy)]:
                c.create_line(x1,y1,x2,y2, fill=self.AMBER, width=1)
            # Corner brackets
            for bx,by,dx,dy in [(cx-10,cy-10,-1,-1),(cx+10,cy-10,1,-1),
                                  (cx-10,cy+10,-1,1),(cx+10,cy+10,1,1)]:
                c.create_line(bx,by, bx+dx*5,by, fill=self.AMBER, width=1)
                c.create_line(bx,by, bx,by+dy*5, fill=self.AMBER, width=1)
            # Centre dot
            c.create_oval(cx-2,cy-2,cx+2,cy+2, fill=self.AMBER, outline="")

        draw_logo(logo_c)

        tk.Label(header, text="TRACKMIND",
                 bg=self.BG2, fg=self.AMBER,
                 font=(self.FONT, 13, "bold")).pack(side=tk.LEFT, padx=(0, 4), pady=8)
        tk.Label(header, text="intelligent ptz auto-tracking",
                 bg=self.BG2, fg=self.FG_DIM,
                 font=(self.FONT, 8)).pack(side=tk.LEFT, padx=4)

        self.status_var  = tk.StringVar(value="OFFLINE")
        self._status_lbl = tk.Label(header, textvariable=self.status_var,
                                    bg=self.BG2, fg=self.FG_DIM,
                                    font=(self.FONT, 10, "bold"))
        self._status_lbl.pack(side=tk.RIGHT, padx=16)
        tk.Frame(self.root, bg=self.AMBER, height=2).pack(fill=tk.X)

        # ═══ Body ═════════════════════════════════════════════
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(body, bg=self.BG2, width=self.PANEL_W)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        tk.Frame(body, bg=self.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        right = tk.Frame(body, bg=self.BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._preview_wrap = tk.Frame(right, bg=self.BG, padx=16, pady=16)
        self._preview_wrap.pack(fill=tk.BOTH, expand=True)
        cb = tk.Frame(self._preview_wrap, bg=self.BORDER, padx=1, pady=1)
        cb.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(cb, bg="#050508", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_text(self.PREVIEW_W//2, self.PREVIEW_H//2,
                                text="NO SIGNAL", fill="#2a2a3a",
                                font=(self.FONT, 28, "bold"), tags="nosignal")

        # ── Scrollable panel ──
        sc = tk.Canvas(left, bg=self.BG2, highlightthickness=0, width=self.PANEL_W)
        vsb = tk.Scrollbar(left, orient="vertical", command=sc.yview,
                           bg=self.BG2, troughcolor=self.BG3,
                           activebackground=self.AMBER_DIM)
        self.inner = tk.Frame(sc, bg=self.BG2)
        self.inner.bind("<Configure>",
                        lambda e: sc.configure(scrollregion=sc.bbox("all")))
        sc.create_window((0,0), window=self.inner, anchor="nw")
        sc.configure(yscrollcommand=vsb.set)
        sc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        sc.bind_all("<MouseWheel>",
                    lambda e: sc.yview_scroll(int(-1*(e.delta/120)), "units"))

        p = self.inner

        # ── Widget helpers ──────────────────────────────────

        def divider():
            tk.Frame(p, bg=self.BORDER, height=1).pack(fill=tk.X, pady=4)

        def section(text):
            tk.Label(p, text=f"  {text}",
                     bg=self.BG3, fg=self.AMBER,
                     font=(self.FONT, 8, "bold"),
                     anchor="w", pady=5).pack(fill=tk.X, pady=(10,0))
            tk.Frame(p, bg=self.AMBER, height=1).pack(fill=tk.X)

        def mk_spin(parent, lo, hi, var, inc=1, w=4, tooltip=""):
            sb = tk.Spinbox(parent, from_=lo, to=hi, textvariable=var,
                            increment=inc, width=w,
                            bg=self.BG3, fg=self.FG,
                            insertbackground=self.AMBER,
                            buttonbackground=self.BG3,
                            relief=tk.FLAT, font=(self.FONT, 10, "bold"),
                            highlightthickness=1,
                            highlightbackground=self.BORDER,
                            highlightcolor=self.AMBER)
            if tooltip: tip(sb, tooltip)
            return sb

        def lspin(label, lo, hi, var, inc=1, w=4, tooltip=""):
            f = tk.Frame(p, bg=self.BG2)
            f.pack(fill=tk.X, padx=10, pady=2)
            lbl = tk.Label(f, text=label, bg=self.BG2, fg=self.FG_DIM,
                           font=(self.FONT, 8), width=14, anchor="w")
            lbl.pack(side=tk.LEFT)
            if tooltip: tip(lbl, tooltip)
            sb = mk_spin(f, lo, hi, var, inc=inc, w=w, tooltip=tooltip)
            sb.pack(side=tk.LEFT, padx=4)
            return sb

        def lentry(label, var, show=None, tooltip=""):
            f = tk.Frame(p, bg=self.BG2)
            f.pack(fill=tk.X, padx=10, pady=2)
            lbl = tk.Label(f, text=label, bg=self.BG2, fg=self.FG_DIM,
                           font=(self.FONT, 8), width=14, anchor="w")
            lbl.pack(side=tk.LEFT)
            if tooltip: tip(lbl, tooltip)
            kw = {"show": show} if show else {}
            e = tk.Entry(f, textvariable=var, width=14,
                         bg=self.BG3, fg=self.FG,
                         insertbackground=self.AMBER,
                         relief=tk.FLAT, font=(self.FONT, 9),
                         highlightthickness=1,
                         highlightcolor=self.AMBER,
                         highlightbackground=self.BORDER, **kw)
            if tooltip: tip(e, tooltip)
            e.pack(side=tk.LEFT, fill=tk.X, expand=True)
            return e

        def pair_spins(lbl_l, lbl_r, lo, hi, var_l, var_r, tl="", tr=""):
            f = tk.Frame(p, bg=self.BG2)
            f.pack(fill=tk.X, padx=10, pady=2)
            ll = tk.Label(f, text=lbl_l, bg=self.BG2, fg=self.FG_DIM,
                          font=(self.FONT, 8), width=9, anchor="w")
            ll.pack(side=tk.LEFT)
            if tl: tip(ll, tl)
            sl = mk_spin(f, lo, hi, var_l, w=3, tooltip=tl)
            sl.pack(side=tk.LEFT, padx=(2,8))
            lr = tk.Label(f, text=lbl_r, bg=self.BG2, fg=self.FG_DIM,
                          font=(self.FONT, 8), width=5, anchor="w")
            lr.pack(side=tk.LEFT)
            if tr: tip(lr, tr)
            sr = mk_spin(f, lo, hi, var_r, w=3, tooltip=tr)
            sr.pack(side=tk.LEFT, padx=2)

        # ══════════════════════════════════════════════════════
        # CAMERA
        # ══════════════════════════════════════════════════════
        section("CAMERA")

        self._ip_var   = tk.StringVar(value=SETTINGS.camera_ip)
        self._usr_var  = tk.StringVar(value=SETTINGS.rtsp_user)
        self._pass_var = tk.StringVar(value=SETTINGS.rtsp_pass)
        self._str_var  = tk.StringVar(value=SETTINGS.rtsp_stream)
        self._pre_var  = tk.IntVar(value=SETTINGS.home_preset)

        lentry("Camera IP",   self._ip_var,
               tooltip="LAN IP of your PTZOptics camera. Default factory IP is 192.168.100.88")
        lentry("Username",    self._usr_var,   tooltip="RTSP username. Default: admin")
        lentry("Password",    self._pass_var,  show="*", tooltip="RTSP password. Default: admin")
        # Stream spinbox — 1 or 2 only
        sf = tk.Frame(p, bg=self.BG2)
        sf.pack(fill=tk.X, padx=10, pady=2)
        lbl_s = tk.Label(sf, text="Stream 1/2", bg=self.BG2, fg=self.FG_DIM,
                         font=(self.FONT, 8), width=14, anchor="w")
        lbl_s.pack(side=tk.LEFT)
        tip(lbl_s, "1 = main stream 1080p (more latency).\n2 = sub stream 720p (less latency). Recommended: 2")
        stream_sb = tk.Spinbox(sf, from_=1, to=2, textvariable=self._str_var,
                               width=3, bg=self.BG3, fg=self.FG,
                               insertbackground=self.AMBER,
                               buttonbackground=self.BG3,
                               relief=tk.FLAT, font=(self.FONT, 10, "bold"),
                               highlightthickness=1,
                               highlightbackground=self.BORDER,
                               highlightcolor=self.AMBER)
        stream_sb.pack(side=tk.LEFT, padx=4)
        tip(stream_sb, "1 = main stream 1080p (more latency).\n2 = sub stream 720p (less latency). Recommended: 2")
        lspin("Home Preset",  1, 9, self._pre_var,
              tooltip="Preset recalled when speaker is lost for 3+ seconds.")

        divider()

        # ── Tracking button ───────────────────────────────────
        divider()

        self._tracking_on = False

        def _on_track_click():
            if not (self._thread and self._thread.running):
                return
            self._tracking_on = not self._tracking_on
            self._thread.tracking = self._tracking_on
            if self._tracking_on:
                if self.tracker:
                    self.tracker.reset()
                self._track_btn.configure(
                    text="● TRACKING  ON",
                    bg=self.GREEN, fg="#000",
                    activebackground="#5fffaa")
            else:
                if self.visca:
                    self.visca.stop()
                    self.visca.zoom_stop()
                self._track_btn.configure(
                    text="○ TRACKING  OFF",
                    bg=self.BG3, fg=self.FG_DIM,
                    activebackground=self.GREEN)
                # Also release lock
                self._lock_active = False
                self._lock_btn.configure(
                    text="🔓  LOCK OFF",
                    bg=self.BG3, fg=self.FG_DIM)

        self._track_btn = tk.Button(p, text="○ TRACKING  OFF",
                                    command=_on_track_click,
                                    bg=self.BG3, fg=self.FG_DIM,
                                    font=(self.FONT, 11, "bold"),
                                    relief=tk.FLAT, cursor="hand2",
                                    activebackground=self.GREEN,
                                    activeforeground="#000",
                                    pady=10)
        self._track_btn.pack(fill=tk.X, padx=10, pady=(6, 3))
        tip(self._track_btn,
            "Start or stop auto-tracking.\nWhen ON the camera follows whoever is in frame.\nWhen OFF you have full manual control.")

        # ── Lock button ────────────────────────────────────────
        self._lock_active = False

        def _on_lock_click():
            if not (self._thread and self._thread.running and self._thread.tracking):
                return
            self._lock_active = not self._lock_active
            if self._lock_active:
                self._lock_btn.configure(
                    text="🔒  LOCKED ON",
                    bg=self.AMBER, fg="#000",
                    activebackground="#ffbe5c")
                print("[LOCK] Locked onto current subject")
            else:
                if self.detector:
                    self.detector.release_lock()
                self._lock_btn.configure(
                    text="🔓  LOCK OFF",
                    bg=self.BG3, fg=self.FG_DIM,
                    activebackground=self.AMBER)
                print("[LOCK] Unlocked")

        self._lock_btn = tk.Button(p, text="🔓  LOCK OFF",
                                   command=_on_lock_click,
                                   bg=self.BG3, fg=self.FG_DIM,
                                   font=(self.FONT, 11, "bold"),
                                   relief=tk.FLAT, cursor="hand2",
                                   activebackground=self.AMBER,
                                   activeforeground="#000",
                                   pady=10)
        self._lock_btn.pack(fill=tk.X, padx=10, pady=(3, 6))
        tip(self._lock_btn,
            "Lock onto the current person in frame.\nWhen locked, ignores everyone else.\nClick again to unlock.")

        self._start_btn = None
        self._stop_btn  = None

        # ══════════════════════════════════════════════════════
        # PAN / TILT
        # ══════════════════════════════════════════════════════
        section("PAN  /  TILT")

        # Vertical offset spinbox
        self._offset_var = tk.IntVar(value=SETTINGS.track_offset)
        of = tk.Frame(p, bg=self.BG2)
        of.pack(fill=tk.X, padx=10, pady=(0, 4))
        lbl_o = tk.Label(of, text="Vertical Offset", bg=self.BG2, fg=self.FG_DIM,
                         font=(self.FONT, 8), width=14, anchor="w")
        lbl_o.pack(side=tk.LEFT)
        tip(lbl_o, "Fine-tune aim point up or down.\n-7 = top of head\n+7 = feet\n0 = centered")
        offset_sb = tk.Spinbox(of, from_=-7, to=7, textvariable=self._offset_var,
                               width=4, bg=self.BG3, fg=self.FG,
                               insertbackground=self.AMBER,
                               buttonbackground=self.BG3,
                               relief=tk.FLAT, font=(self.FONT, 10, "bold"),
                               highlightthickness=1,
                               highlightbackground=self.BORDER,
                               highlightcolor=self.AMBER)
        offset_sb.pack(side=tk.LEFT, padx=4)
        tip(offset_sb, "Fine-tune aim point up or down.\n-7 = top of head\n+7 = feet\n0 = centered")

        self._pan_dead_v  = tk.DoubleVar(value=SETTINGS.pan_dead)
        self._tilt_dead_v = tk.DoubleVar(value=SETTINGS.tilt_dead)
        self._pan_slow_v  = tk.IntVar(value=SETTINGS.pan_slow)
        self._pan_fast_v  = tk.IntVar(value=SETTINGS.pan_fast)
        self._tilt_slow_v = tk.IntVar(value=SETTINGS.tilt_slow)
        self._tilt_fast_v = tk.IntVar(value=SETTINGS.tilt_fast)

        pair_spins("Pan  Slow", "Fast", 1, 24,
                   self._pan_slow_v, self._pan_fast_v,
                   tl="Pan speed when slightly off-center. Lower = smoother. 1-24.",
                   tr="Pan speed when far off-center. Higher = snappier. 1-24.")
        pair_spins("Tilt  Slow", "Fast", 1, 24,
                   self._tilt_slow_v, self._tilt_fast_v,
                   tl="Tilt speed when slightly above/below center. 1-24.",
                   tr="Tilt speed when far above/below center. 1-24.")

        # ══════════════════════════════════════════════════════
        # ZOOM
        # ══════════════════════════════════════════════════════
        section("ZOOM")

        self._zoom_en_v   = tk.BooleanVar(value=SETTINGS.zoom_enabled)
        self._zoom_tgt_v  = tk.IntVar(value=int(SETTINGS.zoom_target * 100))
        self._zoom_dead_v = tk.IntVar(value=int(SETTINGS.zoom_dead  * 100))
        self._zoom_spd_v  = tk.IntVar(value=SETTINGS.zoom_speed)

        zf = tk.Frame(p, bg=self.BG2)
        zf.pack(fill=tk.X, padx=10, pady=(4,2))
        self._zoom_cb = tk.Checkbutton(zf, text="  Enable Auto-Zoom",
                                       variable=self._zoom_en_v,
                                       bg=self.BG2, fg=self.FG,
                                       selectcolor=self.BG3,
                                       activebackground=self.BG2,
                                       font=(self.FONT, 9),
                                       command=self._on_zoom_toggle,
                                       cursor="hand2")
        self._zoom_cb.pack(side=tk.LEFT)
        tip(self._zoom_cb,
            "Automatically zoom in/out to keep subject filling the frame. Disable to zoom manually.")

        self._zoom_rows = []
        self._zoom_rows.append(
            lspin("Target Fill %", 20, 90, self._zoom_tgt_v,
                  tooltip="How much of the frame height the person occupies. 45 = zoomed out, 80 = zoomed in."))
        self._zoom_rows.append(
            lspin("Dead Zone %",   5,  40, self._zoom_dead_v,
                  tooltip="Tolerance before zooming starts. Higher = less zoom hunting. Recommended: 20"))
        self._zoom_rows.append(
            lspin("Zoom Speed",    0,  7,  self._zoom_spd_v,
                  tooltip="Motor speed for zoom. 0-7. Start at 1 for smooth motion."))
        self._on_zoom_toggle()

        # ══════════════════════════════════════════════════════
        # APPLY
        # ══════════════════════════════════════════════════════
        divider()
        btn_row_as = tk.Frame(p, bg=self.BG2)
        btn_row_as.pack(fill=tk.X, padx=10, pady=6)
        ab = tk.Button(btn_row_as, text="APPLY  SETTINGS",
                       command=self._apply_settings,
                       bg=self.BG3, fg=self.AMBER,
                       font=(self.FONT, 9, "bold"),
                       relief=tk.FLAT, cursor="hand2",
                       activebackground=self.AMBER_DIM,
                       activeforeground=self.FG, pady=7)
        ab.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
        tip(ab, "Push all current settings to the live tracker. Takes effect on next frame.")
        sb = tk.Button(btn_row_as, text="💾  SAVE",
                       command=lambda: [self._apply_settings(), SETTINGS.save()],
                       bg=self.BG3, fg=self.FG,
                       font=(self.FONT, 9, "bold"),
                       relief=tk.FLAT, cursor="hand2",
                       activebackground=self.GREEN,
                       activeforeground="#000", pady=7, padx=10)
        sb.pack(side=tk.LEFT)
        tip(sb, "Apply settings and save to disk immediately.")

        # ══════════════════════════════════════════════════════
        # PROFILES
        # ══════════════════════════════════════════════════════
        section("PROFILES")

        prof_row = tk.Frame(p, bg=self.BG2)
        prof_row.pack(fill=tk.X, padx=10, pady=(4,2))

        self._profile_var = tk.StringVar(value=PROFILE_MANAGER.current or "")
        prof_names = list(PROFILE_MANAGER.profiles.keys())
        self._profile_dd = tk.OptionMenu(prof_row, self._profile_var,
                                         *prof_names if prof_names else [""])
        self._profile_dd.configure(bg=self.BG3, fg=self.FG,
                                   activebackground=self.AMBER,
                                   activeforeground="#000",
                                   highlightthickness=0,
                                   relief=tk.FLAT,
                                   font=(self.FONT, 9))
        self._profile_dd["menu"].configure(bg=self.BG3, fg=self.FG,
                                            activebackground=self.AMBER,
                                            activeforeground="#000",
                                            font=(self.FONT, 9))
        self._profile_dd.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
        tip(self._profile_dd, "Select a saved profile to load.")

        load_prof_btn = tk.Button(prof_row, text="LOAD",
                                  command=self._load_profile,
                                  bg=self.BG3, fg=self.FG,
                                  font=(self.FONT, 8, "bold"),
                                  relief=tk.FLAT, cursor="hand2",
                                  activebackground=self.AMBER,
                                  activeforeground="#000",
                                  padx=8, pady=5)
        load_prof_btn.pack(side=tk.LEFT)
        tip(load_prof_btn, "Load the selected profile.")

        prof_row2 = tk.Frame(p, bg=self.BG2)
        prof_row2.pack(fill=tk.X, padx=10, pady=(2,6))

        self._new_profile_var = tk.StringVar()
        new_prof_entry = tk.Entry(prof_row2, textvariable=self._new_profile_var,
                                  width=14, bg=self.BG3, fg=self.FG,
                                  insertbackground=self.AMBER,
                                  relief=tk.FLAT, font=(self.FONT, 9),
                                  highlightthickness=1,
                                  highlightcolor=self.AMBER,
                                  highlightbackground=self.BORDER)
        new_prof_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
        tip(new_prof_entry, "Type a profile name then click SAVE.")

        save_prof_btn = tk.Button(prof_row2, text="SAVE",
                                  command=self._save_profile,
                                  bg=self.AMBER, fg="#000",
                                  font=(self.FONT, 8, "bold"),
                                  relief=tk.FLAT, cursor="hand2",
                                  activebackground="#ffbe5c",
                                  padx=8, pady=5)
        save_prof_btn.pack(side=tk.LEFT, padx=(0,2))
        tip(save_prof_btn, "Save current settings as a named profile.")

        del_prof_btn = tk.Button(prof_row2, text="DEL",
                                 command=self._delete_profile,
                                 bg=self.BG3, fg=self.RED,
                                 font=(self.FONT, 8, "bold"),
                                 relief=tk.FLAT, cursor="hand2",
                                 activebackground=self.RED,
                                 activeforeground="white",
                                 padx=8, pady=5)
        del_prof_btn.pack(side=tk.LEFT)
        tip(del_prof_btn, "Delete the selected profile.")

        # ══════════════════════════════════════════════════════
        # ADVANCED SETTINGS (collapsible)
        # ══════════════════════════════════════════════════════
        divider()
        self._adv_open = False
        self._adv_btn  = tk.Button(p, text="\u2699  ADVANCED  SETTINGS  \u25b8",
                                   command=self._toggle_advanced,
                                   bg=self.BG2, fg=self.FG_DIM,
                                   font=(self.FONT, 8, "bold"),
                                   relief=tk.FLAT, cursor="hand2",
                                   activebackground=self.BG3,
                                   activeforeground=self.FG,
                                   pady=5, anchor="w", padx=10)
        self._adv_btn.pack(fill=tk.X)
        tip(self._adv_btn, "Show/hide advanced tuning. Only change these if you know what you are doing.")

        self._adv_container = tk.Frame(p, bg=self.BG2)
        # not packed until toggled
        adv = self._adv_container

        def adv_sec(text):
            tk.Label(adv, text=f"  {text}",
                     bg=self.BG3, fg=self.AMBER,
                     font=(self.FONT, 8, "bold"),
                     anchor="w", pady=4).pack(fill=tk.X, pady=(6,0))
            tk.Frame(adv, bg=self.AMBER, height=1).pack(fill=tk.X)

        def adv_spin(label, lo, hi, var, inc=1, w=5, tooltip=""):
            f = tk.Frame(adv, bg=self.BG2)
            f.pack(fill=tk.X, padx=10, pady=2)
            lbl = tk.Label(f, text=label, bg=self.BG2, fg=self.FG_DIM,
                           font=(self.FONT, 8), width=16, anchor="w")
            lbl.pack(side=tk.LEFT)
            if tooltip: tip(lbl, tooltip)
            sb = tk.Spinbox(adv if False else f,
                            from_=lo, to=hi, textvariable=var,
                            increment=inc, width=w,
                            bg=self.BG3, fg=self.FG,
                            insertbackground=self.AMBER,
                            buttonbackground=self.BG3,
                            relief=tk.FLAT, font=(self.FONT, 10, "bold"),
                            highlightthickness=1,
                            highlightbackground=self.BORDER,
                            highlightcolor=self.AMBER)
            sb.pack(side=tk.LEFT, padx=4)
            if tooltip: tip(sb, tooltip)
            return sb

        adv_sec("DEAD ZONES")
        adv_spin("Pan Dead Zone",  0.02, 0.30, self._pan_dead_v,  inc=0.01, w=5,
                 tooltip="Fraction of frame where camera ignores small pan offsets. Default: 0.10. Higher = less twitching near center.")
        adv_spin("Tilt Dead Zone", 0.02, 0.30, self._tilt_dead_v, inc=0.01, w=5,
                 tooltip="Fraction of frame where camera ignores small tilt offsets. Default: 0.10. Higher = less twitching near center.")

        adv_sec("PREDICTION")
        self._lat_v = tk.DoubleVar(value=SETTINGS.latency_comp)
        adv_spin("Latency Comp",   0.0, 2.0,  self._lat_v,       inc=0.05, w=5,
                 tooltip="Seconds of look-ahead to compensate for RTSP delay. Default: 0.40. Too high = camera oscillates.")

        adv_sec("TIMING")
        self._lost_v = tk.DoubleVar(value=SETTINGS.lost_timeout)
        adv_spin("Lost Timeout s", 1.0, 10.0, self._lost_v,       inc=0.5,  w=5,
                 tooltip="Seconds before camera returns to home preset when speaker is lost. Default: 3.0")

        tk.Label(adv, bg=self.BG2).pack(pady=4)
        tk.Label(p,   bg=self.BG2).pack(pady=6)


    def _on_zoom_toggle(self):
        state = tk.NORMAL if self._zoom_en_v.get() else tk.DISABLED
        for w in self._zoom_rows:
            try:
                w.configure(state=state)
            except Exception:
                pass

    # ── Start / Stop ────────────────────────────────────────

    def _on_start(self):
        """Start stream thread. Called once at app launch."""
        if self._thread and self._thread.running:
            return
        self._apply_settings()
        self._thread = TrackerThread(self)
        self._thread.start()
        print("[INFO] Stream started")

    def _on_stop(self):
        if self._thread:
            self._thread.tracking = False
            self._thread.stop()
        # Reset both pills to off
        if hasattr(self, '_stream_pill'):
            self._stream_pill["set"](False)
        if hasattr(self, '_lock_pill'):
            self._lock_pill["set"](False)
        self.status_var.set("● OFFLINE")
        if hasattr(self, '_status_lbl'):
            self._status_lbl.configure(fg=self.FG_DIM)

    def _on_toggle_tracking(self):
        """Legacy — now handled by lock pill directly."""
        pass

    # ── Apply settings ──────────────────────────────────────

    def _apply_settings(self):
        SETTINGS.camera_ip    = self._ip_var.get().strip()
        SETTINGS.rtsp_user    = self._usr_var.get().strip()
        SETTINGS.rtsp_pass    = self._pass_var.get().strip()
        SETTINGS.rtsp_stream  = self._str_var.get().strip()
        SETTINGS.home_preset  = self._pre_var.get()
        SETTINGS.pan_dead     = self._pan_dead_v.get()
        SETTINGS.tilt_dead    = self._tilt_dead_v.get()
        SETTINGS.pan_near     = SETTINGS.pan_dead  + 0.15
        SETTINGS.tilt_near    = SETTINGS.tilt_dead + 0.15
        SETTINGS.pan_slow     = self._pan_slow_v.get()
        SETTINGS.pan_fast     = self._pan_fast_v.get()
        SETTINGS.tilt_slow    = self._tilt_slow_v.get()
        SETTINGS.tilt_fast    = self._tilt_fast_v.get()
        SETTINGS.zoom_enabled = self._zoom_en_v.get()
        SETTINGS.zoom_target  = self._zoom_tgt_v.get() / 100.0
        SETTINGS.zoom_dead    = self._zoom_dead_v.get() / 100.0
        SETTINGS.zoom_speed   = self._zoom_spd_v.get()
        SETTINGS.latency_comp = self._lat_v.get()
        SETTINGS.lost_timeout = self._lost_v.get()
        SETTINGS.track_offset = self._offset_var.get()
        # Restart stream if connection settings changed
        if self._thread and self._thread.running:
            new_url = f"rtsp://{SETTINGS.rtsp_user}:{SETTINGS.rtsp_pass}@{SETTINGS.camera_ip}/{SETTINGS.rtsp_stream}"
            old_url = getattr(self, '_last_url', None)
            if new_url != old_url:
                print("[INFO] Connection settings changed — restarting stream...")
                self._thread.tracking = False
                self._thread.stop()
                self._thread = None
                self._last_url = new_url
                self.root.after(800, self._on_start)
        self._last_url = f"rtsp://{SETTINGS.rtsp_user}:{SETTINGS.rtsp_pass}@{SETTINGS.camera_ip}/{SETTINGS.rtsp_stream}"
        SETTINGS.save()
        print(f"[SETTINGS] Applied — IP:{SETTINGS.camera_ip}  "
              f"Pan slow:{SETTINGS.pan_slow} fast:{SETTINGS.pan_fast}  "
              f"Zoom:{'ON' if SETTINGS.zoom_enabled else 'OFF'} "
              f"tgt:{SETTINGS.zoom_target:.2f} spd:{SETTINGS.zoom_speed}")

    # ── Preset recall ────────────────────────────────────────

    def _recall_preset(self, n):
        if self.visca:
            self.visca.recall_preset(n)
            print(f"[PRESET] Recalled {n}")



    # ── Preview update loop ──────────────────────────────────

    def _update_preview(self):
        try:
            if self._thread and self._thread.latest_frame is not None:
                with self._thread._frame_lock:
                    frame = self._thread.latest_frame.copy()

                detection = self._thread.latest_detection
                h, w      = frame.shape[:2]

                # Draw crosshair
                cv2.line(frame, (w//2 - 20, h//2), (w//2 + 20, h//2), (0,255,0), 1)
                cv2.line(frame, (w//2, h//2 - 20), (w//2, h//2 + 20), (0,255,0), 1)

                # Draw detection box
                if detection:
                    dcx, dcy, dw, dh = detection
                    x0 = int((dcx - dw/2) * w)
                    y0 = int((dcy - dh/2) * h)
                    x1 = int((dcx + dw/2) * w)
                    y1 = int((dcy + dh/2) * h)
                    cv2.rectangle(frame, (x0,y0), (x1,y1), (0,200,255), 2)
                    cv2.circle(frame, (int(dcx*w), int(dcy*h)), 5, (0,200,255), -1)

                # Status overlay
                status = self._thread.status if self._thread else "STOPPED"
                color  = (0,255,0) if status == "TRACKING" else (0,165,255)
                cv2.putText(frame, status, (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

                zoom_lbl = ""
                if self._thread and self.tracker:
                    z = self.tracker._prev_zoom
                    zoom_lbl = "ZOOM IN" if z==1 else ("ZOOM OUT" if z==-1 else "")
                if zoom_lbl:
                    cv2.putText(frame, zoom_lbl, (10, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,200,0), 1, cv2.LINE_AA)

                # Resize to preview
                cw = max(self.canvas.winfo_width(), self.PREVIEW_W)
                ch = max(self.canvas.winfo_height(), self.PREVIEW_H)
                display = cv2.resize(frame, (cw, ch))
                img     = Image.fromarray(cv2.cvtColor(display, cv2.COLOR_BGR2RGB))
                imgtk   = ImageTk.PhotoImage(image=img)
                self.canvas.imgtk = imgtk
                self.canvas.delete('all')
                self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)

                # Update status bar
                st = self._thread.status if self._thread else "STOPPED"
                if st == "TRACKING":
                    self.status_var.set("\u25cf TRACKING")
                    self._status_lbl.configure(fg=self.GREEN)
                elif st == "PAUSED":
                    self.status_var.set("\u25cf PAUSED")
                    self._status_lbl.configure(fg=self.AMBER)
                else:
                    self.status_var.set("\u25cf OFFLINE")
                    self._status_lbl.configure(fg=self.FG_DIM)

        except Exception as e:
            pass

        self.root.after(33, self._update_preview)  # ~30fps

    def _toggle_advanced(self):
        self._adv_open = not self._adv_open
        if self._adv_open:
            self._adv_container.pack(fill=tk.X)
            self._adv_btn.configure(text="⚙  ADVANCED  SETTINGS  ▾")
        else:
            self._adv_container.pack_forget()
            self._adv_btn.configure(text="⚙  ADVANCED  SETTINGS  ▸")

    def _toggle_fullscreen(self, event=None):
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)

    def _exit_fullscreen(self, event=None):
        if self._fullscreen:
            self._fullscreen = False
            self.root.attributes("-fullscreen", False)

    # ── Profiles ─────────────────────────────────────────────

    def _refresh_profile_dropdown(self):
        menu = self._profile_dd["menu"]
        menu.delete(0, "end")
        for name in PROFILE_MANAGER.profiles:
            menu.add_command(label=name,
                             command=lambda n=name: self._profile_var.set(n))
        if not PROFILE_MANAGER.profiles:
            menu.add_command(label="(no profiles)")

    def _save_profile(self):
        name = self._new_profile_var.get().strip()
        if not name:
            return
        self._apply_settings()
        PROFILE_MANAGER.save_profile(name)
        self._new_profile_var.set("")
        self._profile_var.set(name)
        self._refresh_profile_dropdown()

    def _load_profile(self):
        name = self._profile_var.get()
        if not name or name not in PROFILE_MANAGER.profiles:
            return
        PROFILE_MANAGER.load_profile(name)
        # Refresh all UI vars from SETTINGS
        self._ip_var.set(SETTINGS.camera_ip)
        self._usr_var.set(SETTINGS.rtsp_user)
        self._pass_var.set(SETTINGS.rtsp_pass)
        self._str_var.set(SETTINGS.rtsp_stream)
        self._pre_var.set(SETTINGS.home_preset)
        self._pan_slow_v.set(SETTINGS.pan_slow)
        self._pan_fast_v.set(SETTINGS.pan_fast)
        self._tilt_slow_v.set(SETTINGS.tilt_slow)
        self._tilt_fast_v.set(SETTINGS.tilt_fast)
        self._pan_dead_v.set(SETTINGS.pan_dead)
        self._tilt_dead_v.set(SETTINGS.tilt_dead)
        self._zoom_en_v.set(SETTINGS.zoom_enabled)
        self._zoom_tgt_v.set(int(SETTINGS.zoom_target * 100))
        self._zoom_dead_v.set(int(SETTINGS.zoom_dead * 100))
        self._zoom_spd_v.set(SETTINGS.zoom_speed)
        self._lat_v.set(SETTINGS.latency_comp)
        self._lost_v.set(SETTINGS.lost_timeout)
        self._offset_var.set(SETTINGS.track_offset)
        print(f"[PROFILE] UI refreshed for: {name}")

    def _delete_profile(self):
        name = self._profile_var.get()
        if not name or name not in PROFILE_MANAGER.profiles:
            return
        PROFILE_MANAGER.delete_profile(name)
        self._profile_var.set("")
        self._refresh_profile_dropdown()

    def on_close(self):
        SETTINGS.save()
        self._on_stop()
        time.sleep(0.3)
        self.root.destroy()


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main():
    # Check Pillow
    try:
        from PIL import Image, ImageTk
    except ImportError:
        sys.exit("ERROR: pip install Pillow")

    root = tk.Tk()
    app  = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
