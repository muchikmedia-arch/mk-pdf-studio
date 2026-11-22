; Instalador de MK PDF Studio
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64
RequestExecutionLevel user
ManifestDPIAware true

!define APPNAME "MK PDF Studio"
!define VERSION "1.3.1"
!define PUBLISHER "Muchik Media"
!define LOCATION "Trujillo - Perú"
!define WEB "https://www.muchikmedia.com"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\MKPDFStudio"
!ifndef SRC
  !define SRC "..\dist\MK PDF Studio"
!endif
!ifndef OUTFILE
  !define OUTFILE "..\dist\MK-PDF-Studio-Instalador-${VERSION}.exe"
!endif

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "Software\${APPNAME}" "InstallDir"
BrandingText "${APPNAME} ${VERSION} · Muchik Media | Apps"

VIProductVersion "1.3.1.0"
VIAddVersionKey /LANG=1034 "ProductName" "${APPNAME}"
VIAddVersionKey /LANG=1034 "CompanyName" "${PUBLISHER}"
VIAddVersionKey /LANG=1034 "LegalCopyright" "(c) 2026 Muchik Media | Apps - ${LOCATION}"
VIAddVersionKey /LANG=1034 "FileDescription" "Instalador de ${APPNAME}"
VIAddVersionKey /LANG=1034 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1034 "ProductVersion" "${VERSION}"

!include "MUI2.nsh"
!include "FileFunc.nsh"

Var UpdateMode

Function .onInit
  StrCpy $UpdateMode "0"
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/ACTUALIZAR" $R1
  IfErrors +2 0
  StrCpy $UpdateMode "1"
FunctionEnd

Function SkipIfUpdate
  StrCmp $UpdateMode "1" 0 +2
  Abort
FunctionEnd

Function .onInstSuccess
  StrCmp $UpdateMode "1" 0 +2
  Exec '"$INSTDIR\runtime\${APPNAME}.exe"'
FunctionEnd
!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Bienvenido a ${APPNAME}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instalará ${APPNAME} ${VERSION} en tu computadora.$\r$\n$\r$\nPrograma gratuito para convertir PDF a Word y Excel, reconocer texto (OCR), organizar páginas, foliar y más. Funciona sin internet.$\r$\n$\r$\nDesarrollado por Muchik Media | Apps · ${LOCATION}.$\r$\n$\r$\nHaz clic en Siguiente para continuar."
!define MUI_FINISHPAGE_RUN "$INSTDIR\runtime\${APPNAME}.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir ${APPNAME} ahora"
!define MUI_FINISHPAGE_LINK "www.muchikmedia.com"
!define MUI_FINISHPAGE_LINK_LOCATION "${WEB}"

!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfUpdate
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfUpdate
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfUpdate
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"

Section "Programa" SecMain
  SectionIn RO
  StrCmp $UpdateMode "1" 0 +3
  SetAutoClose true
  DetailPrint "Actualizando MK PDF Studio a la versión ${VERSION}…"
  ; cerrar una versión anterior si está abierta
  Sleep 1200
  nsExec::Exec 'taskkill /F /IM "${APPNAME}.exe"'
  nsExec::Exec 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $$_.Path -like \"$INSTDIR\*\" } | Stop-Process -Force"'
  Sleep 800
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"
  File "app.ico"
  WriteRegStr HKCU "Software\${APPNAME}" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  SetOutPath "$INSTDIR\runtime"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\runtime\${APPNAME}.exe" "" "$INSTDIR\runtime\${APPNAME}.exe" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\Desinstalar ${APPNAME}.lnk" "$INSTDIR\Desinstalar.exe"
  CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\runtime\${APPNAME}.exe" "" "$INSTDIR\runtime\${APPNAME}.exe" 0
  SetOutPath "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "Muchik Media | Apps"
  WriteRegStr HKCU "${UNINSTKEY}" "URLInfoAbout" "${WEB}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\runtime\${APPNAME}.exe"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" 310000
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /F /IM "${APPNAME}.exe"'
  Sleep 800
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\licencias"
  Delete "$INSTDIR\${APPNAME}.exe"
  Delete "$INSTDIR\app.ico"
  Delete "$INSTDIR\LEEME.txt"
  Delete "$INSTDIR\LICENCIA.txt"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTKEY}"
  DeleteRegKey HKCU "Software\${APPNAME}"
SectionEnd
