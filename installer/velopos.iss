; VeloPOS installer (Inno Setup 6). Built by build_windows.bat
#ifndef BuildDir
  #define BuildDir "..\run.dist"
#endif
#ifndef OutDir
  #define OutDir "Output"
#endif

[Setup]
AppId={{B7C1D0F2-5A3E-4C55-9E0A-0E5E2C1A6F10}
AppName=VeloPOS
AppVersion=7.2
AppPublisher=VeloPOS (Powered by RG)
DefaultDirName={autopf}\VeloPOS
DefaultGroupName=VeloPOS
OutputDir={#OutDir}
OutputBaseFilename=VeloPOS_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
UninstallDisplayIcon={app}\VeloPOS.exe
; Customer data lives in %LOCALAPPDATA%\VeloPOS and is NOT removed on uninstall (on purpose).

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\VeloPOS"; Filename: "{app}\VeloPOS.exe"
Name: "{autodesktop}\VeloPOS"; Filename: "{app}\VeloPOS.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce

[Run]
Filename: "{app}\VeloPOS.exe"; Description: "Start VeloPOS"; Flags: nowait postinstall skipifsilent
