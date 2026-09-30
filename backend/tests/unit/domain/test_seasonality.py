"""
test_seasonality.py — 168 casillas y la disciplina para no contar cuentos con ellas.

Una rejilla de 7 días × 24 horas es el terreno perfecto para el autoengaño: al 5 %
por casilla, ocho salen significativas sin que haya nada, y con 168 números
delante es psicológicamente imposible no encontrarles una historia. Así que los
tests centrales miden la tasa de falso hallazgo y la potencia por separado.

Tres defectos que estos tests fijan porque la calibración los encontró, y ninguno
se habría visto leyendo el código:

1. **El nulo era una rotación circular**, con el argumento —correcto— de que
   conserva toda la dependencia temporal. Pero la rejilla tiene periodo 168 y un
   histórico de semanas completas tiene longitud múltiplo de 168, así que rotar
   mapea cada casilla entera sobre otra: el conjunto de medias es idéntico y el
   nulo ES la observación. Medido: con la actividad duplicada en cuatro casillas,
   el contraste del máximo daba p=0,57 y no detectaba nada.
2. **El p-valor por casilla se contaba sobre las réplicas.** Un recuento sobre R
   réplicas no baja de 1/(R+1); con 300 réplicas eso es 0,0033 y el umbral de
   Benjamini-Hochberg para la primera de 168 casillas es 0,0006. **Ninguna casilla
   podía pasar nunca**, por grande que fuera el efecto.
3. **Solo había un estadístico global**, la dispersión, que promedia sobre las 168
   casillas y es casi ciega a un efecto concentrado en cuatro. Se añadió el máximo,
   y el nivel se reparte entre los cuatro contrastes que hay de verdad.
"""

import numpy as np
import pytest

from core.domain.services import seasonality as sn


H = 3_600_000
SEMANAS = 80
N = 24 * 7 * SEMANAS
INICIO = 1_600_000_000_000 - (1_600_000_000_000 % H)
MARCAS = np.arange(N, dtype=np.int64) * H + INICIO
IDX = sn.week_hour_index(MARCAS)


def garch(seed: int, n: int = N, vol: float = 0.004) -> np.ndarray:
    """Retornos con agrupamiento de volatilidad y sin ninguna estructura horaria."""
    rng = np.random.default_rng(seed)
    e = rng.standard_normal(n)
    v = np.empty(n)
    h = vol ** 2
    for t in range(n):
        v[t] = np.sqrt(h)
        h = 1e-7 + 0.10 * (v[t] * e[t]) ** 2 + 0.87 * h
    return e * v


VIERNES_TARDE = (IDX // 24 == 4) & ((IDX % 24) >= 12) & ((IDX % 24) < 16)
HORARIO_DIA = ((IDX % 24) >= 8) & ((IDX % 24) < 20)


# ───────────────────────────────────────────── lo que promete el contraste


class TestLaTasaDeFalsoHallazgo:

    @pytest.mark.unit
    def test_sin_estructura_el_global_casi_nunca_se_dispara(self):
        """12 series con agrupamiento de volatilidad y ninguna estructura horaria.
        El nivel está repartido entre los cuatro contrastes globales, así que se
        espera ~0,6 disparos; se admite hasta 3."""
        disparos = sum(
            1 for s in range(12)
            if sn.analyse(MARCAS, garch(400 + s), rotations=200,
                          seed=400 + s)["verdict"] != "SIN_ESTRUCTURA"
        )
        assert disparos <= 3, f"{disparos}/12 con estructura inexistente"

    @pytest.mark.unit
    def test_sin_estructura_apenas_se_marca_ninguna_casilla(self):
        """Lo que de verdad importa: 12 series × 168 casillas son 2.016 casillas, y
        sin la corrección por multiplicidad se esperarían un centenar marcadas."""
        marcadas = sum(
            sn.analyse(MARCAS, garch(500 + s), rotations=200,
                       seed=500 + s).get("cells_significant", 0)
            for s in range(12)
        )
        assert marcadas <= 20, f"{marcadas} casillas marcadas de 2016 sin efecto"

    @pytest.mark.unit
    def test_si_el_global_no_pasa_las_casillas_no_se_miran(self):
        """La disciplina que evita las ocho de siempre: cuando el contraste global
        no detecta nada, no se publica ningún detalle por casilla."""
        salida = sn.analyse(MARCAS, garch(401), rotations=200, seed=401)
        if salida["verdict"] == "SIN_ESTRUCTURA":
            assert "cell_detail" not in salida
            assert salida["cells_significant"] == 0


class TestLoQueSiDetecta:

    @pytest.mark.unit
    def test_un_efecto_concentrado_en_cuatro_casillas_se_detecta_entero(self):
        """El caso que la primera versión no veía. La actividad se duplica en
        viernes 12:00–15:00 UTC y tienen que salir esas cuatro y solo esas."""
        r = garch(7)
        salida = sn.analyse(MARCAS, np.where(VIERNES_TARDE, r * 2.0, r),
                            rotations=300, seed=7)
        assert salida["verdict"] == "CON_ESTRUCTURA"
        detalle = salida["cell_detail"]
        casillas = {(c["day"], c["hour_utc"]) for c in detalle["significant"]}
        esperadas = {("vie", h) for h in (12, 13, 14, 15)}
        assert esperadas <= casillas, f"faltan casillas plantadas: {casillas}"
        # Y ninguna de más: es lo que distingue detectar de marcar todo.
        assert len(casillas - esperadas) <= 1

    @pytest.mark.unit
    def test_el_estadistico_del_maximo_es_el_que_ve_lo_concentrado(self):
        """La dispersión promedia sobre 168 casillas y es casi ciega a un efecto
        en cuatro; el máximo no. Se fija para que nadie retire el segundo."""
        r = garch(7)
        salida = sn.analyse(MARCAS, np.where(VIERNES_TARDE, r * 2.0, r),
                            rotations=300, seed=7)
        assert salida["global"]["p_max_activity"] < salida["global"]["alpha"]

    @pytest.mark.unit
    def test_un_efecto_difuso_tambien_se_detecta(self):
        """El complementario: +25 % en todo el horario diurno, 84 casillas. Aquí la
        dispersión es la que manda."""
        r = garch(7)
        salida = sn.analyse(MARCAS, np.where(HORARIO_DIA, r * 1.25, r),
                            rotations=300, seed=8)
        assert salida["verdict"] in ("CON_ESTRUCTURA", "ESTRUCTURA_DIFUSA")
        assert salida["global"]["p_dispersion_activity"] < salida["global"]["alpha"]

    @pytest.mark.unit
    def test_una_casilla_anormalmente_TRANQUILA_tambien_es_un_hallazgo(self):
        """El contraste es a dos colas: una hora sistemáticamente muerta importa
        tanto como una convulsa, porque es cuando el libro está más fino."""
        r = garch(9)
        salida = sn.analyse(MARCAS, np.where(VIERNES_TARDE, r * 0.3, r),
                            rotations=300, seed=9)
        assert salida["verdict"] == "CON_ESTRUCTURA"
        marcadas = {(c["day"], c["hour_utc"])
                    for c in salida["cell_detail"]["significant"]}
        assert ("vie", 13) in marcadas


class TestElNulo:

    @pytest.mark.unit
    def test_la_rotacion_circular_seria_degenerada(self):
        """El defecto número uno, aislado y demostrado.

        Con una longitud múltiplo de 168 —que es lo que tiene cualquier histórico
        de semanas completas— rotar la serie mapea cada casilla sobre otra casilla
        entera. El multiconjunto de medias por casilla no cambia, así que la
        dispersión del nulo es idéntica a la observada y el contraste no puede
        detectar nada.
        """
        r = garch(11)
        assert N % sn.CASILLAS == 0, "el fixture tiene que tener semanas completas"
        media, n = sn._grid(IDX, np.abs(r))
        disp = sn._dispersion(media, n)
        for k in (1, 5, 97, 1000):
            rotada, nn = sn._grid(IDX, np.abs(np.roll(r, k)))
            assert sn._dispersion(rotada, nn) == pytest.approx(disp, rel=1e-9)

    @pytest.mark.unit
    def test_la_permutacion_por_bloques_si_rompe_la_fase(self):
        """La pareja del anterior: el nulo que sí sirve mueve la dispersión."""
        r = garch(11)
        media, n = sn._grid(IDX, np.abs(r))
        disp = sn._dispersion(media, n)
        rng = np.random.default_rng(3)
        distintas = 0
        for _ in range(10):
            p = sn.block_permutation(r, sn.DEFAULT_BLOCK, rng)
            m, nn = sn._grid(IDX, np.abs(p))
            if abs(sn._dispersion(m, nn) - disp) > disp * 1e-6:
                distintas += 1
        assert distintas == 10

    @pytest.mark.unit
    def test_el_bloque_por_defecto_es_coprimo_con_la_rejilla(self):
        """Con un divisor de 168 cada bloque volvería siempre a la misma hora del
        día y el nulo conservaría parte de lo que debe destruir."""
        from math import gcd
        assert gcd(sn.DEFAULT_BLOCK, sn.CASILLAS) == 1
        assert sn.CASILLAS % sn.DEFAULT_BLOCK != 0

    @pytest.mark.unit
    def test_la_permutacion_conserva_la_serie_entera(self):
        """No es un remuestreo: son los mismos retornos en otro orden, así que la
        distribución marginal es exactamente la misma."""
        r = garch(12)
        p = sn.block_permutation(r, 25, np.random.default_rng(1))
        assert p.size == r.size
        assert np.isclose(np.sort(p).sum(), np.sort(r).sum(), rtol=1e-9)

    @pytest.mark.unit
    def test_una_longitud_no_multiplo_del_bloque_no_pierde_datos(self):
        r = garch(13, n=1001)
        p = sn.block_permutation(r, 25, np.random.default_rng(1))
        assert p.size == 1001


class TestLaResolucionDelPValor:

    @pytest.mark.unit
    def test_el_p_por_casilla_baja_del_umbral_de_benjamini_hochberg(self):
        """El defecto número dos, fijado.

        Con un p-valor contado sobre R réplicas el mínimo posible es 1/(R+1). Con
        300 réplicas son 0,0033, y el umbral de BH para la primera de 168 casillas
        es 0,10/168 = 0,0006: ninguna casilla podría cruzarlo nunca. Los momentos
        del nulo salen de las réplicas y la cola de la normal, y por eso un efecto
        grande alcanza p-valores muy por debajo del mínimo empírico.
        """
        r = garch(7)
        salida = sn.analyse(MARCAS, np.where(VIERNES_TARDE, r * 2.0, r),
                            rotations=300, seed=7)
        minimo_empirico = 1.0 / (salida["rotations"] + 1)
        umbral_bh = sn.DEFAULT_FDR / sn.CASILLAS
        assert umbral_bh < minimo_empirico, "el test no mide lo que cree"
        mejores = [c["p"] for c in salida["cell_detail"]["significant"]]
        assert min(mejores) < umbral_bh

    @pytest.mark.unit
    def test_la_aproximacion_normal_se_declara(self):
        """Usar la cola de la normal es defendible y es una aproximación; esconderlo
        la convertiría en un dato aparente."""
        r = garch(7)
        salida = sn.analyse(MARCAS, np.where(VIERNES_TARDE, r * 2.0, r),
                            rotations=200, seed=7)
        assert "aproximación" in salida["cell_detail"]["tail_note"]


class TestLaRejilla:

    @pytest.mark.unit
    def test_el_indice_de_casilla_es_el_correcto(self):
        # 1970-01-01 fue jueves: en el convenio de Python, el 3.
        assert sn.week_hour_index([0])[0] == 3 * 24
        assert sn.week_hour_index([5 * H])[0] == 3 * 24 + 5
        assert sn.week_hour_index([4 * 86_400_000])[0] == 0    # lunes 00:00

    @pytest.mark.unit
    def test_todas_las_casillas_se_cubren_con_semanas_completas(self):
        salida = sn.analyse(MARCAS, garch(20), rotations=100, seed=20)
        assert salida["cells"] == 168
        assert salida["min_per_cell"] == SEMANAS

    @pytest.mark.unit
    def test_la_dispersion_pondera_por_recuento(self):
        """Sin ponderar, el estadístico lo dominarían las casillas peor estimadas,
        que son justo las que menos informan."""
        media = np.full(sn.CASILLAS, 1.0)
        media[0] = 2.0
        muchos = np.full(sn.CASILLAS, 100.0)
        pocos = muchos.copy()
        pocos[0] = 1.0
        assert sn._dispersion(media, pocos) < sn._dispersion(media, muchos)


class TestLasRamasVacias:

    @pytest.mark.unit
    def test_series_desalineadas_lo_dicen(self):
        salida = sn.analyse(np.arange(10), np.zeros(9))
        assert salida["verdict"] == "SIN_DATOS"

    @pytest.mark.unit
    def test_historico_corto_no_emite_veredicto(self):
        """«No hay datos para saberlo» no es «no hay estructura horaria»."""
        corto = MARCAS[:500]
        salida = sn.analyse(corto, garch(21, n=500))
        assert salida["verdict"] == "SIN_DATOS"
        assert str(sn.CASILLAS * sn.MIN_PER_CELL) in salida["note"]

    @pytest.mark.unit
    def test_una_serie_constante_no_revienta(self):
        salida = sn.analyse(MARCAS, np.zeros(N), rotations=50)
        assert salida["verdict"] in ("SIN_ESTRUCTURA", "SIN_DATOS")

    @pytest.mark.unit
    def test_la_nota_dice_que_una_casilla_activa_no_es_una_oportunidad(self):
        """Es la lectura equivocada más probable: más movimiento se lee como más
        oportunidad, cuando con dirección impredecible es más deslizamiento."""
        nota = sn.self_note()
        assert "no es una oportunidad" in nota.lower()
        assert "UTC" in nota
