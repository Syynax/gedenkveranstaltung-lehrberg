#!/usr/bin/with-contenv bashio

bashio::log.info "Anmeldeseite wird gestartet ..."

exec python3 /app/server.py
