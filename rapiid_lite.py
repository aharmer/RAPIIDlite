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
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        `tuple` (exctype, value, traceback.format_exc() )

    result
        `object` data returned from processing, anything

    progress
        `int` indicating % progress

    '''
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(int)


class Worker(QtCore.QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

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
        '''
        Initialise the runner function with passed args, kwargs.
        '''

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

        # start thread pool
        self.threadpool = QtCore.QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        # Set initial camera variables and buttons
        self.liveView = False
        self.camera_type = None
        self.camera_0_model = None
        self.file_format = ".jpg"
        self.webcamView = False

        # Assign camera control features to ui
        self.ui.pushButton_camera_0.pressed.connect(lambda: self.begin_live_view(cam_id = self.ui.camera_0, select_cam = 0, button_id = self.ui.pushButton_camera_0))
        self.ui.spinBox_camera_0_exposure.valueChanged.connect(lambda: self.set_exposure_manual(lab_id = self.ui.camera_0_exposure_label, select_cam = 0, spin_id = self.ui.spinBox_camera_0_exposure))
        self.ui.doubleSpinBox_camera_0_gain.valueChanged.connect(lambda: self.set_gain_manual(lab_id = self.ui.camera_0_gain_label, select_cam = 0, dspin_id = self.ui.doubleSpinBox_camera_0_gain))
        self.ui.doubleSpinBox_camera_0_gamma.valueChanged.connect(lambda: self.set_gamma(lab_id = self.ui.camera_0_gamma_label, select_cam = 0, dspin_id = self.ui.doubleSpinBox_camera_0_gamma))

        self.ui.pushButton_capture.pressed.connect(self.capture_set)

        self.ui.shortcut_capture = QShortcut(QKeySequence('Alt+C'), self)
        self.ui.shortcut_capture.activated.connect(self.capture_set)

        # Initiate webcam
        # self.cap = cv2.VideoCapture(2)
        # self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        # self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.ui.pushButton_camera_1.pressed.connect(lambda: self.begin_webcam(cam_id = self.ui.camera_1, button_id = self.ui.pushButton_camera_1))

        # def returnCameraIndexes():  
        self.index = 0
        self.webcam_arr = []
        while True:
            self.cap = cv2.VideoCapture(self.index)
            try:
                if self.cap.getBackendName() == "MSMF":
                    self.webcam_arr.append("Webcam " + str(self.index))
            except:
                break
            self.cap.release()
            self.index += 1
    
        for webcam in self.webcam_arr:
            self.ui.comboBox_selectWebcam.addItem(webcam)

        self.ui.comboBox_selectWebcam.currentTextChanged.connect(self.select_webcam)

        # Find FLIR cameras, if attached
        try:
            from scripts.rapiid_lite_FLIR import customFLIR
            self.FLIR = customFLIR()

            if len(self.FLIR.cam_list) == 0:
                msg = QMessageBox()
                msg.setWindowTitle("RAPIID Lite Dialog")
                msg.setText("No cameras attached!\nConnect cameras and restart the app.")
                msg.setIcon(QMessageBox.Warning)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec()
                msg.buttonClicked.connect(self.closeApp())

            # camera needs to be initialised before use (self.cam.initialise_camera)
            # all detected FLIR cameras are listed in self.cam.device_names
            # by default, use the first camera found in the list
            # self.cam = self.FLIR
            self.FLIR.initialise_camera(select_cam = 0, exposure = 50000)
            self.log_info("Camera successfully initialised.")
            self.ui.camera_0.setText("Camera successfully initialised.")
            # now retrieve the name of all found FLIR cameras and add them to the camera selection
            for cam in self.FLIR.device_names:
                self.ui.comboBox_selectCamera.addItem(str(cam[0] + " ID: " + cam[1]))
            self.camera_type = "FLIR"
            # cam.device_names contains both model and serial number
            self.camera_0_model = 'Blackfly S BFS-U3-200S6C'
            self.FLIR0_found = True
        except IndexError:
            message0 = "No FLIR camera found!"
            self.log_info(message0)
            print(message0)
            self.FLIR0_found = False
            self.disable_inputs(cam_id = 0)
        except ModuleNotFoundError:
            message = "PYSPIN has not been installed - Disabling FLIR camera inputs"
            self.log_info(message)
            print(message)
            self.disable_inputs(cam_id = 0)
        
        self.ui.comboBox_selectCamera.currentTextChanged.connect(self.select_camera)

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

        self.exif_data = self.config["exif_data"]

        # Show the app
        self.showMaximized()

    def select_camera(self):
        self.disable_inputs(cam_id = 0)
        selected_camera = self.ui.comboBox_selectCamera.currentText()
        self.log_info("Selected camera: " + str(selected_camera))

        # stop the live view if currently in use
        if self.liveView:
            self.begin_live_view()  # sets live view false if already running

        # de-initialised previous FLIR, if it was in use
        if self.camera_type == "FLIR":
            # de-initialise the previous camera before setting up the newly selected one
            self.cam.exit_cam(select_cam = 0)

        # new camera -> FLIR
        if selected_camera.split(" ")[0] == "Blackfly":
            for ID, FLIR in enumerate(self.FLIR.device_names):
                if self.ui.comboBox_selectCamera.currentText() == str(FLIR[0] + " ID: " + FLIR[1]):
                    self.FLIR.initialise_camera(select_cam = ID)
                    self.log_info("Camera in use: " + str(FLIR[0] + " ID: " + FLIR[1]))
                    self.camera_type = "FLIR"
                    self.begin_live_view()
                    self.camera_0_model = self.FLIR.device_names[ID][0]
                    self.enable_inputs(cam_id = 0)
                    self.file_format = ".jpg"

    def select_webcam(self):
        # self.disable_inputs(cam_id = 1)
        selected_camera = self.ui.comboBox_selectWebcam.currentText()
        self.log_info("Selected " + str(selected_camera))

        # stop the webcam if currently in use
        if self.webcamView:
            self.cap.release()

        # Select new webcam
        webcam_id = int(selected_camera.split(" ")[1])
        self.cap = cv2.VideoCapture(webcam_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        # self.enable_inputs(cam_id = 1)
        # self.webcamView = True

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
                  # x1 = x
                  # y1 = y
                  # x2 = x + w
                  # y2 = y + h
                  
                  # x_centre = (x2 - x1)/2 + x1
                  # y_centre = (y2 - y1)/2 + y1
                  
                  # cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 5)
                  # cv2.circle(frame, (int(x_centre), int(y_centre)), 3, (0, 0, 255), 3)
                      
                  # Crop the detected DataMatrix region
                  roi = gray[y - 1:y + h + 1, x - 1:x + w + 1]

                  # Decode the DataMatrix
                  if roi.shape[0] > 0:
                    decoded_data = dmtx.decode(roi)
                    for data in decoded_data:
                        return data.data.decode('utf-8')  # Return the decoded data
                  #   try:
                  #     decoded_data = dmtx.decode(roi)
                  #     for data in decoded_data:
                  #         return data.data.decode('utf-8')  # Return the decoded data
                  # except dmtx.PyLibDMTXError:
                  #     continue

        return None

    def update_webcam(self, cam_id, progress_callback):
        # Read the current frame from the video stream
        while self.webcamView:    
            ret, frame = self.cap.read()

            if ret:
                # Convert the frame to RGB format
                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = cv2.flip(img, -1)
                # h, w, _ = frame.shape
                # scale = 2
                # centerX, centerY = int(h/2),int(w/2)
                # radiusX, radiusY = int(centerX*(1/scale)), int(centerY*(1/scale))

                # minX, maxX = centerX - radiusX, centerX + radiusX
                # minY, maxY = centerY - radiusY, centerY + radiusY

                # crop = img[minX:maxX, minY:maxY]
                # zoom = cv2.resize(crop, (w, h), cv2.INTER_LANCZOS4)

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

    def begin_webcam(self, cam_id, button_id):
        if not self.webcamView:
            self.log_info("Began label camera live view.")
            button_id.setText("Stop Live View")
            self.webcamView = True
            
            worker = Worker(self.update_webcam, cam_id)
            self.threadpool.start(worker)

        else:
            cam_id.setText("Live view disabled.")
            button_id.setText("Start live view")
            self.log_info("Ended label camera live view")
            self.webcamView = False

    def update_live_view(self, cam_id, select_cam, progress_callback):
        while self.liveView and self.camera_type == "FLIR":
            try:
                img = self.FLIR.live_view(select_cam)
                # img = cv2.flip(img, -1)
                # img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

                live_img = QtGui.QImage(img, img.shape[1], img.shape[0], QtGui.QImage.Format_RGB888).rgbSwapped()
                live_img_pixmap = QtGui.QPixmap.fromImage(live_img)

                # Setup pixmap with the acquired image
                live_img_scaled = live_img_pixmap.scaled(cam_id.width(),
                                                         cam_id.height(),
                                                         QtCore.Qt.KeepAspectRatio)
                # Set the pixmap onto the label
                cam_id.setPixmap(live_img_scaled)
                # Align the label to center
                cam_id.setAlignment(QtCore.Qt.AlignCenter)
            except AttributeError:
                print("Live view ended")
        cam_id.setText("Live view disabled.")

    def begin_live_view(self, cam_id, select_cam, button_id):
        if not self.liveView:
            self.log_info("Began camera live view.")
            button_id.setText("Stop Live View")
            self.liveView = True
            
            worker = Worker(self.update_live_view, cam_id, select_cam)
            self.threadpool.start(worker)

        else:
            cam_id.setText("Live view disabled.")
            button_id.setText("Start live view")
            self.log_info("Ended camera live view")
            self.liveView = False

    def set_exposure_manual(self, lab_id, select_cam, spin_id):
        lab_id.setEnabled(True)
        spin_id.setEnabled(True)
        value = spin_id.value()
        if value is not None:
            self.log_info("Exposure time set to " + str(value) + " [us]")
            self.FLIR.set_exposure(select_cam, exposure = float(value))

    def set_gain_manual(self, lab_id, select_cam, dspin_id):
        lab_id.setEnabled(True)
        dspin_id.setEnabled(True)
        value = dspin_id.value()
        if value is not None:
            self.log_info("Gain level set to " + str(value) + " [dB]")
            self.FLIR.set_gain(select_cam, gain = float(value))

    def set_gamma(self, lab_id, select_cam, dspin_id):
        lab_id.setEnabled(True)
        dspin_id.setEnabled(True)
        value = dspin_id.value()
        if value is not None:
            self.log_info("Gamma set to " + str(value))
            self.FLIR.set_gamma(select_cam, gamma = float(value))

    def capture_set(self):
        self.output_location_folder = Path(self.output_location).joinpath(self.ui.lineEdit_project.text()).joinpath(self.ui.lineEdit_accession.text())
        if os.path.exists(self.output_location_folder):
            self.show_popup()

        else:
            self.ui.pushButton_capture.setEnabled(False)
            if self.FLIR0_found:
                self.capture_image(select_cam = 0, tag = "_label")
            self.ui.pushButton_capture.setEnabled(True)

    def show_popup(self):
        button = QMessageBox.question(self, "RAPIID lite Dialog", "A folder with this accession number already exists!\nDo you want to overwrite the existing file/s?")
        if button == QMessageBox.Yes:
            self.popup_button()

    def popup_button(self):
        self.ui.pushButton_capture.setEnabled(False)
        if self.FLIR0_found:
            self.capture_image(select_cam = 0, tag = "_label")
        self.ui.pushButton_capture.setEnabled(True)

    def capture_image(self, select_cam, tag):
        # now = datetime.datetime.now()
        self.create_output_folders()
        file_name = str(self.output_location_folder.joinpath(self.ui.lineEdit_accession.text() + tag + self.file_format))
        self.FLIR.capture_image(select_cam, img_name = file_name)
        self.log_info("Captured " + str(self.ui.lineEdit_accession.text() + tag + self.file_format))

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

            # check if the camera type in the config file matches the connected/selected camera type
            if config["general"]["camera_type"] != self.camera_type:
                self.log_warning("The selected config file was generated for a different camera type!")
                QtWidgets.QMessageBox.critical(self, "Failed to load " + str(config_location.name), "The selected config file was generated for a different camera type!")
                return

            # output path
            self.output_location = config["general"]["output_folder"]
            self.ui.display_path.setText(self.output_location)

            # project name
            self.ui.lineEdit_project.setText(config["general"]["project_name"])

            # camera_settings:
            if config["general"]["camera_type"] == "FLIR":
                self.ui.spinBox_camera_0_exposure.setValue(config["camera_settings"]["camera_0"]["exposure_time"])
                self.ui.doubleSpinBox_camera_0_gain.setValue(config["camera_settings"]["camera_0"]["gain_level"])
                self.ui.doubleSpinBox_camera_0_gamma.setValue(config["camera_settings"]["camera_0"]["gamma"])

            # meta data (exif)
            self.exif_camera_0 = config["exif_data"]["camera_0"]

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
                              'camera_type': self.camera_type,
                              'camera_0_model': self.camera_0_model,
                              },
                  'camera_settings': {'camera_0': {'exposure_time': self.ui.spinBox_camera_0_exposure.value(),
                                                  'gain_level': self.ui.doubleSpinBox_camera_0_gain.value(),
                                                  'gamma': self.ui.doubleSpinBox_camera_0_gamma.value(),
                                                  },    
                                      },
                  'exif_data': self.exif_data
                  }

        ymlRW.write_config_file(config, Path(self.output_location_folder))
        self.log_info("Exported config file successfully!")

    def get_default_values(self):
        # WARNING! THESE SETTINGS ARE SPECIFIC TO THE CAMERA USED DURING DEVELOPMENT
        # AND WILL LIKELY NOT APPLY TO YOUR SETUP
        config = {'general': {'project_name': 'untitled_project'},
                       'exif_data': {'camera_0': {'Make': 'FLIR',
                                                  'Model': 'BFS-U3-200S6C-C',
                                                  'SerialNumber': '21188171',
                                                  'Lens': 'MPZ',
                                                  'CameraSerialNumber': '21188171',
                                                  'LensManufacturer': 'Computar',
                                                  'LensModel': '75.0 f / 3.1',
                                                  'FocalLength': '75.0',
                                                  'FocalLengthIn35mmFormat': '203.0'},
                                    }
                      }
        return config

    
    def disable_inputs(self, cam_id):
        self.ui.pushButton_camera_+cam_id.setEnabled(False)
        self.ui.spinBox_camera_+cam_id+_exposure.setEnabled(False)
        self.ui.doubleSpinBox_camera_+cam_id+_gain.setEnabled(False)
        self.ui.doubleSpinBox_camera_+cam_id+_gamma.setEnabled(False)
        self.ui.pushButton_capture.setEnabled(False)
        self.ui.pushButton_outputFolder.setEnabled(False)
        self.ui.pushButton_load_config.setEnabled(False)

    def enable_inputs(self, cam_id):
        self.ui.pushButton_camera_+cam_id.setEnabled(True)
        self.ui.spinBox_camera_+cam_id+_exposure.setEnabled(True)
        self.ui.doubleSpinBox_camera_+cam_id+_gain.setEnabled(True)
        self.ui.doubleSpinBox_camera_+cam_id+_gamma.setEnabled(True)
        self.ui.pushButton_capture.setEnabled(True)
        self.ui.pushButton_outputFolder.setEnabled(True)
        self.ui.pushButton_load_config.setEnabled(True)

    def closeApp(self):
        self.FLIR0_found = False
        sys.exit()

    def closeEvent(self, event):
        # report the program is to be closed so threads can be exited
        self.exit_program = True

        # stop the live view if currently in use
        if self.liveView:
            self.begin_live_view(cam_id = self.ui.camera_0, select_cam = 0, button_id = self.ui.pushButton_camera_0)  # sets live view false if already running

        # release cameras
        if self.FLIR0_found:
            self.FLIR.exit_cam(0)
        
        self.FLIR.releasePySpin()

        print("Application Closed!")

# Initialise the app
app = QApplication(sys.argv)
UIWindow = UI()
apply_stylesheet(app, theme = 'dark_lightgreen.xml')
app.exec_()