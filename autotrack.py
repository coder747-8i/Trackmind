#!/usr/bin/env python3
"""
Trackmind: Auto Tracker with Control Panel UI
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
import urllib.request
import urllib.error
import subprocess
import tempfile
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


def _read_version():
    if getattr(sys, 'frozen', False):
        bases = [sys._MEIPASS]
    else:
        bases = [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
    for base in bases:
        try:
            with open(os.path.join(base, "version.txt")) as f:
                ver = f.read().strip().lstrip("v")
                if ver:
                    return ver
        except Exception:
            pass
    return "unknown"

VERSION = _read_version()
GITHUB_REPO = "coder747-8i/Trackmind"  # ← update this

# ─────────────────────────────────────────────────────────────
# Shared live settings (read by tracker thread, written by UI)
# ─────────────────────────────────────────────────────────────

class Settings:
    def __init__(self):
        self.camera_ip    = ""
        self.rtsp_user    = ""
        self.rtsp_pass    = ""
        self.rtsp_stream  = "2"
        self.visca_port   = 5678
        self.home_preset  = 0

        self.pan_dead     = 0.17
        self.pan_near     = 0.32
        self.pan_slow     = 2
        self.pan_fast     = 5
        self.tilt_dead    = 0.17
        self.tilt_near    = 0.32
        self.tilt_slow    = 2
        self.tilt_fast    = 5

        self.zoom_enabled = False
        self.zoom_target  = 0.45
        self.zoom_dead    = 0.20
        self.zoom_speed   = 1

        self.latency_comp = 0.4
        self.lost_timeout = 2.0

        self.track_focus  = 'upper'
        self.track_offset = 2

    # ── Persistence ─────────────────────────────────────────

    @staticmethod
    def _system_user():
        return (os.environ.get('USERNAME') or os.environ.get('USER') or 'default').lower()

    @staticmethod
    def _config_dir():
        base = os.path.expanduser("~/.trackmind")
        user_dir = os.path.join(base, Settings._system_user())
        os.makedirs(user_dir, exist_ok=True)
        return user_dir

    @staticmethod
    def _config_path():
        return os.path.join(Settings._config_dir(), "config.json")

    @staticmethod
    def is_first_run():
        return not os.path.exists(Settings._config_path())

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

    def to_dict(self):
        return {
            "camera_ip": self.camera_ip, "rtsp_user": self.rtsp_user,
            "rtsp_pass": self.rtsp_pass, "rtsp_stream": self.rtsp_stream,
            "home_preset": self.home_preset,
            "pan_dead": self.pan_dead, "pan_slow": self.pan_slow, "pan_fast": self.pan_fast,
            "tilt_dead": self.tilt_dead, "tilt_slow": self.tilt_slow, "tilt_fast": self.tilt_fast,
            "zoom_enabled": self.zoom_enabled, "zoom_target": self.zoom_target,
            "zoom_dead": self.zoom_dead, "zoom_speed": self.zoom_speed,
            "latency_comp": self.latency_comp, "lost_timeout": self.lost_timeout,
            "track_offset": self.track_offset,
        }


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
        return os.path.join(Settings._config_dir(), "profiles.json")

    def _settings_dict(self):
        return SETTINGS.to_dict()

    def list_profiles(self):
        return list(self.profiles.keys())

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
# Auto-Updater
# ─────────────────────────────────────────────────────────────

class Updater:
    """
    Checks GitHub releases API for a newer version.
    Auto-check on launch is silent when up to date.
    Manual check always gives feedback.
    """

    RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

    def __init__(self, app):
        self.app             = app
        self._latest_ver     = None
        self._install_url    = None
        self._last_check_time = None

    def check_async(self, manual=False):
        """Run update check in a background thread — never blocks UI."""
        if manual:
            self.app.status_var.set("CHECKING...")
            self.app._status_lbl.configure(fg=AMBER)
        t = threading.Thread(target=self._check, args=(manual,), daemon=True)
        t.start()

    def _check(self, manual=False):
        self._last_check_time = time.time()
        self.app.root.after(0, self._update_check_time_label)
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "TrackMind"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())

            tag = data.get("tag_name", "").lstrip("v")
            if not tag:
                if manual:
                    self.app.root.after(0, lambda: self._notify_uptodate())
                return

            def ver_tuple(v):
                try:
                    return tuple(int(x) for x in v.split("."))
                except Exception:
                    return (0,)

            if ver_tuple(tag) <= ver_tuple(VERSION):
                print(f"[UPDATE] Up to date (v{VERSION})")
                if manual:
                    self.app.root.after(0, lambda: self._notify_uptodate())
                else:
                    self.app.root.after(0, self._restore_status)
                return

            # Find installer .exe asset
            assets = data.get("assets", [])
            install_url = None
            for asset in assets:
                aname = asset.get("name", "")
                if aname.lower().endswith(".exe") and "setup" in aname.lower():
                    install_url = asset.get("browser_download_url")
                    break

            self._latest_ver  = tag
            self._install_url = install_url
            print(f"[UPDATE] New version available: v{tag}")
            self.app.root.after(0, lambda: self._prompt(tag, install_url))

        except Exception as e:
            print(f"[UPDATE] Check failed: {e}")
            if manual:
                self.app.root.after(0, lambda: self._notify_error(str(e)))
            else:
                self.app.root.after(0, self._restore_status)

    def _update_check_time_label(self):
        if hasattr(self.app, '_last_check_lbl') and self._last_check_time:
            import datetime
            t = datetime.datetime.fromtimestamp(self._last_check_time)
            self.app._last_check_lbl.configure(
                text=f"Last checked:  {t.strftime('%b %d  %I:%M %p')}")

    def _restore_status(self):
        """Reset status bar to current tracker state after a silent background check."""
        try:
            st = self.app._thread.status if self.app._thread else "STOPPED"
        except Exception:
            st = "STOPPED"
        if st == "TRACKING":
            self.app.status_var.set("TRACKING")
            self.app._status_lbl.configure(fg=GREEN)
        elif st == "PAUSED":
            self.app.status_var.set("PAUSED")
            self.app._status_lbl.configure(fg=AMBER)
        else:
            self.app.status_var.set("OFFLINE")
            self.app._status_lbl.configure(fg=FG_DIM)

    def _notify_uptodate(self):
        self._restore_status()
        messagebox.showinfo(
            "TrackMind — Up to Date",
            f"You are running the latest version (v{VERSION})."
        )

    def _notify_error(self, err):
        self._restore_status()
        messagebox.showwarning(
            "TrackMind — Update Check Failed",
            f"Could not reach GitHub to check for updates.\n\n{err}\n\n"
            f"Check manually at:\n{self.RELEASES_URL}"
        )

    def _prompt(self, tag, install_url):
        self._restore_status()
        if install_url:
            result = messagebox.askyesno(
                "TrackMind — Update Available",
                f"Version {tag} is available  (you have v{VERSION}).\n\n"
                f"Click Yes to download and install now.\n"
                f"TrackMind will close and relaunch automatically.",
                icon="info"
            )
            if result:
                self._download_and_install(install_url)
        else:
            messagebox.showinfo(
                "TrackMind — Update Available",
                f"Version {tag} is available  (you have v{VERSION}).\n\n"
                f"No installer asset was found on this release.\n"
                f"Download it manually from:\n{self.RELEASES_URL}"
            )

    def _download_and_install(self, url):
        try:
            self.app.status_var.set("DOWNLOADING UPDATE...")
            self.app._status_lbl.configure(fg=AMBER)
            self.app.root.update()

            tmp = tempfile.NamedTemporaryFile(suffix="_Trackmind_Setup.exe", delete=False)
            tmp_path = tmp.name
            tmp.close()

            def reporthook(count, block_size, total_size):
                if total_size > 0:
                    pct = int(count * block_size * 100 / total_size)
                    self.app.status_var.set(f"DOWNLOADING... {min(pct, 100)}%")
                    self.app.root.update()

            urllib.request.urlretrieve(url, tmp_path, reporthook)

            self.app.status_var.set("INSTALLING...")
            self.app.root.update()

            subprocess.Popen([tmp_path, "/S"])
            self.app.root.after(1500, self.app.on_close)

        except Exception as e:
            messagebox.showerror(
                "Update Failed",
                f"Could not download update:\n{e}\n\n"
                f"Download manually from:\n{self.RELEASES_URL}"
            )
            self._restore_status()


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


# ─────────────────────────────────────────────────────────────
# Tooltip helper
# ─────────────────────────────────────────────────────────────

class Tooltip:
    def __init__(self, widget, text):
        self.tip  = None
        self.text = text
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, e=None):
        w = e.widget if e else None
        if w is None:
            return
        x = w.winfo_rootx() + 20
        y = w.winfo_rooty() + w.winfo_height() + 4
        self.tip = tk.Toplevel(w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text,
                 bg="#1e1a0e", fg=AMBER,
                 font=(FONT, 8),
                 relief=tk.FLAT, padx=8, pady=4,
                 wraplength=260, justify=tk.LEFT).pack()

    def _hide(self, e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def tip(widget, text):
    Tooltip(widget, text)


# ─────────────────────────────────────────────────────────────
# Setup Wizard
# ─────────────────────────────────────────────────────────────

class SetupWizard(tk.Toplevel):
    STEPS = 6

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("TrackMind — First Time Setup")
        self.resizable(False, False)
        self.geometry("500x400")
        self.configure(bg=BG)
        self.grab_set()

        self._step     = 0
        self._ip_var   = tk.StringVar(value=SETTINGS.camera_ip)
        self._usr_var  = tk.StringVar(value=SETTINGS.rtsp_user  or "admin")
        self._pass_var = tk.StringVar(value=SETTINGS.rtsp_pass  or "admin")
        self._pre_var  = tk.IntVar(value=SETTINGS.home_preset)
        self._dead_var = tk.DoubleVar(value=SETTINGS.pan_dead if SETTINGS.pan_dead else 0.17)

        self._content   = tk.Frame(self, bg=BG)
        self._content.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        self._nav_frame = tk.Frame(self, bg=BG)
        self._nav_frame.pack(fill=tk.X, padx=30, pady=(0, 20))

        self.update_idletasks()
        px = app.root.winfo_x() + app.root.winfo_width()  // 2 - 250
        py = app.root.winfo_y() + app.root.winfo_height() // 2 - 200
        self.geometry(f"500x400+{px}+{py}")
        self._draw_step()

    def _clear(self):
        for w in self._content.winfo_children():   w.destroy()
        for w in self._nav_frame.winfo_children():  w.destroy()

    def _step_hdr(self, n):
        tk.Label(self._content, text=f"Step {n} of {self.STEPS - 1}",
                 bg=BG, fg=FG_DIM, font=(FONT, 8)).pack(anchor="w")
        tk.Frame(self._content, bg=AMBER, height=1).pack(fill=tk.X, pady=(2, 10))

    def _title(self, t):
        tk.Label(self._content, text=t, bg=BG, fg=AMBER,
                 font=(FONT, 14, "bold"), wraplength=420, justify="left").pack(anchor="w", pady=(0, 4))

    def _sub(self, t):
        tk.Label(self._content, text=t, bg=BG, fg=FG_DIM,
                 font=(FONT, 9), wraplength=420, justify="left").pack(anchor="w", pady=(0, 14))

    def _entry(self, var, show=None):
        kw = {"show": show} if show else {}
        e = tk.Entry(self._content, textvariable=var, width=28,
                     bg=BG3, fg=FG, insertbackground=AMBER,
                     relief=tk.FLAT, font=(FONT, 10),
                     highlightthickness=1, highlightcolor=AMBER,
                     highlightbackground=BORDER, **kw)
        e.pack(anchor="w", pady=4)
        return e

    def _spinbox(self, lo, hi, var, inc=1, fmt=None):
        kw = {"format": fmt} if fmt else {}
        sb = tk.Spinbox(self._content, from_=lo, to=hi, textvariable=var,
                        increment=inc, width=10, bg=BG3, fg=FG,
                        insertbackground=AMBER, buttonbackground=BG3,
                        relief=tk.FLAT, font=(FONT, 12, "bold"),
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=AMBER, **kw)
        sb.pack(anchor="w", pady=4)
        return sb

    def _nav(self, show_back=True, next_text="Next →", next_cmd=None):
        if show_back:
            tk.Button(self._nav_frame, text="← Back", command=self._prev,
                      bg=BG3, fg=FG_DIM, font=(FONT, 10, "bold"),
                      relief=tk.FLAT, cursor="hand2",
                      activebackground=BG3, activeforeground=FG,
                      padx=14, pady=8).pack(side=tk.LEFT)
        tk.Button(self._nav_frame, text=next_text,
                  command=next_cmd or self._next,
                  bg=AMBER, fg="#000", font=(FONT, 10, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground="#ffbe5c",
                  padx=14, pady=8).pack(side=tk.RIGHT)

    def _draw_step(self):
        self._clear()
        s = self._step
        if s == 0:
            tk.Label(self._content, text="", bg=BG).pack(pady=20)
            tk.Label(self._content, text="Welcome to TrackMind",
                     bg=BG, fg=AMBER, font=(FONT, 18, "bold")).pack()
            tk.Label(self._content, text="Let's get your camera connected.",
                     bg=BG, fg=FG_DIM, font=(FONT, 10)).pack(pady=8)
            self._nav(show_back=False, next_text="Begin →")
        elif s == 1:
            self._step_hdr(1)
            self._title("What is your camera's IP address?")
            self._sub("Find this in your camera's web interface or router.\nExample: 192.168.1.10")
            tk.Label(self._content, text="IP Address:", bg=BG, fg=FG, font=(FONT, 9)).pack(anchor="w")
            self._entry(self._ip_var)
            self._nav()
        elif s == 2:
            self._step_hdr(2)
            self._title("Camera login credentials")
            self._sub("Username and password for RTSP/VISCA access.\nDefault is usually admin / admin.")
            tk.Label(self._content, text="Username:", bg=BG, fg=FG, font=(FONT, 9)).pack(anchor="w")
            self._entry(self._usr_var)
            tk.Label(self._content, text="Password:", bg=BG, fg=FG, font=(FONT, 9)).pack(anchor="w")
            self._entry(self._pass_var, show="*")
            self._nav()
        elif s == 3:
            self._step_hdr(3)
            self._title("Home position preset")
            self._sub("When tracking is lost, the camera returns to this preset.\nSet 0 if you haven't configured presets.")
            tk.Label(self._content, text="Home Preset (0–89):", bg=BG, fg=FG, font=(FONT, 9)).pack(anchor="w")
            self._spinbox(0, 89, self._pre_var)
            self._nav()
        elif s == 4:
            self._step_hdr(4)
            self._title("Tracking sensitivity")
            self._sub("The dead zone is how much the subject can drift before the camera follows.\nLarger = steadier. 0.17 recommended.")
            tk.Label(self._content, text="Dead Zone (0.05–0.30):", bg=BG, fg=FG, font=(FONT, 9)).pack(anchor="w")
            self._spinbox(0.05, 0.30, self._dead_var, inc=0.01, fmt="%.2f")
            self._nav()
        elif s == 5:
            tk.Label(self._content, text="", bg=BG).pack(pady=10)
            tk.Label(self._content, text="You're all set!",
                     bg=BG, fg=GREEN, font=(FONT, 18, "bold")).pack()
            tk.Label(self._content, text="Click Finish to start TrackMind.",
                     bg=BG, fg=FG_DIM, font=(FONT, 10)).pack(pady=8)
            self._nav(next_text="Finish", next_cmd=self._finish)

    def _next(self):
        if self._step < self.STEPS - 1:
            self._step += 1
            self._draw_step()

    def _prev(self):
        if self._step > 0:
            self._step -= 1
            self._draw_step()

    def _finish(self):
        SETTINGS.camera_ip   = self._ip_var.get().strip()
        SETTINGS.rtsp_user   = self._usr_var.get().strip()
        SETTINGS.rtsp_pass   = self._pass_var.get().strip()
        SETTINGS.home_preset = self._pre_var.get()
        dead = self._dead_var.get()
        SETTINGS.pan_dead  = dead;  SETTINGS.tilt_dead  = dead
        SETTINGS.pan_near  = dead + 0.15; SETTINGS.tilt_near = dead + 0.15
        SETTINGS.save()
        self.app._refresh_ui_from_settings()
        self.grab_release()
        self.destroy()


# ─────────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────────

class App:
    PANEL_W   = 200
    PREVIEW_W = 720
    PREVIEW_H = 405

    BG = BG; BG2 = BG2; BG3 = BG3; BORDER = BORDER
    AMBER = AMBER; AMBER_DIM = AMBER_DIM; RED = RED; GREEN = GREEN
    FG = FG; FG_DIM = FG_DIM; FONT = FONT

    def __init__(self, root):
        self.root = root
        self.root.title("TrackMind — Intelligent PTZ Auto-Tracking")
        self.root.resizable(True, True)
        self.root.configure(bg=BG)
        self._fullscreen       = False
        self._settings_visible = False
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", self._exit_fullscreen)

        self.visca    = None
        self.detector = None
        self.tracker  = None
        self._thread  = None

        try:
            base = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base, "trackmind_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self._build_ui()
        self._update_preview()
        self.root.after(500, self._on_start)
        self._updater = Updater(self)
        self.root.after(3000, self._updater.check_async)
        if SETTINGS.is_first_run():
            self.root.after(200, self._run_setup_wizard)

    # ── Logo ─────────────────────────────────────────────────

    def _draw_logo(self, c, size=28):
        cx = cy = size // 2
        r  = cx - 2
        r2 = int(r * 0.71)
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=AMBER, width=1)
        c.create_oval(cx-r2, cy-r2, cx+r2, cy+r2, outline=AMBER, fill="#08080f", width=1)
        gap = 3
        for x1,y1,x2,y2 in [(cx,cy-r,cx,cy-gap),(cx,cy+gap,cx,cy+r),
                              (cx-r,cy,cx-gap,cy),(cx+gap,cy,cx+r,cy)]:
            c.create_line(x1,y1,x2,y2, fill=AMBER, width=1)
        arm = max(4, size // 7)
        for bx,by,dx,dy in [(cx-r2,cy-r2,-1,-1),(cx+r2,cy-r2,1,-1),
                              (cx-r2,cy+r2,-1,1),(cx+r2,cy+r2,1,1)]:
            c.create_line(bx,by,bx+dx*arm,by, fill=AMBER, width=1)
            c.create_line(bx,by,bx,by+dy*arm, fill=AMBER, width=1)
        dot = max(2, size // 14)
        c.create_oval(cx-dot,cy-dot,cx+dot,cy+dot, fill=AMBER, outline="")

    # ── Build UI ─────────────────────────────────────────────

    def _build_ui(self):

        # ── Initialise all shared Vars before any panel is built ──
        self._ip_var       = tk.StringVar(value=SETTINGS.camera_ip)
        self._usr_var      = tk.StringVar(value=SETTINGS.rtsp_user)
        self._pass_var     = tk.StringVar(value=SETTINGS.rtsp_pass)
        self._str_var      = tk.StringVar(value=SETTINGS.rtsp_stream)
        self._pre_var      = tk.IntVar(value=SETTINGS.home_preset)
        self._offset_v     = tk.IntVar(value=SETTINGS.track_offset)
        self._pan_dead_v   = tk.DoubleVar(value=SETTINGS.pan_dead)
        self._pan_slow_v   = tk.IntVar(value=SETTINGS.pan_slow)
        self._pan_fast_v   = tk.IntVar(value=SETTINGS.pan_fast)
        self._tilt_dead_v  = tk.DoubleVar(value=SETTINGS.tilt_dead)
        self._tilt_slow_v  = tk.IntVar(value=SETTINGS.tilt_slow)
        self._tilt_fast_v  = tk.IntVar(value=SETTINGS.tilt_fast)
        self._zoom_en_v    = tk.BooleanVar(value=SETTINGS.zoom_enabled)
        self._zoom_tgt_v   = tk.IntVar(value=int(SETTINGS.zoom_target * 100))
        self._zoom_dead_v  = tk.IntVar(value=int(SETTINGS.zoom_dead  * 100))
        self._zoom_spd_v   = tk.IntVar(value=SETTINGS.zoom_speed)
        self._lat_v        = tk.DoubleVar(value=SETTINGS.latency_comp)
        self._lost_v       = tk.DoubleVar(value=SETTINGS.lost_timeout)
        self._profile_var     = tk.StringVar(value=PROFILE_MANAGER.current or "")
        self._new_profile_var = tk.StringVar()

        # ═══ Header bar ══════════════════════════════════════
        header = tk.Frame(self.root, bg=BG2, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        logo_c = tk.Canvas(header, width=28, height=28, bg=BG2, highlightthickness=0)
        logo_c.pack(side=tk.LEFT, padx=(12, 4), pady=10)
        self._draw_logo(logo_c, size=28)

        tk.Label(header, text="TRACKMIND", bg=BG2, fg=AMBER,
                 font=(FONT, 12, "bold")).pack(side=tk.LEFT, padx=(0, 4), pady=8)
        tk.Label(header, text="intelligent ptz auto-tracking", bg=BG2, fg=FG_DIM,
                 font=(FONT, 8)).pack(side=tk.LEFT, padx=4)

        self.status_var  = tk.StringVar(value="OFFLINE")
        self._status_lbl = tk.Label(header, textvariable=self.status_var,
                                    bg=BG2, fg=FG_DIM, font=(FONT, 10, "bold"))

        # Settings gear button — top-right, rightmost in header
        self._settings_btn = tk.Button(header, text="⚙  SETTINGS",
                                       command=self._toggle_settings,
                                       bg=BG2, fg=FG_DIM,
                                       font=(FONT, 9, "bold"),
                                       relief=tk.FLAT, cursor="hand2",
                                       activebackground=AMBER_DIM,
                                       activeforeground=FG,
                                       padx=10, pady=6)
        self._settings_btn.pack(side=tk.RIGHT, padx=(0, 8))
        tip(self._settings_btn, "Open settings panel.")
        self._status_lbl.pack(side=tk.RIGHT, padx=(0, 16))

        tk.Frame(self.root, bg=AMBER, height=2).pack(fill=tk.X)

        # ═══ Body ════════════════════════════════════════════
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Left panel (fixed, no scroll) ─────────────────
        left = tk.Frame(body, bg=BG2, width=self.PANEL_W)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # ── Right area (camera view OR settings view) ──────
        self._right = tk.Frame(body, bg=BG)
        self._right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Camera frame
        self._camera_frame = tk.Frame(self._right, bg=BG)
        self._camera_frame.pack(fill=tk.BOTH, expand=True)
        cb = tk.Frame(self._camera_frame, bg=BORDER, padx=1, pady=1)
        cb.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self.canvas = tk.Canvas(cb, bg="#050508", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_text(self.PREVIEW_W//2, self.PREVIEW_H//2,
                                text="NO SIGNAL", fill="#2a2a3a",
                                font=(FONT, 28, "bold"), tags="nosignal")

        # Settings frame — overlay placed on top of camera via place()
        self._settings_frame = tk.Frame(self._right, bg=BG2,
                                        highlightthickness=2,
                                        highlightbackground=AMBER)
        self._build_settings_panel(self._settings_frame)
        # shown on demand with place(); camera always remains beneath

        # ── Build left panel contents ─────────────────────
        p = left

        # ── Status dot ────────────────────────────────────
        top_row = tk.Frame(p, bg=BG2)
        top_row.pack(fill=tk.X, padx=6, pady=(8, 4))

        self._panel_status_lbl = tk.Label(top_row, text="● OFFLINE",
                                          bg=BG2, fg=FG_DIM,
                                          font=(FONT, 8, "bold"))
        self._panel_status_lbl.pack(side=tk.LEFT)

        tk.Frame(p, bg=AMBER, height=1).pack(fill=tk.X)

        # ── Camera connection fields ───────────────────────

        def stacked(label_text, var, show=None, tooltip_text=""):
            f = tk.Frame(p, bg=BG2)
            f.pack(fill=tk.X, padx=8, pady=(4, 0))
            lbl = tk.Label(f, text=label_text, bg=BG2, fg=FG_DIM,
                           font=(FONT, 7), anchor="w")
            lbl.pack(fill=tk.X)
            if tooltip_text: tip(lbl, tooltip_text)
            kw = {"show": show} if show else {}
            e = tk.Entry(f, textvariable=var, bg=BG3, fg=FG,
                         insertbackground=AMBER, relief=tk.FLAT,
                         font=(FONT, 9), highlightthickness=1,
                         highlightcolor=AMBER, highlightbackground=BORDER, **kw)
            e.pack(fill=tk.X)
            if tooltip_text: tip(e, tooltip_text)
            e.bind("<Return>",   lambda ev: self._apply_settings())
            e.bind("<FocusOut>", lambda ev: self._apply_settings())
            return e

        stacked("Camera IP",   self._ip_var,
                tooltip_text="LAN IP of your PTZOptics camera.")
        stacked("Username",    self._usr_var,
                tooltip_text="RTSP username. Default: admin")
        stacked("Password",    self._pass_var,  show="*",
                tooltip_text="RTSP password. Default: admin")

        pre_f = tk.Frame(p, bg=BG2)
        pre_f.pack(fill=tk.X, padx=8, pady=(4, 0))
        tk.Label(pre_f, text="Home Preset", bg=BG2, fg=FG_DIM,
                 font=(FONT, 7), anchor="w").pack(fill=tk.X)
        _pre_sb = tk.Spinbox(pre_f, from_=0, to=89, textvariable=self._pre_var,
                             width=5, bg=BG3, fg=FG,
                             insertbackground=AMBER, buttonbackground=BG3,
                             relief=tk.FLAT, font=(FONT, 10, "bold"),
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=AMBER)
        _pre_sb.pack(anchor="w")
        _pre_sb.bind("<Return>",   lambda ev: self._apply_settings())
        _pre_sb.bind("<FocusOut>", lambda ev: self._apply_settings())

        tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X, padx=8, pady=8)

        # ── TRACKING toggle ───────────────────────────────
        self._tracking_on = False

        def _on_track():
            if not (self._thread and self._thread.running):
                return
            self._tracking_on = not self._tracking_on
            self._thread.tracking = self._tracking_on
            if self._tracking_on:
                if self.tracker: self.tracker.reset()
                self._track_btn.configure(text="● TRACKING  ON",
                    bg=GREEN, fg="#000", activebackground="#5fffaa")
            else:
                if self.visca: self.visca.stop(); self.visca.zoom_stop()
                self._track_btn.configure(text="○ TRACKING  OFF",
                    bg=BG3, fg=FG_DIM, activebackground=GREEN)
                self._lock_active = False
                self._lock_btn.configure(text="○ LOCK  OFF",
                    bg=BG3, fg=FG_DIM)

        self._track_btn = tk.Button(p, text="○ TRACKING  OFF",
                                    command=_on_track,
                                    bg=BG3, fg=FG_DIM,
                                    font=(FONT, 10, "bold"),
                                    relief=tk.FLAT, cursor="hand2",
                                    activebackground=GREEN,
                                    activeforeground="#000",
                                    pady=10)
        self._track_btn.pack(fill=tk.X, padx=8, pady=(2, 2))
        tip(self._track_btn, "Start/stop auto-tracking.")

        # ── LOCK toggle ───────────────────────────────────
        self._lock_active = False

        def _on_lock():
            if not (self._thread and self._thread.running and self._thread.tracking):
                return
            self._lock_active = not self._lock_active
            if self._lock_active:
                self._lock_btn.configure(text="● LOCKED  ON",
                    bg=AMBER, fg="#000", activebackground="#ffbe5c")
            else:
                if self.detector: self.detector.release_lock()
                self._lock_btn.configure(text="○ LOCK  OFF",
                    bg=BG3, fg=FG_DIM, activebackground=AMBER)

        self._lock_btn = tk.Button(p, text="○ LOCK  OFF",
                                   command=_on_lock,
                                   bg=BG3, fg=FG_DIM,
                                   font=(FONT, 10, "bold"),
                                   relief=tk.FLAT, cursor="hand2",
                                   activebackground=AMBER,
                                   activeforeground="#000",
                                   pady=10)
        self._lock_btn.pack(fill=tk.X, padx=8, pady=(2, 6))
        tip(self._lock_btn, "Lock onto the current subject. Ignores everyone else.")

        tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X, padx=8, pady=(0, 6))

        # ── AUTO ZOOM toggle button ────────────────────────
        def _on_autozoom():
            on = not self._zoom_en_v.get()
            self._zoom_en_v.set(on)
            SETTINGS.zoom_enabled = on
            if not on:
                try:
                    if self.visca: self.visca.zoom_stop()
                except Exception: pass
            self._on_zoom_toggle_main()

        self._autozoom_btn = tk.Button(p, text="○ AUTO-ZOOM  OFF",
                                       command=_on_autozoom,
                                       bg=BG3, fg=FG_DIM,
                                       font=(FONT, 10, "bold"),
                                       relief=tk.FLAT, cursor="hand2",
                                       activebackground=AMBER,
                                       activeforeground="#000",
                                       pady=10)
        self._autozoom_btn.pack(fill=tk.X, padx=8, pady=(2, 6))
        tip(self._autozoom_btn, "Automatically zoom in/out to keep subject filling the frame.")
        self._on_zoom_toggle_main()

    # ── Zoom toggle (main panel) ─────────────────────────────

    def _on_zoom_toggle_main(self):
        on = self._zoom_en_v.get()
        state = tk.NORMAL if on else tk.DISABLED
        try:
            self._zoom_spd_sb.configure(state=state)
        except Exception:
            pass

    # ── Settings panel (inline, replaces camera view) ────────

    def _build_settings_panel(self, root):
        """Build the settings panel with single-column row layout."""

        # ── Header ────────────────────────────────────────
        hdr = tk.Frame(root, bg=BG3, height=40)
        hdr.pack(fill=tk.X, side=tk.TOP)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚙   TRACKMIND  SETTINGS", bg=BG3, fg=AMBER,
                 font=(FONT, 11, "bold")).pack(side=tk.LEFT, padx=16)
        tk.Button(hdr, text="✕", command=self._toggle_settings,
                  bg=BG3, fg=FG_DIM, font=(FONT, 11),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground=RED, activeforeground="white",
                  bd=0).pack(side=tk.RIGHT, padx=12)
        tk.Frame(root, bg=AMBER, height=1).pack(fill=tk.X, side=tk.TOP)

        # ── Footer (packed before canvas so it anchors at bottom) ──
        tk.Frame(root, bg=BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        footer = tk.Frame(root, bg=BG3)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(footer, text="CANCEL",
                  command=self._toggle_settings,
                  bg=BG3, fg=FG_DIM, font=(FONT, 9, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground=BORDER, activeforeground=FG,
                  padx=16, pady=8).pack(side=tk.LEFT, padx=(14, 0), pady=8)
        tk.Button(footer, text="SAVE",
                  command=lambda: [self._apply_settings(), SETTINGS.save()],
                  bg=AMBER, fg="#000", font=(FONT, 9, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground="#ffbe5c",
                  padx=16, pady=8).pack(side=tk.RIGHT, padx=(0, 14), pady=8)
        tk.Button(footer, text="APPLY  SETTINGS",
                  command=self._apply_settings,
                  bg=BG3, fg=AMBER, font=(FONT, 9, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground=AMBER_DIM, activeforeground=FG,
                  padx=16, pady=8).pack(side=tk.RIGHT, padx=(0, 4), pady=8)

        # ── Scrollable content ─────────────────────────────
        sc  = tk.Canvas(root, bg=BG2, highlightthickness=0)
        vsb = tk.Scrollbar(root, orient="vertical", command=sc.yview,
                           bg=BG2, troughcolor=BG3, activebackground=AMBER_DIM)
        self._sw_inner = tk.Frame(sc, bg=BG2)
        self._sw_inner.bind("<Configure>",
                            lambda e: sc.configure(scrollregion=sc.bbox("all")))
        _cw = sc.create_window((0, 0), window=self._sw_inner, anchor="nw")
        sc.bind("<Configure>", lambda e: sc.itemconfigure(_cw, width=e.width))
        sc.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        sc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.bind("<MouseWheel>",
                lambda e: sc.yview_scroll(int(-1*(e.delta/120)), "units"))
        sc.bind("<Button-4>", lambda e: sc.yview_scroll(-1, "units"))
        sc.bind("<Button-5>", lambda e: sc.yview_scroll(1, "units"))

        p = self._sw_inner

        # ── Row / section helpers ──────────────────────────

        def sec(text):
            f = tk.Frame(p, bg=BG3)
            f.pack(fill=tk.X)
            tk.Label(f, text=text, bg=BG3, fg=AMBER,
                     font=(FONT, 8, "bold"), anchor="w",
                     padx=16, pady=6).pack(side=tk.LEFT)
            tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X)

        def make_row(label, subtitle=""):
            f = tk.Frame(p, bg=BG2)
            f.pack(fill=tk.X)
            left = tk.Frame(f, bg=BG2)
            left.pack(side=tk.LEFT, fill=tk.Y, padx=(16, 8), pady=8)
            tk.Label(left, text=label, bg=BG2, fg=FG,
                     font=(FONT, 9), anchor="w").pack(anchor="w")
            if subtitle:
                tk.Label(left, text=subtitle, bg=BG2, fg=FG_DIM,
                         font=(FONT, 7), anchor="w").pack(anchor="w")
            right = tk.Frame(f, bg=BG2)
            right.pack(side=tk.RIGHT, padx=16, pady=8)
            tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X)
            return right

        def spin_row(label, subtitle, lo, hi, var, inc=1, w=7, fmt=None, tooltip=""):
            right = make_row(label, subtitle)
            kw = {"format": fmt} if fmt else {}
            sb = tk.Spinbox(right, from_=lo, to=hi, textvariable=var,
                            increment=inc, width=w,
                            bg=BG3, fg=AMBER, insertbackground=AMBER,
                            buttonbackground=BG3, relief=tk.FLAT,
                            font=(FONT, 10), highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=AMBER, **kw)
            sb.pack(side=tk.RIGHT)
            if tooltip:
                tip(sb, tooltip)
            return sb

        # ── PROFILES ──────────────────────────────────────
        sec("PROFILES")

        # Load profile row
        r1 = make_row("Active Profile", "Select and load a saved profile")
        prof_names = PROFILE_MANAGER.list_profiles()
        self._profile_dd = tk.OptionMenu(r1, self._profile_var,
                                         *(prof_names if prof_names else [""]))
        self._profile_dd.configure(bg=BG3, fg=FG, activebackground=AMBER,
                                   activeforeground="#000", highlightthickness=0,
                                   relief=tk.FLAT, font=(FONT, 8), width=10)
        self._profile_dd["menu"].configure(bg=BG3, fg=FG, activebackground=AMBER,
                                            activeforeground="#000", font=(FONT, 8))
        self._profile_dd.pack(side=tk.LEFT, padx=(0, 4))
        tip(self._profile_dd, "Select a saved profile.")
        tk.Button(r1, text="LOAD", command=self._load_profile,
                  bg=BG3, fg=FG, font=(FONT, 8, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground=AMBER, activeforeground="#000",
                  padx=8, pady=3).pack(side=tk.LEFT)

        # Save profile row
        r2 = make_row("Save Profile", "Name and save current settings as a new profile")
        tk.Button(r2, text="DEL", command=self._delete_profile,
                  bg=BG3, fg=RED, font=(FONT, 8, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground=RED, activeforeground="white",
                  padx=8, pady=3).pack(side=tk.RIGHT)
        tk.Button(r2, text="SAVE AS", command=self._save_profile,
                  bg=AMBER, fg="#000", font=(FONT, 8, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground="#ffbe5c",
                  padx=8, pady=3).pack(side=tk.RIGHT, padx=(0, 4))
        new_e = tk.Entry(r2, textvariable=self._new_profile_var,
                         bg=BG3, fg=FG, insertbackground=AMBER,
                         relief=tk.FLAT, font=(FONT, 8), width=12,
                         highlightthickness=1, highlightcolor=AMBER,
                         highlightbackground=BORDER)
        new_e.pack(side=tk.RIGHT, padx=(0, 6))
        tip(new_e, "Type a name then click SAVE AS.")

        # ── MOVEMENT ──────────────────────────────────────
        sec("MOVEMENT")

        spin_row("Pan Speed  —  Slow", "Speed when subject is slightly off-center  (1–24)",
                 1, 24, self._pan_slow_v,
                 tooltip="Pan speed when slightly off-center (1–24).")
        spin_row("Pan Speed  —  Fast", "Speed when subject is far off-center  (1–24)",
                 1, 24, self._pan_fast_v,
                 tooltip="Pan speed when far off-center (1–24).")
        spin_row("Tilt Speed  —  Slow", "Speed when subject is slightly above/below center  (1–24)",
                 1, 24, self._tilt_slow_v,
                 tooltip="Tilt speed when slightly above/below center (1–24).")
        spin_row("Tilt Speed  —  Fast", "Speed when subject is far above/below center  (1–24)",
                 1, 24, self._tilt_fast_v,
                 tooltip="Tilt speed when far above/below center (1–24).")
        spin_row("Vertical Offset", "Y tracking center offset  (−7 = top of head · 0 = center · +7 = feet)",
                 -7, 7, self._offset_v,
                 tooltip="Fine-tune aim point. -7 = top of head, +7 = feet, 0 = centered.")

        # ── DEAD ZONES ────────────────────────────────────
        sec("DEAD ZONES")

        spin_row("Pan Dead Zone", "Fraction of frame ignored for pan  (0.17 default — higher = steadier)",
                 0.02, 0.30, self._pan_dead_v, inc=0.01, w=6, fmt="%.2f",
                 tooltip="Fraction of frame ignored for pan. 0.17 default. Higher = steadier.")
        spin_row("Tilt Dead Zone", "Fraction of frame ignored for tilt  (0.17 default)",
                 0.02, 0.30, self._tilt_dead_v, inc=0.01, w=6, fmt="%.2f",
                 tooltip="Fraction of frame ignored for tilt. 0.17 default.")

        # ── ZOOM ──────────────────────────────────────────
        sec("ZOOM")

        r3 = make_row("Auto-Zoom", "Automatically zoom to keep subject filling the frame")
        self._zoom_settings_cb = tk.Checkbutton(
            r3, text="Enable",
            variable=self._zoom_en_v,
            command=self._on_zoom_toggle_main,
            bg=BG2, fg=FG, selectcolor=BG3,
            activebackground=BG2, font=(FONT, 9), cursor="hand2")
        self._zoom_settings_cb.pack(side=tk.RIGHT)
        tip(self._zoom_settings_cb, "Automatically zoom to keep subject filling the frame.")

        self._zoom_detail_rows = []
        self._zoom_detail_rows.append(
            spin_row("Target Fill %", "How much frame height the subject occupies  (45 = wide · 80 = tight)",
                     20, 90, self._zoom_tgt_v,
                     tooltip="How much frame height the person occupies. 45 = wide, 80 = tight."))
        self._zoom_detail_rows.append(
            spin_row("Zoom Dead Zone %", "Tolerance before zoom activates — higher means less hunting",
                     5, 40, self._zoom_dead_v,
                     tooltip="Tolerance before zoom activates. Higher = less hunting. 20 recommended."))
        self._zoom_detail_rows.append(
            spin_row("Zoom Speed", "Motor speed  (0–7 · start at 1 for smooth motion)",
                     0, 7, self._zoom_spd_v,
                     tooltip="Motor speed 0–7. Start at 1 for smooth motion."))
        self._sync_zoom_detail_state()

        # ── ADVANCED ──────────────────────────────────────
        sec("ADVANCED")

        spin_row("Latency Compensation", "Look-ahead seconds to offset RTSP delay  (0.40 default)",
                 0.0, 2.0, self._lat_v, inc=0.05, w=6, fmt="%.2f",
                 tooltip="Seconds of look-ahead to compensate RTSP delay. 0.40 default.")
        spin_row("Lost Timeout", "Seconds before returning to home preset when subject is lost  (2.0 default)",
                 1.0, 10.0, self._lost_v, inc=0.5, w=6, fmt="%.1f",
                 tooltip="Seconds before camera returns home when subject is lost. 2.0 default.")

        # ── UPDATES ───────────────────────────────────────
        sec("UPDATES")

        r4 = make_row("Current Version", "Installed software version")
        tk.Label(r4, text=f"v{VERSION}", bg=BG3, fg=AMBER,
                 font=(FONT, 8, "bold"), padx=10, pady=3).pack(side=tk.RIGHT)

        r5 = make_row("Check for Updates", "Fetch the latest release from GitHub")
        self._last_check_lbl = tk.Label(r5, text="never checked",
                                        bg=BG2, fg=FG_DIM, font=(FONT, 8))
        self._last_check_lbl.pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(r5, text="CHECK NOW",
                  command=lambda: self._updater.check_async(manual=True) if hasattr(self, '_updater') else None,
                  bg=BG3, fg=AMBER, font=(FONT, 8, "bold"),
                  relief=tk.FLAT, cursor="hand2",
                  activebackground=AMBER_DIM, activeforeground=FG,
                  padx=10, pady=3).pack(side=tk.RIGHT)

        # Bind scroll to every child widget so Linux scroll events propagate to canvas
        def _bind_scroll(widget):
            widget.bind("<MouseWheel>", lambda e: sc.yview_scroll(int(-1*(e.delta/120)), "units"))
            widget.bind("<Button-4>", lambda e: sc.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda e: sc.yview_scroll(1, "units"))
            for child in widget.winfo_children():
                _bind_scroll(child)
        _bind_scroll(self._sw_inner)

    def _sync_zoom_detail_state(self):
        state = tk.NORMAL if self._zoom_en_v.get() else tk.DISABLED
        for w in self._zoom_detail_rows:
            try: w.configure(state=state)
            except Exception: pass

    def _sync_autozoom_btn(self):
        if not hasattr(self, '_autozoom_btn'):
            return
        if self._zoom_en_v.get():
            self._autozoom_btn.configure(text="● AUTO-ZOOM  ON",
                bg=AMBER, fg="#000", activebackground="#ffbe5c")
        else:
            self._autozoom_btn.configure(text="○ AUTO-ZOOM  OFF",
                bg=BG3, fg=FG_DIM, activebackground=AMBER)

    def _on_zoom_toggle_main(self):
        on = self._zoom_en_v.get()
        state = tk.NORMAL if on else tk.DISABLED
        try: self._zoom_spd_sb.configure(state=state)
        except Exception: pass
        self._sync_zoom_detail_state()
        self._sync_autozoom_btn()

    # ── Toggle settings panel ────────────────────────────────

    def _toggle_settings(self):
        if self._settings_visible:
            self._settings_frame.place_forget()
            self._settings_visible = False
            self._settings_btn.configure(text="⚙  SETTINGS", fg=FG_DIM,
                                         bg=BG2, activebackground=AMBER_DIM)
        else:
            self._settings_frame.place(relx=0.02, rely=0.02,
                                       relwidth=0.96, relheight=0.96)
            self._settings_frame.lift()
            self._settings_visible = True
            self._settings_btn.configure(text="⚙  SETTINGS ▾", fg=AMBER,
                                         bg=AMBER_DIM, activebackground=AMBER_DIM)

    # ── Setup wizard ─────────────────────────────────────────

    def _run_setup_wizard(self):
        SetupWizard(self)

    # ── Refresh all UI vars from SETTINGS ────────────────────

    def _refresh_ui_from_settings(self):
        self._ip_var.set(SETTINGS.camera_ip)
        self._usr_var.set(SETTINGS.rtsp_user)
        self._pass_var.set(SETTINGS.rtsp_pass)
        self._str_var.set(SETTINGS.rtsp_stream)
        self._pre_var.set(SETTINGS.home_preset)
        self._offset_v.set(SETTINGS.track_offset)
        self._pan_dead_v.set(SETTINGS.pan_dead)
        self._pan_slow_v.set(SETTINGS.pan_slow)
        self._pan_fast_v.set(SETTINGS.pan_fast)
        self._tilt_dead_v.set(SETTINGS.tilt_dead)
        self._tilt_slow_v.set(SETTINGS.tilt_slow)
        self._tilt_fast_v.set(SETTINGS.tilt_fast)
        self._zoom_en_v.set(SETTINGS.zoom_enabled)
        self._zoom_tgt_v.set(int(SETTINGS.zoom_target * 100))
        self._zoom_dead_v.set(int(SETTINGS.zoom_dead  * 100))
        self._zoom_spd_v.set(SETTINGS.zoom_speed)
        self._lat_v.set(SETTINGS.latency_comp)
        self._lost_v.set(SETTINGS.lost_timeout)
        self._on_zoom_toggle_main()

    # ── Profile operations ────────────────────────────────────

    def _refresh_profile_dropdown(self):
        menu = self._profile_dd["menu"]
        menu.delete(0, "end")
        names = PROFILE_MANAGER.list_profiles()
        if names:
            for n in names:
                menu.add_command(label=n,
                                 command=lambda x=n: self._profile_var.set(x))
        else:
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
        self._refresh_ui_from_settings()

    def _delete_profile(self):
        name = self._profile_var.get()
        if not name or name not in PROFILE_MANAGER.profiles:
            return
        PROFILE_MANAGER.delete_profile(name)
        self._profile_var.set("")
        self._refresh_profile_dropdown()

    # ── Start / Stop ──────────────────────────────────────────

    def _on_start(self):
        if self._thread and self._thread.running:
            return
        self._apply_settings()
        self._thread = TrackerThread(self)
        self._thread.start()

    def _on_stop(self):
        if self._thread:
            self._thread.tracking = False
            self._thread.stop()
        self.status_var.set("OFFLINE")
        if hasattr(self, '_status_lbl'):
            self._status_lbl.configure(fg=FG_DIM)

    # ── Apply settings ────────────────────────────────────────

    def _apply_settings(self):
        SETTINGS.camera_ip    = self._ip_var.get().strip()
        SETTINGS.rtsp_user    = self._usr_var.get().strip()
        SETTINGS.rtsp_pass    = self._pass_var.get().strip()
        SETTINGS.rtsp_stream  = self._str_var.get().strip()
        SETTINGS.home_preset  = self._pre_var.get()
        SETTINGS.track_offset = self._offset_v.get()
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

        if self._thread and self._thread.running:
            new_url = (f"rtsp://{SETTINGS.rtsp_user}:{SETTINGS.rtsp_pass}"
                       f"@{SETTINGS.camera_ip}/{SETTINGS.rtsp_stream}")
            if new_url != getattr(self, '_last_url', None):
                self._thread.tracking = False
                self._thread.stop()
                self._thread = None
                self._last_url = new_url
                self.root.after(800, self._on_start)

        self._last_url = (f"rtsp://{SETTINGS.rtsp_user}:{SETTINGS.rtsp_pass}"
                          f"@{SETTINGS.camera_ip}/{SETTINGS.rtsp_stream}")
        SETTINGS.save()

    # ── Preview update loop ───────────────────────────────────

    def _update_preview(self):
        try:
            if self._thread and self._thread.latest_frame is not None:
                with self._thread._frame_lock:
                    frame = self._thread.latest_frame.copy()

                detection = self._thread.latest_detection
                h, w = frame.shape[:2]

                cv2.line(frame, (w//2-20, h//2), (w//2+20, h//2), (0,255,0), 1)
                cv2.line(frame, (w//2, h//2-20), (w//2, h//2+20), (0,255,0), 1)

                if detection:
                    dcx, dcy, dw, dh = detection
                    x0 = int((dcx - dw/2) * w); y0 = int((dcy - dh/2) * h)
                    x1 = int((dcx + dw/2) * w); y1 = int((dcy + dh/2) * h)
                    cv2.rectangle(frame, (x0,y0), (x1,y1), (0,200,255), 2)
                    cv2.circle(frame, (int(dcx*w), int(dcy*h)), 5, (0,200,255), -1)

                status = self._thread.status if self._thread else "STOPPED"
                color  = (0,255,0) if status == "TRACKING" else (0,165,255)
                cv2.putText(frame, status, (10,25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

                if self._thread and self.tracker:
                    z = self.tracker._prev_zoom
                    zlbl = "ZOOM IN" if z==1 else ("ZOOM OUT" if z==-1 else "")
                    if zlbl:
                        cv2.putText(frame, zlbl, (10,50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,200,0), 1, cv2.LINE_AA)

                cw = max(self.canvas.winfo_width(),  self.PREVIEW_W)
                ch = max(self.canvas.winfo_height(), self.PREVIEW_H)
                display = cv2.resize(frame, (cw, ch))
                img   = Image.fromarray(cv2.cvtColor(display, cv2.COLOR_BGR2RGB))
                imgtk = ImageTk.PhotoImage(image=img)
                self.canvas.imgtk = imgtk
                self.canvas.delete("all")
                self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)

                st = self._thread.status if self._thread else "STOPPED"
                if st == "TRACKING":
                    self.status_var.set("● TRACKING")
                    self._status_lbl.configure(fg=GREEN)
                    self._panel_status_lbl.configure(text="● TRACKING", fg=GREEN)
                elif st == "PAUSED":
                    self.status_var.set("● PAUSED")
                    self._status_lbl.configure(fg=AMBER)
                    self._panel_status_lbl.configure(text="● PAUSED", fg=AMBER)
                else:
                    self.status_var.set("● OFFLINE")
                    self._status_lbl.configure(fg=FG_DIM)
                    self._panel_status_lbl.configure(text="● OFFLINE", fg=FG_DIM)
        except Exception:
            pass

        self.root.after(33, self._update_preview)

    # ── Fullscreen ────────────────────────────────────────────

    def _toggle_fullscreen(self, event=None):
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)

    def _exit_fullscreen(self, event=None):
        if self._fullscreen:
            self._fullscreen = False
            self.root.attributes("-fullscreen", False)

    # ── Close ─────────────────────────────────────────────────

    def on_close(self):
        SETTINGS.save()
        self._on_stop()
        time.sleep(0.3)
        self.root.destroy()


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main():
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
