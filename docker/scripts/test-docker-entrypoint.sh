#!/bin/sh
set -e

# format code
echo "Running isort..."
poetry run isort moobot tests migrations
echo "Running black..."
poetry run black moobot tests migrations

# run code tests
echo "Running tests..."
poetry run pytest tests

# run linters
echo "Running mypy..."
poetry run mypy moobot tests migrations
echo "Running pylint..."
poetry run pylint moobot tests migrations
