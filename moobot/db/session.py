import time
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as SessionCls
from sqlalchemy.orm import sessionmaker

from moobot.db.models import Base
from moobot.settings import get_settings

settings = get_settings()

credentials = f"{settings.postgres_user}:{settings.postgres_password}"
host = f"{settings.postgres_host}:5432/{settings.postgres_user}"
connection_string = f"postgresql+psycopg://{credentials}@{host}"

engine = create_engine(connection_string, future=True)
Session = sessionmaker(engine)


try:
    Base.metadata.create_all(engine)
except OperationalError:
    print("Waiting for database to be ready...")
    retries = 0
    while retries < 3:
        try:
            Base.metadata.create_all(engine)
            break
        except OperationalError:
            time.sleep(1)
            retries += 1


def get_session() -> Generator[SessionCls, None, None]:
    with Session() as session:
        yield session
