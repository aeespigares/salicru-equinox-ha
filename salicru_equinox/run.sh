#!/command/with-contenv bashio

bashio::log.info "Salicru EQUINOX: iniciando run.sh"

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------

bashio::log.info "Salicru EQUINOX: comprobando servicio MQTT..."

if ! bashio::services.available "mqtt"; then
    bashio::log.error "El servicio MQTT no está disponible desde Supervisor."
    exit 1
fi

bashio::log.info "Salicru EQUINOX: servicio MQTT disponible."

if ! MQTT_HOST="$(bashio::services mqtt 'host')"; then
    bashio::log.error "No se pudo obtener MQTT_HOST desde Supervisor."
    exit 1
fi

if ! MQTT_PORT="$(bashio::services mqtt 'port')"; then
    bashio::log.error "No se pudo obtener MQTT_PORT desde Supervisor."
    exit 1
fi

if ! MQTT_USER="$(bashio::services mqtt 'username')"; then
    bashio::log.error "No se pudo obtener MQTT_USER desde Supervisor."
    exit 1
fi

if ! MQTT_PASSWORD="$(bashio::services mqtt 'password')"; then
    bashio::log.error "No se pudo obtener MQTT_PASSWORD desde Supervisor."
    exit 1
fi

if [ -z "${MQTT_HOST}" ]; then
    bashio::log.error "MQTT_HOST está vacío."
    exit 1
fi

if [ -z "${MQTT_PORT}" ]; then
    bashio::log.error "MQTT_PORT está vacío."
    exit 1
fi

export MQTT_HOST
export MQTT_PORT
export MQTT_USER
export MQTT_PASSWORD

bashio::log.info \
    "Salicru EQUINOX: MQTT configurado en ${MQTT_HOST}:${MQTT_PORT}"

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

if [ ! -x "/opt/venv/bin/python" ]; then
    bashio::log.error "No existe /opt/venv/bin/python."
    exit 1
fi

if [ ! -f "/app/run.py" ]; then
    bashio::log.error "No existe /app/run.py."
    exit 1
fi

bashio::log.info "Salicru EQUINOX: iniciando Python..."

exec /opt/venv/bin/python -u /app/run.py
