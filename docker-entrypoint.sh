#!/bin/sh
set -e

# Ensure data directory exists and symlink DB file for persistence
mkdir -p /data
if [ ! -e /app/agent_mailer.db ]; then
    ln -s /data/agent_mailer.db /app/agent_mailer.db
elif [ ! -L /app/agent_mailer.db ]; then
    # If a real file exists (first run before volume), move it to data
    mv /app/agent_mailer.db /data/agent_mailer.db
    ln -s /data/agent_mailer.db /app/agent_mailer.db
fi

exec "$@"
