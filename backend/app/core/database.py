"""
Legacy database.py is kept for backward compatibility.
The multi-engine setup is in app.models.base.
This module now re-exports for imports that still reference it.
"""
from app.models.base import (
    Base, kp_engine, l6_engine, opp_engine,
    KP_SessionLocal, L6_SessionLocal, Opportunity_SessionLocal,
)
from app.core.config import get_settings

settings = get_settings()

# Backward-compatible get_db — raises to prevent accidental misuse.
# APIs should use explicit Repository sessions (Opportunity_SessionLocal, etc.)
def get_db():
    raise NotImplementedError(
        "get_db() is deprecated. Use explicit Repository sessions "
        "(e.g., Opportunity_SessionLocal) instead to avoid connecting to the wrong database."
    )
