"""Database models for JSR Hydra trading system.

Import all models here so Alembic can detect them during migration generation.
"""

from app.models.account import MasterAccount, FollowerAccount
from app.models.trade import Trade
from app.models.strategy import Strategy
from app.models.regime import RegimeState
from app.models.allocation import CapitalAllocation
from app.models.model_registry import MLModel, ModelVersion
from app.models.system import EventLog, SystemHealth

__all__ = [
    "MasterAccount",
    "FollowerAccount",
    "Trade",
    "Strategy",
    "RegimeState",
    "CapitalAllocation",
    "MLModel",
    "ModelVersion",
    "EventLog",
    "SystemHealth",
]
