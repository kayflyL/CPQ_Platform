"""
PostgreSQL multi-schema engine/session factory.

Architecture:
- Single PostgreSQL database with 6 schemas (kp, l6, opportunities, rules, l6_history, public)
- Each schema has its own session factory for logical isolation
- Satisfies the "independent databases, never mixed" principle via schema separation
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import get_settings


# Single PostgreSQL engine with connection pooling
settings = get_settings()
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    connect_args={
        "client_encoding": "UTF8",
    }
)


# ---- Schema-specific session factories ----
# Each schema gets its own sessionmaker bound to a schema-translated engine

# ---- KP Schema (Key Parts) ----
kp_engine = engine.execution_options(schema_translate_map={None: "kp"})
KP_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=kp_engine)

# ---- L6 Schema ----
l6_engine = engine.execution_options(schema_translate_map={None: "l6"})
L6_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=l6_engine)

# ---- Opportunities Schema (商机线索) ----
opp_engine = engine.execution_options(schema_translate_map={None: "opportunities"})
Opportunity_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=opp_engine)

# ---- Rules Schema (configurable business logic) ----
rules_engine = engine.execution_options(schema_translate_map={None: "rules"})
Rules_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=rules_engine)

# ---- L6 History Schema (price/note change logs) ----
l6_history_engine = engine.execution_options(schema_translate_map={None: "l6_history"})
L6History_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=l6_history_engine)

# ---- Public Schema (comments, etc.) ----
public_engine = engine.execution_options(schema_translate_map={None: "public"})
Public_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=public_engine)


class Base(DeclarativeBase):
    """Common base for all models. All tables share this declarative base."""
    pass
