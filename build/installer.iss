; ---------------------------------------------------------------------------
; AutoTyper - Inno Setup script (single-file Windows installer)
;
; Produces dist\AutoTyper-Setup-<version>.exe from dist\AutoTyper\.
;
; Design decisions:
;   * PrivilegesRequired=lowest  -> per-user install into %LOCALAPPDATA%\Programs,
;     no UAC prompt. AutoTyper needs no elevation to synthesise keystrokes.
;   * One-folder payload, compressed into one .exe by Inno.
;   * Uninstall removes only what it installed; user settings in %APPDATA% are
;     deleted only when the user explicitly asks for a clean removal.
;
; Compile:
;   ISCC.exe build\installer.iss
; ---------------------------------------------------------------------------

#define AppName        "AutoTyper"
#define AppVersion     "1.0.0"
#define AppPublisher   "Otachi"
#define AppExeName     "AutoTyper.exe"

; ``SourcePath`` is the directory this .iss lives in (build\), so the payload
; is resolved relative to the repo regardless of Inno's working directory.
[Setup]
AppId={{8F3A6C21-5B4D-4E77-9E1A-2C7B4F0D9A63}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user: installs under %LOCALAPPDATA%\Programs and never prompts for admin.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=AutoTyper-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Icon shown in the installer, Add/Remove Programs and the wizard.
SetupIconFile=..\assets\autotyper.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}
; NOTE: ``UninstallDisplaySize`` is deliberately omitted. Its units are bytes,
; and the value is *displayed* in MB, so any hand-written number here ends up
; wildly wrong (115400 displayed as "112 KB"). Inno measures the files it
; installs and stores the correct KB total itself.
LicenseFile=..\LICENSE
ShowLanguageDialog=no
; No restart, no registry-wide changes.
ChangesAssociations=no
AllowNoIcons=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startupicon"; Description: "Start AutoTyper when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; The whole one-folder bundle. ``recursesubdirs`` picks up _internal\ (Qt,
; pynput, plugins) and the packaged icons.
Source: "..\dist\AutoTyper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\autotyper\assets\autotyper.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\autotyper\assets\autotyper.ico"; Tasks: desktopicon

[Registry]
; Optional "run at login" toggle, per-user.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AutoTyper"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Deliberately empty aside from the install dir.
;
; ``_internal`` must NOT be listed here: the uninstaller copies itself into a
; temp folder and runs while Qt/Python DLLs from the install folder may still be
; mapped, so a recursive delete fails and leaves ~30 orphaned files behind.
; Inno already removes every file it installed (tracked in unins000.dat), which
; is both correct and safe. ``dirifempty`` only tidies a fully empty folder.
Type: dirifempty; Name: "{app}"
