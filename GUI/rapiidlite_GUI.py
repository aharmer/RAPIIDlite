# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'C:\\Users\\HarmerA\\OneDrive - MWLR\\repos\\RAPIIDlite\\GUI\\rapiidlite_GUI.ui'
#
# Created by: PyQt5 UI code generator 5.15.7
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1865, 1087)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout(self.centralwidget)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.scrollArea = QtWidgets.QScrollArea(self.centralwidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollAreaWidgetContents = QtWidgets.QWidget()
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 1851, 1073))
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.horizontalLayout_9 = QtWidgets.QHBoxLayout(self.scrollAreaWidgetContents)
        self.horizontalLayout_9.setObjectName("horizontalLayout_9")
        self.horizontalWidget = QtWidgets.QWidget(self.scrollAreaWidgetContents)
        self.horizontalWidget.setObjectName("horizontalWidget")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.horizontalWidget)
        self.horizontalLayout_2.setContentsMargins(10, 10, 10, 10)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.camera_0_label = QtWidgets.QLabel(self.horizontalWidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.camera_0_label.sizePolicy().hasHeightForWidth())
        self.camera_0_label.setSizePolicy(sizePolicy)
        self.camera_0_label.setMaximumSize(QtCore.QSize(16777215, 25))
        font = QtGui.QFont()
        font.setPointSize(10)
        font.setBold(True)
        font.setWeight(75)
        self.camera_0_label.setFont(font)
        self.camera_0_label.setAlignment(QtCore.Qt.AlignBottom|QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft)
        self.camera_0_label.setObjectName("camera_0_label")
        self.verticalLayout.addWidget(self.camera_0_label)
        self.camera_0 = QtWidgets.QLabel(self.horizontalWidget)
        self.camera_0.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.camera_0.sizePolicy().hasHeightForWidth())
        self.camera_0.setSizePolicy(sizePolicy)
        self.camera_0.setMinimumSize(QtCore.QSize(800, 600))
        self.camera_0.setMaximumSize(QtCore.QSize(800, 600))
        self.camera_0.setStyleSheet("QFrame, QLabel, QToolTip {\n"
"    border: 2px solid #8BC34A;\n"
"    border-radius: 4px;\n"
"    padding: 2px;\n"
"}")
        self.camera_0.setFrameShape(QtWidgets.QFrame.Box)
        self.camera_0.setText("")
        self.camera_0.setScaledContents(True)
        self.camera_0.setAlignment(QtCore.Qt.AlignCenter)
        self.camera_0.setObjectName("camera_0")
        self.verticalLayout.addWidget(self.camera_0)
        self.horizontalLayout_0 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_0.setObjectName("horizontalLayout_0")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.label_selectCamera = QtWidgets.QLabel(self.horizontalWidget)
        self.label_selectCamera.setObjectName("label_selectCamera")
        self.verticalLayout_2.addWidget(self.label_selectCamera)
        self.comboBox_selectCamera = QtWidgets.QComboBox(self.horizontalWidget)
        self.comboBox_selectCamera.setObjectName("comboBox_selectCamera")
        self.verticalLayout_2.addWidget(self.comboBox_selectCamera)
        self.horizontalLayout_0.addLayout(self.verticalLayout_2)
        self.verticalLayout_5 = QtWidgets.QVBoxLayout()
        self.verticalLayout_5.setContentsMargins(-1, -1, 5, -1)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.camera_0_exposure_label = QtWidgets.QLabel(self.horizontalWidget)
        self.camera_0_exposure_label.setObjectName("camera_0_exposure_label")
        self.verticalLayout_5.addWidget(self.camera_0_exposure_label)
        self.spinBox_camera_0_exposure = QtWidgets.QSpinBox(self.horizontalWidget)
        self.spinBox_camera_0_exposure.setButtonSymbols(QtWidgets.QAbstractSpinBox.UpDownArrows)
        self.spinBox_camera_0_exposure.setKeyboardTracking(False)
        self.spinBox_camera_0_exposure.setMinimum(1000)
        self.spinBox_camera_0_exposure.setMaximum(1000000)
        self.spinBox_camera_0_exposure.setSingleStep(10000)
        self.spinBox_camera_0_exposure.setProperty("value", 300000)
        self.spinBox_camera_0_exposure.setObjectName("spinBox_camera_0_exposure")
        self.verticalLayout_5.addWidget(self.spinBox_camera_0_exposure)
        self.horizontalLayout_0.addLayout(self.verticalLayout_5)
        self.verticalLayout_8 = QtWidgets.QVBoxLayout()
        self.verticalLayout_8.setContentsMargins(-1, -1, 5, -1)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.camera_0_gain_label = QtWidgets.QLabel(self.horizontalWidget)
        self.camera_0_gain_label.setObjectName("camera_0_gain_label")
        self.verticalLayout_8.addWidget(self.camera_0_gain_label)
        self.doubleSpinBox_camera_0_gain = QtWidgets.QDoubleSpinBox(self.horizontalWidget)
        self.doubleSpinBox_camera_0_gain.setKeyboardTracking(False)
        self.doubleSpinBox_camera_0_gain.setMaximum(25.0)
        self.doubleSpinBox_camera_0_gain.setProperty("value", 5.0)
        self.doubleSpinBox_camera_0_gain.setObjectName("doubleSpinBox_camera_0_gain")
        self.verticalLayout_8.addWidget(self.doubleSpinBox_camera_0_gain)
        self.horizontalLayout_0.addLayout(self.verticalLayout_8)
        self.verticalLayout_9 = QtWidgets.QVBoxLayout()
        self.verticalLayout_9.setObjectName("verticalLayout_9")
        self.camera_0_gamma_label = QtWidgets.QLabel(self.horizontalWidget)
        self.camera_0_gamma_label.setObjectName("camera_0_gamma_label")
        self.verticalLayout_9.addWidget(self.camera_0_gamma_label)
        self.doubleSpinBox_camera_0_gamma = QtWidgets.QDoubleSpinBox(self.horizontalWidget)
        self.doubleSpinBox_camera_0_gamma.setKeyboardTracking(False)
        self.doubleSpinBox_camera_0_gamma.setMinimum(0.1)
        self.doubleSpinBox_camera_0_gamma.setMaximum(4.0)
        self.doubleSpinBox_camera_0_gamma.setSingleStep(0.1)
        self.doubleSpinBox_camera_0_gamma.setProperty("value", 0.8)
        self.doubleSpinBox_camera_0_gamma.setObjectName("doubleSpinBox_camera_0_gamma")
        self.verticalLayout_9.addWidget(self.doubleSpinBox_camera_0_gamma)
        self.horizontalLayout_0.addLayout(self.verticalLayout_9)
        self.pushButton_camera_0 = QtWidgets.QPushButton(self.horizontalWidget)
        self.pushButton_camera_0.setObjectName("pushButton_camera_0")
        self.horizontalLayout_0.addWidget(self.pushButton_camera_0, 0, QtCore.Qt.AlignBottom)
        self.verticalLayout.addLayout(self.horizontalLayout_0)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.horizontalLayout_2.addLayout(self.verticalLayout)
        self.verticalLayout_3 = QtWidgets.QVBoxLayout()
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.preview_label = QtWidgets.QLabel(self.horizontalWidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.preview_label.sizePolicy().hasHeightForWidth())
        self.preview_label.setSizePolicy(sizePolicy)
        self.preview_label.setMaximumSize(QtCore.QSize(16777215, 25))
        font = QtGui.QFont()
        font.setPointSize(10)
        font.setBold(True)
        font.setWeight(75)
        self.preview_label.setFont(font)
        self.preview_label.setAlignment(QtCore.Qt.AlignBottom|QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft)
        self.preview_label.setObjectName("preview_label")
        self.verticalLayout_3.addWidget(self.preview_label)
        self.preview = QtWidgets.QLabel(self.horizontalWidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.preview.sizePolicy().hasHeightForWidth())
        self.preview.setSizePolicy(sizePolicy)
        self.preview.setMinimumSize(QtCore.QSize(800, 600))
        self.preview.setMaximumSize(QtCore.QSize(800, 600))
        self.preview.setStyleSheet("QFrame, QLabel, QToolTip {\n"
"    border: 2px solid #8BC34A;\n"
"    border-radius: 4px;\n"
"    padding: 2px;\n"
"}")
        self.preview.setFrameShape(QtWidgets.QFrame.Box)
        self.preview.setText("")
        self.preview.setScaledContents(True)
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setObjectName("preview")
        self.verticalLayout_3.addWidget(self.preview)
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout_3.addItem(spacerItem1)
        self.horizontalLayout_2.addLayout(self.verticalLayout_3)
        self.verticalWidget_4 = QtWidgets.QWidget(self.horizontalWidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.verticalWidget_4.sizePolicy().hasHeightForWidth())
        self.verticalWidget_4.setSizePolicy(sizePolicy)
        self.verticalWidget_4.setMinimumSize(QtCore.QSize(200, 0))
        self.verticalWidget_4.setMaximumSize(QtCore.QSize(200, 16777215))
        self.verticalWidget_4.setObjectName("verticalWidget_4")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.verticalWidget_4)
        self.verticalLayout_4.setSizeConstraint(QtWidgets.QLayout.SetDefaultConstraint)
        self.verticalLayout_4.setContentsMargins(5, 5, 5, -1)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.pushButton_load_config = QtWidgets.QPushButton(self.verticalWidget_4)
        self.pushButton_load_config.setObjectName("pushButton_load_config")
        self.verticalLayout_4.addWidget(self.pushButton_load_config)
        self.pushButton_writeConfig = QtWidgets.QPushButton(self.verticalWidget_4)
        self.pushButton_writeConfig.setObjectName("pushButton_writeConfig")
        self.verticalLayout_4.addWidget(self.pushButton_writeConfig)
        spacerItem2 = QtWidgets.QSpacerItem(20, 50, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        self.verticalLayout_4.addItem(spacerItem2)
        self.pushButton_outputFolder = QtWidgets.QPushButton(self.verticalWidget_4)
        self.pushButton_outputFolder.setObjectName("pushButton_outputFolder")
        self.verticalLayout_4.addWidget(self.pushButton_outputFolder)
        self.display_path = QtWidgets.QLabel(self.verticalWidget_4)
        self.display_path.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.display_path.setFrameShadow(QtWidgets.QFrame.Plain)
        self.display_path.setWordWrap(True)
        self.display_path.setObjectName("display_path")
        self.verticalLayout_4.addWidget(self.display_path)
        spacerItem3 = QtWidgets.QSpacerItem(20, 5, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        self.verticalLayout_4.addItem(spacerItem3)
        self.label_project = QtWidgets.QLabel(self.verticalWidget_4)
        font = QtGui.QFont()
        font.setPointSize(10)
        font.setBold(True)
        font.setWeight(75)
        self.label_project.setFont(font)
        self.label_project.setObjectName("label_project")
        self.verticalLayout_4.addWidget(self.label_project)
        self.lineEdit_project = QtWidgets.QLineEdit(self.verticalWidget_4)
        self.lineEdit_project.setObjectName("lineEdit_project")
        self.verticalLayout_4.addWidget(self.lineEdit_project)
        self.label_accession = QtWidgets.QLabel(self.verticalWidget_4)
        self.label_accession.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_accession.sizePolicy().hasHeightForWidth())
        self.label_accession.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setPointSize(10)
        font.setBold(True)
        font.setWeight(75)
        self.label_accession.setFont(font)
        self.label_accession.setAlignment(QtCore.Qt.AlignBottom|QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft)
        self.label_accession.setObjectName("label_accession")
        self.verticalLayout_4.addWidget(self.label_accession)
        self.lineEdit_accession = QtWidgets.QLineEdit(self.verticalWidget_4)
        self.lineEdit_accession.setObjectName("lineEdit_accession")
        self.verticalLayout_4.addWidget(self.lineEdit_accession)
        spacerItem4 = QtWidgets.QSpacerItem(20, 50, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        self.verticalLayout_4.addItem(spacerItem4)
        self.pushButton_capture = QtWidgets.QPushButton(self.verticalWidget_4)
        font = QtGui.QFont()
        font.setPointSize(10)
        font.setBold(True)
        font.setWeight(75)
        self.pushButton_capture.setFont(font)
        self.pushButton_capture.setObjectName("pushButton_capture")
        self.verticalLayout_4.addWidget(self.pushButton_capture)
        spacerItem5 = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout_4.addItem(spacerItem5)
        self.label_log = QtWidgets.QLabel(self.verticalWidget_4)
        self.label_log.setObjectName("label_log")
        self.verticalLayout_4.addWidget(self.label_log)
        self.listWidget_log = QtWidgets.QListWidget(self.verticalWidget_4)
        self.listWidget_log.setMinimumSize(QtCore.QSize(0, 300))
        self.listWidget_log.setMaximumSize(QtCore.QSize(1000, 400))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.listWidget_log.setFont(font)
        self.listWidget_log.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.listWidget_log.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.listWidget_log.setProperty("isWrapping", False)
        self.listWidget_log.setWordWrap(True)
        self.listWidget_log.setObjectName("listWidget_log")
        self.verticalLayout_4.addWidget(self.listWidget_log)
        self.horizontalLayout_2.addWidget(self.verticalWidget_4)
        self.horizontalLayout_9.addWidget(self.horizontalWidget)
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.horizontalLayout_3.addWidget(self.scrollArea)
        MainWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "RAPIID v1.0"))
        self.camera_0_label.setText(_translate("MainWindow", "Live View"))
        self.label_selectCamera.setText(_translate("MainWindow", "Select camera"))
        self.camera_0_exposure_label.setText(_translate("MainWindow", "Exposure time (us)"))
        self.camera_0_gain_label.setText(_translate("MainWindow", "Gain level (dB)"))
        self.camera_0_gamma_label.setText(_translate("MainWindow", "Gamma correction"))
        self.pushButton_camera_0.setText(_translate("MainWindow", "Start live view"))
        self.preview_label.setText(_translate("MainWindow", "Capture Preview"))
        self.pushButton_load_config.setText(_translate("MainWindow", "Load config file..."))
        self.pushButton_writeConfig.setText(_translate("MainWindow", "Save config file..."))
        self.pushButton_outputFolder.setText(_translate("MainWindow", "Output folder..."))
        self.display_path.setText(_translate("MainWindow", "Path"))
        self.label_project.setText(_translate("MainWindow", "Project name"))
        self.label_accession.setText(_translate("MainWindow", "NZAC accession no."))
        self.pushButton_capture.setText(_translate("MainWindow", "Capture image set"))
        self.label_log.setText(_translate("MainWindow", "Log"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
