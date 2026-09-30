"""
tests/integration/test_seasonality_command.py — La rejilla horaria contra el almacén.

Lo que solo se puede romper con base de datos delante: que el retorno se alinee
con la marca en que se CONOCE, que un activo sin histórico lo diga en vez de
emitir un veredicto, que la rejilla impresa no reviente en ninguna rama, y que el
comando rechace un bloque que comparta divisor con 168 — porque con él el nulo
conserva justo lo que debe destruir y el resultado parecería válido.
"""

from datetime import datetime, timedelta, timezone as _tz
from io import StringIO

import numpy as np
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


H = 3_600_000


def _sembrar(symbol="BTC", semanas=70, interval="1h", seed=1, vol=0.004,
             boost=None):
    """Siembra velas horarias de semanas completas, con boost opcional por casilla.

    `boost` es un par (día, rango de horas, factor): así se puede plantar una
    estructura horaria conocida y comprobar que el comando la encuentra.
    """
    from core.infrastructure.persistence.models import OhlcvCandle
    from core.domain.services import seasonality as sn

    n = 24 * 7 * semanas
    inicio = int((datetime.now(_tz.utc) - timedelta(hours=n + 1)).timestamp() * 1000)
    inicio -= inicio % H
    marcas = np.arange(n, dtype=np.int64) * H + inicio

    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, vol, n)
    if boost:
        dia, (h0, h1), factor = boost
        idx = sn.week_hour_index(marcas)
        sel = (idx // 24 == dia) & ((idx % 24) >= h0) & ((idx % 24) < h1)
        r = np.where(sel, r * factor, r)
    cierres = 30_000.0 * np.exp(np.cumsum(r))

    OhlcvCandle.objects.bulk_create([
        OhlcvCandle(symbol=symbol, interval=interval, open_time=int(marcas[i]),
                    open=cierres[i], high=cierres[i], low=cierres[i],
                    close=cierres[i], volume=1.0, source="test")
        for i in range(n)
    ], batch_size=3000)
    return marcas


class TestElComando:

    @staticmethod
    def _run(*args, **kwargs):
        out = StringIO()
        call_command("seasonality", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    @pytest.mark.integration
    def test_sin_historico_lo_dice_en_vez_de_emitir_veredicto(self, db):
        """«No hay datos para saberlo» no es «no hay estructura horaria»."""
        salida = self._run("BTC")
        assert "SIN_DATOS" in salida

    @pytest.mark.integration
    def test_sobre_ruido_no_encuentra_estructura(self, db):
        _sembrar(semanas=70, seed=3)
        salida = self._run("BTC", "--rotations", "150")
        assert "SIN_ESTRUCTURA" in salida
        assert "CONTRASTE GLOBAL" in salida

    @pytest.mark.integration
    def test_una_estructura_plantada_se_encuentra_y_se_sitúa(self, db):
        """Actividad ×2,5 los viernes de 12 a 16 UTC. Tiene que salir en la rejilla
        y en la lista de casillas, con el día y la hora correctos."""
        _sembrar(semanas=70, seed=4, boost=(4, (12, 16), 2.5))
        salida = self._run("BTC", "--rotations", "300")
        assert "CON_ESTRUCTURA" in salida
        assert "CASILLAS" in salida
        assert "vie 13:00 UTC" in salida or "vie 14:00 UTC" in salida

    @pytest.mark.integration
    def test_la_rejilla_se_imprime_con_los_siete_dias(self, db):
        from core.domain.services import seasonality as sn

        _sembrar(semanas=70, seed=5, boost=(4, (12, 16), 2.5))
        salida = self._run("BTC", "--rotations", "150")
        assert "REJILLA" in salida
        for dia in sn.DAY_NAMES:
            assert dia in salida

    @pytest.mark.integration
    def test_la_multiplicidad_y_la_aproximacion_se_declaran(self, db):
        """Las dos cosas que impiden sobreleer 168 números."""
        _sembrar(semanas=70, seed=6, boost=(4, (12, 16), 2.5))
        salida = self._run("BTC", "--rotations", "300")
        assert "Benjamini-Hochberg" in salida
        assert "aproximación" in salida

    @pytest.mark.integration
    def test_la_nota_avisa_de_la_lectura_equivocada(self, db):
        """Más movimiento se lee como más oportunidad; es lo contrario."""
        _sembrar(semanas=70, seed=7)
        salida = self._run("BTC", "--rotations", "150")
        assert "NO es una oportunidad" in salida

    @pytest.mark.integration
    def test_un_bloque_que_comparte_divisor_con_la_rejilla_se_rechaza(self, db):
        """El error que produciría un resultado con aspecto de válido: con un
        divisor de 168, cada bloque vuelve siempre a la misma hora del día y el
        nulo conserva parte de la estructura que tenía que destruir."""
        for malo in ("24", "12", "168", "56"):
            with pytest.raises(CommandError):
                self._run("BTC", "--block", malo)

    @pytest.mark.integration
    def test_un_bloque_coprimo_se_acepta(self, db):
        _sembrar(semanas=70, seed=8)
        for bueno in ("25", "23", "29"):
            assert "VEREDICTO" in self._run("BTC", "--block", bueno,
                                            "--rotations", "120")

    @pytest.mark.integration
    def test_pocas_replicas_se_rechazan(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "--rotations", "10")

    @pytest.mark.integration
    def test_una_tasa_de_falsos_descubrimientos_imposible_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "--fdr", "0")

    @pytest.mark.integration
    def test_el_json_es_parseable_y_completo(self, db):
        import json

        _sembrar(semanas=70, seed=9)
        datos = json.loads(self._run("BTC", "--json", "--rotations", "150"))
        assert datos[0]["verdict"] in ("SIN_ESTRUCTURA", "CON_ESTRUCTURA",
                                      "ESTRUCTURA_DIFUSA", "SIN_DATOS")
        assert len(datos[0]["mean_abs_return"]) == 168
        assert "protocol" in datos[0]

    @pytest.mark.integration
    def test_dos_activos_se_informan_por_separado(self, db):
        _sembrar("BTC", semanas=70, seed=10)
        _sembrar("ETH", semanas=70, seed=11)
        salida = self._run("BTC", "ETH", "--rotations", "120")
        assert "BTC" in salida and "ETH" in salida

    @pytest.mark.integration
    def test_no_mezcla_marcos_temporales(self, db):
        _sembrar(semanas=70, seed=12, interval="1h")
        assert "SIN_DATOS" in self._run("BTC", "--interval", "4h")
