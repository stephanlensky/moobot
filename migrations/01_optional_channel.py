from sqlalchemy import text

from moobot.db.session import engine


def main() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                'ALTER TABLE moobloomevent ADD COLUMN IF NOT EXISTS "create_channel" BOOLEAN NOT NULL DEFAULT TRUE;'
            )
        )
        connection.execute(
            text('ALTER TABLE moobloomevent ADD COLUMN IF NOT EXISTS "thumbnail_url" VARCHAR;')
        )
        connection.execute(
            text('ALTER TABLE moobloomevent ALTER COLUMN "channel_name" DROP NOT NULL;')
        )


if __name__ == "__main__":
    main()
