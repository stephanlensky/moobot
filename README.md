# moobot

This repository contains code for a Discord bot used to manage common tasks in a private Discord server. The code here remains open-source for contributions from real-life friends and as a code sample reference for future employers.

## Migrations

The schema is managed with Alembic. moobot never migrates the database on its own; it exits
with an error at startup if the schema is behind the code. In production, an init container
runs the upgrade before moobot starts.

```sh
python -m moobot.db upgrade   # Create or migrate the database
python -m moobot.db current   # Show the current and head revisions
python -m moobot.db history   # List the migration revisions
```

A database created before Alembic was introduced is stamped at the initial revision on its
first upgrade, so existing data is preserved.

After changing a model, generate a revision and review the result before committing:

```sh
python -m moobot.db revision -m "add the new column"
```
