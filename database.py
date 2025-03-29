from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from contextlib import contextmanager
import os

Base = declarative_base()

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    task = Column(String)
    created_at = Column(DateTime, default=datetime.now)
    due_date = Column(DateTime)

# Configurar la base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///tasks.db")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


@contextmanager
def get_session():
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()