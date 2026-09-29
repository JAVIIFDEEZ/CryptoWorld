"""
tests/integration/test_factor_study.py — Los factores sobre el almacén real.

El dominio ya está calibrado aparte. Lo que solo se puede romper con base de
datos delante es la construcción del panel, y ahí está la trampa que importa: las
variables de ordenación tienen que describir la semana ANTERIOR. Si `size` o `mom`
llevaran información de la semana que se está midiendo, los factores saldrían
espectaculares por construcción y el alfa de cualquier estrategia quedaría
enterrado bajo un benchmark falso.

Ese desplazamiento no lo puede comprobar el dominio —ordena con lo que le llega—,
así que se comprueba aquí.
"""

import numpy as np
import pytest


def _sembrar(symbol: str, n_dias=500, seed=1, deriva=0.001, vol=0.03,
             volumen=1_000.0):
    """Siembra velas diarias en el almacén."""
    from core.infrastructure.persistence.models import CryptoAsset, OhlcvCandle

    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(deriva, vol, n_dias)))
    base_ms = 1_600_000_000_000
    OhlcvCandle.objects.bulk_create([
        OhlcvCandle(symbol=symbol, interval="1d", open_time=base_ms + i * 86_400_000,
                    open=float(close[i]), high=float(close[i] * 1.01),
                    low=float(close[i] * 0.99), close=float(close[i]),
                    volume=volumen, source="test")
        for i in range(n_dias)
    ])
    CryptoAsset.objects.update_or_create(
        symbol=symbol, defaults={"name": symbol, "market_cap": volumen * 1e6})


def _universo(n=14, n_dias=500):
    for i in range(n):
        _sembrar(f"C{i}", n_dias=n_dias, seed=i + 1,
                 volumen=float(1_000 * (i + 1)))


@pytest.mark.integration
def test_sin_almacen_lo_dice_en_vez_de_inventar_factores(db):
    from core.application.use_cases.factor_study import FactorStudyUseCase

    out = FactorStudyUseCase().execute()
    assert out["available"] is False
    assert out["coverage"]["available"] is False


@pytest.mark.integration
def test_construye_los_factores_con_universo_suficiente(db):
    from core.application.use_cases.factor_study import FactorStudyUseCase

    _universo(n=14)
    out = FactorStudyUseCase().execute()
    assert out["available"] is True
    assert out["coverage"]["symbols_used"] == 14
    assert set(out["factor_summary"]) == {"CMKT", "CSMB", "CMOM"}


@pytest.mark.integration
def test_un_universo_corto_se_rechaza_con_su_motivo(db):
    """Con menos de dos activos por quintil la cartera larga-corta es una apuesta
    sobre dos monedas, y devolverla como factor sería peor que no devolver nada."""
    from core.application.use_cases.factor_study import FactorStudyUseCase

    _universo(n=6)
    out = FactorStudyUseCase().execute()
    assert out["available"] is False
    assert "Universo insuficiente" in out["note"]


@pytest.mark.integration
def test_las_columnas_de_ordenacion_describen_la_semana_anterior(db):
    """La comprobación antifuga. `size` de una semana tiene que ser el volumen de
    la PREVIA, y `mom` un retorno que termina antes de la semana medida."""
    from core.application.use_cases.factor_study import FactorStudyUseCase

    _sembrar("SOLO", n_dias=400, seed=3)
    panel = FactorStudyUseCase()._build_panel(["SOLO"], 400, 25)[0]
    assert panel is not None and len(panel) > 20

    from core.application.use_cases.ohlcv_store import load_dataframe
    import pandas as pd

    df = load_dataframe("SOLO", "1d", 400)
    df["fecha"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    semanal = (df.set_index("fecha")["volume"] * df.set_index("fecha")["close"]
               ).resample("W").sum()

    # El `size` de la fila k debe coincidir con el volumen semanal de k−1, no de k.
    fila = panel.iloc[5]
    idx = list(semanal.index).index(
        [d for d in semanal.index if d.strftime("%Y-%W") == fila["period"]][0])
    assert fila["size"] == pytest.approx(float(semanal.iloc[idx - 1]), rel=1e-6)
    assert fila["size"] != pytest.approx(float(semanal.iloc[idx]), rel=1e-9)


@pytest.mark.integration
def test_mide_el_alfa_de_una_serie_de_retornos(db):
    from core.application.use_cases.factor_study import FactorStudyUseCase

    _universo(n=14)
    estudio = FactorStudyUseCase()
    factores = estudio.execute()
    n = factores["factors"]["periods"]
    rng = np.random.default_rng(7)
    out = estudio.execute(strategy_returns=rng.normal(0, 0.02, n))
    assert out["alpha"]["available"] is True
    assert out["alpha"]["verdict"] in ("ALFA", "SIN_ALFA")


@pytest.mark.integration
def test_una_estrategia_que_es_el_mercado_no_tiene_alfa(db):
    """El caso que da sentido a todo el módulo: Sharpe respetable, alfa cero."""
    from core.application.use_cases.factor_study import FactorStudyUseCase
    from core.domain.services import crypto_factors as cf

    _universo(n=14)
    panel = FactorStudyUseCase()._build_panel(None, 500, 25)[0]
    factores = cf.build_factors(panel)["factors"]
    out = cf.factor_alpha(1.3 * factores["CMKT"].to_numpy(), factores)
    assert out["verdict"] == "SIN_ALFA"
    assert out["betas"]["CMKT"] == pytest.approx(1.3, abs=0.05)


@pytest.mark.integration
def test_declara_el_sesgo_de_supervivencia(db):
    """El universo se elige con la capitalización de HOY: los que desaparecieron
    no están. No se puede corregir sin histórico de altas y bajas, así que se
    dice."""
    from core.application.use_cases.factor_study import FactorStudyUseCase

    _universo(n=14)
    out = FactorStudyUseCase().execute()
    assert "sesgado al alza" in out["survivorship_warning"]
    assert "supervivientes" in out["survivorship_warning"]


@pytest.mark.integration
def test_los_activos_sin_velas_se_reportan_y_no_frenan_el_panel(db):
    from core.application.use_cases.factor_study import FactorStudyUseCase
    from core.infrastructure.persistence.models import CryptoAsset

    _universo(n=12)
    CryptoAsset.objects.update_or_create(
        symbol="VACIO", defaults={"name": "VACIO", "market_cap": 9e18})
    out = FactorStudyUseCase().execute()
    assert "VACIO" in out["coverage"]["symbols_without_data"]
    assert out["available"] is True


@pytest.mark.integration
def test_el_resumen_anualiza_cada_factor_con_su_t(db):
    """Un factor con media positiva y t de 0,3 no es una prima: es ruido, y hay
    que poder verlo al lado del número."""
    from core.application.use_cases.factor_study import FactorStudyUseCase

    _universo(n=14)
    resumen = FactorStudyUseCase().execute()["factor_summary"]
    for nombre in ("CMKT", "CSMB", "CMOM"):
        assert "annualized_pct" in resumen[nombre]
        assert "t_stat" in resumen[nombre]


class TestElComando:

    @staticmethod
    def _run(*args, **kwargs):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command("factor_study", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    @pytest.mark.integration
    def test_imprime_la_prima_de_cada_factor_con_su_t(self, db):
        """Una media positiva con t de 0,3 no es una prima. Sin la t al lado, las
        dos cosas se leen igual."""
        _universo(n=14)
        salida = self._run()
        assert "PRIMA DE CADA FACTOR" in salida
        for nombre in ("CMKT", "CSMB", "CMOM"):
            assert nombre in salida
        assert "t =" in salida

    @pytest.mark.integration
    def test_un_universo_por_debajo_del_minimo_se_rechaza_antes_de_calcular(self, db):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            self._run("--universe", "5")

    @pytest.mark.integration
    def test_los_sesgos_se_imprimen_siempre(self, db):
        """No son una nota al pie: el universo son supervivientes y el tamaño es
        una aproximación, y las dos cosas inflan los factores."""
        _universo(n=14)
        salida = self._run()
        assert "SESGOS QUE NO SE PUEDEN ELIMINAR" in salida
        assert "supervivientes" in salida

    @pytest.mark.integration
    def test_sin_almacen_lo_dice_sin_reventar(self, db):
        assert "sin" in self._run().lower()

    @pytest.mark.integration
    def test_una_estrategia_sin_serie_guardada_se_rechaza_con_su_motivo(self, db):
        from django.core.management.base import CommandError
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition

        _universo(n=14)
        activo = CryptoAsset.objects.filter(symbol="C0").first()
        definicion = StrategyDefinition.objects.create(
            asset=activo, name="sin-serie", spec={}, spec_hash="h1", interval="1d",
            robustness_metrics={"oos_sharpe": 2.0})
        with pytest.raises(CommandError):
            self._run("--strategy", str(definicion.id))

    @pytest.mark.integration
    def test_el_json_es_parseable(self, db):
        import json

        _universo(n=14)
        datos = json.loads(self._run("--json"))
        assert datos["available"] is True
        assert "factor_summary" in datos
