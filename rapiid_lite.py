import sys
import os
import csv
import traceback
from pathlib import Path
import datetime
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from GUI.rapiidlite_GUI import Ui_MainWindow  # importing main window of the GUI
import cv2
import numpy as np
import pylibdmtx.pylibdmtx as dmtx

# Optional imports with error handling
try:
    import scripts.ymlRW as ymlRW
    YML_AVAILABLE = True
except ImportError:
    print("Warning: scripts.ymlRW not available. Config file functionality disabled.")
    YML_AVAILABLE = False

try:
    from qt_material import apply_stylesheet
    QT_MATERIAL_AVAILABLE = True
except ImportError:
    print("Warning: qt_material not available. Using default theme.")
    QT_MATERIAL_AVAILABLE = False

try:
    from PIL import Image
    import piexif
    EXIF_AVAILABLE = True
except ImportError:
    print("Warning: PIL/piexif not available. EXIF embedding disabled.")
    EXIF_AVAILABLE = False

# FLIR camera imports
try:
    import PySpin
    FLIR_AVAILABLE = True
    print("FLIR PySpin library loaded successfully.")
except ImportError:
    FLIR_AVAILABLE = False
    print("FLIR PySpin library not available. FLIR camera functionality disabled.")


# ──────────────────────────────────────────────────────────────────────────────
# Threading helpers
# ──────────────────────────────────────────────────────────────────────────────

class WorkerSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(int)
    frame_ready = QtCore.pyqtSignal(QtGui.QPixmap, QtWidgets.QLabel)


class Worker(QtCore.QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.kwargs['progress_callback'] = self.signals.progress

    @QtCore.pyqtSlot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


# ──────────────────────────────────────────────────────────────────────────────
# FLIR camera
# ──────────────────────────────────────────────────────────────────────────────

class FLIRCamera:
    """Handles all PySpin operations for a single FLIR camera."""

    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.system = None
        self.cam_list = None
        self.camera = None
        self.is_initialized = False
        self.is_acquiring = False

    def initialize(self):
        if not FLIR_AVAILABLE:
            return False
        try:
            self.system = PySpin.System.GetInstance()
            self.cam_list = self.system.GetCameras()
            if self.cam_list.GetSize() == 0:
                print("No FLIR cameras detected")
                self.cleanup()
                return False
            if self.camera_index >= self.cam_list.GetSize():
                print(f"FLIR camera index {self.camera_index} out of range "
                      f"({self.cam_list.GetSize()} camera(s) found)")
                self.cleanup()
                return False
            self.camera = self.cam_list[self.camera_index]
            self.camera.Init()

            try:
                self.camera.TLStream.StreamBufferHandlingMode.SetValue(
                    PySpin.StreamBufferHandlingMode_NewestOnly
                )
            except Exception:
                print("Warning: could not set StreamBufferHandlingMode")

            try:
                self.camera.TLStream.StreamBufferCountMode.SetValue(
                    PySpin.StreamBufferCountMode_Manual
                )
                self.camera.TLStream.StreamBufferCountManual.SetValue(2)
            except Exception:
                print("Warning: could not set StreamBufferCount")

            self.is_initialized = True
            print("FLIR camera initialized successfully")
            return True
        except Exception as ex:
            print(f"Error initializing FLIR camera: {ex}")
            return False

    def configure_camera(self, exposure=None, gain=None, gamma=None,
                         set_acquisition_mode=True, live_fps=20):
        if not self.is_initialized:
            return False
        try:
            if set_acquisition_mode:
                if self.camera.AcquisitionMode.GetAccessMode() == PySpin.RW:
                    self.camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
                else:
                    print("AcquisitionMode not writable — camera may already be streaming")

            if set_acquisition_mode and live_fps is not None:
                try:
                    if self.camera.AcquisitionFrameRateEnable.GetAccessMode() == PySpin.RW:
                        self.camera.AcquisitionFrameRateEnable.SetValue(True)
                        max_fps = self.camera.AcquisitionFrameRate.GetMax()
                        self.camera.AcquisitionFrameRate.SetValue(min(float(live_fps), max_fps))
                except Exception:
                    print("Warning: hardware frame rate cap not available on this camera")

            if exposure is not None:
                self.camera.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
                min_e = self.camera.ExposureTime.GetMin()
                max_e = self.camera.ExposureTime.GetMax()
                self.camera.ExposureTime.SetValue(max(min_e, min(float(exposure), max_e)))

            if gain is not None:
                self.camera.GainAuto.SetValue(PySpin.GainAuto_Off)
                min_g = self.camera.Gain.GetMin()
                max_g = self.camera.Gain.GetMax()
                self.camera.Gain.SetValue(max(min_g, min(float(gain), max_g)))

            if gamma is not None:
                try:
                    if self.camera.Gamma.GetAccessMode() == PySpin.RW:
                        self.camera.GammaEnable.SetValue(True)
                        min_gm = self.camera.Gamma.GetMin()
                        max_gm = self.camera.Gamma.GetMax()
                        self.camera.Gamma.SetValue(max(min_gm, min(float(gamma), max_gm)))
                except Exception:
                    pass

            return True
        except Exception as ex:
            print(f"Error configuring FLIR camera: {ex}")
            return False

    def start_acquisition(self):
        if not self.is_initialized:
            return False
        try:
            self.configure_camera(set_acquisition_mode=True)
            self.camera.BeginAcquisition()
            self.is_acquiring = True
            return True
        except Exception as ex:
            print(f"Error starting acquisition: {ex}")
            return False

    def stop_acquisition(self):
        if not self.is_initialized:
            return
        try:
            self.is_acquiring = False
            self.camera.EndAcquisition()
        except Exception:
            pass

    def get_frame(self):
        if not self.is_initialized or not self.is_acquiring:
            return None
        try:
            try:
                exposure_ms = self.camera.ExposureTime.GetValue() / 1000.0
                timeout_ms = max(200, int(exposure_ms) + 100)
            except Exception:
                timeout_ms = 500

            image_result = self.camera.GetNextImage(timeout_ms)
            if image_result.IsIncomplete():
                image_result.Release()
                return None

            image_converted = image_result.Convert(
                PySpin.PixelFormat_BGR8, PySpin.NEAREST_NEIGHBOR
            )
            image_data = image_converted.GetNDArray().copy()
            image_result.Release()
            return image_data

        except PySpin.SpinnakerException as ex:
            error_str = str(ex)
            if not any(code in error_str for code in ("-1011", "-1013", "-1010")):
                print(f"Error getting frame: {ex}")
            return None
        except Exception as ex:
            print(f"Unexpected error getting frame: {ex}")
            return None

    def get_frame_hq(self):
        """Grab a single HQ_LINEAR frame for saving. Pauses live stream temporarily."""
        if not self.is_initialized:
            return None

        was_acquiring = self.is_acquiring
        if was_acquiring:
            self.stop_acquisition()

        frame = None
        try:
            self.camera.BeginAcquisition()
            self.is_acquiring = True

            try:
                exposure_ms = self.camera.ExposureTime.GetValue() / 1000.0
                timeout_ms = max(200, int(exposure_ms) + 500)
            except Exception:
                timeout_ms = 2000

            image_result = self.camera.GetNextImage(timeout_ms)
            if not image_result.IsIncomplete():
                image_converted = image_result.Convert(
                    PySpin.PixelFormat_BGR8, PySpin.HQ_LINEAR
                )
                frame = image_converted.GetNDArray().copy()
            image_result.Release()

        except Exception as ex:
            print(f"Error capturing HQ frame: {ex}")
        finally:
            self.stop_acquisition()
            if was_acquiring:
                self.camera.BeginAcquisition()
                self.is_acquiring = True

        return frame

    def cleanup(self):
        try:
            if self.camera and self.is_initialized:
                self.is_acquiring = False
                try:
                    self.camera.EndAcquisition()
                except Exception:
                    pass
                self.camera.DeInit()

            self.camera = None
            self.is_initialized = False

            if self.cam_list:
                self.cam_list.Clear()
                self.cam_list = None
            if self.system:
                self.system.ReleaseInstance()
                self.system = None

            print("FLIR camera cleanup completed")
        except Exception as ex:
            print(f"Error during cleanup: {ex}")


# ──────────────────────────────────────────────────────────────────────────────
# Metadata helpers
# ──────────────────────────────────────────────────────────────────────────────

class ExifManager:
    @staticmethod
    def add_exif_to_image(image_path, creator, taxon, accession, device_info, institution=""):
        if not EXIF_AVAILABLE:
            return False, "EXIF embedding skipped (PIL/piexif not installed)"
        try:
            now = datetime.datetime.now()
            rights = institution if institution else "Manaaki Whenua Landcare Research"
            exif_dict = {
                "0th": {
                    piexif.ImageIFD.Copyright: f"CC-BY 4.0 {now.year} {rights}".encode(),
                    piexif.ImageIFD.Artist: creator.encode(),
                    piexif.ImageIFD.DateTime: now.strftime("%Y:%m:%d %H:%M:%S").encode(),
                    piexif.ImageIFD.Make: b"RAPIIDlite",
                    piexif.ImageIFD.Model: device_info.encode(),
                    piexif.ImageIFD.Software: b"RAPIIDlite v3.1",
                    piexif.ImageIFD.ImageDescription: f"Specimen: {taxon} - {accession} - LABEL".encode(),
                },
                "Exif": {
                    piexif.ExifIFD.DateTimeOriginal: now.strftime("%Y:%m:%d %H:%M:%S").encode(),
                    piexif.ExifIFD.DateTimeDigitized: now.strftime("%Y:%m:%d %H:%M:%S").encode(),
                    piexif.ExifIFD.UserComment: f"Taxon: {taxon}, Accession: {accession}".encode(),
                },
                "GPS": {},
                "1st": {},
                "thumbnail": None,
            }
            exif_bytes = piexif.dump(exif_dict)
            img = Image.open(image_path)
            img.save(image_path, exif=exif_bytes)
            img.close()
            return True, f"EXIF data added to {os.path.basename(image_path)}"
        except Exception as e:
            return False, f"Failed to add EXIF data: {e}"

    @staticmethod
    def get_csv_data(creator, taxon, accession, file_format, device_info="", tag="_label", institution=""):
        now = datetime.datetime.now()
        rights = institution if institution else "Manaaki Whenua Landcare Research"
        return {
            'image_filename': f"{accession}{tag}{file_format}",
            'accession_number': accession,
            'taxon_name': taxon,
            'image_format': file_format.replace('.', '').upper(),
            'copyright_type': f"CC-BY 4.0 {now.year}",
            'rights_owner': rights,
            'creator': creator,
            'date_captured': now.strftime("%Y-%m-%d %H:%M:%S"),
            'capture_device': device_info or "RAPIIDlite",
            'caption': f"{accession} - Specimen label",
            'title': f"{taxon} - {accession} - Specimen label",
        }


class FileManager:
    CSV_HEADERS = [
        'image_filename', 'accession_number', 'taxon_name', 'image_format',
        'copyright_type', 'rights_owner', 'creator', 'date_captured',
        'capture_device', 'caption', 'title',
    ]

    @staticmethod
    def create_folders(output_path):
        output_path = Path(output_path)
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
            return True, f"Created folder: {output_path}"
        return False, ""

    @staticmethod
    def create_or_update_csv(output_location, taxon, csv_data):
        taxon_folder = Path(output_location).joinpath(taxon)
        csv_path = taxon_folder.joinpath(f"{taxon}_captures.csv")
        file_exists = csv_path.exists()
        try:
            taxon_folder.mkdir(parents=True, exist_ok=True)
            with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=FileManager.CSV_HEADERS)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(csv_data)
            return True, f"Saved capture metadata to {csv_path.name}"
        except Exception as e:
            return False, f"Failed to write CSV: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# Fixed-aspect-ratio live view label
# ──────────────────────────────────────────────────────────────────────────────

class AspectRatioLabel(QLabel):
    """QLabel that enforces a fixed aspect ratio.

    Uses setFixedHeight inside resizeEvent to lock the height, with a
    recursion guard to prevent the infinite loop that setFixedHeight
    would otherwise cause (it triggers another resizeEvent).
    """

    def __init__(self, ratio_w=16, ratio_h=9, parent=None):
        super().__init__(parent)
        self._ratio_w = ratio_w
        self._ratio_h = ratio_h
        self._resizing = False             # recursion guard
        self.setMinimumSize(200, 112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "QLabel { border: 2px solid #2979ff; border-radius: 4px; padding: 2px; }"
        )

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return int(width * self._ratio_h / self._ratio_w)

    def sizeHint(self):
        w = max(self.width(), 400)
        return QtCore.QSize(w, self.heightForWidth(w))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._resizing:
            return
        new_h = self.heightForWidth(event.size().width())
        cap = self.maximumHeight()
        if 0 < cap < 16777215:
            new_h = min(new_h, cap)
        if self.height() != new_h:
            self._resizing = True
            try:
                self.setFixedHeight(new_h)
            finally:
                self._resizing = False


# ──────────────────────────────────────────────────────────────────────────────
# LabelCameraSlot — one self-contained label camera widget
# ──────────────────────────────────────────────────────────────────────────────

class LabelCameraSlot(QWidget):
    """
    Self-contained widget representing one label camera.

    Each slot owns its live-view QLabel, start/stop button, camera dropdown,
    and FLIR exposure/gain/gamma spinboxes.  The UI class creates/destroys
    these dynamically and iterates over them at capture time.
    """

    def __init__(self, slot_index, webcams, flir_count, frame_signal, parent=None):
        super().__init__(parent)
        self.slot_index = slot_index
        self.flir_count = flir_count
        self.frame_signal = frame_signal

        # Each slot owns its own FLIRCamera instance so multiple slots can
        # use different physical FLIR cameras independently.
        self.flir_camera = None

        # Per-slot streaming state
        self.label_webcamView = False
        self.label_camera_type = 'Webcam'
        self.cap = None
        self.frame = None
        self.selected_camera = ''   # empty until user makes a selection
        self._taken_cameras = set() # cameras currently claimed by other slots

        self._settings_timer = QtCore.QTimer()
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(400)
        self._settings_timer.timeout.connect(self._apply_camera_settings)

        self._build_ui(webcams, flir_count)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self, webcams, flir_count):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        # The slot itself must be Expanding so the QGridLayout stretches it
        # to fill its cell uniformly across both columns.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Header row: bold title + Remove button
        header_row = QHBoxLayout()
        self.header_label = QLabel(f"Label camera {self.slot_index + 1}")
        bold = QtGui.QFont()
        bold.setFamilies(["Segoe UI", "system-ui", "ui-sans-serif", "sans-serif"])
        bold.setBold(True)
        bold.setPointSize(10)
        self.header_label.setFont(bold)
        self.remove_btn = QPushButton("× Remove")
        self.remove_btn.setFixedWidth(110)
        header_row.addWidget(self.header_label)
        header_row.addStretch()
        header_row.addWidget(self.remove_btn)
        layout.addLayout(header_row)

        # Controls row — above the live view so they're always visible
        controls = QHBoxLayout()

        # Start/stop button
        btn_col = QVBoxLayout()
        btn_col.addWidget(QLabel(" "))
        self.start_btn = QPushButton("Start live view")
        self.start_btn.setMinimumWidth(130)
        self.start_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_col.addWidget(self.start_btn)
        controls.addLayout(btn_col)

        # Camera selection dropdown — webcams + numbered FLIR entries
        cam_col = QVBoxLayout()
        cam_col.addWidget(QLabel(" "))
        self.cam_combo = QComboBox()
        # Placeholder — selectable (so users can return to it to deselect),
        # styled italic and muted so it reads as a prompt rather than a camera.
        self.cam_combo.addItem("— Select camera —")
        _ph = self.cam_combo.model().item(0)
        _phf = _ph.font(); _phf.setItalic(True); _ph.setFont(_phf)
        _ph.setForeground(QtGui.QColor(150, 150, 150))
        for name in webcams:
            self.cam_combo.addItem(name)
        for i in range(flir_count):
            self.cam_combo.addItem(f"FLIR Camera {i}")
        cam_col.addWidget(self.cam_combo)
        controls.addLayout(cam_col)

        # Exposure spinbox — displayed in milliseconds, converted to µs for FLIR
        exp_col = QVBoxLayout()
        exp_col.addWidget(QLabel("Exposure (ms)"))
        self.exposure_spinbox = QDoubleSpinBox()
        self.exposure_spinbox.setRange(0.1, 1000.0)
        self.exposure_spinbox.setDecimals(1)
        self.exposure_spinbox.setSingleStep(1.0)
        self.exposure_spinbox.setValue(50.0)
        self.exposure_spinbox.setSuffix(" ms")
        exp_col.addWidget(self.exposure_spinbox)
        controls.addLayout(exp_col)

        # Gain spinbox (FLIR only)
        gain_col = QVBoxLayout()
        gain_col.addWidget(QLabel("Gain level (dB)"))
        self.gain_spinbox = QSpinBox()
        self.gain_spinbox.setRange(0, 40)
        self.gain_spinbox.setValue(0)
        gain_col.addWidget(self.gain_spinbox)
        controls.addLayout(gain_col)

        # Gamma spinbox (FLIR only)
        gamma_col = QVBoxLayout()
        gamma_col.addWidget(QLabel("Gamma correction"))
        self.gamma_spinbox = QSpinBox()
        self.gamma_spinbox.setRange(1, 300)
        self.gamma_spinbox.setValue(100)
        gamma_col.addWidget(self.gamma_spinbox)
        controls.addLayout(gamma_col)

        controls.addStretch()
        layout.addLayout(controls)

        # Live view — sits below controls, expands to fill remaining cell space
        self.live_view = AspectRatioLabel(ratio_w=16, ratio_h=9)
        layout.addWidget(self.live_view, stretch=1)

        # No separator — the tile border provides enough visual separation
        # in the grid and a horizontal rule between cells adds clutter.

        # FLIR controls start disabled — enabled when FLIR is selected
        self._set_flir_controls_enabled(False)

        # Wire up signals
        self.cam_combo.currentTextChanged.connect(self._on_camera_changed)
        self.exposure_spinbox.valueChanged.connect(lambda _: self._settings_timer.start())
        self.gain_spinbox.valueChanged.connect(lambda _: self._settings_timer.start())
        self.gamma_spinbox.valueChanged.connect(lambda _: self._settings_timer.start())

        # No camera is opened until the user makes a selection — the placeholder
        # prevents any camera handle being claimed before the user chooses.

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _set_flir_controls_enabled(self, enabled):
        self.exposure_spinbox.setEnabled(enabled)
        self.gain_spinbox.setEnabled(enabled)
        self.gamma_spinbox.setEnabled(enabled)

    def _open_cap(self, camera_name):
        """Open a VideoCapture handle for a webcam device.

        Uses DirectShow on Windows to avoid MSMF grab errors (-1072873821).
        """
        try:
            if self.cap:
                self.cap.release()
                self.cap = None
            if camera_name.startswith("Webcam"):
                webcam_id = int(camera_name.split()[-1])
                backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
                self.cap = cv2.VideoCapture(webcam_id, backend)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        except Exception as e:
            print(f"Slot {self.slot_index}: error opening cap for {camera_name}: {e}")

    def _on_camera_changed(self, selected):
        """Respond to the user picking a different camera in the dropdown."""
        try:
            # If the selected camera is taken by another slot/barcode, revert
            # immediately without opening any hardware handle.
            if selected and selected != "— Select camera —" and selected in self._taken_cameras:
                self.cam_combo.blockSignals(True)
                # Revert to previous selection or placeholder
                prev = self.selected_camera if self.selected_camera else "— Select camera —"
                idx = self.cam_combo.findText(prev)
                if idx >= 0:
                    self.cam_combo.setCurrentIndex(idx)
                self.cam_combo.blockSignals(False)
                return
            # Clean up existing FLIR instance if switching away from it
            if self.flir_camera and self.flir_camera.is_initialized:
                self.flir_camera.stop_acquisition()
                self.flir_camera.cleanup()
                self.flir_camera = None

            if selected == "— Select camera —" or not selected:
                self.selected_camera = ''
                self.label_camera_type = 'Webcam'
                self._set_flir_controls_enabled(False)
                if self.cap:
                    self.cap.release()
                    self.cap = None

            elif selected.startswith("Webcam"):
                self.label_camera_type = 'Webcam'
                self._set_flir_controls_enabled(False)
                self.selected_camera = selected
                self._open_cap(selected)

            elif selected.startswith("FLIR Camera") and FLIR_AVAILABLE:
                self.label_camera_type = 'FLIR'
                self._set_flir_controls_enabled(True)
                flir_index = int(selected.split()[-1])
                self.flir_camera = FLIRCamera(camera_index=flir_index)
                if self.flir_camera.initialize():
                    self.selected_camera = selected
                    self._apply_camera_settings()
                else:
                    print(f"Slot {self.slot_index}: FLIR Camera {flir_index} failed to initialize")
                    self.flir_camera = None
                    self.selected_camera = ''

            # Notify the parent UI to refresh availability across all slots
            if self.parent() and hasattr(self.parent(), '_refresh_camera_availability'):
                self.parent()._refresh_camera_availability()

        except Exception as e:
            print(f"Slot {self.slot_index}: error changing camera: {e}")

    def _apply_camera_settings(self):
        """Push current spinbox values to the FLIR camera (debounced)."""
        try:
            if self.label_camera_type != 'FLIR':
                return
            if not (self.flir_camera and self.flir_camera.is_initialized):
                return
            exposure = self.exposure_spinbox.value() * 1000.0   # ms → µs
            gain = self.gain_spinbox.value()
            gamma = self.gamma_spinbox.value() / 100.0
            was_streaming = self.label_webcamView
            if was_streaming:
                self.flir_camera.stop_acquisition()
            self.flir_camera.configure_camera(
                exposure=exposure, gain=gain, gamma=gamma,
                set_acquisition_mode=False
            )
            if was_streaming:
                self.flir_camera.start_acquisition()
        except Exception as e:
            print(f"Slot {self.slot_index}: error applying settings: {e}")

    # ── Public interface ───────────────────────────────────────────────────────

    def sync_camera_availability(self, taken_cameras):
        """Visually mark taken cameras and store the taken set for the
        signal handler to enforce when the user makes a selection."""
        self._taken_cameras = taken_cameras
        model = self.cam_combo.model()
        for i in range(self.cam_combo.count()):
            item = model.item(i)
            name = item.text()
            if name == "— Select camera —":
                continue
            if name in taken_cameras:
                item.setForeground(QtGui.QColor(150, 150, 150))
                font = item.font(); font.setItalic(True); item.setFont(font)
            else:
                item.setForeground(QtGui.QColor())   # reset to theme default
                font = item.font(); font.setItalic(False); item.setFont(font)

    def get_frame_for_capture(self):
        """Return the best available frame for saving to disk."""
        if self.label_camera_type == 'FLIR' and self.flir_camera and self.flir_camera.is_initialized:
            return self.flir_camera.get_frame_hq()
        return self.frame

    def get_device_info(self):
        """Short description of the active camera for EXIF/CSV metadata."""
        try:
            if self.label_camera_type == 'FLIR' and self.flir_camera and self.flir_camera.is_initialized:
                cam = self.flir_camera.camera
                try:
                    model = cam.DeviceModelName.GetValue()
                    serial = cam.DeviceSerialNumber.GetValue()
                    return f"FLIR {model} S/N:{serial}"
                except Exception:
                    return "FLIR Camera"
            elif self.cap:
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(self.cap.get(cv2.CAP_PROP_FPS))
                return f"Webcam ({width}x{height} @ {fps}fps)"
        except Exception:
            pass
        return "Unknown device"

    def cleanup(self):
        """Release all camera resources owned by this slot."""
        self.label_webcamView = False
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.flir_camera and self.flir_camera.is_initialized:
            self.flir_camera.stop_acquisition()
            self.flir_camera.cleanup()
            self.flir_camera = None


# ──────────────────────────────────────────────────────────────────────────────
# Reusable progress dialog
# ──────────────────────────────────────────────────────────────────────────────

class ProgressDialog(QDialog):
    """
    A small, always-on-top dialog with a status label and progress bar.

    Usage — indeterminate (e.g. discovery):
        dlg = ProgressDialog(parent, title="Discovering cameras",
                             message="Searching for connected cameras…")
        dlg.show()
        # … later:
        dlg.close()

    Usage — determinate (e.g. multi-camera capture):
        dlg = ProgressDialog(parent, title="Capturing",
                             message="Saving images…", maximum=3)
        dlg.show()
        dlg.set_step(1, "Capturing camera 1 of 3…")
        dlg.set_step(2, "Capturing camera 2 of 3…")
        dlg.set_step(3, "Capturing camera 3 of 3…")
        dlg.close()
    """

    def __init__(self, parent, title, message, maximum=0):
        """
        maximum=0  → indeterminate (bouncing) bar
        maximum>0  → determinate bar, range 0..maximum
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowTitleHint |
            Qt.WindowStaysOnTopHint |
            Qt.CustomizeWindowHint   # hides the close button so user can't dismiss it
        )
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._label = QLabel(message)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setMinimum(0)
        self._bar.setMaximum(maximum)   # 0 = indeterminate
        self._bar.setValue(0)
        self._bar.setTextVisible(maximum > 0)
        self._bar.setMinimumHeight(22)
        layout.addWidget(self._bar)

        self.adjustSize()

    def set_step(self, step, message=None):
        """Advance the bar to `step` and optionally update the label text."""
        self._bar.setValue(step)
        if message:
            self._label.setText(message)
        QApplication.processEvents()   # keep UI responsive between steps


# ──────────────────────────────────────────────────────────────────────────────
# Main UI window
# ──────────────────────────────────────────────────────────────────────────────

class UI(QMainWindow):
    # Signals used by worker threads to push frames safely to the main thread
    _label_frame_signal = QtCore.pyqtSignal(QtGui.QPixmap, QtWidgets.QLabel)
    _barcode_frame_signal = QtCore.pyqtSignal(QtGui.QPixmap, QtWidgets.QLabel)

    def __init__(self):
        super(UI, self).__init__()
        try:
            self.exit_program = False
            self.ui = Ui_MainWindow()
            self.ui.setupUi(self)

            # Load app icon — taskbar, window title bar, and header bar
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
            else:
                app_dir = Path(__file__).parent

            ico_path = app_dir / "images" / "RAPIIDlite_icon.ico"
            png_path = app_dir / "images" / "RAPIIDlite_icon.png"

            # Window/taskbar icon — .ico preferred (Windows picks the right
            # frame size itself), .png fallback
            win_icon = ico_path if ico_path.exists() else png_path
            if win_icon.exists():
                self.setWindowIcon(QtGui.QIcon(str(win_icon)))

            # Header bar pixmap — always from the high-res PNG so the 44px
            # scale-down stays crisp (QPixmap grabs a single small frame from
            # an .ico, which looks blurry when upscaled)
            if png_path.exists():
                icon_pixmap = QtGui.QPixmap(str(png_path)).scaled(
                    44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.ui.headerIconLabel.setPixmap(icon_pixmap)
            else:
                # Fallback: blue rounded square matching brand colour
                self.ui.headerIconLabel.setStyleSheet(
                    "background-color: #2979ff; border-radius: 10px;"
                )

            self.threadpool = QtCore.QThreadPool()
            print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

            # ── Global state ──────────────────────────────────────────────────
            self.file_format = ".jpg"
            self.label_slots = []           # list[LabelCameraSlot]
            self._all_webcams = []          # full discovered webcam list (for adding new slots)
            self._flir_count = 0            # number of FLIR cameras found at discovery

            # Barcode camera
            self.barcode_webcamView = False
            self.selected_barcodecam = ''
            self._barcode_taken_cameras = set()  # label cameras taken, for barcode revert guard
            self.webcam_arr_barcode = []
            self.cap_barcode = None

            # ── Setup that doesn't need camera hardware ───────────────────────
            self.setup_ui_connections()
            self.setup_file_system()
            self.setup_config_system()

            # Show immediately — camera discovery happens on a background thread
            self.showMaximized()
            self._set_camera_controls_enabled(False)
            self.statusBar().showMessage("Discovering cameras…")

            self._discovery_dlg = ProgressDialog(
                self,
                title="Please wait",
                message="Searching for connected cameras…\n"
                        "This may take a few seconds.",
            )
            self._discovery_dlg.show()
            QApplication.processEvents()

            worker = Worker(self._discover_webcams)
            worker.signals.result.connect(self._on_cameras_discovered)
            worker.signals.error.connect(self._on_discovery_error)
            self.threadpool.start(worker)

        except Exception as e:
            print(f"Error during UI initialization: {e}")
            traceback.print_exc()
            sys.exit(1)

    # ── Camera discovery ───────────────────────────────────────────────────────

    def _discover_webcams(self, **kwargs):
        """Scan webcam indices and count FLIR cameras. Runs on a worker thread.

        On Windows, cv2.VideoCapture(index, CAP_DSHOW) can hang indefinitely
        when probing an index with no device. Each probe runs in a daemon thread
        with a 3-second timeout to avoid blocking forever.

        Returns a dict: {'webcams': [...], 'flir_count': N}
        """
        import threading

        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        webcams = []

        def _probe(index, result):
            try:
                cap = cv2.VideoCapture(index, backend)
                if cap.isOpened():
                    ret, _ = cap.read()
                    cap.release()
                    if ret:
                        result['ok'] = True
                else:
                    cap.release()
            except Exception:
                pass

        for index in range(10):
            result = {'ok': False}
            t = threading.Thread(target=_probe, args=(index, result), daemon=True)
            t.start()
            t.join(timeout=3.0)
            if not result['ok']:
                break
            webcams.append(f"Webcam {index}")

        # Count FLIR cameras via Spinnaker (fast — no frame grab needed)
        flir_count = 0
        if FLIR_AVAILABLE:
            try:
                system = PySpin.System.GetInstance()
                cam_list = system.GetCameras()
                flir_count = cam_list.GetSize()
                cam_list.Clear()
                system.ReleaseInstance()
            except Exception as e:
                print(f"FLIR discovery error: {e}")

        return {'webcams': webcams, 'flir_count': flir_count}

    @QtCore.pyqtSlot(object)
    def _on_cameras_discovered(self, result):
        """Main-thread slot: populate UI once discovery finishes."""
        self._discovery_dlg.close()
        self._all_webcams = result['webcams']
        self._flir_count = result['flir_count']
        self.webcam_arr_barcode = result['webcams']

        self._add_label_slot()
        self.setup_barcode_camera_selection()

        self._set_camera_controls_enabled(True)

        parts = []
        if self._all_webcams:
            parts.append(f"{len(self._all_webcams)} webcam(s)")
        if self._flir_count:
            parts.append(f"{self._flir_count} FLIR camera(s)")
        msg = "Found " + " and ".join(parts) + "." if parts else "No cameras detected."
        self.statusBar().showMessage(msg, 4000)

    @QtCore.pyqtSlot(tuple)
    def _on_discovery_error(self, error_tuple):
        _, value, _ = error_tuple
        print(f"Camera discovery error: {value}")
        self._discovery_dlg.close()
        self._set_camera_controls_enabled(True)
        self.statusBar().showMessage("Camera discovery failed — see console for details.", 5000)

    # ── Slot management ────────────────────────────────────────────────────────

    def _get_label_container(self):
        """Return the permanent QGridLayout installed in setup_ui_connections."""
        return self._label_grid

    def _retile_grid(self):
        """Re-position all slots in the grid.

        1 slot  → spans both columns, live_view capped at 450px so controls
                   remain visible without scrolling on any typical screen.
        2+ slots → 2-column grid, live_view uncapped (naturally sized by 16:9).

        A stretch row at the bottom absorbs spare vertical space so slots stay
        compact rather than being spread across the full panel height.
        """
        grid = self._get_label_container()

        for slot in self.label_slots:
            grid.removeWidget(slot)
        for r in range(grid.rowCount()):
            grid.setRowStretch(r, 0)

        n = len(self.label_slots)
        if n == 1:
            slot = self.label_slots[0]
            slot.live_view.setMaximumHeight(16777215)
            grid.addWidget(slot, 0, 0, 1, 2)
            grid.setRowStretch(0, 0)
            grid.setRowStretch(1, 1)
        else:
            n_rows = (n + 1) // 2
            for i, slot in enumerate(self.label_slots):
                slot.live_view.setMaximumHeight(16777215)
                slot.setMaximumWidth(16777215)
                grid.addWidget(slot, i // 2, i % 2)
                grid.setRowStretch(i // 2, 0)
            grid.setRowStretch(n_rows, 1)

        self._update_single_slot_width()
        QtCore.QTimer.singleShot(100, self._update_single_slot_width)

    def _add_label_slot(self, webcams=None):
        """Create a new LabelCameraSlot and tile it into the grid."""
        try:
            if webcams is None:
                webcams = self._all_webcams

            idx = len(self.label_slots)
            slot = LabelCameraSlot(
                slot_index=idx,
                webcams=webcams,
                flir_count=self._flir_count,
                frame_signal=self._label_frame_signal,
                parent=self,
            )
            slot.start_btn.pressed.connect(lambda s=slot: self.begin_label_camera(s))
            slot.remove_btn.pressed.connect(lambda s=slot: self._remove_label_slot(s))

            self.label_slots.append(slot)
            self._retile_grid()
            self._update_remove_buttons()
            self._refresh_camera_availability()

            if idx > 0:
                self.log_info(f"Added label camera {idx + 1}.")

        except Exception as e:
            print(f"Error adding label slot: {e}")
            self.log_info(f"Error adding label camera: {e}")

    def _remove_label_slot(self, slot):
        """Stop, remove, and re-tile the label camera grid."""
        try:
            if len(self.label_slots) <= 1:
                return

            if slot.label_webcamView:
                slot.label_webcamView = False
                if slot.label_camera_type == 'FLIR' and slot.flir_camera:
                    slot.flir_camera.stop_acquisition()
                QtCore.QThread.msleep(200)

            slot.cleanup()
            slot.setParent(None)
            slot.deleteLater()
            self.label_slots.remove(slot)

            # Re-number remaining slots
            for i, s in enumerate(self.label_slots):
                s.slot_index = i
                s.header_label.setText(f"Label camera {i + 1}")

            self._retile_grid()
            self._update_remove_buttons()
            self._refresh_camera_availability()
            self.log_info(f"Removed label camera. {len(self.label_slots)} remaining.")

        except Exception as e:
            print(f"Error removing label slot: {e}")
            self.log_info(f"Error removing label camera: {e}")

    def _update_remove_buttons(self):
        """Disable Remove on the last slot (must always have at least one)."""
        only_one = len(self.label_slots) == 1
        for slot in self.label_slots:
            slot.remove_btn.setEnabled(not only_one)

    def _refresh_camera_availability(self):
        """Update all dropdowns to reflect which cameras are taken.

        Taken cameras are shown in grey/italic and — critically — the
        signal handlers revert the selection if a taken item is picked,
        since qt_material's delegate ignores item flags for blocking clicks.
        """
        label_selected = {s.selected_camera for s in self.label_slots if s.selected_camera}
        barcode_selected = self.selected_barcodecam if self.selected_barcodecam else ''
        all_taken = label_selected | ({barcode_selected} if barcode_selected else set())

        # Update each label slot's taken set and visual state
        for slot in self.label_slots:
            others = all_taken - ({slot.selected_camera} if slot.selected_camera else set())
            slot.sync_camera_availability(others)

        # Update barcode's taken set and visual state
        barcode_others = all_taken - ({barcode_selected} if barcode_selected else set())
        self._barcode_taken_cameras = barcode_others
        model = self.ui.comboBox_selectBarcodeCam.model()
        for i in range(self.ui.comboBox_selectBarcodeCam.count()):
            item = model.item(i)
            name = item.text()
            if name == "— Select camera —":
                continue
            if name in barcode_others:
                item.setForeground(QtGui.QColor(150, 150, 150))
                font = item.font(); font.setItalic(True); item.setFont(font)
            else:
                item.setForeground(QtGui.QColor())
                font = item.font(); font.setItalic(False); item.setFont(font)

    def _update_single_slot_width(self):
        """Cap the single slot's width to 80% of the window width so the
        live view is proportionally sized rather than spanning the full panel."""
        if len(self.label_slots) != 1:
            return
        target = max(400, int(self.width() * 0.80))
        self.label_slots[0].setMaximumWidth(target)

    def resizeEvent(self, event):
        """Keep the single-camera slot at 80% window width on resize."""
        super().resizeEvent(event)
        self._update_single_slot_width()

    # ── UI setup ───────────────────────────────────────────────────────────────

    def setup_ui_connections(self):
        try:
            self.ui.pushButton_capture.pressed.connect(self.capture_set)

            self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
            self.ui.shortcut_capture.activated.connect(self.capture_set)

            self.ui.pushButton_add_label_cam.pressed.connect(
                lambda: self._add_label_slot()
            )
            self.ui.pushButton_barcode_webcam.pressed.connect(
                lambda: self.begin_barcode_webcam(
                    cam_id=self.ui.barcode_camera,
                    button_id=self.ui.pushButton_barcode_webcam
                )
            )

            self._label_frame_signal.connect(self._display_frame)
            self._barcode_frame_signal.connect(self._display_frame)

            self.statusBar().showMessage("Ready")

            # Capture button flash timer
            self._capture_flash_timer = QtCore.QTimer(self)
            self._capture_flash_timer.setSingleShot(True)
            self._capture_flash_timer.setInterval(1500)
            self._capture_flash_timer.timeout.connect(self._clear_capture_flash)

            # Install the QGridLayout by replacing the scroll area's widget
            # entirely with a fresh one. This avoids any conflict with the
            # placeholder layout defined in the .ui file — Qt won't allow
            # setLayout() on a widget that already has one.
            container = QWidget()
            container.setStyleSheet("background-color: #f1f5f9;")
            self._label_grid = QGridLayout(container)
            self._label_grid.setContentsMargins(0, 0, 0, 0)
            self._label_grid.setSpacing(6)
            self._label_grid.setColumnStretch(0, 1)
            self._label_grid.setColumnStretch(1, 1)
            self.ui.labelCameraScrollArea.setWidget(container)

        except Exception as e:
            print(f"Error setting up UI connections: {e}")

    def _set_camera_controls_enabled(self, enabled: bool):
        """Enable/disable all camera-related controls (used during discovery)."""
        for slot in self.label_slots:
            slot.start_btn.setEnabled(enabled)
            slot.cam_combo.setEnabled(enabled)
        self.ui.pushButton_add_label_cam.setEnabled(enabled)
        self.ui.pushButton_barcode_webcam.setEnabled(enabled)
        self.ui.comboBox_selectBarcodeCam.setEnabled(enabled)
        self.ui.pushButton_capture.setEnabled(enabled)

    def setup_barcode_camera_selection(self):
        try:
            # Placeholder — selectable so users can return to it to deselect
            self.ui.comboBox_selectBarcodeCam.addItem("— Select camera —")
            _ph = self.ui.comboBox_selectBarcodeCam.model().item(0)
            _phf = _ph.font(); _phf.setItalic(True); _ph.setFont(_phf)
            _ph.setForeground(QtGui.QColor(150, 150, 150))

            for name in self.webcam_arr_barcode:
                self.ui.comboBox_selectBarcodeCam.addItem(name)

            self.ui.comboBox_selectBarcodeCam.currentTextChanged.connect(
                self.select_barcode_webcam
            )

            # Default to second webcam if available, else first
            if len(self.webcam_arr_barcode) > 1:
                self.ui.comboBox_selectBarcodeCam.setCurrentIndex(2)  # offset by placeholder
            elif len(self.webcam_arr_barcode) > 0:
                self.ui.comboBox_selectBarcodeCam.setCurrentIndex(1)

            if self.ui.comboBox_selectBarcodeCam.count() > 1:
                self.select_barcode_webcam()

        except Exception as e:
            print(f"Error setting up barcode camera selection: {e}")

    def setup_file_system(self):
        try:
            self.output_location = str(Path.home())
            self.update_output_location()
            self.ui.pushButton_outputFolder.pressed.connect(self.set_output_location)
            self.output_location_folder = Path(self.output_location)
        except Exception as e:
            print(f"Error setting up file system: {e}")

    def setup_config_system(self):
        try:
            self.config = self.get_default_values()
            self.loadedConfig = False
            if YML_AVAILABLE:
                self.ui.pushButton_load_config.pressed.connect(self.loadConfig)
                self.ui.pushButton_writeConfig.pressed.connect(self.writeConfig)
            else:
                self.ui.pushButton_load_config.setEnabled(False)
                self.ui.pushButton_writeConfig.setEnabled(False)
        except Exception as e:
            print(f"Error setting up config system: {e}")

    # ── Thread-safe display ────────────────────────────────────────────────────

    @QtCore.pyqtSlot(QtGui.QPixmap, QtWidgets.QLabel)
    def _display_frame(self, pixmap, label):
        label.setPixmap(pixmap)
        label.setAlignment(QtCore.Qt.AlignCenter)

    # ── Capture feedback ───────────────────────────────────────────────────────

    def _flash_capture_feedback(self, success: bool):
        if success:
            self.ui.pushButton_capture.setText("✓  Captured!")
            self.statusBar().showMessage("Image captured successfully.", 4000)
        else:
            self.ui.pushButton_capture.setText("✗  Failed!")
            self.statusBar().showMessage("Capture failed — check the log for details.", 4000)
        self._capture_flash_timer.start()

    def _clear_capture_flash(self):
        self.ui.pushButton_capture.setText("Capture image")

    # ── Barcode camera ─────────────────────────────────────────────────────────

    def select_barcode_webcam(self):
        try:
            selected_camera = self.ui.comboBox_selectBarcodeCam.currentText()

            # Revert if this camera is already taken by a label slot
            if (selected_camera and selected_camera != "— Select camera —"
                    and selected_camera in self._barcode_taken_cameras):
                self.ui.comboBox_selectBarcodeCam.blockSignals(True)
                prev = self.selected_barcodecam if self.selected_barcodecam else "— Select camera —"
                idx = self.ui.comboBox_selectBarcodeCam.findText(prev)
                if idx >= 0:
                    self.ui.comboBox_selectBarcodeCam.setCurrentIndex(idx)
                self.ui.comboBox_selectBarcodeCam.blockSignals(False)
                return

            if selected_camera == "— Select camera —" or not selected_camera:
                self.selected_barcodecam = ''
                if self.cap_barcode:
                    self.cap_barcode.release()
                    self.cap_barcode = None
                self._refresh_camera_availability()
                return
            if self.barcode_webcamView and self.cap_barcode:
                self.cap_barcode.release()
            webcam_id = int(selected_camera.split()[-1])
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            self.cap_barcode = cv2.VideoCapture(webcam_id, backend)
            self.cap_barcode.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap_barcode.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.selected_barcodecam = selected_camera
            self.log_info("Selected " + selected_camera)
            self._refresh_camera_availability()
        except Exception as e:
            print(f"Error selecting barcode webcam: {e}")
            self.log_info(f"Error selecting barcode camera: {e}")

    def begin_barcode_webcam(self, cam_id, button_id):
        try:
            selected_camera = self.ui.comboBox_selectBarcodeCam.currentText()
            if not self.barcode_webcamView:
                if selected_camera == "— Select camera —" or not selected_camera:
                    self.log_info("Barcode camera: please select a camera first.")
                    return
                label_conflict = any(
                    s.label_webcamView and s.selected_camera == selected_camera
                    for s in self.label_slots
                )
                if not label_conflict:
                    button_id.setText("Stop live view")
                    self.barcode_webcamView = True
                    self.log_info("Started barcode camera live view.")
                    self._refresh_camera_availability()
                    worker = Worker(self.update_barcode_webcam, cam_id)
                    self.threadpool.start(worker)
                else:
                    self.log_info("Selected camera is already in use by a label camera.")
            else:
                button_id.setText("Start live view")
                self.log_info("Ended barcode camera live view.")
                self.barcode_webcamView = False
                self._refresh_camera_availability()
        except Exception as e:
            print(f"Error in begin_barcode_webcam: {e}")
            self.log_info(f"Error with barcode camera: {e}")

    def update_barcode_webcam(self, cam_id, progress_callback):
        """Worker: stream and decode barcode camera frames.

        Decode runs on the full-res frame for accuracy.
        Display pipeline resizes BGR to widget size first so cvtColor,
        flip, putText, and QImage all operate on display-sized pixels.
        """
        import time
        target_fps = 15
        frame_interval = 1.0 / target_fps
        decode_interval = 5   # decode datamatrix on every Nth frame
        frame_count = 0
        last_decoded = None

        try:
            while self.barcode_webcamView and self.cap_barcode:
                t_start = time.monotonic()
                ret, frame = self.cap_barcode.read()

                if ret:
                    frame_count += 1

                    # Decode on full-res frame — accuracy matters here
                    if frame_count % decode_interval == 0:
                        decoded_data = self.decode_datamatrix(frame)
                        if decoded_data:
                            last_decoded = decoded_data
                            QtCore.QMetaObject.invokeMethod(
                                self.ui.lineEdit_accession, "setText",
                                QtCore.Qt.QueuedConnection,
                                QtCore.Q_ARG(str, last_decoded)
                            )

                    # Display pipeline — resize BGR first, then process small frame
                    disp_w = cam_id.width()
                    disp_h = cam_id.height()
                    if disp_w > 0 and disp_h > 0:
                        small = cv2.resize(frame, (disp_w, disp_h),
                                           interpolation=cv2.INTER_LINEAR)
                    else:
                        small = frame

                    small = cv2.flip(small, -1)
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

                    if last_decoded:
                        # Font size and position scaled to the display frame
                        cv2.putText(rgb, "Decoded: " + last_decoded, (8, 20),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                    (48, 56, 65), 1, cv2.LINE_AA)

                    if not rgb.flags['C_CONTIGUOUS']:
                        rgb = np.ascontiguousarray(rgb)

                    h, w, ch = rgb.shape
                    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                    self._barcode_frame_signal.emit(
                        QtGui.QPixmap.fromImage(qimg), cam_id
                    )

                elapsed = time.monotonic() - t_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            QtCore.QMetaObject.invokeMethod(
                cam_id, "setText",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, "Live view disabled.")
            )

        except Exception as e:
            print(f"Error in barcode webcam update: {e}")
            QtCore.QMetaObject.invokeMethod(
                cam_id, "setText",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, "Error in barcode camera.")
            )

    def decode_datamatrix(self, frame):
        """Attempt to decode a datamatrix barcode from a BGR frame.

        Strategy:
          1. Resize to a fixed decode width (faster, consistent scale for dmtx)
          2. Convert to grayscale and try dmtx.decode() directly — pylibdmtx
             has its own internal region finder, so complex OpenCV preprocessing
             often hurts more than it helps.
          3. If that fails, try again on an adaptively thresholded image — this
             helps with uneven or low-contrast lighting conditions.

        The old approach used a fixed threshold + contour filter with `break`
        statements that exited the loop on the first non-matching contour,
        silently skipping the actual datamatrix region in most frames.
        """
        try:
            # Resize to a consistent decode width — large frames slow dmtx down
            # considerably and small details aren't needed for barcode reading.
            decode_width = 640
            h, w = frame.shape[:2]
            if w != decode_width:
                scale = decode_width / w
                frame = cv2.resize(frame, (decode_width, int(h * scale)),
                                   interpolation=cv2.INTER_LINEAR)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Attempt 1: direct decode on grayscale
            results = dmtx.decode(gray, timeout=200)
            if results:
                return results[0].data.decode('utf-8')

            # Attempt 2: adaptive threshold — helps with uneven lighting
            thresh = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=21,
                C=10
            )
            results = dmtx.decode(thresh, timeout=200)
            if results:
                return results[0].data.decode('utf-8')

            return None

        except Exception as e:
            print(f"Error decoding datamatrix: {e}")
            return None

    # ── Label camera live view ─────────────────────────────────────────────────

    def begin_label_camera(self, slot):
        """Start or stop live view for the given slot."""
        try:
            if not slot.label_webcamView:
                if not slot.selected_camera:
                    self.log_info(f"Label camera {slot.slot_index + 1}: please select a camera first.")
                    return

                barcode_conflict = (
                    self.barcode_webcamView
                    and self.selected_barcodecam == slot.selected_camera
                )
                if barcode_conflict:
                    self.log_info("Selected camera is already in use by the barcode camera.")
                    return

                slot.start_btn.setText("Stop live view")
                slot.label_webcamView = True
                self.log_info(f"Started label camera {slot.slot_index + 1} live view.")
                self._refresh_camera_availability()

                if slot.label_camera_type == 'FLIR' and slot.flir_camera:
                    if not slot.flir_camera.start_acquisition():
                        self.log_info("Failed to start FLIR acquisition.")
                        slot.label_webcamView = False
                        slot.start_btn.setText("Start live view")
                        return

                worker = Worker(self.update_label_camera, slot)
                self.threadpool.start(worker)
            else:
                slot.start_btn.setText("Start live view")
                slot.label_webcamView = False
                self.log_info(f"Ended label camera {slot.slot_index + 1} live view.")
                self._refresh_camera_availability()
                if slot.label_camera_type == 'FLIR' and slot.flir_camera:
                    slot.flir_camera.stop_acquisition()

        except Exception as e:
            print(f"Error in begin_label_camera (slot {slot.slot_index}): {e}")
            self.log_info(f"Error with label camera {slot.slot_index + 1}: {e}")

    def update_label_camera(self, slot, progress_callback):
        """Worker: stream frames for a single LabelCameraSlot.

        Pipeline order (optimised for low-powered hardware):
          1. Grab full-res BGR frame (camera native)
          2. Store full-res BGR on slot.frame for HQ capture
          3. Resize BGR down to the display widget size  ← most of the saving
          4. Flip (webcam only) on the small frame
          5. cvtColor BGR→RGB on the small frame
          6. Build QImage directly at display size — no .scaled() needed
        Steps 4-6 operate on ~6-10× fewer pixels than the original pipeline.
        """
        import time
        webcam_frame_interval = 1.0 / 15

        try:
            while slot.label_webcamView:
                t_start = time.monotonic()
                frame = None

                if slot.label_camera_type == 'Webcam' and slot.cap:
                    ret, frame = slot.cap.read()
                    if not ret:
                        time.sleep(0.05)
                        continue
                elif slot.label_camera_type == 'FLIR' and slot.flir_camera:
                    frame = slot.flir_camera.get_frame()
                    if frame is None:
                        time.sleep(0.01)
                        continue

                if frame is not None:
                    slot.frame = frame   # store full-res BGR for HQ capture

                    disp_w = slot.live_view.width()
                    disp_h = slot.live_view.height()

                    if disp_w > 0 and disp_h > 0:
                        # Resize first — all subsequent ops work on display-sized pixels
                        small = cv2.resize(frame, (disp_w, disp_h),
                                           interpolation=cv2.INTER_LINEAR)
                    else:
                        small = frame

                    if slot.label_camera_type == 'Webcam':
                        small = cv2.flip(small, -1)

                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    # Ensure C-contiguous memory layout — required by QImage
                    if not rgb.flags['C_CONTIGUOUS']:
                        rgb = np.ascontiguousarray(rgb)

                    h, w, ch = rgb.shape
                    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                    # QPixmap.fromImage deep-copies so rgb can be safely overwritten next frame
                    self._label_frame_signal.emit(
                        QtGui.QPixmap.fromImage(qimg), slot.live_view
                    )

                # Webcam throttle — FLIR paces itself via hardware frame rate cap
                if slot.label_camera_type == 'Webcam':
                    elapsed = time.monotonic() - t_start
                    sleep_time = webcam_frame_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            QtCore.QMetaObject.invokeMethod(
                slot.live_view, "setText",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, "Live view disabled.")
            )

        except Exception as e:
            print(f"Error in label camera update (slot {slot.slot_index}): {e}")
            QtCore.QMetaObject.invokeMethod(
                slot.live_view, "setText",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, "Error in label camera.")
            )

        return slot.frame

    # ── Capture ────────────────────────────────────────────────────────────────

    def capture_set(self):
        try:
            self.output_location_folder = (
                Path(self.output_location)
                .joinpath(self.ui.lineEdit_taxon.text())
                .joinpath(self.ui.lineEdit_accession.text())
            )
            if os.path.exists(self.output_location_folder):
                self.show_popup()
            else:
                self._do_capture()
        except Exception as e:
            print(f"Error in capture_set: {e}")
            self.log_info(f"Error during capture: {e}")

    def show_popup(self):
        try:
            button = QMessageBox.question(
                self, "RAPIID lite Dialog",
                "A folder with this accession number already exists!\n"
                "Do you want to overwrite the existing file/s?"
            )
            if button == QMessageBox.Yes:
                self._do_capture()
        except Exception as e:
            print(f"Error showing popup: {e}")

    def _do_capture(self):
        """Capture sequentially from all label slots with progress feedback."""
        try:
            n = len(self.label_slots)
            self.ui.pushButton_capture.setEnabled(False)

            if n > 1:
                capture_dlg = ProgressDialog(
                    self,
                    title="Capturing images",
                    message=f"Saving image 1 of {n}…",
                    maximum=n,
                )
                capture_dlg.show()
                QApplication.processEvents()

            for i, slot in enumerate(self.label_slots):
                tag = f"_label_{slot.slot_index + 1}" if n > 1 else "_label"
                if n > 1:
                    capture_dlg.set_step(i + 1, f"Saving image {i + 1} of {n}…")
                self.capture_label_camera(slot, tag)

            if n > 1:
                capture_dlg.set_step(n, "Done!")
                # Brief pause so the user sees 100% before the dialog closes
                QtCore.QTimer.singleShot(600, capture_dlg.close)

            self.ui.pushButton_capture.setEnabled(True)
        except Exception as e:
            print(f"Error in _do_capture: {e}")
            self.log_info(f"Error during capture: {e}")
            self.ui.pushButton_capture.setEnabled(True)

    def capture_label_camera(self, slot, tag):
        try:
            self.create_output_folders()
            accession = self.ui.lineEdit_accession.text()
            taxon = self.ui.lineEdit_taxon.text()
            creator = self.ui.lineEdit_creator.text()
            institution = self.ui.lineEdit_institution.text()

            file_name = str(
                self.output_location_folder.joinpath(accession + tag + self.file_format)
            )

            frame_to_save = slot.get_frame_for_capture()
            if frame_to_save is None:
                self.log_info(f"Camera {slot.slot_index + 1}: no frame available!")
                self._flash_capture_feedback(success=False)
                return

            cv2.imwrite(file_name, frame_to_save)
            self.log_info(f"Camera {slot.slot_index + 1}: {os.path.basename(file_name)} saved.")
            self._flash_capture_feedback(success=True)

            device_info = slot.get_device_info()

            _, exif_msg = ExifManager.add_exif_to_image(
                file_name, creator, taxon, accession, device_info, institution
            )
            self.log_info(exif_msg)

            csv_data = ExifManager.get_csv_data(
                creator, taxon, accession, self.file_format, device_info,
                tag=tag, institution=institution
            )
            _, csv_msg = FileManager.create_or_update_csv(
                self.output_location, taxon, csv_data
            )
            self.log_info(csv_msg)

        except Exception as e:
            print(f"Error capturing from slot {slot.slot_index}: {e}")
            self.log_info(f"Camera {slot.slot_index + 1}: capture failed! {e}")
            self._flash_capture_feedback(success=False)

    def create_output_folders(self):
        try:
            created, msg = FileManager.create_folders(self.output_location_folder)
            if created:
                self.log_info(msg)
        except Exception as e:
            print(f"Error creating output folders: {e}")

    # ── File system & config ───────────────────────────────────────────────────

    def set_output_location(self):
        try:
            new_location = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Choose output folder...", str(Path.cwd())
            )
            if new_location:
                self.output_location = new_location
                self.log_info("Output location updated.")
            self.update_output_location()
        except Exception as e:
            print(f"Error setting output location: {e}")

    def update_output_location(self):
        try:
            self.ui.display_path.setText(self.output_location)
        except Exception as e:
            print(f"Error updating output location: {e}")

    def log_info(self, info):
        try:
            now = datetime.datetime.now()
            self.ui.listWidget_log.addItem(now.strftime("%H:%M:%S") + " " + info)
            self.ui.listWidget_log.sortItems(QtCore.Qt.DescendingOrder)
        except Exception as e:
            print(f"Error logging info: {e}")

    def loadConfig(self):
        try:
            if not YML_AVAILABLE:
                self.log_info("YAML library not available")
                return
            config_file = QtWidgets.QFileDialog.getOpenFileName(
                self, "Load config file...", str(Path.cwd()), "YAML files (*.yml *.yaml)"
            )[0]
            if config_file:
                self.config = ymlRW.read_config_file(config_file)
                self.ui.lineEdit_creator.setText(self.config["general"]["creator"])
                self.ui.lineEdit_institution.setText(self.config["general"].get("institution", ""))
                self.ui.lineEdit_taxon.setText(self.config["general"]["taxon_name"])
                self.loadedConfig = True
                self.log_info("Loaded config file successfully!")
        except Exception as e:
            print(f"Error loading config: {e}")
            self.log_info(f"Error loading config file: {e}")

    def writeConfig(self):
        try:
            if not YML_AVAILABLE:
                self.log_info("YAML library not available")
                return
            self.output_location_folder = Path(self.output_location).joinpath(
                self.ui.lineEdit_taxon.text()
            )
            if not os.path.exists(self.output_location_folder):
                os.makedirs(self.output_location_folder)
                self.log_info("Created folder: " + str(self.ui.lineEdit_taxon.text()))

            camera_settings = {}
            for i, slot in enumerate(self.label_slots):
                camera_settings[f'camera_{i}'] = {
                    'camera_type': slot.label_camera_type,
                    'selected_camera': slot.selected_camera,
                    'exposure_ms': slot.exposure_spinbox.value(),
                    'gain_level': slot.gain_spinbox.value(),
                    'gamma': slot.gamma_spinbox.value() / 100.0,
                }

            config = {
                'general': {
                    'creator': self.ui.lineEdit_creator.text(),
                    'institution': self.ui.lineEdit_institution.text(),
                    'taxon_name': self.ui.lineEdit_taxon.text(),
                    'output_folder': self.output_location,
                    'num_label_cameras': len(self.label_slots),
                },
                'camera_settings': camera_settings,
            }
            ymlRW.write_config_file(config, Path(self.output_location_folder))
            self.log_info("Exported config file successfully!")
        except Exception as e:
            print(f"Error writing config: {e}")
            self.log_info(f"Error saving config file: {e}")

    def get_default_values(self):
        return {
            'general': {
                'creator': '',
                'institution': '',
                'taxon_name': 'untitled_project',
            }
        }

    # ── App lifecycle ──────────────────────────────────────────────────────────

    def closeApp(self):
        sys.exit()

    def closeEvent(self, event):
        try:
            self.exit_program = True

            # Signal all live-view loops to stop
            for slot in self.label_slots:
                slot.label_webcamView = False
            self.barcode_webcamView = False

            # Wait for workers to exit cleanly before releasing hardware
            self.threadpool.waitForDone(3000)

            # Each slot's cleanup() releases its own webcam cap and FLIRCamera
            for slot in self.label_slots:
                slot.cleanup()

            # Release barcode camera
            if self.cap_barcode:
                self.cap_barcode.release()

            print("Application Closed!")
            event.accept()
        except Exception as e:
            print(f"Error during close: {e}")
            event.accept()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        # Set the Windows AppUserModelID before creating QApplication so the
        # taskbar and Start Menu use the app's own icon rather than Python's.
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ManaakiWhenua.RAPIIDlite.3"
            )

        app = QApplication(sys.argv)

        # Set the application icon early so the taskbar uses it from launch.
        # This must be set on the QApplication object, not just the window.
        if getattr(sys, 'frozen', False):
            _app_dir = Path(sys.executable).parent
        else:
            _app_dir = Path(__file__).parent
        _icon_path = _app_dir / "images" / "RAPIIDlite_icon.ico"
        if not _icon_path.exists():
            _icon_path = _app_dir / "images" / "RAPIIDlite_icon.png"
        if _icon_path.exists():
            app.setWindowIcon(QtGui.QIcon(str(_icon_path)))

        # Match the Tailwind font-sans stack used by the Chrysalis web app.
        # QFont resolves to the first family actually installed on the system:
        # Segoe UI on Windows, SF Pro on macOS (via system-ui), DejaVu/Ubuntu on Linux.
        app_font = QtGui.QFont()
        app_font.setFamilies(["Segoe UI", "system-ui", "ui-sans-serif", "sans-serif"])
        app_font.setPointSize(10)
        app.setFont(app_font)

        UIWindow = UI()
        if QT_MATERIAL_AVAILABLE:
            apply_stylesheet(app, theme='light_blue.xml')
        else:
            print("Using default Qt theme")
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Critical error starting application: {e}")
        traceback.print_exc()
        sys.exit(1)