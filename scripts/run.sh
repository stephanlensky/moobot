#!/bin/sh
API_PORT=${API_PORT:-8000}

run="run"
if [ "$1" = "dev" ]; then
    run="dev"
fi

python -m moobot.main &
bot_pid=$!

fastapi $run --host 0.0.0.0 --port "$API_PORT" moobot/fastapi/app.py &
server_pid=$!

cleanup() {
    echo "Kill signal received, shutting down now"
    kill -TERM $bot_pid
    while ps -p $bot_pid > /dev/null 2>&1; do sleep 1; done
    kill -TERM $server_pid
    while ps -p $server_pid > /dev/null 2>&1; do sleep 1; done
}

trap cleanup TERM INT
wait $bot_pid
wait $server_pid
