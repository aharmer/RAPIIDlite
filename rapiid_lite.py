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

# FLIR camera imports - these should be wrapped in try/except in case FLIR SDK is not available
try:
    import PySpin
    FLIR_AVAILABLE = True
    print("FLIR PySpin library loaded successfully.")
except ImportError:
    FLIR_AVAILABLE = False
    print("FLIR PySpin library not available. FLIR camera functionality disabled.")


class WorkerSignals(QtCore.QObject):
    '''
    Defines the signals available from a running worker thread.
    '''
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(int)
    # Emits (pixmap, label_widget) so the main thread can safely update the UI
    frame_ready = QtCore.pyqtSignal(QtGui.QPixmap, QtWidgets.QLabel)


class Worker(QtCore.QRunnable):
    '''
    Worker thread
    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.kwargs['progress_callback'] = self.signals.progress

    @QtCore.pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
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


class FLIRCamera:
    """Class to handle FLIR camera operations"""
    
    def __init__(self):
        self.system = None
        self.cam_list = None
        self.camera = None
        self.is_initialized = False
        self.is_acquiring = False  # tracks BeginAcquisition/EndAcquisition state
        
    def initialize(self):
        """Initialize FLIR camera system"""
        if not FLIR_AVAILABLE:
            return False
            
        try:
            self.system = PySpin.System.GetInstance()
            self.cam_list = self.system.GetCameras()
            
            if self.cam_list.GetSize() == 0:
                print("No FLIR cameras detected")
                self.cleanup()
                return False
                
            self.camera = self.cam_list[0]
            self.camera.Init()

            # --- Latency optimisation: configure stream buffer BEFORE BeginAcquisition ---
            # NewestOnly tells Spinnaker to always overwrite old buffered frames rather
            # than queuing them. Without this, frames pile up and the live view shows
            # images that are many frames behind reality.
            try:
                self.camera.TLStream.StreamBufferHandlingMode.SetValue(
                    PySpin.StreamBufferHandlingMode_NewestOnly
                )
            except Exception:
                print("Warning: could not set StreamBufferHandlingMode (may not be supported)")

            # Keep the buffer size tiny — 2 is enough for double-buffering without lag.
            try:
                self.camera.TLStream.StreamBufferCountMode.SetValue(
                    PySpin.StreamBufferCountMode_Manual
                )
                self.camera.TLStream.StreamBufferCountManual.SetValue(2)
            except Exception:
                print("Warning: could not set StreamBufferCount (may not be supported)")

            self.is_initialized = True
            print("FLIR camera initialized successfully")
            return True
            
        except Exception as ex:
            print(f"Error initializing FLIR camera: {ex}")
            return False
    
    def configure_camera(self, exposure=None, gain=None, gamma=None,
                         set_acquisition_mode=True, live_fps=20):
        """Configure camera settings.
        
        set_acquisition_mode should only be True BEFORE BeginAcquisition() is called.
        live_fps caps the camera's hardware frame rate for the live view. Keeping this
        at or below your display rate (15-20fps) reduces USB/GigE bandwidth and prevents
        the buffer filling faster than frames are consumed.
        """
        if not self.is_initialized:
            return False
            
        try:
            # AcquisitionMode is read-only once acquisition has started.
            if set_acquisition_mode:
                if self.camera.AcquisitionMode.GetAccessMode() == PySpin.RW:
                    self.camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
                else:
                    print("AcquisitionMode not writable — camera may already be streaming")

            # Cap the camera's hardware frame rate to reduce buffer pressure.
            # Only set before acquisition starts; the node is read-only while streaming.
            if set_acquisition_mode and live_fps is not None:
                try:
                    if self.camera.AcquisitionFrameRateEnable.GetAccessMode() == PySpin.RW:
                        self.camera.AcquisitionFrameRateEnable.SetValue(True)
                        max_fps = self.camera.AcquisitionFrameRate.GetMax()
                        self.camera.AcquisitionFrameRate.SetValue(
                            min(float(live_fps), max_fps)
                        )
                except Exception:
                    print("Warning: hardware frame rate cap not available on this camera")
            
            # Configure exposure if provided
            if exposure is not None:
                self.camera.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
                min_exposure = self.camera.ExposureTime.GetMin()
                max_exposure = self.camera.ExposureTime.GetMax()
                self.camera.ExposureTime.SetValue(
                    max(min_exposure, min(float(exposure), max_exposure))
                )
            
            # Configure gain if provided
            if gain is not None:
                self.camera.GainAuto.SetValue(PySpin.GainAuto_Off)
                min_gain = self.camera.Gain.GetMin()
                max_gain = self.camera.Gain.GetMax()
                self.camera.Gain.SetValue(
                    max(min_gain, min(float(gain), max_gain))
                )
            
            # Configure gamma if provided
            if gamma is not None:
                try:
                    if self.camera.Gamma.GetAccessMode() == PySpin.RW:
                        self.camera.GammaEnable.SetValue(True)
                        min_gamma = self.camera.Gamma.GetMin()
                        max_gamma = self.camera.Gamma.GetMax()
                        self.camera.Gamma.SetValue(
                            max(min_gamma, min(float(gamma), max_gamma))
                        )
                except Exception:
                    print("Gamma control not available on this camera")
                
            return True
            
        except Exception as ex:
            print(f"Error configuring FLIR camera: {ex}")
            return False
    
    def start_acquisition(self):
        """Start image acquisition"""
        if not self.is_initialized:
            return False
            
        try:
            self.camera.BeginAcquisition()
            self.is_acquiring = True
            return True
        except Exception as ex:
            print(f"Error starting acquisition: {ex}")
            return False
    
    def stop_acquisition(self):
        """Stop image acquisition"""
        if not self.is_initialized:
            return
        
        self.is_acquiring = False  # signal get_frame() to stop before EndAcquisition
        try:
            self.camera.EndAcquisition()
        except Exception as ex:
            print(f"Error stopping acquisition: {ex}")
    
    def get_frame(self):
        """Get a frame from the camera"""
        if not self.is_initialized or not self.is_acquiring:
            return None
            
        image_result = None
        try:
            # Set timeout dynamically based on current exposure time.
            # Using a fixed short timeout causes -1011 errors whenever the exposure
            # is longer than that timeout. We add 100ms headroom above the exposure
            # duration, with a 200ms floor for cameras where exposure isn't readable.
            try:
                exposure_ms = self.camera.ExposureTime.GetValue() / 1000.0
                timeout_ms = max(200, int(exposure_ms) + 100)
            except Exception:
                timeout_ms = 200
            image_result = self.camera.GetNextImage(timeout_ms)
            
            if image_result.IsIncomplete():
                print(f"Incomplete image, status: {image_result.GetImageStatus()}")
                image_result.Release()
                return None
            
            # Use NEAREST_NEIGHBOR for live preview (much faster than HQ_LINEAR)
            image_converted = image_result.Convert(
                PySpin.PixelFormat_BGR8, PySpin.NEAREST_NEIGHBOR
            )
            image_data = image_converted.GetNDArray().copy()  # copy before Release
            
            image_result.Release()
            return image_data
            
        except PySpin.SpinnakerException as ex:
            # Suppress expected transient errors:
            # -1011: GetNextImage timeout (no frame in the wait window) — normal during
            #        startup, long exposures, or brief gaps between frames.
            # -1013: No image to release — occurs during stop/reconfigure/start cycle.
            # -1010: Stream not started — occurs during stop/reconfigure/start cycle.
            error_str = str(ex)
            if not any(code in error_str for code in ("-1011", "-1013", "-1010")):
                print(f"Error getting frame: {ex}")
            return None
        except Exception as ex:
            print(f"Unexpected error getting frame: {ex}")
            return None
    
    def get_frame_hq(self):
        """Grab a single high-quality frame for saving.

        Uses HQ_LINEAR debayering (vs NEAREST_NEIGHBOR in get_frame) for maximum
        image quality. Should only be called at capture time, not in the live loop.
        Temporarily pauses the live stream so the capture gets a clean, dedicated
        buffer slot, then resumes acquisition.
        """
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
                timeout_ms = max(200, int(exposure_ms) + 500)  # extra headroom for HQ
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
            # Always restore whichever acquisition state we started with
            self.stop_acquisition()
            if was_acquiring:
                self.camera.BeginAcquisition()
                self.is_acquiring = True

        return frame

    def cleanup(self):
        """Clean up camera resources"""
        try:
            if self.camera and self.is_initialized:
                self.is_acquiring = False
                try:
                    self.camera.EndAcquisition()
                except Exception:
                    pass
                self.camera.DeInit()

            # Null out the Python reference to the camera object BEFORE calling
            # cam_list.Clear(). Spinnaker raises -1004 ("something still holds a
            # reference") if any Python variable still points to the camera when
            # Clear() is called.
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


class ExifManager:
    """Manages EXIF metadata embedding in captured images."""

    @staticmethod
    def add_exif_to_image(image_path, creator, taxon, accession, device_info):
        """Embed EXIF metadata into a saved image. Requires PIL and piexif."""
        if not EXIF_AVAILABLE:
            return False, "EXIF embedding skipped (PIL/piexif not installed)"

        try:
            now = datetime.datetime.now()
            img = Image.open(image_path)
            img.close()

            exif_dict = {
                "0th": {
                    piexif.ImageIFD.Copyright: f"CC-BY 4.0 {now.year} Manaaki Whenua Landcare Research".encode(),
                    piexif.ImageIFD.Artist: creator.encode(),
                    piexif.ImageIFD.DateTime: now.strftime("%Y:%m:%d %H:%M:%S").encode(),
                    piexif.ImageIFD.Make: b"RAPIIDlite",
                    piexif.ImageIFD.Model: device_info.encode(),
                    piexif.ImageIFD.Software: b"RAPIIDlite v2.0",
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
    def get_csv_data(creator, taxon, accession, file_format, device_info=""):
        """Return a dict of capture metadata suitable for writing to CSV."""
        now = datetime.datetime.now()
        return {
            'image_filename': f"{accession}_label{file_format}",
            'accession_number': accession,
            'taxon_name': taxon,
            'image_format': file_format.replace('.', '').upper(),
            'copyright_type': f"CC-BY 4.0 {now.year}",
            'rights_owner': "Manaaki Whenua Landcare Research",
            'creator': creator,
            'date_captured': now.strftime("%Y-%m-%d %H:%M:%S"),
            'capture_device': device_info or "RAPIIDlite",
            'caption': f"{accession} - Specimen label",
            'title': f"{taxon} - {accession} - Specimen label",
        }


class FileManager:
    """Manages file and CSV operations."""

    CSV_HEADERS = [
        'image_filename', 'accession_number', 'taxon_name', 'image_format',
        'copyright_type', 'rights_owner', 'creator', 'date_captured',
        'capture_device', 'caption', 'title',
    ]

    @staticmethod
    def create_folders(output_path):
        """Create output folders if they don't exist. Returns (created, message)."""
        output_path = Path(output_path)
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
            return True, f"Created folder: {output_path}"
        return False, ""

    @staticmethod
    def create_or_update_csv(output_location, taxon, csv_data):
        """Append a row to the per-taxon CSV, creating it with headers if new."""
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


class UI(QMainWindow):
    # Signals used by worker threads to push frames to the main thread safely
    _label_frame_signal = QtCore.pyqtSignal(QtGui.QPixmap, QtWidgets.QLabel)
    _barcode_frame_signal = QtCore.pyqtSignal(QtGui.QPixmap, QtWidgets.QLabel)

    def __init__(self):
        super(UI, self).__init__()
        
        try:
            # Set window icon if available
            icon_path = Path.cwd().joinpath("images", "RAPIIDlite_icon.png")
            if icon_path.exists():
                self.setWindowIcon(QtGui.QIcon(str(icon_path)))

            self.exit_program = False
            self.ui = Ui_MainWindow()
            self.ui.setupUi(self)

            self.frame = None

            # start thread pool
            self.threadpool = QtCore.QThreadPool()
            print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

            # Set initial camera variables and buttons
            self.file_format = ".jpg"
            self.label_webcamView = False
            self.barcode_webcamView = False
            self.selected_labelcam = 'Webcam 0'
            self.selected_barcodecam = 'Webcam 1'
            
            # Camera type selection
            self.label_camera_type = 'Webcam'  # Default to webcam
            self.flir_camera = None
            self.cap_label = None
            self.cap_barcode = None
            
            # Initialize FLIR camera if available
            if FLIR_AVAILABLE:
                self.flir_camera = FLIRCamera()

            # Discover webcams once, before any persistent VideoCapture is opened.
            # Both dropdowns share this list. If discovery ran inside each setup
            # method separately, the second method would see webcam 0 as busy
            # (held open by the first) and only find one camera.
            discovered = self._discover_webcams()
            self.webcam_arr_label = discovered
            self.webcam_arr_barcode = discovered

            self.setup_ui_connections()
            self.setup_camera_selection()
            self.setup_barcode_camera_selection()
            self.setup_camera_controls()
            self.setup_file_system()
            self.setup_config_system()

            # Show the app
            self.showMaximized()
            
        except Exception as e:
            print(f"Error during UI initialization: {e}")
            traceback.print_exc()
            sys.exit(1)

    def setup_ui_connections(self):
        """Setup UI connections"""
        try:
            # Assign camera control features to ui
            self.ui.pushButton_capture.pressed.connect(self.capture_set)
            
            # Keyboard shortcut
            self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
            self.ui.shortcut_capture.activated.connect(self.capture_set)

            # Camera buttons
            self.ui.pushButton_label_webcam.pressed.connect(lambda: self.begin_label_camera(cam_id=self.ui.label_camera, button_id=self.ui.pushButton_label_webcam))
            self.ui.pushButton_barcode_webcam.pressed.connect(lambda: self.begin_barcode_webcam(cam_id=self.ui.barcode_camera, button_id=self.ui.pushButton_barcode_webcam))

            # Connect frame signals to the main-thread slot (thread-safe display updates)
            self._label_frame_signal.connect(self._display_frame)
            self._barcode_frame_signal.connect(self._display_frame)

        except Exception as e:
            print(f"Error setting up UI connections: {e}")

    @QtCore.pyqtSlot(QtGui.QPixmap, QtWidgets.QLabel)
    def _display_frame(self, pixmap, label):
        """Slot that safely updates a camera label from the main thread."""
        label.setPixmap(pixmap)
        label.setAlignment(QtCore.Qt.AlignCenter)

    def _discover_webcams(self):
        """Scan for available webcam indices before any are held open.
        
        Must be called before select_label_camera() or select_barcode_webcam()
        open their persistent VideoCapture handles, otherwise occupied indices
        return ret=False and break the loop prematurely.
        """
        webcams = []
        for index in range(10):
            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                cap.release()
                break
            ret, _ = cap.read()
            cap.release()
            if ret:
                webcams.append(f"Webcam {index}")
            else:
                break
        return webcams

    def setup_camera_selection(self):
        """Setup the camera selection dropdown for label camera"""
        try:
            self.ui.comboBox_selectLabelCam.clear()

            for name in self.webcam_arr_label:
                self.ui.comboBox_selectLabelCam.addItem(name)

            # Add FLIR option if available
            if FLIR_AVAILABLE and self.flir_camera:
                if self.flir_camera.initialize():
                    self.ui.comboBox_selectLabelCam.addItem("FLIR Camera")
                    self.flir_camera.cleanup()

            # Connect signal BEFORE setting index so the handler fires
            self.ui.comboBox_selectLabelCam.currentTextChanged.connect(self.select_label_camera)

            if self.ui.comboBox_selectLabelCam.count() > 0:
                self.ui.comboBox_selectLabelCam.setCurrentIndex(0)
                # Explicitly initialise cap_label — setCurrentIndex(0) on a previously
                # empty combo does not fire currentTextChanged.
                self.select_label_camera()

        except Exception as e:
            print(f"Error setting up camera selection: {e}")

    def setup_barcode_camera_selection(self):
        """Setup barcode camera selection"""
        try:
            for name in self.webcam_arr_barcode:
                self.ui.comboBox_selectBarcodeCam.addItem(name)

            # Connect signal BEFORE setting index
            self.ui.comboBox_selectBarcodeCam.currentTextChanged.connect(self.select_barcode_webcam)

            if len(self.webcam_arr_barcode) > 1:
                self.ui.comboBox_selectBarcodeCam.setCurrentIndex(1)
            elif len(self.webcam_arr_barcode) > 0:
                self.ui.comboBox_selectBarcodeCam.setCurrentIndex(0)

            # Explicitly initialise cap_barcode
            if self.ui.comboBox_selectBarcodeCam.count() > 0:
                self.select_barcode_webcam()

        except Exception as e:
            print(f"Error setting up barcode camera selection: {e}")

    def setup_camera_controls(self):
        """Initialize camera settings controls"""
        try:
            self.ui.flir_0_exposure_spinBox.setRange(1, 1000000)  # 1 to 1,000,000 microseconds
            self.ui.flir_0_exposure_spinBox.setValue(50000)  # Default 50ms
            self.ui.flir_0_gain_spinBox.setRange(0, 40)  # 0 to 40 dB
            self.ui.flir_0_gain_spinBox.setValue(0)  # Default 0 dB
            self.ui.flir_0_gamma_spinBox.setRange(1, 300)  # 0.01 to 3.0 (stored as int * 100)
            self.ui.flir_0_gamma_spinBox.setValue(100)  # Default 1.0

            # Debounce timer — applies camera settings 400ms after the user stops
            # adjusting a spinbox. Without this, holding an arrow key fires
            # stop_acquisition → configure → start_acquisition on every single step.
            self._settings_debounce_timer = QtCore.QTimer(self)
            self._settings_debounce_timer.setSingleShot(True)
            self._settings_debounce_timer.setInterval(400)
            self._settings_debounce_timer.timeout.connect(self.update_camera_settings)

            # Connect spinboxes to the debounce timer, not directly to update_camera_settings
            self.ui.flir_0_exposure_spinBox.valueChanged.connect(self._settings_debounce_timer.start)
            self.ui.flir_0_gain_spinBox.valueChanged.connect(self._settings_debounce_timer.start)
            self.ui.flir_0_gamma_spinBox.valueChanged.connect(self._settings_debounce_timer.start)
            
        except Exception as e:
            print(f"Error setting up camera controls: {e}")

    def setup_file_system(self):
        """Setup file system related functionality"""
        try:
            # Select output folder
            self.output_location = str(Path.home())
            self.update_output_location()
            self.ui.pushButton_outputFolder.pressed.connect(self.set_output_location)
            self.output_location_folder = Path(self.output_location)
            
        except Exception as e:
            print(f"Error setting up file system: {e}")

    def setup_config_system(self):
        """Setup configuration system"""
        try:
            # Config file
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

    def select_label_camera(self):
        """Handle label camera selection"""
        try:
            selected_camera = self.ui.comboBox_selectLabelCam.currentText()

            # stop the current camera if in use
            if self.label_webcamView:
                if self.cap_label:
                    self.cap_label.release()
                if self.flir_camera and self.flir_camera.is_initialized:
                    self.flir_camera.stop_acquisition()
                    self.flir_camera.cleanup()

            # Determine camera type and initialize
            if selected_camera.startswith("Webcam"):
                self.label_camera_type = 'Webcam'
                webcam_id = int(selected_camera.split(" ")[1])
                self.cap_label = cv2.VideoCapture(webcam_id)
                self.cap_label.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap_label.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.selected_labelcam = selected_camera
                
                # Hide camera controls for webcam
                self.ui.flir_0_exposure_spinBox.setEnabled(False)
                self.ui.flir_0_gain_spinBox.setEnabled(False)
                self.ui.flir_0_gamma_spinBox.setEnabled(False)
                
            elif selected_camera == "FLIR Camera" and FLIR_AVAILABLE:
                self.label_camera_type = 'FLIR'
                if self.flir_camera.initialize():
                    self.selected_labelcam = selected_camera
                    
                    # Enable camera controls for FLIR
                    self.ui.flir_0_exposure_spinBox.setEnabled(True)
                    self.ui.flir_0_gain_spinBox.setEnabled(True)
                    self.ui.flir_0_gamma_spinBox.setEnabled(True)
                    
                    # Configure with current settings
                    self.update_camera_settings()
                else:
                    self.log_info("Failed to initialize FLIR camera")
                    return

            self.log_info("Selected " + str(selected_camera))
            
        except Exception as e:
            print(f"Error selecting label camera: {e}")
            self.log_info(f"Error selecting camera: {e}")

    def select_barcode_webcam(self):
        """Handle barcode webcam selection"""
        try:
            selected_camera = self.ui.comboBox_selectBarcodeCam.currentText()

            # stop the webcam if currently in use
            if self.barcode_webcamView and self.cap_barcode:
                self.cap_barcode.release()

            # Select new webcam
            webcam_id = int(selected_camera.split(" ")[1])
            self.cap_barcode = cv2.VideoCapture(webcam_id)
            self.cap_barcode.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap_barcode.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.selected_barcodecam = selected_camera
            self.log_info("Selected " + str(selected_camera))
            
        except Exception as e:
            print(f"Error selecting barcode webcam: {e}")
            self.log_info(f"Error selecting barcode camera: {e}")

    def update_camera_settings(self):
        """Update FLIR camera settings.
        
        Exposure/gain/gamma can be changed while streaming on most FLIR cameras.
        We pass set_acquisition_mode=False so we don't attempt to write the
        AcquisitionMode node while BeginAcquisition is active (causes AccessException).
        """
        try:
            if self.label_camera_type == 'FLIR' and self.flir_camera and self.flir_camera.is_initialized:
                exposure = self.ui.flir_0_exposure_spinBox.value()
                gain = self.ui.flir_0_gain_spinBox.value()
                gamma = self.ui.flir_0_gamma_spinBox.value() / 100.0

                # If streaming, briefly stop acquisition to apply settings then restart
                was_streaming = self.label_webcamView
                if was_streaming:
                    self.flir_camera.stop_acquisition()

                self.flir_camera.configure_camera(
                    exposure=exposure, gain=gain, gamma=gamma,
                    set_acquisition_mode=False  # AcquisitionMode already set at init
                )

                if was_streaming:
                    self.flir_camera.start_acquisition()

        except Exception as e:
            print(f"Error updating camera settings: {e}")

    def set_output_location(self):
        try:
            new_location = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder...", str(Path.cwd()))
                    
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

    def decode_datamatrix(self, frame):
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (3,3), 0)
            _, threshold = cv2.threshold(blur, 50, 255, cv2.THRESH_BINARY_INV)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7,7))
            closing = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(closing, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                if cv2.contourArea(contour) > 1000:
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = float(w) / h

                    if 0.8 <= aspect_ratio <= 1.2:
                        roi = gray[y - 1:y + h + 1, x - 1:x + w + 1]

                        if roi is not None and roi.size > 0:
                            decoded_data = dmtx.decode(roi)
                            for data in decoded_data:
                                return data.data.decode('utf-8')
                        else:
                            break
                    else:
                        break
                else:
                    break

            return None
            
        except Exception as e:
            print(f"Error decoding datamatrix: {e}")
            return None

    def update_barcode_webcam(self, cam_id, progress_callback):
        try:
            import time
            target_fps = 15
            frame_interval = 1.0 / target_fps

            while self.barcode_webcamView and self.cap_barcode:
                t_start = time.monotonic()
                ret, frame = self.cap_barcode.read()

                if ret:
                    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = cv2.flip(img, -1)

                    decoded_data = self.decode_datamatrix(frame)
                    if decoded_data:
                        cv2.putText(img, "Decoded data: " + decoded_data, (30, 40),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (48, 56, 65), 2, cv2.LINE_AA)
                        # Use invokeMethod to safely update the line edit from the worker thread
                        QtCore.QMetaObject.invokeMethod(
                            self.ui.lineEdit_accession, "setText",
                            QtCore.Qt.QueuedConnection,
                            QtCore.Q_ARG(str, decoded_data)
                        )

                    h, w, ch = img.shape
                    live_img = QImage(img.data, w, h, ch * w, QImage.Format_RGB888)
                    live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                    live_img_scaled = live_img_pixmap.scaled(
                        cam_id.width(), cam_id.height(), QtCore.Qt.KeepAspectRatio
                    )
                    # Emit signal so the main thread updates the label (thread-safe)
                    self._barcode_frame_signal.emit(live_img_scaled, cam_id)

                # Throttle to target FPS
                elapsed = time.monotonic() - t_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # Signal the main thread to restore the placeholder text
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

    def update_label_camera(self, cam_id, progress_callback):
        """Update label camera feed - handles both webcam and FLIR"""
        import time
        # Webcam throttle — FLIR frame rate is capped at the hardware level so no
        # sleep is used there; sleeping would let frames accumulate in the buffer.
        webcam_target_fps = 15
        webcam_frame_interval = 1.0 / webcam_target_fps

        try:
            while self.label_webcamView:
                t_start = time.monotonic()
                frame = None

                if self.label_camera_type == 'Webcam' and self.cap_label:
                    ret, frame = self.cap_label.read()
                    if not ret:
                        time.sleep(0.05)
                        continue

                elif self.label_camera_type == 'FLIR' and self.flir_camera:
                    frame = self.flir_camera.get_frame()
                    if frame is None:
                        # get_frame() returns None on timeout or while not acquiring;
                        # brief sleep avoids a tight spin during transient gaps.
                        time.sleep(0.01)
                        continue

                if frame is not None:
                    self.frame = frame

                    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    if self.label_camera_type == 'Webcam':
                        img = cv2.flip(img, -1)

                    h, w, ch = img.shape
                    live_img = QImage(img.data, w, h, ch * w, QImage.Format_RGB888)
                    live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                    live_img_scaled = live_img_pixmap.scaled(
                        cam_id.width(), cam_id.height(), QtCore.Qt.KeepAspectRatio
                    )
                    self._label_frame_signal.emit(live_img_scaled, cam_id)

                # Only throttle for webcam — FLIR paces itself via its hardware frame rate
                if self.label_camera_type == 'Webcam':
                    elapsed = time.monotonic() - t_start
                    sleep_time = webcam_frame_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            QtCore.QMetaObject.invokeMethod(
                cam_id, "setText",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, "Live view disabled.")
            )

        except Exception as e:
            print(f"Error in label camera update: {e}")
            QtCore.QMetaObject.invokeMethod(
                cam_id, "setText",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, "Error in label camera.")
            )

        return self.frame
        
    def begin_label_camera(self, cam_id, button_id):
        """Start/stop label camera live view"""
        try:
            selected_camera = self.ui.comboBox_selectLabelCam.currentText()
            if not self.label_webcamView:
                # Only block if the barcode camera is actively streaming the same device.
                # Matching dropdown selections are fine as long as only one is live.
                barcode_conflict = (
                    self.barcode_webcamView
                    and self.selected_barcodecam == selected_camera
                )
                if not barcode_conflict:
                    self.log_info("Started label camera live view.")
                    button_id.setText("Stop Live View")
                    self.label_webcamView = True

                    # Start acquisition for FLIR camera
                    if self.label_camera_type == 'FLIR' and self.flir_camera:
                        if not self.flir_camera.start_acquisition():
                            self.log_info("Failed to start FLIR acquisition")
                            self.label_webcamView = False
                            button_id.setText("Start live view")
                            return

                    worker = Worker(self.update_label_camera, cam_id)
                    self.threadpool.start(worker)
                else:
                    self.log_info("Selected camera is already in use by the barcode camera.")
            else:
                button_id.setText("Start live view")
                self.log_info("Ended label camera live view")
                self.label_webcamView = False

                # Stop acquisition for FLIR camera
                if self.label_camera_type == 'FLIR' and self.flir_camera:
                    self.flir_camera.stop_acquisition()

        except Exception as e:
            print(f"Error in begin_label_camera: {e}")
            self.log_info(f"Error with label camera: {e}")

    def begin_barcode_webcam(self, cam_id, button_id):
        try:
            selected_camera = self.ui.comboBox_selectBarcodeCam.currentText()
            if not self.barcode_webcamView:
                # Only block if the label camera is actively streaming the same device.
                label_conflict = (
                    self.label_webcamView
                    and self.selected_labelcam == selected_camera
                )
                if not label_conflict:
                    self.log_info("Started barcode camera live view.")
                    button_id.setText("Stop Live View")
                    self.barcode_webcamView = True

                    worker = Worker(self.update_barcode_webcam, cam_id)
                    self.threadpool.start(worker)
                else:
                    self.log_info("Selected camera is already in use by the label camera.")
            else:
                button_id.setText("Start live view")
                self.log_info("Ended barcode camera live view")
                self.barcode_webcamView = False

        except Exception as e:
            print(f"Error in begin_barcode_webcam: {e}")
            self.log_info(f"Error with barcode camera: {e}")

    def capture_set(self):
        try:
            self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text()).joinpath(self.ui.lineEdit_accession.text())
            if os.path.exists(self.output_location_folder):
                self.show_popup()
            else:
                self.ui.pushButton_capture.setEnabled(False)
                self.capture_label_camera(tag="_label")
                self.ui.pushButton_capture.setEnabled(True)
                
        except Exception as e:
            print(f"Error in capture_set: {e}")
            self.log_info(f"Error during capture: {e}")

    def show_popup(self):
        try:
            button = QMessageBox.question(self, "RAPIID lite Dialog", "A folder with this accession number already exists!\nDo you want to overwrite the existing file/s?")
            if button == QMessageBox.Yes:
                self.popup_button()
        except Exception as e:
            print(f"Error showing popup: {e}")

    def popup_button(self):
        try:
            self.ui.pushButton_capture.setEnabled(False)
            self.capture_label_camera(tag="_label")
            self.ui.pushButton_capture.setEnabled(True)
        except Exception as e:
            print(f"Error in popup_button: {e}")

    def capture_label_camera(self, tag):
        try:
            self.create_output_folders()
            accession = self.ui.lineEdit_accession.text()
            taxon = self.ui.lineEdit_taxon.text()
            creator = self.ui.lineEdit_creator.text()

            file_name = str(self.output_location_folder.joinpath(accession + tag + self.file_format))

            # For FLIR, grab a dedicated HQ frame (HQ_LINEAR debayering) rather than
            # saving the NEAREST_NEIGHBOR preview frame cached in self.frame.
            if self.label_camera_type == 'FLIR' and self.flir_camera and self.flir_camera.is_initialized:
                frame_to_save = self.flir_camera.get_frame_hq()
                if frame_to_save is None:
                    self.log_info("Failed to capture HQ frame from FLIR camera!")
                    return
            else:
                frame_to_save = self.frame
                if frame_to_save is None:
                    self.log_info("No frame available to save!")
                    return

            cv2.imwrite(file_name, frame_to_save)
            self.log_info(f"File {file_name} saved successfully.")

            # Build a short device description for metadata
            device_info = self._get_device_info()

            # Embed EXIF metadata (silently skipped if PIL/piexif not installed)
            _, exif_msg = ExifManager.add_exif_to_image(
                file_name, creator, taxon, accession, device_info
            )
            self.log_info(exif_msg)

            # Append a row to the per-taxon CSV log
            csv_data = ExifManager.get_csv_data(
                creator, taxon, accession, self.file_format, device_info
            )
            _, csv_msg = FileManager.create_or_update_csv(
                self.output_location, taxon, csv_data
            )
            self.log_info(csv_msg)

        except Exception as e:
            print(f"Error capturing image: {e}")
            self.log_info(f"File was unable to be saved! Error: {e}")

    def _get_device_info(self):
        """Return a short description of the active label camera for metadata."""
        try:
            if self.label_camera_type == 'FLIR' and self.flir_camera and self.flir_camera.is_initialized:
                cam = self.flir_camera.camera
                try:
                    model = cam.DeviceModelName.GetValue()
                    serial = cam.DeviceSerialNumber.GetValue()
                    return f"FLIR {model} (S/N: {serial})"
                except Exception:
                    return "FLIR Camera"
            elif self.cap_label and self.cap_label.isOpened():
                w = int(self.cap_label.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self.cap_label.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = self.cap_label.get(cv2.CAP_PROP_FPS)
                return f"{self.selected_labelcam} - {w}x{h} @ {fps:.0f}fps"
        except Exception:
            pass
        return "RAPIIDlite"

    def create_output_folders(self):
        try:
            self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text()).joinpath(self.ui.lineEdit_accession.text())
            if not os.path.exists(self.output_location_folder):
                os.makedirs(self.output_location_folder)
                self.log_info("Created folder: " + str(self.ui.lineEdit_taxon.text() + "/" + self.ui.lineEdit_accession.text()))
        except Exception as e:
            print(f"Error creating output folders: {e}")

    def loadConfig(self):
        try:
            if not YML_AVAILABLE:
                self.log_info("YAML library not available")
                return
                
            file = QtWidgets.QFileDialog.getOpenFileName(self, "Load existing config file", str(Path.cwd()), "config file (*.yaml)")
            config_location = file[0]
            if config_location:
                config_location = Path(config_location)
                config = ymlRW.read_config_file(config_location)

                # output path
                if "general" in config and "output_folder" in config["general"]:
                    self.output_location = config["general"]["output_folder"]
                    self.ui.display_path.setText(self.output_location)

                # creator
                if "general" in config and "creator" in config["general"]:
                    self.ui.lineEdit_creator.setText(config["general"]["creator"])
                    
                # taxon name
                if "general" in config and "taxon_name" in config["general"]:
                    self.ui.lineEdit_taxon.setText(config["general"]["taxon_name"])

                # camera_settings for FLIR:
                if "camera_settings" in config and "camera_0" in config["camera_settings"]:
                    camera_settings = config["camera_settings"]["camera_0"]
                    if "exposure_time" in camera_settings:
                        self.ui.flir_0_exposure_spinBox.setValue(camera_settings["exposure_time"])
                    if "gain_level" in camera_settings:
                        self.ui.flir_0_gain_spinBox.setValue(int(camera_settings["gain_level"]))
                    if "gamma" in camera_settings:
                        self.ui.flir_0_gamma_spinBox.setValue(int(camera_settings["gamma"] * 100))

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
                
            self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text())
            if not os.path.exists(self.output_location_folder):
                os.makedirs(self.output_location_folder)
                self.log_info("Created folder: " + str(self.ui.lineEdit_taxon.text()))

            config = {
                'general': {
                    'creator': self.ui.lineEdit_creator.text(),
                    'taxon_name': self.ui.lineEdit_taxon.text(),
                    'output_folder': self.output_location,
                    'camera_type': self.label_camera_type,
                },
                'camera_settings': {
                    'camera_0': {
                        'exposure_time': self.ui.flir_0_exposure_spinBox.value(),
                        'gain_level': self.ui.flir_0_gain_spinBox.value(),
                        'gamma': self.ui.flir_0_gamma_spinBox.value() / 100.0,
                    }    
                }
            }

            ymlRW.write_config_file(config, Path(self.output_location_folder))
            self.log_info("Exported config file successfully!")
            
        except Exception as e:
            print(f"Error writing config: {e}")
            self.log_info(f"Error saving config file: {e}")

    def get_default_values(self):
        config = {
            'general': {
                'creator': '',
                'taxon_name': 'untitled_project'
            }
        }
        return config

    def closeApp(self):
        sys.exit()

    def closeEvent(self, event):
        try:
            self.exit_program = True

            # Signal both live-view loops to stop
            self.label_webcamView = False
            self.barcode_webcamView = False

            # Wait up to 3 seconds for worker threads to finish their current
            # iteration and exit cleanly. Without this, the FLIR cleanup below
            # can fire while a thread is still inside get_frame(), causing a
            # crash or Spinnaker reference errors.
            self.threadpool.waitForDone(3000)

            # Now it is safe to release camera resources
            if self.cap_label:
                self.cap_label.release()
            if self.flir_camera and self.flir_camera.is_initialized:
                self.flir_camera.stop_acquisition()
                self.flir_camera.cleanup()

            if self.cap_barcode:
                self.cap_barcode.release()

            print("Application Closed!")
            event.accept()
            
        except Exception as e:
            print(f"Error during close: {e}")
            event.accept()


# Initialise the app
if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        UIWindow = UI()
        
        if QT_MATERIAL_AVAILABLE:
            apply_stylesheet(app, theme='dark_lightgreen.xml')
        else:
            print("Using default Qt theme")
            
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f"Critical error starting application: {e}")
        traceback.print_exc()
        sys.exit(1)

# import sys
# import os
# from pathlib import Path
# import datetime
# import csv
# import traceback
# from PyQt5 import QtWidgets, QtGui, QtCore
# from PyQt5.QtGui import *
# from PyQt5.QtWidgets import *
# from PyQt5.QtCore import *
# from GUI.rapiidlite_GUI import Ui_MainWindow
# import scripts.ymlRW as ymlRW
# import cv2
# import pylibdmtx.pylibdmtx as dmtx
# from qt_material import apply_stylesheet
# from PIL import Image
# from PIL.ExifTags import TAGS
# import piexif
# import socket


# class WorkerSignals(QtCore.QObject):
#     finished = QtCore.pyqtSignal()
#     error = QtCore.pyqtSignal(tuple)
#     result = QtCore.pyqtSignal(object)
#     progress = QtCore.pyqtSignal(int)


# class Worker(QtCore.QRunnable):
#     def __init__(self, fn, *args, **kwargs):
#         super(Worker, self).__init__()
#         self.fn = fn
#         self.args = args
#         self.kwargs = kwargs
#         self.signals = WorkerSignals()
#         self.kwargs['progress_callback'] = self.signals.progress

#     @QtCore.pyqtSlot()
#     def run(self):
#         try:
#             result = self.fn(*self.args, **self.kwargs)
#         except:
#             traceback.print_exc()
#             exctype, value = sys.exc_info()[:2]
#             self.signals.error.emit((exctype, value, traceback.format_exc()))
#         else:
#             self.signals.result.emit(result)
#         finally:
#             self.signals.finished.emit()


# class CameraManager:
#     """Manages camera operations and reduces duplication between label and barcode cameras"""
    
#     def __init__(self, camera_type, ui_components):
#         self.camera_type = camera_type  # 'label' or 'barcode'
#         self.ui_components = ui_components
#         self.cap = None
#         self.webcam_view = False
#         self.selected_camera = f'Webcam {0 if camera_type == "label" else 1}'
#         self.frame = None
#         self.webcam_list = []
        
#     def discover_cameras(self):
#         """Discover available cameras"""
#         self.webcam_list = []
#         index = 0
#         while True:
#             cap = cv2.VideoCapture(index)
#             try:
#                 if cap.getBackendName() == "MSMF":
#                     self.webcam_list.append(f"Webcam {index}")
#             except:
#                 break
#             cap.release()
#             index += 1
#         return self.webcam_list
    
#     def setup_camera(self, camera_id):
#         """Setup camera with standard settings"""
#         if self.cap:
#             self.cap.release()
        
#         self.cap = cv2.VideoCapture(camera_id)
#         self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
#         self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
#     def select_camera(self, camera_name):
#         """Select and setup a camera"""
#         if self.webcam_view:
#             self.cap.release()
        
#         camera_id = int(camera_name.split(" ")[1])
#         self.setup_camera(camera_id)
#         self.selected_camera = camera_name
#         return f"Selected {camera_name}"
    
#     def update_webcam_feed(self, cam_id, progress_callback):
#         """Generic webcam feed update method"""
#         while self.webcam_view:
#             ret, frame = self.cap.read()
#             if ret:
#                 self.frame = frame
#                 img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#                 img = cv2.flip(img, -1)
                
#                 # Apply camera-specific processing
#                 if self.camera_type == 'barcode':
#                     img = self._process_barcode_frame(frame, img)
                
#                 # Convert and display
#                 live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
#                 live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
#                 live_img_scaled = live_img_pixmap.scaled(
#                     cam_id.width(), cam_id.height(), QtCore.Qt.KeepAspectRatio
#                 )
#                 cam_id.setPixmap(live_img_scaled)
#                 cam_id.setAlignment(QtCore.Qt.AlignCenter)
        
#         cam_id.setText("Live view disabled.")
#         return self.frame
    
#     def _process_barcode_frame(self, original_frame, display_frame):
#         """Process frame for barcode detection"""
#         decoded_data = self._decode_datamatrix(original_frame)
#         if decoded_data:
#             cv2.putText(display_frame, f"Decoded data: {decoded_data}", 
#                        (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (48, 56, 65), 2, cv2.LINE_AA)
#             self.ui_components['accession_field'].setText(decoded_data)
#         return display_frame
    
#     def _decode_datamatrix(self, frame):
#         """Decode datamatrix from frame"""
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         blur = cv2.GaussianBlur(gray, (3,3), 0)
#         _, threshold = cv2.threshold(blur, 50, 255, cv2.THRESH_BINARY_INV)
#         kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7,7))
#         closing = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel)
#         contours, _ = cv2.findContours(closing, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

#         for contour in contours:
#             if cv2.contourArea(contour) > 1000:
#                 x, y, w, h = cv2.boundingRect(contour)
#                 aspect_ratio = float(w) / h
                
#                 if 0.8 <= aspect_ratio <= 1.2:
#                     roi = gray[y - 1:y + h + 1, x - 1:x + w + 1]
#                     if roi is not None and roi.size > 0:
#                         decoded_data = dmtx.decode(roi)
#                         for data in decoded_data:
#                             return data.data.decode('utf-8')
#         return None
    
#     def toggle_webcam_view(self, cam_id, button_id, other_camera_manager):
#         """Toggle webcam view on/off"""
#         if not self.webcam_view:
#             if other_camera_manager.selected_camera != self.selected_camera:
#                 self.webcam_view = True
#                 button_id.setText("Stop Live View")
#                 return True, f"Began {self.camera_type} camera live view."
#             else:
#                 return False, "Selected camera is already in use."
#         else:
#             self.webcam_view = False
#             button_id.setText("Start live view")
#             return True, f"Ended {self.camera_type} camera live view."
    
#     def get_device_info(self):
#         """Get camera device information"""
#         try:
#             width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
#             height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
#             fps = self.cap.get(cv2.CAP_PROP_FPS)
#             backend = self.cap.getBackendName()
#             return f"{self.selected_camera} ({backend}) - {width}x{height} @ {fps}fps"
#         except:
#             return f"{self.selected_camera} - Camera"


# class ExifManager:
#     """Manages EXIF data operations"""
    
#     @staticmethod
#     def create_exif_data(image_path, creator, taxon, accession, device_info):
#         """Create EXIF data dictionary"""
#         now = datetime.datetime.now()
        
#         # Get image dimensions
#         img = Image.open(image_path)
#         width, height = img.size
#         img.close()
        
#         exif_dict = {
#             "0th": {},
#             "Exif": {},
#             "GPS": {},
#             "1st": {},
#             "thumbnail": None
#         }
        
#         # Basic image info
#         exif_dict["0th"][piexif.ImageIFD.Copyright] = f"CC-BY 4.0 {now.year} Manaaki Whenua Landcare Research"
#         exif_dict["0th"][piexif.ImageIFD.Artist] = creator  # Fixed: Changed from Author to Artist
#         exif_dict["0th"][piexif.ImageIFD.DateTime] = now.strftime("%Y:%m:%d %H:%M:%S")
#         exif_dict["0th"][piexif.ImageIFD.Make] = "RAPIIDlite"
#         exif_dict["0th"][piexif.ImageIFD.Model] = device_info
#         exif_dict["0th"][piexif.ImageIFD.Software] = "RAPIIDlite v2.0"
#         exif_dict["0th"][piexif.ImageIFD.ImageDescription] = f"Specimen: {taxon} - {accession} - LABEL"
        
#         # EXIF specific data
#         exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = now.strftime("%Y:%m:%d %H:%M:%S")
#         exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = now.strftime("%Y:%m:%d %H:%M:%S")
#         exif_dict["Exif"][piexif.ExifIFD.UserComment] = f"Taxon: {taxon}, Accession: {accession}".encode('utf-8')
        
#         return exif_dict
    
#     @staticmethod
#     def add_exif_to_image(image_path, creator, taxon, accession, device_info):
#         """Add EXIF data to an image"""
#         try:
#             exif_dict = ExifManager.create_exif_data(image_path, creator, taxon, accession, device_info)
#             exif_bytes = piexif.dump(exif_dict)
            
#             img = Image.open(image_path)
#             img.save(image_path, exif=exif_bytes)
#             img.close()
            
#             return True, f"EXIF data added to {os.path.basename(image_path)}"
#         except Exception as e:
#             return False, f"Failed to add EXIF data: {str(e)}"
    
#     @staticmethod
#     def get_csv_data(creator, taxon, accession, file_format):
#         """Get EXIF data as a dictionary for CSV logging"""
#         now = datetime.datetime.now()
        
#         return {
#             'copyright_type': f"CC-BY 4.0 {now.year}",
#             'rights_owner': f"Manaaki Whenua Landcare Research",
#             'creator': creator,  # Fixed: Use parameter instead of self.ui
#             'date_captured': now.strftime("%Y-%m-%d %H:%M:%S"),
#             'capture_device': f"RAPIIDlite",
#             'caption': f"{accession} - Specimen label",  # Fixed: Use parameter
#             'image_format': file_format.replace('.', '').upper(),
#             'taxon_name': taxon,  # Fixed: Use parameter
#             'accession_number': accession,  # Fixed: Use parameter
#             'image_filename': f"{accession}_label{file_format}",  # Fixed: Use parameter
#             'title': f"{taxon} - {accession} - Specimen label"  # Fixed: Use parameter
#         }


# class FileManager:
#     """Manages file operations"""
    
#     CSV_HEADERS = [
#         'image_filename', 'accession_number', 'taxon_name', 'image_format',
#         'copyright_type', 'rights_owner', 'creator', 'date_captured',
#         'capture_device', 'caption', 'title'
#     ]
    
#     @staticmethod
#     def create_folders(output_path):
#         """Create output folders if they don't exist"""
#         if not os.path.exists(output_path):
#             os.makedirs(output_path)
#             return True, f"Created folder: {output_path}"
#         return False, ""
    
#     @staticmethod
#     def create_or_update_csv(output_location, taxon, csv_data):
#         """Create or update CSV file with image capture data"""
#         taxon_folder = Path(output_location).joinpath(taxon)
#         csv_file_path = taxon_folder.joinpath(f"{taxon}_captures.csv")
        
#         file_exists = csv_file_path.exists()
        
#         try:
#             taxon_folder.mkdir(parents=True, exist_ok=True)
            
#             with open(csv_file_path, 'a', newline='', encoding='utf-8') as csvfile:
#                 writer = csv.DictWriter(csvfile, fieldnames=FileManager.CSV_HEADERS)
                
#                 if not file_exists:
#                     writer.writeheader()
                
#                 writer.writerow(csv_data)
                
#             return True, f"Added capture data to CSV: {csv_file_path.name}"
#         except Exception as e:
#             return False, f"Failed to write to CSV: {str(e)}"


# class UI(QMainWindow):
#     def __init__(self):
#         super(UI, self).__init__()
        
#         self.setWindowIcon(QtGui.QIcon(str(Path.cwd().joinpath("images", "RAPIIDlite_icon.png"))))
#         self.exit_program = False
#         self.ui = Ui_MainWindow()
#         self.ui.setupUi(self)
        
#         # Initialize thread pool
#         self.threadpool = QtCore.QThreadPool()
#         print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")
        
#         # Initialize camera managers
#         self.label_camera = CameraManager('label', {
#             'accession_field': self.ui.lineEdit_accession
#         })
#         self.barcode_camera = CameraManager('barcode', {
#             'accession_field': self.ui.lineEdit_accession
#         })
        
#         # Set initial variables
#         self.file_format = ".jpg"
#         self.output_location = str(Path.home())
        
#         self._setup_ui_connections()
#         self._setup_cameras()
#         self._setup_config()
        
#         self.showMaximized()
    
#     def _setup_ui_connections(self):
#         """Setup UI connections"""
#         # Capture controls
#         self.ui.pushButton_capture.pressed.connect(self.capture_set)
#         self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
#         self.ui.shortcut_capture.activated.connect(self.capture_set)
        
#         # Camera controls
#         self.ui.pushButton_label_webcam.pressed.connect(
#             lambda: self._toggle_camera_view(self.label_camera, self.ui.label_camera, self.ui.pushButton_label_webcam)
#         )
#         self.ui.pushButton_barcode_webcam.pressed.connect(
#             lambda: self._toggle_camera_view(self.barcode_camera, self.ui.barcode_camera, self.ui.pushButton_barcode_webcam)
#         )
        
#         # Camera selection
#         self.ui.comboBox_selectLabelWebcam.currentTextChanged.connect(
#             lambda: self._select_camera(self.label_camera, self.ui.comboBox_selectLabelWebcam.currentText())
#         )
#         self.ui.comboBox_selectBarcodeWebcam.currentTextChanged.connect(
#             lambda: self._select_camera(self.barcode_camera, self.ui.comboBox_selectBarcodeWebcam.currentText())
#         )
        
#         # File operations
#         self.ui.pushButton_outputFolder.pressed.connect(self.set_output_location)
#         self.ui.pushButton_load_config.pressed.connect(self.loadConfig)
#         self.ui.pushButton_writeConfig.pressed.connect(self.writeConfig)
    
#     def _setup_cameras(self):
#         """Setup camera discovery and selection"""
#         # Setup label camera
#         label_cameras = self.label_camera.discover_cameras()
#         for camera in label_cameras:
#             self.ui.comboBox_selectLabelWebcam.addItem(camera)
#         if label_cameras:
#             self.ui.comboBox_selectLabelWebcam.setCurrentIndex(0)
        
#         # Setup barcode camera
#         barcode_cameras = self.barcode_camera.discover_cameras()
#         for camera in barcode_cameras:
#             self.ui.comboBox_selectBarcodeWebcam.addItem(camera)
#         if barcode_cameras and len(barcode_cameras) > 1:
#             self.ui.comboBox_selectBarcodeWebcam.setCurrentIndex(1)
        
#         # Initialize camera selections
#         self._select_camera(self.label_camera, self.ui.comboBox_selectLabelWebcam.currentText())
#         self._select_camera(self.barcode_camera, self.ui.comboBox_selectBarcodeWebcam.currentText())
    
#     def _setup_config(self):
#         """Setup configuration"""
#         self.config = self.get_default_values()
#         self.ui.lineEdit_taxon.setText(self.config["general"]["taxon_name"])
#         self.ui.lineEdit_creator.setText(self.config["general"]["creator"])
#         self.loadedConfig = False
#         self.update_output_location()
    
#     def _select_camera(self, camera_manager, camera_name):
#         """Select camera for a camera manager"""
#         if camera_name:
#             message = camera_manager.select_camera(camera_name)
#             self.log_info(message)
    
#     def _toggle_camera_view(self, camera_manager, cam_id, button_id):
#         """Toggle camera view for a camera manager"""
#         other_camera = self.barcode_camera if camera_manager == self.label_camera else self.label_camera
#         success, message = camera_manager.toggle_webcam_view(cam_id, button_id, other_camera)
        
#         if success and camera_manager.webcam_view:
#             worker = Worker(camera_manager.update_webcam_feed, cam_id)
#             self.threadpool.start(worker)
        
#         self.log_info(message)
    
#     def set_output_location(self):
#         """Set output location"""
#         new_location = QtWidgets.QFileDialog.getExistingDirectory(
#             self, "Choose output folder...", str(Path.cwd())
#         )
        
#         if new_location:
#             self.output_location = new_location
#             self.log_info("Output location updated.")
        
#         self.update_output_location()
    
#     def update_output_location(self):
#         """Update output location display"""
#         self.ui.display_path.setText(self.output_location)
    
#     def log_info(self, info):
#         """Log information to the UI"""
#         now = datetime.datetime.now()
#         self.ui.listWidget_log.addItem(f"{now.strftime('%H:%M:%S')} {info}")
#         self.ui.listWidget_log.sortItems(QtCore.Qt.DescendingOrder)
    
#     def capture_set(self):
#         """Handle capture operation"""
#         output_folder = Path(self.output_location).joinpath(
#             self.ui.lineEdit_taxon.text(),
#             self.ui.lineEdit_accession.text()
#         )
        
#         if output_folder.exists():
#             self.show_popup()
#         else:
#             self._perform_capture()
    
#     def show_popup(self):
#         """Show overwrite confirmation popup"""
#         button = QMessageBox.question(
#             self, "RAPIID lite Dialog",
#             "A folder with this accession number already exists!\nDo you want to overwrite the existing file/s?"
#         )
#         if button == QMessageBox.Yes:
#             self._perform_capture()
    
#     def _perform_capture(self):
#         """Perform the actual capture operation"""
#         self.ui.pushButton_capture.setEnabled(False)
#         self.capture_label_webcam("_label")
#         self.ui.pushButton_capture.setEnabled(True)
    
#     def capture_label_webcam(self, tag):
#         """Capture image from label webcam"""
#         # Create output folders
#         output_folder = Path(self.output_location).joinpath(
#             self.ui.lineEdit_taxon.text(),
#             self.ui.lineEdit_accession.text()
#         )
        
#         created, folder_msg = FileManager.create_folders(output_folder)
#         if created:
#             self.log_info(folder_msg)
        
#         # Save image
#         file_name = str(output_folder.joinpath(f"{self.ui.lineEdit_accession.text()}{tag}{self.file_format}"))
#         frame_to_save = self.label_camera.frame
        
#         try:
#             cv2.imwrite(file_name, frame_to_save)
#             self.log_info(f"File {file_name} saved successfully.")
            
#             # Get current values from UI
#             creator = self.ui.lineEdit_creator.text()
#             taxon = self.ui.lineEdit_taxon.text()
#             accession = self.ui.lineEdit_accession.text()
#             device_info = self.label_camera.get_device_info()
            
#             # Add EXIF data
#             success, exif_msg = ExifManager.add_exif_to_image(
#                 file_name,
#                 creator,
#                 taxon,
#                 accession,
#                 device_info
#             )
#             self.log_info(exif_msg)
            
#             # Create CSV data - Fixed: Pass all required parameters
#             csv_data = ExifManager.get_csv_data(
#                 creator,
#                 taxon,
#                 accession,
#                 self.file_format
#             )
            
#             # Update CSV
#             success, csv_msg = FileManager.create_or_update_csv(
#                 self.output_location,
#                 taxon,
#                 csv_data
#             )
#             self.log_info(csv_msg)
            
#         except Exception as e:
#             self.log_info(f"File {file_name} was unable to be saved! Error: {str(e)}")
    
#     def loadConfig(self):
#         """Load configuration from file"""
#         file = QtWidgets.QFileDialog.getOpenFileName(
#             self, "Load existing config file", str(Path.cwd()), "config file (*.yaml)"
#         )
#         config_location = file[0]
        
#         if config_location:
#             config_location = Path(config_location)
#             config = ymlRW.read_config_file(config_location)
            
#             # Apply configuration
#             self.output_location = config["general"]["output_folder"]
#             self.ui.display_path.setText(self.output_location)
#             self.ui.lineEdit_creator.setText(config["general"]["creator"])
#             self.ui.lineEdit_taxon.setText(config["general"]["taxon_name"])
            
#             self.loadedConfig = True
#             self.log_info("Loaded config file successfully!")
    
#     def writeConfig(self):
#         """Write configuration to file"""
#         output_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text())
        
#         created, folder_msg = FileManager.create_folders(output_folder)
#         if created:
#             self.log_info(folder_msg)
        
#         config = {
#             'general': {
#                 'creator': self.ui.lineEdit_creator.text(),
#                 'taxon_name': self.ui.lineEdit_taxon.text(),
#                 'output_folder': self.output_location,
#             }
#         }
        
#         ymlRW.write_config_file(config, output_folder)
#         self.log_info("Exported config file successfully!")
    
#     def get_default_values(self):
#         """Get default configuration values"""
#         return {
#             'general': {
#                 'creator': 'new_user',
#                 'taxon_name': 'untitled_taxon',
#             }
#         }
    
#     def closeApp(self):
#         """Close the application"""
#         sys.exit()
    
#     def closeEvent(self, event):
#         """Handle application close event"""
#         self.exit_program = True
#         print("Application Closed!")


# # Initialize the app
# app = QApplication(sys.argv)
# UIWindow = UI()
# apply_stylesheet(app, theme='dark_lightgreen.xml')
# app.exec_()