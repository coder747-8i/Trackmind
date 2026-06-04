# Changelog

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
