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
!define MUI_ICON "logos\trackmind_icon.ico"
!define MUI_UNICON "logos\trackmind_icon.ico"

!define MUI_WELCOMEFINISHPAGE_BITMAP "logos\trackmind_installer.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "logos\trackmind_installer.bmp"
!define MUI_WELCOMEPAGE_TITLE "TrackMind"
!define MUI_WELCOMEPAGE_TEXT "This will install Trackmind on your computer.$\r$\n$\r$\nAuto-tracking software for PTZOptics cameras using AI pose detection.$\r$\n$\r$\nClick Next to continue."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

; Offer to launch the app at the end of an interactive install
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Launch Trackmind now"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Start Trackmind as the signed-in user, not as admin. This installer runs
; elevated, and a plain Exec would hand that elevation to the app. Going
; through Explorer starts it the same way a double-click does.

Function LaunchApp
  Exec '"$WINDIR\explorer.exe" "$INSTDIR\Trackmind.exe"'
FunctionEnd

;--------------------------------
; Installer section

Section "Install" SecMain

  ; ── Close the running app before replacing it ──
  ; The auto-updater launches this installer and then closes itself. Give it
  ; a few seconds to exit cleanly (it saves settings on the way out), then
  ; force it. NEVER use taskkill /T here: an installer started through the
  ; UAC prompt counts as a child of the app that launched it, so /T killed
  ; this installer along with the app. That was the v1.4–v1.7 "update does
  ; nothing" bug.
  DetailPrint "Waiting for Trackmind to close..."
  StrCpy $R1 0
  wait_exit:
    nsExec::ExecToStack 'cmd /c tasklist /FI "IMAGENAME eq Trackmind.exe" /NH | find /I "Trackmind.exe"'
    Pop $0   ; find's exit code: 0 = still running
    Pop $1
    StrCmp $0 "0" 0 app_closed
    IntOp $R1 $R1 + 1
    IntCmp $R1 24 force_close 0 force_close   ; 24 × 250 ms = 6 s
    Sleep 250
    Goto wait_exit
  force_close:
    DetailPrint "Closing Trackmind..."
    nsExec::Exec 'taskkill /F /IM Trackmind.exe'
    Pop $0
    Sleep 500
  app_closed:

  SetOutPath "$INSTDIR"

  ; Move the old EXE aside instead of deleting it. Windows lets you rename an
  ; EXE even while it's still running or held open by antivirus, which a
  ; delete doesn't allow. Retry for a while in case an AV scan is holding it
  ; exclusively.
  Delete "$INSTDIR\Trackmind.old.exe"   ; leftover from a previous update
  StrCpy $R0 0
  move_old:
    IfFileExists "$INSTDIR\Trackmind.exe" 0 old_moved   ; fresh install
    ClearErrors
    Rename "$INSTDIR\Trackmind.exe" "$INSTDIR\Trackmind.old.exe"
    IfErrors 0 old_moved
    IntOp $R0 $R0 + 1
    IntCmp $R0 15 old_stuck 0 old_stuck
    DetailPrint "Waiting for Trackmind.exe to be released ($R0/15)..."
    Sleep 1000
    Goto move_old
  old_stuck:
    ; The old EXE is still intact. Put the user back where they were.
    MessageBox MB_OK|MB_ICONSTOP \
      "Update failed: Trackmind.exe is locked (usually by antivirus).$\n$\nRestart your PC and run the installer again, or download it from:$\nhttps://github.com/coder747-8i/Trackmind/releases" \
      /SD IDOK
    ${If} ${Silent}
      Call LaunchApp
    ${EndIf}
    Abort
  old_moved:
  ClearErrors

  SetOverwrite on

  ; Main executable
  File "dist\Trackmind.exe"
  IfErrors 0 copy_ok
    ; Couldn't write the new EXE: restore the old one so Trackmind still runs.
    Rename "$INSTDIR\Trackmind.old.exe" "$INSTDIR\Trackmind.exe"
    MessageBox MB_OK|MB_ICONSTOP \
      "Update failed: could not write the new Trackmind.exe.$\n$\nDownload the installer manually from:$\nhttps://github.com/coder747-8i/Trackmind/releases" \
      /SD IDOK
    ${If} ${Silent}
      Call LaunchApp
    ${EndIf}
    Abort
  copy_ok:
  ; Gone now, or on the next reboot if something still holds it.
  Delete /REBOOTOK "$INSTDIR\Trackmind.old.exe"

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
    Call LaunchApp
  ${EndIf}

SectionEnd

;--------------------------------
; Uninstaller section

Section "Uninstall"

  ; Close the app so its files can be removed
  nsExec::Exec 'taskkill /F /IM Trackmind.exe'
  Pop $0
  Sleep 500

  ; Remove files
  Delete "$INSTDIR\Trackmind.exe"
  Delete /REBOOTOK "$INSTDIR\Trackmind.old.exe"
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
