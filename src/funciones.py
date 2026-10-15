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
