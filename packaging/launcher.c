/* Acceso rápido en la carpeta del programa: abre runtime\MK PDF Studio.exe */
#include <windows.h>
#include <wchar.h>
#include <stdlib.h>

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmd, int show) {
    wchar_t base[MAX_PATH * 2];
    GetModuleFileNameW(NULL, base, MAX_PATH * 2);
    wchar_t *slash = wcsrchr(base, L'\\');
    if (slash) *slash = 0;
    wchar_t exe[MAX_PATH * 2 + 64];
    swprintf(exe, MAX_PATH * 2 + 64, L"%ls\\runtime\\MK PDF Studio.exe", base);
    size_t len = wcslen(exe) + (cmd ? wcslen(cmd) : 0) + 8;
    wchar_t *line = (wchar_t *)calloc(len, sizeof(wchar_t));
    swprintf(line, len, L"\"%ls\" %ls", exe, cmd ? cmd : L"");
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si)); si.cb = sizeof(si); ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(exe, line, NULL, NULL, FALSE, 0, NULL, base, &si, &pi)) {
        MessageBoxW(NULL, L"No se pudo iniciar MK PDF Studio.\nSi el antivirus lo bloqueó, permite el programa y vuelve a abrirlo.",
                    L"MK PDF Studio", MB_ICONERROR | MB_OK);
        return 1;
    }
    AllowSetForegroundWindow(pi.dwProcessId);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return 0;
}
