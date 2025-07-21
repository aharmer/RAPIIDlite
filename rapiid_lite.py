import sys
import os
from pathlib import Path
import datetime
import csv
import traceback
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from GUI.rapiidlite_GUI import Ui_MainWindow
import scripts.ymlRW as ymlRW
import cv2
import pylibdmtx.pylibdmtx as dmtx
from qt_material import apply_stylesheet
from PIL import Image
from PIL.ExifTags import TAGS
import piexif
import socket


class WorkerSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(int)


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
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class CameraManager:
    """Manages camera operations and reduces duplication between label and barcode cameras"""
    
    def __init__(self, camera_type, ui_components):
        self.camera_type = camera_type  # 'label' or 'barcode'
        self.ui_components = ui_components
        self.cap = None
        self.webcam_view = False
        self.selected_camera = f'Webcam {0 if camera_type == "label" else 1}'
        self.frame = None
        self.webcam_list = []
        
    def discover_cameras(self):
        """Discover available cameras"""
        self.webcam_list = []
        index = 0
        while True:
            cap = cv2.VideoCapture(index)
            try:
                if cap.getBackendName() == "MSMF":
                    self.webcam_list.append(f"Webcam {index}")
            except:
                break
            cap.release()
            index += 1
        return self.webcam_list
    
    def setup_camera(self, camera_id):
        """Setup camera with standard settings"""
        if self.cap:
            self.cap.release()
        
        self.cap = cv2.VideoCapture(camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
    def select_camera(self, camera_name):
        """Select and setup a camera"""
        if self.webcam_view:
            self.cap.release()
        
        camera_id = int(camera_name.split(" ")[1])
        self.setup_camera(camera_id)
        self.selected_camera = camera_name
        return f"Selected {camera_name}"
    
    def update_webcam_feed(self, cam_id, progress_callback):
        """Generic webcam feed update method"""
        while self.webcam_view:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = cv2.flip(img, -1)
                
                # Apply camera-specific processing
                if self.camera_type == 'barcode':
                    img = self._process_barcode_frame(frame, img)
                
                # Convert and display
                live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
                live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                live_img_scaled = live_img_pixmap.scaled(
                    cam_id.width(), cam_id.height(), QtCore.Qt.KeepAspectRatio
                )
                cam_id.setPixmap(live_img_scaled)
                cam_id.setAlignment(QtCore.Qt.AlignCenter)
        
        cam_id.setText("Live view disabled.")
        return self.frame
    
    def _process_barcode_frame(self, original_frame, display_frame):
        """Process frame for barcode detection"""
        decoded_data = self._decode_datamatrix(original_frame)
        if decoded_data:
            cv2.putText(display_frame, f"Decoded data: {decoded_data}", 
                       (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (48, 56, 65), 2, cv2.LINE_AA)
            self.ui_components['accession_field'].setText(decoded_data)
        return display_frame
    
    def _decode_datamatrix(self, frame):
        """Decode datamatrix from frame"""
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
        return None
    
    def toggle_webcam_view(self, cam_id, button_id, other_camera_manager):
        """Toggle webcam view on/off"""
        if not self.webcam_view:
            if other_camera_manager.selected_camera != self.selected_camera:
                self.webcam_view = True
                button_id.setText("Stop Live View")
                return True, f"Began {self.camera_type} camera live view."
            else:
                return False, "Selected camera is already in use."
        else:
            self.webcam_view = False
            button_id.setText("Start live view")
            return True, f"Ended {self.camera_type} camera live view."
    
    def get_device_info(self):
        """Get camera device information"""
        try:
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            backend = self.cap.getBackendName()
            return f"{self.selected_camera} ({backend}) - {width}x{height} @ {fps}fps"
        except:
            return f"{self.selected_camera} - Camera"


class ExifManager:
    """Manages EXIF data operations"""
    
    @staticmethod
    def create_exif_data(image_path, creator, taxon, accession, device_info):
        """Create EXIF data dictionary"""
        now = datetime.datetime.now()
        
        # Get image dimensions
        img = Image.open(image_path)
        width, height = img.size
        img.close()
        
        exif_dict = {
            "0th": {},
            "Exif": {},
            "GPS": {},
            "1st": {},
            "thumbnail": None
        }
        
        # Basic image info
        exif_dict["0th"][piexif.ImageIFD.Copyright] = f"CC-BY 4.0 {now.year} Manaaki Whenua Landcare Research"
        exif_dict["0th"][piexif.ImageIFD.Artist] = creator  # Fixed: Changed from Author to Artist
        exif_dict["0th"][piexif.ImageIFD.DateTime] = now.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict["0th"][piexif.ImageIFD.Make] = "RAPIIDlite"
        exif_dict["0th"][piexif.ImageIFD.Model] = device_info
        exif_dict["0th"][piexif.ImageIFD.Software] = "RAPIIDlite v2.0"
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = f"Specimen: {taxon} - {accession} - LABEL"
        
        # EXIF specific data
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = now.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = now.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = f"Taxon: {taxon}, Accession: {accession}".encode('utf-8')
        
        return exif_dict
    
    @staticmethod
    def add_exif_to_image(image_path, creator, taxon, accession, device_info):
        """Add EXIF data to an image"""
        try:
            exif_dict = ExifManager.create_exif_data(image_path, creator, taxon, accession, device_info)
            exif_bytes = piexif.dump(exif_dict)
            
            img = Image.open(image_path)
            img.save(image_path, exif=exif_bytes)
            img.close()
            
            return True, f"EXIF data added to {os.path.basename(image_path)}"
        except Exception as e:
            return False, f"Failed to add EXIF data: {str(e)}"
    
    @staticmethod
    def get_csv_data(creator, taxon, accession, file_format):
        """Get EXIF data as a dictionary for CSV logging"""
        now = datetime.datetime.now()
        
        return {
            'copyright_type': f"CC-BY 4.0 {now.year}",
            'rights_owner': f"Manaaki Whenua Landcare Research",
            'creator': creator,  # Fixed: Use parameter instead of self.ui
            'date_captured': now.strftime("%Y-%m-%d %H:%M:%S"),
            'capture_device': f"RAPIIDlite",
            'caption': f"{accession} - Specimen label",  # Fixed: Use parameter
            'image_format': file_format.replace('.', '').upper(),
            'taxon_name': taxon,  # Fixed: Use parameter
            'accession_number': accession,  # Fixed: Use parameter
            'image_filename': f"{accession}_label{file_format}",  # Fixed: Use parameter
            'title': f"{taxon} - {accession} - Specimen label"  # Fixed: Use parameter
        }


class FileManager:
    """Manages file operations"""
    
    CSV_HEADERS = [
        'image_filename', 'accession_number', 'taxon_name', 'image_format',
        'copyright_type', 'rights_owner', 'creator', 'date_captured',
        'capture_device', 'caption', 'title'
    ]
    
    @staticmethod
    def create_folders(output_path):
        """Create output folders if they don't exist"""
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            return True, f"Created folder: {output_path}"
        return False, ""
    
    @staticmethod
    def create_or_update_csv(output_location, taxon, csv_data):
        """Create or update CSV file with image capture data"""
        taxon_folder = Path(output_location).joinpath(taxon)
        csv_file_path = taxon_folder.joinpath(f"{taxon}_captures.csv")
        
        file_exists = csv_file_path.exists()
        
        try:
            taxon_folder.mkdir(parents=True, exist_ok=True)
            
            with open(csv_file_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=FileManager.CSV_HEADERS)
                
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(csv_data)
                
            return True, f"Added capture data to CSV: {csv_file_path.name}"
        except Exception as e:
            return False, f"Failed to write to CSV: {str(e)}"


class UI(QMainWindow):
    def __init__(self):
        super(UI, self).__init__()
        
        self.setWindowIcon(QtGui.QIcon(str(Path.cwd().joinpath("images", "RAPIIDlite_icon.png"))))
        self.exit_program = False
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # Initialize thread pool
        self.threadpool = QtCore.QThreadPool()
        print(f"Multithreading with maximum {self.threadpool.maxThreadCount()} threads")
        
        # Initialize camera managers
        self.label_camera = CameraManager('label', {
            'accession_field': self.ui.lineEdit_accession
        })
        self.barcode_camera = CameraManager('barcode', {
            'accession_field': self.ui.lineEdit_accession
        })
        
        # Set initial variables
        self.file_format = ".jpg"
        self.output_location = str(Path.home())
        
        self._setup_ui_connections()
        self._setup_cameras()
        self._setup_config()
        
        self.showMaximized()
    
    def _setup_ui_connections(self):
        """Setup UI connections"""
        # Capture controls
        self.ui.pushButton_capture.pressed.connect(self.capture_set)
        self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
        self.ui.shortcut_capture.activated.connect(self.capture_set)
        
        # Camera controls
        self.ui.pushButton_label_webcam.pressed.connect(
            lambda: self._toggle_camera_view(self.label_camera, self.ui.label_camera, self.ui.pushButton_label_webcam)
        )
        self.ui.pushButton_barcode_webcam.pressed.connect(
            lambda: self._toggle_camera_view(self.barcode_camera, self.ui.barcode_camera, self.ui.pushButton_barcode_webcam)
        )
        
        # Camera selection
        self.ui.comboBox_selectLabelWebcam.currentTextChanged.connect(
            lambda: self._select_camera(self.label_camera, self.ui.comboBox_selectLabelWebcam.currentText())
        )
        self.ui.comboBox_selectBarcodeWebcam.currentTextChanged.connect(
            lambda: self._select_camera(self.barcode_camera, self.ui.comboBox_selectBarcodeWebcam.currentText())
        )
        
        # File operations
        self.ui.pushButton_outputFolder.pressed.connect(self.set_output_location)
        self.ui.pushButton_load_config.pressed.connect(self.loadConfig)
        self.ui.pushButton_writeConfig.pressed.connect(self.writeConfig)
    
    def _setup_cameras(self):
        """Setup camera discovery and selection"""
        # Setup label camera
        label_cameras = self.label_camera.discover_cameras()
        for camera in label_cameras:
            self.ui.comboBox_selectLabelWebcam.addItem(camera)
        if label_cameras:
            self.ui.comboBox_selectLabelWebcam.setCurrentIndex(0)
        
        # Setup barcode camera
        barcode_cameras = self.barcode_camera.discover_cameras()
        for camera in barcode_cameras:
            self.ui.comboBox_selectBarcodeWebcam.addItem(camera)
        if barcode_cameras and len(barcode_cameras) > 1:
            self.ui.comboBox_selectBarcodeWebcam.setCurrentIndex(1)
        
        # Initialize camera selections
        self._select_camera(self.label_camera, self.ui.comboBox_selectLabelWebcam.currentText())
        self._select_camera(self.barcode_camera, self.ui.comboBox_selectBarcodeWebcam.currentText())
    
    def _setup_config(self):
        """Setup configuration"""
        self.config = self.get_default_values()
        self.ui.lineEdit_taxon.setText(self.config["general"]["taxon_name"])
        self.ui.lineEdit_creator.setText(self.config["general"]["creator"])
        self.loadedConfig = False
        self.update_output_location()
    
    def _select_camera(self, camera_manager, camera_name):
        """Select camera for a camera manager"""
        if camera_name:
            message = camera_manager.select_camera(camera_name)
            self.log_info(message)
    
    def _toggle_camera_view(self, camera_manager, cam_id, button_id):
        """Toggle camera view for a camera manager"""
        other_camera = self.barcode_camera if camera_manager == self.label_camera else self.label_camera
        success, message = camera_manager.toggle_webcam_view(cam_id, button_id, other_camera)
        
        if success and camera_manager.webcam_view:
            worker = Worker(camera_manager.update_webcam_feed, cam_id)
            self.threadpool.start(worker)
        
        self.log_info(message)
    
    def set_output_location(self):
        """Set output location"""
        new_location = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose output folder...", str(Path.cwd())
        )
        
        if new_location:
            self.output_location = new_location
            self.log_info("Output location updated.")
        
        self.update_output_location()
    
    def update_output_location(self):
        """Update output location display"""
        self.ui.display_path.setText(self.output_location)
    
    def log_info(self, info):
        """Log information to the UI"""
        now = datetime.datetime.now()
        self.ui.listWidget_log.addItem(f"{now.strftime('%H:%M:%S')} {info}")
        self.ui.listWidget_log.sortItems(QtCore.Qt.DescendingOrder)
    
    def capture_set(self):
        """Handle capture operation"""
        output_folder = Path(self.output_location).joinpath(
            self.ui.lineEdit_taxon.text(),
            self.ui.lineEdit_accession.text()
        )
        
        if output_folder.exists():
            self.show_popup()
        else:
            self._perform_capture()
    
    def show_popup(self):
        """Show overwrite confirmation popup"""
        button = QMessageBox.question(
            self, "RAPIID lite Dialog",
            "A folder with this accession number already exists!\nDo you want to overwrite the existing file/s?"
        )
        if button == QMessageBox.Yes:
            self._perform_capture()
    
    def _perform_capture(self):
        """Perform the actual capture operation"""
        self.ui.pushButton_capture.setEnabled(False)
        self.capture_label_webcam("_label")
        self.ui.pushButton_capture.setEnabled(True)
    
    def capture_label_webcam(self, tag):
        """Capture image from label webcam"""
        # Create output folders
        output_folder = Path(self.output_location).joinpath(
            self.ui.lineEdit_taxon.text(),
            self.ui.lineEdit_accession.text()
        )
        
        created, folder_msg = FileManager.create_folders(output_folder)
        if created:
            self.log_info(folder_msg)
        
        # Save image
        file_name = str(output_folder.joinpath(f"{self.ui.lineEdit_accession.text()}{tag}{self.file_format}"))
        frame_to_save = self.label_camera.frame
        
        try:
            cv2.imwrite(file_name, frame_to_save)
            self.log_info(f"File {file_name} saved successfully.")
            
            # Get current values from UI
            creator = self.ui.lineEdit_creator.text()
            taxon = self.ui.lineEdit_taxon.text()
            accession = self.ui.lineEdit_accession.text()
            device_info = self.label_camera.get_device_info()
            
            # Add EXIF data
            success, exif_msg = ExifManager.add_exif_to_image(
                file_name,
                creator,
                taxon,
                accession,
                device_info
            )
            self.log_info(exif_msg)
            
            # Create CSV data - Fixed: Pass all required parameters
            csv_data = ExifManager.get_csv_data(
                creator,
                taxon,
                accession,
                self.file_format
            )
            
            # Update CSV
            success, csv_msg = FileManager.create_or_update_csv(
                self.output_location,
                taxon,
                csv_data
            )
            self.log_info(csv_msg)
            
        except Exception as e:
            self.log_info(f"File {file_name} was unable to be saved! Error: {str(e)}")
    
    def loadConfig(self):
        """Load configuration from file"""
        file = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load existing config file", str(Path.cwd()), "config file (*.yaml)"
        )
        config_location = file[0]
        
        if config_location:
            config_location = Path(config_location)
            config = ymlRW.read_config_file(config_location)
            
            # Apply configuration
            self.output_location = config["general"]["output_folder"]
            self.ui.display_path.setText(self.output_location)
            self.ui.lineEdit_creator.setText(config["general"]["creator"])
            self.ui.lineEdit_taxon.setText(config["general"]["taxon_name"])
            
            self.loadedConfig = True
            self.log_info("Loaded config file successfully!")
    
    def writeConfig(self):
        """Write configuration to file"""
        output_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text())
        
        created, folder_msg = FileManager.create_folders(output_folder)
        if created:
            self.log_info(folder_msg)
        
        config = {
            'general': {
                'creator': self.ui.lineEdit_creator.text(),
                'taxon_name': self.ui.lineEdit_taxon.text(),
                'output_folder': self.output_location,
            }
        }
        
        ymlRW.write_config_file(config, output_folder)
        self.log_info("Exported config file successfully!")
    
    def get_default_values(self):
        """Get default configuration values"""
        return {
            'general': {
                'creator': 'new_user',
                'taxon_name': 'untitled_taxon',
            }
        }
    
    def closeApp(self):
        """Close the application"""
        sys.exit()
    
    def closeEvent(self, event):
        """Handle application close event"""
        self.exit_program = True
        print("Application Closed!")


# Initialize the app
app = QApplication(sys.argv)
UIWindow = UI()
apply_stylesheet(app, theme='dark_lightgreen.xml')
app.exec_()

