# GeoVigil Analytics — Nota Conceptual

> Por qué este diseño, cuáles son los desafíos y qué opciones no se eligieron.
> Para las especificaciones detalladas, ver [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Antecedentes: evaluación del modelo del predecesor

El predecesor dejó un modelo Faster R-CNN (ResNet-50 FPN) entrenado con 178 imágenes de pistas de aterrizaje clandestinas en la Amazonía brasileña (imágenes Planet NICFI). El análisis identificó los siguientes problemas:

| Problema | Descripción |
|---|---|
| Volumen de datos insuficiente | 178 imágenes es extremadamente poco para detección de objetos |
| Sin independencia del conjunto de validación | train/val se dividieron aleatoriamente del mismo grupo; el rendimiento sobre datos no vistos no está verificado |
| Sesgo geográfico | Solo Brasil. Se desconoce la capacidad de generalización a otras regiones como Perú |
| Sin umbral de confianza | En inferencia se generan todas las detecciones, sin filtrado de falsos positivos |
| Banda NIR no utilizada | Las imágenes de 4 bandas se convirtieron a RGB, descartando el infrarrojo cercano, útil para detectar vegetación |
| Configuración de entrenamiento inconsistente | Las épocas/tasa de aprendizaje difieren entre el código y el informe, baja reproducibilidad |
| Ausencia de valores mAP | Prácticamente no se realizó evaluación cuantitativa |

→ Conclusión: **el modelo puede usarse como punto de partida, pero no está listo para producción tal como está.** El mayor activo es el know-how del predecesor para construir el ground truth (integración de múltiples fuentes de datos, reglas de filtrado).

---

## Estrategia de ampliación del conjunto de datos

### Opciones consideradas y motivos de rechazo

| Opción | Motivo de rechazo |
|---|---|
| Buscar un nuevo conjunto de datos desde cero | Escasez de fuentes de terceros confiables; no es realista |
| Verificar todo mediante muestreo aleatorio | La tasa de positivos es inferior al 0.01%, no justifica el esfuerzo del personal |
| Operar solo con detección de cambios | No es compatible con la lógica de reconfirmación periódica de pistas ya existentes (largo tiempo desde la tala); la transición de estado de 3/6 meses no funcionaría |

### Estrategia adoptada: Active Learning (ampliación de datos por etapas con participación humana)

```
Detección con el modelo Faster R-CNN existente (sin umbral) → 500 imágenes verificadas por el personal
+
Extracción de candidatos mediante detección de cambios NDVI (filtro de forma alargada) → 500 imágenes verificadas por el personal
+
178 imágenes originales (solo positivas)
─────────────────────────────
Total: ~1178 imágenes para reentrenar con YOLO
```

**Por qué mezclar dos fuentes:**
- Detecciones del modelo existente → refinamiento de patrones que el modelo ya maneja bien, aprovechando también los falsos positivos como datos de entrenamiento
- Detección de cambios → descubrimiento de patrones nuevos o atípicos que el modelo tiende a pasar por alto (mitigación de falsos negativos)

**Valor de las muestras negativas:** tanto en Faster R-CNN como en YOLO, agregar negativos explícitos (elementos confundibles que no son pistas: caminos rurales, orillas de ríos, límites de parcelas agrícolas) reduce los falsos positivos. Las 178 imágenes del predecesor eran todas positivas, y se estima que la falta de patrones negativos confundibles es una de las causas de los falsos positivos.

**Ciclo de reentrenamiento:** repetir un proceso similar cada varios años (de 3 a 10 años), para seguir la evolución de las técnicas de construcción de pistas y las mejoras en la resolución de imágenes satelitales.

---

## División de roles entre las dos fuentes de imágenes (Sentinel-2 y Planet NICFI)

El plan original (documentado en ARCHITECTURE.md) preveía entrenar un modelo YOLO independiente para cada fuente. Tras el análisis, se decidió el siguiente cambio.

### Motivo del cambio

Sentinel-2 tiene una resolución de 10 m, por lo que el ancho de una pista (15–30 m) equivale a solo 1–3 píxeles, lo que **dificulta la clasificación independiente por forma**. Planet NICFI, en cambio, tiene 4.77 m de resolución y los datos del predecesor ya están unificados en esta fuente, por lo que la detección principal basada en reconocimiento de forma se concentra en NICFI.

### División de roles confirmada

| Fuente | Rol | Frecuencia | Poder de confirmación |
|---|---|---|---|
| **Planet NICFI** | Detección principal (inferencia YOLO, clasificación por forma) | Mensual, todo el Perú | Única fuente que puede elevar el estado a `active` |
| **Sentinel-2** | Alerta temprana (solo detección de cambios, sin clasificación de forma) | Semanal, solo zonas despejadas | Solo registra `unconfirmed`, no confirma |

### Lógica de transición de estado (confirmada)

Orden de prioridad de evaluación: active → unconfirmed → inactive.

```
active:      detección NICFI dentro de los últimos 3 meses
unconfirmed: (detección NICFI entre 3 y 6 meses atrás) O (detección Sentinel dentro de los últimos 6 meses)
inactive:    detección NICFI hace más de 6 meses Y detección Sentinel también hace más de 6 meses
```

**Ejemplo concreto (imagen NICFI del 1/7 sin pista, nueva pista construida el 8/7, Sentinel detecta el cambio el 8/7):**
1. 8/7: detección de cambio por Sentinel → se registra de inmediato como `unconfirmed` (amarillo)
2. 1/8: la actualización mensual de NICFI confirma la pista → se eleva a `active` (verde)
3. Si NICFI no confirma en un plazo de 6 meses, pasa automáticamente a `inactive` (posible falso positivo exclusivo de Sentinel)

**Confianza para detecciones exclusivas de Sentinel:** no es un valor fijo, sino una confianza variable por detección (ver "Flujo de construcción" más abajo). Se calcula mediante una curva de calibración a partir de una variable continua como la magnitud del cambio NDVI.

---

## Formato de salida y filtros de candidatos de la detección de cambios de Sentinel-2 (confirmado)

**Formato de salida: coordenada puntual + puntaje** (no se usan bounding boxes). A la resolución de 10 m de Sentinel-2 no se puede obtener información de forma de la pista (1–3 píxeles de ancho), por lo que un bbox sería solo el "rectángulo circunscrito del grupo de píxeles con cambio NDVI conectado" y no aportaría precisión. Para la coincidencia de duplicados (umbral de proximidad de 500 m) basta con la coordenada puntual.

**Garantizar capacidad de respuesta en tiempo real:** no se exige confirmación en múltiples pasadas consecutivas como condición de entrada. Cada vez que se obtiene una imagen despejada, el candidato se registra de inmediato como `unconfirmed`, y la confianza se va acumulando en cada nueva detección (implementado mediante la actualización de confianza de la lógica de detección de duplicados existente, ver ARCHITECTURE.md). Esto mantiene la alerta temprana en un ciclo mínimo de 5 días, mientras que el ruido puntual (sombras de nubes, reflejos del agua, etc.) no se vuelve a detectar y por lo tanto no acumula confianza, quedando descartado de forma natural.

**Condiciones de filtrado de candidatos (confirmadas):**
- Detección de cambio NDVI (tala, pérdida de vegetación)
- Filtro de forma alargada (relación de aspecto)
- **Filtro de linealidad** (agregado) — las pistas tienden a ser rectas; las carreteras serpentean, los ríos son curvos y los frentes de deforestación son irregulares, lo que ayuda a distinguirlas
- **Umbral de longitud mínima** (agregado) — excluye pequeñas talas o parcelas agrícolas comunes

→ No se adoptaron los filtros de "aislamiento (distancia a caminos/ríos existentes)" ni "exclusión por cercanía a cuerpos de agua (para excluir minería)". Solo se agregaron condiciones directamente ligadas a la restricción física de una pista (recta, de cierta longitud), evitando condiciones que aumentaran el riesgo de falsos negativos.

**Nota:** Sentinel-2 sigue sin poder realizar una "identificación específica de pista de aterrizaje", por lo que pueden colarse candidatos erróneos (tala, minería, etc.). La confirmación final la realiza NICFI (clasificación de forma por YOLO), de modo que los candidatos erróneos no se elevan a `active` y convergen automáticamente a `inactive` en 6 meses; esta estructura de dos etapas es la premisa (ver sección Models de ARCHITECTURE.md).

### Estrategia de ajuste de parámetros (confirmada)

Los parámetros iniciales (umbral NDVI, relación de aspecto, residuo de linealidad, longitud mínima) se configuran **intencionalmente de forma laxa (para capturar de manera amplia)**, dejando la garantía de recall a esta decisión de diseño inicial. Los resultados de verificación del personal (etiquetas verdadero/falso) se ajustan a la distribución de magnitud de cambio de los verdaderos positivos (TP), y **el umbral se determina por extrapolación hasta el nivel que cubre el 99.9% de confianza en la distribución** (no simplemente "el valor mínimo observado entre los TP"; se busca capturar con cierta probabilidad incluso TP de cambios muy pequeños que aún no están en los datos observados). Por este método, el recálculo no necesariamente implica "endurecer" el umbral; también podría volverse más laxo.

Motivo: no es posible construir datos de verdad exhaustivos para verificar cuantitativamente los falsos negativos. Se consideró usar las 178 pistas conocidas (casos que el modelo del predecesor detectó claramente) para verificar el recall, pero este es un conjunto con sesgo de selección ("pistas fáciles de identificar") y no representa los casos límite que Sentinel-2 tiende a pasar por alto (etapa inicial de construcción, tala pequeña, efecto de nubes, etc.). Por lo tanto, aunque no hubiera falsos negativos entre esas 178 imágenes, esto no demostraría que el filtro es suficientemente laxo, y se descartó como método.

**Consideración sobre el tamaño de muestra:** si el número de TP es bajo (del orden de decenas a cien), leer directamente el percentil 99.9 (punto del 0.1% inferior) de la distribución empírica genera una estimación de cola inestable. Si el número de casos no es suficiente, se debe considerar una estimación paramétrica asumiendo, por ejemplo, una distribución log-normal.

---

## Integración con Global Forest Watch (GFW) y características adicionales (confirmado, añadido el 2026-07-01)

Tras consultarlo con el personal, se confirmó incorporar los siguientes tres elementos adicionales.

### Agregar GFW como fuente de alerta temprana en paralelo a Sentinel-2

Se agrega [Global Forest Watch](https://www.globalforestwatch.org/) (Integrated Deforestation Alerts, integración de GLAD-L / GLAD-S2 / RADD / DIST-ALERT) como **una segunda fuente de alerta temprana** en paralelo a la detección de cambios de Sentinel-2.

**Detalles internos de GFW (resolución y frecuencia de actualización no son uniformes):**

| Subsistema | Satélite | Resolución | Frecuencia de actualización |
|---|---|---|---|
| GLAD-L | Landsat (óptico) | 30 m | Semanal |
| GLAD-S2 | Sentinel-2 (óptico) | 10 m | Semanal (afectado por nubes) |
| RADD | Sentinel-1 (radar SAR) | 10 m | Casi en tiempo real (no afectado por nubes; cobertura sin vacíos cada 6–12 días en zonas tropicales) |

Dado que la resolución y actualidad reales varían según qué subsistema detectó el cambio, se conserva una etiqueta de origen del subsistema en cada detección de GFW, con miras a incluirla en el futuro como característica de la curva de calibración de GFW.

- **Rol:** GFW tampoco puede confirmar la forma de una pista, por lo que se le asigna el mismo rol que a Sentinel-2 ("solo alerta temprana, no puede elevar a `active`"). La regla de dominancia existente (solo NICFI puede elevar a `active`) no cambia.
- **Confianza:** la curva de calibración de Sentinel-2 (basada en el margen de cambio NDVI) no se puede aplicar directamente a GFW (las características son distintas). Se usan las características propias de GFW (nivel de confianza: valor ordinal low/nominal/high, etc.) para **construir una curva de calibración específica para GFW**.
- **Combinación de confianza cuando Sentinel-2 y GFW detectan simultáneamente:** anteriormente se descartó un "boost de corroboración" entre NICFI y Sentinel-2 por ser "arbitrario sin un modelo probabilístico adecuado", pero Sentinel-2 y GFW son ambas fuentes no confirmatorias entre sí; si se acumulan suficientes etiquetas verdadero/falso de candidatos detectados por ambas, se puede estimar estadísticamente `P(TP | margen de Sentinel-2, características de GFW)` mediante, por ejemplo, regresión logística. Se adoptará solo si la combinación puede basarse en datos y no en un valor de boost arbitrario (ver detalles en "Flujo de construcción" más abajo).
- **Extensibilidad futura:** dado que los datos de GFW también tendrán valor para funciones futuras como la predicción de cultivos de coca, el cliente de la API de GFW se implementará como un módulo genérico.

**Por qué no se construye un análisis propio de Sentinel-1 (SAR) y en su lugar se usan las alertas ya elaboradas de GFW/RADD:**

Los datos de Sentinel-1 en sí están disponibles gratuitamente bajo CC BY 4.0, al igual que RADD, pero por los siguientes motivos se opta por usar las alertas ya elaboradas de GFW/RADD en lugar de una implementación propia:

1. La frecuencia real de actualización de RADD (6–12 días en trópicos) no es dramáticamente más rápida que Sentinel-2 en cielo despejado (5 días); su ventaja principal se limita a "no verse afectado por nubes"
2. La eliminación de ruido speckle propio de los datos SAR y la corrección de distorsiones por relieve requieren más especialización que la detección de cambios NDVI en imágenes ópticas, aumentando el costo de implementación y validación
3. RADD/GLAD ya son alertas terminadas (punto + valor ordinal de confianza), por lo que no se les puede aplicar directamente el método de calibración propio usado con Sentinel-2 (características continuas propias + filtros de forma de pista [relación de aspecto, linealidad, longitud mínima] + extrapolación de umbral desde la distribución de TP)

**Tema a considerar en el futuro (capa propia de Sentinel-1):** si en el futuro se pudiera construir una capa propia que aplique filtros de forma de pista a Sentinel-1, se lograría simultáneamente "no verse afectado por nubes" y "estar optimizada para la forma de la pista", lo que podría superar en precisión tanto a Sentinel-2 (optimizado para forma pero vulnerable a las nubes) como a GFW (resistente a nubes pero de detección de deforestación genérica) actuales. Sin embargo, dado que el reconocimiento de forma en SAR es más difícil que en óptico debido al ruido speckle, se estima que la necesidad de una estructura de dos etapas con confirmación final por NICFI se mantendrá en el futuro. No se abordará en esta fase; se deja registrado como candidato de expansión para un ciclo de reentrenamiento futuro.

### Integración de Sentinel-1 (SAR) como característica de la detección de cambios, no como modelo independiente (añadido, 2026-07-01)

Propuesta de un miembro del equipo: la sección de una pista es un suelo desnudo y liso, por lo que en SAR presenta una retrodispersión débil y aparece oscura. Esta característica se considera integrar no como "modelo de detección independiente", sino como **característica adicional de la detección de cambios de Sentinel-2**. El motivo es el mismo que en el caso de GFW (a 10 m de resolución, Sentinel-1 por sí solo tiene dificultades para una clasificación independiente por forma, y su rol se superpone con el de RADD ya existente), pero el valor de "aparecer oscuro" en sí podría correlacionarse con el margen de NDVI existente, por lo que sería un desperdicio descartarlo como información.

- Se obtiene el valor de retrodispersión de Sentinel-1 (caída de intensidad de backscatter) correspondiente a cada candidato y fecha de Sentinel-2, como característica adicional
- Una vez reunidas las etiquetas verdadero/falso del Paso 2, se verifica estadísticamente si mejora el poder predictivo respecto al margen NDVI por sí solo
- Si se confirma correlación, se extiende al mismo marco que en el caso de GFW (por ejemplo, regresión logística de `P(TP | margen de Sentinel-2, característica SAR)`), combinándola con el margen NDVI en un modelo de calibración conjunto
- Si no se confirma correlación, se procede igual que con los datos de pendiente/distancia: se conserva solo como metadato, sin incorporarla al cálculo de confianza

### Datos de pendiente (Slope) y distancia a ríos/poblados (conservados como características adicionales)

Reglas empíricas del personal de campo:
- Las pistas clandestinas suelen estar cerca de ríos, caminos y poblados existentes
- Los deslizamientos de tierra solo ocurren en terrenos con pendiente (Slope), mientras que las pistas clandestinas solo existen en terrenos planos, por lo que la información de pendiente es útil para distinguir entre ambos falsos positivos

Estos datos **no se adoptan como filtro de exclusión previo** (mismo motivo por el que se descartaron "aislamiento" y "exclusión por cercanía a cuerpos de agua": el riesgo de falsos negativos). En su lugar, se conservarán la pendiente, la distancia a ríos y la distancia a poblados como metadatos de cada candidato, y una vez acumuladas suficientes etiquetas verdadero/falso del personal, se evaluará incorporarlas a la lógica de cálculo de confianza **solo si se confirma una correlación estadísticamente significativa**. Si no se confirma correlación, no se incorporarán (conservar los datos en sí tiene bajo costo, por lo que la decisión puede posponerse).

---

### Flujo de construcción (revisado, 2026-07-01)

Reorganizado en 2 pasos según su objetivo. El Paso 2 es "calibración de la propia lógica de alerta temprana (Sentinel-2, GFW)"; el Paso 3 es "recolección de datos de entrenamiento YOLO mediante confirmación NICFI"; solo el Paso 3b requiere que el Paso 2 esté completo. Las fechas son ejemplos ilustrativos; las fechas reales de adquisición se fijarán al momento de obtener los datos.

**Adquisición de imágenes**
- Sentinel-2: se obtienen pares semanales con el mismo intervalo de 7 días que en producción (ejemplo: 2025-06-01 / 2025-06-08)
- Planet NICFI: un mosaico mensual (ejemplo: 2025-06-15)
- GFW: alertas de la API para el mismo período que Sentinel-2

**Paso 2: calibración de la lógica de alerta temprana (sin usar NICFI, 700 imágenes en total)**

| Subpaso | Contenido | Cantidad | Objetivo |
|---|---|---|---|
| 2a | Detección de cambio NDVI en el par 2025-06-01/06-08 (4 condiciones configuradas de forma laxa: magnitud de cambio NDVI, forma alargada, linealidad, longitud mínima) → verificación verdadero/falso por el personal | 500 imágenes | Extrapolación del umbral de Sentinel-2 (99.9% de confianza a partir de la distribución de magnitud de cambio de TP) |
| 2b | Puntos detectados por GFW pero no capturados por la generación de candidatos de Sentinel-2 → verificación verdadero/falso por el personal | 100 imágenes | Verificar el efecto de recuperación de falsos negativos que Sentinel-2 por sí solo pasaría por alto |
| 2c | Puntos detectados por Sentinel-2 pero no por GFW, extraídos intencionalmente → verificación verdadero/falso por el personal | 100 imágenes | Verificación estadística del boost de confianza en detección simultánea Sentinel-2×GFW (comparado con el solapamiento con GFW en 2a) |

- **Limitación conocida (respecto a 2a):** en casos donde la revegetación parcial avanza después de la tala, si el intervalo es más largo (por haberse omitido por nubes), la magnitud de cambio puede ser menor que en un intervalo semanal, y es posible que los parámetros optimizados para intervalos semanales no la capturen. No se resuelve en esta fase; se registra como limitación conocida
- **Método de muestreo de 2b y 2c:** las 500 imágenes de 2a se mantienen como muestreo aleatorio. Si la tasa de solapamiento natural con GFW es extremadamente alta (por ejemplo, 480 de 500 imágenes se solapan), solo con 2a los casos de "Sentinel-2 exclusivo, no detectado por GFW" serían pocos (por ejemplo, unas 20 imágenes), insuficientes para verificar estadísticamente el efecto de boost; por eso se extrae 2c de forma intencional y separada. El cálculo de calibración del umbral de 2a se mantiene sin distorsionar el muestreo aleatorio; 2b y 2c se tratan como conteos separados

**Paso 3: recolección de datos de entrenamiento YOLO (usando NICFI, 1834 imágenes en total entre 3a, 3b y 3c; 3a y 3b pueden realizarse en paralelo, 3b requiere que el Paso 2 esté completo)**

| Subpaso | Contenido | Cantidad |
|---|---|---|
| 3a | Aplicar el Faster R-CNN existente sin umbral a NICFI (2025-06-15) → verificación verdadero/falso por el personal | 500 imágenes |
| 3b | Aplicar la lógica de 2a al siguiente par semanal (2025-06-08/06-15) → verificación verdadero/falso por el personal sobre la imagen NICFI del mismo punto | 500 imágenes |

- 178 imágenes originales + 500 de 3a + 500 de 3b = **1178 imágenes en total** para el nuevo entrenamiento de YOLO
- Las muestras provenientes de 3b se etiquetan como "originadas por disparador de Sentinel" (no para el cálculo de confianza, sino con fines de trazabilidad para futuras reevaluaciones de datos y ciclos de reentrenamiento)

**Paso 3c: ampliación multitemporal (añadido el 2026-07-01, corregido el 2026-07-01)**

Objetivo: las ubicaciones de las 178 imágenes originales + las ubicaciones confirmadas como TRUE en el paso 2a (la cantidad exacta se determinará tras completar 2a; se estima del orden de 100 ubicaciones). Para estas ubicaciones se obtienen mosaicos NICFI adicionales de **3, 6 y 9 meses antes** de la misma coordenada (3 imágenes adicionales por ubicación, es decir, 4 veces el volumen).

- **No se asigna la etiqueta Positive de forma automática.** Aunque la ubicación fue confirmada como verdadero positivo en su momento, en los cortes de 3/6/9 meses antes la pista puede no estar construida todavía o puede estar cubierta por vegetación y ser indistinguible, por lo que sería False. Las imágenes adicionales se envían a la **misma revisión T/F del personal que en los Pasos 2 y 3** (verificación completa, no una comprobación ligera)
- **La división train/val se realiza por ubicación.** Si las imágenes de múltiples fechas de la misma ubicación se distribuyen aleatoriamente entre train y val, en la práctica se estaría usando el mismo lugar tanto para entrenar como para validar, contaminando la evaluación de la capacidad de generalización
- Se eligió el intervalo fijo de 3/6/9 meses porque los datos de entrenamiento originales (178 imágenes, Pasos 3a/3b) correspondían a imágenes relativamente recientes; el objetivo es añadir variación temporal retrocediendo desde ese punto. La diversidad de estación/nubosidad se obtiene como beneficio secundario, pero el criterio de selección es el intervalo fijo, no una selección arbitraria
- Igual que en 3a y 3b, tanto las etiquetas True como False resultantes se usan como datos de entrenamiento (ver el valor de las muestras negativas en "Estrategia de ampliación del conjunto de datos" más arriba), por lo que el número de imágenes revisadas equivale al número de imágenes incorporadas al entrenamiento de YOLO

**Resumen de cifras**

| Categoría | Desglose | Cantidad |
|---|---|---|
| Revisión (Paso 2: calibración de la lógica de alerta temprana) | 2a 500 + 2b 100 + 2c 100 | 700 imágenes |
| Revisión (Paso 3: recolección de datos de entrenamiento YOLO) | 3a 500 + 3b 500 + 3c 834 (estimado) | 1834 imágenes |
| **Total de revisión** | Paso 2 + Paso 3 | **2534 imágenes** |
| Imágenes incorporadas al entrenamiento de YOLO | 178 originales + 3a 500 + 3b 500 + 3c 834 (estimado) | **2012 imágenes** |

*El Paso 2 (700 imágenes) tiene como objetivo calibrar la lógica de alerta temprana de Sentinel-2/GFW y no se usa para entrenar YOLO, por lo que el total de revisión y el total incorporado al entrenamiento no coinciden. Las 834 imágenes de 3c son una estimación (variará según la cantidad real de TRUE confirmados tras el Paso 2a).

**Paso 4: recálculo de parámetros y calibración de la confianza variable**
- Se agrupan las 500 imágenes de 2a y las 500 de 3b (1000 en total, con confirmación NICFI, tratadas con el mismo nivel de fiabilidad de etiqueta) y se recalcula el umbral de Sentinel-2 con 99.9% de confianza. Es posible que resulte más laxo que con 2a por sí sola
- Se ajusta una curva de calibración monótona (por ejemplo, regresión isotónica) entre el "margen respecto al umbral" (principalmente magnitud de cambio NDVI) de cada candidato y su etiqueta verdadero/falso, permitiendo calcular una confianza variable por detección de Sentinel-2 (no se usa un valor fijo de precisión promedio)
- Con los datos de 2b se construye por separado una curva de calibración basada en las características propias de GFW
- Se comparan 2a (solapamiento con GFW) y 2c para verificar si el boost de confianza en detección simultánea Sentinel-2×GFW puede justificarse estadísticamente (por ejemplo, mediante regresión logística de `P(TP | margen de Sentinel-2, características de GFW)`). Si no puede justificarse, no se adopta el boost
- **La iteración se limita a una sola vez:** no se repetirá el proceso de relajar aún más el umbral y volver a recolectar candidatos, ya que la relación costo-beneficio se deteriora rápidamente. La próxima revisión queda a cargo del ciclo de reentrenamiento dentro de varios años

**Total de imágenes a revisar: Paso 2 (700) + Paso 3 (1834, incluyendo 3c) = 2534 imágenes.** Ver el desglose detallado en "Resumen de cifras" más arriba

## Temas pendientes

- Viabilidad de **Weighted Boxes Fusion (WBF)** — dado que el formato de salida se definió como coordenada puntual + puntaje, es muy probable que WBF no sea necesario y baste con el emparejamiento por proximidad (tendencia hacia "prácticamente innecesario"). Falta reflejar esto en ARCHITECTURE.md
- Valores iniciales concretos de los parámetros de la lógica de detección de cambios (umbral NDVI, umbral de relación de aspecto, residuo tolerado de linealidad, umbral de longitud mínima; los valores iniciales se configuran para capturar de forma amplia)
- Alcance geográfico (todo el Perú o, de forma experimental, algunas regiones)
- Selección del método de ajuste de distribución cuando el número de TP es bajo (distribución empírica o distribución paramétrica)
- Confirmación detallada del método de autenticación de la API de GFW y de las características que proporciona (nivel de confianza, etc.)
- Modelo de combinación para el boost de confianza Sentinel-2×GFW (regresión logística, etc.): método de implementación concreto y decisión final sobre su necesidad
- Método de obtención de los datos de pendiente y distancia a ríos/poblados (fuente y formato de datos) y forma de vincularlos a los datos de Candidate
- Método concreto de incorporación a la lógica de cálculo de confianza, en caso de confirmarse correlación estadística entre los datos de pendiente/distancia y las etiquetas verdadero/falso
- **(Tema futuro, no abordado en esta fase) Capa propia de detección de pistas mediante Sentinel-1 (SAR)** — ver la sección "Integración con GFW (GLAD/RADD)". Si en el futuro se pudiera construir una capa propia no afectada por nubes y optimizada para la forma de las pistas, habría margen de mejora en precisión, pero por la especialización y el costo de implementación del procesamiento de ruido speckle propio de SAR, no se incluye en el alcance actual (aparte de la capa independiente, la "integración de Sentinel-1 como característica de la detección de cambios de Sentinel-2" descrita arriba sí forma parte del alcance actual)
- **(Idea futura, no abordada en esta fase) Detección de cultivos/campos de coca (modelo predictivo) usando las carreteras como elemento clave** — existe un patrón de cambio de cobertura terrestre en el que la deforestación avanza en la dirección en que se extienden las carreteras y se convierte en cultivos de coca; se espera una relación similar con la aparición de pistas clandestinas. La detección de carreteras en sí tiene una dificultad alta (estructuras lineales, área objetivo muy extensa, muchas fuentes de ruido como ríos, senderos de fauna y tierras de cultivo abandonadas), por lo que no es viable implementarla de inmediato; se deja registrada como candidato de expansión futura
