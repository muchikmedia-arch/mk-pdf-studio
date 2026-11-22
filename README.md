# MK PDF Studio

Programa gratuito para Windows para **convertir, editar y organizar documentos PDF** en la oficina.
Funciona sin internet: los documentos nunca salen de la computadora.

Desarrollado por **Muchik Media | Apps** · Trujillo, Perú
Web: [www.muchikmedia.com](https://www.muchikmedia.com) · Correo: muchikmedia@gmail.com

## Descargar

**[Descargar MK PDF Studio para Windows](https://github.com/muchikmedia-arch/mk-pdf-studio/raw/descargas/MK-PDF-Studio-Instalador.exe)** (75 MB) · versión 1.3.1

Requiere Windows 10 u 11 de 64 bits. No necesita permisos de administrador.
Si ya lo tienes instalado, el programa te avisa solo cuando hay una versión nueva.

## Qué puede hacer

**Convertir**
- PDF a Word (también PDF escaneados, con reconocimiento de texto OCR en español)
- PDF a Excel (las tablas quedan con números que se pueden sumar)
- PDF a PowerPoint (texto editable o páginas como imagen)
- PDF escaneado a PDF con texto (para buscar y copiar)
- Imagen a texto · PDF a imágenes · Word a imágenes

**Editar PDF**
- Escribir texto, corregir texto existente, resaltar, subrayar, tachar y notas
- Tapar datos (se borran de verdad), firma o sello guardado, sello «Recibido» con fecha y hora
- Dibujar, recuadros y llenar formularios

**Organizar páginas**
- Mover, quitar, girar, agregar y extraer páginas

**Herramientas**
- Foliar (de adelante hacia atrás o al revés, formato 1/20, ceros a la izquierda, color rojo o azul)
- Todas las páginas a tamaño A4, Carta u Oficio
- Unir / armar expediente (PDF, fotos, Word y Excel), dividir, comprimir
- Quitar el fondo a firmas y sellos (PNG transparente) y mejorar su color
- Fotos del celular a PDF tipo escáner, marca de agua, contraseña, limpiar escaneos, buscar en una carpeta

El programa avisa cuando hay una versión nueva y se actualiza con un clic.

## Licencia

Software libre bajo la licencia **GNU AGPL-3.0** (ver `LICENCIA.txt`).
Usa PyMuPDF/MuPDF, Tesseract OCR, pdf2docx, Qt (PySide6), OpenCV, NumPy, openpyxl,
python-docx, python-pptx y Pillow, cada uno con su propia licencia.

## Estructura del código

- `mkpdf/core/` – motores de conversión, OCR, herramientas y editor (sin interfaz)
- `mkpdf/ui/` – interfaz gráfica (PySide6)
- `packaging/` – lanzadores de Windows, armado de la carpeta del programa e instalador (NSIS)
- `version.json` – información de la última versión (el programa lo lee para avisar de actualizaciones)
