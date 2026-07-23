# Changelog

All notable changes to this project are documented here.

## [4.0.1] — 2026-07-23

Patch release. Fixes a packaging fault that prevented v4.0 from starting on
machines without a conda installation, and makes FLIR camera setup diagnosable.

### Added

- Documented the FLIR Spinnaker SDK prerequisite in the **installer** section of
  the README. The SDK supplies the FLIR camera driver, which cannot be bundled
  into the installer, so a clean machine detects no FLIR camera even though the
  app is otherwise working. The note explains that the SDK version need not
  match the app — RAPIID ships its own Spinnaker runtime (2.7.0.128) and needs
  the SDK only for the driver — and makes clear it is **not** needed for
  webcam-only use.
- Step-by-step Spinnaker SDK installer instructions: which installer to
  download (x64), the **Application Development** profile, the Visual Studio
  prompt, when to tick "I will use GigE cameras" (not for the USB 3.0
  Blackfly S), and that evaluation programs can be declined. Also notes that
  SpinView can be used to test the camera independently of RAPIID.

### Fixed

- **FLIR detection failures were invisible.** Diagnostics were written with
  `print()`, but the app is frozen with `base="Win32GUI"` and therefore has no
  console, so end users saw cameras silently missing with no explanation. The
  reason a FLIR camera was not found is now reported in the in-app log panel,
  along with a note that the Spinnaker SDK is only required for FLIR cameras.
  The camera-discovery error handler no longer refers users to a console that
  does not exist.

- **Frozen builds failed to start on machines without a conda install**, with
  "The code execution cannot proceed because zlib.dll was not found".
  `python38.dll` links against `zlib.dll` dynamically in conda builds, but
  cx_Freeze placed `zlib.dll` under `lib/`, where the Windows loader does not
  look — it searches the executable's own directory. Development machines
  masked this because the conda environment is on `PATH`. `setup.py` now ships
  `zlib.dll` alongside the executable, and fails the build early if it cannot
  be located in the active environment.

## [4.0] — 2026-07-23

Unified release. RAPIID and RAPIIDlite are now a single application under the
name **RAPIID**.

### Changed

- **Renamed the application from RAPIIDlite to RAPIID.** The two applications
  had merged into one, and the "lite" qualifier no longer described a real
  distinction. This release is the direct continuation of RAPIIDlite v3.2 —
  no functionality has been removed.
- Renamed the repository from `aharmer/RAPIIDlite` to `aharmer/RAPIID`. The
  previous URL redirects to the new one.
- Renamed source files, GUI modules, icons, and the workflow document to drop
  the `lite` qualifier (`rapiid_lite.py` → `rapiid.py`,
  `rapiidlite_GUI.*` → `rapiid_GUI.*`, `RAPIIDlite_icon.*` → `RAPIID_icon.*`).
- Updated the installer: application name, install directory, Start Menu and
  desktop shortcuts, and output filename now use the RAPIID name. The Inno
  Setup `AppId` is unchanged, so existing installations upgrade in place
  rather than installing alongside the old version.
- Updated the Windows AppUserModelID to `ManaakiWhenua.RAPIID.4`.
- Images captured with this version are tagged `RAPIID` in their EXIF `Make`
  and `Software` fields, and in the `capture_device` CSV column. Images
  captured with earlier versions retain their original `RAPIIDlite` tags.
- Replaced the `pyuic5.exe` launcher in the GUI rebuild helper with
  `python -m PyQt5.uic.pyuic` and relative paths. The `.exe` launcher embeds
  an absolute interpreter path at install time and breaks if the environment
  is renamed.

### Fixed

- Documented the `qt-material` version ceiling in `environment.yml`. Release
  2.14.2 dropped PyQt5 support, and newer versions fail silently: the material
  theme's icons and fonts never load, and the app logs
  "qt_material must be imported after PySide or PyQt!". The pin at 2.12 was
  already correct; the constraint is now stated so it is not upgraded past it.

### Upgrading

Existing installations upgrade in place. Desktop and Start Menu shortcuts are
recreated under the new name; you may want to remove stale pinned taskbar
shortcuts, which point at the old executable name.

---

## Earlier releases

Versions 3.2 and earlier were published under the name **RAPIIDlite**. Their
history is available from the git tags in this repository:

- [3.2] — 2026-07-08
- [3.1] — 2025-07-21
- [3.0] — 2026-03-23
