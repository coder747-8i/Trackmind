<p align="center">
  <img src="trackmind_logo.svg" width="500" alt="TrackMind">
</p>

# TrackMind
### Intelligent PTZ Auto-Tracking

![Built with AI](https://img.shields.io/badge/built%20with-AI-f5a623?style=flat-square)
![Python](https://img.shields.io/badge/python-3.9--3.11-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

---

AI-built desktop application that brings intelligent auto-tracking to PTZOptics cameras. Uses MediaPipe pose detection to locate a person in the camera's RTSP video feed and sends real-time VISCA over IP pan, tilt, and zoom commands to keep them centered in frame.

Built as an open-source replacement for the PTZOptics CMP tracking feature, which dropped support for G2 USB-model cameras.

---

## Requirements

- Windows 10 or 11
- PTZOptics camera with a LAN port (tested on PT12X-USB-G2)
- Camera LAN port connected to the same network as your PC
- Python 3.9–3.11 — https://www.python.org/downloads/
  - Check **Add Python to PATH** during install (only needed for source install)
  - mediapipe 0.10.9 does not support Python 3.12+

---

## Installation

### Recommended — Windows Installer

Run `Trackmind_Setup.exe` and follow the prompts. Creates a Start Menu entry, desktop shortcut, and uninstaller. No Python required.

### Run from Source

1. Install Python 3.9–3.11 — check **Add Python to PATH**
2. Double-click `INSTALL.bat` to install dependencies
3. Double-click `START_TRACKER.bat` to launch

### Build Your Own EXE

1. Install Python 3.9–3.11
2. Double-click `BUILD_EXE.bat` — installs all dependencies automatically, then produces `dist\Trackmind.exe`
3. *(Optional)* Install NSIS from https://nsis.sourceforge.io/Download, then run `BUILD_INSTALLER.bat` to produce a `Trackmind_Setup.exe` installer

---

## First-Time Setup

On the very first launch, TrackMind walks you through a setup wizard:

1. **Camera IP** — the LAN IP of your camera (find it in your router or camera web UI)
2. **Credentials** — RTSP username and password (default: `admin` / `admin`)
3. **Home Preset** — the preset the camera returns to when the subject is lost (0 if not configured)
4. **Dead Zone** — tracking sensitivity. 0.17 is recommended — increase if the camera twitches
5. **Done** — settings are saved per Windows user account

Settings are stored per user in `%USERPROFILE%\.trackmind\<username>\config.json`, so multiple users on the same PC each have independent settings.

---

## Camera Setup

1. Connect your camera LAN port to your network
2. Find the camera IP — check your router, or try `http://192.168.100.88` (factory default)
3. PC and camera must be on the same subnet
4. VISCA over IP must be enabled — camera web UI → Network settings
5. VISCA uses TCP port 5678 — make sure Windows Firewall is not blocking it

**RTSP stream URLs:**
```
Main stream (1080p): rtsp://admin:admin@[camera-ip]/1
Sub stream  (720p):  rtsp://admin:admin@[camera-ip]/2  ← recommended (default)
```

---

## Using the App

The app connects to the camera automatically on startup. The preview shows **NO SIGNAL** until the stream connects (2–5 seconds).

### Main Panel

The left panel is kept minimal — only the controls you need during a shoot:

| Control | Description |
|---------|-------------|
| Camera IP | LAN IP of your camera |
| Username | RTSP username |
| Password | RTSP password |
| Home Preset | Preset recalled when subject is lost |
| **TRACKING** button | Green = tracking on. Camera follows whoever is in frame |
| **LOCK** button | Amber = locked on. Camera ignores everyone except the current subject |
| **SETTINGS** button | Opens the full settings panel |

### Tracking Button
When ON (green) the camera follows whoever MediaPipe detects in frame. When OFF the camera stops moving and you have full manual control via joystick, Stream Deck, vMix, or any other controller.

### Lock Button
While tracking is ON, click **LOCK** to lock onto the current subject. The camera ignores everyone else. Click again to unlock. Lock resets automatically when tracking is turned off.

---

## Settings Panel

Click **SETTINGS** to open the settings window. Changes take effect when you click **Apply Settings** or **Save**.

### Profiles

Save and load named setting presets — useful for switching between different rooms, presenters, or camera positions.

| Control | Description |
|---------|-------------|
| Dropdown | Select a saved profile |
| LOAD | Apply the selected profile immediately |
| Name entry + SAVE AS | Save current settings under a new name |
| DEL | Delete the selected profile |

Profiles are stored per Windows user account alongside your settings.

### Tracking — Pan / Tilt

| Field | Default | Description |
|-------|---------|-------------|
| Vertical Offset | 2 | Fine-tune aim point. -7 = top of head, +7 = feet, 0 = centered |
| Pan Dead Zone | 0.17 | Fraction of frame where pan offsets are ignored. Higher = steadier near center |
| Pan Slow | 2 | Pan speed when slightly off-center (1–24) |
| Pan Fast | 5 | Pan speed when far off-center (1–24) |
| Tilt Dead Zone | 0.17 | Same as Pan Dead Zone but for tilt |
| Tilt Slow | 2 | Tilt speed when slightly above/below center (1–24) |
| Tilt Fast | 5 | Tilt speed when far above/below center (1–24) |

### Zoom

| Field | Default | Description |
|-------|---------|-------------|
| Enable Auto-Zoom | Off | Toggle auto-zoom. Off = manual zoom only |
| Target Fill % | 45 | How much frame height the person occupies. 45 = wider, 80 = tight |
| Dead Zone % | 20 | Tolerance before zoom activates. Higher = less hunting |
| Zoom Speed | 1 | Motor speed 0–7. Start at 1 for smooth motion |

### Advanced

| Field | Default | Description |
|-------|---------|-------------|
| Latency Comp | 0.40 | Seconds of look-ahead to compensate for RTSP delay. Too high = oscillation |
| Lost Timeout | 2.0 | Seconds before camera returns to home preset when subject is missing |

### Updates

Click **Check for Updates** to check GitHub for a newer version. If one is found, TrackMind will download and install it automatically.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F11 | Toggle fullscreen |
| Esc | Exit fullscreen |

---

## How It Works

1. Video is pulled from the camera's RTSP stream over the LAN port
2. Each frame is processed by **MediaPipe Pose** — a local AI model, no internet required
3. A dedicated buffer thread drains the RTSP stream continuously, keeping only the latest frame to prevent lag buildup
4. Velocity prediction estimates where the subject is heading to compensate for RTSP latency
5. **VISCA over IP** pan/tilt/zoom commands are sent to the camera's LAN port (TCP 5678)

**Lock-on:** When LOCK is active, the detector only follows detections within 25% of the frame distance from the last known position of the locked subject. Anyone else is ignored.

---

## Troubleshooting

**App opens but shows NO SIGNAL**
- Check camera IP is correct in the main panel
- Test in VLC: Media → Open Network Stream → `rtsp://admin:admin@[ip]/2`
- Verify username and password are correct

**Camera doesn't move**
- Ping the camera IP from your PC
- Check TCP port 5678 is not blocked by Windows Firewall
- Confirm VISCA over IP is enabled in the camera web UI

**Tracking is jittery or oscillating**
- Open Settings → increase Pan/Tilt Dead Zone (try 0.20–0.22)
- Lower Pan Slow / Tilt Slow speed
- Reduce Latency Comp in Advanced (try 0.2)

**Camera goes in the wrong direction**
- In `autotrack.py` find `pan_vel = -zone_speed(...)` and remove or add the minus sign

**EXE shows default Windows icon**
- Make sure `trackmind_icon.ico` is in the same folder as `autotrack.py` before building
- Rebuild with `BUILD_EXE.bat`

**Setup wizard doesn't appear on first launch**
- Delete `%USERPROFILE%\.trackmind\<your-username>\config.json` and relaunch

---

## Dependencies

| Package | Version | Notes |
|---------|---------|-------|
| opencv-python | >= 4.8.0 | Video capture and frame processing |
| mediapipe | == 0.10.9 | Pinned — newer versions removed the solutions API |
| Pillow | >= 10.0.0 | UI image rendering |
| numpy | >= 1.24.0 | Array operations |
| pyinstaller | >= 6.0.0 | EXE packaging (build only) |

---

## Known Limitations

- RTSP latency (1–3s) means the camera lags the subject slightly. Velocity prediction compensates but does not fully eliminate this.
- MediaPipe single-pose model always detects the most visually prominent person in frame. Use LOCK to pin to a specific subject.

---

## Built With

- [MediaPipe](https://mediapipe.dev) — pose detection
- [OpenCV](https://opencv.org) — video capture
- [Tkinter](https://docs.python.org/3/library/tkinter.html) — UI
- [PyInstaller](https://pyinstaller.org) — exe packaging
- [NSIS](https://nsis.sourceforge.io) — Windows installer
