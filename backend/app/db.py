from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import config

class Base(DeclarativeBase):
    pass

engine = create_engine(config().database_url, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)

def database():
    with Session() as session:
        yield session
