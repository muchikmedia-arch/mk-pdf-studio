"""Arma la carpeta del programa para Windows (runtime de Python + librerías + programa).

Uso: python3 packaging/build.py <runtime_windows> <paquetes_windows> <salida>
"""
import fnmatch
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_SRC, PKGS_SRC, DIST = sys.argv[1], sys.argv[2], sys.argv[3]

RUNTIME_SKIP = [
    "include", "share", "Scripts", "Tools", "conda-meta", "libs", "CACHEDIR.TAG",
    "Lib/test", "Lib/idlelib", "Lib/tkinter", "Lib/turtledemo", "Lib/ensurepip", "Lib/lib2to3",
    "Lib/site-packages", "Library/lib", "Library/include", "Library/share", "Library/ssl",
    "DLLs/_test*", "DLLs/_tkinter.pyd", "DLLs/xxlimited*", "DLLs/_ctypes_test.pyd", "DLLs/_msi.pyd",
    "Library/bin/tcl*", "Library/bin/tk*", "Library/bin/openssl*", "Library/bin/c_rehash*",
    "Library/bin/*.pdb", "*.pdb", "tcl", "Library/bin/sqlite3.exe",
]

PYSIDE_KEEP_DLL = {"Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Svg.dll", "pyside6.abi3.dll",
                   "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_codecvt_ids.dll",
                   "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll"}
PYSIDE_KEEP_PYD = {"QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtSvg.pyd"}
PYSIDE_KEEP_PLUGINS = {"platforms", "imageformats", "iconengines", "styles"}

PKG_SKIP = ["*/__pycache__", "*.pyi", "cv2/opencv_videoio_ffmpeg*.dll", "pymupdf/layout", "pymupdf/mupdf-devel",
            "fitz/__pycache__", "numpy/_core/tests", "numpy/*/tests", "numpy/tests", "PIL/*.pyi",
            "fontTools/*/tests", "lxml/includes", "lxml/*.h", "*/py.typed"]


def skip(rel, patterns):
    rel = rel.replace("\\", "/")
    return any(fnmatch.fnmatch(rel, p) or rel.startswith(p.rstrip("*") + "/") and "*" not in p for p in patterns)


def copytree(src, dst, patterns):
    for root, dirs, files in os.walk(src):
        rel_root = os.path.relpath(root, src)
        rel_root = "" if rel_root == "." else rel_root
        dirs[:] = [d for d in dirs if not skip(os.path.join(rel_root, d), patterns)]
        os.makedirs(os.path.join(dst, rel_root), exist_ok=True)
        for f in files:
            rel = os.path.join(rel_root, f)
            if skip(rel, patterns):
                continue
            shutil.copy2(os.path.join(src, rel), os.path.join(dst, rel))


def main():
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    rt = os.path.join(DIST, "runtime")
    print("runtime…")
    copytree(RUNTIME_SRC, rt, RUNTIME_SKIP)
    # DLL de soporte junto a python312.dll (para que las encuentre sin depender del PATH)
    libbin = os.path.join(RUNTIME_SRC, "Library", "bin")
    for f in os.listdir(libbin):
        if f.lower().endswith(".dll") and not f.lower().startswith(("tcl", "tk")):
            shutil.copy2(os.path.join(libbin, f), os.path.join(rt, f))
    shutil.rmtree(os.path.join(rt, "Library"), ignore_errors=True)

    print("librerías…")
    sp = os.path.join(rt, "Lib", "site-packages")
    copytree(PKGS_SRC, sp, PKG_SKIP)
    # Recortar Qt a lo necesario
    ps = os.path.join(sp, "PySide6")
    for f in os.listdir(ps):
        p = os.path.join(ps, f)
        if os.path.isdir(p):
            if f == "plugins":
                for pl in os.listdir(p):
                    if pl not in PYSIDE_KEEP_PLUGINS:
                        shutil.rmtree(os.path.join(p, pl))
                continue
            shutil.rmtree(p)
        elif f.endswith(".dll") and f not in PYSIDE_KEEP_DLL:
            os.remove(p)
        elif f.endswith(".pyd") and f not in PYSIDE_KEEP_PYD:
            os.remove(p)
        elif f.endswith(".exe"):
            os.remove(p)
    for pl in ("imageformats",):
        d = os.path.join(ps, "plugins", pl)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if not any(k in f for k in ("qsvg", "qjpeg", "qico", "qgif")):
                    os.remove(os.path.join(d, f))
    # El archivo de rutas de Python incluido no debe limitar sys.path
    for f in os.listdir(rt):
        if f.endswith("._pth"):
            os.remove(os.path.join(rt, f))

    print("programa…")
    app = os.path.join(DIST, "app")
    copytree(os.path.join(ROOT, "mkpdf"), os.path.join(app, "mkpdf"), ["*/__pycache__", "__pycache__"])
    shutil.copy2(os.path.join(ROOT, "main.py"), os.path.join(app, "main.py"))
    td = os.path.join(app, "mkpdf", "resources", "tessdata")
    os.makedirs(td, exist_ok=True)
    for lang in ("spa", "eng"):
        shutil.copy2(f"/usr/share/tesseract-ocr/5/tessdata/{lang}.traineddata", td)
    shutil.copy2(os.path.join(ROOT, "packaging", "MK PDF Studio.exe"), os.path.join(DIST, "MK PDF Studio.exe"))
    # proceso principal con el logo (lo que se ve en la barra de tareas)
    shutil.copy2(os.path.join(ROOT, "packaging", "app_runtime.exe"), os.path.join(rt, "MK PDF Studio.exe"))
    for f in ("LICENCIA.txt", "LEEME.txt", "LICENSE"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(DIST, f))
    licdir = os.path.join(DIST, "licencias")
    os.makedirs(licdir, exist_ok=True)
    for root, dirs, files in os.walk(sp):
        if root.endswith(".dist-info"):
            for f in files:
                if f.upper().startswith(("LICEN", "COPYING", "NOTICE")):
                    name = os.path.basename(root).split("-")[0]
                    shutil.copy2(os.path.join(root, f), os.path.join(licdir, f"{name} - {f}"))
        if "licenses" in root and root.split(os.sep)[-2].endswith(".dist-info"):
            name = root.split(os.sep)[-2].split("-")[0]
            for f in files:
                shutil.copy2(os.path.join(root, f), os.path.join(licdir, f"{name} - {f}"))
    total = 0
    for root, dirs, files in os.walk(DIST):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    print(f"listo: {total / 1024 / 1024:.0f} MB")


if __name__ == "__main__":
    main()
