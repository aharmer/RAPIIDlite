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
        exif_dict["0th"][piexif.ImageIFD.Author] = creator
        exif_dict["0th"][piexif.ImageIFD.DateTime] = now.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict["0th"][piexif.ImageIFD.Make] = "RAPIIDlite"
        exif_dict["0th"][piexif.ImageIFD.Model] = device_info
        exif_dict["0th"][piexif.ImageIFD.Software] = "RAPIIDlite v1.0"
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
            'creator': creator,
            'date_captured': now.strftime("%Y-%m-%d %H:%M:%S"),
            'capture_device': f"RAPIIDlite",
            'caption': f"{accession} - Specimen label",
            'image_format': file_format.replace('.', '').upper(),
            'taxon_name': taxon,
            'accession_number': accession,
            'image_filename': f"{accession}_label{file_format}",
            'title': f"{taxon} - {accession} - Specimen label"
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
            
            # Add EXIF data
            success, exif_msg = ExifManager.add_exif_to_image(
                file_name,
                self.ui.lineEdit_creator.text(),
                self.ui.lineEdit_taxon.text(),
                self.ui.lineEdit_accession.text(),
                self.label_camera.get_device_info()
            )
            self.log_info(exif_msg)
            
            # Create CSV data
            csv_data = ExifManager.get_csv_data(
                self.ui.lineEdit_creator.text(),
                self.ui.lineEdit_taxon.text(),
                self.ui.lineEdit_accession.text(),
                self.file_format
            )
            
            # Update CSV
            success, csv_msg = FileManager.create_or_update_csv(
                self.output_location,
                self.ui.lineEdit_taxon.text(),
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





# import sys
# import os
# from pathlib import Path
# import datetime
# import csv
# from PyQt5 import QtWidgets, QtGui, QtCore
# from PyQt5.QtGui import *
# from PyQt5.QtWidgets import *
# from PyQt5.QtCore import *
# from GUI.rapiidlite_GUI import Ui_MainWindow  # importing main window of the GUI
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

#         # Store constructor arguments (re-used for processing)
#         self.fn = fn
#         self.args = args
#         self.kwargs = kwargs
#         self.signals = WorkerSignals()

#         # Add the callback to kwargs
#         self.kwargs['progress_callback'] = self.signals.progress

#     @QtCore.pyqtSlot()
#     def run(self):
#         # Retrieve args/kwargs here; and fire processing using them
#         try:
#             result = self.fn(*self.args, **self.kwargs)
#         except:
#             traceback.print_exc()
#             exctype, value = sys.exc_info()[:2]
#             self.signals.error.emit((exctype, value, traceback.format_exc()))
#         else:
#             self.signals.result.emit(result)  # Return the result of the processing
#         finally:
#             self.signals.finished.emit()  # Done


# class UI(QMainWindow):
#     def __init__(self):
#         super(UI, self).__init__()

#         self.setWindowIcon(QtGui.QIcon(str(Path.cwd().joinpath("images", "RAPIIDlite_icon.png"))))

#         self.exit_program = False

#         self.ui = Ui_MainWindow()
#         self.ui.setupUi(self)

#         self.frame = None

#         # start thread pool
#         self.threadpool = QtCore.QThreadPool()
#         print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

#         # Set initial camera variables and buttons
#         self.file_format = ".jpg"
#         self.label_webcamView = False
#         self.barcode_webcamView = False
#         self.selected_labelcam = 'Webcam 0'
#         self.selected_barcodecam = 'Webcam 1'

#         # # Assign camera control features to ui
#         self.ui.pushButton_capture.pressed.connect(self.capture_set)

#         self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
#         self.ui.shortcut_capture.activated.connect(self.capture_set)

#         # Initiate webcam
#         self.ui.pushButton_label_webcam.pressed.connect(lambda: self.begin_label_webcam(cam_id = self.ui.label_camera, button_id = self.ui.pushButton_label_webcam))
#         self.ui.pushButton_barcode_webcam.pressed.connect(lambda: self.begin_barcode_webcam(cam_id = self.ui.barcode_camera, button_id = self.ui.pushButton_barcode_webcam))

#         # List webcams for label camera  
#         self.index_label = 0
#         self.webcam_arr_label = []
#         while True:
#             self.cap_label = cv2.VideoCapture(self.index_label)
#             try:
#                 if self.cap_label.getBackendName() == "MSMF":
#                     self.webcam_arr_label.append("Webcam " + str(self.index_label))
#             except:
#                 break
#             self.cap_label.release()
#             self.index_label += 1
    
#         for webcam in self.webcam_arr_label:
#             self.ui.comboBox_selectLabelWebcam.addItem(webcam)
#         self.ui.comboBox_selectLabelWebcam.setCurrentIndex(0)

#         # List webcams for barcode camera  
#         self.index_barcode = 0
#         self.webcam_arr_barcode = []
#         while True:
#             self.cap_barcode = cv2.VideoCapture(self.index_barcode)
#             try:
#                 if self.cap_barcode.getBackendName() == "MSMF":
#                     self.webcam_arr_barcode.append("Webcam " + str(self.index_barcode))
#             except:
#                 break
#             self.cap_barcode.release()
#             self.index_barcode += 1
    
#         for webcam in self.webcam_arr_barcode:
#             self.ui.comboBox_selectBarcodeWebcam.addItem(webcam)
#         self.ui.comboBox_selectBarcodeWebcam.setCurrentIndex(1)

#         self.ui.comboBox_selectLabelWebcam.currentTextChanged.connect(self.select_label_webcam)
#         self.ui.comboBox_selectBarcodeWebcam.currentTextChanged.connect(self.select_barcode_webcam)

#         self.select_label_webcam()
#         self.select_barcode_webcam()

#         # Select output folder
#         self.output_location = str(Path.home())
#         self.update_output_location()
#         self.ui.pushButton_outputFolder.pressed.connect(self.set_output_location)
#         self.output_location_folder = Path(self.output_location)

#         # Config file
#         self.config = self.get_default_values()
#         self.ui.lineEdit_taxon.setText(self.config["general"]["taxon_name"])
#         self.ui.lineEdit_creator.setText(self.config["general"]["creator"])
#         self.loadedConfig = False
#         self.ui.pushButton_load_config.pressed.connect(self.loadConfig)
#         self.ui.pushButton_writeConfig.pressed.connect(self.writeConfig)

#         # Show the app
#         self.showMaximized()

#     def select_label_webcam(self):
#         selected_camera = self.ui.comboBox_selectLabelWebcam.currentText()

#         # stop the webcam if currently in use
#         if self.label_webcamView:
#             self.cap_label.release()

#         # Select new webcam
#         webcam_id = int(selected_camera.split(" ")[1])
#         self.cap_label = cv2.VideoCapture(webcam_id)
#         self.cap_label.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
#         self.cap_label.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
#         self.selected_labelcam = selected_camera
#         self.log_info("Selected " + str(selected_camera))

#     def select_barcode_webcam(self):
#         selected_camera = self.ui.comboBox_selectBarcodeWebcam.currentText()

#         # stop the webcam if currently in use
#         if self.barcode_webcamView:
#             self.cap_barcode.release()

#         # Select new webcam
#         webcam_id = int(selected_camera.split(" ")[1])
#         self.cap_barcode = cv2.VideoCapture(webcam_id)
#         self.cap_barcode.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
#         self.cap_barcode.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
#         self.selected_barcodecam = selected_camera
#         self.log_info("Selected " + str(selected_camera))

#     def set_output_location(self):
#         new_location = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder...", str(Path.cwd()))
                
#         if new_location:
#             self.output_location = new_location
#             self.log_info("Output location updated.")

#         self.update_output_location()

#     def update_output_location(self):
#         self.ui.display_path.setText(self.output_location)

#     def log_info(self, info):
#         now = datetime.datetime.now()
#         self.ui.listWidget_log.addItem(now.strftime("%H:%M:%S") + " " + info)
#         self.ui.listWidget_log.sortItems(QtCore.Qt.DescendingOrder)

#     def decode_datamatrix(self, frame):
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         blur = cv2.GaussianBlur(gray, (3,3), 0)
#         _, threshold = cv2.threshold(blur, 50, 255, cv2.THRESH_BINARY_INV)
#         kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7,7))
#         closing = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel)
#         contours, _ = cv2.findContours(closing, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

#         for contour in contours:
#             if cv2.contourArea(contour) > 1000:  # Adjust the threshold based on your needs
#                 x, y, w, h = cv2.boundingRect(contour)
#                 aspect_ratio = float(w) / h

#                 # Check if the aspect ratio is close to 1 (square shape)
#                 if 0.8 <= aspect_ratio <= 1.2:
                  
#                   # Crop the detected DataMatrix region
#                   roi = gray[y - 1:y + h + 1, x - 1:x + w + 1]

#                   # Decode the DataMatrix
#                   if roi is not None and roi.size > 0:
#                     decoded_data = dmtx.decode(roi)
#                     for data in decoded_data:
#                         return data.data.decode('utf-8')  # Return the decoded data

#         return None

#     def update_barcode_webcam(self, cam_id, progress_callback):
#         # Read the current frame from the video stream
#         while self.barcode_webcamView:    
#             ret, frame = self.cap_barcode.read()

#             if ret:
#                 # Convert the frame to RGB format
#                 img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#                 img = cv2.flip(img, -1)
                
#                 decoded_data = self.decode_datamatrix(frame)

#                 if decoded_data:
#                     cv2.putText(img, "Decoded data: " + decoded_data, (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (48, 56, 65), 2, cv2.LINE_AA)
#                     self.ui.lineEdit_accession.setText(decoded_data)

#                 # Convert the frame to QImage
#                 live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
#                 live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                
#                 # Setup pixmap with the acquired image
#                 live_img_scaled = live_img_pixmap.scaled(cam_id.width(),
#                                                          cam_id.height(),
#                                                          QtCore.Qt.KeepAspectRatio)
#                 # Set the pixmap onto the label
#                 cam_id.setPixmap(live_img_scaled)
#                  # Align the label to center
#                 cam_id.setAlignment(QtCore.Qt.AlignCenter)

#         cam_id.setText("Live view disabled.")

    
#     def update_label_webcam(self, cam_id, progress_callback):
#         # Read the current frame from the video stream
#         while self.label_webcamView:    
#             ret, frame = self.cap_label.read()

#             if ret:
#                 # Update the frame attribute
#                 self.frame = frame

#                 # Convert the frame to RGB format
#                 img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#                 img = cv2.flip(img, -1)

#                 # Convert the frame to QImage
#                 live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
#                 live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                
#                 # Setup pixmap with the acquired image
#                 live_img_scaled = live_img_pixmap.scaled(cam_id.width(),
#                                                          cam_id.height(),
#                                                          QtCore.Qt.KeepAspectRatio)
#                 # Set the pixmap onto the label
#                 cam_id.setPixmap(live_img_scaled)
#                  # Align the label to center
#                 cam_id.setAlignment(QtCore.Qt.AlignCenter)

#         else:
#             cam_id.setText("Live view disabled.")

#         return self.frame
        
        
#     def begin_label_webcam(self, cam_id, button_id):
#         selected_camera = self.ui.comboBox_selectLabelWebcam.currentText()
#         if not self.label_webcamView:
#             if self.selected_barcodecam != selected_camera:
#                 self.log_info("Began label camera live view.")
#                 button_id.setText("Stop Live View")
#                 self.label_webcamView = True
            
#                 worker = Worker(self.update_label_webcam, cam_id)
#                 self.threadpool.start(worker)
#             else:
#                 self.log_info("Selected camera is already in use.")
#         else:
#             button_id.setText("Start live view")
#             self.log_info("Ended label camera live view")
#             self.label_webcamView = False

#     def begin_barcode_webcam(self, cam_id, button_id):
#         selected_camera = self.ui.comboBox_selectBarcodeWebcam.currentText()
#         if not self.barcode_webcamView:
#             if self.selected_labelcam != selected_camera:
#                 self.log_info("Began label camera live view.")
#                 button_id.setText("Stop Live View")
#                 self.barcode_webcamView = True
                
#                 worker = Worker(self.update_barcode_webcam, cam_id)
#                 self.threadpool.start(worker)
#             else:
#                 self.log_info("Selected camera is already in use.")
#         else:
#             button_id.setText("Start live view")
#             self.log_info("Ended label camera live view")
#             self.barcode_webcamView = False

#     def get_capture_device_info(self):
#         """Get capture device information"""
#         try:
#             # Get camera properties
#             width = int(self.cap_label.get(cv2.CAP_PROP_FRAME_WIDTH))
#             height = int(self.cap_label.get(cv2.CAP_PROP_FRAME_HEIGHT))
#             fps = self.cap_label.get(cv2.CAP_PROP_FPS)
#             backend = self.cap_label.getBackendName()
            
#             device_info = f"{self.selected_labelcam} ({backend}) - {width}x{height} @ {fps}fps"
#             return device_info
#         except:
#             return f"{self.selected_labelcam} - Camera"

#     def create_exif_data(self, image_path):
#         """Create EXIF data dictionary"""
#         now = datetime.datetime.now()
        
#         # Get image dimensions
#         img = Image.open(image_path)
#         width, height = img.size
#         img.close()
        
#         # Create EXIF dictionary
#         exif_dict = {
#             "0th": {},
#             "Exif": {},
#             "GPS": {},
#             "1st": {},
#             "thumbnail": None
#         }
        
#         # Basic image info
#         exif_dict["0th"][piexif.ImageIFD.Copyright] = f"CC-BY 4.0 {now.year} Manaaki Whenua Landcare Research"
#         exif_dict["0th"][piexif.ImageIFD.Author] = self.ui.lineEdit_creator.text()
#         exif_dict["0th"][piexif.ImageIFD.DateTime] = now.strftime("%Y:%m:%d %H:%M:%S")
#         exif_dict["0th"][piexif.ImageIFD.Make] = "RAPIIDlite"
#         exif_dict["0th"][piexif.ImageIFD.Model] = self.get_capture_device_info()
#         exif_dict["0th"][piexif.ImageIFD.Software] = "RAPIIDlite v1.0"
#         exif_dict["0th"][piexif.ImageIFD.ImageDescription] = f"Specimen: {self.ui.lineEdit_taxon.text()} - {self.ui.lineEdit_accession.text()} - LABEL"
        
#         # EXIF specific data
#         exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = now.strftime("%Y:%m:%d %H:%M:%S")
#         exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = now.strftime("%Y:%m:%d %H:%M:%S")
#         exif_dict["Exif"][piexif.ExifIFD.UserComment] = f"Taxon: {self.ui.lineEdit_taxon.text()}, Accession: {self.ui.lineEdit_accession.text()}".encode('utf-8')
        
#         return exif_dict

#     def add_exif_to_image(self, image_path):
#         """Add EXIF data to an image"""
#         try:
#             exif_dict = self.create_exif_data(image_path)
#             exif_bytes = piexif.dump(exif_dict)
            
#             # Read image and add EXIF data
#             img = Image.open(image_path)
#             img.save(image_path, exif=exif_bytes)
#             img.close()
            
#             self.log_info(f"EXIF data added to {os.path.basename(image_path)}")
#             return True
#         except Exception as e:
#             self.log_info(f"Failed to add EXIF data: {str(e)}")
#             return False

#     def get_exif_data_for_csv(self):
#         """Get EXIF data as a dictionary for CSV logging"""
#         now = datetime.datetime.now()
        
#         return {
#             'copyright_type': f"CC-BY 4.0 {now.year}",
#             'rights_owner': f"Manaaki Whenua Landcare Research",
#             'creator': self.ui.lineEdit_creator.text(),
#             'date_captured': now.strftime("%Y-%m-%d %H:%M:%S"),
#             'capture_device': f"RAPIIDlite",
#             'caption': f"{self.ui.lineEdit_accession.text()} - Specimen label",
#             'image_format': self.file_format.replace('.', '').upper(),
#             'taxon_name': self.ui.lineEdit_taxon.text(),
#             'accession_number': self.ui.lineEdit_accession.text(),
#             'image_filename': f"{self.ui.lineEdit_accession.text()}_label{self.file_format}",
#             'title': f"{self.ui.lineEdit_taxon.text()} - {self.ui.lineEdit_accession.text()} - Specimen label"
#         }

#     def create_or_update_csv(self, csv_data):
#         """Create or update CSV file with image capture data"""
#         taxon_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text())
#         csv_file_path = taxon_folder.joinpath(f"{self.ui.lineEdit_taxon.text()}_captures.csv")
        
#         # Define CSV headers
#         headers = [
#             'image_filename',
#             'accession_number',
#             'taxon_name',
#             'image_format',
#             'copyright_type',
#             'rights_owner',
#             'creator',
#             'date_captured',
#             'capture_device',
#             'caption',
#             'title'
#         ]
        
#         # Check if CSV file exists
#         file_exists = csv_file_path.exists()
        
#         try:
#             # Create taxon folder if it doesn't exist
#             taxon_folder.mkdir(parents=True, exist_ok=True)
            
#             # Write to CSV file
#             with open(csv_file_path, 'a', newline='', encoding='utf-8') as csvfile:
#                 writer = csv.DictWriter(csvfile, fieldnames=headers)
                
#                 # Write header if file is new
#                 if not file_exists:
#                     writer.writeheader()
#                     self.log_info(f"Created new CSV file: {csv_file_path.name}")
                
#                 # Write data row
#                 writer.writerow(csv_data)
#                 self.log_info(f"Added capture data to CSV: {csv_file_path.name}")
                
#         except Exception as e:
#             self.log_info(f"Failed to write to CSV: {str(e)}")

#     def capture_set(self):
#         self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text()).joinpath(self.ui.lineEdit_accession.text())
#         if os.path.exists(self.output_location_folder):
#             self.show_popup()
#         else:
#             self.ui.pushButton_capture.setEnabled(False)
#             self.capture_label_webcam(tag = "_label")
#             self.ui.pushButton_capture.setEnabled(True)

#     def show_popup(self):
#         button = QMessageBox.question(self, "RAPIID lite Dialog", "A folder with this accession number already exists!\nDo you want to overwrite the existing file/s?")
#         if button == QMessageBox.Yes:
#             self.popup_button()

#     def popup_button(self):
#         self.ui.pushButton_capture.setEnabled(False)
#         self.capture_label_webcam(tag = "_label")
#         self.ui.pushButton_capture.setEnabled(True)

#     def capture_label_webcam(self, tag):
#         self.create_output_folders()
#         file_name = str(self.output_location_folder.joinpath(self.ui.lineEdit_accession.text() + tag + self.file_format))
#         frame_to_save = self.frame
        
#         try:
#             # Save the image
#             cv2.imwrite(file_name, frame_to_save)
#             self.log_info("File " + file_name + " saved successfully.")
            
#             # Add EXIF data to the image
#             self.add_exif_to_image(file_name)
            
#             # Get EXIF data for CSV
#             csv_data = self.get_exif_data_for_csv()
            
#             # Create or update CSV file
#             self.create_or_update_csv(csv_data)
            
#         except Exception as e:
#             self.log_info("File " + file_name + " was unable to be saved! Error: " + str(e))

#     def create_output_folders(self):
#         self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text()).joinpath(self.ui.lineEdit_accession.text())
#         if not os.path.exists(self.output_location_folder):
#             os.makedirs(self.output_location_folder)
#             self.log_info("Created folder: " + str(self.ui.lineEdit_taxon.text() + "/" + self.ui.lineEdit_accession.text()))

#     def loadConfig(self):
#         file = QtWidgets.QFileDialog.getOpenFileName(self, "Load existing config file", str(Path.cwd()), "config file (*.yaml)")
#         config_location = file[0]
#         if config_location:
#             # if a file has been selected, convert it into a Path object
#             config_location = Path(config_location)
#             config = ymlRW.read_config_file(config_location)

#             return

#             # output path
#             self.output_location = config["general"]["output_folder"]
#             self.ui.display_path.setText(self.output_location)

#             # creator
#             self.ui.lineEdit_creator.setText(config["general"]["creator"])

#             # taxon name
#             self.ui.lineEdit_taxon.setText(config["general"]["taxon_name"])

#             self.loadedConfig = True
#             self.log_info("Loaded config file successfully!")
#             print(config)

#     def writeConfig(self):
#         self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text())
#         if not os.path.exists(self.output_location_folder):
#             os.makedirs(self.output_location_folder)
#             self.log_info("Created folder: " + str(self.ui.lineEdit_taxon.text()))

#         config = {'general': {'creator': self.ui.lineEdit_creator.text(),
#                               'taxon_name': self.ui.lineEdit_taxon.text(),
#                               'output_folder': self.output_location,
#                               },
#                   }

#         ymlRW.write_config_file(config, Path(self.output_location_folder))
#         self.log_info("Exported config file successfully!")

#     def get_default_values(self):
#         config = {'general': {'creator': 'new_user',
#                               'taxon_name': 'untitled_taxon',
#                               },
#                       }
#         return config

#     def closeApp(self):
#         sys.exit()

#     def closeEvent(self, event):
#         # report the program is to be closed so threads can be exited
#         self.exit_program = True
#         print("Application Closed!")

# # Initialise the app
# app = QApplication(sys.argv)
# UIWindow = UI()
# apply_stylesheet(app, theme = 'dark_lightgreen.xml')
# app.exec_()


# import sys
# import os
# from pathlib import Path
# import datetime
# from PyQt5 import QtWidgets, QtGui, QtCore
# from PyQt5.QtGui import *
# from PyQt5.QtWidgets import *
# from PyQt5.QtCore import *
# from GUI.rapiidlite_GUI import Ui_MainWindow  # importing main window of the GUI
# import scripts.ymlRW as ymlRW
# import cv2
# import pylibdmtx.pylibdmtx as dmtx
# from qt_material import apply_stylesheet


# class WorkerSignals(QtCore.QObject):
    
#     finished = QtCore.pyqtSignal()
#     error = QtCore.pyqtSignal(tuple)
#     result = QtCore.pyqtSignal(object)
#     progress = QtCore.pyqtSignal(int)


# class Worker(QtCore.QRunnable):

#     def __init__(self, fn, *args, **kwargs):
#         super(Worker, self).__init__()

#         # Store constructor arguments (re-used for processing)
#         self.fn = fn
#         self.args = args
#         self.kwargs = kwargs
#         self.signals = WorkerSignals()

#         # Add the callback to kwargs
#         self.kwargs['progress_callback'] = self.signals.progress

#     @QtCore.pyqtSlot()
#     def run(self):
#         # Retrieve args/kwargs here; and fire processing using them
#         try:
#             result = self.fn(*self.args, **self.kwargs)
#         except:
#             traceback.print_exc()
#             exctype, value = sys.exc_info()[:2]
#             self.signals.error.emit((exctype, value, traceback.format_exc()))
#         else:
#             self.signals.result.emit(result)  # Return the result of the processing
#         finally:
#             self.signals.finished.emit()  # Done


# class UI(QMainWindow):
#     def __init__(self):
#         super(UI, self).__init__()

#         self.setWindowIcon(QtGui.QIcon(str(Path.cwd().joinpath("images", "RAPIIDlite_icon.png"))))

#         self.exit_program = False

#         self.ui = Ui_MainWindow()
#         self.ui.setupUi(self)

#         self.frame = None

#         # start thread pool
#         self.threadpool = QtCore.QThreadPool()
#         print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

#         # Set initial camera variables and buttons
#         self.file_format = ".jpg"
#         self.label_webcamView = False
#         self.barcode_webcamView = False
#         self.selected_labelcam = 'Webcam 0'
#         self.selected_barcodecam = 'Webcam 1'

#         # # Assign camera control features to ui
#         self.ui.pushButton_capture.pressed.connect(self.capture_set)

#         self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
#         self.ui.shortcut_capture.activated.connect(self.capture_set)

#         # Initiate webcam
#         self.ui.pushButton_label_webcam.pressed.connect(lambda: self.begin_label_webcam(cam_id = self.ui.label_camera, button_id = self.ui.pushButton_label_webcam))
#         self.ui.pushButton_barcode_webcam.pressed.connect(lambda: self.begin_barcode_webcam(cam_id = self.ui.barcode_camera, button_id = self.ui.pushButton_barcode_webcam))

#         # List webcams for label camera  
#         self.index_label = 0
#         self.webcam_arr_label = []
#         while True:
#             self.cap_label = cv2.VideoCapture(self.index_label)
#             try:
#                 if self.cap_label.getBackendName() == "MSMF":
#                     self.webcam_arr_label.append("Webcam " + str(self.index_label))
#             except:
#                 break
#             self.cap_label.release()
#             self.index_label += 1
    
#         for webcam in self.webcam_arr_label:
#             self.ui.comboBox_selectLabelWebcam.addItem(webcam)
#         self.ui.comboBox_selectLabelWebcam.setCurrentIndex(0)

#         # List webcams for barcode camera  
#         self.index_barcode = 0
#         self.webcam_arr_barcode = []
#         while True:
#             self.cap_barcode = cv2.VideoCapture(self.index_barcode)
#             try:
#                 if self.cap_barcode.getBackendName() == "MSMF":
#                     self.webcam_arr_barcode.append("Webcam " + str(self.index_barcode))
#             except:
#                 break
#             self.cap_barcode.release()
#             self.index_barcode += 1
    
#         for webcam in self.webcam_arr_barcode:
#             self.ui.comboBox_selectBarcodeWebcam.addItem(webcam)
#         self.ui.comboBox_selectBarcodeWebcam.setCurrentIndex(1)

#         self.ui.comboBox_selectLabelWebcam.currentTextChanged.connect(self.select_label_webcam)
#         self.ui.comboBox_selectBarcodeWebcam.currentTextChanged.connect(self.select_barcode_webcam)

#         self.select_label_webcam()
#         self.select_barcode_webcam()

#         # Select output folder
#         self.output_location = str(Path.home())
#         self.update_output_location()
#         self.ui.pushButton_outputFolder.pressed.connect(self.set_output_location)
#         self.output_location_folder = Path(self.output_location)

#         # Config file
#         self.config = self.get_default_values()
#         self.ui.lineEdit_taxon.setText(self.config["general"]["taxon_name"])
#         self.ui.lineEdit_creator.setText(self.config["general"]["creator"])
#         self.loadedConfig = False
#         self.ui.pushButton_load_config.pressed.connect(self.loadConfig)
#         self.ui.pushButton_writeConfig.pressed.connect(self.writeConfig)

#         # Show the app
#         self.showMaximized()

#     def select_label_webcam(self):
#         selected_camera = self.ui.comboBox_selectLabelWebcam.currentText()

#         # stop the webcam if currently in use
#         if self.label_webcamView:
#             self.cap_label.release()

#         # Select new webcam
#         webcam_id = int(selected_camera.split(" ")[1])
#         self.cap_label = cv2.VideoCapture(webcam_id)
#         self.cap_label.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
#         self.cap_label.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
#         self.selected_labelcam = selected_camera
#         self.log_info("Selected " + str(selected_camera))

#     def select_barcode_webcam(self):
#         selected_camera = self.ui.comboBox_selectBarcodeWebcam.currentText()

#         # stop the webcam if currently in use
#         if self.barcode_webcamView:
#             self.cap_barcode.release()

#         # Select new webcam
#         webcam_id = int(selected_camera.split(" ")[1])
#         self.cap_barcode = cv2.VideoCapture(webcam_id)
#         self.cap_barcode.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
#         self.cap_barcode.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
#         self.selected_barcodecam = selected_camera
#         self.log_info("Selected " + str(selected_camera))

#     def set_output_location(self):
#         new_location = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder...", str(Path.cwd()))
                
#         if new_location:
#             self.output_location = new_location
#             self.log_info("Output location updated.")

#         self.update_output_location()

#     def update_output_location(self):
#         self.ui.display_path.setText(self.output_location)

#     def log_info(self, info):
#         now = datetime.datetime.now()
#         self.ui.listWidget_log.addItem(now.strftime("%H:%M:%S") + " " + info)
#         self.ui.listWidget_log.sortItems(QtCore.Qt.DescendingOrder)

#     def decode_datamatrix(self, frame):
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         blur = cv2.GaussianBlur(gray, (3,3), 0)
#         _, threshold = cv2.threshold(blur, 50, 255, cv2.THRESH_BINARY_INV)
#         kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7,7))
#         closing = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel)
#         contours, _ = cv2.findContours(closing, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

#         for contour in contours:
#             if cv2.contourArea(contour) > 1000:  # Adjust the threshold based on your needs
#                 x, y, w, h = cv2.boundingRect(contour)
#                 aspect_ratio = float(w) / h

#                 # Check if the aspect ratio is close to 1 (square shape)
#                 if 0.8 <= aspect_ratio <= 1.2:
                  
#                   # Crop the detected DataMatrix region
#                   roi = gray[y - 1:y + h + 1, x - 1:x + w + 1]

#                   # Decode the DataMatrix
#                   if roi is not None and roi.size > 0:
#                     decoded_data = dmtx.decode(roi)
#                     for data in decoded_data:
#                         return data.data.decode('utf-8')  # Return the decoded data
#             #       else:
#             #         break
#             #     else:
#             #         break
#             # else:
#             #     break

#         return None

#     def update_barcode_webcam(self, cam_id, progress_callback):
#         # Read the current frame from the video stream
#         while self.barcode_webcamView:    
#             ret, frame = self.cap_barcode.read()

#             if ret:
#                 # Convert the frame to RGB format
#                 img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#                 img = cv2.flip(img, -1)
                
#                 decoded_data = self.decode_datamatrix(frame)

#                 if decoded_data:
#                     cv2.putText(img, "Decoded data: " + decoded_data, (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (48, 56, 65), 2, cv2.LINE_AA)
#                     self.ui.lineEdit_accession.setText(decoded_data)

#                 # Convert the frame to QImage
#                 live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
#                 live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                
#                 # Setup pixmap with the acquired image
#                 live_img_scaled = live_img_pixmap.scaled(cam_id.width(),
#                                                          cam_id.height(),
#                                                          QtCore.Qt.KeepAspectRatio)
#                 # Set the pixmap onto the label
#                 cam_id.setPixmap(live_img_scaled)
#                  # Align the label to center
#                 cam_id.setAlignment(QtCore.Qt.AlignCenter)

#         cam_id.setText("Live view disabled.")

    
#     def update_label_webcam(self, cam_id, progress_callback):
#         # Read the current frame from the video stream
#         while self.label_webcamView:    
#             ret, frame = self.cap_label.read()

#             if ret:
#                 # Update the frame attribute
#                 self.frame = frame

#                 # Convert the frame to RGB format
#                 img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#                 img = cv2.flip(img, -1)

#                 # Convert the frame to QImage
#                 live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
#                 live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                
#                 # Setup pixmap with the acquired image
#                 live_img_scaled = live_img_pixmap.scaled(cam_id.width(),
#                                                          cam_id.height(),
#                                                          QtCore.Qt.KeepAspectRatio)
#                 # Set the pixmap onto the label
#                 cam_id.setPixmap(live_img_scaled)
#                  # Align the label to center
#                 cam_id.setAlignment(QtCore.Qt.AlignCenter)

#         else:
#             cam_id.setText("Live view disabled.")

#         return self.frame
        
        
#     def begin_label_webcam(self, cam_id, button_id):
#         selected_camera = self.ui.comboBox_selectLabelWebcam.currentText()
#         if not self.label_webcamView:
#             if self.selected_barcodecam != selected_camera:
#                 self.log_info("Began label camera live view.")
#                 button_id.setText("Stop Live View")
#                 self.label_webcamView = True
            
#                 worker = Worker(self.update_label_webcam, cam_id)
#                 self.threadpool.start(worker)
#             else:
#                 self.log_info("Selected camera is already in use.")
#         else:
#             button_id.setText("Start live view")
#             self.log_info("Ended label camera live view")
#             self.label_webcamView = False

#     def begin_barcode_webcam(self, cam_id, button_id):
#         selected_camera = self.ui.comboBox_selectBarcodeWebcam.currentText()
#         if not self.barcode_webcamView:
#             if self.selected_labelcam != selected_camera:
#                 self.log_info("Began label camera live view.")
#                 button_id.setText("Stop Live View")
#                 self.barcode_webcamView = True
                
#                 worker = Worker(self.update_barcode_webcam, cam_id)
#                 self.threadpool.start(worker)
#             else:
#                 self.log_info("Selected camera is already in use.")
#         else:
#             button_id.setText("Start live view")
#             self.log_info("Ended label camera live view")
#             self.barcode_webcamView = False

#     def capture_set(self):
#         self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text()).joinpath(self.ui.lineEdit_accession.text())
#         if os.path.exists(self.output_location_folder):
#             self.show_popup()

#         else:
#             self.ui.pushButton_capture.setEnabled(False)
#             self.capture_label_webcam(tag = "_label")
#             self.ui.pushButton_capture.setEnabled(True)
#             # self.begin_barcode_webcam(cam_id = self.ui.barcode_camera, button_id = self.ui.pushButton_barcode_webcam)

#     def show_popup(self):
#         button = QMessageBox.question(self, "RAPIID lite Dialog", "A folder with this accession number already exists!\nDo you want to overwrite the existing file/s?")
#         if button == QMessageBox.Yes:
#             self.popup_button()

#     def popup_button(self):
#         self.ui.pushButton_capture.setEnabled(False)
#         self.capture_label_webcam(tag = "_label")
#         self.ui.pushButton_capture.setEnabled(True)

#     def capture_label_webcam(self, tag):
#         self.create_output_folders()
#         file_name = str(self.output_location_folder.joinpath(self.ui.lineEdit_accession.text() + tag + self.file_format))
#         frame_to_save = self.frame
#         try:
#             cv2.imwrite(file_name, frame_to_save)
#             self.log_info("File " + file_name + " saved successfully.")
#         except:
#             self.log_info("File " + file_name + " was unable to be saved!")

#     def create_output_folders(self):
#         self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text()).joinpath(self.ui.lineEdit_accession.text())
#         if not os.path.exists(self.output_location_folder):
#             os.makedirs(self.output_location_folder)
#             self.log_info("Created folder: " + str(self.ui.lineEdit_taxon.text() + self.ui.lineEdit_accession.text()))

#     def loadConfig(self):
#         file = QtWidgets.QFileDialog.getOpenFileName(self, "Load existing config file", str(Path.cwd()), "config file (*.yaml)")
#         config_location = file[0]
#         if config_location:
#             # if a file has been selected, convert it into a Path object
#             config_location = Path(config_location)
#             config = ymlRW.read_config_file(config_location)

#             return

#             # output path
#             self.output_location = config["general"]["output_folder"]
#             self.ui.display_path.setText(self.output_location)

#             # creator
#             self.ui.lineEdit_creator.setText(config["general"]["creator"])

#             # taxon name
#             self.ui.lineEdit_taxon.setText(config["general"]["taxon_name"])

#             self.loadedConfig = True
#             self.log_info("Loaded config file successfully!")
#             print(config)

#     def writeConfig(self):
#         self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_taxon.text())
#         if not os.path.exists(self.output_location_folder):
#             os.makedirs(self.output_location_folder)
#             self.log_info("Created folder: " + str(self.ui.lineEdit_taxon.text()))

#         config = {'general': {'creator': self.ui.lineEdit_creator.text(),
#                               'taxon_name': self.ui.lineEdit_taxon.text(),
#                               'output_folder': self.output_location,
#                               },
#                   # 'exif_data': self.exif_data
#                   }

#         ymlRW.write_config_file(config, Path(self.output_location_folder))
#         self.log_info("Exported config file successfully!")

#     def get_default_values(self):
#         config = {'general': {'creator': 'new_user',
#                               'taxon_name': 'untitled_taxon',
#                               },
#                       }
#         return config

#     def closeApp(self):
#         sys.exit()

#     def closeEvent(self, event):
#         # report the program is to be closed so threads can be exited
#         self.exit_program = True
#         print("Application Closed!")

# # Initialise the app
# app = QApplication(sys.argv)
# UIWindow = UI()
# apply_stylesheet(app, theme = 'dark_lightgreen.xml')
# app.exec_()