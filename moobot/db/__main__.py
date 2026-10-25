import argparse
import sys

from alembic import command

from moobot.db.migrations import (
    SchemaOutdatedError,
    alembic_config,
    check_schema_current,
    current_revision,
    head_revision,
    upgrade_database,
)


def upgrade(_args: argparse.Namespace) -> None:
    print(f"Schema revision: {upgrade_database()}")


def current(_args: argparse.Namespace) -> None:
    print(f"Current revision: {current_revision() or 'unversioned'}")
    print(f"Head revision:    {head_revision()}")


def check(_args: argparse.Namespace) -> None:
    try:
        check_schema_current()
    except SchemaOutdatedError as e:
        sys.exit(str(e))


def history(_args: argparse.Namespace) -> None:
    command.history(alembic_config())


def revision(args: argparse.Namespace) -> None:
    command.revision(alembic_config(), message=args.message, autogenerate=args.autogenerate)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m moobot.db")
    subparsers = parser.add_subparsers(required=True)

    subparsers.add_parser("upgrade", help="Create or migrate the database").set_defaults(
        func=upgrade
    )
    subparsers.add_parser("current", help="Show the current and head revisions").set_defaults(
        func=current
    )
    subparsers.add_parser("check", help="Exit with an error if the schema is behind").set_defaults(
        func=check
    )
    subparsers.add_parser("history", help="List the migration revisions").set_defaults(func=history)
    revision_parser = subparsers.add_parser("revision", help="Create a migration revision")
    revision_parser.add_argument("-m", "--message", required=True)
    revision_parser.add_argument("--no-autogenerate", dest="autogenerate", action="store_false")
    revision_parser.set_defaults(func=revision)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
