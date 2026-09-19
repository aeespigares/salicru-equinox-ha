#!/usr/bin/env python3

import json
import logging
import os
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPCookieProcessor,
    Request,
    build_opener,
)

import paho.mqtt.client as mqtt


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

LOGGER = logging.getLogger("salicru-equinox")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPTIONS_FILE = "/data/options.json"

EQUINOX_WEB = "https://equinox.salicru.com"
EQUINOX_API = "https://api.equinox.salicru.com"

MQTT_DISCOVERY_PREFIX = "homeassistant"

HTTP_TIMEOUT = 30
MQTT_KEEPALIVE = 60


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_options():
    """Load and validate Home Assistant App options."""

    try:
        with open(OPTIONS_FILE, "r", encoding="utf-8") as file:
            options = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"No se pudo leer la configuración de la App: {error}"
        ) from error

    email = str(options.get("email") or "").strip()
    password = str(options.get("password") or "")
    plant_id = str(options.get("plant_id") or "").strip()

    try:
        poll_interval = int(options.get("poll_interval", 900))
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            "poll_interval debe ser un número entero."
        ) from error

    if not email:
        raise RuntimeError(
            "No se ha configurado el email de EQUINOX."
        )

    if not password:
        raise RuntimeError(
            "No se ha configurado la contraseña de EQUINOX."
        )

    if not plant_id:
        raise RuntimeError(
            "No se ha configurado el Plant ID de EQUINOX."
        )

    if poll_interval <= 0:
        raise RuntimeError(
            "poll_interval debe ser mayor que 0."
        )

    return {
        "email": email,
        "password": password,
        "plant_id": plant_id,
        "poll_interval": poll_interval,
    }


def load_mqtt_config():
    """Load and validate MQTT configuration supplied by Home Assistant."""

    host = os.environ.get("MQTT_HOST", "").strip()
    port_raw = os.environ.get("MQTT_PORT", "").strip()
    username = os.environ.get("MQTT_USER", "")
    password = os.environ.get("MQTT_PASSWORD", "")

    if not host:
        raise RuntimeError(
            "Home Assistant no ha proporcionado MQTT_HOST."
        )

    if not port_raw:
        raise RuntimeError(
            "Home Assistant no ha proporcionado MQTT_PORT."
        )

    try:
        port = int(port_raw)
    except ValueError as error:
        raise RuntimeError(
            f"MQTT_PORT no es válido: {port_raw!r}"
        ) from error

    if not 1 <= port <= 65535:
        raise RuntimeError(
            f"MQTT_PORT está fuera de rango: {port}"
        )

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }


OPTIONS = load_options()
MQTT_CONFIG = load_mqtt_config()

EMAIL = OPTIONS["email"]
PASSWORD = OPTIONS["password"]
PLANT_ID = OPTIONS["plant_id"]
POLL_INTERVAL = OPTIONS["poll_interval"]

MQTT_HOST = MQTT_CONFIG["host"]
MQTT_PORT = MQTT_CONFIG["port"]
MQTT_USER = MQTT_CONFIG["username"]
MQTT_PASSWORD = MQTT_CONFIG["password"]


# ---------------------------------------------------------------------------
# MQTT topics
# ---------------------------------------------------------------------------

DEVICE_ID = f"salicru_equinox_{PLANT_ID}"

STATE_TOPIC = f"salicru/{PLANT_ID}/state"
AVAILABILITY_TOPIC = f"salicru/{PLANT_ID}/availability"


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

COOKIE_JAR = CookieJar()

OPENER = build_opener(
    HTTPCookieProcessor(COOKIE_JAR)
)

TOKEN = None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def http_request(url, method="GET", data=None, headers=None):
    """Perform an HTTP request using the shared cookie jar."""

    request_headers = {
        "User-Agent": "Home Assistant Salicru EQUINOX",
    }

    if headers:
        request_headers.update(headers)

    body = None

    if data is not None:
        body = urlencode(data).encode("utf-8")
        request_headers["Content-Type"] = (
            "application/x-www-form-urlencoded"
        )

    request = Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )

    return OPENER.open(
        request,
        timeout=HTTP_TIMEOUT,
    )


def read_json_response(response):
    """Read and decode a JSON HTTP response."""

    try:
        return json.loads(
            response.read().decode("utf-8")
        )
    finally:
        response.close()


# ---------------------------------------------------------------------------
# EQUINOX authentication
# ---------------------------------------------------------------------------


def reset_session():
    """Clear the current EQUINOX session."""

    global TOKEN

    TOKEN = None

    try:
        COOKIE_JAR.clear()
    except KeyError:
        pass


def login():
    """Authenticate against EQUINOX and obtain raw-token."""

    global TOKEN

    reset_session()

    LOGGER.info("Obteniendo CSRF de EQUINOX...")

    try:
        response = http_request(
            f"{EQUINOX_WEB}/api/auth/csrf"
        )
        csrf_data = read_json_response(response)

    except (HTTPError, URLError, OSError, ValueError) as error:
        raise RuntimeError(
            f"No se pudo obtener el CSRF de EQUINOX: {error}"
        ) from error

    csrf_token = csrf_data.get("csrfToken")

    if not csrf_token:
        raise RuntimeError(
            "EQUINOX no devolvió un csrfToken válido."
        )

    LOGGER.info("Iniciando sesión en EQUINOX...")

    login_data = {
        "email": EMAIL,
        "password": PASSWORD,
        "redirect": "false",
        "csrfToken": csrf_token,
        "callbackUrl": f"{EQUINOX_WEB}/",
        "json": "true",
    }

    try:
        response = http_request(
            f"{EQUINOX_WEB}/api/auth/callback/credentials",
            method="POST",
            data=login_data,
            headers={
                "Origin": EQUINOX_WEB,
                "Referer": f"{EQUINOX_WEB}/login",
            },
        )

        # El contenido de esta respuesta no es necesario para la
        # autenticación. Cerramos la respuesta y obtenemos raw-token
        # directamente del CookieJar.
        response.close()

    except HTTPError as error:
        raise RuntimeError(
            f"Error HTTP durante el inicio de sesión en EQUINOX "
            f"(HTTP {error.code})."
        ) from error

    except (URLError, OSError) as error:
        raise RuntimeError(
            f"No se pudo iniciar sesión en EQUINOX: {error}"
        ) from error

    for cookie in COOKIE_JAR:
        if cookie.name == "raw-token":
            TOKEN = cookie.value
            break

    if not TOKEN:
        raise RuntimeError(
            "El inicio de sesión no proporcionó la cookie raw-token."
        )

    LOGGER.info("Autenticación EQUINOX correcta.")


# ---------------------------------------------------------------------------
# EQUINOX API
# ---------------------------------------------------------------------------


def request_realtime():
    """Request current plant data using the current token."""

    if not TOKEN:
        login()

    url = f"{EQUINOX_API}/plants/{PLANT_ID}/realTime"

    response = http_request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Platform-Referer": "EquinoxWeb",
        },
    )

    return read_json_response(response)

def request_plant():
    """Request current plant information using the current token."""

    if not TOKEN:
        login()

    url = f"{EQUINOX_API}/plants/{PLANT_ID}"

    response = http_request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Platform-Referer": "EquinoxWeb",
        },
    )

    return read_json_response(response)

def get_realtime():
    """
    Get current plant data.

    If EQUINOX returns HTTP 401, authenticate again and retry once.
    """

    global TOKEN

    try:
        return request_realtime()

    except HTTPError as error:
        if error.code != 401:
            raise

        LOGGER.warning(
            "El token EQUINOX ha expirado. Renovando sesión..."
        )

        TOKEN = None
        login()

        return request_realtime()

def get_plant():
    """
    Get current plant information.

    If EQUINOX returns HTTP 401, authenticate again and retry once.
    """

    global TOKEN

    try:
        return request_plant()

    except HTTPError as error:
        if error.code != 401:
            raise

        LOGGER.warning(
            "El token EQUINOX ha expirado. Renovando sesión..."
        )

        TOKEN = None
        login()

        return request_plant()

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------


def mqtt_publish(client, topic, payload, retain=False):
    """Publish an MQTT message and verify the immediate result code."""

    result = client.publish(
        topic,
        payload,
        qos=0,
        retain=retain,
    )

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(
            f"Error publicando MQTT en {topic}: "
            f"rc={result.rc}"
        )


def mqtt_connect():
    """Connect to the MQTT broker supplied by Home Assistant."""

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=DEVICE_ID,
    )

    if MQTT_USER:
        client.username_pw_set(
            MQTT_USER,
            MQTT_PASSWORD,
        )

    # Si la aplicación desaparece sin desconectarse correctamente,
    # el broker publicará "offline" automáticamente.
    client.will_set(
        AVAILABILITY_TOPIC,
        payload="offline",
        qos=0,
        retain=True,
    )

    LOGGER.info(
        "Conectando a MQTT %s:%s",
        MQTT_HOST,
        MQTT_PORT,
    )

    client.connect(
        MQTT_HOST,
        MQTT_PORT,
        MQTT_KEEPALIVE,
    )

    client.loop_start()

    return client


# ---------------------------------------------------------------------------
# MQTT Discovery
# ---------------------------------------------------------------------------


def device_info():
    """Return the Home Assistant device information."""

    return {
        "identifiers": [DEVICE_ID],
        "name": "Salicru EQUINOX",
        "manufacturer": "Salicru",
        "model": "EQUINOX",
    }


def sensor_discovery_config():
    """Return MQTT Discovery configuration for numeric/text sensors."""

    return {
        "inverter_power": {
            "name": "Potencia inversor",
            "unit": "kW",
            "device_class": "power",
            "state_class": "measurement",
            "suggested_display_precision": 3,
        },
        "daily_generation": {
            "name": "Generación diaria",
            "unit": "kWh"
#            "device_class": "energy",
#            "state_class": "total_increasing",
#            "suggested_display_precision": 2,
        },
        "daily_consumption": {
            "name": "Consumo diario",
            "unit": "kWh"
#            "device_class": "energy",
#            "state_class": "total_increasing",
#            "suggested_display_precision": 2,
        },
        "import_energy": {
            "name": "Energía importada",
            "unit": "kWh"
#            "device_class": "energy",
#            "state_class": "total_increasing",
#            "suggested_display_precision": 2,
        },
        "export_energy": {
            "name": "Energía exportada",
            "unit": "kWh"
#            "device_class": "energy",
#            "state_class": "total_increasing",
#            "suggested_display_precision": 2,
        },
        "self_consumption": {
            "name": "Autoconsumo",
            "unit": "kWh"
#            "device_class": "energy",
#            "state_class": "total_increasing",
#            "suggested_display_precision": 2,
        },
        "grid_power": {
            "name": "Potencia red",
            "unit": "kW",
            "device_class": "power",
            "state_class": "measurement",
            "suggested_display_precision": 3,
        },
        "alarm_count": {
            "name": "Número de alarmas",
            "unit": None,
            "suggested_display_precision": 0,
        },
        "last_update": {
            "name": "Última actualización",
            "unit": None,
            "device_class": "timestamp",
        },
    }


def publish_discovery(client):
    """Publish MQTT Discovery configuration."""

    device = device_info()

    for key, config in sensor_discovery_config().items():
        discovery_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/sensor/"
            f"{DEVICE_ID}/{key}/config"
        )

        payload = {
            "name": config["name"],
            "unique_id": f"{DEVICE_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "value_template": (
                f"{{{{ value_json.{key} }}}}"
            ),
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }

        if config["unit"]:
            payload["unit_of_measurement"] = config["unit"]

        if config.get("device_class"):
            payload["device_class"] = config["device_class"]

        if config.get("state_class"):
            payload["state_class"] = config["state_class"]

        if config.get("suggested_display_precision") is not None:
            payload["suggested_display_precision"] = (
                config["suggested_display_precision"]
            )

        mqtt_publish(
            client,
            discovery_topic,
            json.dumps(payload, ensure_ascii=False),
            retain=True,
        )

    # -----------------------------------------------------------------------
    # Alarmas inversor
    # -----------------------------------------------------------------------

    discovery_topic = (
        f"{MQTT_DISCOVERY_PREFIX}/sensor/"
        f"{DEVICE_ID}/alarms/config"
    )

    payload = {
        "name": "Alarmas inversor",
        "unique_id": f"{DEVICE_ID}_alarms",
        "state_topic": STATE_TOPIC,
        "value_template": "{{ value_json.alarms }}",
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
    }

    mqtt_publish(
        client,
        discovery_topic,
        json.dumps(payload, ensure_ascii=False),
        retain=True,
    )

    # -----------------------------------------------------------------------
    # Comunicación EQUINOX
    # -----------------------------------------------------------------------

    discovery_topic = (
        f"{MQTT_DISCOVERY_PREFIX}/binary_sensor/"
        f"{DEVICE_ID}/api_ok/config"
    )

    payload = {
        "name": "Comunicación EQUINOX",
        "unique_id": f"{DEVICE_ID}_api_ok",
        "state_topic": STATE_TOPIC,
        "value_template": "{{ value_json.api_ok }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "connectivity",
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
    }

    mqtt_publish(
        client,
        discovery_topic,
        json.dumps(payload, ensure_ascii=False),
        retain=True,
    )


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------


def format_alarms(alarms):
    """Convert EQUINOX alarm data into a displayable text value."""

    if not alarms:
        return ""

    if isinstance(alarms, list):
        return ", ".join(
            str(alarm)
            for alarm in alarms
        )

    return str(alarms)


def extract_inverter_power(data):
    """Get inverter output power from the first inverter."""

    inverters = data.get("invertersProps")

    if not isinstance(inverters, list) or not inverters:
        return None

    first_inverter = inverters[0]

    if not isinstance(first_inverter, dict):
        return None

    return first_inverter.get("outputPower")


def extract_data(data):
    """Convert the EQUINOX response into the MQTT state payload."""

    alarms = data.get("inverterAlarms") or []

    if isinstance(alarms, list):
        alarm_count = len(alarms)
    elif alarms:
        alarm_count = 1
    else:
        alarm_count = 0

    return {
        "inverter_power": extract_inverter_power(data),
        "daily_generation": data.get("dailyGeneration"),
        "daily_consumption": data.get("dailyConsumption"),
        "import_energy": data.get("importEnergy"),
        "export_energy": data.get("exportEnergy"),
        "self_consumption": data.get("selfConsumption"),
        "grid_power": data.get("gridPower"),
        "alarm_count": alarm_count,
        "alarms": format_alarms(alarms),
        "last_update": datetime.now(timezone.utc).isoformat(),
        "api_ok": "ON",
    }


# ---------------------------------------------------------------------------
# State publishing
# ---------------------------------------------------------------------------


def publish_state(client, state):
    """Publish the current state and availability."""

    mqtt_publish(
        client,
        STATE_TOPIC,
        json.dumps(
            state,
            ensure_ascii=False,
        ),
        retain=True,
    )

    mqtt_publish(
        client,
        AVAILABILITY_TOPIC,
        "online",
        retain=True,
    )


def publish_offline(client):
    """Publish offline availability if possible."""

    try:
        mqtt_publish(
            client,
            AVAILABILITY_TOPIC,
            "offline",
            retain=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main():
    LOGGER.info(
        "Iniciando Salicru EQUINOX - planta %s",
        PLANT_ID,
    )

    LOGGER.info(
        "Intervalo de consulta: %s segundos",
        POLL_INTERVAL,
    )

    mqtt_client = mqtt_connect()

    try:
        publish_discovery(mqtt_client)

        while True:
            try:
                data = get_realtime()
                state = extract_data(data)

                publish_state(
                    mqtt_client,
                    state,
                )

                LOGGER.info(
                    "EQUINOX OK - potencia inversor: %s kW",
                    state["inverter_power"],
                )

            except HTTPError as error:
                LOGGER.error(
                    "Error HTTP consultando EQUINOX: HTTP %s",
                    error.code,
                )

                publish_offline(mqtt_client)

            except URLError as error:
                LOGGER.error(
                    "Error de conexión con EQUINOX: %s",
                    error.reason,
                )

                publish_offline(mqtt_client)

            except Exception as error:
                LOGGER.error(
                    "Error consultando EQUINOX: %s",
                    error,
                )

                publish_offline(mqtt_client)

            time.sleep(POLL_INTERVAL)

    finally:
        publish_offline(mqtt_client)

        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
