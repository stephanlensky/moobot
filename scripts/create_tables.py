from moobot.db.models import Base
from moobot.db.session import engine

Base.metadata.create_all(engine)
