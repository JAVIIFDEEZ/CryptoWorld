"""
interfaces/api/urls.py — Enrutador de la API REST.

Define las URLs de los endpoints de la aplicación.
Cada URL apunta a un View que delega en un caso de uso.

Convención REST aplicada:
  - Recursos en plural y minúsculas
  - Verbos HTTP para las operaciones (GET, POST, PUT, DELETE)
  - Sin verbos en la URL (/api/auth/login, no /api/login-user)
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core.interfaces.api import views
from core.interfaces.api import admin_views

urlpatterns = [
    # ── Health ─────────────────────────────────────────────────────
    path("health/", views.HealthCheckView.as_view(), name="health-check"),

    # ── Auth — Registro y login ─────────────────────────────────────
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),

    # Renovar access_token usando refresh_token (SimpleJWT built-in)
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # ── Auth — Verificación de email ───────────────────────────────
    path("auth/verify-email/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path(
        "auth/verify-email/resend/",
        views.ResendVerificationEmailView.as_view(),
        name="auth-verify-email-resend",
    ),

    # ── Auth — Recuperación de contraseña ──────────────────────────
    path(
        "auth/password-reset/",
        views.PasswordResetRequestView.as_view(),
        name="auth-password-reset",
    ),
    path(
        "auth/password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),

    # ── Auth — Cambio de contraseña (autenticado) ──────────────────
    path(
        "auth/change-password/",
        views.ChangePasswordView.as_view(),
        name="auth-change-password",
    ),
    # ── Auth — Cambio de email (con verificación al nuevo correo) ──
    path(
        "auth/change-email/",
        views.ChangeEmailRequestView.as_view(),
        name="auth-change-email",
    ),
    path(
        "auth/change-email/confirm/",
        views.ChangeEmailConfirmView.as_view(),
        name="auth-change-email-confirm",
    ),
    path(
        "auth/delete-account/",
        views.DeleteAccountView.as_view(),
        name="auth-delete-account",
    ),
    # ── Auth — 2FA (TOTP / Google Authenticator) ───────────────────
    path("auth/2fa/setup/", views.Setup2FAView.as_view(), name="auth-2fa-setup"),
    path("auth/2fa/enable/", views.Enable2FAView.as_view(), name="auth-2fa-enable"),
    path("auth/2fa/disable/", views.Disable2FAView.as_view(), name="auth-2fa-disable"),
    path("auth/2fa/login/", views.Verify2FALoginView.as_view(), name="auth-2fa-login"),
    path(
        "auth/2fa/recovery-codes/",
        views.Regenerate2FARecoveryCodesView.as_view(),
        name="auth-2fa-recovery-codes",
    ),

    # ── Assets ──────────────────────────────────────────────────────
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path("assets/sparklines/", views.AssetSparklinesView.as_view(), name="asset-sparklines"),
    path("assets/<str:symbol>/info/", views.AssetDetailInfoView.as_view(), name="asset-detail-info"),
    path("assets/<str:symbol>/confluence/", views.ConfluenceCardView.as_view(), name="asset-confluence"),
    path("assets/<str:symbol>/ohlcv/", views.AssetOhlcvView.as_view(), name="asset-ohlcv"),

    # ── Analysis ────────────────────────────────────────────────────
    path("analysis/run/", views.RunAnalysisView.as_view(), name="analysis-run"),
    path("analysis/calculate/", views.CalculateAnalysisView.as_view(), name="analysis-calculate"),
    path("analysis/signals/", views.SignalsDashboardView.as_view(), name="analysis-signals"),
    path("analysis/mtf/", views.MtfConfluenceView.as_view(), name="analysis-mtf"),
    path("analysis/levels/", views.PriceStructureView.as_view(), name="analysis-levels"),
    path("analysis/quant/", views.QuantSnapshotView.as_view(), name="analysis-quant"),
    path("analysis/predict/", views.PredictPriceView.as_view(), name="analysis-predict"),
    path("analysis/predictions/", views.PredictionTrackRecordView.as_view(), name="analysis-predictions"),
    path("analysis/predictions/monitoring/", views.PredictionMonitoringView.as_view(), name="analysis-predictions-monitoring"),
    path("analysis/confluence/", views.ConfluenceView.as_view(), name="analysis-confluence"),
    path("analysis/patterns/", views.DetectPatternsView.as_view(), name="analysis-patterns"),
    path("analysis/backtest/", views.RunBacktestView.as_view(), name="analysis-backtest"),
    path(
        "analysis/backtest/robust/",
        views.RobustBacktestLaunchView.as_view(),
        name="analysis-backtest-robust",
    ),
    path(
        "analysis/backtest/robust/compare/",
        views.RobustBacktestCompareView.as_view(),
        name="analysis-backtest-robust-compare",
    ),
    path(
        "analysis/backtest/robust/<str:job_id>/",
        views.RobustBacktestStatusView.as_view(),
        name="analysis-backtest-robust-status",
    ),
    path("analysis/strategies/", views.AvailableStrategiesView.as_view(), name="analysis-strategies"),

    # ── Generador genético de estrategias (Módulo 2) ────────────────
    path(
        "strategies/generate/",
        views.StrategyGenerateLaunchView.as_view(),
        name="strategies-generate",
    ),
    path(
        "strategies/generate/<str:job_id>/",
        views.StrategyGenerateStatusView.as_view(),
        name="strategies-generate-status",
    ),
    path(
        "strategies/robustness/",
        views.SpecRobustnessLaunchView.as_view(),
        name="strategies-robustness",
    ),
    path(
        "strategies/robustness/<str:job_id>/",
        views.SpecRobustnessStatusView.as_view(),
        name="strategies-robustness-status",
    ),
    path(
        "strategies/",
        views.SavedStrategiesListView.as_view(),
        name="strategies-saved-list",
    ),
    path(
        "strategies/signals/recent/",
        views.RecentSignalEventsView.as_view(),
        name="strategies-signals-recent",
    ),
    path(
        "strategies/compare/",
        views.StrategyCompareView.as_view(),
        name="strategies-compare",
    ),
    path(
        "strategies/<int:strategy_id>/dossier/",
        views.StrategyDossierView.as_view(),
        name="strategies-dossier",
    ),
    path(
        "strategies/<int:strategy_id>/monitor/",
        views.StrategyMonitorView.as_view(),
        name="strategies-monitor",
    ),
    path(
        "strategies/<int:strategy_id>/signal/",
        views.StrategySignalView.as_view(),
        name="strategies-signal",
    ),
    path(
        "strategies/paper/",
        views.PaperTradingView.as_view(),
        name="strategies-paper",
    ),
    path(
        "strategies/paper/<int:account_id>/",
        views.PaperTradingDetailView.as_view(),
        name="strategies-paper-detail",
    ),
    path(
        "strategies/paper/<int:account_id>/live/",
        views.PaperLivePromotionView.as_view(),
        name="strategies-paper-live",
    ),
    path(
        "strategies/paper/<int:account_id>/live/orders/",
        views.PaperLiveOrdersView.as_view(),
        name="strategies-paper-live-orders",
    ),
    path(
        "strategies/best/",
        views.BestStrategiesView.as_view(),
        name="strategies-best",
    ),
    path(
        "strategies/portfolio/",
        views.StrategyPortfolioView.as_view(),
        name="strategies-portfolio",
    ),

    # ── Market Intelligence ─────────────────────────────────────────
    path("market/overview/", views.MarketOverviewView.as_view(), name="market-overview"),
    path("market/fx/", views.FxRatesView.as_view(), name="market-fx"),
    path("blockchain/metrics/", views.BlockchainMetricsView.as_view(), name="blockchain-metrics"),
    path("blockchain/multichain/", views.MultiChainStatsView.as_view(), name="blockchain-multichain"),
    path("blockchain/wallet/", views.WalletOverviewView.as_view(), name="blockchain-wallet"),
    path("blockchain/pulse/", views.OnChainMarketPulseView.as_view(), name="blockchain-pulse"),
    path("blockchain/wallet/dossier/", views.WalletDossierView.as_view(), name="blockchain-wallet-dossier"),
    path("blockchain/wallet/chains/", views.WalletChainsView.as_view(), name="blockchain-wallet-chains"),
    path("blockchain/wallet/history/", views.WalletBalanceHistoryView.as_view(), name="blockchain-wallet-history"),
    path("blockchain/health/", views.ChainHealthView.as_view(), name="blockchain-health"),
    path("blockchain/movements/", views.WhaleMovementsView.as_view(), name="blockchain-movements"),
    path("blockchain/forensics/flow/", views.OnChainFlowTraceView.as_view(), name="blockchain-forensics-flow"),
    path("blockchain/forensics/concentration/", views.OnChainConcentrationView.as_view(), name="blockchain-forensics-concentration"),
    path("blockchain/forensics/fingerprint/", views.OnChainFingerprintView.as_view(), name="blockchain-forensics-fingerprint"),
    path("blockchain/forensics/risk/", views.OnChainRiskScoreView.as_view(), name="blockchain-forensics-risk"),
    path("blockchain/forensics/approvals/", views.OnChainApprovalsView.as_view(), name="blockchain-forensics-approvals"),
    path("blockchain/forensics/entity/", views.OnChainEntityGraphView.as_view(), name="blockchain-forensics-entity"),
    path("blockchain/forensics/token-safety/", views.OnChainTokenSafetyView.as_view(), name="blockchain-forensics-token-safety"),
    path("blockchain/forensics/dossier/", views.OnChainAddressDossierView.as_view(), name="blockchain-forensics-dossier"),
    path("blockchain/forensics/wash-trading/", views.OnChainWashTradingView.as_view(), name="blockchain-forensics-wash-trading"),
    path("blockchain/pressure/", views.OnChainPressureView.as_view(), name="blockchain-pressure"),
    path("blockchain/smartmoney/", views.SmartMoneyView.as_view(), name="blockchain-smartmoney"),
    path("blockchain/watchlist/", views.AddressWatchlistView.as_view(), name="blockchain-watchlist"),
    path("blockchain/watchlist/<int:watch_id>/", views.AddressWatchlistItemView.as_view(), name="blockchain-watchlist-item"),
    # ── Trading real multi-exchange (ccxt, manual, testnet por defecto) ──
    path("trading/risk-policy/", views.LiveRiskPolicyView.as_view(), name="trading-risk-policy"),
    path("trading/connections/", views.TradingConnectionsView.as_view(), name="trading-connections"),
    path("trading/connections/<int:connection_id>/", views.TradingConnectionDetailView.as_view(), name="trading-connection-detail"),
    path("trading/connections/<int:connection_id>/balance/", views.TradingBalanceView.as_view(), name="trading-balance"),
    path("trading/connections/<int:connection_id>/orders/", views.TradingOrdersView.as_view(), name="trading-orders"),
    path("trading/connections/<int:connection_id>/orders/cancel/", views.TradingCancelOrderView.as_view(), name="trading-cancel-order"),

    path("notifications/", views.NotificationsView.as_view(), name="notifications"),
    path("notifications/seen/", views.NotificationsSeenView.as_view(), name="notifications-seen"),
    path("news/", views.NewsFeedView.as_view(), name="news-feed"),
    path("push/public-key/", views.PushPublicKeyView.as_view(), name="push-public-key"),
    path("push/subscribe/", views.PushSubscriptionView.as_view(), name="push-subscribe"),
    path("news/globe/", views.NewsGlobeView.as_view(), name="news-globe"),
    path("market/history/", views.OhlcvCoverageView.as_view(), name="market-history"),
    path("market/history/backfill/", views.OhlcvBackfillView.as_view(), name="market-history-backfill"),

    # ── Admin ───────────────────────────────────────────────────────
    path("admin/users/", admin_views.AdminUserListView.as_view(), name="admin-user-list"),
    path("admin/users/<int:user_id>/", admin_views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path(
        "admin/users/<int:user_id>/resend-verification/",
        admin_views.AdminResendVerificationView.as_view(),
        name="admin-user-resend-verification",
    ),
    path("admin/market/sync/", admin_views.AdminMarketSyncView.as_view(), name="admin-market-sync"),

    # ── Portfolio ────────────────────────────────────────────────────
    path("portfolio/risk/", views.PortfolioRiskView.as_view(), name="portfolio-risk"),
    path("portfolio/", views.PortfolioView.as_view(), name="portfolio-summary"),
    path("portfolio/trades/", views.TradeListView.as_view(), name="portfolio-trades"),
    path("portfolio/trades/<int:trade_id>/", views.TradeDetailView.as_view(), name="portfolio-trade-detail"),

    # ── Portfolio — Posiciones explícitas ────────────────────────────
    path("portfolio/export/", views.PortfolioExportView.as_view(), name="portfolio-export"),
    path("portfolio/positions/", views.PositionListView.as_view(), name="position-list"),
    path("portfolio/positions/<int:position_id>/", views.PositionDetailView.as_view(), name="position-detail"),
    path("portfolio/positions/<int:position_id>/add/", views.PositionAddView.as_view(), name="position-add"),
    path("portfolio/positions/<int:position_id>/close/", views.PositionCloseView.as_view(), name="position-close"),

    # ── Alerts ───────────────────────────────────────────────────────
    path("alerts/", views.AlertListView.as_view(), name="alert-list"),
    path("alerts/<int:alert_id>/", views.AlertDetailView.as_view(), name="alert-detail"),
    path("alerts/<int:alert_id>/toggle/", views.AlertToggleView.as_view(), name="alert-toggle"),

    # ── Watchlist ────────────────────────────────────────────────────
    path("watchlist/", views.WatchlistView.as_view(), name="watchlist-list"),
    path("watchlist/<str:symbol>/", views.WatchlistItemView.as_view(), name="watchlist-detail"),
]
