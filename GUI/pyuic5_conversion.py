# Run from the repository root with the project environment active.
# Invoked as a module rather than via pyuic5.exe: the .exe launcher bakes in
# the interpreter path at install time and breaks if the env is ever renamed.

python -m PyQt5.uic.pyuic -x GUI/rapiid_GUI.ui -o GUI/rapiid_GUI.py