"""
test_economic_calendar.py — El calendario y su única regla dura.

El valor de este módulo no está en generar fechas: está en **no inventarlas** y en
que las variables que produce no miren al futuro que no se conocía. Así que los
tests centrales son dos:

· que el horario de verano se respete, porque la nómina no agrícola se publica a
  las 08:30 de Nueva York y tratarlo como una hora UTC fija desplaza el evento
  exactamente una vela horaria durante ocho meses al año;
· que una variable de calendario NO use un evento anunciado después de la vela,
  que es el único lookahead posible en la única familia de variables a la que se
  le permite mirar hacia delante.
"""

from datetime import datetime, timezone as _tz

import numpy as np
import pytest

from core.domain.services import economic_calendar as cal


H = 3_600_000


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def _hora_utc(e) -> int:
    return datetime.fromtimestamp(e.scheduled_at / 1000, _tz.utc).hour


# ─────────────────────────────────────────────────── la trampa del horario


class TestElHorarioDeVerano:

    @pytest.mark.unit
    def test_la_nomina_cae_a_las_12_30_o_13_30_utc_segun_la_epoca(self):
        """08:30 de Nueva York son 13:30 UTC en invierno y 12:30 en verano.

        Si el módulo usara una hora UTC fija, el evento quedaría desplazado una
        vela horaria durante ocho meses al año, y el estudio de eventos mediría la
        reacción de la vela anterior — cuyo retorno ya estaba cerrado antes de la
        publicación.
        """
        eventos = cal.nonfarm_payrolls(_ms("2024-01-01T00:00+00:00"),
                                       _ms("2024-12-31T23:00+00:00"))
        horas = {_hora_utc(e) for e in eventos}
        assert horas == {12, 13}, horas

    @pytest.mark.unit
    def test_en_enero_es_13_30_y_en_julio_12_30(self):
        eventos = cal.nonfarm_payrolls(_ms("2024-01-01T00:00+00:00"),
                                       _ms("2024-12-31T23:00+00:00"))
        por_mes = {datetime.fromtimestamp(e.scheduled_at / 1000, _tz.utc).month:
                   _hora_utc(e) for e in eventos}
        assert por_mes[1] == 13
        assert por_mes[7] == 12

    @pytest.mark.unit
    def test_siempre_es_el_primer_viernes(self):
        eventos = cal.nonfarm_payrolls(_ms("2023-01-01T00:00+00:00"),
                                       _ms("2025-12-31T23:00+00:00"))
        assert len(eventos) == 36
        for e in eventos:
            d = datetime.fromtimestamp(e.scheduled_at / 1000, _tz.utc)
            # Primer viernes: es viernes y el día está entre 1 y 7. Se comprueba
            # en UTC, donde la fecha puede adelantarse — no lo hace, porque 12:30
            # y 13:30 UTC caen el mismo día.
            assert d.weekday() == 4
            assert 1 <= d.day <= 7


# ──────────────────────────────────────────────── la regla point-in-time


class TestNoMirarElFuturoQueNoSeSabia:

    @pytest.mark.unit
    def test_un_evento_anunciado_despues_de_la_vela_no_entra(self):
        """La única forma de hacer lookahead con esta familia, y la que se corta.

        Se plantan dos eventos idénticos salvo en cuándo se anunciaron. El
        anunciado tarde no puede aparecer como «próximo evento» en las velas
        anteriores a su anuncio: en esas velas nadie sabía que iba a ocurrir.
        """
        marcas = np.arange(200, dtype=np.int64) * H
        tarde = cal.CalendarEvent(key="X", scheduled_at=int(marcas[150]),
                                  announced_at=int(marcas[140]))
        f = cal.calendar_features(marcas, [tarde], horizon_bars=200)

        # Antes del anuncio no hay próximo evento: la variable va al tope.
        assert f["cal_x_to_next"][100] == pytest.approx(1.0)
        # Después del anuncio y antes del evento, sí lo hay y falta menos del tope.
        assert f["cal_x_to_next"][145] < 1.0
        assert f["cal_x_to_next"][145] > 0.0

    @pytest.mark.unit
    def test_un_evento_anunciado_desde_siempre_si_entra(self):
        """La pareja del anterior: los eventos derivados por regla se conocen
        desde antes de que existiera cualquier vela, así que no se filtran."""
        marcas = np.arange(200, dtype=np.int64) * H
        pronto = cal.CalendarEvent(key="X", scheduled_at=int(marcas[150]),
                                   announced_at=0)
        f = cal.calendar_features(marcas, [pronto], horizon_bars=200)
        assert f["cal_x_to_next"][100] < 1.0

    @pytest.mark.unit
    def test_lo_que_ya_ocurrio_no_necesita_anuncio(self):
        """Un evento pasado es observable se hubiera anunciado antes o no."""
        marcas = np.arange(200, dtype=np.int64) * H
        sorpresa = cal.CalendarEvent(key="X", scheduled_at=int(marcas[50]),
                                     announced_at=int(marcas[50]))
        f = cal.calendar_features(marcas, [sorpresa], horizon_bars=200)
        assert f["cal_x_since"][60] > 0.0
        assert f["cal_x_active"][52] == 1.0
        assert f["cal_x_active"][100] == 0.0

    @pytest.mark.unit
    def test_las_variables_estan_normalizadas_y_acotadas(self):
        """Sin tope, «faltan 900 velas para el halving» domina la escala y el
        modelo aprende el reloj en vez del evento."""
        marcas = np.arange(500, dtype=np.int64) * H
        ev = cal.derived_calendar(int(marcas[0]), int(marcas[-1]), ("expiry",))
        f = cal.calendar_features(marcas, ev, horizon_bars=48)
        for nombre, v in f.items():
            assert np.all(v >= 0.0) and np.all(v <= 1.0), nombre


# ──────────────────────────────────────────────── los generadores por regla


class TestLoQueSeDerivaPorRegla:

    @pytest.mark.unit
    def test_la_financiacion_es_tres_veces_al_dia(self):
        ev = cal.funding_settlements(_ms("2024-03-01T00:00+00:00"),
                                     _ms("2024-03-30T23:00+00:00"))
        assert len(ev) == 30 * 3
        assert {_hora_utc(e) for e in ev} == {0, 8, 16}

    @pytest.mark.unit
    def test_los_vencimientos_son_viernes_a_las_ocho(self):
        ev = cal.option_expiries(_ms("2024-01-01T00:00+00:00"),
                                 _ms("2024-12-31T23:00+00:00"))
        for e in ev:
            d = datetime.fromtimestamp(e.scheduled_at / 1000, _tz.utc)
            assert d.weekday() == 4 and d.hour == 8

    @pytest.mark.unit
    def test_cada_vencimiento_tiene_una_sola_etiqueta(self):
        """Semanal, mensual y trimestral son eventos distintos y el tamaño se
        concentra en los dos últimos. Si el último viernes de marzo apareciera a
        la vez como semanal y como trimestral, el efecto del grande se diluiría
        en la bolsa del pequeño."""
        ev = cal.option_expiries(_ms("2024-01-01T00:00+00:00"),
                                 _ms("2024-12-31T23:00+00:00"))
        instantes = [e.scheduled_at for e in ev]
        assert len(instantes) == len(set(instantes))
        claves = {e.key for e in ev}
        assert claves == {"OPTION_EXPIRY_WEEKLY", "OPTION_EXPIRY_MONTHLY",
                          "OPTION_EXPIRY_QUARTERLY"}

    @pytest.mark.unit
    def test_hay_cuatro_trimestrales_al_ano(self):
        ev = cal.option_expiries(_ms("2024-01-01T00:00+00:00"),
                                 _ms("2024-12-31T23:00+00:00"))
        trimestrales = [e for e in ev if e.key == "OPTION_EXPIRY_QUARTERLY"]
        assert len(trimestrales) == 4
        meses = {datetime.fromtimestamp(e.scheduled_at / 1000, _tz.utc).month
                 for e in trimestrales}
        assert meses == {3, 6, 9, 12}

    @pytest.mark.unit
    def test_los_cierres_de_periodo_marcan_los_trimestres(self):
        ev = cal.period_ends(_ms("2024-01-01T00:00+00:00"),
                             _ms("2024-12-31T23:00+00:00"))
        assert len([e for e in ev if e.key == "QUARTER_END"]) == 4
        assert len([e for e in ev if e.key == "MONTH_END"]) == 8

    @pytest.mark.unit
    def test_el_ultimo_dia_del_mes_es_el_correcto_en_febrero_bisiesto(self):
        ev = cal.period_ends(_ms("2024-02-01T00:00+00:00"),
                             _ms("2024-02-29T23:00+00:00"))
        assert len(ev) == 1
        d = datetime.fromtimestamp(ev[0].scheduled_at / 1000, _tz.utc)
        assert (d.month, d.day) == (2, 29)

    @pytest.mark.unit
    def test_los_halvings_son_los_ocurridos_y_ninguno_mas(self):
        """El quinto no se estima. Poner una fecha calculada a partir de la
        altura de bloque futura sería exactamente lo que este módulo no hace."""
        ev = cal.bitcoin_halvings(0, _ms("2035-01-01T00:00+00:00"))
        assert len(ev) == len(cal.BITCOIN_HALVINGS) == 4
        ultimo = datetime.fromtimestamp(ev[-1].scheduled_at / 1000, _tz.utc)
        assert (ultimo.year, ultimo.month) == (2024, 4)

    @pytest.mark.unit
    def test_nth_weekday_y_last_weekday(self):
        # El primer viernes de marzo de 2024 fue el día 1; el último, el 29.
        assert cal.nth_weekday(2024, 3, 4, 1).day == 1
        assert cal.last_weekday(2024, 3, 4).day == 29
        # Diciembre obliga a cruzar de año al buscar el último.
        assert cal.last_weekday(2024, 12, 4).day == 27


class TestLoQueNoSeInventa:

    @pytest.mark.unit
    def test_el_fomc_y_el_ipc_se_declaran_ausentes(self):
        """Un calendario con reuniones del FOMC puestas a ojo produciría un
        estudio sobre días en los que no pasó nada, y el ruido resultante se
        leería como «lo macro no mueve cripto»: una conclusión falsa sacada de
        datos falsos."""
        assert "FOMC" in cal.UNDERIVABLE
        assert "CPI" in cal.UNDERIVABLE
        claves = {e.key for e in cal.derived_calendar(
            _ms("2024-01-01T00:00+00:00"), _ms("2024-12-31T00:00+00:00"))}
        assert "FOMC" not in claves
        assert "CPI" not in claves

    @pytest.mark.unit
    def test_la_descripcion_lleva_lo_que_falta(self):
        ev = cal.derived_calendar(_ms("2024-01-01T00:00+00:00"),
                                  _ms("2024-12-31T00:00+00:00"))
        d = cal.describe(ev)
        assert d["total"] == len(ev)
        assert "FOMC" in d["underivable"]
        assert d["by_key"]["FUNDING_SETTLEMENT"] > d["by_key"]["NFP"]

    @pytest.mark.unit
    def test_la_nota_avisa_de_la_estructura_horaria(self):
        nota = cal.self_note()
        assert "sorpresa" in nota.lower()
        assert "hora" in nota.lower()


class TestElPuenteAlModelo:
    """El bloque que entra de verdad en las features del modelo."""

    @pytest.mark.unit
    def test_solo_entran_tres_columnas_y_no_veintiuna(self):
        """Siete familias × tres variables serían veintiuna columnas para un
        modelo que tiene diecisiete. Multiplicaría el espacio de búsqueda por
        encima de lo que la muestra sostiene y el estudio de importancia
        repartiría crédito entre variables casi idénticas."""
        from core.domain.services import exogenous_features as ex

        marcas = np.arange(2000, dtype=np.int64) * H
        ev = cal.derived_calendar(int(marcas[0]), int(marcas[-1]))
        bloque = ex.calendar_features(marcas, ev)
        assert set(bloque) == {"cal_high_to_next", "cal_high_since",
                               "cal_high_active", "calendar_available"}

    @pytest.mark.unit
    def test_solo_cuenta_la_importancia_alta(self):
        """La variable dice «falta poco para algo gordo», no de qué se trata. Una
        liquidación de financiación cada ocho horas dejaría la variable pegada a
        cero y sin información."""
        from core.domain.services import exogenous_features as ex

        marcas = np.arange(2000, dtype=np.int64) * H
        solo_bajos = cal.derived_calendar(int(marcas[0]), int(marcas[-1]),
                                          ("funding",))
        bloque = ex.calendar_features(marcas, solo_bajos)
        assert bloque["calendar_available"].max() == 0.0
        assert np.all(np.isnan(bloque["cal_high_to_next"]))

    @pytest.mark.unit
    def test_sin_calendario_el_bloque_aparece_con_su_bandera_a_cero(self):
        """Omitirlo cambiaría el número de columnas según el activo, y entonces
        dos estudios no serían comparables."""
        from core.domain.services import exogenous_features as ex

        marcas = np.arange(100, dtype=np.int64) * H
        bloque = ex.calendar_features(marcas, [])
        assert bloque["calendar_available"].sum() == 0.0
        assert len(bloque["cal_high_to_next"]) == 100

    @pytest.mark.unit
    def test_el_bloque_esta_registrado_en_la_cobertura(self):
        from core.domain.services import exogenous_features as ex

        assert any(g.name == "calendar" for g in ex.GROUPS)
        marcas = np.arange(2000, dtype=np.int64) * H
        ev = cal.derived_calendar(int(marcas[0]), int(marcas[-1]))
        frame = ex.assemble(marcas, calendar=ev)
        cobertura = ex.coverage(frame)
        assert cobertura["groups"]["calendar"]["coverage_pct"] == 100.0
        assert cobertura["groups"]["calendar"]["usable"] is True


class TestLasRamasVacias:

    @pytest.mark.unit
    def test_sin_marcas_no_hay_features(self):
        assert cal.calendar_features(np.array([], dtype=np.int64), []) == {}

    @pytest.mark.unit
    def test_sin_eventos_no_hay_columnas(self):
        marcas = np.arange(100, dtype=np.int64) * H
        assert cal.calendar_features(marcas, []) == {}

    @pytest.mark.unit
    def test_un_intervalo_vacio_devuelve_lista_vacia(self):
        t = _ms("2024-06-01T00:00+00:00")
        assert cal.derived_calendar(t, t - H) == []

    @pytest.mark.unit
    def test_los_eventos_salen_ordenados(self):
        ev = cal.derived_calendar(_ms("2024-01-01T00:00+00:00"),
                                  _ms("2024-06-30T00:00+00:00"))
        instantes = [e.scheduled_at for e in ev]
        assert instantes == sorted(instantes)
