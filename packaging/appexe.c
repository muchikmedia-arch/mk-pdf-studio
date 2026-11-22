/* MK PDF Studio: proceso principal del programa (equivalente a pythonw.exe, con el ícono propio).
   Vive dentro de la carpeta "runtime" junto a python312.dll. */
#include <windows.h>
#include <wchar.h>
#include <stdlib.h>

__declspec(dllimport) int Py_Main(int argc, wchar_t **argv);

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmd, int show) {
    int argc = __argc;
    wchar_t **argv = __wargv;
    /* Procesos internos de trabajo (multiprocessing) llegan con opciones que empiezan con '-' */
    if (argc > 1 && argv[1][0] == L'-') {
        return Py_Main(argc, argv);
    }
    wchar_t dir[MAX_PATH * 2];
    GetModuleFileNameW(NULL, dir, MAX_PATH * 2);
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = 0;
    slash = wcsrchr(dir, L'\\');          /* subir de "runtime" a la carpeta del programa */
    if (slash) *slash = 0;
    static wchar_t script[MAX_PATH * 2 + 32];
    swprintf(script, MAX_PATH * 2 + 32, L"%ls\\app\\main.py", dir);
    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL, L"No se pudo iniciar MK PDF Studio porque falta una parte del programa.\nVuelve a instalarlo.",
                    L"MK PDF Studio", MB_ICONERROR | MB_OK);
        return 1;
    }
    wchar_t **nargv = (wchar_t **)calloc(argc + 8, sizeof(wchar_t *));
    int n = 0;
    nargv[n++] = argv[0];
    nargv[n++] = L"-E";        /* ignorar variables PYTHON* de otras instalaciones */
    nargv[n++] = L"-s";        /* sin paquetes del usuario */
    nargv[n++] = L"-X";
    nargv[n++] = L"utf8";
    nargv[n++] = script;
    for (int i = 1; i < argc; i++) nargv[n++] = argv[i];
    return Py_Main(n, nargv);
}
