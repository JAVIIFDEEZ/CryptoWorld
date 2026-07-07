"""
core/tasks.py — Tareas asíncronas Celery para CryptoWorld.

Las tareas se ejecutan en background por el servicio 'celery-worker' de Docker.
El scheduler (celery-beat) las dispara según CELERY_BEAT_SCHEDULE en settings.py.

Tareas:
- check_price_alerts:  Evalúa todas las alertas activas cada 2 min.
- sync_prices_quick:   Actualiza precios vía Binance ticker/24hr cada 60 s.
                       Sin cuota CoinGecko, sin crear MarketDataSnapshot.
- sync_market_prices:  Sync completo vía CoinGecko cada 5 min.
                       Actualiza market_cap, logos y crea MarketDataSnapshot.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def dispatch_task(task, *args, **kwargs):
    """
    Encolar una tarea en Celery con degradación a ejecución síncrona.

    En despliegues sin worker Celery o sin broker Redis accesible
    (p. ej. Railway con solo el servicio web), `.delay()` lanza
    OperationalError y la tarea se perdería — el usuario nunca
    recibiría su email de verificación. Este helper detecta el fallo
    de conexión al broker y ejecuta la tarea en el propio proceso web
    como plan B, de forma que el envío de emails nunca depende de que
    la infraestructura asíncrona esté disponible.
    """
    try:
        return task.delay(*args, **kwargs)
    except Exception as exc:
        logger.warning(
            "Broker Celery no disponible (%s). Ejecutando %s de forma síncrona.",
            exc,
            task.name,
        )
        # .apply() ejecuta en el proceso actual; los errores quedan en el
        # EagerResult (no se propagan) y la propia tarea ya los loguea.
        return task.apply(args=args, kwargs=kwargs)


@shared_task(
    name="core.tasks.check_price_alerts",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def check_price_alerts(self):
    """
    Evalúa todas las alertas de precio activas y no disparadas.
    Marca como triggered las que cumplan la condición (ABOVE/BELOW).
    """
    try:
        from core.application.use_cases.manage_alerts import CheckAlertsUseCase

        triggered = CheckAlertsUseCase().execute()
        logger.info(
            "check_price_alerts: %d alertas disparadas",
            len(triggered),
        )
        return {"triggered": len(triggered)}
    except Exception as exc:
        logger.error("check_price_alerts error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.sync_prices_quick",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def sync_prices_quick(self):
    """
    Actualiza current_price, volume_24h y price_change_24h usando Binance
    ticker/24hr (1 llamada HTTP, weight=40, sin cuota CoinGecko).
    No crea MarketDataSnapshot. Se ejecuta cada 60 s.
    """
    try:
        from core.application.use_cases.sync_prices_quick import SyncPricesQuickUseCase

        result = SyncPricesQuickUseCase().execute()
        logger.info(
            "sync_prices_quick: updated=%d, skipped=%d, errors=%d",
            result.updated,
            result.skipped,
            result.errors,
        )
        return {
            "updated": result.updated,
            "skipped": result.skipped,
            "errors": result.errors,
        }
    except Exception as exc:
        logger.error("sync_prices_quick error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.sync_market_prices",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def sync_market_prices(self):
    """
    Sync completo vía CoinGecko: actualiza market_cap, logos, coingecko_id
    y crea MarketDataSnapshot para sparklines. Se ejecuta cada 5 min.
    """
    try:
        from core.application.use_cases.sync_market_data import SyncMarketDataUseCase

        result = SyncMarketDataUseCase().execute()
        logger.info(
            "sync_market_prices: creados=%d, actualizados=%d, snapshots=%d, errores=%d",
            result.assets_created,
            result.assets_updated,
            result.snapshots_created,
            len(result.errors),
        )
        return {
            "created": result.assets_created,
            "updated": result.assets_updated,
            "snapshots": result.snapshots_created,
            "errors": len(result.errors),
        }
    except Exception as exc:
        logger.error("sync_market_prices error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────
# Email tasks — Envío asíncrono para no bloquear la respuesta HTTP
# ─────────────────────────────────────────────────────────────────

@shared_task(
    name="core.tasks.send_verification_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_verification_email(self, user_id: int) -> dict:
    """
    Envía el email de verificación de cuenta al usuario indicado.

    Se llama desde RegisterView y ResendVerificationEmailView con .delay()
    para no bloquear la respuesta HTTP al usuario.
    Reintenta hasta 3 veces con backoff de 60 s ante fallos de red o SendGrid.
    """
    try:
        from core.application.use_cases.send_verification_email import (
            SendVerificationEmailUseCase,
        )

        SendVerificationEmailUseCase().execute(user_id)
        logger.info("send_verification_email: enviado a user_id=%d", user_id)
        return {"status": "sent", "user_id": user_id}
    except ValueError as exc:
        # Usuario no encontrado u otro error de negocio — no reintentar
        logger.warning("send_verification_email: ValueError user_id=%d — %s", user_id, exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.error("send_verification_email error user_id=%d: %s", user_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.send_market_digest",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def send_market_digest(self) -> dict:
    """
    Envía el resumen semanal del mercado a los usuarios suscritos
    (notify_market_digest=True). Programado por celery beat los lunes.
    """
    try:
        from core.application.use_cases.send_market_digest import (
            SendMarketDigestUseCase,
        )

        sent = SendMarketDigestUseCase().execute()
        logger.info("send_market_digest: %d emails enviados", sent)
        return {"sent": sent}
    except Exception as exc:
        logger.error("send_market_digest error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.send_email_change_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_email_change_email(self, user_id: int) -> dict:
    """
    Envía el enlace de confirmación de cambio de email a la dirección
    pendiente (pending_email) del usuario. Despachado con dispatch_task
    desde ChangeEmailRequestView.
    """
    try:
        from core.application.use_cases.change_email import RequestEmailChangeUseCase

        RequestEmailChangeUseCase.send_confirmation_email(user_id)
        logger.info("send_email_change_email: enviado para user_id=%d", user_id)
        return {"status": "sent", "user_id": user_id}
    except ValueError as exc:
        logger.warning("send_email_change_email: ValueError user_id=%d — %s", user_id, exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.error("send_email_change_email error user_id=%d: %s", user_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.send_password_reset_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_password_reset_email(self, email: str) -> dict:
    """
    Envía el email de recuperación de contraseña a la dirección indicada.

    Se llama desde PasswordResetRequestView con .delay() para no bloquear
    la respuesta HTTP. Si el email no existe en el sistema, la tarea
    termina silenciosamente (sin error) para evitar timing attacks.
    """
    try:
        from core.application.use_cases.request_password_reset import (
            RequestPasswordResetUseCase,
        )
        from core.application.dto.auth_dto import PasswordResetRequestDTO

        RequestPasswordResetUseCase().execute(PasswordResetRequestDTO(email=email))
        logger.info("send_password_reset_email: procesado para email=%s", email)
        return {"status": "processed", "email": email}
    except Exception as exc:
        logger.error("send_password_reset_email error email=%s: %s", email, exc, exc_info=True)
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────
# Suite de robustez de backtest — cientos de backtests, va en background
# ─────────────────────────────────────────────────────────────────

@shared_task(
    name="core.tasks.run_robust_backtest",
    bind=True,
    max_retries=0,
)
def run_robust_backtest(
    self,
    asset_symbol: str,
    strategy: str,
    interval: str = "1d",
    limit: int = 365,
    initial_capital: float = 10000.0,
    objective: str = "sharpe",
    preset: str = "balanced",
) -> dict:
    """
    Ejecuta la suite de robustez completa (walk-forward, Optuna, Monte Carlo,
    DSR, PBO y detectores de sesgo) y devuelve el informe con el veredicto.

    Lanzada con .delay() desde RobustBacktestLaunchView; el cliente consulta
    el resultado con el job_id (AsyncResult). No reintenta: es costosa y un
    fallo de datos ya se devuelve como payload {"error": ...}.
    """
    try:
        from core.application.use_cases.run_robust_backtest import (
            RunRobustBacktestUseCase,
        )

        result = RunRobustBacktestUseCase().execute(
            asset_symbol=asset_symbol,
            strategy=strategy,
            interval=interval,
            limit=limit,
            initial_capital=initial_capital,
            objective=objective,
            preset=preset,
        )
        logger.info(
            "run_robust_backtest: %s/%s → %s",
            asset_symbol, strategy, result.get("verdict", result.get("error")),
        )
        return result
    except Exception as exc:
        logger.error(
            "run_robust_backtest error %s/%s: %s",
            asset_symbol, strategy, exc, exc_info=True,
        )
        raise


@shared_task(
    name="core.tasks.compare_strategies_robustness",
    bind=True,
    max_retries=0,
)
def compare_strategies_robustness(
    self,
    asset_symbol: str,
    interval: str = "1d",
    objective: str = "sharpe",
    preset: str = "fast",
) -> dict:
    """
    Evalúa la robustez de las 5 estrategias y devuelve el ranking por
    Robustness Score. Reutiliza la caché por estrategia.
    """
    try:
        from core.application.use_cases.run_robust_backtest import (
            CompareStrategiesUseCase,
        )

        result = CompareStrategiesUseCase().execute(
            asset_symbol=asset_symbol, interval=interval,
            objective=objective, preset=preset,
        )
        logger.info(
            "compare_strategies_robustness: %s → mejor %s",
            asset_symbol, result.get("best", {}).get("strategy", result.get("error")),
        )
        return result
    except Exception as exc:
        logger.error("compare_strategies_robustness error %s: %s", asset_symbol, exc, exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────
# Generador genético de estrategias — evolución + gating, va en background
# ─────────────────────────────────────────────────────────────────

@shared_task(
    name="core.tasks.generate_strategies",
    bind=True,
    max_retries=0,
)
def generate_strategies(
    self,
    asset_symbol: str,
    interval: str = "1d",
    limit: int = 730,
    initial_capital: float = 10000.0,
    preset: str = "balanced",
    optimizer: str = "single",
) -> dict:
    """
    Genera estrategias por algoritmo genético: evoluciona StrategySpecs con
    fitness robustez-aware (Sharpe OOS walk-forward), pasa los finalistas por el
    gating de robustez (PBO, lookahead, Monte Carlo, eficiencia) y los re-evalúa
    en el tramo de validación final intacto. Persiste el ranking como
    StrategyDefinition.

    Lanzada con .delay() desde StrategyGenerateLaunchView; el cliente consulta el
    resultado con el job_id (AsyncResult). No reintenta: es costosa y un fallo de
    datos ya se devuelve como payload {"error": ...}.
    """
    try:
        from core.application.use_cases.generate_strategies import (
            GenerateStrategiesUseCase,
        )

        result = GenerateStrategiesUseCase().execute(
            asset_symbol=asset_symbol,
            interval=interval,
            limit=limit,
            initial_capital=initial_capital,
            preset=preset,
            optimizer=optimizer,
        )
        logger.info(
            "generate_strategies: %s → %s finalistas robustos",
            asset_symbol, result.get("summary", {}).get("passed_gating", result.get("error")),
        )
        return result
    except Exception as exc:
        logger.error("generate_strategies error %s: %s", asset_symbol, exc, exc_info=True)
        raise


@shared_task(
    name="core.tasks.analyze_spec_robustness",
    bind=True,
    max_retries=0,
)
def analyze_spec_robustness(
    self,
    spec: dict,
    asset_symbol: str,
    interval: str = "1d",
    limit: int = 365,
    preset: str = "balanced",
) -> dict:
    """
    Análisis profundo de robustez de un StrategySpec generado: suite completa
    (PBO, DSR, Monte Carlo, permutación, lookahead) sobre el activo principal +
    validación cruzada en varios activos. Lanzada con .delay() desde
    SpecRobustnessLaunchView; el resultado se consulta con el job_id.
    """
    try:
        from core.application.use_cases.run_spec_robustness import RunSpecRobustnessUseCase

        result = RunSpecRobustnessUseCase().execute(
            spec=spec, asset_symbol=asset_symbol, interval=interval, limit=limit, preset=preset,
        )
        logger.info(
            "analyze_spec_robustness: %s → %s",
            asset_symbol, result.get("verdict", result.get("error")),
        )
        return result
    except Exception as exc:
        logger.error("analyze_spec_robustness error %s: %s", asset_symbol, exc, exc_info=True)
        raise


@shared_task(
    name="core.tasks.resolve_predictions",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def resolve_predictions(self) -> dict:
    """
    Verifica las predicciones cuyo horizonte ya transcurrió: trae el precio real
    de la fecha de resolución y las marca acierto/fallo. Es el bucle de mejora
    continua del modelo ML. Programada por celery beat (cada 30 min).
    """
    try:
        from core.application.use_cases.track_predictions import ResolvePredictionsUseCase

        result = ResolvePredictionsUseCase().execute()
        logger.info("resolve_predictions: %d resueltas, %d aciertos",
                    result["resolved"], result["correct"])
        return result
    except Exception as exc:
        logger.error("resolve_predictions error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.warm_ml_predictions",
    bind=True,
    max_retries=0,
)
def warm_ml_predictions(self) -> dict:
    """
    Precalienta la caché de la predicción ML (1h, horizonte 5 — la combinación
    por defecto de la UI) para los activos de mayor capitalización. El cálculo
    es el mismo que dispararía el usuario; aquí se paga en segundo plano para
    que la pestaña de predicción responda al instante. No registra predicciones
    (log=False): solo las peticiones reales de usuarios alimentan el historial.
    Programada por celery beat (cada 10 min; la caché dura 15).
    """
    from core.application.dto.asset_dto import PredictionRequestDTO
    from core.application.use_cases.predict_price import PredictPriceUseCase
    from core.infrastructure.persistence.models import CryptoAsset

    symbols = list(
        CryptoAsset.objects.exclude(market_cap__isnull=True)
        .order_by("-market_cap")
        .values_list("symbol", flat=True)[:8]
    )
    warmed, failed = 0, 0
    use_case = PredictPriceUseCase()
    for symbol in symbols:
        try:
            out = use_case.execute(
                PredictionRequestDTO(asset_symbol=symbol, interval="1h", horizon=5),
                owner=None, log=False,
            )
            warmed += int("error" not in out)
            failed += int("error" in out)
        except Exception as exc:  # noqa: BLE001 — un activo caído no frena al resto
            failed += 1
            logger.warning("warm_ml_predictions: %s falló: %s", symbol, exc)
    logger.info("warm_ml_predictions: %d precalentadas, %d fallidas", warmed, failed)
    return {"warmed": warmed, "failed": failed, "symbols": symbols}


@shared_task(
    name="core.tasks.evaluate_monitored_strategies",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def evaluate_monitored_strategies(self) -> dict:
    """
    Reevalúa las estrategias generadas activas y notifica los cambios de señal a
    sus dueños. Programada por celery beat (cada 15 min).
    """
    try:
        from core.application.use_cases.monitor_strategies import (
            EvaluateMonitoredStrategiesUseCase,
        )

        result = EvaluateMonitoredStrategiesUseCase().execute()
        logger.info(
            "evaluate_monitored_strategies: %d evaluadas, %d notificadas",
            result["evaluated"], result["notified"],
        )
        return result
    except Exception as exc:
        logger.error("evaluate_monitored_strategies error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.evaluate_paper_trading",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def evaluate_paper_trading(self) -> dict:
    """
    Reevalúa las carteras de paper trading activas y ejecuta sus señales (abrir/
    cerrar posición con costes), registrando el P&L realizado. Verifica hacia
    delante, en vivo y sin riesgo, las estrategias generadas. Programada por
    celery beat (cada 15 min).
    """
    try:
        from core.application.use_cases.paper_trading import EvaluatePaperTradingUseCase

        result = EvaluatePaperTradingUseCase().execute()
        logger.info("evaluate_paper_trading: %d carteras, %d operaciones",
                    result["evaluated"], result["trades"])
        # Decadencia detectada → reoptimizar ese activo ya, sin esperar al ciclo
        # semanal (cierre del bucle drift→reoptimización).
        for symbol, interval in result.get("decayed_pairs", []):
            reoptimize_asset.delay(symbol, interval)
        return result
    except Exception as exc:
        logger.error("evaluate_paper_trading error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.monitor_watched_addresses",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def monitor_watched_addresses(self) -> dict:
    """
    Revisa las direcciones on-chain vigiladas por los usuarios y crea alertas
    cuando su saldo nativo varía por encima del umbral (whale tracking ligero).
    Programada por celery beat (cada 30 min).
    """
    try:
        from core.application.use_cases.watchlist import MonitorWatchedAddressesUseCase

        result = MonitorWatchedAddressesUseCase().execute()
        logger.info("monitor_watched_addresses: %d revisadas, %d alertas",
                    result["checked"], result["alerts"])
        return result
    except Exception as exc:
        logger.error("monitor_watched_addresses error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.scan_whale_movements",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def scan_whale_movements(self) -> dict:
    """
    Escanea los mayores movimientos on-chain recientes y los persiste
    clasificados por dirección respecto a exchanges (depósito/retirada). Nutre
    el histórico del indicador de presión on-chain. Programada por celery beat
    (cada 15 min).
    """
    try:
        from core.application.use_cases.onchain_pressure import (
            DetectPressureSignalUseCase, ScanWhaleMovementsUseCase,
        )

        result = ScanWhaleMovementsUseCase().execute()
        # Tras nutrir el histórico, detectar cambios de régimen (señal global
        # que alimenta el centro de notificaciones).
        signals = DetectPressureSignalUseCase().execute()
        result["signals_created"] = signals["created"]
        logger.info("scan_whale_movements: %d redes, %d nuevos, %d señales",
                    result["chains_scanned"], result["created"], signals["created"])
        return result
    except Exception as exc:
        logger.error("scan_whale_movements error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.reoptimize_asset",
    bind=True,
    max_retries=0,
)
def reoptimize_asset(self, symbol: str, interval: str) -> dict:
    """
    Reoptimiza un único activo (regenera con datos frescos) cuando su estrategia
    se ha degradado en vivo. Se dispara desde el paper trading al detectar
    decadencia, para no esperar al ciclo semanal.
    """
    try:
        from core.application.use_cases.reoptimize_strategies import ReoptimizeStrategiesUseCase

        result = ReoptimizeStrategiesUseCase().execute(pairs=[(symbol.upper(), interval)])
        logger.info("reoptimize_asset %s/%s: %d nuevas", symbol, interval, result["new_strategies"])
        return result
    except Exception as exc:
        logger.error("reoptimize_asset %s/%s error: %s", symbol, interval, exc, exc_info=True)
        return {"error": str(exc)}


@shared_task(
    name="core.tasks.reoptimize_strategies",
    bind=True,
    max_retries=0,
)
def reoptimize_strategies(self) -> dict:
    """
    Reoptimiza (regenera con datos frescos) las estrategias de los activos que el
    usuario sigue —paper trading activo o monitorización— y persiste solo las
    nuevas. Mantiene fresca la "mejor estrategia por activo" frente al drift.
    Programada por celery beat (semanal: lunes 03:00 UTC, fuera de horas punta).
    """
    try:
        from core.application.use_cases.reoptimize_strategies import ReoptimizeStrategiesUseCase

        result = ReoptimizeStrategiesUseCase().execute()
        logger.info("reoptimize_strategies: %d pares, %d nuevas",
                    result["regenerated"], result["new_strategies"])
        return result
    except Exception as exc:
        logger.error("reoptimize_strategies error: %s", exc, exc_info=True)
        return {"error": str(exc)}


@shared_task(
    name="core.tasks.sync_ohlcv_history",
    bind=True,
    max_retries=0,
)
def sync_ohlcv_history(self) -> dict:
    """
    Mantiene al día el almacén histórico OHLCV propio: para los activos
    relevantes (top por capitalización + los que tienen paper trading activo)
    y los marcos de trabajo (1h, 4h, 1d), trae las velas recientes y las
    persiste (solo cerradas; idempotente). Programada por celery beat (30 min).
    """
    from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
    from core.application.use_cases.ohlcv_store import persist_candles
    from core.infrastructure.persistence.models import CryptoAsset, PaperTradingAccount

    top = list(
        CryptoAsset.objects.exclude(market_cap__isnull=True)
        .order_by("-market_cap").values_list("symbol", flat=True)[:8]
    )
    active = list(
        PaperTradingAccount.objects.filter(is_active=True)
        .values_list("asset_symbol", flat=True).distinct()
    )
    symbols = list(dict.fromkeys(top + active))   # únicos, conservando orden
    synced = created = 0
    for symbol in symbols:
        for interval in ("1h", "4h", "1d"):
            try:
                res = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=200)
                if res is None or res.df.empty or res.source == "store":
                    continue   # el fetcher ya persiste lo remoto; store = ya al día
                synced += 1
                created += persist_candles(symbol, interval, res.df, source=res.source)
            except Exception as exc:  # noqa: BLE001 — un símbolo caído no frena el resto
                logger.warning("sync_ohlcv %s %s: %s", symbol, interval, exc)
    logger.info("sync_ohlcv_history: %d combinaciones, %d velas nuevas", synced, created)
    return {"symbols": symbols, "synced": synced, "created": created}


@shared_task(
    name="core.tasks.backfill_ohlcv",
    bind=True,
    max_retries=0,
)
def backfill_ohlcv(self, symbol: str, interval: str = "1d",
                   target_candles: int = 3000) -> dict:
    """
    Retro-carga profunda del histórico de un símbolo+marco (bajo demanda desde
    el endpoint de cobertura). Idempotente y reanudable por tandas.
    """
    from core.application.use_cases.ohlcv_store import BackfillOhlcvUseCase

    result = BackfillOhlcvUseCase().execute(
        symbol=symbol, interval=interval, target_candles=target_candles,
    )
    logger.info("backfill_ohlcv %s %s: %s", symbol, interval, result)
    return result


@shared_task(
    name="core.tasks.resolve_confluence_snapshots",
    bind=True,
    max_retries=0,
)
def resolve_confluence_snapshots(self) -> dict:
    """
    Resuelve las lecturas de confluencia vencidas contra el precio real. Es el
    combustible del aprendizaje de pesos del motor 360°. Beat: cada 30 min.
    """
    from core.application.use_cases.get_confluence import ResolveConfluenceSnapshotsUseCase

    result = ResolveConfluenceSnapshotsUseCase().execute()
    logger.info("resolve_confluence_snapshots: %s", result)
    return result


@shared_task(
    name="core.tasks.evaluate_confluence",
    bind=True,
    max_retries=0,
)
def evaluate_confluence(self) -> dict:
    """
    Evalúa el motor de confluencia 360° para los activos relevantes: alimenta
    el aprendizaje continuo de pesos y registra los cambios de veredicto como
    eventos (centro de notificaciones). Beat: cada 30 min.
    """
    from core.application.use_cases.get_confluence import EvaluateConfluenceUseCase

    result = EvaluateConfluenceUseCase().execute()
    logger.info("evaluate_confluence: %s", result)
    return result


@shared_task(
    name="core.tasks.reconcile_live_positions",
    bind=True,
    max_retries=0,
)
def reconcile_live_positions(self) -> dict:
    """
    OMS: reconcilia la posición esperada de cada promoción activa con el
    balance real del exchange; las discrepancias se registran y notifican.
    Beat: cada hora.
    """
    from core.application.use_cases.paper_trading import ReconcileLivePositionsUseCase

    result = ReconcileLivePositionsUseCase().execute()
    logger.info("reconcile_live_positions: %s", result)
    return result
