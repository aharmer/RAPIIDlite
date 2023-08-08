import cv2
import numpy as np
import time
from itertools import chain
from PySpin import PySpin  # to run on windows


class customFLIR():

    def __init__(self):

        # Retrieve singleton reference to system object
        self.system = PySpin.System.GetInstance()

        # Get current library version
        version = self.system.GetLibraryVersion()
        print('Spinnaker library version: %d.%d.%d.%d' % (version.major, version.minor, version.type, version.build))

        # Retrieve list of cameras from the system
        self.cam_list = self.system.GetCameras()
        
        # get all serial numbers of connected and support FLIR cameras
        self.device_names = []

        for id, cam in enumerate(self.cam_list):
            nodemap = cam.GetTLDeviceNodeMap()

            # Retrieve device serial number
            node_device_serial_number = PySpin.CStringPtr(nodemap.GetNode("DeviceSerialNumber"))
            node_device_model = PySpin.CStringPtr(nodemap.GetNode("DeviceModelName"))

            if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
                self.device_names.append([node_device_model.GetValue(), node_device_serial_number.GetValue()])

            print("Detected", self.device_names[id][0], "with Serial ID", self.device_names[id][1])


        # serial_0 = '23218621'
        
        self.cam = self.cam_list[0]
        num_cameras = len(self.cam_list)

        print('Number of cameras detected: %d' % num_cameras)

        # Finish if there are no cameras
        if num_cameras == 0:
            # Clear camera list before releasing system
            self.cam_list.Clear()

            # Release system instance
            self.system.ReleaseInstance()

            print('\nNo cameras attached!\nConnect cameras and restart the app.\nApp closed.')

            return None

    def initialise_camera(self, select_cam = 0, exposure = 50000):
        # overwrite the selected cam at initialisation if desired
        self.cam = self.cam_list[select_cam]
        # initialise camera, apply settings and begin acquisition
        # Initialize camera
        self.cam.Init()

        # Set acquisition mode to continuous
        if self.cam.AcquisitionMode.GetAccessMode() != PySpin.RW:
            print('Unable to set acquisition mode to continuous. Aborting...')
            return False

        # always retrieve the newest captured image for the live view
        self.cam.TLStream.StreamBufferHandlingMode.SetValue(PySpin.StreamBufferHandlingMode_NewestOnly)
        self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
        print('Acquisition mode set to continuous...')

        self.set_gain(select_cam, gain = 5)
        self.set_gamma(select_cam, gamma = 0.8)
        self.set_exposure(select_cam, exposure = exposure)

        # Begin Acquisition of image stream
        self.cam.BeginAcquisition()


    def set_exposure(self, select_cam = 0, exposure = 50000):
        self.cam = self.cam_list[select_cam]
        self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
        exposure = min(self.cam.ExposureTime.GetMax(), exposure)
        self.cam.ExposureTime.SetValue(exposure)

    def set_gain(self, select_cam = 0, gain = 5):
        self.cam = self.cam_list[select_cam]
        self.cam.GainAuto.SetValue(PySpin.GainAuto_Off)
        self.cam.Gain.SetValue(gain)

    def set_gamma(self, select_cam = 0, gamma = 0.8):
        self.cam = self.cam_list[select_cam]
        self.cam.Gamma.SetValue(gamma)

    def live_view(self, select_cam = 0):
        self.cam = self.cam_list[select_cam]
        resized = None

        try:

            try:
                # Retrieve next received image and ensure image completion
                image_result = self.cam.GetNextImage()

                if image_result.IsIncomplete():
                    print('Image incomplete with image status %d...' % image_result.GetImageStatus())

                else:
                    # Print image information
                    width = image_result.GetWidth()
                    height = image_result.GetHeight()

                    # convert from FLIR format to OpenCV np array
                    img_conv = image_result.Convert(PySpin.PixelFormat_BGR8, PySpin.HQ_LINEAR)

                    scale_percent = 75  # percent of original size
                    width = int(width * scale_percent / 100)
                    height = int(height * scale_percent / 100)
                    dim = (width, height)
                    
                    # resize image
                    resized = cv2.resize(img_conv.GetNDArray(), dim, interpolation=cv2.INTER_AREA)

                    # Release image
                    image_result.Release()

            except PySpin.SpinnakerException as ex:
                print('Error: %s' % ex)

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)

        return resized

    def capture_image(self, select_cam = 0, img_name = "example.tif", return_image = False):
        self.cam = self.cam_list[select_cam]
        try:
            try:
                # Retrieve next received image and ensure image completion
                image_result = self.cam.GetNextImage()

                if image_result.IsIncomplete():
                    print('Image incomplete with image status %d...' % image_result.GetImageStatus())

                else:
                    # Print image information
                    width = image_result.GetWidth()
                    height = image_result.GetHeight()
                    print('Captured Image with width = %d, height = %d' % (width, height))

                    # Create a unique filename
                    filename = img_name

                    if return_image:
                        return image_result
                    else:
                        # Save RAW image
                        image_result.Save(filename)

                        print('Image saved as %s' % filename)

                # Release image
                image_result.Release()


            except PySpin.SpinnakerException as ex:
                print('Error: %s' % ex)

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)

    def exit_cam(self, select_cam = 0):
        """ ###  End acquisition ### """
        self.cam = self.cam_list[select_cam]
        self.cam.EndAcquisition()
        # Deinitialize camera
        self.cam.DeInit()
        del self.cam

    def releasePySpin(self):
        # Clear camera list before releasing system
        self.cam_list.Clear()
        del self.cam_list

        # Release system instance
        self.system.ReleaseInstance()


if __name__ == '__main__':
    display_for_num_images = 10

    # initialise camera
    FLIR = customFLIR()
    FLIR.initialise_camera(select_cam = 0)

    # custom settings
    gain = 5

    for i in range(display_for_num_images):
        FLIR.set_gain(gain + i * 0.2)

        img = FLIR.live_view()
        # overlay = FLIR.showExposure(img)

        cv2.imshow("Live view", img)

        cv2.waitKey(1)

    FLIR.capture_image(img_name = "testy_mac_test_face.tif")

    # release camera
    FLIR.exit_cam(select_cam = 0)
