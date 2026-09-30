"""
test_event_study.py — La tasa de falso positivo de un estudio de eventos.

Un estudio de eventos es trivial de escribir y casi imposible de creer: coge
velas alrededor de unas fechas, ve que el precio se movió y concluye lo que sea.
Por eso los tests centrales de este módulo miden dos cosas sobre datos donde se
conoce la respuesta:

1. **Cuántas veces dice que hay efecto cuando no lo hay.** Medido: 3 de 72
   series sintéticas sin efecto plantado, un 4,2 % contra un 5 % nominal.
2. **Que no se deje engañar por la estructura del calendario.** Es el test que
   justifica el módulo entero: sobre una serie con un efecto fuerte de *viernes
   por la mañana* y NINGÚN efecto de evento, la razón de volatilidad observada en
   los vencimientos es de 2,37× — y el contraste correcto dice p=0,83 mientras
   que el ingenuo da p=0,005 y un falso positivo redondo.

Y dos defectos que estos tests fijan porque la calibración los encontró:

· El nulo remuestreaba el grupo de control y comparaba la media de los eventos
  contra esa distribución. Queda centrado en la media del control —que tiene su
  propio error— y la tasa de falso positivo medida se fue al 17 %. Se sustituyó
  por una permutación de etiquetas, que está exactamente calibrada.
· Antes de eso, el sorteo del control era sin reemplazo, y la corrección de
  población finita estrechaba el nulo hasta un 21 % de falsos positivos.
"""

import numpy as np
import pytest

from core.domain.services import economic_calendar as cal
from core.domain.services import event_study as es


H = 3_600_000
N = 24 * 365 * 2
VOL = 0.004
INICIO = 1_600_000_000_000 - (1_600_000_000_000 % H)
MARCAS = np.arange(N, dtype=np.int64) * H + INICIO


def serie(seed, indices=(), vol_mult=1.0, drift=0.0, post=6, viernes=1.0):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, VOL, N)
    if viernes != 1.0:
        dow = ((MARCAS // 86_400_000) + 3) % 7
        hora = (MARCAS // H) % 24
        r = np.where((dow == 4) & (hora >= 8) & (hora <= 14), r * viernes, r)
    for i in indices:
        fin = min(i + post + 1, N)
        if vol_mult != 1.0:
            r[i:fin] *= vol_mult
        if drift:
            r[i:fin] += drift
    return r


def familia(claves):
    ev = cal.derived_calendar(int(MARCAS[0]), int(MARCAS[-1]))
    return np.array([e.scheduled_at for e in ev if e.key in claves], dtype=np.int64)


MENSUAL = familia({"OPTION_EXPIRY_MONTHLY", "OPTION_EXPIRY_QUARTERLY"})
SEMANAL = familia({"OPTION_EXPIRY_WEEKLY"})
FUNDING = familia({"FUNDING_SETTLEMENT"})


def indices(t):
    idx = es.align_events(MARCAS, t)
    return idx[idx >= 0]


# ────────────────────────────────────────────── lo que promete el contraste


class TestLaTasaDeFalsoPositivo:

    @pytest.mark.unit
    def test_sin_efecto_plantado_casi_nunca_dice_que_lo_hay(self):
        """12 series sin efecto. Con un 5 % nominal se espera 0,6; se admite
        hasta 3, que es el percentil ~98 de una binomial(12, 0.05)."""
        positivos = sum(
            1 for s in range(12)
            if es.study(MARCAS, serie(700 + s), MENSUAL, replicates=200,
                        seed=700 + s).get("significant")
        )
        assert positivos <= 3, f"{positivos}/12 falsos positivos"

    @pytest.mark.unit
    def test_la_permutacion_esta_centrada(self):
        """El defecto que motivó el cambio de contraste: comparar contra un
        remuestreo del control deja el nulo centrado en la media del CONTROL, que
        tiene su propio error. Con dos muestras de la misma distribución, el
        p-valor de la permutación tiene que repartirse por todo el intervalo y no
        acumularse en los extremos."""
        rng = np.random.default_rng(3)
        ps = []
        for _ in range(60):
            a = rng.normal(0, 1, 40)
            b = rng.normal(0, 1, 120)
            ps.append(es.permutation_p(float(a.mean()), a, b, 200, rng))
        ps = np.array(ps)
        assert 0.3 < float(np.mean(ps < 0.5)) < 0.7
        assert float(np.mean(ps < 0.05)) < 0.20


class TestLaTrampaDelCalendario:

    @staticmethod
    def _p_ingenuo(r, rng):
        """p-valor con control sorteado uniformemente, sin conservar hora ni día."""
        obs = es._aggregate(es.window_batch(r, indices(MENSUAL)))
        nulos = []
        for _ in range(200):
            p = rng.integers(MARCAS[0], MARCAS[-1], size=MENSUAL.size)
            pidx = es.align_events(MARCAS, p)
            lote = es.window_batch(r, pidx[pidx >= 0])
            if lote["index"].size >= es.MIN_EVENTS:
                nulos.append(es._aggregate(lote)["vol_ratio_mean"])
        return (1 + sum(1 for v in nulos if v >= obs["vol_ratio_mean"])) / (len(nulos) + 1)

    @pytest.mark.unit
    def test_el_efecto_de_viernes_engana_al_control_ingenuo_y_no_al_emparejado(self):
        """El test que justifica el módulo entero.

        La serie tiene un efecto brutal de viernes por la mañana y NINGÚN efecto
        de vencimiento. Como los vencimientos son todos viernes a las 08:00, su
        razón de volatilidad observada sale en torno a 2,5× — parece un hallazgo
        enorme y no hay nada.

        Se compara sobre ocho semillas para que el resultado no dependa de una:
        el control ingenuo —instantes uniformes— se deja engañar casi siempre,
        mientras que el emparejado —los demás viernes a las 08:00, que llevan el
        mismo efecto dentro— casi nunca. No se afirma «nunca»: el contraste tiene
        su tasa nominal y dispararse alguna vez es parte del diseño.
        """
        rng = np.random.default_rng(7)
        enganados_ingenuo = enganados_emparejado = 0
        for s in range(43, 51):
            r = serie(s, viernes=2.5)
            out = es.study(MARCAS, r, MENSUAL, replicates=300, seed=s)
            assert out["observed"]["vol_ratio_mean"] > 1.8, "el sesgo tiene que estar"
            enganados_emparejado += out["p_volatility"] < 0.025
            enganados_ingenuo += self._p_ingenuo(r, rng) < 0.025

        assert enganados_ingenuo >= 7, (
            f"el control ingenuo solo se engañó {enganados_ingenuo}/8: el test no "
            f"está midiendo lo que cree")
        assert enganados_emparejado <= 2, (
            f"el control emparejado se engañó {enganados_emparejado}/8")
        assert enganados_emparejado < enganados_ingenuo


class TestLoQueSiDetecta:

    @pytest.mark.unit
    def test_un_efecto_de_volatilidad_moderado_se_detecta(self):
        r = serie(41, indices(MENSUAL), vol_mult=1.5)
        out = es.study(MARCAS, r, MENSUAL, replicates=300, seed=41)
        assert out["significant"] is True
        assert out["p_volatility"] < 0.025
        assert out["observed"]["vol_ratio_mean"] > 1.3

    @pytest.mark.unit
    def test_un_efecto_direccional_grande_se_detecta(self):
        r = serie(42, indices(MENSUAL), drift=0.002)
        out = es.study(MARCAS, r, MENSUAL, replicates=300, seed=42)
        assert out["p_direction"] < 0.025

    @pytest.mark.unit
    def test_un_efecto_direccional_por_debajo_de_la_potencia_no_se_detecta(self):
        """Y el informe dice por qué: el efecto mínimo detectable es mayor que el
        plantado. «No se detecta» y «no lo hay» no son lo mismo, y esta es la
        diferencia."""
        r = serie(42, indices(MENSUAL), drift=0.0005)
        out = es.study(MARCAS, r, MENSUAL, replicates=300, seed=42)
        assert out["verdict"] == "SIN_EFECTO_DETECTABLE"
        plantado = 0.0005 * (es.DEFAULT_POST + 1)
        assert out["minimum_detectable_car"] > plantado


class TestLoQueNoEsIdentificable:

    @pytest.mark.unit
    def test_una_familia_densa_con_ventana_larga_lo_dice(self):
        """Liquidaciones cada 8 h con ventana de reacción de 6: las ventanas
        tejen todo el histórico y no queda ni un instante normal contra el que
        comparar. El módulo se niega en vez de devolver un «no hay efecto» que
        sería un artefacto."""
        out = es.study(MARCAS, serie(45), FUNDING, replicates=50,
                       null_mode="offset", post=6, seed=45)
        assert out["verdict"] == "NO_IDENTIFICABLE"
        assert out["control_candidates"] == 0

    @pytest.mark.unit
    def test_con_ventana_corta_la_misma_familia_si_es_identificable(self):
        """La pareja: acortando la reacción cabe un hueco y el estudio procede."""
        out = es.study(MARCAS, serie(46), FUNDING, replicates=50,
                       null_mode="offset", post=2, seed=46)
        assert out["verdict"] != "NO_IDENTIFICABLE"
        assert out["control_usable"] > es.MIN_EVENTS

    @pytest.mark.unit
    def test_el_desplazamiento_semanal_es_degenerado_en_familias_semanales(self):
        """Desplazar semanas enteras un vencimiento semanal aterriza sobre otro
        vencimiento semanal: el control contendría la señal."""
        out = es.study(MARCAS, serie(47), FUNDING, replicates=50,
                       null_mode="week", seed=47)
        assert out["verdict"] == "NO_IDENTIFICABLE"

    @pytest.mark.unit
    def test_pocos_eventos_es_sin_potencia_y_no_sin_efecto(self):
        out = es.study(MARCAS, serie(48), MENSUAL[:5], replicates=50, seed=48)
        assert out["verdict"] == "SIN_POTENCIA"
        assert out["significant"] is False


# ───────────────────────────────────────────────────────────── las piezas


class TestElAlineamiento:

    @pytest.mark.unit
    def test_el_evento_va_a_la_vela_que_LO_CONTIENE(self):
        """Redondear a la vela más cercana colocaría la mitad de los eventos en
        la ANTERIOR, cuyo retorno ya estaba cerrado antes del evento: lookahead
        puro, con una reacción que empieza antes que la causa."""
        marcas = np.arange(10, dtype=np.int64) * H
        # Un evento a los 50 minutos de la vela 3 pertenece a la vela 3, aunque
        # esté mucho más cerca del comienzo de la 4.
        idx = es.align_events(marcas, [3 * H + 50 * 60 * 1000])
        assert idx[0] == 3

    @pytest.mark.unit
    def test_un_evento_justo_en_la_apertura_es_de_esa_vela(self):
        marcas = np.arange(10, dtype=np.int64) * H
        assert es.align_events(marcas, [5 * H])[0] == 5

    @pytest.mark.unit
    def test_un_evento_fuera_del_historico_se_marca_con_menos_uno(self):
        marcas = np.arange(10, dtype=np.int64) * H
        idx = es.align_events(marcas, [-H, 100 * H])
        assert idx[0] == -1
        # Más allá del final cae en la última vela solo si entra en su duración.
        assert idx[1] == -1

    @pytest.mark.unit
    def test_un_evento_en_un_hueco_de_velas_no_se_asigna(self):
        """Si falta la vela 5, un evento en ese hueco no pertenece a la 4."""
        marcas = np.array([0, 1, 2, 3, 4, 6, 7], dtype=np.int64) * H
        assert es.align_events(marcas, [5 * H + 600_000])[0] == -1


class TestLasVentanas:

    @pytest.mark.unit
    def test_la_version_de_uno_y_la_de_lote_coinciden(self):
        """`window_stats` es un envoltorio de `window_batch` para que no puedan
        desviarse. El test lo fija."""
        r = serie(50)
        idx = indices(MENSUAL)[:20]
        lote = es.window_batch(r, idx)
        for k, i in enumerate(lote["index"]):
            uno = es.window_stats(r, int(i))
            assert uno["car"] == pytest.approx(float(lote["car"][k]))
            assert uno["vol_ratio"] == pytest.approx(float(lote["vol_ratio"][k]))

    @pytest.mark.unit
    def test_un_evento_sin_sitio_se_descarta_y_no_se_recorta(self):
        """Recortar la ventana haría que los eventos de los extremos se midieran
        con menos datos y pesaran distinto sin que nada lo dijera."""
        r = serie(51)
        assert es.window_stats(r, 5) is None            # sin estimación delante
        assert es.window_stats(r, N - 2) is None        # sin reacción detrás
        assert es.window_stats(r, 500) is not None

    @pytest.mark.unit
    def test_la_estimacion_deja_un_hueco_antes_del_evento(self):
        """Sin hueco, el posicionamiento previo entra en la referencia, sube su
        volatilidad y el efecto se mide contra una referencia contaminada."""
        r = np.full(400, 0.01)
        # El posicionamiento previo: solo las 50 velas justo antes del evento son
        # grandes. Con hueco de 60 la estimación no las ve; sin hueco, sí.
        r[330:380] = 0.05
        con = es.window_stats(r, 380, estimation=100, gap=60)
        sin = es.window_stats(r, 380, estimation=100, gap=0)
        assert con["baseline_vol"] == pytest.approx(0.01)
        assert sin["baseline_vol"] > con["baseline_vol"] * 1.5

    @pytest.mark.unit
    def test_una_referencia_plana_no_produce_division_por_cero(self):
        r = np.zeros(400)
        r[380:] = 0.01
        assert es.window_stats(r, 380) is None


class TestElGrupoDeControl:

    @pytest.mark.unit
    def test_el_emparejado_conserva_hora_y_dia_de_la_semana(self):
        ctrl = es.control_times(MARCAS, MENSUAL, "matched", tolerance_ms=6 * H)
        assert ctrl.size > 0
        assert (set(es.weekday_hour_key(ctrl).tolist())
                <= set(es.weekday_hour_key(MENSUAL).tolist()))

    @pytest.mark.unit
    def test_el_emparejado_excluye_los_propios_eventos(self):
        ctrl = es.control_times(MARCAS, MENSUAL, "matched", tolerance_ms=6 * H)
        assert not set(ctrl.tolist()) & set(MENSUAL.tolist())

    @pytest.mark.unit
    def test_el_control_no_se_sale_del_historico(self):
        ctrl = es.control_times(MARCAS, MENSUAL, "week", tolerance_ms=6 * H)
        assert ctrl.min() >= MARCAS[0] and ctrl.max() <= MARCAS[-1]

    @pytest.mark.unit
    def test_una_tolerancia_mayor_deja_menos_control(self):
        """La tolerancia tiene que superar la separación entre eventos para morder.

        Los vencimientos mensuales están a más de siete días unos de otros, así
        que una tolerancia de 48 h no quita ningún viernes: hay que llegar a ocho
        días. Es la misma aritmética que hace no identificable a la financiación,
        donde los eventos están a ocho HORAS y una ventana de reacción de seis se
        come todo el control.
        """
        poco = es.control_times(MARCAS, MENSUAL, "matched", tolerance_ms=48 * H)
        mucho = es.control_times(MARCAS, MENSUAL, "matched", tolerance_ms=192 * H)
        assert mucho.size < poco.size

    @pytest.mark.unit
    def test_en_una_familia_densa_la_ventana_de_reaccion_borra_el_control(self):
        """La aritmética que produce el NO_IDENTIFICABLE, aislada."""
        con_hueco = es.control_times(MARCAS, FUNDING, "offset", tolerance_ms=2 * H,
                                     offset_hours=4.0)
        sin_hueco = es.control_times(MARCAS, FUNDING, "offset", tolerance_ms=6 * H,
                                     offset_hours=4.0)
        assert con_hueco.size > 1000
        assert sin_hueco.size == 0

    @pytest.mark.unit
    def test_la_clave_dia_hora_es_la_correcta(self):
        # 1970-01-01 fue jueves: en el convenio de Python, el 3.
        assert es.weekday_hour_key([0])[0] == 3 * 24
        assert es.weekday_hour_key([5 * H])[0] == 3 * 24 + 5


class TestLaPotencia:

    @pytest.mark.unit
    def test_mas_eventos_bajan_el_efecto_minimo_detectable(self):
        assert (es.minimum_detectable_car(0.02, 100)
                < es.minimum_detectable_car(0.02, 25))

    @pytest.mark.unit
    def test_con_un_solo_evento_no_hay_potencia_que_declarar(self):
        assert not np.isfinite(es.minimum_detectable_car(0.02, 1))

    @pytest.mark.unit
    def test_el_informe_publica_la_potencia_aunque_no_encuentre_nada(self):
        out = es.study(MARCAS, serie(60), MENSUAL, replicates=100, seed=60)
        assert np.isfinite(out["minimum_detectable_car"])
        assert "protocol" in out and "note" in out

    @pytest.mark.unit
    def test_la_nota_avisa_del_coste_de_ejecucion(self):
        """Un efecto detectado no es una estrategia: el evento es justo cuando el
        diferencial se abre y la profundidad desaparece."""
        assert "ejecución" in es.self_note() or "ejecucion" in es.self_note()


class TestLasRamasVacias:

    @pytest.mark.unit
    def test_series_desalineadas_lo_dicen(self):
        out = es.study(np.arange(10), np.zeros(9), [1])
        assert out["verdict"] == "SIN_DATOS"

    @pytest.mark.unit
    def test_sin_eventos_no_hay_estudio(self):
        out = es.study(MARCAS, serie(61), np.array([], dtype=np.int64))
        assert out["verdict"] == "SIN_POTENCIA"

    @pytest.mark.unit
    def test_el_intervalo_de_vela_sale_de_la_mediana(self):
        assert es.bar_interval_ms(MARCAS) == H
        assert es.bar_interval_ms(np.array([0], dtype=np.int64)) == H
