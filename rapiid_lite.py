import sys
import os
from pathlib import Path
import datetime
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from GUI.rapiidlite_GUI import Ui_MainWindow  # importing main window of the GUI
import scripts.ymlRW as ymlRW
import cv2
import pylibdmtx.pylibdmtx as dmtx
from qt_material import apply_stylesheet


class WorkerSignals(QtCore.QObject):
    
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(int)


class Worker(QtCore.QRunnable):

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to kwargs
        self.kwargs['progress_callback'] = self.signals.progress

    @QtCore.pyqtSlot()
    def run(self):
        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class UI(QMainWindow):
    def __init__(self):
        super(UI, self).__init__()

        self.setWindowIcon(QtGui.QIcon(str(Path.cwd().joinpath("images", "RAPIIDlite_icon.png"))))

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

        # # Assign camera control features to ui
        self.ui.pushButton_capture.pressed.connect(self.capture_set)

        self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
        self.ui.shortcut_capture.activated.connect(self.capture_set)

        # Initiate webcam
        self.ui.pushButton_label_webcam.pressed.connect(lambda: self.begin_label_webcam(cam_id = self.ui.label_camera, button_id = self.ui.pushButton_label_webcam))
        self.ui.pushButton_barcode_webcam.pressed.connect(lambda: self.begin_barcode_webcam(cam_id = self.ui.barcode_camera, button_id = self.ui.pushButton_barcode_webcam))

        # List webcams for label camera  
        self.index_label = 0
        self.webcam_arr_label = []
        while True:
            self.cap_label = cv2.VideoCapture(self.index_label)
            try:
                if self.cap_label.getBackendName() == "MSMF":
                    self.webcam_arr_label.append("Webcam " + str(self.index_label))
            except:
                break
            self.cap_label.release()
            self.index_label += 1
    
        for webcam in self.webcam_arr_label:
            self.ui.comboBox_selectLabelWebcam.addItem(webcam)
        self.ui.comboBox_selectLabelWebcam.setCurrentIndex(0)

        # List webcams for barcode camera  
        self.index_barcode = 0
        self.webcam_arr_barcode = []
        while True:
            self.cap_barcode = cv2.VideoCapture(self.index_barcode)
            try:
                if self.cap_barcode.getBackendName() == "MSMF":
                    self.webcam_arr_barcode.append("Webcam " + str(self.index_barcode))
            except:
                break
            self.cap_barcode.release()
            self.index_barcode += 1
    
        for webcam in self.webcam_arr_barcode:
            self.ui.comboBox_selectBarcodeWebcam.addItem(webcam)
        self.ui.comboBox_selectBarcodeWebcam.setCurrentIndex(1)

        self.ui.comboBox_selectLabelWebcam.currentTextChanged.connect(self.select_label_webcam)
        self.ui.comboBox_selectBarcodeWebcam.currentTextChanged.connect(self.select_barcode_webcam)

        self.select_label_webcam()
        self.select_barcode_webcam()

        # Select output folder
        self.output_location = str(Path.home())
        self.update_output_location()
        self.ui.pushButton_outputFolder.pressed.connect(self.set_output_location)
        self.output_location_folder = Path(self.output_location)

        # Config file
        self.config = self.get_default_values()
        self.ui.lineEdit_project.setText(self.config["general"]["project_name"])
        self.loadedConfig = False
        self.ui.pushButton_load_config.pressed.connect(self.loadConfig)
        self.ui.pushButton_writeConfig.pressed.connect(self.writeConfig)

        # Show the app
        self.showMaximized()

    def select_label_webcam(self):
        selected_camera = self.ui.comboBox_selectLabelWebcam.currentText()

        # stop the webcam if currently in use
        if self.label_webcamView:
            self.cap_label.release()

        # Select new webcam
        webcam_id = int(selected_camera.split(" ")[1])
        self.cap_label = cv2.VideoCapture(webcam_id)
        self.cap_label.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap_label.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.selected_labelcam = selected_camera
        self.log_info("Selected " + str(selected_camera))

    def select_barcode_webcam(self):
        selected_camera = self.ui.comboBox_selectBarcodeWebcam.currentText()

        # stop the webcam if currently in use
        if self.barcode_webcamView:
            self.cap_barcode.release()

        # Select new webcam
        webcam_id = int(selected_camera.split(" ")[1])
        self.cap_barcode = cv2.VideoCapture(webcam_id)
        self.cap_barcode.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap_barcode.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.selected_barcodecam = selected_camera
        self.log_info("Selected " + str(selected_camera))

    def set_output_location(self):
        new_location = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder...", str(Path.cwd()))
                
        if new_location:
            self.output_location = new_location
            self.log_info("Output location updated.")

        self.update_output_location()

    def update_output_location(self):
        self.ui.display_path.setText(self.output_location)

    def log_info(self, info):
        now = datetime.datetime.now()
        self.ui.listWidget_log.addItem(now.strftime("%H:%M:%S") + " " + info)
        self.ui.listWidget_log.sortItems(QtCore.Qt.DescendingOrder)

    def decode_datamatrix(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3,3), 0)
        _, threshold = cv2.threshold(blur, 50, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7,7))
        closing = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closing, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            if cv2.contourArea(contour) > 1000:  # Adjust the threshold based on your needs
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = float(w) / h

                # Check if the aspect ratio is close to 1 (square shape)
                if 0.8 <= aspect_ratio <= 1.2:
                  
                  # Crop the detected DataMatrix region
                  roi = gray[y - 1:y + h + 1, x - 1:x + w + 1]

                  # Decode the DataMatrix
                  if roi is not None and roi.size > 0:
                    decoded_data = dmtx.decode(roi)
                    for data in decoded_data:
                        return data.data.decode('utf-8')  # Return the decoded data
            #       else:
            #         break
            #     else:
            #         break
            # else:
            #     break

        return None

    def update_barcode_webcam(self, cam_id, progress_callback):
        # Read the current frame from the video stream
        while self.barcode_webcamView:    
            ret, frame = self.cap_barcode.read()

            if ret:
                # Convert the frame to RGB format
                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = cv2.flip(img, -1)
                
                decoded_data = self.decode_datamatrix(frame)

                if decoded_data:
                    cv2.putText(img, "Decoded data: " + decoded_data, (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (48, 56, 65), 2, cv2.LINE_AA)
                    self.ui.lineEdit_accession.setText(decoded_data)

                # Convert the frame to QImage
                live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
                live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                
                # Setup pixmap with the acquired image
                live_img_scaled = live_img_pixmap.scaled(cam_id.width(),
                                                         cam_id.height(),
                                                         QtCore.Qt.KeepAspectRatio)
                # Set the pixmap onto the label
                cam_id.setPixmap(live_img_scaled)
                 # Align the label to center
                cam_id.setAlignment(QtCore.Qt.AlignCenter)

        cam_id.setText("Live view disabled.")

    
    def update_label_webcam(self, cam_id, progress_callback):
        # Read the current frame from the video stream
        while self.label_webcamView:    
            ret, frame = self.cap_label.read()

            if ret:
                # Update the frame attribute
                self.frame = frame

                # Convert the frame to RGB format
                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = cv2.flip(img, -1)

                # Convert the frame to QImage
                live_img = QImage(img, img.shape[1], img.shape[0], QImage.Format_RGB888)
                live_img_pixmap = QtGui.QPixmap.fromImage(live_img)
                
                # Setup pixmap with the acquired image
                live_img_scaled = live_img_pixmap.scaled(cam_id.width(),
                                                         cam_id.height(),
                                                         QtCore.Qt.KeepAspectRatio)
                # Set the pixmap onto the label
                cam_id.setPixmap(live_img_scaled)
                 # Align the label to center
                cam_id.setAlignment(QtCore.Qt.AlignCenter)

        else:
            cam_id.setText("Live view disabled.")

        return self.frame
        
        
    def begin_label_webcam(self, cam_id, button_id):
        selected_camera = self.ui.comboBox_selectLabelWebcam.currentText()
        if not self.label_webcamView:
            if self.selected_barcodecam != selected_camera:
                self.log_info("Began label camera live view.")
                button_id.setText("Stop Live View")
                self.label_webcamView = True
            
                worker = Worker(self.update_label_webcam, cam_id)
                self.threadpool.start(worker)
            else:
                self.log_info("Selected camera is already in use.")
        else:
            button_id.setText("Start live view")
            self.log_info("Ended label camera live view")
            self.label_webcamView = False

    def begin_barcode_webcam(self, cam_id, button_id):
        selected_camera = self.ui.comboBox_selectBarcodeWebcam.currentText()
        if not self.barcode_webcamView:
            if self.selected_labelcam != selected_camera:
                self.log_info("Began label camera live view.")
                button_id.setText("Stop Live View")
                self.barcode_webcamView = True
                
                worker = Worker(self.update_barcode_webcam, cam_id)
                self.threadpool.start(worker)
            else:
                self.log_info("Selected camera is already in use.")
        else:
            button_id.setText("Start live view")
            self.log_info("Ended label camera live view")
            self.barcode_webcamView = False

    def capture_set(self):
        self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_project.text()).joinpath(self.ui.lineEdit_accession.text())
        if os.path.exists(self.output_location_folder):
            self.show_popup()

        else:
            self.ui.pushButton_capture.setEnabled(False)
            self.capture_label_webcam(tag = "_label")
            self.ui.pushButton_capture.setEnabled(True)
            # self.begin_barcode_webcam(cam_id = self.ui.barcode_camera, button_id = self.ui.pushButton_barcode_webcam)

    def show_popup(self):
        button = QMessageBox.question(self, "RAPIID lite Dialog", "A folder with this accession number already exists!\nDo you want to overwrite the existing file/s?")
        if button == QMessageBox.Yes:
            self.popup_button()

    def popup_button(self):
        self.ui.pushButton_capture.setEnabled(False)
        self.capture_label_webcam(tag = "_label")
        self.ui.pushButton_capture.setEnabled(True)

    def capture_label_webcam(self, tag):
        self.create_output_folders()
        file_name = str(self.output_location_folder.joinpath(self.ui.lineEdit_accession.text() + tag + self.file_format))
        frame_to_save = self.frame
        try:
            cv2.imwrite(file_name, frame_to_save)
            self.log_info("File " + file_name + " saved successfully.")
        except:
            self.log_info("File " + file_name + " was unable to be saved!")

    def create_output_folders(self):
        self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_project.text()).joinpath(self.ui.lineEdit_accession.text())
        if not os.path.exists(self.output_location_folder):
            os.makedirs(self.output_location_folder)
            self.log_info("Created folder: " + str(self.ui.lineEdit_project.text() + self.ui.lineEdit_accession.text()))

    def loadConfig(self):
        file = QtWidgets.QFileDialog.getOpenFileName(self, "Load existing config file", str(Path.cwd()), "config file (*.yaml)")
        config_location = file[0]
        if config_location:
            # if a file has been selected, convert it into a Path object
            config_location = Path(config_location)
            config = ymlRW.read_config_file(config_location)

            return

            # output path
            self.output_location = config["general"]["output_folder"]
            self.ui.display_path.setText(self.output_location)

            # project name
            self.ui.lineEdit_project.setText(config["general"]["project_name"])

            self.loadedConfig = True
            self.log_info("Loaded config file successfully!")
            print(config)

    def writeConfig(self):
        self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_project.text())
        if not os.path.exists(self.output_location_folder):
            os.makedirs(self.output_location_folder)
            self.log_info("Created folder: " + str(self.ui.lineEdit_project.text()))

        config = {'general': {'project_name': self.ui.lineEdit_project.text(),
                              'output_folder': self.output_location,
                              },
                  # 'exif_data': self.exif_data
                  }

        ymlRW.write_config_file(config, Path(self.output_location_folder))
        self.log_info("Exported config file successfully!")

    def get_default_values(self):
        config = {'general': {'project_name': 'untitled_project'},
                      }
        return config

    def closeApp(self):
        sys.exit()

    def closeEvent(self, event):
        # report the program is to be closed so threads can be exited
        self.exit_program = True
        print("Application Closed!")

# Initialise the app
app = QApplication(sys.argv)
UIWindow = UI()
apply_stylesheet(app, theme = 'dark_lightgreen.xml')
app.exec_()