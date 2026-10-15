# Actividad 4 — Symbolic Fuzzing con LLM

**Nombre:** Monserrat Diaz
**Número de alumno/a:** 21626545

**Modelo utilizado:** Gemini (gemini.google.com, sin ejecucion de codigo ni herramientas)
**Versión:** 3.8 Flash
**Fecha de las consultas:** 2026-10-15
**Motor de caminos:** enumerador propio (fuzzingbook no disponible)

Tres chats nuevos, una sola solicitud en cada uno, sin iterar. Evidencia completa en `prompts/`.

---

## Tabla 1 — Paso 1: extracción

| Función | Caminos reales | Propuestos | Equivalentes | Faltantes | De más |
|---|---|---|---|---|---|
| apply_coupon | 2 | 2 | 2 | 0 | 0 |
| tarifa_noche | 4 | 4 | 4 | 0 | 0 |
| puntaje_riesgo | 8 | 8 | 8 | 0 | 0 |

### Caminos que el modelo no encontró

Ninguno. Los 14 caminos reales fueron propuestos y Z3 confirmó la equivalencia lógica de cada uno.

| Función | Camino faltante | Por qué crees que se le escapó |
|---|---|---|
| — | — | No hubo faltantes. |

### Caminos de más

Ninguno. No propuso caminos infactibles ni duplicados.

| Función | Camino propuesto | Diagnóstico |
|---|---|---|
| — | — | No hubo caminos de más. |

Nota: la respuesta del modelo trajo, después del JSON, un párrafo de "siguientes pasos sugeridos" que el prompt no pedía (el prompt decía "nothing else"). No afectó la extracción; el JSON se guardó sin ese texto en `inputs/constraints_llm.json` y la respuesta completa está en `prompts/paso1.md`.

---

## Tabla 2 — Paso 2: resolución

| Config | Extrae | Resuelve | Satisfacen | Caminos alcanzados |
|---|---|---|---|---|
| A | fuzzer | Z3 | 14/14 | 14/14 |
| B | LLM | LLM | 14/14 | 14/14 |
| C | LLM | Z3 | 14/14 | 14/14 |
| D | fuzzer | LLM | 14/14 | 14/14 |

Detalle por función (satisfacen / alcanzados), idéntico en las cuatro configuraciones: apply_coupon 2/2, tarifa_noche 4/4, puntaje_riesgo 8/8.

---

## Análisis

El modelo acertó todo. Según el enunciado (sección 2.7) eso también es dato: las conclusiones de abajo dicen qué se puede y qué no se puede afirmar con una medición donde no hay ninguna falla que atribuir.

**1. Compara B con C. ¿El modelo supo extraer las restricciones pero no resolverlas, o ya fallaba al extraer? Justifica con los dos números.**

Ninguna de las dos cosas. B alcanza 14/14 caminos y C alcanza 14/14, así que la diferencia es 0 y resolver no es el cuello de botella. Tampoco lo es extraer: la Tabla 1 muestra 14/14 equivalentes, 0 faltantes y 0 de más, que es justamente la razón por la que C no puede quedar por debajo de B. Con este código el modelo no falló en ninguna de las dos etapas, así que la medición no permite atribuir una falla.

**2. Compara D con A. Con restricciones correctas de entrada, ¿cuántas resolvió bien el modelo? ¿Qué agrega esto a la comparación anterior?**

D satisface 14/14 y alcanza 14/14, igual que A (el solver). Con restricciones correctas el modelo resolvió bien los 14 caminos. Lo que agrega: B y C mezclan la calidad de la extracción con la de la resolución, porque el modelo resuelve sus propias restricciones y un error de extracción podría quedar oculto. D separa eso, porque las restricciones vienen del fuzzer y son correctas por construcción.

Una precaución sobre la validez de esta comparación: como la extracción fue perfecta, el prompt del paso 2 con las restricciones del modelo y el prompt con las del fuzzer quedaron con el mismo texto (solo difieren los encabezados que imprime el notebook). Los chats de B y D son por tanto dos muestras de la misma pregunta, no dos condiciones distintas. Las respuestas no son idénticas: en `puntaje_riesgo` paths 4 y 5, el chat de D usó `historial: 6` y el de B usó `historial: 12`. Ambas asignaciones son válidas, porque esa variable no aparece en las restricciones de esos caminos. Es variación sin efecto, no un error.

**3. ¿La dificultad creció con el número de caminos? Compara el desempeño en `apply_coupon` (2 caminos) contra `puntaje_riesgo` (8).**

No creció en lo medido: `apply_coupon` 2/2 y `puntaje_riesgo` 8/8, en B, C y D. Una razón por la que 8 caminos no es más difícil en este código: en cada camino, cada variable aparece a lo sumo en una comparación contra una constante (por ejemplo `monto > 500000 AND mora > 30 AND avales < 2`). Las restricciones son independientes entre variables y se resuelven una por una, sin interacción. Esto no dice que no crecería con restricciones acopladas o aritmética no lineal, que no se midieron.

**4. ¿Hubo alguna asignación que *satisficiera* las restricciones pero *no alcanzara* el camino al ejecutarse? Si la hay, explica cómo es posible. Si no, explica por qué en este código no puede ocurrir.**

No hubo: satisfacen 14/14 y alcanzan 14/14 en todas las configuraciones. En este código tampoco puede ocurrir con restricciones bien extraídas. Cada camino se define por la conjunción de todos los `if` que atraviesa, y las ramas de un mismo `if` son complementarias, así que los caminos particionan el espacio de entradas. Una asignación que cumple la conjunción completa de un camino ejecuta ese camino, y ningún otro. El caso que sí puede divergir es una extracción incompleta o incorrecta, por ejemplo una conjunción a la que le falta un `if`: la asignación la satisface y puede caer en otro camino. Aquí la extracción fue 14/14 equivalente, por lo que ese escenario no se dio.

**5. De los errores de resolución, ¿qué tipo predominó? Mira especialmente los valores en el borde exacto de una comparación.**

No hubo errores de resolución, así que no hay tipo predominante. El modelo sí eligió valores exactamente en el borde de las comparaciones, y acertó el lado correcto en todos: `qty` 3 y 2 (`>= 3`), `dias` 8 y 7, `piso` 11 y 10, `edad` 24 y 25, `monto` 500001 y 500000, `mora` 31 y 30 y 91 y 90, `avales` 1 y 2, `historial` 11 y 12 y 5 y 6. Las comparaciones `>=` y `<` en el borde (`qty >= 3` con 3, `edad < 25` con 24) son donde habría sido más fácil equivocarse por uno.

**6. El fuzzer simbólico de la guía no maneja condiciones con `and` o `or`, ni variables que se reasignan. ¿El modelo tuvo esas mismas limitaciones, o las suyas son de otra naturaleza?**

Con estos datos no puedo afirmar que el modelo no las tenga: las tres funciones se escribieron a propósito en el estilo restringido (sin `and`/`or`, sin reasignaciones, sin docstring), así que esas condiciones nunca se pusieron a prueba. Lo que sí se observó es que el modelo no tuvo la limitación del fuzzer en el sentido de que no depende de la sintaxis del código para trabajar: leyó el código y escribió `not (cond)` según el prompt. Las limitaciones del fuzzer son de implementación (falla con `Z3Exception`, devuelve vacío o lanza excepción). Las del modelo, si existen, serían de otra naturaleza: errores de razonamiento o aritmética que no producen una excepción, sino un valor equivocado sin aviso. Esa diferencia es una hipótesis, no un resultado de esta medición.

**7. Con lo que mediste: ¿para qué parte de un fuzzer simbólico usarías un LLM, y para cuál un solver? Justifica con tus números.**

La medición no discrimina entre ambos (todo 14/14), así que mi respuesta se apoya en el diseño más que en los números. Usaría al LLM para la extracción: lo hizo perfecto aquí (14/14 equivalentes) y no tiene las fronteras sintácticas del fuzzer (`and`/`or`, reasignaciones, docstrings), así que podría cubrir código que el fuzzer no puede analizar. Usaría al solver para la resolución: A, C y el solver dan 14/14 por construcción y el resultado es verificable y determinista, mientras que el modelo puede fallar sin avisar en casos más difíciles que los medidos. Y en cualquier caso, los caminos que extraiga el LLM deben verificarse con Z3 por equivalencia lógica, como hace este notebook. Limitación: una sola corrida por configuración, un solo modelo y funciones de tamaño pequeño con restricciones independientes, así que 14/14 no se puede extrapolar a código más grande.



PD: me ayude con ia para que este reporte quedara mejor redactado y mas ordenado u.u

por otra parte me paso lo mismo que se mencionaba en el foro pero la vdd dsp no tengo tiempo de modificar esta tarea asi que no pude esperar la respuesta del foro. si algo esta mal prdn u.u