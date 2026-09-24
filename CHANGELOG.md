# Changelog

## v1.7 — 2026-09-23

### A brand-new Trackmind
- **Rebuilt interface.** The live camera now fills the window, and every control floats over the picture as **liquid glass**: real refraction, specular rims, and tally-colored tints, in the vMix language of green = tracking, amber = lock, red = on air. The window is a native WebView2 window. Run with `--browser` to use it in a web browser instead.
- **Tracking overlay.** A reticle follows the detected subject (green, turning amber when locked), with a dead-zone guide and a "zooming" indicator.
- **Control dock.** Large Tracking, Lock, Auto-Zoom and Home buttons, with live status under each.
- **Live tune.** A floating panel for adjusting vertical aim, smoothing and zoom target, or switching profile, mid-service.
- **Settings sheet.** Camera, Profiles, Tracking, Zoom, Advanced, Stream Deck and About sections. Every change applies and saves immediately; there's no Apply button. You can now also choose the RTSP stream (Main 1080p or Sub 720p).
- **New setup wizard, update prompts, and connection states.** Covers "connecting", "can't reach the camera" (with Reconnect), and "add your camera". Updates show release notes and live download progress.
- **Keyboard shortcuts:** `T` tracking, `L` lock, `Z` auto-zoom, `H` home, `U` live tune, `F` full screen, `,` settings.
- **New logo and app icon.** A tracking frame holding a tally-green subject, whose green dot is also the dot of the "i" in the wordmark. The icon, installer art and README banner are all generated from `branding/`.

### Stream Deck
- **New plugin.** It covers Tracking, Lock Subject, Recall Preset (glows red while on air), Home Preset, Auto-Zoom, Pan/Tilt and Zoom hold keys, Load Profile, Motion Sync, a live Status tile, and a Stream Deck + **Tracking Dial** for live tuning. Keys are rendered as liquid glass, with the same optics as the app. Install by downloading `Trackmind-StreamDeck-v1.7.streamDeckPlugin` from this release and double-clicking it. See `streamdeck/README.md`.

### Control API
- **Local JSON HTTP API** on `127.0.0.1:8742`. It drives tracking, lock, presets, profiles, manual PTZ and live values. The Stream Deck plugin uses it, and so can Companion, vMix scripts and anything else that speaks HTTP. Manual moves have a built-in dead-man switch, so they stop by themselves if the controller goes quiet. External clients can never read the camera login or settings. Full reference in `docs/API.md`.

### Under the hood
- Tkinter and Pillow are gone. The tracking engine is unchanged, and now also serves the interface, the live preview (MJPEG) and state updates (Server-Sent Events) from one local-only server.
- Loading a profile with a different camera now reconnects the stream automatically.

---

## v1.6 — 2026-06-21

### Fixes
- **Auto-update file-overwrite race condition fixed.** The NSIS installer previously relied on a fixed 2-second sleep after `taskkill`, which was not always enough time for Windows Defender or other AV software to release its lock on the killed process's EXE. NSIS would then silently skip the file copy, relaunch the *old* binary, and the update appeared to do nothing. The installer now confirms the lock is released by repeatedly attempting to delete the old EXE (up to 10 retries × 1 second each = 10 s max) before copying the new one, and explicitly aborts with an error message if the copy still fails.

---

## v1.5 — 2026-06-21

### Fixes
- **Hardened the auto-updater.** The downloaded installer now has its Mark-of-the-Web (the "downloaded from the internet" tag) stripped before launch, so Windows SmartScreen no longer silently blocks the silent/elevated install. The updater also verifies the download finished (catching truncated/empty files) and now reports a clear reason when an update can't start — including when the User Account Control prompt is declined — instead of failing silently.

---

## v1.4 — 2026-06-21

### Fixes
- **Auto-update now actually applies.** The updater launched the silent installer while the old app was still running, so Windows refused to overwrite the locked `.exe` — the install failed quietly and reopening still showed the old version. The installer now force-closes the running app before copying files, then relaunches the updated app when it finishes a silent (auto-update) install. The app also shows an "updating — app will restart" status and exits cleanly so the file unlocks.
- Fixed a Start Menu shortcut that pointed at a folder the installer never created.

---

## v1.3 — 2026-06-21

### Changes
- **Smoother tracking motion.** The pan/tilt controller now uses continuous proportional speed instead of snapping between discrete slow/fast steps, and ramps acceleration and deceleration so the camera eases into and out of moves rather than jerking. The result is noticeably more cinematic following.
  - New **Motion Smoothing** setting (0–10, default 5) under MOVEMENT tunes how gentle the accel/decel ramps are. 0 restores the old instant behavior; 10 is silkiest (slightly slower to react).
- Added **Motion Sync** setting — when enabled, the PTZOptics camera scales each axis's speed so pan, tilt, and zoom all reach a recalled preset at the same moment, producing smooth, coordinated motion instead of one axis finishing early. Toggle it in the settings panel under the new **Motion Sync** section. The state is saved per profile and applied to the camera on connect.

---

## v1.2 — 2026-06-03

### Fixes
- Settings panel: pressing Enter or clicking away from any field now immediately applies and saves values — no more needing to click Apply
- Version display: app no longer shows "unknown" when run from certain working directories
- Installer: version is now read automatically from `version.txt` — no more hardcoded version strings to forget to update

### Changes
- GitHub Actions workflow added — releases are now built automatically on Windows when a version tag is pushed

---

## v1.1

### Changes
- Redesigned settings panel with scrollable single-column layout
- Added user profiles — save and load sets of tracking settings by name
- Added auto-updater — checks GitHub releases on launch and can download/install updates
- Dynamic versioning via `version.txt`
- App icon and NSIS installer

---

## v1.0

Initial release.
- MediaPipe Pose detection for PTZOptics cameras over RTSP
- VISCA over IP pan/tilt/zoom control
- Auto-tracking with dead zone, slow/fast speed zones, and velocity prediction
- Lock-on mode to ignore other people in frame
- Auto-zoom to keep subject filling the frame
- First-run setup wizard
