# Paso 1 - extraccion

- Modelo: Gemini (gemini.google.com, sin ejecucion de codigo ni herramientas)
- Version: 3.8 Flash
- Fecha: 2026-10-15

## Prompt enviado

``````
You are a symbolic execution engine. For EACH function below, enumerate ALL execution paths. For each path, give the list of path constraints: the condition of every `if` the path goes through, written as it must hold on that path.

Rules:
- Use the parameter names exactly as they appear in the code.
- Write a condition that is taken as-is, and one that is not taken as `not (condition)`.
- Do NOT include assignments, only the conditions of the `if` statements.
- One entry per path, in any order.

Answer with a JSON object and nothing else, mapping each function name to a list of paths, where each path is a list of constraint strings:

  {"nombre_funcion": [["a > 10", "b > 5"], ["a > 10", "not (b > 5)"]], ...}

```python
# Tres funciones con caminos de ejecucion bien definidos.
#
# Todas estan escritas en el estilo que el fuzzer simbolico de fuzzingbook
# puede analizar: cada condicion es una comparacion simple, cada camino asigna
# su variable de resultado una sola vez, y ninguna lleva docstring.
#
# NO MODIFICAR.


# Descuenta 5 cuando la cantidad llega a 3. Dos caminos.
def apply_coupon(total: int, qty: int) -> int:
    if qty >= 3:
        final: int = total - 5
    else:
        final: int = total
    return final


# Precio por noche segun estadia, piso y edad. Cuatro caminos.
def tarifa_noche(dias: int, piso: int, edad: int) -> int:
    if dias > 7:
        if piso > 10:
            precio: int = dias * 90
        else:
            precio: int = dias * 100
    else:
        if edad < 25:
            precio: int = dias * 70
        else:
            precio: int = dias * 120
    return precio


# Puntaje de riesgo crediticio. Ocho caminos.
def puntaje_riesgo(monto: int, mora: int, avales: int, historial: int) -> int:
    if monto > 500000:
        if mora > 30:
            if avales < 2:
                score: int = 95
            else:
                score: int = 70
        else:
            if historial < 12:
                score: int = 60
            else:
                score: int = 25
    else:
        if mora > 90:
            if avales < 1:
                score: int = 85
            else:
                score: int = 55
        else:
            if historial < 6:
                score: int = 40
            else:
                score: int = 10
    return score
```
``````

## Respuesta completa del modelo

``````json
{
"apply_coupon": [
["qty >= 3"],
["not (qty >= 3)"]
],
"tarifa_noche": [
["dias > 7", "piso > 10"],
["dias > 7", "not (piso > 10)"],
["not (dias > 7)", "edad < 25"],
["not (dias > 7)", "not (edad < 25)"]
],
"puntaje_riesgo": [
["monto > 500000", "mora > 30", "avales < 2"],
["monto > 500000", "mora > 30", "not (avales < 2)"],
["monto > 500000", "not (mora > 30)", "historial < 12"],
["monto > 500000", "not (mora > 30)", "not (historial < 12)"],
["not (monto > 500000)", "mora > 90", "avales < 1"],
["not (monto > 500000)", "mora > 90", "not (avales < 1)"],
["not (monto > 500000)", "not (mora > 90)", "historial < 6"],
["not (monto > 500000)", "not (mora > 90)", "not (historial < 6)"]
]
}

Siguientes pasos sugeridos para análisis y testing simbólico:

Generar casos de prueba con valores concretos por camino

Exportar condiciones a formato SMT-LIB o Z3 en Python
``````
