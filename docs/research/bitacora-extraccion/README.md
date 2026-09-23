# Bitácora visual de extracción e interpretación curricular

[Abrir la primera libreta](bitacora-extraccion.ipynb) · [Ver el recorrido](figuras/recorrido.svg)

Esta libreta personal registra **lo observado en la investigación**, con sus corridas congeladas y sus límites. El seguimiento de trabajo se mantendrá en los issues de este repositorio; esta libreta registra resultados, no tareas. Esta carpeta no ejecuta el importador ni modifica contenido curricular.

## Qué contiene este primer corte

- Un recorrido retrospectivo breve de Fase I: antecedentes de adaptadores del 2 de septiembre y microbenchmark de cascadas del 17 de septiembre. «Fase I» agrupa aquí esos antecedentes; no renombra los experimentos A/B del manuscrito.
- Una sección distinta para el **objetivo e hipótesis de Fase II**, sin simular resultados futuros.
- Figuras SVG regenerables de cobertura/estados de adaptadores, decisiones mecánicas de cascadas y cronología. La libreta permite elegir un documento y ver sus estados al ejecutarla localmente.
- Tres medidas objetivo, hoy pendientes: precisión entre afirmaciones aceptadas, cobertura y planeaciones que alcanzan revisión general sin correcciones puntuales. También falta medir costo humano. Requieren gold/adjudicación y protocolo; el 13/22 y 15/22 observacional no se transforman en precisión.

Los CSV y el JSON en `datos/` provienen del suplemento numérico local de la revisión del 18 de septiembre. El CSV de cascadas conserva los valores y normaliza saltos de línea CRLF a LF; el manifiesto guarda tanto el hash del origen como el de esta copia. No incluyen PDFs, capturas textuales, anotaciones narrativas ni identidades. `historial.json` fija SHA-256 de cada copia para impedir cambios silenciosos. Los documentos C01–C04 y D01–D04 son corpus distintos. El recibo protegido de Docling se mantiene separado de la matriz histórica; `censored_timeout` es censura, no tiempo completo ni fallo de calidad semántica.

## Actualizar con una corrida nueva

1. Congelar primero los artefactos de la corrida y su procedencia. Copiar aquí **solo resultados compartibles**, sin documentos fuente ni datos personales.
2. Añadir a `historial.json` una entrada con `id`, fecha, fase, tipo, pregunta, rutas relativas y SHA-256. No modificar una entrada anterior; un cambio de bytes es otra corrida. `kind` admite `adapters` o `cascade_matrix` con los esquemas CSV existentes.
3. Ejecutar `python3 docs/research/bitacora-extraccion/graficas.py` desde la raíz del repositorio, o ejecutar la celda de actualización de la libreta. El script verifica hashes y regenera las imágenes sin llamar a una LLM.
4. Revisar en Codex el texto breve de **resultado, alcance y límite** antes de añadir un hito destacado a la libreta. Un cambio de código, corpus o protocolo que impida comparación directa debe quedar explícito.

La actualización normal consume una modificación pequeña del manifiesto y la ejecución de un script determinista. La libreta no consulta GitHub ni vigila carpetas en segundo plano. Se actualiza al cerrar una corrida, tal como se acordó.

## Uso local

La vista en GitHub muestra la narración y los SVG sin ejecutar nada. Para usar el selector de documentos se necesita Jupyter e `ipywidgets` en el entorno local. Si no está `ipywidgets`, se puede llamar directamente a `cascade_svg(run, "D02")` desde la celda de exploración. `graficas.py` solo requiere Python 3.10 o posterior.

## Fuentes y alcance

- [Protocolo público](../../protocolo-extraccion.md): pregunta, métricas y gates de evaluación.
- [Procedencia de la separación](../../procedencia-migracion.md): origen de las copias numéricas y límites de lo publicable.

La reproducción de las figuras y la verificación de hashes **no** equivalen a reproducir la extracción completa ni a validar la interpretación curricular.
