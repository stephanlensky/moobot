from typing import Generator

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.models import Base

sqlite_engine = create_engine(
    "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
)


@pytest.fixture
def test_db_session(mocker: MockerFixture) -> Generator[sessionmaker[Session], None, None]:
    """
    Test fixture for replacing the postgres session with a clean SQLite session.
    DB is cleared after use.
    """
    sm = sessionmaker(sqlite_engine)
    mocker.patch("moobot.db.session.Session", sm)

    Base.metadata.create_all(sqlite_engine)
    yield sm
    Base.metadata.drop_all(sqlite_engine)
