# Changelog

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
