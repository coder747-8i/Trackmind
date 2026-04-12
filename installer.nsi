; PTZ Auto-Tracker — NSIS Installer Script
; Requires NSIS installed: https://nsis.sourceforge.io/Download
; Build the exe first with BUILD_EXE.bat, then compile this with NSIS.

;--------------------------------
; General

Name "PTZ Auto-Tracker"
OutFile "Trackmind_Setup.exe"
InstallDir "$PROGRAMFILES64\PTZ Auto-Tracker"
InstallDirRegKey HKLM "Software\PTZAutoTracker" "Install_Dir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

;--------------------------------
; Version info shown in installer

VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName"      "PTZ Auto-Tracker"
VIAddVersionKey "FileDescription"  "PTZ Auto-Tracker Installer"
VIAddVersionKey "FileVersion"      "1.0.0"
VIAddVersionKey "LegalCopyright"   "Open Source"

;--------------------------------
; Pages

!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "trackmind_icon.ico"
!define MUI_UNICON "trackmind_icon.ico"

!define MUI_WELCOMEFINISHPAGE_BITMAP "trackmind_installer.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "trackmind_installer.bmp"
!define MUI_WELCOMEPAGE_TITLE "TrackMind"
!define MUI_WELCOMEPAGE_TEXT "This will install PTZ Auto-Tracker on your computer.$\r$\n$\r$\nAuto-tracking software for PTZOptics cameras using AI pose detection.$\r$\n$\r$\nClick Next to continue."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer section

Section "Install" SecMain

  SetOutPath "$INSTDIR"

  ; Main executable
  File "dist\Trackmind.exe"

  ; Optional docs — use /nonfatal so build continues if files are missing
  File /nonfatal "context.txt"
  File /nonfatal "README.md"

  ; Write install location to registry
  WriteRegStr HKLM "Software\PTZAutoTracker" "Install_Dir" "$INSTDIR"

  ; Write uninstaller registry keys
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTZAutoTracker" \
    "DisplayName" "PTZ Auto-Tracker"
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTZAutoTracker" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTZAutoTracker" \
    "DisplayVersion" "1.0.0"
  WriteRegStr HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTZAutoTracker" \
    "Publisher" "Open Source"
  WriteRegDWORD HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTZAutoTracker" \
    "NoModify" 1
  WriteRegDWORD HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTZAutoTracker" \
    "NoRepair" 1

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\PTZ Auto-Tracker"
  CreateShortcut "$SMPROGRAMS\PTZ Auto-Tracker\PTZ Auto-Tracker.lnk" \
    "$INSTDIR\Trackmind.exe"
  CreateShortcut "$SMPROGRAMS\PTZ Auto-Tracker\Uninstall.lnk" \
    "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut
  CreateShortcut "$DESKTOP\PTZ Auto-Tracker.lnk" "$INSTDIR\Trackmind.exe"

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
  Delete "$SMPROGRAMS\PTZ Auto-Tracker\PTZ Auto-Tracker.lnk"
  Delete "$SMPROGRAMS\PTZ Auto-Tracker\Uninstall.lnk"
  RMDir  "$SMPROGRAMS\PTZ Auto-Tracker"

  ; Remove Desktop shortcut
  Delete "$DESKTOP\PTZ Auto-Tracker.lnk"

  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTZAutoTracker"
  DeleteRegKey HKLM "Software\PTZAutoTracker"

SectionEnd
