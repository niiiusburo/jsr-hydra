"""Initial schema creation for JSR Hydra trading system.

Revision ID: 001
Revises: None
Create Date: 2026-02-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    PURPOSE: Create initial database schema with all tables and indexes.

    Creates tables for:
    - Master and follower accounts
    - Trading data (trades, strategies, allocations)
    - Market regime detection
    - Machine learning models and versions
    - System monitoring (events, health checks)
    """
    # Master Accounts Table
    op.create_table(
        "master_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt5_login", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(length=100), nullable=True),
        sa.Column("balance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("equity", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("peak_equity", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("daily_start_balance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="RUNNING"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mt5_login"),
    )
    op.create_index("ix_master_accounts_mt5_login", "master_accounts", ["mt5_login"], unique=True)

    # Follower Accounts Table
    op.create_table(
        "follower_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mt5_login", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(length=100), nullable=True),
        sa.Column("lot_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["master_id"], ["master_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mt5_login"),
    )
    op.create_index("ix_follower_accounts_master_id", "follower_accounts", ["master_id"])
    op.create_index("ix_follower_accounts_mt5_login", "follower_accounts", ["mt5_login"], unique=True)

    # Strategies Table
    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PAUSED"),
        sa.Column("allocation_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("win_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("profit_factor", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_profit", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("config", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_strategies_code", "strategies", ["code"], unique=True)

    # Regime States Table
    op.create_table(
        "regime_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("regime", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("conviction_score", sa.Integer(), nullable=True),
        sa.Column("hmm_state", sa.Integer(), nullable=True),
        sa.Column("is_drifting", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("layer_scores", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regime_states_detected_at", "regime_states", ["detected_at"])

    # Trades Table
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("mt5_ticket", sa.BigInteger(), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=True),
        sa.Column("lots", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("profit", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("commission", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("swap", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("net_profit", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("regime_at_entry", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["master_id"], ["master_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("mt5_ticket"),
    )
    op.create_index("ix_trades_idempotency_key", "trades", ["idempotency_key"], unique=True)
    op.create_index("ix_trades_master_id", "trades", ["master_id"])
    op.create_index("ix_trades_master_status", "trades", ["master_id", "status"])
    op.create_index("ix_trades_mt5_ticket", "trades", ["mt5_ticket"], unique=True)
    op.create_index("ix_trades_strategy_id", "trades", ["strategy_id"])
    op.create_index("ix_trades_strategy_opened", "trades", ["strategy_id", "opened_at"])

    # Capital Allocations Table
    op.create_table(
        "capital_allocs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("regime_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("allocated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["master_id"], ["master_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["regime_id"], ["regime_states.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_capital_allocs_master_id", "capital_allocs", ["master_id"])
    op.create_index("ix_capital_allocs_strategy_id", "capital_allocs", ["strategy_id"])

    # ML Models Table
    op.create_table(
        "ml_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("model_type", sa.String(length=50), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Model Versions Table
    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("metrics", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("trained_at", sa.DateTime(), nullable=False),
        sa.Column("samples_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["ml_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_versions_model_id", "model_versions", ["model_id"])
    op.create_index("ix_model_versions_model_active", "model_versions", ["model_id", "is_active"])

    # Event Log Table
    op.create_table(
        "event_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="INFO"),
        sa.Column("source_module", sa.String(length=100), nullable=True),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_log_created_at", "event_log", ["created_at"])

    # System Health Table
    op.create_table(
        "system_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(), nullable=True),
        sa.Column("metrics", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("version", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_name"),
    )
    op.create_index("ix_system_health_service_name", "system_health", ["service_name"], unique=True)


def downgrade() -> None:
    """
    PURPOSE: Drop all tables created in upgrade.

    Reverses the initial schema creation by dropping all tables in reverse order.
    """
    op.drop_table("system_health")
    op.drop_table("event_log")
    op.drop_table("model_versions")
    op.drop_table("ml_models")
    op.drop_table("capital_allocs")
    op.drop_table("trades")
    op.drop_table("regime_states")
    op.drop_table("strategies")
    op.drop_table("follower_accounts")
    op.drop_table("master_accounts")
