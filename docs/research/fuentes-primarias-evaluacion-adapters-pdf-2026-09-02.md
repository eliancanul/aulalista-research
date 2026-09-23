# Fuentes primarias para evaluar adapters PDF locales

**Fecha de consulta:** 2026-09-02.
**Ámbito:** gold set y runner aislado para comparar pypdf, Docling local y PDF
nativo con OCR selectivo. No autoriza integración con `CurriculumImportJob`,
modelos, vistas, prompts ni flujo editorial.

Esta nota complementa, sin repetir, el método y las métricas de
[`importacion-curricular-pdf-heterogenea-2026-09-02.md`](importacion-curricular-pdf-heterogenea-2026-09-02.md)
(§§2.2--2.6 y §3) y el inventario de
[`corpus-referencia-importacion-curricular-2026-09-02.md`](corpus-referencia-importacion-curricular-2026-09-02.md).

## Hechos verificables de las fuentes que mantienen cada herramienta

| Ruta | Hecho primario | Consecuencia para el gold set y la corrida |
| --- | --- | --- |
| **pypdf** | `extract_text()` admite modo `layout` y callbacks de visitante que reciben texto y matrices de transformación; su propia documentación advierte que las coordenadas pueden ser erróneas en documentos complejos. [Documentación de extracción de pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) | Conservar la salida de texto por página y cualquier `bbox` derivado como salida del adapter, no como verdad de anotación. Medir su provenance contra el `bbox` humano y registrar `extraction_mode`, orientaciones y versión. |
| **pypdf** | PDF no contiene una capa semántica para encabezados, párrafos o tablas; pypdf no hace OCR ni extrae texto de imágenes. La documentación desaconseja rasterizar siempre un PDF nacido digital, porque la extracción nativa aprovecha fuentes y codificaciones. [Documentación de extracción de pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) | No convertir CER/WER de una página nativa en evidencia de estructura de tabla, jerarquía u orden. La ruta base debe declarar páginas/regiones sin captura suficiente en vez de perderlas en silencio. |
| **Docling local** | `DoclingDocument` representa texto, tablas, imágenes, jerarquía, `bbox` cuando existe y provenance. [Modelo documental oficial de Docling](https://docling-project.github.io/docling/concepts/docling_document/) | Normalizar esos elementos al formato intermedio canónico, conservando `page_no`, geometría y procedencia originales. Evaluar tanto captura como layout, orden, tablas y provenance; no sólo Markdown exportado. |
| **Docling local** | Sus modelos se descargan automáticamente al primer uso, pero pueden prefijarse y fijarse con `artifacts_path`; los servicios remotos requieren `enable_remote_services=True`. [Opciones avanzadas oficiales de Docling](https://docling-project.github.io/docling/usage/advanced_options/) | Antes de cada medición, fijar versión, hashes/ruta de artefactos y modo local; dejar `enable_remote_services=False`. Un primer uso que descarga modelos no cuenta como latencia de documento: registrar warm-up aparte. |
| **Docling local** | El pipeline permite activar reconocimiento de estructura de tabla y seleccionar `FAST` o `ACCURATE`; la documentación presenta el primero como más rápido y el segundo como mejor para tablas difíciles. [Opciones de tablas de Docling](https://docling-project.github.io/docling/usage/advanced_options/) | Tratar modo de tablas, escala de render y OCR como configuración de experimento. Si se comparan ambos modos, son filas distintas; no combinar sus resultados ni seleccionar por página después de ver la etiqueta de referencia. |
| **OCR selectivo** | OCRmyPDF define `skip` (no OCR donde ya hay texto), `redo` (reconoce de nuevo texto OCR invisible sin perturbar el texto visible) y `force` (rasteriza toda la página); `force` aplana formularios/objetos interactivos y `redo`/`force` descartan el árbol estructural etiquetado que ya no corresponde. [Modos oficiales de OCRmyPDF](https://ocrmypdf.readthedocs.io/en/latest/advanced.html) | En la ruta híbrida, conservar nativo y OCR como evidencias separadas y registrar regla de enrutamiento por página/región. No usar `force` como baseline silencioso; medirlo sólo como configuración explícita y verificar pérdida de estructura/provenance. |
| **OCR selectivo** | OCRmyPDF expone timeout de Tesseract por página y omite imágenes grandes según configuración; Tesseract indica que calidad depende de preprocesamiento, recomienda al menos 300 DPI y que una región pequeña use un `--psm` apropiado. [Límites de OCRmyPDF](https://ocrmypdf.readthedocs.io/en/latest/advanced.html), [guía oficial de calidad de Tesseract](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html) | Congelar idioma, DPI/escala, preprocesamiento, `--psm`, timeout, límites de imagen y versión de datos lingüísticos. Los timeout, páginas omitidas y salidas parciales son resultados, no ceros ni exclusiones implícitas. |
| **OCR selectivo** | Tesseract documenta que tiene problemas conocidos con reconocimiento de tablas sin segmentación o análisis de layout personalizado. [Guía oficial de calidad de Tesseract](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html) | No interpretar una mejora de CER/WER como mejora de tablas. Mantener las métricas de tabla y orden propuestas en la investigación como gates independientes. |

## Decisiones de medición que se desprenden de esos hechos

1. Cada corrida debe producir un registro por página y región con `included`,
   `reference_only`, `quarantined` o `excluded`, más su razón. Una salida vacía,
   timeout u omisión de OCR no puede desaparecer del manifest.
2. Para igualdad experimental, los tres adapters reciben el mismo archivo por
   hash y el mismo split. La ruta OCR añade su configuración completa; Docling
   añade sus pesos y opciones; pypdf añade modo de extracción y orientación.
3. La comparación mínima por página separa: captura de texto, layout/`bbox`,
   orden de lectura, estructura de tabla, jerarquía/relaciones y resolubilidad
   de provenance. Los valores de rendimiento se informan por configuración y
   distinguen warm-up de corrida estable.
4. La anotación humana renderizada continúa siendo el referente. Ninguna salida
   de adapter, confianza OCR o éxito de conversión autoriza aceptar un campo
   sin `EvidenceSpan` ni convertir `unknown`/`quarantined`.

## Límite de decisión

Estas fuentes demuestran capacidades y restricciones de las herramientas; no
demuestran precisión en las cuatro familias C01--C04 ni en la Mac M4/16 GB.
Por ello todavía no permiten escoger un futuro `CurriculumSourceInterpreter`.
La siguiente decisión válida es ejecutar el runner aislado sobre los splits
congelados y revisar visualmente los errores graves, conforme a los gates ya
definidos en la investigación principal.
