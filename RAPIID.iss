[Setup]
AppId={{8AAE16EC-C49C-439A-9B9C-1541DC8A1807}
AppName=RAPIID
AppVersion=4.0.1
AppVerName=RAPIID 4.0.1
AppPublisher=Aaron Harmer
AppPublisherURL=https://github.com/aharmer/RAPIID
DefaultDirName={autopf64}\RAPIID
DefaultGroupName=RAPIID
UninstallDisplayIcon={app}\rapiid.exe
OutputDir=dist
OutputBaseFilename=RAPIID-4.0.1-win64-setup
SetupIconFile=images\RAPIID_icon.ico
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
Name: "{group}\RAPIID"; Filename: "{app}\rapiid.exe"; IconFilename: "{app}\images\RAPIID_icon.ico"
Name: "{autodesktop}\RAPIID"; Filename: "{app}\rapiid.exe"; IconFilename: "{app}\images\RAPIID_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\rapiid.exe"; Description: "Launch RAPIID"; Flags: nowait postinstall skipifsilent
