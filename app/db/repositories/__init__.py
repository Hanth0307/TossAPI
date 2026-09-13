"""Repository API for the Phase 03 Data Platform - what Phase 04's
Scanner (and everything else) reads and writes through.

**The point-in-time rule**: every method that reads historical
observed-event data (market bars, ticks, orderbook snapshots, news,
disclosures, signals, positions, account snapshots) takes a required
`as_of: datetime` parameter and filters `available_at <= as_of`. There
is no "get everything" method for these tables - a caller cannot
accidentally see data that was not yet available at `as_of`, because
the parameter is not optional. See
docs/architecture/0008-data-platform.md.

Import surface for Phase 04:

    from app.db.repositories import (
        InstrumentRepository, MarketBarRepository, TradeTickRepository,
        OrderbookRepository, NewsRepository, DisclosureRepository,
        StrategyRegistryRepository, SignalRepository, ModelRunRepository,
        BacktestRunRepository, PaperOrderRepository, BrokerOrderRepository,
        PositionRepository, AccountSnapshotRepository, SystemEventRepository,
        AIContextRepository,
    )
"""

from app.db.repositories.account import AccountSnapshotRepository
from app.db.repositories.ai_context import AIContextRepository
from app.db.repositories.disclosure import DisclosureRepository
from app.db.repositories.market_data import (
    InstrumentRepository,
    MarketBarRepository,
    OrderbookRepository,
    TradeTickRepository,
)
from app.db.repositories.news import NewsRepository
from app.db.repositories.orders import BrokerOrderRepository, PaperOrderRepository
from app.db.repositories.positions import PositionRepository
from app.db.repositories.runs import BacktestRunRepository, ModelRunRepository
from app.db.repositories.signals import SignalRepository
from app.db.repositories.strategy import StrategyRegistryRepository
from app.db.repositories.system_events import SystemEventRepository

__all__ = [
    "AIContextRepository",
    "AccountSnapshotRepository",
    "BacktestRunRepository",
    "BrokerOrderRepository",
    "DisclosureRepository",
    "InstrumentRepository",
    "MarketBarRepository",
    "ModelRunRepository",
    "NewsRepository",
    "OrderbookRepository",
    "PaperOrderRepository",
    "PositionRepository",
    "SignalRepository",
    "StrategyRegistryRepository",
    "SystemEventRepository",
    "TradeTickRepository",
]
