[Setup]
AppId={{8AAE16EC-C49C-439A-9B9C-1541DC8A1807}
AppName=RAPIIDlite
AppVersion=3.2
AppVerName=RAPIIDlite 3.2
AppPublisher=Aaron Harmer
AppPublisherURL=https://github.com/aharmer/RAPIIDlite
DefaultDirName={autopf64}\RAPIIDlite
DefaultGroupName=RAPIIDlite
UninstallDisplayIcon={app}\rapiid_lite.exe
OutputDir=dist
OutputBaseFilename=RAPIIDlite-3.2-win64-setup
SetupIconFile=images\RAPIIDlite_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "build\exe.win-amd64-3.8\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\RAPIIDlite"; Filename: "{app}\rapiid_lite.exe"; IconFilename: "{app}\images\RAPIIDlite_icon.ico"
Name: "{autodesktop}\RAPIIDlite"; Filename: "{app}\rapiid_lite.exe"; IconFilename: "{app}\images\RAPIIDlite_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\rapiid_lite.exe"; Description: "Launch RAPIIDlite"; Flags: nowait postinstall skipifsilent
