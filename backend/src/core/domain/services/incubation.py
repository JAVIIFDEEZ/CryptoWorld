"""
incubation.py — Puerta de incubación antes del capital real.

Un backtest, por bien validado que esté, mide el pasado. La única evidencia que
no puede estar sobreajustada es la que llega **después** de haber fijado la
estrategia: rendimiento hacia delante, sobre datos que no existían cuando se
tomó la decisión.

Por eso una cartera de paper no puede promocionarse a ejecución real sin haber
incubado: un periodo mínimo funcionando en simulado, con un número mínimo de
operaciones y sin haberse degradado. Es el último filtro y el único que el
sobreajuste no puede burlar, porque no hay nada que ajustar sobre datos que
todavía no han ocurrido.

Es también la frontera de cumplimiento: poner capital real detrás de una
estrategia sin evidencia prospectiva es exactamente lo que un supervisor
señalaría.

El criterio que faltaba: cuánta evidencia es «suficiente»
────────────────────────────────────────────────────────
Durante un tiempo esta puerta exigió catorce días y **cinco operaciones**, sin
pedir que el resultado fuera positivo. El razonamiento de que el sobreajuste no
puede falsear datos futuros era correcto en especie y falso en grado: con cinco
operaciones, una moneda al aire deja un historial positivo la mitad de las veces.
Medido, esa puerta dejaba pasar el **100 %** de las carteras con Sharpe real cero
que simplemente hubieran existido dos semanas.

Y el instrumento que responde a la pregunta correcta ya estaba escrito en este
mismo motor, sin usarse aquí: el **Sharpe probabilístico** (PSR) da la
probabilidad de que el Sharpe verdadero supere un umbral, corrigiendo por
asimetría y curtosis, y el **MinTRL** traduce el «todavía no» en «te faltan N
días». Así que la puerta pasa a exigir PSR ≥ 0,95 y a publicar el MinTRL como
plazo.

Lo que cuesta, medido: con Sharpe real cero pasa el 5 % —la tasa nominal, veinte
veces mejor que el 100 % anterior— y con un Sharpe real de 2,0 pasa el 29 % a los
90 días y el 68 % al año. Es exigente, y la asimetría lo justifica: un falso
positivo es dinero real detrás de una estrategia sin ventaja, y un falso negativo
es esperar.

Por qué la curva se remuestrea a DIARIA
───────────────────────────────────────
Las instantáneas de patrimonio se graban en cada evaluación de la estrategia, o
sea cada quince minutos. Alimentar el PSR con esa serie cruda lo vuelve
sobreconfiado, porque el patrimonio de una posición abierta sobre un precio con
tendencia está autocorrelacionado y el PSR supone observaciones independientes.
Medido sobre curvas con Sharpe real cero: con autocorrelación 0,3 la serie cruda
deja pasar el 11 %, con 0,6 el 20 % y con 0,9 el **33 %**, mientras que
remuestreada a diaria se queda en el 5 % en los cuatro casos. Así que se
remuestrea, y no es una preferencia de estilo.

Capa de dominio: sin Django, sin ORM. Recibe hechos y devuelve un veredicto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MS_POR_DIA = 86_400_000

# Observaciones diarias mínimas para que el PSR signifique algo. Coincide a
# propósito con `min_days`: por debajo no es que el contraste falle, es que no hay
# serie que contrastar.
MIN_DAILY_OBSERVATIONS = 14

# Horizonte más allá del cual el plazo estimado deja de publicarse como número.
# El MinTRL diverge cuando el Sharpe observado roza el umbral: una cartera con un
# exceso casi nulo produce «te faltan 12.643 días», que es aritméticamente cierto
# y comunicativamente desastroso — un número absurdo hace que se deje de creer
# también los que no lo son. Por encima del horizonte se dice lo que de verdad
# significa: que al ritmo actual esto no converge.
RUNWAY_HORIZON_DAYS = 365


@dataclass(frozen=True)
class IncubationPolicy:
    """Requisitos para que una cartera pueda operar con dinero real."""
    min_days: int = 14          # dos semanas de funcionamiento hacia delante
    min_trades: int = 5         # suelo mínimo; el criterio que manda es el PSR
    require_profitable: bool = False
    # Rechazar carteras marcadas como decaídas (la estrategia se degradó en vivo).
    reject_decayed: bool = True

    # ── El criterio estadístico ──────────────────────────────────────────
    # Probabilidad mínima de que el Sharpe verdadero supere el umbral. 0,95 es el
    # mismo nivel que usa `significance.annotate` para llamar significativo a
    # cualquier otro número de esta plataforma: la puerta del dinero no puede ser
    # más laxa que la de un gráfico.
    require_statistical: bool = True
    min_psr: float = 0.95
    # Umbral anualizado contra el que se compara. Cero responde «¿hay ventaja?».
    benchmark_sharpe: float = 0.0


@dataclass(frozen=True)
class IncubationFacts:
    """Estado observado de la cartera, ya extraído de la persistencia."""
    days_running: float
    trades_count: int
    realized_pnl: float
    decayed: bool
    # Retornos DIARIOS de la curva de patrimonio, ya remuestreados. Vacío cuando
    # no hay curva, y entonces el criterio estadístico falla CERRADO: la ausencia
    # de evidencia no puede abrir la puerta del dinero real.
    daily_returns: tuple[float, ...] = field(default_factory=tuple)


def evaluate(facts: IncubationFacts, policy: IncubationPolicy | None = None) -> dict:
    """
    ¿Puede esta cartera pasar a ejecución real?

    Devuelve el veredicto con el detalle de cada requisito y cuánto falta para
    cumplirlo. El detalle importa: un «no» sin explicación empuja al usuario a
    buscar la forma de saltárselo, mientras que «te faltan 6 días y 2
    operaciones» convierte la barrera en un plazo.
    """
    pol = policy or IncubationPolicy()
    estadistico = statistical_evidence(facts.daily_returns, pol)

    checks = {
        "min_days": facts.days_running >= pol.min_days,
        "min_trades": facts.trades_count >= pol.min_trades,
        "not_decayed": not (pol.reject_decayed and facts.decayed),
        "profitable": (not pol.require_profitable) or facts.realized_pnl > 0,
        "statistical_edge": (not pol.require_statistical) or estadistico["passes"],
    }
    missing = [name for name, ok in checks.items() if not ok]

    return {
        "incubated": not missing,
        "checks": checks,
        "missing": missing,
        "days_running": round(float(facts.days_running), 1),
        "days_required": pol.min_days,
        "days_remaining": max(0, round(pol.min_days - facts.days_running, 1)),
        "trades_count": facts.trades_count,
        "trades_required": pol.min_trades,
        "trades_remaining": max(0, pol.min_trades - facts.trades_count),
        "statistical": estadistico,
        "note": _explain(checks, facts, pol, estadistico),
    }


def daily_returns_from_curve(timestamps_ms, equities) -> tuple[float, ...]:
    """Retornos logarítmicos DIARIOS a partir de la curva de patrimonio.

    Se toma el ÚLTIMO patrimonio de cada día UTC y se encadenan los retornos
    logarítmicos entre cierres consecutivos. Dos decisiones:

    · **Diario y no la cadencia nativa.** Las instantáneas llegan cada quince
      minutos y esa serie está autocorrelacionada cuando hay posición abierta
      sobre un precio con tendencia. El PSR supone independencia, así que sobre la
      serie cruda sale sobreconfiado: medido con Sharpe real cero, la cruda deja
      pasar hasta el 33 % de las carteras y la diaria el 5 %.
    · **El último del día y no la media.** El patrimonio es un nivel, no un flujo:
      promediarlo dentro del día suavizaría la varianza y volvería a inflar el
      Sharpe.

    Los días sin instantánea no se rellenan: se encadena con el siguiente día que
    la tenga. Rellenar con el valor anterior inventaría retornos de cero, que
    bajarían la varianza y subirían el Sharpe sin que haya ocurrido nada.
    """
    import math

    marcas = [int(t) for t in (timestamps_ms or [])]
    valores = [float(e) for e in (equities or [])]
    if len(marcas) != len(valores) or len(marcas) < 2:
        return ()

    ultimo_por_dia: dict[int, tuple[int, float]] = {}
    for t, e in zip(marcas, valores):
        dia = t // MS_POR_DIA
        previo = ultimo_por_dia.get(dia)
        if previo is None or t >= previo[0]:
            ultimo_por_dia[dia] = (t, e)

    cierres = [ultimo_por_dia[d][1] for d in sorted(ultimo_por_dia)]
    salida = []
    for antes, ahora in zip(cierres, cierres[1:]):
        if antes > 0 and ahora > 0:
            salida.append(math.log(ahora / antes))
    return tuple(salida)


def statistical_evidence(daily_returns, policy: IncubationPolicy | None = None) -> dict:
    """¿Sostiene la curva de patrimonio la afirmación de que hay ventaja?

    Falla CERRADO: sin serie, con serie corta o con momentos degenerados, el
    criterio NO se cumple. Es la misma regla que gobierna los controles de riesgo
    del OMS — un control que falla abierto es peor que no tenerlo, porque da la
    apariencia de protección exactamente cuando no protege.
    """
    pol = policy or IncubationPolicy()
    r = tuple(float(x) for x in (daily_returns or []))

    if len(r) < MIN_DAILY_OBSERVATIONS:
        return {
            "passes": False,
            "psr": None,
            "observations": len(r),
            "observations_required": MIN_DAILY_OBSERVATIONS,
            "min_psr": pol.min_psr,
            "days_remaining_estimate": None,
            "note": (f"Solo {len(r)} observaciones diarias de patrimonio y hacen "
                     f"falta {MIN_DAILY_OBSERVATIONS}. No es que la estrategia "
                     f"falle el contraste: es que todavía no hay serie que "
                     f"contrastar, y sin evidencia la puerta no se abre."),
        }

    from core.domain.services import significance as sig

    bloque = sig.probabilistic_sharpe_ratio(r, pol.benchmark_sharpe, ppy=365.0)
    psr = bloque.get("psr")
    mintrl = bloque.get("min_track_record_length")

    if psr is None:
        return {
            "passes": False,
            "psr": None,
            "observations": len(r),
            "observations_required": MIN_DAILY_OBSERVATIONS,
            "min_psr": pol.min_psr,
            "days_remaining_estimate": None,
            "note": ("La curva de patrimonio no admite un Sharpe —plana o con "
                     "momentos degenerados—, así que no hay nada que sostenga la "
                     "afirmación de ventaja."),
        }

    pasa = psr >= pol.min_psr
    # MinTRL dice cuántas observaciones harían falta AL RITMO ACTUAL. Convertirlo
    # en «días que faltan» es lo que transforma una barrera en un plazo — pero solo
    # mientras el número sea creíble.
    bruto = max(0, int(mintrl) - len(r)) if mintrl else None
    fuera_de_horizonte = bruto is not None and bruto > RUNWAY_HORIZON_DAYS
    faltan = None if (bruto is None or fuera_de_horizonte) else bruto

    if pasa:
        cola = ""
    elif faltan is not None:
        cola = (f" Hace falta {pol.min_psr * 100:.0f}%. Al ritmo actual harían falta "
                f"unos {mintrl} días de curva en total, o sea {faltan} más.")
    elif fuera_de_horizonte:
        cola = (f" Hace falta {pol.min_psr * 100:.0f}%. Con el Sharpe observado el "
                f"historial necesario pasa del año, así que el plazo no se publica "
                f"como una fecha: lo que dice es que a este ritmo no converge, y lo "
                f"que lo cambiaría es un Sharpe mayor, no esperar más.")
    else:
        cola = (f" Hace falta {pol.min_psr * 100:.0f}%. Con el Sharpe observado "
                f"ningún histórico bastaría: no hay exceso sobre el umbral que "
                f"acumular.")

    return {
        "passes": bool(pasa),
        "psr": psr,
        "min_psr": pol.min_psr,
        "benchmark_sharpe": pol.benchmark_sharpe,
        "observations": len(r),
        "observations_required": MIN_DAILY_OBSERVATIONS,
        "min_track_record_length": mintrl,
        "days_remaining_estimate": faltan,
        "runway_beyond_horizon": bool(fuera_de_horizonte),
        "runway_horizon_days": RUNWAY_HORIZON_DAYS,
        "note": (
            f"Probabilidad del {psr * 100:.0f}% de que el Sharpe verdadero supere "
            f"{pol.benchmark_sharpe:.2f}, sobre {len(r)} días de curva." + cola
        ),
    }


def _explain(checks: dict, facts: IncubationFacts, pol: IncubationPolicy,
             estadistico: dict) -> str:
    if all(checks.values()):
        psr = estadistico.get("psr")
        evidencia = (f" y un {psr * 100:.0f}% de probabilidad de que el Sharpe "
                     f"verdadero sea positivo" if psr is not None else "")
        return (f"Incubación superada: {facts.days_running:.0f} días en simulado, "
                f"{facts.trades_count} operaciones{evidencia}. La cartera puede "
                f"operar en real.")

    reasons: list[str] = []
    if not checks["min_days"]:
        reasons.append(f"faltan {pol.min_days - facts.days_running:.0f} días de simulado")
    if not checks["min_trades"]:
        reasons.append(f"faltan {pol.min_trades - facts.trades_count} operaciones")
    if not checks["not_decayed"]:
        reasons.append("la estrategia se ha degradado en vivo")
    if not checks["profitable"]:
        reasons.append("el P&L acumulado en simulado no es positivo")
    if not checks["statistical_edge"]:
        reasons.append("la evidencia no sostiene todavía que haya ventaja")

    cola = ""
    if not checks["statistical_edge"]:
        cola = " " + estadistico.get("note", "")

    return (
        "Incubación no superada: " + ", ".join(reasons) + ". La única evidencia "
        "que el sobreajuste no puede falsear es la que llega después de fijar la "
        "estrategia, y todavía no hay suficiente." + cola
    )
