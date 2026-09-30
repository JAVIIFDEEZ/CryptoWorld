"""
test_structural_break.py — El umbral que promete un 5 % tiene que dar un 5 %.

Un detector de rupturas es fácil de escribir y difícil de creer. Corre, devuelve
un veredicto, y no hay forma de saber si el veredicto significa algo mirando el
código. Por eso los tests centrales de este módulo no comprueban ramas: miden la
TASA DE FALSA ALARMA sobre series donde por construcción no ha pasado nada, y el
RETARDO sobre series donde se sabe exactamente cuándo pasó.

Tres de estos tests existen porque la primera versión del módulo fallaba
justamente ahí, y ninguno de los tres fallos habría salido de una revisión de
código:

1. La holgura del CUSUM estaba puesta a media sigma «porque parece razonable».
   Sobre el producto cruzado por barra, pasar de una correlación de 0.80 a 0.30
   —una ruptura brutal— es un desplazamiento de 0.42 sigmas: la holgura se lo
   comía entero. Detectaba 8 de 60 rupturas evidentes.
2. Sin desvolatilizar, la falsa alarma medida sobre retornos con volatilidad
   agrupada se iba al 20 % contra el 5 % prometido. El detector avisaba de
   tormentas, no de rupturas.
3. El módulo devolvía un `earliest_cause_index` presentado como cota inferior del
   momento de la ruptura. Medido contra rupturas plantadas, acertaba 0 de 10: la
   cota era falsa. Se sustituyó por el estimador de punto de cambio del propio
   CUSUM, que sí se puede medir —y que llega unas pocas barras TARDE, no pronto,
   cosa que el test fija para que nadie vuelva a leerlo como una cota.

Los tests de tasa usan pocas réplicas a propósito: lo que se defiende aquí es que
el procedimiento no esté roto, y la calibración fina vive en el script de
laboratorio. Un test que tardara diez minutos no se ejecutaría.
"""

import numpy as np
import pytest

from core.domain.services import structural_break as sb


VOL = 0.02


def pareja(n=1400, rho=0.80, seed=1, rho2=None, corte=None, garch=False):
    """Retornos emparejados con correlación `rho`, y `rho2` a partir de `corte`."""
    rng = np.random.default_rng(seed)
    e1 = rng.standard_normal(n)
    e2 = rng.standard_normal(n)
    r = np.full(n, float(rho))
    if rho2 is not None and corte is not None:
        r[corte:] = float(rho2)
    vol = np.full(n, VOL)
    if garch:
        h = VOL ** 2
        for t in range(n):
            vol[t] = np.sqrt(h)
            h = 1e-6 + 0.10 * (vol[t] * e1[t]) ** 2 + 0.87 * h
    a = e1 * vol
    b = (r * e1 + np.sqrt(np.maximum(1.0 - r ** 2, 0.0)) * e2) * vol
    return a, b


def ruptura_en(corte=900, w=30, ref=500, devol=True):
    """Índice, en el tramo vigilado, donde la ruptura entra en la ventana.

    Tres cambios de coordenadas encadenados: el cebado de la volatilidad local se
    come las primeras barras, la correlación del índice i resume los retornos
    [i, i+w), y el CUSUM vigila a partir de `ref`.
    """
    c = corte - (sb.DEVOL_WARMUP if devol else 0)
    return c - w + 1 - ref


# --------------------------------------------------------------- lo que promete


class TestLaTasaDeFalsaAlarma:
    """Lo único que convierte el umbral en un número con significado."""

    @pytest.mark.unit
    def test_bajo_el_nulo_casi_nunca_avisa(self):
        """Correlación constante: el detector tiene que callarse casi siempre.

        Con 40 series y un 5 % prometido se esperan 2 alarmas. Se admite hasta 6
        —que es el percentil ~99 de una binomial(40, 0.05)— porque por debajo de
        eso el test fallaría por azar más a menudo que por un fallo real.
        """
        alarmas = sum(
            1 for s in range(40)
            if sb.correlation_break(*pareja(seed=100 + s), window=30,
                                    reference=500, replicates=120,
                                    seed=100 + s)["broken"]
        )
        assert alarmas <= 6, f"{alarmas}/40 falsas alarmas con un 5 % prometido"

    @pytest.mark.unit
    def test_con_volatilidad_agrupada_sigue_callandose(self):
        """El caso que rompía la versión sin desvolatilizar.

        La volatilidad agrupada no cambia ninguna correlación: solo hace que unas
        ventanas sean más convulsas que otras. Un detector que confunda eso con
        una ruptura es peor que no tener detector, porque avisa precisamente en
        los momentos en los que se está mirando.
        """
        alarmas = sum(
            1 for s in range(40)
            if sb.correlation_break(*pareja(seed=200 + s, garch=True), window=30,
                                    reference=500, replicates=120,
                                    seed=200 + s)["broken"]
        )
        assert alarmas <= 6, f"{alarmas}/40 falsas alarmas con volatilidad agrupada"

    @pytest.mark.unit
    def test_desvolatilizar_es_lo_que_arregla_la_volatilidad_agrupada(self):
        """La corrección se mide, no se declara.

        Si algún día alguien quita la desvolatilización por simplificar, este test
        enseña el número que se pierde. No exige una diferencia enorme —el tamaño
        muestral es pequeño— sino que la versión sin corregir avise MÁS.
        """
        def alarmas(devol):
            return sum(
                1 for s in range(30)
                if sb.correlation_break(*pareja(seed=300 + s, garch=True),
                                        window=30, reference=500, replicates=120,
                                        devol=devol, seed=300 + s)["broken"]
            )
        assert alarmas(True) <= alarmas(False)


class TestLoQueSiTieneQueDetectar:

    @pytest.mark.unit
    def test_una_ruptura_grande_se_detecta_siempre(self):
        """0.80 → 0.30 es el final de una diversificación. Si esto se escapa, el
        detector no sirve para nada."""
        detectadas = sum(
            1 for s in range(20)
            if sb.correlation_break(*pareja(seed=400 + s, rho2=0.30, corte=900),
                                    window=30, reference=500, replicates=120,
                                    seed=400 + s)["broken"]
        )
        assert detectadas >= 18, f"solo {detectadas}/20"

    @pytest.mark.unit
    def test_el_retardo_es_de_decenas_de_barras_y_no_de_cientos(self):
        """El retardo es el producto de verdad de este módulo: un aviso que llega
        400 barras tarde llega después de la pérdida."""
        v = ruptura_en()
        retardos = []
        for s in range(20):
            out = sb.correlation_break(*pareja(seed=500 + s, rho2=0.30, corte=900),
                                       window=30, reference=500, replicates=120,
                                       seed=500 + s)
            if out["broken"]:
                retardos.append(out["alarm_index"] - v)
        assert len(retardos) >= 18
        assert np.median(retardos) < 120, f"retardo mediano {np.median(retardos)}"

    @pytest.mark.unit
    def test_una_ruptura_al_alza_tambien_avisa(self):
        """Una correlación que se dispara destruye la diversificación igual que
        una que se hunde. El CUSUM es de dos colas por eso."""
        out = sb.correlation_break(*pareja(seed=601, rho=0.20, rho2=0.85, corte=900),
                                   window=30, reference=500, replicates=200, seed=601)
        assert out["broken"] is True
        assert out["direction"] == "arriba"


class TestElPuntoDeCambio:

    @pytest.mark.unit
    def test_llega_tarde_y_no_es_una_cota(self):
        """El estimador es el último reinicio del CUSUM, y se sitúa unas barras
        DESPUÉS de la ruptura, no antes.

        Se fija el signo porque la versión anterior presentaba un número parecido
        como cota inferior del momento del suceso, y no lo era. Quien lea esto
        tiene que ver que el estimador puede quedarse corto.
        """
        v = ruptura_en()
        errores = []
        for s in range(20):
            out = sb.correlation_break(*pareja(seed=700 + s, rho2=0.30, corte=900),
                                       window=30, reference=500, replicates=120,
                                       seed=700 + s)
            if out["broken"]:
                errores.append(out["change_point_index"] - v)
        assert len(errores) >= 18
        # Cerca de la verdad, pero con sesgo positivo: llega tarde.
        assert abs(np.median(errores)) < 40
        assert np.median(errores) > -20

    @pytest.mark.unit
    def test_nunca_va_por_delante_de_su_propia_alarma(self):
        out = sb.correlation_break(*pareja(seed=800, rho2=0.30, corte=900),
                                   window=30, reference=500, replicates=120, seed=800)
        assert out["broken"] is True
        assert out["change_point_index"] <= out["alarm_index"]


# ------------------------------------------------------------------- las piezas


class TestLaHolgura:

    @pytest.mark.unit
    def test_se_deriva_de_la_caida_y_no_es_una_constante(self):
        """El fallo número uno: `k` fijo ignoraba el tamaño real del cambio."""
        sigma = 0.17
        pequena = sb.slack_for_drop(0.80, 0.10, sigma)
        grande = sb.slack_for_drop(0.80, 0.50, sigma)
        assert grande["k"] > pequena["k"]
        assert pequena["derived"] is True

    @pytest.mark.unit
    def test_una_sigma_degenerada_no_revienta(self):
        salida = sb.slack_for_drop(0.80, 0.30, 0.0)
        assert salida["derived"] is False
        assert salida["k"] > 0

    @pytest.mark.unit
    def test_el_mismo_salto_pesa_mas_donde_la_correlacion_es_alta(self):
        """Es la razón de transformar con Fisher: caer de 0.95 a 0.85 es un
        cambio mucho mayor, en unidades de error típico, que de 0.15 a 0.05."""
        alta = sb.slack_for_drop(0.95, 0.10, 0.17)
        baja = sb.slack_for_drop(0.15, 0.10, 0.17)
        assert alta["shift_z"] > baja["shift_z"]


class TestLaCorrelacionMovil:

    @pytest.mark.unit
    def test_recupera_la_correlacion_plantada(self):
        a, b = pareja(n=2000, rho=0.70, seed=11)
        r = sb.rolling_correlation(a, b, 120)
        assert abs(float(np.median(r)) - 0.70) < 0.06

    @pytest.mark.unit
    def test_la_longitud_y_el_alineamiento_son_los_declarados(self):
        a, b = pareja(n=500, seed=12)
        r = sb.rolling_correlation(a, b, 30)
        assert r.size == 500 - 30 + 1
        # El último valor resume las últimas 30 barras y solo esas.
        assert r[-1] == pytest.approx(np.corrcoef(a[-30:], b[-30:])[0, 1], abs=1e-9)

    @pytest.mark.unit
    def test_una_pata_plana_no_correlaciona_con_nada(self):
        a, _ = pareja(n=300, seed=13)
        r = sb.rolling_correlation(a, np.zeros(300), 30)
        assert np.all(r == 0.0)

    @pytest.mark.unit
    def test_la_version_rapida_da_lo_mismo_que_la_lenta(self):
        """La suma acumulada es una optimización; si se desvía de la definición,
        todo lo demás mide otra cosa."""
        a, b = pareja(n=400, seed=14)
        rapida = sb.rolling_correlation(a, b, 40)
        lenta = np.array([np.corrcoef(a[i:i + 40], b[i:i + 40])[0, 1]
                          for i in range(400 - 40 + 1)])
        assert np.allclose(rapida, lenta, atol=1e-8)


class TestLaDesvolatilizacion:

    @pytest.mark.unit
    def test_deja_la_serie_con_varianza_estable(self):
        a, _ = pareja(n=3000, seed=15, garch=True)
        d = sb.devolatilize(a)
        mitad = d.size // 2
        v1 = float(np.var(d[:mitad]))
        v2 = float(np.var(d[mitad:]))
        cruda = a[sb.DEVOL_WARMUP:]
        c1 = float(np.var(cruda[:mitad]))
        c2 = float(np.var(cruda[mitad:]))
        assert max(v1, v2) / min(v1, v2) < max(c1, c2) / min(c1, c2)

    @pytest.mark.unit
    def test_no_mira_el_retorno_del_propio_instante(self):
        """Si la varianza incluyera `x[t]`, una barra enorme se dividiría por su
        propia magnitud y el detector quedaría ciego justo donde importa.

        Se comprueba cambiando UNA barra y viendo que las anteriores no se mueven
        y que la propia barra sí crece.
        """
        a, _ = pareja(n=600, seed=16)
        b = a.copy()
        b[400] *= 25.0
        da = sb.devolatilize(a)
        db = sb.devolatilize(b)
        i = 400 - sb.DEVOL_WARMUP
        assert np.allclose(da[:i], db[:i])
        assert abs(db[i]) > abs(da[i]) * 10

    @pytest.mark.unit
    def test_una_serie_demasiado_corta_devuelve_vacio(self):
        assert sb.devolatilize(np.zeros(50)).size == 0


class TestElCusum:

    @pytest.mark.unit
    def test_sobre_ruido_centrado_se_queda_cerca_de_cero(self):
        x = np.random.default_rng(17).standard_normal(400)
        stat = sb.cusum_path(x, 0.0, 1.0, 0.5)["stat"]
        assert stat.max() < 40

    @pytest.mark.unit
    def test_un_escalon_lo_dispara_y_el_brazo_dice_el_sentido(self):
        x = np.concatenate([np.zeros(200), np.full(200, 2.0)])
        camino = sb.cusum_path(x, 0.0, 1.0, 0.5)
        assert camino["pos"][-1] > 100
        assert camino["neg"][-1] == 0.0

    @pytest.mark.unit
    def test_una_sigma_no_positiva_se_rechaza(self):
        with pytest.raises(ValueError):
            sb.cusum_path([1.0, 2.0], 0.0, 0.0, 0.5)

    @pytest.mark.unit
    def test_la_referencia_se_estima_solo_con_la_referencia(self):
        """Si la sigma saliera de la serie entera, una ruptura grande la inflaría,
        el desplazamiento cabría dentro y el detector se quedaría ciego en el
        único caso que justifica su existencia."""
        x = np.concatenate([np.zeros(300), np.full(300, 8.0)])
        x = x + np.random.default_rng(18).standard_normal(600) * 0.5
        out = sb.scan(x, 300, shift_sigma=1.0)
        assert out["sigma0"] < 1.0          # la de la referencia, no la del todo
        assert out["peak"] > 100


class TestElRemuestreo:

    @pytest.mark.unit
    def test_los_indices_caen_dentro_del_rango(self):
        rng = np.random.default_rng(19)
        idx = sb.stationary_indices(200, 1000, 5.0, rng)
        assert idx.size == 1000
        assert idx.min() >= 0 and idx.max() < 200

    @pytest.mark.unit
    def test_bloques_mas_largos_conservan_mas_continuidad(self):
        """La propiedad que hace del remuestreo un nulo y no ruido: dentro de un
        bloque la serie sigue siendo la real."""
        rng = np.random.default_rng(20)
        def continuidad(bm):
            idx = sb.stationary_indices(500, 4000, bm, rng)
            return float(np.mean(np.diff(idx) == 1))
        assert continuidad(50.0) > continuidad(3.0)

    @pytest.mark.unit
    def test_el_nulo_de_correlacion_constante_la_deja_constante(self):
        """El nulo tiene que imponer lo que dice imponer."""
        a, b = pareja(n=1400, rho=0.80, rho2=0.20, corte=700, seed=21)
        rng = np.random.default_rng(22)
        bn = sb.constant_correlation_null(a, b, 529, rng)
        r = sb.rolling_correlation(a, bn, 120)
        primera = float(np.median(r[:300]))
        ultima = float(np.median(r[-300:]))
        assert abs(primera - ultima) < 0.15   # la ruptura ha desaparecido
        assert primera > 0.55                 # y el nivel es el de la referencia


class TestElUmbral:

    @pytest.mark.unit
    def test_es_el_estadistico_de_orden_y_no_el_cuantil_interpolado(self):
        """Con un número finito de réplicas, el cuantil interpolado se queda por
        debajo del umbral que de verdad controla la tasa, y el error va en la
        dirección mala: umbral bajo, más falsas alarmas de las prometidas. Se usa
        el estadístico de orden ⌈(R+1)(1−α)⌉, que es la misma corrección de
        muestra finita de la predicción conforme.

        Medido: la tasa de falsa alarma sobre series con correlación constante
        bajó del 8,0 % al 6,7 % al aplicarla, contra un 5 % nominal.
        """
        picos = np.arange(1.0, 101.0)
        out = sb.calibrate_threshold(picos, alpha=0.05)
        assert out["order_statistic"] == int(np.ceil(101 * 0.95))
        assert out["threshold"] == pytest.approx(np.sort(picos)[out["order_statistic"] - 1])
        assert out["threshold"] >= np.quantile(picos, 0.95)

    @pytest.mark.unit
    def test_con_pocas_replicas_se_niega_a_dar_umbral(self):
        """Un cuantil sobre diez números es más ruidoso que el estadístico que
        tiene que juzgar; devolver uno sería peor que no devolver nada."""
        out = sb.calibrate_threshold(np.arange(10.0), alpha=0.05)
        assert out["threshold"] is None

    @pytest.mark.unit
    def test_pedir_menos_falsa_alarma_sube_el_umbral(self):
        picos = np.random.default_rng(23).gamma(2.0, 10.0, 500)
        assert (sb.calibrate_threshold(picos, 0.01)["threshold"]
                > sb.calibrate_threshold(picos, 0.10)["threshold"])


class TestLasRamasQueNoSonVeredicto:

    @pytest.mark.unit
    def test_series_de_distinta_longitud_lo_dicen(self):
        out = sb.correlation_break(np.zeros(100), np.zeros(90))
        assert out["verdict"] == "SIN_DATOS"

    @pytest.mark.unit
    def test_historico_corto_no_emite_veredicto(self):
        """«No hay datos para saberlo» no es lo mismo que «no se ha roto»."""
        a, b = pareja(n=300, seed=24)
        out = sb.correlation_break(a, b, window=30)
        assert out["verdict"] == "SIN_DATOS"
        assert out["broken"] is False

    @pytest.mark.unit
    def test_el_minimo_se_cuenta_en_ventanas_independientes(self):
        """El defecto que este test fija: con 300 retornos salían 171
        correlaciones y una referencia de 68, y el módulo emitía veredicto. Esas
        68 correlaciones de ventana 30 son 2,3 ventanas INDEPENDIENTES —el mismo
        dato contado treinta veces— y la sigma de referencia que sale de ahí no
        sostiene ningún umbral."""
        a, b = pareja(n=300, seed=29)
        out = sb.correlation_break(a, b, window=30)
        assert out["verdict"] == "SIN_DATOS"
        assert out["independent_windows"] < sb.MIN_REFERENCE_WINDOWS
        assert out["reference_required"] == sb.MIN_REFERENCE_WINDOWS * 30

    @pytest.mark.unit
    def test_con_referencia_suficiente_si_emite_veredicto(self):
        """La pareja del anterior: el mínimo tiene que dejar pasar lo que basta."""
        a, b = pareja(n=1400, seed=30)
        out = sb.correlation_break(a, b, window=30, reference=500,
                                   replicates=60, seed=30)
        assert out["verdict"] in ("ESTABLE", "ROTO")
        assert out["independent_windows"] >= sb.MIN_REFERENCE_WINDOWS

    @pytest.mark.unit
    def test_dos_series_identicas_no_revientan_en_el_arcotangente(self):
        """arctanh(1) es infinito y una correlación de exactamente 1 aparece en
        cuanto alguien compara un activo consigo mismo."""
        a, _ = pareja(n=1400, seed=25)
        out = sb.correlation_break(a, a.copy(), window=30, reference=500,
                                   replicates=60, seed=25)
        assert out["verdict"] in ("ESTABLE", "ROTO", "SIN_DATOS")
        assert np.isfinite(out.get("mu0_z", 0.0))

    @pytest.mark.unit
    def test_el_informe_trae_lo_necesario_para_volver_a_fechar_los_indices(self):
        """Sin el cebado descartado, los índices no se pueden llevar a velas."""
        a, b = pareja(seed=26)
        out = sb.correlation_break(a, b, window=30, reference=500,
                                   replicates=60, seed=26)
        assert out["warmup_returns_dropped"] == sb.DEVOL_WARMUP
        assert out["window"] == 30
        assert out["reference"] == 500
        assert "protocol" in out

    @pytest.mark.unit
    def test_la_nota_declara_lo_que_el_detector_no_ve(self):
        nota = sb.self_note()
        assert "varianza" in nota.lower()


class TestElDetectorGenerico:

    @pytest.mark.unit
    def test_un_escalon_en_una_serie_cualquiera_se_detecta(self):
        rng = np.random.default_rng(27)
        x = np.concatenate([rng.normal(0, 1, 400), rng.normal(2.5, 1, 400)])
        out = sb.detect_break(x, reference=400, replicates=200, seed=27)
        assert out["verdict"] == "ROTO"

    @pytest.mark.unit
    def test_sin_escalon_casi_nunca_avisa(self):
        """Sobre una sola semilla esto es una moneda cargada al 95 %: una de cada
        veinte series sin ruptura da alarma POR DISEÑO, y fijar el test a una
        semilla concreta lo convertiría en un test que pasa o falla por azar. Se
        mide la tasa, que es lo que el módulo promete."""
        alarmas = sum(
            1 for s in range(24)
            if sb.detect_break(np.random.default_rng(1000 + s).normal(0, 1, 800),
                               reference=400, replicates=150,
                               seed=1000 + s)["broken"]
        )
        assert alarmas <= 5, f"{alarmas}/24 falsas alarmas con un 5 % prometido"

    @pytest.mark.unit
    def test_una_serie_corta_lo_dice(self):
        out = sb.detect_break(np.arange(40.0))
        assert out["verdict"] == "SIN_DATOS"

    @pytest.mark.unit
    def test_una_referencia_constante_no_emite_veredicto(self):
        x = np.concatenate([np.zeros(200), np.ones(200)])
        out = sb.detect_break(x, reference=200, replicates=50)
        assert out["verdict"] == "SIN_DATOS"
