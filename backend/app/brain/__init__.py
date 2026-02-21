"""
PURPOSE: Brain package initialization and singleton factory.

Provides get_brain() to access the global Brain singleton instance.

CALLED BY:
    - engine/engine.py
    - api/routes_brain.py
"""

from typing import Optional

from app.brain.brain import Brain

_brain_instance: Optional[Brain] = None


def get_brain() -> Brain:
    """
    PURPOSE: Return the global Brain singleton, creating it on first call.

    Returns:
        Brain: The singleton Brain instance

    CALLED BY: engine/engine.py, api/routes_brain.py
    """
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = Brain()
    return _brain_instance


__all__ = ["get_brain", "Brain"]
