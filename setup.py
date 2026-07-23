# https://cx-freeze.readthedocs.io/en/latest/distutils.html
# Make sure cx_Freeze is installed - 'pip install cx_Freeze'
# Run 'python setup.py build' to create a compiled directory
# OR run 'python setup.py bdist_msi' to create a single msi installer file
import os
import sys
import pylibdmtx
from cx_Freeze import setup, Executable

icon_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images', 'RAPIID_icon.ico')

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

# In conda builds, python38.dll links against zlib.dll dynamically. cx_Freeze
# places zlib.dll under lib/, where the Windows loader will not find it: it
# searches the executable's own directory, not lib/. The app therefore starts
# fine on a dev machine (conda is on PATH) but fails on a clean install with
# "zlib.dll was not found". Ship it next to the executable instead.
zlib_dll = next(
    (p for p in (os.path.join(sys.prefix, 'zlib.dll'),
                 os.path.join(sys.prefix, 'Library', 'bin', 'zlib.dll'))
     if os.path.exists(p)),
    None,
)
if zlib_dll is None:
    raise SystemExit(
        "zlib.dll not found in the active environment. The frozen app will not "
        "start without it - check the environment before building."
    )
runtime_dlls = [(zlib_dll, 'zlib.dll')]

# Include your files and folders
includefiles = ['GUI/', 'images/', 'scripts/', 'config.yaml'] + dmtx_dlls + runtime_dlls

# Exclude unnecessary packages
excludes = ['cx_Freeze', 'setuptools', 'tkinter']

base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name='RAPIID',
    version='4.0',
    description='RAked Pinned Insect Imaging Device',
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
            'initial_target_dir': r'[ProgramFilesFolder]\RAPIID',
            'install_icon': 'images/RAPIID_icon.ico',
        }
    },
    executables=[
        Executable(
            'rapiid.py',
            base=base,
            icon=icon_file,
            shortcut_name='RAPIID',
            shortcut_dir='DesktopFolder'
        ),
        Executable(
            'rapiid.py',
            base=base,
            icon=icon_file,
            shortcut_name='RAPIID',
            shortcut_dir='ProgramMenuFolder'
        ),
    ]
)