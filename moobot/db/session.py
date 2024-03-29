from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SessionCls
from sqlalchemy.orm import sessionmaker

from moobot.settings import get_settings

settings = get_settings()

credentials = f"{settings.postgres_user}:{settings.postgres_password}"
host = f"db:5432/{settings.postgres_user}"
connection_string = f"postgresql://{credentials}@{host}"

engine = create_engine(f"postgresql://{credentials}@{host}", future=True)
Session = sessionmaker(engine)


def get_session() -> Generator[SessionCls, None, None]:
    with Session() as session:
        yield session
