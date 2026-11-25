# AulaLista Research · Investigación de algoritmos

[![Research checks](https://github.com/eliancanul/aulalista-research/actions/workflows/research.yml/badge.svg?branch=main)](https://github.com/eliancanul/aulalista-research/actions/workflows/research.yml)

**Research on verifiable extraction and interpretation of heterogeneous Mexican school planning documents.** This repository presents the experimental methods and evidence behind AulaLista. The product application is maintained separately in [AulaLista](https://github.com/eliancanul/AulaLista).

Este repositorio reúne **investigación algorítmica**, empezando por captura de documentos, interpretación curricular y cascadas con abstención. Su propósito es permitir que otra persona entienda la pregunta, ejecute pruebas sintéticas y distinga resultados observados de hipótesis pendientes. La aplicación AulaLista y su flujo docente viven en otro repositorio.

## Empieza aquí

1. [Bitácora visual de extracción e interpretación](docs/research/bitacora-extraccion/bitacora-extraccion.ipynb): Fase I retrospectiva, datos congelados y objetivo de Fase II.
2. [Protocolo y estado de evidencia](docs/protocolo-extraccion.md): unidades, métricas y condiciones antes de declarar calidad.
3. `scripts/shadow_import/`: harness aislado para capturar páginas, cerrar raw e interpretar estados técnicos. Sus pruebas crean PDFs sintéticos al ejecutarse.
4. [Procedencia de la separación](docs/procedencia-migracion.md): qué se trasladó desde el repositorio de producto y qué se excluyó. Ese documento lo describe como privado; hoy es público.

## Estado de la investigación

Las corridas disponibles describen cobertura, estados, conteos y tiempos bajo sus condiciones registradas. La referencia semántica independiente **no está cerrada**: no se declara precisión, recall, F1, ganador de cascada, ahorro de tiempo docente ni impacto pedagógico. Una aceptación técnica solo significa que una salida pasó las reglas instrumentadas.

## Reproducir la parte pública

Se requiere Python 3.11 o posterior. Desde la raíz:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests/test_shadow_import_benchmark.py tests/test_ux9_blocker5_gates.py
.venv/bin/python docs/research/bitacora-extraccion/graficas.py
```

Las 9 pruebas generan sus propios PDFs sintéticos y comprueban el comportamiento del harness ante fallos: recibo y reanudación tras un timeout, checkpoints que quedan obsoletos cuando cambia la configuración o el hash de la fuente, rechazo del cierre de raw con orden de páginas inválido y negativa del intérprete a trabajar sobre un raw sin cerrar. El workflow `Research checks` ejecuta estos mismos comandos en cada push y pull request, y falla si las figuras regeneradas difieren de las versionadas.

El adaptador `pypdf` y las pruebas sintéticas funcionan con las dependencias indicadas. Docling y la ruta OCR necesitan sus runtimes adicionales; disponibilidad de un adaptador no acredita calidad curricular. La bitácora se lee estáticamente en GitHub. Para ejecutar su selector local, instala Jupyter e `ipywidgets` en tu entorno.

## Datos y publicación

No se incluyen PDFs curriculares de terceros, textos de captura, datos estudiantiles, nombres docentes ni anotaciones cuya publicación no esté autorizada. Las copias numéricas de la bitácora tienen hashes y alcances explícitos. El corpus completo y el gold adjudicado no son públicos en este corte; por eso la reproducción integral del experimento y la estimación de calidad semántica siguen pendientes.

**Licencia:** pendiente de decisión. La visibilidad pública permite consultar el repositorio; no se concede aquí una licencia de reutilización del código o los materiales.
