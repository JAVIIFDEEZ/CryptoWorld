"""
tests/integration/test_option_surface.py — De la cadena de Deribit a la serie.

El dominio ya está verificado aparte: la integral recupera la σ plantada. Lo que
solo se puede romper aquí son las tres cosas que hace el adaptador, y las tres
son silenciosas si fallan:

  · las **conversiones de unidades** — Deribit cotiza primas en unidades del
    subyacente y la IV en porcentaje; equivocarse da una volatilidad 100 veces
    mayor o un precio 100.000 veces menor, y en ninguno de los dos casos salta
    nada;
  · la **lectura del nombre del instrumento** — un strike mal parseado entra en
    la integral y la contamina entera sin error visible;
  · el **archivado**, sin el cual la volatilidad de la volatilidad nunca será
    calculable, porque la superficie de opciones no se reconstruye hacia atrás.

El cliente es de mentira: aquí no se prueba Deribit, se prueba qué hace este
módulo con lo que Deribit devuelva.
"""

import numpy as np
import pytest

from core.application.use_cases.option_surface import (
    IV_30D, RR_25D, OptionSurfaceUseCase, vol_of_vol,
)
from core.infrastructure.external_apis.deribit_client import parse_instrument


def _bs(forward, strike, sigma, T):
    from scipy.stats import norm
    sq = sigma * np.sqrt(T)
    d1 = (np.log(forward / strike) + 0.5 * sq ** 2) / sq
    d2 = d1 - sq
    call = forward * norm.cdf(d1) - strike * norm.cdf(d2)
    put = strike * norm.cdf(-d2) - forward * norm.cdf(-d1)
    return float(call), float(put)


class _DeribitFalso:
    """
    Cadena sintética a volatilidad conocida, en el FORMATO de Deribit: primas en
    unidades del subyacente y volatilidad en porcentaje.
    """

    def __init__(self, sigma=0.60, spot=100_000.0, dias=30, n=61, skew=0.0,
                 vacio=False, falla=False):
        self.sigma, self.spot, self.dias = sigma, spot, dias
        self.n, self.skew = n, skew
        self.vacio, self.falla = vacio, falla

    def option_book_summary(self, currency="BTC"):
        if self.falla:
            raise RuntimeError("Deribit caído")
        if self.vacio:
            return []

        from datetime import datetime, timedelta, timezone as _tz
        venc = datetime.now(_tz.utc) + timedelta(days=self.dias)
        etiqueta = venc.strftime("%d%b%y").upper().lstrip("0")
        T = self.dias / 365.0
        paso = self.spot * self.sigma * np.sqrt(T) * 5.0 / (self.n // 2)
        strikes = self.spot + paso * np.arange(-(self.n // 2), self.n // 2 + 1)

        filas = []
        for k in strikes[strikes > 0]:
            s = max(self.sigma + self.skew * np.log(k / self.spot), 0.05)
            call, put = _bs(self.spot, float(k), s, T)
            for precio, tipo in ((call, "C"), (put, "P")):
                filas.append({
                    "instrument_name": f"{currency}-{etiqueta}-{int(k)}-{tipo}",
                    # Formato Deribit: prima en unidades del subyacente, IV en %.
                    "mark_price": precio / self.spot,
                    "mark_iv": s * 100.0,
                    "underlying_price": self.spot,
                })
        return filas


class TestLaLecturaDelNombreDelInstrumento:
    """
    Un strike mal parseado entra en la integral y la contamina sin que nada
    falle. Por eso `parse_instrument` devuelve None en vez de adivinar.
    """

    @pytest.mark.unit
    def test_lee_las_cuatro_partes(self):
        out = parse_instrument("BTC-27JUN25-100000-C")
        assert out["currency"] == "BTC" and out["strike"] == 100_000.0
        assert out["is_call"] is True

    @pytest.mark.unit
    def test_distingue_call_de_put(self):
        assert parse_instrument("BTC-27JUN25-100000-P")["is_call"] is False

    @pytest.mark.unit
    def test_el_vencimiento_es_a_las_ocho_utc(self):
        """Deribit vence a las 08:00 UTC; suponer medianoche desplazaría el
        horizonte casi un tercio de día en los vencimientos semanales."""
        assert parse_instrument("BTC-27JUN25-100000-C")["expiry"].hour == 8

    @pytest.mark.unit
    @pytest.mark.parametrize("malo", [
        "BTC-27JUN25-100000", "BTC-27JUN25-100000-X", "BTC-NOFECHA-100000-C",
        "BTC-27JUN25-abc-C", "BTC-27JUN25--C", "", "BTC-27JUN25-0-C",
    ])
    def test_un_formato_raro_devuelve_none_en_vez_de_adivinar(self, malo):
        assert parse_instrument(malo) is None


class TestLasConversionesDeUnidades:
    """
    Las dos conversiones que, si se equivocan, no hacen saltar nada: dan una
    volatilidad 100 veces mayor o un precio 100.000 veces menor.
    """

    @pytest.mark.integration
    def test_recupera_la_volatilidad_de_la_cadena_de_deribit(self, db):
        """La comprobación de las dos conversiones a la vez: si la IV se leyera
        como fracción en vez de porcentaje, o la prima como USD en vez de
        unidades del subyacente, este número no saldría."""
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(sigma=0.60))
        assert out["available"] is True
        assert out["variance"]["implied_vol_annual"] == pytest.approx(0.60, rel=0.05)

    @pytest.mark.integration
    def test_y_tambien_con_otra_volatilidad(self, db):
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(sigma=1.10))
        assert out["variance"]["implied_vol_annual"] == pytest.approx(1.10, rel=0.06)

    @pytest.mark.integration
    def test_el_subyacente_llega_en_dolares(self, db):
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(spot=95_000.0))
        assert out["underlying_price"] == pytest.approx(95_000.0)


class TestLaSuperficie:

    @pytest.mark.integration
    def test_elige_el_vencimiento_mas_cercano_a_treinta_dias(self, db):
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(dias=28))
        assert 25 <= out["days_to_expiry"] <= 31

    @pytest.mark.integration
    def test_calcula_las_alas_con_su_asimetria(self, db):
        out = OptionSurfaceUseCase().execute(
            "BTC", client=_DeribitFalso(sigma=0.60, skew=-0.5))
        assert out["wings"]["available"] is True
        assert out["wings"]["risk_reversal_pct"] < 0

    @pytest.mark.integration
    def test_declara_que_el_delta_no_es_libre_de_modelo(self, db):
        """La varianza sí lo es; el delta con el que se localizan las alas de 25
        no: no se observa, se calcula. Es la distinción que convierte una cifra
        auditable en una que parece un dato."""
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso())
        assert out["delta_model"] == "BLACK76"
        assert "LIBRE DE MODELO" in out["note"]

    @pytest.mark.integration
    def test_la_prima_de_varianza_se_calcula_si_se_pasa_la_realizada(self, db):
        out = OptionSurfaceUseCase().execute(
            "BTC", client=_DeribitFalso(sigma=0.60), realized_vol_annual=0.40)
        assert out["vrp"]["expensive"] is True
        assert out["vrp"]["vrp_vol_points"] == pytest.approx(20.0, abs=2.0)

    @pytest.mark.integration
    def test_una_cadena_vacia_lo_dice(self, db):
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(vacio=True))
        assert out["available"] is False and "vacía" in out["note"]

    @pytest.mark.integration
    def test_deribit_caido_no_revienta(self, db):
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(falla=True))
        assert out["available"] is False
        assert "no disponible" in out["note"]

    @pytest.mark.integration
    def test_los_vencimientos_demasiado_cercanos_se_descartan(self, db):
        """Por debajo de cinco días la implícita se vuelve errática —el gamma
        explota— y ensucia la serie más de lo que informa."""
        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(dias=2))
        assert out["available"] is False


class TestElArchivadoQueHaceposibleLaVolDeVol:

    @pytest.mark.integration
    def test_persiste_los_momentos_como_serie(self, db):
        from core.infrastructure.persistence.models import DerivativeMetricPoint

        out = OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(skew=-0.5))
        assert out["stored"] >= 2
        assert DerivativeMetricPoint.objects.filter(
            symbol="BTC", venue="deribit", metric=IV_30D).exists()
        assert DerivativeMetricPoint.objects.filter(metric=RR_25D).exists()

    @pytest.mark.integration
    def test_el_venue_lo_separa_de_las_series_de_binance(self, db):
        """Comparten tabla; mezclarlos haría que la volatilidad implícita de
        Deribit y el interés abierto de Binance vivieran en la misma serie."""
        from core.infrastructure.persistence.models import DerivativeMetricPoint

        OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso())
        assert DerivativeMetricPoint.objects.filter(venue="deribit").exists()
        assert not DerivativeMetricPoint.objects.filter(venue="binance").exists()

    @pytest.mark.integration
    def test_se_puede_pedir_sin_persistir(self, db):
        from core.infrastructure.persistence.models import DerivativeMetricPoint

        OptionSurfaceUseCase().execute("BTC", client=_DeribitFalso(), persist=False)
        assert DerivativeMetricPoint.objects.count() == 0

    @pytest.mark.integration
    def test_sin_serie_la_vol_de_vol_dice_por_que_no_y_no_devuelve_cero(self, db):
        """Cero significaría «la volatilidad implícita es perfectamente estable»,
        que es lo contrario de «todavía no hay datos»."""
        out = vol_of_vol("BTC")
        assert out["available"] is False
        assert "no se puede reconstruir hacia atrás" in out["note"]

    @pytest.mark.integration
    def test_con_serie_suficiente_la_calcula(self, db):
        from datetime import datetime, timezone as _tz

        from core.infrastructure.persistence.models import DerivativeMetricPoint

        ahora = int(datetime.now(_tz.utc).timestamp() * 1000)
        rng = np.random.default_rng(3)
        DerivativeMetricPoint.objects.bulk_create([
            DerivativeMetricPoint(symbol="BTC", venue="deribit", metric=IV_30D,
                                  observed_at=ahora - i * 3_600_000,
                                  value=float(0.60 + rng.normal(0, 0.02)))
            for i in range(40)
        ])
        out = vol_of_vol("BTC")
        assert out["available"] is True and out["points"] == 40
        assert out["vov"] > 0

    @pytest.mark.integration
    def test_la_vol_de_vol_se_mide_sobre_cambios_y_no_sobre_niveles(self, db):
        """La desviación del NIVEL mezcla el régimen de volatilidad con su
        inestabilidad. Una serie con tendencia suave tiene desviación de nivel
        alta y de cambios baja, y lo segundo es lo que se busca."""
        from datetime import datetime, timezone as _tz

        from core.infrastructure.persistence.models import DerivativeMetricPoint

        ahora = int(datetime.now(_tz.utc).timestamp() * 1000)
        # Rampa suave: nivel muy disperso, cambios minúsculos.
        DerivativeMetricPoint.objects.bulk_create([
            DerivativeMetricPoint(symbol="BTC", venue="deribit", metric=IV_30D,
                                  observed_at=ahora - (40 - i) * 3_600_000,
                                  value=0.40 + 0.01 * i)
            for i in range(40)
        ])
        out = vol_of_vol("BTC")
        assert out["vov"] == pytest.approx(0.0, abs=1e-6)
        assert "CAMBIOS" in out["note"]


class TestElComandoYLaTareaProgramada:

    @staticmethod
    def _run(*args, **kwargs):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command("option_surface", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    @pytest.mark.integration
    def test_esta_en_el_planificador(self, db):
        """Sin tarea programada la superficie no se archiva, y no se puede
        reconstruir hacia atrás."""
        from django.conf import settings

        entrada = settings.CELERY_BEAT_SCHEDULE.get("sync-option-surface")
        assert entrada is not None
        assert entrada["task"] == "core.tasks.sync_option_surface"

    @pytest.mark.integration
    def test_la_tarea_recorre_las_dos_monedas_con_opciones(self, db, monkeypatch):
        import core.application.use_cases.option_surface as os_mod
        from core.tasks import sync_option_surface

        monkeypatch.setattr(
            os_mod.OptionSurfaceUseCase, "execute",
            lambda self, currency, **k: {"stored": 3, "currency": currency})
        out = sync_option_surface()
        assert out["stored"] == 6
        assert set(out["by_currency"]) == {"BTC", "ETH"}

    @pytest.mark.integration
    def test_una_moneda_caida_no_frena_la_otra(self, db, monkeypatch):
        import core.application.use_cases.option_surface as os_mod
        from core.tasks import sync_option_surface

        def _falla_btc(self, currency, **k):
            if currency == "BTC":
                raise RuntimeError("cadena caída")
            return {"stored": 2, "currency": currency}

        monkeypatch.setattr(os_mod.OptionSurfaceUseCase, "execute", _falla_btc)
        out = sync_option_surface()
        assert out["stored"] == 2 and "ETH" in out["by_currency"]

    @pytest.mark.integration
    def test_el_comando_imprime_la_cobertura_en_sigmas(self, db, monkeypatch):
        """Es la cifra que permite juzgar el sesgo de truncación; sin ella la
        volatilidad implícita no se puede auditar."""
        import core.application.use_cases.option_surface as os_mod

        # El original se captura ANTES de parchear: llamar al método parcheado
        # desde dentro del parche es recursión infinita.
        original = os_mod.OptionSurfaceUseCase.execute
        monkeypatch.setattr(
            os_mod.OptionSurfaceUseCase, "execute",
            lambda self, currency, **k: original(
                self, currency, client=_DeribitFalso(skew=-0.4), persist=False))
        salida = self._run("BTC", "--no-persist")
        assert "VOLATILIDAD IMPLÍCITA" in salida
        assert "infravalora" in salida
        assert "risk reversal" in salida

    @pytest.mark.integration
    def test_el_comando_informa_cuando_no_hay_serie_para_la_vol_de_vol(self, db):
        salida = self._run("BTC", "--vov")
        assert "no se puede reconstruir hacia atrás" in salida
