"""
test_incubation_statistical.py — La puerta del dinero real, medida.

Esta es la única puerta de la plataforma al otro lado de la cual hay dinero. Hasta
ahora exigía catorce días y **cinco operaciones**, sin pedir que el resultado fuera
positivo, y el instrumento que responde a la pregunta correcta —el Sharpe
probabilístico— ya estaba escrito en este mismo motor sin usarse aquí.

El test central no comprueba ramas: mide **cuántas carteras sin ninguna ventaja
atraviesan la puerta**. Con la puerta anterior eran todas; con esta tienen que ser
una de cada veinte, que es el nivel nominal.

Y tres defectos que la calibración encontró antes de escribir una línea de la
implementación:

1. **Alimentar el PSR con la curva nativa lo vuelve sobreconfiado.** Las
   instantáneas se graban cada quince minutos y el patrimonio de una posición
   abierta sobre un precio con tendencia está autocorrelacionado, mientras que el
   PSR supone independencia. Medido con Sharpe real cero: con autocorrelación 0,3
   la serie cruda deja pasar el 11 %, con 0,6 el 20 % y con 0,9 el 33 %. La
   remuestreada a diaria se queda en el 5 % en los cuatro casos.
2. **El MinTRL diverge** cuando el Sharpe observado roza el umbral, y producía
   mensajes como «te faltan 12.643 días». Un número absurdo hace que se deje de
   creer también los que no lo son.
3. **Sin curva, el criterio tiene que fallar cerrado.** Una cartera con 400 días y
   500 operaciones pero sin curva archivada no demuestra nada.
"""

import numpy as np
import pytest

from core.domain.services import incubation as inc


PPY = 365.0
VOL = 0.60
MS_DIA = inc.MS_POR_DIA


def diarios(sharpe_anual: float, dias: int, seed: int) -> tuple[float, ...]:
    """Retornos diarios con un Sharpe anual objetivo."""
    rng = np.random.default_rng(seed)
    return tuple(rng.normal(sharpe_anual * VOL / PPY, VOL / np.sqrt(PPY), dias))


def facts(sharpe: float, dias: int, seed: int, trades: int = 20):
    return inc.IncubationFacts(
        days_running=float(dias), trades_count=trades, realized_pnl=1.0,
        decayed=False, daily_returns=diarios(sharpe, dias, seed),
    )


# ──────────────────────────────────────── lo que la puerta promete


class TestLaTasaDeFalsoPositivo:

    @pytest.mark.unit
    def test_una_cartera_sin_ventaja_casi_nunca_pasa(self):
        """El test que justifica el cambio entero.

        120 carteras con Sharpe real CERO y 180 días de curva. Con la puerta
        anterior —14 días y 5 operaciones— pasaban las 120. Con esta tienen que
        pasar unas 6; se admite hasta 15, que es el percentil ~99 de una
        binomial(120, 0.05).
        """
        pasan = sum(1 for s in range(120)
                    if inc.evaluate(facts(0.0, 180, 7000 + s))["incubated"])
        assert pasan <= 15, f"{pasan}/120 carteras sin ventaja llegaron a dinero real"

    @pytest.mark.unit
    def test_la_puerta_anterior_dejaba_pasar_a_todas(self):
        """Se fija para que el cambio no se deshaga por comodidad.

        Con la política anterior —sin criterio estadístico— cualquier cartera que
        hubiera existido dos semanas y operado cinco veces pasaba, con Sharpe real
        cero. Es exactamente lo que ya no ocurre.
        """
        laxa = inc.IncubationPolicy(require_statistical=False)
        pasan = sum(1 for s in range(40)
                    if inc.evaluate(facts(0.0, 180, 8000 + s), laxa)["incubated"])
        assert pasan == 40

    @pytest.mark.unit
    def test_una_ventaja_real_y_sostenida_si_pasa(self):
        """La puerta tiene que ser atravesable: si nada pasa nunca, no es una
        puerta, es un muro, y el usuario buscará la forma de rodearlo."""
        pasan = sum(1 for s in range(40)
                    if inc.evaluate(facts(3.0, 365, 9000 + s))["incubated"])
        assert pasan >= 20, f"solo {pasan}/40 con Sharpe 3,0 y un año de curva"

    @pytest.mark.unit
    def test_mas_historial_con_la_misma_ventaja_pasa_mas(self):
        """La propiedad que hace del plazo algo honesto: esperar sirve de algo."""
        def tasa(dias):
            return sum(1 for s in range(40)
                       if inc.evaluate(facts(2.0, dias, 9500 + s))["incubated"])
        assert tasa(365) > tasa(30)


class TestElRemuestreoADiario:

    @staticmethod
    def _curva_autocorrelada(dias, seed, phi, por_dia=96):
        """Patrimonio cada 15 min con AR(1) dentro de la posición y Sharpe cero."""
        rng = np.random.default_rng(seed)
        n = dias * por_dia
        vol_p = VOL / np.sqrt(PPY * por_dia)
        e = rng.normal(0, vol_p * np.sqrt(max(1 - phi ** 2, 1e-9)), n)
        x = np.empty(n)
        x[0] = e[0]
        for t in range(1, n):
            x[t] = phi * x[t - 1] + e[t]
        dentro = np.zeros(n, dtype=bool)
        t = 0
        while t < n:
            largo = 3 * por_dia
            dentro[t:t + largo] = True
            t += 2 * largo
        r = np.where(dentro, x, 0.0)
        equity = 10_000.0 * np.exp(np.cumsum(r))
        marcas = [1_700_000_000_000 + int(i * MS_DIA / por_dia) for i in range(n)]
        return marcas, list(equity), r

    @pytest.mark.unit
    def test_la_serie_cruda_seria_sobreconfiada_y_la_diaria_no(self):
        """El defecto número uno, medido en los dos sentidos.

        Con autocorrelación alta y Sharpe real cero, el PSR sobre la serie nativa
        de quince minutos deja pasar muchas más carteras que sobre la diaria. Es la
        razón por la que `daily_returns_from_curve` existe.
        """
        from core.domain.services import significance as sig

        por_dia = 96
        crudo = diario = 0
        for s in range(40):
            marcas, equity, r = self._curva_autocorrelada(90, 300 + s, phi=0.9,
                                                          por_dia=por_dia)
            o_crudo = sig.probabilistic_sharpe_ratio(r, 0.0, PPY * por_dia)
            o_diario = sig.probabilistic_sharpe_ratio(
                inc.daily_returns_from_curve(marcas, equity), 0.0, PPY)
            crudo += (o_crudo.get("psr") or 0) >= 0.95
            diario += (o_diario.get("psr") or 0) >= 0.95
        assert crudo > diario, (
            f"crudo {crudo}/40 vs diario {diario}/40: el test no mide lo que cree")
        assert diario <= 6, f"la serie diaria dejó pasar {diario}/40 sin ventaja"

    @pytest.mark.unit
    def test_toma_el_ultimo_patrimonio_de_cada_dia(self):
        """Y no la media: el patrimonio es un nivel, no un flujo, y promediarlo
        dentro del día suavizaría la varianza e inflaría el Sharpe."""
        base = 1_700_000_000_000 - (1_700_000_000_000 % MS_DIA)
        marcas = [base, base + MS_DIA // 2, base + MS_DIA,
                  base + MS_DIA + MS_DIA // 2]
        equity = [100.0, 150.0, 200.0, 400.0]
        r = inc.daily_returns_from_curve(marcas, equity)
        # Cierres: día 0 → 150, día 1 → 400. Un solo retorno, log(400/150).
        assert len(r) == 1
        assert r[0] == pytest.approx(np.log(400 / 150))

    @pytest.mark.unit
    def test_un_dia_sin_instantanea_no_se_rellena(self):
        """Rellenar con el valor anterior inventaría un retorno de cero, que
        bajaría la varianza y subiría el Sharpe sin que haya pasado nada."""
        base = 1_700_000_000_000 - (1_700_000_000_000 % MS_DIA)
        # Días 0 y 2; el 1 no tiene instantánea.
        marcas = [base, base + 2 * MS_DIA]
        r = inc.daily_returns_from_curve(marcas, [100.0, 121.0])
        assert len(r) == 1
        assert r[0] == pytest.approx(np.log(1.21))

    @pytest.mark.unit
    def test_las_ramas_degeneradas_devuelven_vacio(self):
        assert inc.daily_returns_from_curve([], []) == ()
        assert inc.daily_returns_from_curve([1], [1.0]) == ()
        assert inc.daily_returns_from_curve([1, 2], [1.0]) == ()       # desalineadas
        base = 1_700_000_000_000
        # Patrimonio no positivo: no hay logaritmo que tomar.
        assert inc.daily_returns_from_curve(
            [base, base + MS_DIA], [0.0, 100.0]) == ()


class TestFallaCerrado:

    @pytest.mark.unit
    def test_sin_curva_no_se_abre_aunque_todo_lo_demas_sobre(self):
        """La ausencia de evidencia no es evidencia. Es la misma regla que el OMS:
        un control que falla abierto es peor que no tenerlo."""
        out = inc.evaluate(inc.IncubationFacts(
            days_running=400, trades_count=500, realized_pnl=9999.0,
            decayed=False, daily_returns=(),
        ))
        assert out["incubated"] is False
        assert out["missing"] == ["statistical_edge"]
        assert out["statistical"]["passes"] is False
        assert out["statistical"]["psr"] is None

    @pytest.mark.unit
    def test_una_curva_corta_no_se_contrasta(self):
        """Y se distingue de «falla el contraste»: no hay serie que contrastar."""
        out = inc.statistical_evidence(diarios(5.0, 10, 1))
        assert out["passes"] is False
        assert out["observations"] == 10
        assert out["observations_required"] == inc.MIN_DAILY_OBSERVATIONS
        assert "todavía no hay serie" in out["note"]

    @pytest.mark.unit
    def test_una_curva_plana_no_se_contrasta(self):
        """Una estrategia que no opera da retornos planos: ahí no hay ni magnitud
        ni incertidumbre, y devolver un veredicto sugeriría una certeza falsa."""
        out = inc.statistical_evidence((0.0,) * 60)
        assert out["passes"] is False
        assert out["psr"] is None

    @pytest.mark.unit
    def test_el_criterio_se_puede_desactivar_pero_no_por_defecto(self):
        """La política es explícita. Si alguien lo apaga, que sea a propósito."""
        assert inc.IncubationPolicy().require_statistical is True
        assert inc.IncubationPolicy().min_psr == 0.95


class TestElPlazo:

    @pytest.mark.unit
    def test_ningun_plazo_publicado_pasa_del_horizonte(self):
        """El defecto número dos: el MinTRL diverge cuando el exceso es casi nulo y
        producía «te faltan 12.643 días». Ninguna salida puede publicar eso."""
        malos = 0
        for s in range(300):
            sh = np.random.default_rng(s).uniform(-1.0, 3.0)
            est = inc.statistical_evidence(diarios(sh, 30, 9900 + s))
            d = est["days_remaining_estimate"]
            if d is not None and d > inc.RUNWAY_HORIZON_DAYS:
                malos += 1
        assert malos == 0

    @pytest.mark.unit
    def test_cuando_no_converge_se_dice_por_que(self):
        """Y no se calla: callarlo dejaría al usuario esperando un plazo que no
        existe, cuando lo que hace falta es un Sharpe mayor."""
        est = inc.statistical_evidence(diarios(0.1, 30, 4))
        if not est["passes"] and est["days_remaining_estimate"] is None:
            assert ("no converge" in est["note"]
                    or "ningún histórico bastaría" in est["note"])

    @pytest.mark.unit
    def test_cuando_falta_poco_se_da_el_numero(self):
        """Una barrera con plazo es un plazo; sin plazo es un muro."""
        encontrado = False
        for s in range(60):
            est = inc.statistical_evidence(diarios(3.0, 60, 5000 + s))
            if not est["passes"] and est["days_remaining_estimate"] is not None:
                assert est["days_remaining_estimate"] > 0
                assert "días más" in est["note"] or "más." in est["note"]
                encontrado = True
                break
        assert encontrado, "ningún caso dio un plazo concreto: revisar el fixture"


class TestLosOtrosCriteriosSiguenVigentes:

    @pytest.mark.unit
    def test_una_estrategia_decaida_no_pasa_ni_con_ventaja(self):
        f = inc.IncubationFacts(400, 100, 500.0, True, diarios(4.0, 365, 1))
        assert inc.evaluate(f)["incubated"] is False
        assert "not_decayed" in inc.evaluate(f)["missing"]

    @pytest.mark.unit
    def test_pocos_dias_no_pasan_ni_con_ventaja(self):
        f = inc.IncubationFacts(3, 100, 500.0, False, diarios(4.0, 365, 1))
        assert "min_days" in inc.evaluate(f)["missing"]

    @pytest.mark.unit
    def test_el_informe_lleva_el_bloque_estadistico_siempre(self):
        """Tanto si pasa como si no: esconderlo cuando falla sería esconder la
        única razón por la que importa."""
        for f in (facts(4.0, 365, 1), facts(0.0, 20, 2)):
            out = inc.evaluate(f)
            assert "statistical" in out
            assert "psr" in out["statistical"]
            assert out["statistical"]["note"]

    @pytest.mark.unit
    def test_la_nota_del_exito_menciona_la_evidencia(self):
        out = inc.evaluate(facts(5.0, 365, 1))
        if out["incubated"]:
            assert "%" in out["note"]
