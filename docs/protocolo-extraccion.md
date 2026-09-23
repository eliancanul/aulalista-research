# Investigación 1 · Extracción e interpretación curricular

## Pregunta

¿Qué combinación de captura, estructura, interpretación y cascadas recupera datos y relaciones de planeaciones heterogéneas con evidencia localizable y una carga de revisión humana aceptable?

**Unidad experimental propuesta:** afirmación curricular atómica (dato o relación) vinculada a documento, hash, página o región, método y estado. Las páginas, documentos, entidades y repeticiones temporizadas son unidades diferentes; no se suman como si fueran ejemplos independientes.

## Hipótesis y fases

- **Fase I retrospectiva:** observar cuánto conservan los adaptadores y qué decisiones técnicas producen tres políticas deterministas sobre las capturas disponibles. Los resultados de septiembre de 2026 son exploratorios.
- **Fase II propuesta:** comparar rutas selectivas con verificación de evidencia y abstención. La hipótesis es que podrían aumentar los datos y relaciones correctos resueltos automáticamente sin multiplicar las intervenciones puntuales antes de la revisión general humana.

La estructura de Fase II es una propuesta de investigación, no un resultado ni una autorización para que un modelo publique contenido.

## Medidas necesarias

| Medida | Unidad y condición |
|---|---|
| Precisión entre aceptados | Afirmaciones aceptadas comparadas con gold independiente y adjudicado. |
| Cobertura | Afirmaciones esperadas resueltas, con abstenciones y ausencias explícitas. |
| Fidelidad relacional | Relaciones correctas entre proyecto, etapa, sesión, actividad y recurso según lo declarado en la fuente. |
| Trabajo humano | Intervenciones puntuales y tiempo de revisión por documento, medidos con un protocolo real. |
| Coste técnico | Latencia por etapa y extremo a extremo, memoria, fallos y censura temporal. |

Los estados `not_evaluable`, captura parcial y `censored_timeout` se conservan en sus propios denominadores. Un resultado vacío, un dato ausente y una contradicción no son equivalentes. La concordancia por presencia 13/22 o 15/22 del piloto no mide precisión de afirmaciones atómicas.

## Condiciones antes de comparar calidad

1. Cerrar ontología, protocolo de anotación, adjudicación, corpus y particiones por familias de documento.
2. Congelar captura raw y condiciones de cada corrida antes de calcular métricas.
3. Comparar rutas sobre la misma entrada y con presupuestos documentados; una diferencia de fuente, tarea o censura impide ordenar rutas como ganadoras.
4. Mantener revisión y autoridad editorial humanas. La salida experimental no altera el producto.

La [bitácora](research/bitacora-extraccion/bitacora-extraccion.ipynb) muestra exclusivamente lo disponible en este corte.
