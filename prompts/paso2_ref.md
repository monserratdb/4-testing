# Paso 2 - resolver las del fuzzer simbolico

- Modelo: Gemini (gemini.google.com, sin ejecucion de codigo ni herramientas)
- Version: 3.8 Flash
- Fecha: 2026-10-15

## Prompt enviado

``````
Below is a list of path constraints. For EACH path, give concrete integer values for the variables that satisfy ALL of its constraints at the same time. If a path is impossible, use null.

Answer with a JSON object and nothing else, with the same structure, where each path becomes an object of variable values:

  {"nombre_funcion": [{"a": 11, "b": 6}, {"a": 11, "b": 0}], ...}

apply_coupon (variables: total, qty)
  path 0: qty >= 3
  path 1: not (qty >= 3)

tarifa_noche (variables: dias, piso, edad)
  path 0: dias > 7 AND piso > 10
  path 1: dias > 7 AND not (piso > 10)
  path 2: not (dias > 7) AND edad < 25
  path 3: not (dias > 7) AND not (edad < 25)

puntaje_riesgo (variables: monto, mora, avales, historial)
  path 0: monto > 500000 AND mora > 30 AND avales < 2
  path 1: monto > 500000 AND mora > 30 AND not (avales < 2)
  path 2: monto > 500000 AND not (mora > 30) AND historial < 12
  path 3: monto > 500000 AND not (mora > 30) AND not (historial < 12)
  path 4: not (monto > 500000) AND mora > 90 AND avales < 1
  path 5: not (monto > 500000) AND mora > 90 AND not (avales < 1)
  path 6: not (monto > 500000) AND not (mora > 90) AND historial < 6
  path 7: not (monto > 500000) AND not (mora > 90) AND not (historial < 6)
``````

## Respuesta completa del modelo

``````json
{
"apply_coupon": [
{"total": 100, "qty": 3},
{"total": 100, "qty": 2}
],
"tarifa_noche": [
{"dias": 8, "piso": 11, "edad": 30},
{"dias": 8, "piso": 10, "edad": 30},
{"dias": 7, "piso": 5, "edad": 24},
{"dias": 7, "piso": 5, "edad": 25}
],
"puntaje_riesgo": [
{"monto": 500001, "mora": 31, "avales": 1, "historial": 12},
{"monto": 500001, "mora": 31, "avales": 2, "historial": 12},
{"monto": 500001, "mora": 30, "avales": 0, "historial": 11},
{"monto": 500001, "mora": 30, "avales": 0, "historial": 12},
{"monto": 500000, "mora": 91, "avales": 0, "historial": 6},
{"monto": 500000, "mora": 91, "avales": 1, "historial": 6},
{"monto": 500000, "mora": 90, "avales": 0, "historial": 5},
{"monto": 500000, "mora": 90, "avales": 0, "historial": 6}
]
}
``````
