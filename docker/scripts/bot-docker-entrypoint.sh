#!/bin/bash
(trap 'kill 0' SIGINT; poetry run moobot & poetry run uvicorn moobot.fastapi.app:app --host 0.0.0.0 --port 3000)
