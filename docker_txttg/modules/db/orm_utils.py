import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .orm_models import Base

DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
DB_PATH = './data/sent_files.db'

def get_engine():
    if DB_TYPE == 'mysql':
        user = os.getenv('DB_USER', 'root')
        pwd = os.getenv('DB_PASS', '')
        host = os.getenv('DB_HOST', 'localhost')
        db = os.getenv('DB_NAME', 'test')
        url = f"mysql+pymysql://{user}:{pwd}@{host}/{db}?charset=utf8mb4"
    else:
        url = f"sqlite:///{DB_PATH}"
    return create_engine(url, echo=False, future=True)

engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    Base.metadata.create_all(engine)
