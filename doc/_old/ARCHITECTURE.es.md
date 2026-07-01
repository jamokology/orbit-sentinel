# GeoVigil Analytics — Arquitectura del Sistema

> Plataforma de detección de pistas de aterrizaje clandestinas para Perú
> Proyecto UNODC / GeoVigil Analytics

---

## Visión general

GeoVigil Analytics es un sistema de detección basado en imágenes satelitales que identifica pistas de aterrizaje clandestinas en Perú mediante modelos de detección de objetos YOLO. Los resultados de detección se publican en un panel web a través de un pipeline diario automatizado.

```
Imágenes satelitales (Sentinel-2 + Planet NICFI)
        │
        ▼
  Estación de trabajo (Windows, PC compartida)
  ├─ Cron semanal vía el Programador de tareas
  ├─ NICFI: inferencia YOLO (basada en forma, confirmatoria)
  ├─ Sentinel-2: lógica de detección de cambios (no basada en ML, solo disparador)
  ├─ Fusión por regla de dominancia (la confirmación de NICFI siempre prevalece; sin WBF ni combinación de puntajes)
  └─ git push → data/detections.json
        │
        ▼
  Repositorio en GitHub (rama main)
        │
        ▼
  Cloudflare Pages (despliegue automático)
        │
        ▼
  Panel web (Vanilla JS + Leaflet)
```

---

## Fuentes de imágenes satelitales

Se utilizan dos fuentes complementarias en paralelo para maximizar la cobertura y la frecuencia de actualización.

### Fuente 1 — Sentinel-2 (ESA Copernicus)

| Propiedad | Valor |
|---|---|
| Resolución | 10 m (bandas visibles) |
| Frecuencia de actualización | Cada 5 días (imágenes en bruto) |
| Cobertura de nubes | Afectada por nubes — filtrada a menos del 20% de cobertura de nubes |
| Costo | Gratuito, datos abiertos |
| Acceso | API de Copernicus Data Space / librería Python `sentinelsat` / `eodag` |

### Fuente 2 — Planet NICFI (nivel gratuito)

| Propiedad | Valor |
|---|---|
| Resolución | 4.77 m |
| Frecuencia de actualización | Mosaico mensual libre de nubes |
| Cobertura de nubes | No afectada — mosaico pre-compuesto |
| Costo | Gratuito (NICFI Nivel 1, financiado por Noruega) |
| Acceso | API Python de Google Earth Engine |
| Cobertura geográfica | Bosques tropicales, incluyendo todo Perú |

### Justificación para usar ambas fuentes

| Escenario | Fuente utilizada | Frecuencia |
|---|---|---|
| Cielo despejado sobre el área objetivo | Sentinel-2 | Hasta semanal |
| Alta cobertura de nubes | Mosaico de Planet NICFI | Mensual (garantizado) |
| Ambas disponibles | Ambas — inferencia combinada | Semanal / mensual |

El uso de ambas fuentes garantiza que cada área objetivo reciba al menos una actualización de detección por mes, independientemente de las condiciones de nubosidad, mientras que las áreas con cielo despejado pueden actualizarse con mayor frecuencia mediante Sentinel-2.

---

## Pipeline de aprendizaje automático

> **Revisado el 2026-06-30** — ver [CONCEPT_NOTE.es.md](CONCEPT_NOTE.es.md) para el razonamiento detrás de esta revisión. El diseño original de dos modelos independientes + WBF (conservado más abajo como referencia histórica) fue reemplazado por un único modelo confirmatorio (NICFI) más una capa de alerta temprana por detección de cambios (Sentinel-2).

### Modelos (diseño actual)

| Componente | Imágenes | Rol | ¿Confirma `active`? |
|---|---|---|---|
| `model_planet.pt` (YOLO) | Mosaicos de Planet NICFI | Detección principal — detección de objetos basada en forma | Sí — única fuente que puede confirmar/elevar a `active` |
| Lógica de detección de cambios (no ML o ligera) | Imágenes Sentinel-2 | Alerta temprana — señala cambios por deforestación, sin clasificación de forma | No — solo produce entradas `unconfirmed` |

**Por qué Sentinel-2 no tiene un modelo YOLO independiente:** a una resolución de 10 m, una pista (15–30 m de ancho) abarca solo 1–3 píxeles, demasiado grueso para una clasificación confiable basada en forma. El valor de Sentinel-2 está en la frecuencia de actualización (semanal, si el cielo está despejado), no en la discriminación de forma. Se usa como disparador, no como confirmador.

**Confianza de detección exclusiva de Sentinel:** una confianza variable por detección, no un valor fijo. Cada candidato de detección de cambios de Sentinel-2 tiene una característica continua de "margen" (principalmente la magnitud del cambio NDVI en relación con el umbral de decisión). Una curva de calibración monótona (regresión isotónica, ajustada con los lotes de verificación del personal — ver [CONCEPT_NOTE.es.md](CONCEPT_NOTE.es.md) "Flujo de construcción") mapea este margen a una probabilidad empírica de ser un verdadero positivo, usada como puntaje de confianza para esa detección.

### Combinación de confianza de NICFI y Sentinel-2 — sin WBF, sin combinación de puntajes (confirmado)

**Decidido: no se usa WBF, y las confianzas nunca se combinan numéricamente (sin promedio ponderado).** La justificación original de WBF (fusionar los cuadros delimitadores de dos modelos independientes mediante IoU) asumía dos modelos YOLO ejecutándose en paralelo con puntajes comparables a nivel de cuadro. Bajo el diseño revisado, Sentinel-2 ya no produce cuadros delimitadores (solo salida de punto + puntaje), por lo que la fusión basada en IoU no puede aplicarse mecánicamente. Pero más allá de eso: incluso la idea subyacente de promediar los dos valores de confianza se rechaza, porque los dos puntajes miden cosas distintas (NICFI = confianza de clasificación por forma; Sentinel = puntaje proxy de "¿este cambio NDVI se parece a una pista?" con un techo mucho más bajo, ya que Sentinel no puede resolver la forma a 10 m) y las dos fuentes no son pares en la máquina de estados — solo NICFI puede confirmar/elevar a `active`.

**Regla de dominancia (confirmada):** `confidence` no se deriva del `status` actual — es el puntaje asociado al **evento de actualización más reciente**, sujeto a dominancia al escribir:
- Una detección de NICFI **siempre** sobrescribe `confidence`/`source` con su propio puntaje YOLO, sin importar lo que hubiera antes.
- Una detección de Sentinel-2 sobrescribe `confidence`/`source` con su propio puntaje calibrado **solo si el `source` actual del registro no es `"Planet NICFI"`** (es decir, Sentinel-2 puede actualizar un registro exclusivo de Sentinel-2, pero nunca puede sobrescribir un valor confirmado por NICFI).
- Si no llega una nueva detección, `confidence`/`source` simplemente conservan su último valor — incluso a través de una transición de `status` de `active` a `unconfirmed` (por ejemplo, un registro confirmado por NICFI que supera los 3 meses sin reconfirmación sigue mostrando el último puntaje de NICFI, no un valor vacío ni derivado de Sentinel).
- Se consideró un "boost de corroboración" (pequeño incremento de confianza cuando ambas fuentes detectan de forma independiente la misma ubicación) y **se rechazó** — la magnitud del boost sería arbitraria sin un modelo probabilístico adecuado, y agrega complejidad con un beneficio poco claro. No implementado.

<details>
<summary>Diseño original (reemplazado, conservado como referencia)</summary>

Originalmente se planeaban dos modelos YOLO separados:

| Modelo | Imágenes de entrenamiento | Estado |
|---|---|---|
| `model_planet.pt` | Mosaicos de Planet NICFI | Por entrenar / heredado del predecesor |
| `model_sentinel.pt` | Imágenes Sentinel-2 | Por entrenar / heredado del predecesor |

Cuando las detecciones de ambos modelos estuvieran disponibles para la misma área geográfica, los resultados se fusionarían usando **Weighted Boxes Fusion (WBF)**:

```python
from ensemble_boxes import weighted_boxes_fusion

boxes, scores, labels = weighted_boxes_fusion(
    [boxes_nicfi, boxes_sentinel],
    [scores_nicfi, scores_sentinel],
    [labels_nicfi, labels_sentinel],
    iou_thr=0.5,
    skip_box_thr=0.4,
)
```

</details>

---

## Ejecución del pipeline (estación de trabajo)

### Estructura de directorios

```
py/
  pipeline/
    fetch_sentinel.py    # Obtención de imágenes Sentinel-2 (Copernicus Data Space)
    fetch_planet.py      # Obtención del mosaico mensual de Planet NICFI
    run_inference.py     # Inferencia YOLO (solo NICFI)
    change_detection.py  # Detección de cambio NDVI de Sentinel-2 + filtros de forma (no ML)
    merge.py             # Fusión por regla de dominancia (confirmación de NICFI prevalece; sin WBF/combinación de puntajes)
    update_json.py       # Actualización de detections.json (deduplicación y gestión de estado)
    git_push.py          # Commit y push a GitHub
  daily_run.py           # Punto de entrada invocado por el Programador de tareas
web/
  data/
    detections.json      # Salida consumida por el panel web
```

### Programación de ejecución

- **Disparador:** Programador de tareas de Windows, semanal (por ejemplo, cada lunes a las 02:00 hora local)
- **Pasos:**
  1. Obtener las últimas imágenes de Sentinel-2 para las regiones objetivo (omitir si la cobertura de nubes supera el 20%)
  2. Obtener el último mosaico de Planet NICFI si hay un nuevo mosaico mensual disponible
  3. Ejecutar inferencia YOLO de NICFI y/o detección de cambios de Sentinel-2 sobre las imágenes disponibles
  4. Fusionar resultados usando la regla de dominancia (ver sección Modelos) — sin WBF, sin combinación de puntajes
  5. Escribir `data/detections.json`
  6. `git commit` + `git push` a la rama `main`

### Autenticación de GitHub en la estación de trabajo

Se utiliza una **clave de despliegue (SSH) con alcance limitado al repositorio** o un **token de acceso personal de grano fino** limitado a este repositorio con permiso `contents: write`. Esto evita almacenar credenciales de cuenta completas en una máquina compartida.

---

## Formato de salida — `data/detections.json`

```json
{
  "generated_at": "2026-06-22T02:00:00Z",
  "is_demo": false,
  "detections": [
    {
      "lat": -3.7491,
      "lon": -73.2538,
      "confidence": 0.93,
      "detected_at": "2026-01-10 08:22",
      "confirmed_at": "2026-06-22 02:15",
      "status": "active",
      "source": "Planet NICFI"
    }
  ]
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `generated_at` | Cadena ISO 8601 | Marca de tiempo de la ejecución del pipeline |
| `is_demo` | booleano | `true` para datos de demostración/prueba, `false` para detecciones reales |
| `lat` / `lon` | flotante | Coordenadas WGS84 del centroide de la pista detectada |
| `confidence` | flotante (0–1) | Confianza solo de la fuente confirmatoria — ver "Combinación de confianza de NICFI y Sentinel-2" arriba. No es un valor combinado/ensamblado; los registros `"active"` muestran el puntaje YOLO de NICFI, los registros `"unconfirmed"` muestran el puntaje calibrado de Sentinel-2 |
| `detected_at` | cadena | Marca de tiempo de la primera detección |
| `confirmed_at` | cadena | Marca de tiempo de la detección más reciente (actualizada en cada ejecución del pipeline) |
| `status` | cadena | Ver la tabla de ciclo de vida más abajo |
| `source` | cadena | `"Sentinel-2"` o `"Planet NICFI"` — la fuente cuya confianza se muestra actualmente (ver regla de dominancia). No existe valor `"Ensemble"`; no se usa WBF/combinación de puntajes |

---

## Ciclo de vida del registro de detección

Cada registro de detección persiste en `detections.json` y transita por los siguientes estados. **Evaluado en orden de prioridad: `active` → `unconfirmed` → `inactive`** (una condición `unconfirmed` puede técnicamente superponerse con `active`; `active` siempre prevalece).

```
active:      detección NICFI dentro de los últimos 3 meses
unconfirmed: (detección NICFI hace 3–6 meses) O (detección Sentinel-2 dentro de los últimos 6 meses)
inactive:    detección NICFI hace 6+ meses (o nunca) Y detección Sentinel-2 hace 6+ meses (o nunca)
```

Solo las detecciones de NICFI pueden producir/confirmar el estado `active` — Sentinel-2 por sí solo solo puede llevar un registro a `unconfirmed`. Esto refleja el rol de Sentinel-2 como disparador de alerta temprana, no como fuente confirmatoria (ver sección Modelos arriba).

| Estado | Condición | Visualización en el mapa | Verificación de duplicados |
|---|---|---|---|
| `active` | Confirmado por NICFI dentro de los últimos 3 meses | Verde `#3fb950`, pulsante | Sí |
| `unconfirmed` | NICFI hace 3–6 meses, o exclusivo de Sentinel-2 dentro de 6 meses | Amarillo `#d29922`, estático | Sí |
| `inactive` | Ninguna fuente dentro de los últimos 6 meses | Oculto | **No** |

**Ejemplo desarrollado:** el mosaico NICFI del 1 de julio no muestra ninguna pista. El 8 de julio aparece una nueva pista clandestina; Sentinel-2 detecta el cambio de vegetación la misma semana → el registro se inserta como `unconfirmed` (amarillo) de inmediato. El 1 de agosto, el mosaico mensual de NICFI confirma la forma → el registro se eleva a `active` (verde). Si NICFI nunca lo confirma dentro de los 6 meses posteriores a la señal de Sentinel-2, el registro pasa a `inactive` (tratado como probable falso positivo de Sentinel-2).

### Lógica de detección de duplicados

Cuando llega una nueva detección, el pipeline verifica si existe un registro (en estado `active` o `unconfirmed`) dentro de **500 m** de las nuevas coordenadas:

- **Coincidencia encontrada:** siempre se actualiza `confirmed_at`. `confidence`/`source` se actualizan según la regla de dominancia al escribir (ver sección Modelos arriba) — una detección de NICFI siempre sobrescribe; una detección de Sentinel-2 sobrescribe solo si el `source` actual del registro no es `"Planet NICFI"`. `detected_at` se mantiene sin cambios.
- **Coincidencia encontrada (`inactive`):** se trata como una nueva detección independiente — la pista puede haberse reabierto o puede tratarse de una nueva construcción cercana.
- **Sin coincidencia:** se inserta un nuevo registro con `status: "active"` si proviene de NICFI, o `status: "unconfirmed"` si proviene de Sentinel-2.

### Por qué se conservan los registros `inactive`

Los registros nunca se eliminan. Establecer `status: "inactive"` en lugar de eliminar el registro cumple dos propósitos:

1. **Registro histórico:** proporciona un conjunto de datos a largo plazo sobre la actividad de las pistas (útil para informes y análisis de tendencias).
2. **Evita una re-detección falsa:** asegura que una nueva detección cercana no se combine incorrectamente con un registro obsoleto de un período operativo distinto.

### Decaimiento de la confianza y abandono natural

A medida que se abandona una pista clandestina, la vegetación recupera gradualmente el área despejada. Esto se refleja de forma natural en el puntaje de confianza del modelo a lo largo de ejecuciones sucesivas del pipeline:

```
Recién despejada    → confianza 0.9+  → status: active
Pasto creciendo     → confianza 0.7–0.8
Parcialmente cubierta → confianza 0.5–0.6 → status: unconfirmed
Completamente revegetada → no detectada → status: inactive (después de 6 meses)
```

---

## Interfaz del panel — indicador de estado

Cada tarjeta emergente de detección muestra un pequeño indicador circular de estado en la esquina superior derecha, separando visualmente la **actualidad** (status) de la **confianza** (color del marcador).

| Indicador | Color | Animación | Significado |
|---|---|---|---|
| ● | Verde `#3fb950` | Brillo pulsante | `active` — confirmado dentro de los últimos 3 meses |
| ● | Amarillo `#d29922` | Estático | `unconfirmed` — sin reconfirmar en 3–6 meses |
| — | — | — | `inactive` — oculto del mapa |

Los mismos indicadores aparecen en la leyenda de la barra lateral junto a la leyenda de color de confianza existente.

**Justificación del diseño:** el color del marcador ya codifica el nivel de confianza (rojo / naranja / azul). Usar un punto pequeño separado para el estado evita sobrecargar un único canal visual y mantiene ambas dimensiones legibles de un vistazo.

---

## Panel web (Cloudflare Pages)

- **Framework:** Vanilla JS + Leaflet (`web/index.html`)
- **Hospedaje:** Cloudflare Pages (despliegue automático al hacer push a `main`, directorio de publicación: `web/`)
- **Carga de datos:** `web/data/detections.json` obtenido al cargar la página
- **Idiomas:** alternancia entre japonés / inglés
- **Funciones:** filtro de confianza, filtro de fuente, mapa interactivo Leaflet, tarjetas emergentes de detección con indicador de estado

### Flujo de despliegue

```
git push (estación de trabajo) → GitHub main → compilación automática de Cloudflare Pages → panel en vivo actualizado
```

No se requiere ningún paso de despliegue manual.

---

## Elementos pendientes (al 2026-06-30)

Ver [HANDOFF.md](HANDOFF.md) para la lista priorizada de acciones del próximo hilo de trabajo. Resumen:

| Elemento | Responsable | Estado |
|---|---|---|
| Modelo Faster R-CNN del predecesor + conjunto de datos de 178 imágenes (Brasil, Planet NICFI) | Recibido | Analizado — ver [CONCEPT_NOTE.es.md](CONCEPT_NOTE.es.md) |
| Ejecutar el modelo existente sobre nuevas imágenes, generar ~500 detecciones candidatas para revisión del personal | Propio | No iniciado |
| Construir lógica de detección de cambios NDVI + filtro de forma, generar ~500 mosaicos candidatos para revisión del personal | Propio | No iniciado |
| Verificación por el personal de ~1000 candidatos (etiquetado verdadero/falso) | Personal | No iniciado |
| Reentrenar como YOLO con el conjunto de datos combinado (178 + ~1000 verificados) | Propio | No iniciado |
| Decidir el destino de WBF ahora que Sentinel-2 no tiene un modelo independiente | Propio | Pregunta abierta |
| Acceso a la API de GEE para Planet NICFI (nivel gratuito) | Propio | Por configurar |
| Credenciales de la API de Copernicus Data Space | Propio | Por configurar |
| Configuración de la clave de despliegue SSH en la estación de trabajo | Propio | Por configurar después de completar el código del pipeline |

---

## Pila tecnológica

| Capa | Tecnología |
|---|---|
| Detección de objetos | YOLOv? (Ultralytics) |
| Ensamble | `ensemble-boxes` (WBF) |
| Datos satelitales | `sentinelhub` (Copernicus Data Space), Planet SDK v2 |
| Pipeline backend | Python 3.12 |
| Panel | Vanilla JS + Leaflet |
| Hospedaje | Cloudflare Pages |
| Control de versiones | GitHub |
| Programador | Programador de tareas de Windows |
| Gestión de paquetes | `uv` |
