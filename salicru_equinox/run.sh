#!/usr/bin/with-contenv bashio

bashio::log.info "Salicru EQUINOX: iniciando run.sh"
bashio::log.info "Salicru EQUINOX: comprobando servicio MQTT..."

if ! bashio::services.available "mqtt"; then
    bashio::log.error "El servicio MQTT no está disponible desde Supervisor."
    exit 1
fi

bashio::log.info "Salicru EQUINOX: servicio MQTT disponible."

export MQTT_HOST="$(bashio::services mqtt 'host')"
export MQTT_PORT="$(bashio::services mqtt 'port')"
export MQTT_USER="$(bashio::services mqtt 'username')"
export MQTT_PASSWORD="$(bashio::services mqtt 'password')"

bashio::log.info \
    "Salicru EQUINOX: MQTT configurado en ${MQTT_HOST}:${MQTT_PORT}"

bashio::log.info "Salicru EQUINOX: iniciando Python..."

exec /opt/venv/bin/python -u /app/run.py
