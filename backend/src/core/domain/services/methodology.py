"""
methodology.py — Qué significa cada cifra propia, y dónde deja de valer.

Por qué esto es código y no un documento suelto
───────────────────────────────────────────────
Una nota metodológica en un PDF envejece mal: el código cambia, el umbral se
recalibra y el documento sigue diciendo lo de antes. Aquí las notas viven junto a
la implementación, se sirven por la misma API y se prueban con la misma suite,
así que una métrica que cambia de definición sin actualizar su nota rompe un
test en lugar de mentirle a quien la lee.

Qué lleva cada entrada
──────────────────────
Tres campos y ninguno es decorativo:

  · **qué mide** — la definición operativa, no el nombre bonito.
  · **supuestos** — lo que tiene que ser cierto para que el número signifique lo
    que parece.
  · **límites** — cuándo NO vale. Es el campo que casi nadie publica y el único
    que distingue una nota metodológica de un folleto.

La regla que gobierna todas ellas
─────────────────────────────────
Ninguna cifra que esta plataforma muestre puede estar (a) dentro de muestra,
(b) bruta de costes o (c) sin deflactar por el número de configuraciones
probadas. Cuando una métrica incumple alguna, se dice en sus límites en lugar de
retirarla en silencio: un número retirado no enseña nada, uno acotado sí.

Capa de dominio: datos y texto, sin Django ni cálculo.
"""

from __future__ import annotations

# Versión de la nota. Cambia cuando cambia una definición, no cuando se corrige
# una errata: quien citó una cifra tiene que poder saber contra qué definición
# la citó.
METHODOLOGY_VERSION = "2026.09"

NOTES: tuple[dict, ...] = (
    {
        "key": "fitness",
        "title": "Fitness del generador",
        "what": (
            "Ratio de Sharpe fuera de muestra en validación hacia delante, NETO de "
            "comisiones y deslizamiento, penalizado por la brecha entre dentro y "
            "fuera de muestra, por rotación y por complejidad del genoma."),
        "assumptions": (
            "Que los costes configurados se parecen a los reales del usuario, y "
            "que el activo tiene profundidad suficiente para que el tamaño "
            "operado no mueva el precio."),
        "limits": (
            "NO es el rendimiento esperado. Es la función que ordena candidatas "
            "dentro de una búsqueda, y está optimizada por un algoritmo genético: "
            "el valor de la ganadora está sesgado al alza por selección, que es "
            "precisamente lo que el Sharpe deflactado corrige después. Leer el "
            "fitness como una previsión de rentabilidad es el error más común."),
    },
    {
        "key": "deflated_sharpe",
        "title": "Sharpe deflactado (DSR)",
        "what": (
            "Probabilidad de que el Sharpe observado sea superior al mejor que "
            "produciría el azar habiendo probado el mismo número de "
            "configuraciones, con la varianza observada entre ellas."),
        "assumptions": (
            "Que el número de pruebas registrado es el real. Por eso cada "
            "ejecución del generador queda registrada aunque no produzca ninguna "
            "estrategia: contar solo las búsquedas fructíferas subestimaría N y "
            "haría el deflactado demasiado generoso."),
        "limits": (
            "Corrige la multiplicidad de ESTA plataforma, no la del usuario. Si "
            "alguien consulta veinte activos y se queda con el mejor, ha hecho "
            "veinte pruebas más que el DSR no ve."),
    },
    {
        "key": "pbo",
        "title": "Probabilidad de sobreajuste (PBO)",
        "what": (
            "Frecuencia con la que la configuración óptima dentro de muestra cae "
            "por debajo de la mediana fuera de muestra, sobre particiones "
            "combinatorias de la serie."),
        "assumptions": (
            "Que la matriz de rendimientos viene de las configuraciones realmente "
            "evaluadas por la búsqueda."),
        "limits": (
            "Alimentado con vecinos perturbados de una sola campeona mide "
            "estabilidad paramétrica, no sobreajuste de selección, y sale casi "
            "siempre bien. Ese uso existía y se renombró a «sensibilidad "
            "paramétrica», que es lo que era."),
    },
    {
        "key": "purged_cv",
        "title": "Validación purgada con embargo",
        "what": (
            "Partición hacia delante que elimina del entrenamiento las muestras "
            "cuya etiqueta se resuelve dentro del tramo de prueba, más un margen "
            "adicional por correlación serial."),
        "assumptions": (
            "Que el horizonte declarado es el real: es a la vez lo que se predice "
            "y lo que se purga, y no son dos parámetros sino uno."),
        "limits": (
            "Respetar el orden temporal no basta y esa confusión estuvo en este "
            "motor: medido sobre ocho series de ruido puro, la falta de purga "
            "inflaba la precisión publicada en 0,76 puntos porcentuales."),
    },
    {
        "key": "edge_ml",
        "title": "Edge del modelo de dirección",
        "what": (
            "Precisión fuera de muestra menos la de predecir siempre la clase "
            "mayoritaria, con intervalo de Wilson al 95 %."),
        "assumptions": (
            "Clases razonablemente equilibradas y muestra fuera de muestra "
            "suficiente para que el intervalo signifique algo."),
        "limits": (
            "El veredicto exige que el intervalo excluya el cero, no que la "
            "magnitud supere un umbral. Con unos cientos de observaciones el "
            "error estándar ronda los dos puntos, así que un edge del 4 % no "
            "llega a dos desviaciones típicas: el umbral fijo anterior no medía "
            "señal. Y un edge direccional de 1-2 % —el único realista en cripto "
            "líquido— necesita del orden de 4.000 a 15.000 observaciones para "
            "detectarse; por debajo de eso, «sin edge» significa «esta muestra no "
            "puede responder», que no es lo mismo."),
    },
    {
        "key": "feature_importance",
        "title": "Importancia de variables",
        "what": (
            "Caída de precisión fuera de muestra al permutar cada grupo de "
            "variables en los tramos purgados, con error estándar entre tramos y "
            "corrección por multiplicidad."),
        "assumptions": (
            "Que las variables muy correlacionadas se miden agrupadas: por "
            "separado se sustituyen entre sí y todas parecen inútiles."),
        "limits": (
            "Con 3-6 tramos el contraste tiene poca potencia. Un grupo no "
            "significativo significa «no se ha demostrado que aporte», nunca «se "
            "ha demostrado que no aporta». La métrica anterior —impureza del "
            "bosque— era dentro de muestra y estaba sesgada por cardinalidad."),
    },
    {
        "key": "execution_cost",
        "title": "Coste de ejecución por tamaño",
        "what": (
            "Impacto esperado de una orden según el modelo de raíz cuadrada, "
            "calibrado con el volumen medio diario en USD y la volatilidad "
            "diaria observados."),
        "assumptions": (
            "Condiciones de mercado típicas y un único parámetro libre (gamma), "
            "que se declara en la respuesta en lugar de calibrarse sobre el mismo "
            "histórico con el que se valida la estrategia."),
        "limits": (
            "NO es una lectura del libro de órdenes. La plataforma consulta "
            "profundidad en vivo pero no la archiva, así que no hay serie con la "
            "que medir el coste real hacia atrás ni con la que contrastar este "
            "modelo. En estrés el coste real será mayor."),
    },
    {
        "key": "edge_test",
        "title": "Test de potencia: dirección frente a volatilidad",
        "what": (
            "Corre las dos preguntas sobre la misma serie con la misma validación "
            "purgada y dice cuál puede responder la muestra disponible."),
        "assumptions": (
            "Para la volatilidad, que la hipótesis nula es la media constante del "
            "entrenamiento y no la persistencia."),
        "limits": (
            "El criterio de partida —batir a la persistencia— se descartó al "
            "calibrar sobre series con la respuesta conocida, porque falla en las "
            "dos direcciones: una serie homocedástica, impredecible por "
            "construcción, lo cumple con R² relativo +0,45, y series GARCH con "
            "correlación de 0,7 no lo cumplen en 7 de 9 casos."),
    },
    {
        "key": "incubation",
        "title": "Puerta de incubación",
        "what": (
            "Periodo mínimo de funcionamiento en simulado, con un número mínimo "
            "de operaciones y sin degradación, antes de permitir capital real."),
        "assumptions": (
            "Que el periodo incubado es posterior a la fijación de la estrategia."),
        "limits": (
            "Es el único filtro que el sobreajuste no puede burlar, porque no hay "
            "nada que ajustar sobre datos que aún no han ocurrido. A cambio es "
            "lento, y no dice nada sobre regímenes que no hayan ocurrido durante "
            "la incubación."),
    },
    {
        "key": "risk_gate",
        "title": "Controles de riesgo del OMS",
        "what": (
            "Límite de pérdida diaria y de concentración, evaluados antes de "
            "enviar cualquier compra, tanto en el espejo de paper a real como en "
            "la compra manual."),
        "assumptions": (
            "Que la política del usuario está configurada; sin límite fijado no "
            "hay nada que hacer cumplir."),
        "limits": (
            "Un control que no puede evaluarse NO autoriza: si la comprobación "
            "falla, la compra se bloquea. Antes devolvía «adelante», es decir "
            "fallaba abierto justo cuando el sistema estaba roto. Las ventas no "
            "pasan por el control y nunca se bloquean: reducir exposición tiene "
            "que poder hacerse siempre."),
    },
)

# La regla que gobierna todo lo anterior, en una frase que se pueda citar.
GOLDEN_RULE = (
    "Ninguna cifra mostrada puede estar dentro de muestra, bruta de costes o sin "
    "deflactar por el número de configuraciones probadas. Si una lo está, se dice "
    "en sus límites en vez de retirarla en silencio."
)

# Lo que esta plataforma NO afirma. Va en la nota porque la ausencia de una
# promesa es tan informativa como la promesa, y porque es lo que separa esto de
# todo el segmento.
DISCLAIMERS: tuple[str, ...] = (
    "No se predice la dirección del precio con ventaja demostrada. La muestra "
    "disponible no alcanza para detectar el tamaño de efecto que existiría en un "
    "mercado líquido, y decirlo es más honesto que enseñar un veredicto.",
    "Todo rendimiento mostrado es simulado salvo el que proviene de órdenes "
    "reales registradas, que va etiquetado como tal.",
    "El número de configuraciones probadas acompaña a toda cifra de estrategia. "
    "Un Sharpe sin ese número no es interpretable.",
)


def note_for(key: str) -> dict | None:
    """La nota de una métrica concreta, o None si no existe."""
    for note in NOTES:
        if note["key"] == key:
            return dict(note)
    return None


def all_notes() -> list[dict]:
    """Todas las notas, en el orden en que se publican."""
    return [dict(note) for note in NOTES]
