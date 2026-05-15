import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from packages.domain.models import Base

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "stock_kb.sqlite")

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()


class Transaction:
    def __init__(self):
        self.session = get_session()

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
