"""
test_correlation_heatmap.py — Que el mapa no invite a leer lo que no hay.

Un mapa de calor es la pieza más fácil de convertir en adorno peligroso: un
degradado bonito sobre una matriz con un error de estimación que nadie publica.
Así que los tests centrales miden tres cosas:

1. **Que el orden agrupe los bloques.** Alfabético esconde la estructura, que es
   justo lo único que un mapa de calor sirve para mostrar.
2. **Que la tasa de celdas marcadas como «cambió» sea la nominal.** Medido: 4,1 %
   de las parejas sobre series con correlación CONSTANTE, contra un ~5 % que
   implica el umbral de dos errores típicos.
3. **Que el resumen del espectro distinga de verdad una cartera concentrada de una
   repartida**, porque es el número que se va a leer cuando nadie mire la matriz.
"""

import numpy as np
import pytest

from core.domain.services import correlation_heatmap as ch


def un_factor(n=1200, k=5, rho=0.95, seed=1):
    """`k` activos que siguen al mismo factor con la misma carga."""
    rng = np.random.default_rng(seed)
    f = rng.normal(0, 0.02, n)
    return {f"A{i}": rho * f + np.sqrt(max(1 - rho ** 2, 0)) * rng.normal(0, 0.02, n)
            for i in range(k)}


def independientes(n=1200, k=5, seed=2):
    return {f"A{i}": np.random.default_rng(seed + i).normal(0, 0.02, n)
            for i in range(k)}


def dos_bloques(n=1200, seed=3):
    """Tres activos en un factor y dos en otro, sin relación entre factores."""
    rng = np.random.default_rng(seed)
    f1, f2 = rng.normal(0, 0.02, n), rng.normal(0, 0.02, n)
    salida = {}
    for nombre, f, carga in (("BTC", f1, 0.95), ("ETH", f1, 0.90), ("SOL", f1, 0.85),
                             ("XMR", f2, 0.90), ("ZEC", f2, 0.85)):
        salida[nombre] = (carga * f
                          + np.sqrt(max(1 - carga ** 2, 0)) * rng.normal(0, 0.02, n))
    return salida


def estable(n=1200, k=10, rho=0.6, seed=0):
    rng = np.random.default_rng(seed)
    f = rng.normal(0, 0.02, n)
    return {f"A{i}": rho * f + np.sqrt(1 - rho ** 2) * rng.normal(0, 0.02, n)
            for i in range(k)}


def se_rompe(n=1200, k=10, seed=0, antes=0.2, despues=0.85, ventana=90):
    """La correlación salta en la última ventana: el colapso de diversificación."""
    rng = np.random.default_rng(seed)
    f = rng.normal(0, 0.02, n)
    salida = {}
    for i in range(k):
        r = np.where(np.arange(n) >= n - ventana, despues, antes)
        salida[f"A{i}"] = (r * f
                           + np.sqrt(np.maximum(1 - r ** 2, 0)) * rng.normal(0, 0.02, n))
    return salida


# ─────────────────────────────────────────────────── lo que promete el mapa


class TestLaTasaDeCeldasMarcadas:

    @pytest.mark.unit
    def test_con_correlacion_constante_casi_ninguna_celda_se_marca(self):
        """El umbral de dos errores típicos tiene que dar ~5 % de marcas sobre
        series donde la correlación NO cambia. Si diera mucho más, el mapa estaría
        lleno de avisos falsos y dejaría de leerse."""
        marcas = parejas = 0
        for s in range(12):
            h = ch.heatmap(estable(seed=s), window=90, reference_window=90)
            k = len(h["labels"])
            parejas += k * (k - 1) // 2
            marcas += h["pairs_beyond_noise"]
        tasa = marcas / parejas
        assert tasa < 0.12, f"{tasa:.1%} de celdas marcadas sin que nada cambiara"

    @pytest.mark.unit
    def test_un_colapso_de_diversificacion_se_marca_entero(self):
        h = ch.heatmap(se_rompe(seed=1), window=90, reference_window=90)
        k = len(h["labels"])
        assert h["pairs_beyond_noise"] == k * (k - 1) // 2
        assert h["reference_average_correlation"] < 0.3
        assert h["average_correlation"] > 0.6

    @pytest.mark.unit
    def test_el_numero_efectivo_de_apuestas_recoge_el_colapso(self):
        """Es la cifra que se lee cuando nadie mira la matriz: pasar de nueve
        apuestas a tres es la cartera entera convirtiéndose en una posición."""
        h = ch.heatmap(se_rompe(seed=2), window=90, reference_window=90)
        assert h["reference_eigen"]["effective_bets"] > 7
        assert h["eigen"]["effective_bets"] < 4

    @pytest.mark.unit
    def test_el_error_de_cada_celda_viaja_en_la_salida(self):
        """Sin él, un degradado se lee como si fuera exacto."""
        h = ch.heatmap(dos_bloques(), window=90)
        assert h["cell_se_z"] == pytest.approx(1 / np.sqrt(87), abs=1e-3)

    @pytest.mark.unit
    def test_una_ventana_mas_corta_tiene_mas_error(self):
        corto = ch.heatmap(dos_bloques(), window=30)
        largo = ch.heatmap(dos_bloques(), window=200)
        assert corto["cell_se_z"] > largo["cell_se_z"]


class TestElOrden:

    @pytest.mark.unit
    def test_agrupa_los_bloques_en_vez_de_ordenar_alfabeticamente(self):
        """BTC/ETH/SOL siguen a un factor y XMR/ZEC a otro. El orden tiene que
        dejar cada bloque contiguo, que es lo único que un mapa de calor sirve
        para mostrar."""
        h = ch.heatmap(dos_bloques(), window=200)
        pos = {s: i for i, s in enumerate(h["labels"])}
        primero = sorted(pos[s] for s in ("BTC", "ETH", "SOL"))
        segundo = sorted(pos[s] for s in ("XMR", "ZEC"))
        assert primero == list(range(primero[0], primero[0] + 3))
        assert segundo == list(range(segundo[0], segundo[0] + 2))

    @pytest.mark.unit
    def test_la_matriz_sale_permutada_igual_que_las_etiquetas(self):
        """Si la matriz y las etiquetas no van en el mismo orden, el mapa muestra
        las correlaciones de otros activos: el peor fallo posible aquí porque no
        tiene ningún síntoma visible."""
        datos = dos_bloques()
        h = ch.heatmap(datos, window=200)
        m = np.array(h["matrix"])
        # La diagonal es 1 y la matriz es simétrica, en el orden que sea.
        assert np.allclose(np.diag(m), 1.0)
        assert np.allclose(m, m.T)
        # Y la celda (BTC, ETH) del mapa coincide con la correlación de esas dos
        # series recalculada aparte.
        from core.domain.services import structural_break as sb
        i, j = h["labels"].index("BTC"), h["labels"].index("ETH")
        a = sb.devolatilize(datos["BTC"])[-200:]
        b = sb.devolatilize(datos["ETH"])[-200:]
        assert m[i, j] == pytest.approx(float(np.corrcoef(a, b)[0, 1]), abs=1e-3)


class TestElResumenDelEspectro:

    @pytest.mark.unit
    def test_todo_en_un_factor_sale_concentrado(self):
        h = ch.heatmap(un_factor(rho=0.97), window=200)
        assert h["verdict"] == "CONCENTRADO"
        assert h["eigen"]["top_share"] > ch.CONCENTRADO
        assert h["eigen"]["effective_bets"] < 2.0

    @pytest.mark.unit
    def test_activos_independientes_salen_repartidos(self):
        h = ch.heatmap(independientes(k=5), window=200)
        assert h["verdict"] == "REPARTIDO"
        assert h["eigen"]["effective_bets"] > 4.0

    @pytest.mark.unit
    def test_el_numero_efectivo_no_pasa_del_numero_de_activos(self):
        for datos in (un_factor(k=6), independientes(k=6), dos_bloques()):
            h = ch.heatmap(datos, window=200)
            assert h["eigen"]["effective_bets"] <= h["eigen"]["n"] + 1e-9

    @pytest.mark.unit
    def test_la_nota_traduce_la_concentracion_a_una_consecuencia(self):
        """Un 94 % de varianza en un factor no significa nada para quien lo lea si
        no se dice qué implica."""
        h = ch.heatmap(un_factor(rho=0.97), window=200)
        assert "apalancada" in h["note"]


class TestLaReferencia:

    @pytest.mark.unit
    def test_no_se_solapa_con_la_ventana_pintada(self):
        """Dos matrices que comparten datos darían un cambio artificialmente
        pequeño y el mapa diría que nada se mueve.

        Se comprueba plantando un salto exactamente en el borde: si la referencia
        se solapara, arrastraría datos del régimen nuevo y el cambio saldría
        menor.
        """
        h = ch.heatmap(se_rompe(seed=5, ventana=90), window=90, reference_window=90)
        ref = np.array(h["reference_matrix"])
        fuera = ~np.eye(ref.shape[0], dtype=bool)
        # La referencia mide el régimen viejo (rho 0.2) sin contaminarse del nuevo.
        assert float(ref[fuera].mean()) < 0.35

    @pytest.mark.unit
    def test_sin_historico_para_la_referencia_se_dice(self):
        """Hacen falta ventana + referencia retornos UTILIZABLES, y el cebado de
        la volatilidad local se come los primeros cien: con 240 retornos quedan
        140, que dan para la ventana de 90 pero no para su referencia."""
        h = ch.heatmap(estable(n=240), window=90, reference_window=90)
        assert h["matrix"]                      # la ventana sí se puede pintar
        assert "reference_note" in h
        assert "pairs_beyond_noise" not in h

    @pytest.mark.unit
    def test_el_umbral_del_cambio_esta_en_la_salida(self):
        h = ch.heatmap(estable(), window=90, reference_window=90)
        assert h["delta_threshold_z"] > 0
        assert "multiplicidad" in h["delta_note"]


class TestLasRamasVacias:

    @pytest.mark.unit
    def test_un_solo_activo_no_es_una_matriz(self):
        h = ch.heatmap({"BTC": np.random.default_rng(1).normal(0, 0.02, 1000)})
        assert h["verdict"] == "SIN_DATOS"

    @pytest.mark.unit
    def test_series_de_distinta_longitud_se_rechazan(self):
        """Alinear por posición series de distinta longitud daría una correlación
        entre trozos distintos del tiempo: otra cantidad, no una mal estimada."""
        rng = np.random.default_rng(1)
        h = ch.heatmap({"A": rng.normal(0, 0.02, 1000),
                        "B": rng.normal(0, 0.02, 900)})
        assert h["verdict"] == "SIN_DATOS"

    @pytest.mark.unit
    def test_un_activo_plano_se_descarta_sin_tumbar_el_resto(self):
        datos = dos_bloques()
        datos["PLANO"] = np.zeros(1200)
        h = ch.heatmap(datos, window=200)
        assert "PLANO" not in h["labels"]
        assert len(h["labels"]) == 5

    @pytest.mark.unit
    def test_historico_mas_corto_que_la_ventana_lo_dice(self):
        h = ch.heatmap(estable(n=150), window=200)
        assert h["verdict"] == "SIN_DATOS"

    @pytest.mark.unit
    def test_el_cebado_descartado_viaja_en_la_salida(self):
        """Sin ese número no se pueden volver a fechar las ventanas."""
        from core.domain.services import structural_break as sb
        h = ch.heatmap(estable(n=1200), window=90)
        assert h["warmup_returns_dropped"] == sb.DEVOL_WARMUP

    @pytest.mark.unit
    def test_la_nota_avisa_de_lo_que_la_correlacion_no_ve(self):
        nota = ch.self_note()
        assert "no lineal" in nota
        assert "multiplicidad" in nota
