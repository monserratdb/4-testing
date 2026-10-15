"""Motor de la Actividad 4 - Symbolic Fuzzing con LLM.

Tres piezas:

  1. Caminos de referencia. Los obtiene de fuzzingbook si esta disponible, y si
     no, de un enumerador propio equivalente para el estilo restringido de
     src/funciones.py. Ambos producen lo mismo.

  2. Traduccion de restricciones a Z3. Tolera como escriba el modelo la
     negacion y los operadores.

  3. Evaluacion. Para cada configuracion mide: caminos enumerados, equivalencia
     de restricciones, y que camino alcanza realmente cada input al ejecutarse.
"""

import ast
import contextlib
import importlib
import inspect
import json
import os
import re
import sys

import z3


RUTA_SUT = "src/funciones.py"
FUNCIONES = ["apply_coupon", "tarifa_noche", "puntaje_riesgo"]

RESULTADOS = {}
_MOTOR_CAMINOS = None


# ==========================================================================
# 1. Caminos de referencia
# ==========================================================================

def _enumerar_ast(fn):
    """Enumera los caminos de una funcion con ifs anidados y condiciones
    simples. Devuelve [[(condicion_fuente, tomada), ...], ...] en el orden en
    que aparecen, igual que fuzzingbook."""
    fuente = inspect.getsource(fn)
    arbol = ast.parse(fuente).body[0]

    def recorrer(cuerpo, acumulado):
        for nodo in cuerpo:
            if isinstance(nodo, ast.If):
                cond = ast.unparse(nodo.test)
                return (recorrer(nodo.body, acumulado + [(cond, True)])
                        + recorrer(nodo.orelse, acumulado + [(cond, False)]))
        return [acumulado]

    return recorrer(arbol.body, [])


@contextlib.contextmanager
def _silencio():
    """Silencia salida y errores incluso de subprocesos: fuzzingbook lanza pip
    al importarse y escribe directo al descriptor."""
    nulo = os.open(os.devnull, os.O_RDWR)
    guardados = (os.dup(1), os.dup(2))
    try:
        os.dup2(nulo, 1)
        os.dup2(nulo, 2)
        yield
    finally:
        os.dup2(guardados[0], 1)
        os.dup2(guardados[1], 2)
        for fd in guardados:
            os.close(fd)
        os.close(nulo)


def _caminos_fuzzingbook(fn):
    """Intenta usar fuzzingbook. Devuelve None si no esta disponible o falla.

    El import se intenta solo si el paquete existe: fuzzingbook ejecuta pip al
    importarse y sin esta guarda ensucia la salida con errores de instalacion
    cuando no esta presente."""
    import importlib.util
    if importlib.util.find_spec("fuzzingbook") is None:
        return None
    try:
        with _silencio():
            from fuzzingbook.SymbolicFuzzer import SimpleSymbolicFuzzer
            import fuzzingbook.SymbolicFuzzer as sf
    except Exception:
        return None
    try:
        with _silencio():
            f = SimpleSymbolicFuzzer(fn)
            rutas = f.get_all_paths(f.fnenter)
            exec(sf.define_symbolic_vars(f.used_variables, ""), sf.__dict__)
        salida = []
        for p in rutas:
            crudas = f.extract_constraints(p)
            # descartamos las asignaciones (var == expr): solo nos interesan
            # las condiciones de los if
            conds = [c for c in crudas if not _es_asignacion(c, fn)]
            salida.append(conds)
        return salida
    except Exception:
        return None


def _es_asignacion(restriccion, fn):
    """True si la restriccion es la asignacion de la variable de resultado."""
    params = set(inspect.signature(fn).parameters)
    m = re.match(r"^\s*([A-Za-z_]\w*)\s*==", restriccion)
    return bool(m) and m.group(1) not in params


def _normalizar_cond(c):
    """Lleva una restriccion al estilo 'not (cond)' o 'cond'."""
    c = c.strip()
    m = re.match(r"^(?:z3\.)?Not\s*\((.*)\)\s*$", c, re.S)
    if m:
        return "not (%s)" % m.group(1).strip()
    return c


def caminos_referencia(fn):
    """Lista de caminos; cada uno es una lista de condiciones normalizadas."""
    global _MOTOR_CAMINOS
    fb = _caminos_fuzzingbook(fn)
    if fb is not None:
        _MOTOR_CAMINOS = "fuzzingbook"
        return [[_normalizar_cond(c) for c in p] for p in fb]
    _MOTOR_CAMINOS = "enumerador propio (fuzzingbook no disponible)"
    return [[(c if tomada else "not (%s)" % c) for c, tomada in p]
            for p in _enumerar_ast(fn)]


def motor_caminos():
    return _MOTOR_CAMINOS or "sin determinar"


# ==========================================================================
# 2. Restricciones -> Z3
# ==========================================================================

_REEMPLAZOS = [
    (r"(?<![\w.])z3\.Not\s*\(", "Not("),
    (r"(?<![\w.])Not\s*\(", "Not("),
    (r"(?<![\w.])NOT\s*\(", "Not("),
    (r"(?<![\w.])not\s+", "Not_PREFIJO "),
    (r"!\s*\(", "Not("),
    (r"(?<![=!<>])=(?![=])", "=="),
    (r"<>", "!="),
    (r"≥", ">="), (r"≤", "<="), (r"≠", "!="), (r"¬", "Not_PREFIJO "),
    (r"(?<![\w.])AND(?![\w])", "and"),
    (r"(?<![\w.])OR(?![\w])", "or"),
]


def _a_expresion(texto):
    """Normaliza como el modelo haya escrito la restriccion."""
    t = texto.strip().rstrip(";").strip()
    for patron, nuevo in _REEMPLAZOS:
        t = re.sub(patron, nuevo, t)
    # 'not (x > 1)' -> 'Not(x > 1)'
    t = re.sub(r"Not_PREFIJO\s*\((.*)\)\s*$", r"Not(\1)", t, flags=re.S)
    t = re.sub(r"Not_PREFIJO\s*(.+)$", r"Not(\1)", t, flags=re.S)
    return t


def a_z3(restricciones, variables):
    """Convierte una lista de restricciones en una conjuncion de Z3.

    variables: nombres de los parametros de la funcion.
    Devuelve (expresion, problemas)."""
    entorno = {v: z3.Int(v) for v in variables}
    entorno.update({"Not": z3.Not, "And": z3.And, "Or": z3.Or,
                    "Implies": z3.Implies, "z3": z3, "True": True, "False": False})
    partes, problemas = [], []
    for r in restricciones:
        if not isinstance(r, str):
            problemas.append("restriccion que no es texto: %r" % (r,))
            continue
        expr = _a_expresion(r)
        try:
            valor = eval(expr, {"__builtins__": {}}, entorno)
        except Exception as e:
            problemas.append("no se pudo interpretar %r (%s)" % (r, type(e).__name__))
            continue
        if isinstance(valor, bool):
            valor = z3.BoolVal(valor)
        partes.append(valor)
    if not partes:
        return None, problemas
    return (partes[0] if len(partes) == 1 else z3.And(*partes)), problemas


def resolver(restricciones, variables):
    """Resuelve con Z3. Devuelve (asignacion o None, problemas)."""
    expr, problemas = a_z3(restricciones, variables)
    if expr is None:
        return None, problemas
    s = z3.Solver()
    s.add(expr)
    if s.check() != z3.sat:
        return None, problemas
    m = s.model()
    return {v: m.evaluate(z3.Int(v), model_completion=True).as_long()
            for v in variables}, problemas


def equivalentes(a, b, variables):
    """True si dos conjuntos de restricciones son logicamente equivalentes."""
    ea, pa = a_z3(a, variables)
    eb, pb = a_z3(b, variables)
    if ea is None or eb is None:
        return False
    s = z3.Solver()
    s.add(z3.Distinct(z3.If(ea, 1, 0), z3.If(eb, 1, 0)))
    return s.check() == z3.unsat


# ==========================================================================
# 3. Que camino toma realmente un input
# ==========================================================================

def firma_de_ejecucion(fn, args):
    """Ejecuta la funcion y devuelve la tupla de lineas que recorrio."""
    lineas = []
    archivo = inspect.getsourcefile(fn)
    inicio = inspect.getsourcelines(fn)[1]
    fin = inicio + len(inspect.getsourcelines(fn)[0])

    def traza(frame, evento, arg):
        if evento == "line" and frame.f_code.co_filename == archivo \
                and inicio <= frame.f_lineno < fin:
            lineas.append(frame.f_lineno)
        return traza

    anterior = sys.gettrace()
    sys.settrace(traza)
    try:
        fn(*args)
    finally:
        sys.settrace(anterior)
    return tuple(lineas)


def firmas_de_referencia(fn, caminos, variables):
    """Para cada camino de referencia, resuelve y ejecuta para obtener su
    firma. Devuelve {firma: indice_de_camino}."""
    firmas = {}
    for i, c in enumerate(caminos):
        sol, _ = resolver(c, variables)
        if sol is None:
            continue
        args = [sol[v] for v in variables]
        firmas[firma_de_ejecucion(fn, args)] = i
    return firmas


# ==========================================================================
# 4. Prompts
# ==========================================================================

INSTRUCCION_P1 = """You are a symbolic execution engine. For EACH function below, \
enumerate ALL execution paths. For each path, give the list of path constraints: \
the condition of every `if` the path goes through, written as it must hold on \
that path.

Rules:
- Use the parameter names exactly as they appear in the code.
- Write a condition that is taken as-is, and one that is not taken as \
`not (condition)`.
- Do NOT include assignments, only the conditions of the `if` statements.
- One entry per path, in any order.

Answer with a JSON object and nothing else, mapping each function name to a \
list of paths, where each path is a list of constraint strings:

  {"nombre_funcion": [["a > 10", "b > 5"], ["a > 10", "not (b > 5)"]], ...}
"""

INSTRUCCION_P2 = """Below is a list of path constraints. For EACH path, give \
concrete integer values for the variables that satisfy ALL of its constraints \
at the same time. If a path is impossible, use null.

Answer with a JSON object and nothing else, with the same structure, where each \
path becomes an object of variable values:

  {"nombre_funcion": [{"a": 11, "b": 6}, {"a": 11, "b": 0}], ...}
"""


def _codigo_sut():
    return open(RUTA_SUT, encoding="utf-8").read()


def mostrar_prompt_paso1():
    print("=" * 78)
    print("PASO 1 - EXTRACCION. Copia todo esto en un chat nuevo.")
    print("=" * 78)
    print()
    print(INSTRUCCION_P1)
    print("```python")
    print(_codigo_sut().rstrip())
    print("```")
    print()
    print("=" * 78)
    print("Guarda la respuesta cruda en prompts/paso1.md y el JSON en")
    print("inputs/constraints_llm.json")
    print("=" * 78)


def _bloque_restricciones(fuente):
    """fuente: 'llm' o 'ref'. Devuelve el texto con las restricciones."""
    lineas = []
    for n in FUNCIONES:
        fn = _funcion(n)
        cam = (_caminos_llm().get(n, []) if fuente == "llm"
               else caminos_referencia(fn))
        lineas.append("%s (variables: %s)" % (n, ", ".join(_variables(fn))))
        for i, c in enumerate(cam):
            lineas.append("  path %d: %s" % (i, " AND ".join(c)))
        lineas.append("")
    return "\n".join(lineas)


def mostrar_prompt_paso2(fuente="llm"):
    """fuente='llm' usa las restricciones que el modelo extrajo;
    fuente='ref' usa las del fuzzer simbolico."""
    etiqueta = ("las que tu mismo extrajiste" if fuente == "llm"
                else "las del fuzzer simbolico")
    print("=" * 78)
    print("PASO 2 - RESOLUCION (%s). Copia todo esto en un chat NUEVO." % etiqueta)
    print("=" * 78)
    print()
    print(INSTRUCCION_P2)
    print(_bloque_restricciones(fuente))
    print("=" * 78)
    archivo = "solucion_llm.json" if fuente == "llm" else "solucion_llm_ref.json"
    print("Guarda la respuesta cruda en prompts/paso2_%s.md y el JSON en" % fuente)
    print("inputs/%s" % archivo)
    print("=" * 78)


# ==========================================================================
# 5. Lectura tolerante de las respuestas
# ==========================================================================

ENVOLTORIOS = ("solucion", "solution", "answer", "result", "respuesta",
               "paths", "caminos", "constraints", "restricciones", "data")


def _leer_json(ruta):
    texto = open(ruta, encoding="utf-8").read().strip()
    if not texto:
        raise ValueError("%s esta vacio" % ruta)
    if texto.startswith("```"):
        texto = "\n".join(l for l in texto.splitlines()
                          if not l.strip().startswith("```"))
    texto = re.sub(r"^\s*(//|#).*$", "", texto, flags=re.M)
    texto = re.sub(r",(\s*[\]\}])", r"\1", texto)
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        try:
            datos = ast.literal_eval(texto)
        except (ValueError, SyntaxError):
            raise ValueError("%s no es JSON valido ni un dict de Python (%s)"
                             % (ruta, e))
        print("  [aviso] %s venia como dict de Python. Se leyo igual." % ruta)
        return datos


def _desenvolver(v):
    n = 0
    while isinstance(v, dict) and len(v) == 1 and n < 4:
        k = next(iter(v))
        if str(k).strip().lower() not in ENVOLTORIOS:
            break
        v = v[k]
        n += 1
    return v


def _clave(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _funcion(nombre):
    mod = importlib.import_module("src.funciones")
    importlib.reload(mod)
    return getattr(mod, nombre)


def _variables(fn):
    return list(inspect.signature(fn).parameters)


def _por_funcion(datos):
    """Mapea las llaves del modelo a los nombres reales de las funciones."""
    datos = _desenvolver(datos)
    reales = {_clave(f): f for f in FUNCIONES}
    salida, avisos, errores = {}, [], []
    if not isinstance(datos, dict):
        return {}, [], ["se esperaba un objeto {funcion: ...}, llego %s"
                        % type(datos).__name__]
    for k, v in datos.items():
        real = reales.get(_clave(k))
        if real is None:
            errores.append("no existe la funcion %r (validas: %s)"
                           % (k, ", ".join(FUNCIONES)))
            continue
        if k != real:
            avisos.append("%r se interpreto como %s" % (k, real))
        salida[real] = _desenvolver(v)
    return salida, avisos, errores


_CACHE_LLM = None


def _caminos_llm():
    global _CACHE_LLM
    if _CACHE_LLM is not None:
        return _CACHE_LLM
    datos, avisos, errores = _por_funcion(_leer_json("inputs/constraints_llm.json"))
    limpio = {}
    for n, caminos in datos.items():
        if isinstance(caminos, dict):
            caminos = list(caminos.values())
        if not isinstance(caminos, list):
            errores.append("%s: se esperaba una lista de caminos" % n)
            continue
        norm = []
        for p in caminos:
            if isinstance(p, str):
                p = [x.strip() for x in re.split(r"\bAND\b|&&", p) if x.strip()]
            if isinstance(p, dict):
                p = list(p.values())
            if not isinstance(p, list):
                errores.append("%s: un camino no es una lista (%r)" % (n, p))
                continue
            norm.append([str(x) for x in p])
        limpio[n] = norm
    for a in avisos:
        print("  [aviso] %s" % a)
    for e in errores:
        print("  [error] %s" % e)
    _CACHE_LLM = limpio
    return limpio


# ==========================================================================
# 6. Evaluacion
# ==========================================================================

def evaluar_extraccion(mostrar=True):
    """Compara los caminos que extrajo el modelo con los de referencia."""
    llm = _caminos_llm()
    filas = []
    for n in FUNCIONES:
        fn = _funcion(n)
        vs = _variables(fn)
        ref = caminos_referencia(fn)
        prop = llm.get(n, [])
        emparejados, sobrantes = set(), []
        for p in prop:
            calce = next((i for i in range(len(ref))
                          if i not in emparejados and equivalentes(p, ref[i], vs)),
                         None)
            if calce is None:
                sobrantes.append(p)
            else:
                emparejados.add(calce)
        faltantes = [ref[i] for i in range(len(ref)) if i not in emparejados]
        filas.append({"funcion": n, "ref": len(ref), "propuestos": len(prop),
                      "correctos": len(emparejados), "faltantes": faltantes,
                      "sobrantes": sobrantes, "variables": vs})
    RESULTADOS["extraccion"] = filas
    if mostrar:
        print("Paso 1 - extraccion de restricciones")
        print("-" * 68)
        for f in filas:
            print("  %-16s referencia %d | propuso %d | equivalentes %d"
                  % (f["funcion"], f["ref"], f["propuestos"], f["correctos"]))
            for p in f["faltantes"]:
                print("      camino NO encontrado: %s" % " AND ".join(p))
            for p in f["sobrantes"]:
                sat, _ = resolver(p, f["variables"])
                marca = "infactible" if sat is None else "no calza con ninguno"
                print("      camino de mas (%s): %s" % (marca, " AND ".join(p)))
        tot_ref = sum(f["ref"] for f in filas)
        tot_ok = sum(f["correctos"] for f in filas)
        print("-" * 68)
        print("  Caminos correctos: %d de %d" % (tot_ok, tot_ref))
    return filas


def _leer_soluciones(ruta):
    datos, avisos, errores = _por_funcion(_leer_json(ruta))
    for a in avisos:
        print("  [aviso] %s" % a)
    for e in errores:
        print("  [error] %s" % e)
    return datos


def _entero(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if float(v).is_integer() else None
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return None
    return None


def _args_de(asignacion, variables):
    """Convierte la asignacion del modelo en una tupla de argumentos."""
    if asignacion is None:
        return None
    asignacion = _desenvolver(asignacion)
    if isinstance(asignacion, (list, tuple)):
        if len(asignacion) != len(variables):
            return None
        asignacion = dict(zip(variables, asignacion))
    if not isinstance(asignacion, dict):
        return None
    porminus = {str(k).strip().lower(): v for k, v in asignacion.items()}
    args = []
    for v in variables:
        if v.lower() not in porminus:
            return None
        n = _entero(porminus[v.lower()])
        if n is None:
            return None
        args.append(n)
    return args


def _evaluar_solucion(etiqueta, caminos_por_funcion, soluciones, mostrar=True):
    """Para cada camino, comprueba si la asignacion lo satisface y que camino
    alcanza de verdad al ejecutar."""
    filas = []
    for n in FUNCIONES:
        fn = _funcion(n)
        vs = _variables(fn)
        ref = caminos_referencia(fn)
        firmas = firmas_de_referencia(fn, ref, vs)
        caminos = caminos_por_funcion.get(n, [])
        props = soluciones.get(n, [])
        if isinstance(props, dict):
            props = list(props.values())
        satisface = alcanzados = sin_respuesta = 0
        vistos = set()
        detalles = []
        for i, c in enumerate(caminos):
            prop = props[i] if i < len(props) else None
            args = _args_de(prop, vs)
            if args is None:
                sin_respuesta += 1
                detalles.append((i, "sin asignacion valida"))
                continue
            expr, _ = a_z3(c, vs)
            ok = False
            if expr is not None:
                s = z3.Solver()
                s.add(expr)
                for v, val in zip(vs, args):
                    s.add(z3.Int(v) == val)
                ok = s.check() == z3.sat
            if ok:
                satisface += 1
            else:
                detalles.append((i, "no satisface sus restricciones"))
            f = firma_de_ejecucion(fn, args)
            if f in firmas and f not in vistos:
                vistos.add(f)
                alcanzados += 1
        filas.append({"funcion": n, "caminos": len(caminos),
                      "satisface": satisface, "sin_respuesta": sin_respuesta,
                      "alcanzados": alcanzados, "ref": len(ref),
                      "detalles": detalles})
    RESULTADOS[etiqueta] = filas
    if mostrar:
        print(etiqueta)
        print("-" * 68)
        for f in filas:
            print("  %-16s %d/%d satisfacen | alcanza %d de %d caminos reales"
                  % (f["funcion"], f["satisface"], f["caminos"],
                     f["alcanzados"], f["ref"]))
            for i, m in f["detalles"][:4]:
                print("      path %d: %s" % (i, m))
    return filas


def evaluar_B(mostrar=True):
    """LLM extrae + LLM resuelve."""
    return _evaluar_solucion("B: LLM extrae + LLM resuelve", _caminos_llm(),
                             _leer_soluciones("inputs/solucion_llm.json"), mostrar)


def evaluar_C(mostrar=True):
    """LLM extrae + Z3 resuelve."""
    llm = _caminos_llm()
    sol = {}
    for n, caminos in llm.items():
        vs = _variables(_funcion(n))
        sol[n] = [resolver(c, vs)[0] for c in caminos]
    return _evaluar_solucion("C: LLM extrae + Z3 resuelve", llm, sol, mostrar)


def evaluar_D(mostrar=True):
    """Fuzzer simbolico extrae + LLM resuelve."""
    ref = {n: caminos_referencia(_funcion(n)) for n in FUNCIONES}
    return _evaluar_solucion("D: fuzzer extrae + LLM resuelve", ref,
                             _leer_soluciones("inputs/solucion_llm_ref.json"),
                             mostrar)


def evaluar_A(mostrar=True):
    """Referencia: fuzzer simbolico extrae + Z3 resuelve."""
    ref = {n: caminos_referencia(_funcion(n)) for n in FUNCIONES}
    sol = {}
    for n, caminos in ref.items():
        vs = _variables(_funcion(n))
        sol[n] = [resolver(c, vs)[0] for c in caminos]
    return _evaluar_solucion("A: fuzzer extrae + Z3 resuelve (referencia)",
                             ref, sol, mostrar)


def consolidar():
    print("Motor de caminos:", motor_caminos())
    ext = RESULTADOS.get("extraccion")
    if ext:
        print("\n## Tabla 1 - Paso 1: extraccion\n")
        print("| Funcion | Caminos reales | Propuestos | Equivalentes | "
              "Faltantes | De mas |")
        print("|---|---|---|---|---|---|")
        for f in ext:
            print("| %s | %d | %d | %d | %d | %d |" % (
                f["funcion"], f["ref"], f["propuestos"], f["correctos"],
                len(f["faltantes"]), len(f["sobrantes"])))

    print("\n## Tabla 2 - Paso 2: resolucion (matriz 2x2)\n")
    print("| Config | Extrae | Resuelve | Satisfacen | Caminos alcanzados |")
    print("|---|---|---|---|---|")
    etiquetas = [
        ("A: fuzzer extrae + Z3 resuelve (referencia)", "fuzzer", "Z3"),
        ("B: LLM extrae + LLM resuelve", "LLM", "LLM"),
        ("C: LLM extrae + Z3 resuelve", "LLM", "Z3"),
        ("D: fuzzer extrae + LLM resuelve", "fuzzer", "LLM"),
    ]
    for clave, ex, re_ in etiquetas:
        filas = RESULTADOS.get(clave)
        letra = clave.split(":")[0]
        if filas is None:
            print("| %s | %s | %s | - | - |" % (letra, ex, re_))
            continue
        sat = sum(f["satisface"] for f in filas)
        tot = sum(f["caminos"] for f in filas)
        alc = sum(f["alcanzados"] for f in filas)
        ref = sum(f["ref"] for f in filas)
        print("| %s | %s | %s | %d/%d | %d/%d |" % (letra, ex, re_, sat, tot, alc, ref))

    print("\n" + "-" * 68)
    print("Lee la tabla asi: si C alcanza mucho mas que B, el cuello de botella")
    print("esta en RESOLVER. Si C tambien queda corto, el problema venia de")
    print("EXTRAER. Compara D con A para aislar lo mismo al reves.")
    print("Copia las dos tablas a REPORTE.md.")
