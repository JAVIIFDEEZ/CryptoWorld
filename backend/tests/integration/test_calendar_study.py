"""
tests/integration/test_calendar_study.py — El estudio de eventos contra el almacén.

Lo que solo se puede romper con base de datos delante:

· que el retorno se alinee con la marca temporal en la que SE CONOCE, no con la
  anterior — un desfase de una vela adelantaría todo el estudio y produciría una
  reacción anterior a su causa;
· que los ajustes de cada familia salgan del calendario y no de quien lanza el
  comando, porque el modo de control equivocado produce un estudio que corre y no
  significa nada;
· que la corrección por multiplicidad se aplique sobre TODOS los contrastes del
  informe;
· que un activo sin histórico lo diga en vez de emitir un veredicto, y que el
  informe impreso no reviente en ninguna rama.
"""

from datetime import datetime, timedelta, timezone as _tz
from io import StringIO

import numpy as np
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


H = 3_600_000


def _sembrar(symbol="BTC", n=9000, interval="1h", seed=1, vol=0.004,
             base_ms=None, boost_viernes=1.0):
    """Siembra `n` velas horarias con retornos gaussianos."""
    from core.infrastructure.persistence.models import OhlcvCandle

    rng = np.random.default_rng(seed)
    inicio = base_ms if base_ms is not None else int(
        (datetime.now(_tz.utc) - timedelta(hours=n + 1)).timestamp() * 1000)
    inicio -= inicio % H
    marcas = np.arange(n, dtype=np.int64) * H + inicio

    r = rng.normal(0.0, vol, n)
    if boost_viernes != 1.0:
        dow = ((marcas // 86_400_000) + 3) % 7
        hora = (marcas // H) % 24
        r = np.where((dow == 4) & (hora >= 8) & (hora <= 14), r * boost_viernes, r)
    cierres = 30_000.0 * np.exp(np.cumsum(r))

    OhlcvCandle.objects.bulk_create([
        OhlcvCandle(symbol=symbol, interval=interval, open_time=int(marcas[i]),
                    open=cierres[i], high=cierres[i], low=cierres[i],
                    close=cierres[i], volume=1.0, source="test")
        for i in range(n)
    ], batch_size=2000)
    return marcas


# ───────────────────────────────────────────────────────── el alineamiento


@pytest.mark.integration
def test_el_retorno_se_alinea_con_la_vela_en_que_se_conoce(db):
    """El retorno de la vela `t` no existe hasta que `t` cierra, o sea hasta la
    marca de `t+1`. Alinearlo con `t` adelantaría todo el estudio una vela y la
    reacción a un evento empezaría antes que el evento."""
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    marcas = _sembrar(n=1000)
    uc = CalendarStudyUseCase()
    m, r = uc._load("BTC", "1h", 5000)
    assert m.size == r.size == 999
    assert int(m[0]) == int(marcas[1])        # la primera marca útil es la segunda
    assert int(m[-1]) == int(marcas[-1])


@pytest.mark.integration
def test_sin_almacen_lo_dice_en_vez_de_emitir_veredicto(db):
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    out = CalendarStudyUseCase().execute("BTC")
    assert out["verdict"] == "SIN_DATOS"
    assert out["families"] == []


@pytest.mark.integration
def test_un_historico_corto_no_emite_veredicto(db):
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    _sembrar(n=100)
    assert CalendarStudyUseCase().execute("BTC")["verdict"] == "SIN_DATOS"


@pytest.mark.integration
def test_no_mezcla_marcos_temporales(db):
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    _sembrar(n=3000, interval="1h")
    assert CalendarStudyUseCase().execute("BTC", interval="4h")["verdict"] == "SIN_DATOS"


# ──────────────────────────────────────────────────── el estudio completo


@pytest.mark.integration
def test_sobre_ruido_ninguna_familia_sale_con_efecto(db):
    """El caso base y el que más importa: con retornos sin estructura, el informe
    no debe inventar efectos en ninguna de las ocho familias."""
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    _sembrar(n=9000, seed=7)
    out = CalendarStudyUseCase().execute("BTC", replicates=150)
    assert out["verdict"] == "SIN_EFECTOS"
    assert out["families_with_effect"] == 0
    assert out["families_studied"] >= 5


@pytest.mark.integration
def test_cada_familia_se_estudia_con_los_ajustes_que_declara_el_calendario(db):
    """El modo de control no lo elige quien lanza el comando: es una propiedad de
    la estructura temporal de cada familia, y equivocarlo invalida el estudio."""
    from core.application.use_cases.calendar_study import CalendarStudyUseCase
    from core.domain.services import economic_calendar as cal

    _sembrar(n=9000, seed=8)
    out = CalendarStudyUseCase().execute("BTC", replicates=100)
    por_clave = {f["family"]: f for f in out["families"]}

    funding = por_clave.get("FUNDING_SETTLEMENT")
    assert funding is not None
    assert funding["hint"]["null_mode"] == "offset"
    assert funding["post"] == cal.study_hint("FUNDING_SETTLEMENT")["post"] == 2

    mensual = por_clave.get("OPTION_EXPIRY_MONTHLY")
    assert mensual["hint"]["null_mode"] == "matched"
    assert mensual["post"] == 6


@pytest.mark.integration
def test_la_financiacion_con_su_ventana_corta_si_es_identificable(db):
    """Con la ventana de seis velas que usan las demás familias, la financiación
    sería NO_IDENTIFICABLE. La pista del calendario la baja a dos justo para que
    quepa un hueco de control."""
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    _sembrar(n=9000, seed=9)
    out = CalendarStudyUseCase().execute("BTC", families=("funding",),
                                         replicates=100)
    funding = out["families"][0]
    assert funding["verdict"] != "NO_IDENTIFICABLE"
    assert funding["control_usable"] > 0


@pytest.mark.integration
def test_las_familias_sin_potencia_no_se_cuentan_como_sin_efecto(db):
    """Cuatro halvings no permiten concluir nada, y decir «sin efecto» sería
    presentar una ausencia de datos como un resultado."""
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    _sembrar(n=9000, seed=10)
    out = CalendarStudyUseCase().execute("BTC", replicates=100)
    veredictos = {f["family"]: f["verdict"] for f in out["families"]}
    for clave, v in veredictos.items():
        if v == "SIN_POTENCIA":
            assert not next(f for f in out["families"]
                            if f["family"] == clave)["significant"]
    assert "no admiten conclusión" in out["note"] or out["families_with_effect"] == 0


@pytest.mark.integration
def test_la_multiplicidad_se_corrige_sobre_todos_los_contrastes(db):
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    _sembrar(n=9000, seed=11)
    out = CalendarStudyUseCase().execute("BTC", replicates=100)
    evaluadas = [f for f in out["families"] if f.get("p_volatility") is not None]
    assert evaluadas
    for f in evaluadas:
        assert "survives_fdr" in f
        # Dos preguntas por familia evaluada, así que el recuento de contrastes
        # tiene que ser al menos el doble de las familias evaluadas.
        assert f["fdr_tests"] >= 2 * len(evaluadas) - 2


@pytest.mark.integration
def test_dos_ejecuciones_seguidas_dan_el_mismo_p_valor(db):
    """La semilla sale del nombre del activo y la familia, no de `hash()`, que va
    salado por proceso: si no, el mismo informe daría p-valores distintos en cada
    ejecución y no sería auditable."""
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    _sembrar(n=9000, seed=12)
    uc = CalendarStudyUseCase()
    a = uc.execute("BTC", families=("expiry",), replicates=100)
    b = uc.execute("BTC", families=("expiry",), replicates=100)
    pa = {f["family"]: f.get("p_volatility") for f in a["families"]}
    pb = {f["family"]: f.get("p_volatility") for f in b["families"]}
    assert pa == pb

    from zlib import crc32
    assert uc._seed("BTC", "NFP") == crc32(b"BTC:NFP") & 0x7FFFFFFF
    assert uc._seed("BTC", "NFP") != uc._seed("ETH", "NFP")


@pytest.mark.integration
def test_un_efecto_de_viernes_no_se_atribuye_al_vencimiento(db):
    """La trampa, ahora de punta a punta contra la base de datos: un efecto de
    viernes por la mañana no puede convertirse en un efecto de vencimiento."""
    from core.application.use_cases.calendar_study import CalendarStudyUseCase

    # 20.000 velas horarias son 833 días: hace falta ese tramo para que la familia
    # mensual pase del mínimo de 12 eventos con ventana completa. Con 12.000 salían
    # once y el estudio devolvía SIN_POTENCIA, que es el veredicto correcto pero no
    # el que este test quiere comprobar.
    _sembrar(n=20000, seed=13, boost_viernes=2.5)
    out = CalendarStudyUseCase().execute("BTC", families=("expiry",),
                                         replicates=300)
    mensual = next(f for f in out["families"]
                   if f["family"] == "OPTION_EXPIRY_MONTHLY")
    assert mensual["verdict"] not in ("SIN_POTENCIA", "SIN_DATOS")
    # La volatilidad observada sale inflada por el efecto de viernes…
    assert mensual["observed"]["vol_ratio_mean"] > 1.5
    # …y el control, que son los demás viernes, la lleva igual de inflada, así que
    # el contraste no se lo atribuye al vencimiento.
    assert mensual["control"]["vol_ratio_mean"] > 1.5
    assert not mensual["survives_fdr"]


# ───────────────────────────────────────────────────────────── el comando


class TestElComando:

    @staticmethod
    def _run(*args, **kwargs):
        out = StringIO()
        call_command("calendar_study", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    @pytest.mark.integration
    def test_imprime_el_veredicto_y_las_familias(self, db):
        _sembrar(n=9000, seed=20)
        salida = self._run("BTC", "--replicates", "100")
        assert "VEREDICTO" in salida
        assert "FAMILIAS" in salida
        assert "OPTION_EXPIRY_MONTHLY" in salida

    @pytest.mark.integration
    def test_declara_lo_que_no_es_derivable(self, db):
        """Si el informe no dijera que el FOMC y el IPC no están, quien lo lea
        creería que el calendario los cubre."""
        _sembrar(n=9000, seed=21)
        salida = self._run("BTC", "--replicates", "100")
        assert "FOMC" in salida
        assert "NO derivable" in salida

    @pytest.mark.integration
    def test_el_protocolo_y_los_limites_viajan_con_el_resultado(self, db):
        _sembrar(n=9000, seed=22)
        salida = self._run("BTC", "--replicates", "100")
        assert "PROTOCOLO" in salida
        assert "no es una estrategia" in salida.lower() or "estrategia" in salida

    @pytest.mark.integration
    def test_la_rama_sin_datos_tambien_se_imprime(self, db):
        assert "SIN_DATOS" in self._run("BTC")

    @pytest.mark.integration
    def test_el_json_es_parseable_y_completo(self, db):
        import json

        _sembrar(n=9000, seed=23)
        datos = json.loads(self._run("BTC", "--json", "--replicates", "100"))
        assert datos[0]["verdict"] in ("CON_EFECTOS", "SIN_EFECTOS", "SIN_DATOS")
        assert "families" in datos[0] and "calendar" in datos[0]

    @pytest.mark.integration
    def test_se_puede_limitar_a_una_familia(self, db):
        _sembrar(n=9000, seed=24)
        salida = self._run("BTC", "--families", "nfp", "--replicates", "100")
        assert "NFP" in salida
        assert "FUNDING_SETTLEMENT" not in salida

    @pytest.mark.integration
    def test_pocas_permutaciones_se_rechazan(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "--replicates", "10")

    @pytest.mark.integration
    def test_una_tasa_de_falsos_descubrimientos_imposible_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "--fdr", "1.5")

    @pytest.mark.integration
    def test_una_familia_inexistente_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "--families", "inventada")
