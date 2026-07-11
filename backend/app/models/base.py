"""
Multi-database engine/session factory.

Per the architecture:
- Each DB has its own engine + sessionmaker
- This satisfies the "independent databases, never mixed" principle
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
from app.core.config import get_settings

DATA_DIR = os.path.join(get_settings().DATA_PATH, "Reference")

# ---- KP Database ----
KP_DB_PATH = os.path.join(DATA_DIR, "kp_data.db")
KP_URL = f"sqlite:///{KP_DB_PATH}"
kp_engine = create_engine(KP_URL, connect_args={"check_same_thread": False})
KP_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=kp_engine)

# ---- L6 Database ----
L6_DB_PATH = os.path.join(DATA_DIR, "l6_data.db")
L6_URL = f"sqlite:///{L6_DB_PATH}"
l6_engine = create_engine(L6_URL, connect_args={"check_same_thread": False})
L6_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=l6_engine)

# ---- Opportunities Database (商机线索) ----
OPP_DB_PATH = os.path.join(DATA_DIR, "opportunities.db")
OPP_URL = f"sqlite:///{OPP_DB_PATH}"
opp_engine = create_engine(OPP_URL, connect_args={"check_same_thread": False})
Opp_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=opp_engine)

# ---- Rules Database (configurable business logic) ----
RULES_DB_PATH = os.path.join(DATA_DIR, "rules.db")
RULES_URL = f"sqlite:///{RULES_DB_PATH}"
rules_engine = create_engine(RULES_URL, connect_args={"check_same_thread": False})
Rules_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=rules_engine)

# ---- L6 History Database (price/note change logs) ----
L6_HISTORY_DB_PATH = os.path.join(DATA_DIR, "l6_history.db")
L6_HISTORY_URL = f"sqlite:///{L6_HISTORY_DB_PATH}"
l6_history_engine = create_engine(L6_HISTORY_URL, connect_args={"check_same_thread": False})
L6History_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=l6_history_engine)


class Base(DeclarativeBase):
    """Common base for all models. All tables share this declarative base."""
    pass
