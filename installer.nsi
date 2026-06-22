; Trackmind — NSIS Installer Script
; Requires NSIS installed: https://nsis.sourceforge.io/Download
; Build the exe first with BUILD_EXE.bat, then compile this with NSIS.
;
; Version is passed in automatically by BUILD_INSTALLER.bat from version.txt:
;   makensis /DAPP_VERSION=1.1 /DAPP_VERSION_4=1.1.0.0 installer.nsi
; Fallback defaults below are used only if compiling manually without /D flags.

!ifndef APP_VERSION
  !define APP_VERSION "1.2"
!endif
!ifndef APP_VERSION_4
  !define APP_VERSION_4 "1.2.0.0"
!endif

;--------------------------------
; General

Name "Trackmind"
OutFile "Trackmind_Setup_v${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\Trackmind"
InstallDirRegKey HKLM "Software\Trackmind" "Install_Dir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

;--------------------------------
; Version info shown in installer

VIProductVersion "${APP_VERSION_4}"
VIAddVersionKey "ProductName"      "Trackmind"
VIAddVersionKey "FileDescription"  "Trackmind Installer"
VIAddVersionKey "FileVersion"      "${APP_VERSION}"
VIAddVersionKey "LegalCopyright"   "Open Source"

;--------------------------------
; Pages

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "trackmind_icon.ico"
!define MUI_UNICON "trackmind_icon.ico"

!define MUI_WELCOMEFINISHPAGE_BITMAP "trackmind_installer.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "trackmind_installer.bmp"
!define MUI_WELCOMEPAGE_TITLE "TrackMind"
!define MUI_WELCOMEPAGE_TEXT "This will install Trackmind on your computer.$\r$\n$\r$\nAuto-tracking software for PTZOptics cameras using AI pose detection.$\r$\n$\r$\nClick Next to continue."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

; Offer to launch the app at the end of an interactive install
!define MUI_FINISHPAGE_RUN "$INSTDIR\Trackmind.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Trackmind now"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer section

Section "Install" SecMain

  ; ── Close any running instance before copying files ──
  ; The auto-updater launches this installer while the old Trackmind is
  ; still open. On Windows a running .exe is locked, so a silent install
  ; would fail to overwrite it (quietly, with no error) and the update
  ; would appear to "do nothing". Force it closed, then confirm the lock
  ; is released before writing — Windows Defender and other AV software
  ; can hold the lock for several seconds after a forced kill.
  DetailPrint "Closing any running Trackmind..."
  nsExec::Exec 'taskkill /F /IM Trackmind.exe /T'
  Pop $0

  SetOutPath "$INSTDIR"

  ; Retry deleting the old EXE until the file lock releases.
  ; Up to 10 attempts × 1 s = 10 s max wait.
  StrCpy $R0 0
  check_lock:
    IfFileExists "$INSTDIR\Trackmind.exe" 0 file_ready  ; fresh install — skip
    ClearErrors
    Delete "$INSTDIR\Trackmind.exe"
    IfErrors 0 file_ready            ; deleted — lock is gone
    IntOp $R0 $R0 + 1
    IntCmp $R0 10 file_ready wait_1s file_ready  ; >= 10 tries: give up
    wait_1s:
      DetailPrint "Waiting for file lock to release ($R0/10)..."
      Sleep 1000
      Goto check_lock
  file_ready:
  ClearErrors

  SetOverwrite on

  ; Main executable
  File "dist\Trackmind.exe"
  IfErrors 0 copy_ok
    MessageBox MB_OK|MB_ICONSTOP \
      "Update failed: could not replace Trackmind.exe.$\n$\nThe file may still be locked by antivirus. Please restart your PC and reinstall if needed.$\n$\nManual download: https://github.com/coder747-8i/Trackmind/releases" \
      /SD IDOK
    Abort
  copy_ok:

  ; Optional docs — use /nonfatal so build continues if files are missing
  File /nonfatal "context.txt"
  File /nonfatal "README.md"

  ; Write install location to registry
  WriteRegStr HKLM "Software\Trackmind" "Install_Dir" "$INSTDIR"

  ; Write uninstaller registry keys
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\Trackmind" \
    "DisplayName" "Trackmind"
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\Trackmind" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\Trackmind" \
    "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\Trackmind" \
    "Publisher" "Open Source"
  WriteRegDWORD HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\Trackmind" \
    "NoModify" 1
  WriteRegDWORD HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\Trackmind" \
    "NoRepair" 1

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\Trackmind"
  CreateShortcut "$SMPROGRAMS\Trackmind\Trackmind.lnk" \
    "$INSTDIR\Trackmind.exe"
  CreateShortcut "$SMPROGRAMS\Trackmind\Uninstall.lnk" \
    "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut
  CreateShortcut "$DESKTOP\Trackmind.lnk" "$INSTDIR\Trackmind.exe"

  ; ── Relaunch after a silent (auto-update) install ──
  ; Silent mode skips the Finish page, so relaunch the freshly installed
  ; app ourselves — otherwise an auto-update ends with nothing running.
  ${If} ${Silent}
    Exec '"$INSTDIR\Trackmind.exe"'
  ${EndIf}

SectionEnd

;--------------------------------
; Uninstaller section

Section "Uninstall"

  ; Remove files
  Delete "$INSTDIR\Trackmind.exe"
  Delete /REBOOTOK "$INSTDIR\context.txt"
  Delete /REBOOTOK "$INSTDIR\README.md"
  Delete "$INSTDIR\Uninstall.exe"

  ; Remove install directory
  RMDir "$INSTDIR"

  ; Remove Start Menu shortcuts
  Delete "$SMPROGRAMS\Trackmind\Trackmind.lnk"
  Delete "$SMPROGRAMS\Trackmind\Uninstall.lnk"
  RMDir  "$SMPROGRAMS\Trackmind"

  ; Remove Desktop shortcut
  Delete "$DESKTOP\Trackmind.lnk"

  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Trackmind"
  DeleteRegKey HKLM "Software\Trackmind"

SectionEnd
