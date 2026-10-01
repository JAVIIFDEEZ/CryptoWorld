"""
test_execution_window.py — Que el semáforo no se encienda sin base.

El modo de fallo caro de esta herramienta no es equivocar una hora: es **pintar un
semáforo sobre un número que no significa nada**. Si el estudio de estacionalidad
no encontró estructura de hora de la semana, el componente horario no puede entrar
en el veredicto, y el test central de este módulo es precisamente ese.

El segundo modo de fallo es de lectura: que alguien entienda «hora tranquila» como
«ahora sube». La salida nunca habla de dirección y hay un test que lo fija.

Y un defecto que los tests encontraron: con un vencimiento mensual a sesenta
minutos el veredicto salía NEUTRAL, porque solo se miraban los eventos de
importancia ALTA. Un vencimiento a una hora ensancha el diferencial de verdad.
"""

from datetime import datetime, timezone as _tz

import numpy as np
import pytest

from core.domain.services import economic_calendar as cal
from core.domain.services import execution_window as ew
from core.domain.services import seasonality as sn


H = 3_600_000
SEMANAS = 80
N = 24 * 7 * SEMANAS


def _en_casilla(casilla: int, desde: int = 1_700_000_000_000) -> int:
    """Una marca horaria que cae en la casilla pedida de la rejilla semanal."""
    t = desde - (desde % H)
    while int(sn.week_hour_index([t])[0]) != casilla:
        t += H
    return t


# Viernes 13:00 UTC y la rejilla que lo rodea.
AHORA = _en_casilla(4 * 24 + 13)
MARCAS = np.arange(N, dtype=np.int64) * H + AHORA - N * H
IDX = sn.week_hour_index(MARCAS)
VIERNES_TARDE = (IDX // 24 == 4) & ((IDX % 24) >= 12) & ((IDX % 24) < 16)


def _rejilla(con_estructura: bool, seed: int = 3) -> dict:
    """Rejilla con una casilla plantada, o sin ninguna estructura."""
    r = np.random.default_rng(seed).normal(0, 0.004, N)
    if con_estructura:
        r = np.where(VIERNES_TARDE, r * 2.5, r)
    return sn.analyse(MARCAS, r, rotations=200, seed=seed)


REJILLA_CON = _rejilla(True)
REJILLA_SIN = _rejilla(False, seed=9)


def _eventos(t: int, horas: int = 52) -> list:
    return cal.derived_calendar(t - 2 * H, t + horas * H)


def _antes_de(clave: str, margen_h: int) -> int:
    """Marca `margen_h` horas antes del próximo evento de esa familia."""
    futuros = cal.derived_calendar(AHORA, AHORA + 150 * 24 * H)
    objetivo = next(e for e in futuros if e.key == clave)
    return objetivo.scheduled_at - margen_h * H


# ──────────────────────────────────────────── lo que no se hace sin base


class TestNoSeEnciendeElSemaforoSinBase:

    @pytest.mark.unit
    def test_sin_estructura_horaria_el_veredicto_lo_declara(self):
        """El test central. Si la rejilla no encontró estructura, la hora NO puede
        entrar en el veredicto: un semáforo sobre un número sin significado es
        peor que no tener semáforo."""
        salida = ew.assess(AHORA, REJILLA_SIN, _eventos(AHORA))
        assert REJILLA_SIN["verdict"] == "SIN_ESTRUCTURA"
        assert salida["verdict"] == "SIN_BASE_HORARIA"
        assert salida["seasonality_usable"] is False
        assert "NO entra en el veredicto" in " ".join(salida["reasons"])

    @pytest.mark.unit
    def test_sin_estructura_la_actividad_por_hora_no_se_publica(self):
        """Y no se publica el número, para que nadie lo pinte."""
        salida = ew.assess(AHORA, REJILLA_SIN, _eventos(AHORA))
        assert all(h["activity"] is None for h in salida["hours"])

    @pytest.mark.unit
    def test_sin_estructura_no_significa_que_todas_las_horas_sean_iguales(self):
        """La diferencia entre «no hay efecto» y «no se puede saber» tiene que
        estar escrita, porque es la que decide si alguien busca más datos."""
        salida = ew.assess(AHORA, REJILLA_SIN, _eventos(AHORA))
        assert "no se puede saber" in salida["note"]

    @pytest.mark.unit
    def test_una_casilla_que_no_sobrevive_a_la_correccion_se_marca_como_pista(self):
        """Actividad alta sin significación es una pista, no un hecho, y el texto
        lo dice: es la diferencia entre mirar y afirmar."""
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA))
        ahora = salida["now"]
        texto = " ".join(salida["reasons"])
        if ahora["established"]:
            assert "sobrevive a la corrección" in texto
        else:
            assert "NO sobrevive" in texto


class TestLoQueNoDice:

    @pytest.mark.unit
    def test_nunca_habla_de_direccion(self):
        """El modo de fallo de lectura: «hora tranquila» no es «ahora sube». Ni el
        veredicto ni las razones pueden sugerir dirección."""
        for rejilla in (REJILLA_CON, REJILLA_SIN):
            salida = ew.assess(AHORA, rejilla, _eventos(AHORA))
            texto = (" ".join(salida["reasons"]) + salida["note"]).lower()
            for prohibido in ("comprar", "vender", "subirá", "bajará", "alcista",
                              "bajista", "señal de compra"):
                assert prohibido not in texto, prohibido

    @pytest.mark.unit
    def test_la_nota_de_limites_avisa_de_que_es_un_filtro(self):
        nota = ew.self_note()
        assert "FILTRO DE EJECUCIÓN" in nota
        assert "no es una hora en la que suba" in nota

    @pytest.mark.unit
    def test_declara_que_el_calendario_no_cubre_lo_macro(self):
        """Que no haya eventos en la lista no significa que no haya nada previsto;
        significa que no hay nada de lo que este motor sabe derivar."""
        assert "FOMC" in ew.self_note()


# ─────────────────────────────────────────────────── los veredictos


class TestLosVeredictos:

    @pytest.mark.unit
    def test_dentro_de_una_hora_activa_sale_desfavorable(self):
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA))
        assert salida["verdict"] == "DESFAVORABLE"
        assert "hora_activa" in salida["signals"]
        assert salida["now"]["activity"] > ew.ACTIVIDAD_ALTA

    @pytest.mark.unit
    def test_un_evento_de_importancia_alta_encima_manda_esperar(self):
        t = _antes_de("OPTION_EXPIRY_QUARTERLY", 1)
        salida = ew.assess(t, REJILLA_SIN, _eventos(t))
        assert salida["verdict"] == "ESPERAR"
        assert "evento_inminente" in salida["signals"]

    @pytest.mark.unit
    def test_la_nomina_no_agricola_tambien_manda_esperar(self):
        t = _antes_de("NFP", 1)
        salida = ew.assess(t, REJILLA_SIN, _eventos(t))
        assert salida["verdict"] == "ESPERAR"

    @pytest.mark.unit
    def test_un_evento_de_importancia_media_a_una_hora_si_cuenta(self):
        """El defecto que este test fija: con un vencimiento mensual a sesenta
        minutos el veredicto salía NEUTRAL, porque solo se miraban los de
        importancia alta. Un vencimiento a una hora ensancha el diferencial."""
        t = _antes_de("OPTION_EXPIRY_MONTHLY", 1)
        salida = ew.assess(t, REJILLA_SIN, _eventos(t))
        assert salida["verdict"] == "DESFAVORABLE"
        assert "evento_cercano" in salida["signals"]

    @pytest.mark.unit
    def test_lejos_de_cualquier_evento_no_se_inventa_una_alarma(self):
        t = _antes_de("OPTION_EXPIRY_QUARTERLY", 10)
        salida = ew.assess(t, REJILLA_SIN, _eventos(t))
        assert "evento_inminente" not in salida["signals"]
        assert "evento_cercano" not in salida["signals"]

    @pytest.mark.unit
    def test_un_coste_que_domina_manda_sobre_la_hora(self):
        """A 120 puntos básicos, la hora del día es el menor de los problemas: lo
        que hay que cambiar es el tamaño, y el veredicto tiene que decir eso y no
        «espera»."""
        coste = {"available": True, "steps": [{"impact_bps": 120.0}]}
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA), coste)
        assert salida["verdict"] == "EL_TAMANO_MANDA"
        assert "trocear" in salida["note"] or "Trocear" in salida["note"]

    @pytest.mark.unit
    def test_un_coste_pequeno_no_cambia_el_veredicto(self):
        coste = {"available": True, "steps": [{"impact_bps": 3.0}]}
        sin = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA))
        con = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA), coste)
        assert con["verdict"] == sin["verdict"]

    @pytest.mark.unit
    def test_un_coste_no_disponible_no_tumba_el_veredicto_horario(self):
        """El coste sale de la cadena que consulta la red; sin salida a internet no
        hay número, y el valor principal de la pantalla no depende de él."""
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA), None)
        assert salida["verdict"] == "DESFAVORABLE"
        assert salida["cost_bps_first_step"] is None


# ─────────────────────────────────────────────────── la mejor ventana


class TestLaMejorVentana:

    @pytest.mark.unit
    def test_propone_una_ventana_a_la_que_se_pueda_llegar(self):
        """La hora en curso ya está empezada, así que no puede ser la propuesta:
        sin saltarla, la herramienta recomendaría esperar a un momento pasado."""
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA))
        assert salida["best_window"]["in_hours"] >= 1

    @pytest.mark.unit
    def test_la_ventana_elegida_es_mas_barata_que_la_hora_actual(self):
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA))
        assert salida["best_window"]["score"] <= salida["hours"][0]["score"]

    @pytest.mark.unit
    def test_evita_las_casillas_activas_plantadas(self):
        """Con la actividad duplicada en viernes 12–15 UTC, la ventana propuesta no
        puede caer dentro de ese tramo."""
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA))
        v = salida["best_window"]
        assert not (v["day"] == "vie" and 12 <= v["hour_utc"] < 16)

    @pytest.mark.unit
    def test_una_ventana_mas_larga_no_puede_ser_mas_barata(self):
        """Promediar más horas solo puede acercar la puntuación a la media."""
        corta = ew.find_window(ew.score_hours(AHORA, REJILLA_CON, _eventos(AHORA)), 2)
        larga = ew.find_window(ew.score_hours(AHORA, REJILLA_CON, _eventos(AHORA)), 8)
        assert larga["score"] >= corta["score"]

    @pytest.mark.unit
    def test_sin_horizonte_suficiente_no_hay_ventana(self):
        assert ew.find_window([], 2) is None
        pocas = ew.score_hours(AHORA, REJILLA_CON, _eventos(AHORA), horizon_hours=2)
        assert ew.find_window(pocas, 4) is None


# ───────────────────────────────────────────── la puntuación por hora


class TestLaPuntuacionPorHora:

    @pytest.mark.unit
    def test_hay_una_fila_por_hora_del_horizonte(self):
        horas = ew.score_hours(AHORA, REJILLA_CON, _eventos(AHORA), horizon_hours=24)
        assert len(horas) == 24
        # Consecutivas y alineadas a la hora en punto.
        for i in range(1, len(horas)):
            assert horas[i]["hour_ms"] - horas[i - 1]["hour_ms"] == H
        assert all(h["hour_ms"] % H == 0 for h in horas)

    @pytest.mark.unit
    def test_la_casilla_de_cada_hora_es_la_correcta(self):
        horas = ew.score_hours(AHORA, REJILLA_CON, _eventos(AHORA), horizon_hours=48)
        for h in horas:
            esperada = int(sn.week_hour_index([h["hour_ms"]])[0])
            assert h["cell"] == esperada
            assert h["day"] == sn.DAY_NAMES[esperada // 24]
            assert h["hour_utc"] == esperada % 24

    @pytest.mark.unit
    def test_un_evento_encarece_su_propia_hora(self):
        t = _antes_de("OPTION_EXPIRY_QUARTERLY", 0)
        horas = ew.score_hours(t, REJILLA_SIN, _eventos(t), horizon_hours=24)
        con_evento = [h for h in horas if h["events"]]
        sin_evento = [h for h in horas if not h["events"]]
        assert con_evento, "el fixture tiene que tener alguna hora con evento"
        assert min(h["score"] for h in con_evento) >= min(h["score"]
                                                          for h in sin_evento)

    @pytest.mark.unit
    def test_el_recargo_por_evento_se_suma_y_no_multiplica(self):
        """Multiplicarlos haría que una hora ya activa con un evento pareciera
        catastrófica, y el recargo dejaría de ser legible.

        La hora del vencimiento trimestral —viernes 08:00 UTC— es TAMBIÉN una
        liquidación de financiación, así que lleva dos recargos. La expectativa se
        deriva de los eventos que de verdad hay en esa hora y no de un número
        escrito a mano: con la rejilla plana la actividad es 1,0 y el resto es la
        suma de los recargos.
        """
        recargo = {cal.ALTA: 0.35, cal.MEDIA: 0.15, cal.BAJA: 0.05}
        t = _antes_de("OPTION_EXPIRY_QUARTERLY", 0)
        eventos = _eventos(t)
        horas = ew.score_hours(t, REJILLA_SIN, eventos, horizon_hours=6)
        con = next(h for h in horas if cal.ALTA in h["event_importance"])

        por_clave = {e.key: e.importance for e in eventos}
        esperado = 1.0 + sum(recargo[por_clave[k]] for k in con["events"])
        assert len(con["events"]) >= 2, "la hora tiene que llevar más de un evento"
        assert con["score"] == pytest.approx(esperado, abs=1e-9)

    @pytest.mark.unit
    def test_la_puntuacion_no_se_presenta_como_un_contraste(self):
        """Es una ordenación para decidir cuándo mirar, no un p-valor. Prestarle
        rigor estadístico sería el error."""
        salida = ew.assess(AHORA, REJILLA_CON, _eventos(AHORA))
        assert "ORDENACIÓN" in salida["protocol"]
        assert "no un contraste" in salida["protocol"]


class TestLosEventosProximos:

    @pytest.mark.unit
    def test_solo_los_del_horizonte_y_ordenados(self):
        eventos = _eventos(AHORA, horas=200)
        proximos = ew.upcoming_events(eventos, AHORA, 24)
        assert proximos
        assert all(0 <= e["in_hours"] <= 24 for e in proximos)
        assert [e["at_ms"] for e in proximos] == sorted(e["at_ms"] for e in proximos)

    @pytest.mark.unit
    def test_las_liquidaciones_de_financiacion_aparecen_cada_ocho_horas(self):
        proximos = ew.upcoming_events(_eventos(AHORA), AHORA, 24)
        horas = sorted({
            datetime.fromtimestamp(e["at_ms"] / 1000, _tz.utc).hour
            for e in proximos if e["key"] == "FUNDING_SETTLEMENT"
        })
        assert set(horas) <= {0, 8, 16}

    @pytest.mark.unit
    def test_un_calendario_vacio_no_revienta(self):
        salida = ew.assess(AHORA, REJILLA_CON, [])
        assert salida["upcoming_events"] == []
        assert salida["verdict"] in ("DESFAVORABLE", "NEUTRAL", "FAVORABLE")
