# Procedencia de la separación

Esta primera versión fue preparada desde el repositorio privado `eliancanul/AulaLista`, con base de producto `6025f59` (22 de septiembre de 2026) y la libreta del PR privado `#131` (`71c4f96`). El repositorio de producto conserva su historial original. Este repositorio inicia una historia propia y declara qué fue trasladado; no presenta los archivos importados como trabajo nuevo escrito desde cero.

## Incluido

- Harness independiente `scripts/shadow_import/` y su CLI, con pruebas que generan PDFs sintéticos.
- Primera bitácora visual, figuras regenerables y tablas numéricas agregadas con hashes.
- Antecedente documental de evaluación de adaptadores y este protocolo público.

## Excluido en este corte

- Código de Django, modelos, migraciones, interfaz docente y pruebas de producto: permanecen en AulaLista producto.
- `scripts/benchmark_issue96_annexes.py`: depende de Django, del importador productivo y de un PDF cuya redistribución no está confirmada.
- PDFs curriculares, capturas de texto, manifiestos con rutas locales, anotaciones ligadas a documentos de terceros, informes con datos de docentes y artefactos locales sin revisión de publicación.
- Issues y PR privados: conservan la discusión histórica en el repositorio original; un enlace a ellos no sirve como documentación pública.

La separación se hará en el repositorio de producto después de verificar sus dependencias y pruebas. La copia inicial no autoriza borrar allí archivos que otras pruebas o flujos usan.
