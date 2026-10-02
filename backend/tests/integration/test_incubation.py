"""
test_incubation.py — Puerta de incubación antes del capital real (G5).

Un backtest, por bien validado que esté, mide el pasado. La única evidencia que
el sobreajuste no puede falsear es la que llega DESPUÉS de fijar la estrategia,
sobre datos que no existían cuando se tomó la decisión.

Estos tests fijan que no se puede poner dinero real detrás de una cartera sin
esa evidencia, y que cortar la exposición nunca se bloquea.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.domain.services import incubation


def _curva_con_ventaja(dias=180, sharpe=4.0, seed=1):
    """Curva diaria con ventaja holgada, para aislar los demás criterios.

    Existe porque la puerta pasó a exigir evidencia estadística: sin una curva
    creíble, TODOS los tests de los otros criterios fallarían por el motivo
    equivocado y dejarían de probar lo que dicen probar. El Sharpe es
    deliberadamente alto —4,0— para que el criterio estadístico no sea el que
    decide en los tests que miran los días, las operaciones o la decadencia.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    vol = 0.60
    return tuple(rng.normal(sharpe * vol / 365.0, vol / (365.0 ** 0.5), dias))


def _facts(days=30.0, trades=10, pnl=100.0, decayed=False, daily=None):
    return incubation.IncubationFacts(
        days_running=days, trades_count=trades, realized_pnl=pnl, decayed=decayed,
        daily_returns=_curva_con_ventaja() if daily is None else daily,
    )


class TestPolicy:

    @pytest.mark.unit
    def test_mature_account_is_incubated(self):
        out = incubation.evaluate(_facts())
        assert out["incubated"] is True
        assert out["missing"] == []
        assert "superada" in out["note"]

    @pytest.mark.unit
    def test_too_recent_is_not_incubated(self):
        out = incubation.evaluate(_facts(days=3.0))
        assert out["incubated"] is False
        assert out["missing"] == ["min_days"]
        assert out["days_remaining"] == pytest.approx(11.0)

    @pytest.mark.unit
    def test_too_few_trades_is_not_incubated(self):
        out = incubation.evaluate(_facts(trades=1))
        assert out["missing"] == ["min_trades"]
        assert out["trades_remaining"] == 4

    @pytest.mark.unit
    def test_a_decayed_strategy_never_reaches_real_money(self):
        """Si se ha degradado en vivo, el tiempo cumplido no la rehabilita."""
        out = incubation.evaluate(_facts(days=200.0, trades=99, decayed=True))
        assert out["incubated"] is False
        assert "not_decayed" in out["missing"]

    @pytest.mark.unit
    def test_the_note_says_exactly_what_is_missing(self):
        """Un «no» sin explicación empuja a buscar cómo saltárselo; un plazo
        concreto lo convierte en espera."""
        out = incubation.evaluate(_facts(days=2.0, trades=1))
        assert "días de simulado" in out["note"]
        assert "operaciones" in out["note"]

    @pytest.mark.unit
    def test_profitability_is_optional_by_default(self):
        """Perder en simulado no impide incubar por defecto: la evidencia que
        se exige es de funcionamiento, no de acierto."""
        assert incubation.evaluate(_facts(pnl=-50.0))["incubated"] is True
        strict = incubation.IncubationPolicy(require_profitable=True)
        assert incubation.evaluate(_facts(pnl=-50.0), strict)["incubated"] is False


@pytest.fixture
def account(db, test_user):
    from core.infrastructure.persistence.models import (
        CryptoAsset, PaperTradingAccount, StrategyDefinition,
    )
    asset = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin", current_price=100)
    strategy = StrategyDefinition.objects.create(
        asset=asset, name="RSI reversal", spec_hash="abc", interval="1d",
        passed_gating=True, status="validated",
        spec={
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "gt", "threshold": 70.0}]},
        },
    )
    return PaperTradingAccount.objects.create(
        strategy=strategy, owner=test_user, asset_symbol="BTC", interval="1d",
        cash=1000.0, initial_capital=1000.0,
    )


@pytest.fixture
def connection(db, test_user):
    from core.infrastructure.security.crypto import encrypt_secret
    from core.infrastructure.persistence.models import ExchangeConnection
    return ExchangeConnection.objects.create(
        owner=test_user, exchange="binance",
        api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
    )


class TestPromotionEndpoint:

    @pytest.mark.integration
    def test_fresh_account_cannot_go_live(self, authenticated_client, account, connection):
        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/",
            {"enable": True, "connection_id": connection.id}, format="json",
        )

        assert resp.status_code == 409
        assert resp.data["blocked_by"] == "incubation"
        assert "min_days" in resp.data["incubation"]["missing"]

        account.refresh_from_db()
        assert account.live_enabled is False        # y no se activó a medias

    @staticmethod
    def _sembrar_curva(account, dias=200, sharpe=4.0, seed=3, por_dia=4):
        """Instantáneas de patrimonio con ventaja real, a varias por día.

        `por_dia=4` reproduce la cadencia nativa —la tarea graba una instantánea
        por evaluación— para que el test recorra de verdad el remuestreo a diario
        y no una serie ya diaria que nunca ocurre en producción.
        """
        import numpy as np

        from core.infrastructure.persistence.models import PaperEquitySnapshot

        rng = np.random.default_rng(seed)
        vol = 0.60
        pasos = dias * por_dia
        r = rng.normal(sharpe * vol / 365.0 / por_dia,
                       vol / (365.0 ** 0.5) / (por_dia ** 0.5), pasos)
        equity = 10_000.0 * np.exp(np.cumsum(r))
        inicio = timezone.now() - timedelta(days=dias)

        filas = [
            PaperEquitySnapshot(
                account=account, equity=round(float(equity[i]), 2),
                price=100.0, in_position=bool(i % 2),
            )
            for i in range(pasos)
        ]
        PaperEquitySnapshot.objects.bulk_create(filas)
        # `created_at` es auto_now_add, así que se reescribe después para repartir
        # las instantáneas en el tiempo: sin esto todas caerían en el mismo día y
        # el remuestreo devolvería una sola observación.
        for i, fila in enumerate(PaperEquitySnapshot.objects
                                 .filter(account=account).order_by("id")):
            PaperEquitySnapshot.objects.filter(id=fila.id).update(
                created_at=inicio + timedelta(hours=24 * i / por_dia))

    @pytest.mark.integration
    def test_incubated_account_can_go_live(self, authenticated_client, account, connection):
        """El camino feliz, que ahora exige además evidencia estadística.

        Antes bastaba con poner 30 días y 12 operaciones en la cartera. Ahora hace
        falta una curva de patrimonio que sostenga la afirmación de ventaja, que es
        el punto de todo el cambio.
        """
        from core.infrastructure.persistence.models import PaperTradingAccount

        PaperTradingAccount.objects.filter(id=account.id).update(
            started_at=timezone.now() - timedelta(days=200), trades_count=12,
        )
        self._sembrar_curva(account)

        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/",
            {"enable": True, "connection_id": connection.id}, format="json",
        )

        assert resp.status_code == 200
        assert resp.data["live_enabled"] is True
        assert resp.data["incubation"]["incubated"] is True
        assert resp.data["incubation"]["statistical"]["psr"] >= 0.95

    @pytest.mark.integration
    def test_sin_curva_de_patrimonio_no_se_abre_la_puerta(
            self, authenticated_client, account, connection):
        """Fallo CERRADO, y es el test más importante del fichero.

        Una cartera con 400 días, 500 operaciones y un P&L enorme pero SIN curva
        archivada no puede pasar: la ausencia de evidencia no es evidencia. Es la
        misma regla que gobierna los controles de riesgo del OMS, donde un control
        que falla abierto es peor que no tenerlo.
        """
        from core.infrastructure.persistence.models import PaperTradingAccount

        PaperTradingAccount.objects.filter(id=account.id).update(
            started_at=timezone.now() - timedelta(days=400), trades_count=500,
            realized_pnl=9999.0,
        )

        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/",
            {"enable": True, "connection_id": connection.id}, format="json",
        )

        assert resp.status_code == 409
        assert "statistical_edge" in resp.data["incubation"]["missing"]
        account.refresh_from_db()
        assert account.live_enabled is False

    @pytest.mark.integration
    def test_una_curva_sin_ventaja_no_abre_la_puerta(
            self, authenticated_client, account, connection):
        """Y el complementario: curva larga, completa y sin ventaja ninguna."""
        from core.infrastructure.persistence.models import PaperTradingAccount

        PaperTradingAccount.objects.filter(id=account.id).update(
            started_at=timezone.now() - timedelta(days=200), trades_count=50,
        )
        self._sembrar_curva(account, sharpe=0.0, seed=11)

        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/",
            {"enable": True, "connection_id": connection.id}, format="json",
        )

        assert resp.status_code == 409
        assert "statistical_edge" in resp.data["incubation"]["missing"]
        # Y el 409 trae el plazo o la explicación de por qué no hay plazo.
        est = resp.data["incubation"]["statistical"]
        assert est["psr"] is not None and est["psr"] < 0.95
        assert est["note"]

    @pytest.mark.integration
    def test_disabling_is_never_blocked(self, authenticated_client, account):
        """Cortar la exposición siempre está permitido, incubada o no."""
        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/", {"enable": False}, format="json",
        )
        assert resp.status_code == 200
        assert resp.data["live_enabled"] is False
