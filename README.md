# RAPIIDlite v3.2

**Transforming specimen labels to digital data**

RAPIIDlite is a desktop imaging application for natural history collection digitisation workflows. It captures high-quality images of specimen labels using one or more cameras, decodes DataMatrix barcodes from accession labels, and automatically records capture metadata to CSV and EXIF tags — with no manual data entry required.

Developed at [Manaaki Whenua – Landcare Research](https://www.landcareresearch.co.nz/) as part of the [Chrysalis](https://chrysalis-ento.vercel.app/) digitisation platform.

---

## Installation

### Option 1 — Windows installer (recommended for end users)

The easiest way to get started is to download the pre-built Windows installer from the [GitHub releases page](../../releases/latest). Download the `.msi` file, run it, and follow the prompts — no Python or dependency installation is required.

> **Note:** Windows may show a SmartScreen warning on first run because the installer is not yet code-signed. Click *More info* → *Run anyway* to proceed.

### Option 2 — Run from source (recommended for developers)

If you want to modify the app, add features, or run it on macOS or Linux, follow the instructions in the [Requirements](#requirements) and [Running the application](#running-the-application) sections below.

---

## Features

- **Multi-camera label capture** — supports 1–4 simultaneous label cameras in a responsive 2-column grid view; single-camera mode fills the available screen
- **FLIR machine vision cameras** — full integration with FLIR cameras via the Spinnaker PySpin SDK, with per-camera exposure (ms), gain (dB), and gamma controls; high-quality HQ_LINEAR debayering at capture time
- **Webcam support** — any DirectShow-compatible webcam (Windows) or V4L2/AVFoundation device (Linux/macOS). However, a camera with a very short focal range is recommended for accurate label viewing
- **DataMatrix barcode decoding** — automatically decodes DataMatrix barcodes from a dedicated barcode camera, populating the accession number field; adaptive thresholding for reliable detection under varied lighting
- **CSV metadata logging** — appends a metadata row to a per-taxon CSV file on every capture, recording filename, accession number, taxon, creator, date, camera device, and copyright
- **EXIF embedding** — embeds creator, taxon, accession, date, copyright, and camera metadata directly into saved image files (requires Pillow and piexif)
- **Config file save/load** — saves and restores session settings (creator, taxon, output folder, camera type, and FLIR exposure settings) as a YAML file
- **Threaded architecture** — all camera streaming and discovery runs on worker threads; the UI remains fully responsive at all times
- **Progress feedback** — animated progress dialogs during camera discovery and multi-camera capture sequences

---

## Project structure for dev

```
rapiid_lite/
├── rapiid_lite.py              # Main application
├── GUI/
│   └── rapiidlite_GUI.py       # Auto-generated PyQt5 UI class (from .ui file)
├── GUI/
│   └── rapiidlite_GUI.ui       # Qt Designer UI definition
├── images/
│   └── RAPIIDlite_icon.png     # Application icon (512×512 PNG)
├── scripts/
│   └── ymlRW.py                # YAML config read/write helper (optional)
└── README.md
```

---

## Requirements

### Python

Python 3.8 or later is recommended.

### Required dependencies

```
PyQt5
opencv-python
numpy
pylibdmtx
```

### Optional dependencies

| Package | Purpose | Behaviour if absent |
|---|---|---|
| `qt-material` | Dark material theme | Falls back to default Qt theme |
| `Pillow` + `piexif` | EXIF metadata embedding | EXIF embedding silently skipped |
| `PySpin` (Spinnaker SDK) | FLIR camera support | FLIR options hidden from UI |
| `scripts.ymlRW` | Config file save/load | Config buttons disabled |

### Installing dependencies

```bash
pip install PyQt5 opencv-python numpy pylibdmtx qt-material Pillow piexif
```

`pylibdmtx` requires the native `libdmtx` library. On Windows the PyPI wheel bundles it. On Linux:

```bash
sudo apt install libdmtx-dev
pip install pylibdmtx
```

### FLIR Spinnaker SDK

Download and install the Spinnaker SDK from [FLIR's website](https://www.flir.com/products/spinnaker-sdk/), then install the matching Python wheel:

```bash
pip install spinnaker_python-<version>-cp<pyver>-win_amd64.whl
```

---

## Running the application

```bash
python rapiid_lite.py
```

The application window appears immediately. Camera discovery runs in the background — a progress dialog is shown while webcams and FLIR cameras are detected. Controls are enabled once discovery completes.

### Windows note

On Windows, OpenCV uses the DirectShow backend (`CAP_DSHOW`) for all webcam operations. This avoids the MSMF `can't grab frame. Error: -1072873821` error that occurs with the default MSMF backend on many webcams.

---

## Workflow

1. **Select output folder** — click *Output folder...* and choose where images will be saved
2. **Enter creator and taxon name** — used in file paths, EXIF metadata, and CSV logging
3. **Start barcode camera** — select the barcode camera from the dropdown and click *Start live view*; point it at a DataMatrix label to auto-populate the accession number field
4. **Start label camera(s)** — select each label camera, click *Start live view*; the live view appears in the grid
5. **Capture** — click *Capture image* (or press `Alt+C`); images are saved, EXIF is embedded, and a CSV row is appended
6. **Add cameras** — click *+ Add label camera* to add up to 4 cameras; the grid switches to 2-column layout automatically

---

## Output files

For each capture session the following are created under `<output_folder>/<taxon_name>/<accession_number>/`:

| File | Description |
|---|---|
| `<accession>_label.jpg` | Captured image (single camera) |
| `<accession>_label_1.jpg`, `_label_2.jpg` … | Per-camera images (multi-camera) |

A shared CSV log is written to `<output_folder>/<taxon_name>/<taxon_name>_captures.csv` with the following columns:

```
image_filename, accession_number, taxon_name, image_format,
copyright_type, rights_owner, creator, date_captured,
capture_device, caption, title
```

---

## Camera settings (FLIR only)

FLIR camera controls appear when a FLIR device is selected in a label camera slot.

| Control | Range | Notes |
|---|---|---|
| Exposure | 0.1 – 1000.0 ms | Displayed in ms, sent to camera in µs |
| Gain | 0 – 40 dB | |
| Gamma correction | 1 – 300 | Stored as integer × 100 (e.g. 100 = γ 1.0) |

Settings are debounced — the camera is only updated 400 ms after the user stops adjusting a control, preventing excessive stop/reconfigure/start cycles.

Live preview uses `NEAREST_NEIGHBOR` debayering for performance. Saved images use `HQ_LINEAR` debayering for maximum quality.

---

## Config files

Config files are saved and loaded as YAML. A saved config stores (for example):

```yaml
general:
  creator: Aaron Harmer
  taxon_name: Aenetus virescens
  output_folder: /path/to/output
  num_label_cameras: 2
camera_settings:
  camera_0:
    camera_type: FLIR
    selected_camera: FLIR Camera 0
    exposure_ms: 50.0
    gain_level: 0
    gamma: 1.0
  camera_1:
    camera_type: Webcam
    selected_camera: Webcam 0
    exposure_ms: 50.0
    gain_level: 0
    gamma: 1.0
```

---

## Architecture notes

- All camera streaming runs on `QThreadPool` worker threads via the `Worker` / `WorkerSignals` pattern
- UI updates from worker threads use Qt signals (`_label_frame_signal`, `_barcode_frame_signal`) — direct widget access from threads is never used
- Each `LabelCameraSlot` owns its own `FLIRCamera` instance, allowing different physical FLIR cameras to be used in different slots independently
- Webcam discovery probes each index in a daemon thread with a 3-second timeout to prevent DirectShow from hanging on empty indices
- The live view image pipeline resizes frames to display dimensions before colour conversion and QImage construction, reducing per-frame CPU cost by 6–10× compared to converting at full camera resolution
- DataMatrix decoding runs every 5th frame with a cached last result, and falls back to adaptive thresholding when direct grayscale decoding fails

---

## Known limitations

- FLIR `get_frame_hq()` briefly pauses the live stream during capture; with multiple FLIR cameras this is sequential, not simultaneous
- Config file loading does not currently restore camera slot count or re-open camera handles; it only restores creator, taxon name, and output folder

---

## License

Images captured with RAPIIDlite are tagged with a CC-BY 4.0 license. The application code itself is under a GPL-3.0 license.

---

## Acknowledgements

- [Spinnaker SDK](https://www.flir.com/products/spinnaker-sdk/) — FLIR Systems
- [pylibdmtx](https://github.com/NaturalHistoryMuseum/pylibdmtx) — Natural History Museum, London
- [qt-material](https://github.com/UN-GCPDS/qt-material) — UN-GCPDS
- [OpenCV](https://opencv.org/)