# https://cx-freeze.readthedocs.io/en/latest/distutils.html
# Make sure cx_Freeze is installed - 'pip install cx_Freeze'
# Run 'python setup.py build' to create a compiled directory
# OR run 'python setup.py bdist_msi' to create a single msi installer file
import os
import sys
import pylibdmtx
from cx_Freeze import setup, Executable

icon_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images', 'RAPIIDlite_icon.ico')

includes = []

# Explicitly include the native libdmtx DLLs bundled with pylibdmtx.
# cx_Freeze does not detect these automatically because they are loaded
# at runtime via ctypes rather than a normal Python import.
pylibdmtx_dir = os.path.dirname(pylibdmtx.__file__)
dmtx_dlls = [
    (os.path.join(pylibdmtx_dir, f), f)
    for f in os.listdir(pylibdmtx_dir)
    if f.endswith('.dll')
]

# Include your files and folders
includefiles = ['GUI/', 'images/', 'scripts/', 'config.yaml'] + dmtx_dlls

# Exclude unnecessary packages
excludes = ['cx_Freeze', 'setuptools', 'tkinter']

base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name='RAPIIDlite',
    version='3.2',
    description='RAked Pinned Insect Imaging Device (Lite)',
    author='A.M.T. Harmer',
    author_email='harmera@landcareresearch.co.nz',
    options={
        'build_exe': {
            'includes': includes,
            'excludes': excludes,
            'include_files': includefiles
        },
        'bdist_msi': {
            'add_to_path': False,
            'initial_target_dir': r'[ProgramFilesFolder]\RAPIIDlite',
            'install_icon': 'images/RAPIIDlite_icon.ico',
        }
    },
    executables=[
        Executable(
            'rapiid_lite.py',
            base=base,
            icon=icon_file,
            shortcut_name='RAPIIDlite',
            shortcut_dir='DesktopFolder'
        ),
        Executable(
            'rapiid_lite.py',
            base=base,
            icon=icon_file,
            shortcut_name='RAPIIDlite',
            shortcut_dir='ProgramMenuFolder'
        ),
    ]
)