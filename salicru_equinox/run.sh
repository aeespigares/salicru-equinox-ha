#!/usr/bin/with-contenv bashio

bashio::log.info "Salicru EQUINOX: iniciando run.sh"
bashio::log.info "Salicru EQUINOX: comprobando servicio MQTT..."

if ! bashio::services.available "mqtt"; then
    bashio::log.error "El servicio MQTT no está disponible desde Supervisor."
    exit 1
fi

bashio::log.info "Salicru EQUINOX: servicio MQTT disponible."

if ! MQTT_HOST="$(bashio::services mqtt 'host')"; then
    bashio::log.error "No se pudo obtener MQTT_HOST."
    exit 1
fi

if ! MQTT_PORT="$(bashio::services mqtt 'port')"; then
    bashio::log.error "No se pudo obtener MQTT_PORT."
    exit 1
fi

if ! MQTT_USER="$(bashio::services mqtt 'username')"; then
    bashio::log.error "No se pudo obtener MQTT_USER."
    exit 1
fi

if ! MQTT_PASSWORD="$(bashio::services mqtt 'password')"; then
    bashio::log.error "No se pudo obtener MQTT_PASSWORD."
    exit 1
fi

export MQTT_HOST
export MQTT_PORT
export MQTT_USER
export MQTT_PASSWORD

bashio::log.info \
    "Salicru EQUINOX: MQTT configurado en ${MQTT_HOST}:${MQTT_PORT}"

bashio::log.info "Salicru EQUINOX: comprobando Python..."

if [ ! -x "/opt/venv/bin/python" ]; then
    bashio::log.error "No existe /opt/venv/bin/python o no es ejecutable."
    exit 1
fi

if [ ! -f "/app/run.py" ]; then
    bashio::log.error "No existe /app/run.py."
    exit 1
fi

PYTHON_VERSION="$(/opt/venv/bin/python --version 2>&1)"
bashio::log.info "Salicru EQUINOX: ${PYTHON_VERSION}"

RUNPY_LINES="$(wc -l < /app/run.py)"
bashio::log.info "Salicru EQUINOX: run.py tiene ${RUNPY_LINES} líneas"

bashio::log.info "Salicru EQUINOX: probando importación de paho-mqtt..."

if ! /opt/venv/bin/python -c \
    'import paho.mqtt; print("paho-mqtt OK:", paho.mqtt.__version__)'
then
    bashio::log.error "Falló la importación de paho-mqtt."
    exit 1
fi

bashio::log.info "Salicru EQUINOX: iniciando Python..."

/opt/venv/bin/python -u /app/run.py
PYTHON_EXIT_CODE=$?

bashio::log.error \
    "Salicru EQUINOX: Python terminó con código ${PYTHON_EXIT_CODE}."

exit "${PYTHON_EXIT_CODE}"
