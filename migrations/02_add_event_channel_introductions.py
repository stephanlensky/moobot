from sqlalchemy import text

from moobot.db.session import engine


def main() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                'ALTER TABLE moobloomevent ADD COLUMN IF NOT EXISTS "channel_introduction_message_id" VARCHAR NULL DEFAULT NULL;'
            )
        )


if __name__ == "__main__":
    main()
