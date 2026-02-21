"""
PURPOSE: Hierarchical LLM Memory System for JSR Hydra Brain.

Implements a three-tier memory architecture inspired by FinMem (arXiv:2311.13743):

  SHORT-TERM  -- Current session insights, last ~2 hours, max 20 entries.
                 Raw LLM outputs, market snapshots, recent trade reviews.
                 Decays quickly; promoted to medium-term if importance > threshold.

  MEDIUM-TERM -- Today's consolidated patterns, max 50 entries.
                 Trade outcome summaries, regime-level learnings, recurring signals.
                 Persists for the trading day; promoted to long-term on day rollover.

  LONG-TERM   -- Historical patterns that repeat across days/weeks, max 200 entries.
                 Strategy effectiveness by regime, recurring failure modes,
                 validated edge patterns.  Persists across restarts via JSON file.

Each memory entry carries:
  - text: the insight content
  - importance: float 0-1 (how useful this was -- updated by feedback)
  - recency: float 0-1 (decays over time)
  - access_count: how many times retrieved for context
  - tags: list of classification tags (regime, strategy, symbol, etc.)
  - created_at / updated_at: ISO timestamps

Memory is persisted to a JSON file under the brain data directory.
No external dependencies beyond the standard library and existing brain paths.

CALLED BY: brain/llm_brain.py -- for context injection and insight storage
"""

import json
import os
import time
from datetime import datetime, timezone, date
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field, asdict

from app.brain.paths import resolve_brain_state_path
from app.utils.logger import get_logger

logger = get_logger("brain.llm_memory")

# --- Configuration ---
SHORT_TERM_MAX = 20
MEDIUM_TERM_MAX = 50
LONG_TERM_MAX = 200
SHORT_TERM_TTL_SECONDS = 7200          # 2 hours
MEDIUM_TERM_TTL_SECONDS = 86400        # 24 hours (1 trading day)
PROMOTION_IMPORTANCE_THRESHOLD = 0.6   # Promote if importance exceeds this
DECAY_RATE_SHORT = 0.05                # Per-step decay for short-term recency
DECAY_RATE_MEDIUM = 0.01               # Per-step decay for medium-term recency
DECAY_RATE_LONG = 0.002                # Per-step decay for long-term recency
PERSIST_FILE = "llm_memory.json"


@dataclass
class MemoryEntry:
    """A single memory entry in the hierarchical system."""
    text: str
    importance: float = 0.5
    recency: float = 1.0
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    source_type: str = ""              # market_analysis, trade_review, etc.
    created_at: str = ""
    updated_at: str = ""
    symbol: str = ""
    regime: str = ""
    strategy: str = ""
    pnl: Optional[float] = None

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @property
    def compound_score(self) -> float:
        """Compound relevance score: importance * recency, boosted by access."""
        access_boost = min(self.access_count * 0.05, 0.3)
        return self.importance * self.recency + access_boost

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "MemoryEntry":
        # Filter to known fields only
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


class LLMMemory:
    """
    PURPOSE: Three-tier hierarchical memory for LLM trading insights.

    Stores, retrieves, decays, and promotes memory entries across
    short-term, medium-term, and long-term layers. Provides formatted
    context strings for LLM prompt injection.

    CALLED BY: LLMBrain methods (analyze_market, review_trade, etc.)
    """

    def __init__(self):
        self._short_term: List[MemoryEntry] = []
        self._medium_term: List[MemoryEntry] = []
        self._long_term: List[MemoryEntry] = []
        self._persist_path = resolve_brain_state_path(PERSIST_FILE)
        self._current_date: Optional[str] = None
        self._last_decay_time = time.time()
        self._decay_interval = 300  # Decay every 5 minutes
        self._load()

        logger.info(
            "llm_memory_initialized",
            short=len(self._short_term),
            medium=len(self._medium_term),
            long=len(self._long_term),
            path=self._persist_path,
        )

    # --- Public API ---

    def add(
        self,
        text: str,
        source_type: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        symbol: str = "",
        regime: str = "",
        strategy: str = "",
        pnl: Optional[float] = None,
    ) -> MemoryEntry:
        """
        PURPOSE: Add a new insight to short-term memory.

        The entry starts in short-term and may be promoted to medium-term
        during the next decay/promote cycle if its importance is high enough.

        Args:
            text: The insight text content.
            source_type: One of market_analysis, trade_review, strategy_review,
                        regime_analysis, loss_diagnosis.
            importance: Initial importance score (0-1).
            tags: Classification tags for retrieval filtering.
            symbol: Trading symbol if applicable.
            regime: Market regime at time of insight.
            strategy: Strategy code if applicable.
            pnl: Trade P&L if this is a trade review.

        Returns:
            The created MemoryEntry.
        """
        entry = MemoryEntry(
            text=text,
            importance=importance,
            source_type=source_type,
            tags=tags or [],
            symbol=symbol,
            regime=regime,
            strategy=strategy,
            pnl=pnl,
        )
        self._short_term.append(entry)
        self._trim(self._short_term, SHORT_TERM_MAX)
        logger.debug(
            "llm_memory_added",
            layer="short",
            source_type=source_type,
            importance=importance,
        )
        return entry

    def query(
        self,
        source_type: Optional[str] = None,
        symbol: Optional[str] = None,
        regime: Optional[str] = None,
        strategy: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 5,
        layers: Optional[List[str]] = None,
    ) -> List[MemoryEntry]:
        """
        PURPOSE: Retrieve the most relevant memories across all layers.

        Filters by optional criteria, then ranks by compound_score.
        Each retrieved memory gets its access_count incremented.

        Args:
            source_type: Filter by insight source type.
            symbol: Filter by trading symbol.
            regime: Filter by market regime.
            strategy: Filter by strategy code.
            tags: Filter by any matching tag.
            limit: Maximum entries to return.
            layers: Which layers to search ("short", "medium", "long").

        Returns:
            List of MemoryEntry, highest compound_score first.
        """
        if layers is None:
            layers = ["short", "medium", "long"]

        candidates: List[MemoryEntry] = []
        layer_map = {
            "short": self._short_term,
            "medium": self._medium_term,
            "long": self._long_term,
        }
        for layer_name in layers:
            candidates.extend(layer_map.get(layer_name, []))

        # Apply filters
        if source_type:
            candidates = [m for m in candidates if m.source_type == source_type]
        if symbol:
            candidates = [m for m in candidates if m.symbol == symbol]
        if regime:
            candidates = [m for m in candidates if m.regime == regime]
        if strategy:
            candidates = [m for m in candidates if m.strategy == strategy]
        if tags:
            tag_set = set(tags)
            candidates = [m for m in candidates if tag_set.intersection(m.tags)]

        # Sort by compound score descending
        candidates.sort(key=lambda m: m.compound_score, reverse=True)
        results = candidates[:limit]

        # Increment access count for retrieved memories
        for entry in results:
            entry.access_count += 1
            entry.updated_at = datetime.now(timezone.utc).isoformat()

        return results

    def get_context_for_prompt(
        self,
        source_type: Optional[str] = None,
        symbol: Optional[str] = None,
        regime: Optional[str] = None,
        max_short: int = 3,
        max_medium: int = 3,
        max_long: int = 2,
    ) -> str:
        """
        PURPOSE: Build a formatted memory context string for LLM prompt injection.

        Retrieves top memories from each layer separately and formats them
        into a structured context block. This is the primary interface used
        by LLMBrain methods to inject memory into system/user prompts.

        Returns:
            Formatted string with labeled memory sections, or empty string
            if no relevant memories exist.
        """
        sections = []

        short = self.query(
            source_type=source_type, symbol=symbol, regime=regime,
            limit=max_short, layers=["short"],
        )
        medium = self.query(
            source_type=source_type, symbol=symbol, regime=regime,
            limit=max_medium, layers=["medium"],
        )
        long_term = self.query(
            symbol=symbol, regime=regime,
            limit=max_long, layers=["long"],
        )

        if short:
            items = "\n".join(
                f"  - [{m.source_type}] {m.text[:200]}" for m in short
            )
            sections.append(f"[Recent Session Context]\n{items}")

        if medium:
            items = "\n".join(
                f"  - [{m.source_type}] {m.text[:200]}" for m in medium
            )
            sections.append(f"[Today's Patterns]\n{items}")

        if long_term:
            items = "\n".join(
                f"  - [{m.source_type}] {m.text[:200]}" for m in long_term
            )
            sections.append(f"[Historical Patterns]\n{items}")

        if not sections:
            return ""

        return (
            "=== MEMORY CONTEXT (your prior observations) ===\n"
            + "\n\n".join(sections)
            + "\n=== END MEMORY CONTEXT ===\n"
        )

    def feedback(self, entry: MemoryEntry, delta: float) -> None:
        """
        PURPOSE: Adjust importance of a memory based on outcome feedback.

        Called when we know whether the insight was useful (e.g., a trade
        reviewed by the LLM was later confirmed as a good/bad pattern).

        Args:
            entry: The memory entry to adjust.
            delta: Importance adjustment (-1.0 to 1.0).
        """
        entry.importance = max(0.0, min(1.0, entry.importance + delta))
        entry.updated_at = datetime.now(timezone.utc).isoformat()

    def step(self) -> Dict:
        """
        PURPOSE: Run one maintenance cycle: decay, promote, demote, persist.

        Should be called periodically (e.g., every 5 minutes).
        Handles:
          1. Day rollover: flush medium-term, promote best to long-term.
          2. Recency decay across all layers.
          3. Promotion: short->medium if importance > threshold.
          4. Cleanup: remove entries with near-zero compound scores.
          5. Persist to disk.

        Returns:
            Dict with counts of promotions, demotions, cleanups.
        """
        now = time.time()
        if now - self._last_decay_time < self._decay_interval:
            return {"skipped": True}
        self._last_decay_time = now

        stats = {"promoted_s2m": 0, "promoted_m2l": 0, "cleaned": 0}
        today = date.today().isoformat()

        # Day rollover: promote best medium-term to long-term
        if self._current_date and self._current_date != today:
            best_medium = sorted(
                self._medium_term,
                key=lambda m: m.importance,
                reverse=True,
            )[:10]
            for entry in best_medium:
                if entry.importance >= PROMOTION_IMPORTANCE_THRESHOLD:
                    entry.tags.append("day_promoted")
                    self._long_term.append(entry)
                    stats["promoted_m2l"] += 1
            self._medium_term.clear()
            logger.info(
                "llm_memory_day_rollover",
                old_date=self._current_date,
                new_date=today,
                promoted=stats["promoted_m2l"],
            )
        self._current_date = today

        # Decay recency
        self._decay_layer(self._short_term, DECAY_RATE_SHORT)
        self._decay_layer(self._medium_term, DECAY_RATE_MEDIUM)
        self._decay_layer(self._long_term, DECAY_RATE_LONG)

        # Promote short -> medium
        promoted = []
        remaining = []
        for entry in self._short_term:
            if entry.importance >= PROMOTION_IMPORTANCE_THRESHOLD:
                entry.recency = 1.0  # Reset recency on promotion
                entry.tags.append("promoted")
                self._medium_term.append(entry)
                promoted.append(entry)
                stats["promoted_s2m"] += 1
            else:
                remaining.append(entry)
        self._short_term = remaining

        # Cleanup: remove near-zero compound score entries
        for layer_name, layer, min_score in [
            ("short", self._short_term, 0.05),
            ("medium", self._medium_term, 0.03),
            ("long", self._long_term, 0.01),
        ]:
            before = len(layer)
            layer[:] = [m for m in layer if m.compound_score >= min_score]
            removed = before - len(layer)
            stats["cleaned"] += removed

        # Trim to max sizes
        self._trim(self._short_term, SHORT_TERM_MAX)
        self._trim(self._medium_term, MEDIUM_TERM_MAX)
        self._trim(self._long_term, LONG_TERM_MAX)

        # Persist
        self._save()

        if stats["promoted_s2m"] or stats["promoted_m2l"] or stats["cleaned"]:
            logger.info(
                "llm_memory_step",
                short=len(self._short_term),
                medium=len(self._medium_term),
                long=len(self._long_term),
                **stats,
            )

        return stats

    def get_stats(self) -> Dict:
        """Return memory layer sizes and configuration for API endpoints."""
        return {
            "short_term_count": len(self._short_term),
            "medium_term_count": len(self._medium_term),
            "long_term_count": len(self._long_term),
            "total_memories": (
                len(self._short_term)
                + len(self._medium_term)
                + len(self._long_term)
            ),
            "current_date": self._current_date,
            "persist_path": self._persist_path,
        }

    def get_all_entries(self, layer: str = "all", limit: int = 50) -> List[Dict]:
        """Return memory entries as dicts for API inspection."""
        entries: List[MemoryEntry] = []
        if layer in ("all", "short"):
            entries.extend(self._short_term)
        if layer in ("all", "medium"):
            entries.extend(self._medium_term)
        if layer in ("all", "long"):
            entries.extend(self._long_term)
        entries.sort(key=lambda m: m.compound_score, reverse=True)
        return [m.to_dict() for m in entries[:limit]]

    # --- Internal helpers ---

    @staticmethod
    def _decay_layer(layer: List[MemoryEntry], rate: float) -> None:
        """Apply exponential recency decay to all entries in a layer."""
        for entry in layer:
            entry.recency = max(0.0, entry.recency - rate)

    @staticmethod
    def _trim(layer: List[MemoryEntry], max_size: int) -> None:
        """Remove lowest-scoring entries if layer exceeds max size."""
        if len(layer) > max_size:
            layer.sort(key=lambda m: m.compound_score, reverse=True)
            del layer[max_size:]

    def _save(self) -> None:
        """Persist all layers to JSON file."""
        try:
            data = {
                "current_date": self._current_date,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "short_term": [m.to_dict() for m in self._short_term],
                "medium_term": [m.to_dict() for m in self._medium_term],
                "long_term": [m.to_dict() for m in self._long_term],
            }
            tmp_path = self._persist_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, self._persist_path)
        except Exception as e:
            logger.error("llm_memory_save_failed", error=str(e))

    def _load(self) -> None:
        """Load persisted memory from JSON file."""
        if not os.path.exists(self._persist_path):
            logger.info("llm_memory_no_file", path=self._persist_path)
            return
        try:
            with open(self._persist_path, "r") as f:
                data = json.load(f)
            self._current_date = data.get("current_date")
            self._short_term = [
                MemoryEntry.from_dict(d) for d in data.get("short_term", [])
            ]
            self._medium_term = [
                MemoryEntry.from_dict(d) for d in data.get("medium_term", [])
            ]
            self._long_term = [
                MemoryEntry.from_dict(d) for d in data.get("long_term", [])
            ]
            logger.info(
                "llm_memory_loaded",
                short=len(self._short_term),
                medium=len(self._medium_term),
                long=len(self._long_term),
                saved_at=data.get("saved_at"),
            )
        except Exception as e:
            logger.error("llm_memory_load_failed", error=str(e))
