#!/usr/bin/env python3

import json
import logging
import os
import re
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
DISCOVERY_STATE_FILE = "/data/discovery_state.json"

EQUINOX_WEB = "https://equinox.salicru.com"
EQUINOX_API = "https://api.equinox.salicru.com"

MQTT_DISCOVERY_PREFIX = "homeassistant"

HTTP_TIMEOUT = 30
MQTT_KEEPALIVE = 60
MQTT_CLIENT_ID = "salicru_equinox_app"
MIN_POLL_INTERVAL = 60


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

    plant_ids_raw = options.get("plant_ids")

    if plant_ids_raw is None:
        plant_ids_raw = []

    if not isinstance(plant_ids_raw, list):
        raise RuntimeError(
            "plant_ids debe ser una lista de Plant ID."
        )

    plant_ids = []

    for value in plant_ids_raw:
        plant_id = str(value or "").strip()

        if not plant_id:
            continue

        if not re.fullmatch(r"[A-Za-z0-9_-]+", plant_id):
            raise RuntimeError(
                f"Plant ID no válido: {plant_id!r}. "
                "Solo se permiten letras, números, guion y guion bajo."
            )

        if plant_id not in plant_ids:
            plant_ids.append(plant_id)

    # Compatibilidad con configuraciones 1.0.x
    legacy_plant_id = str(
        options.get("plant_id") or ""
    ).strip()

    if not plant_ids and legacy_plant_id:
        if not re.fullmatch(
            r"[A-Za-z0-9_-]+",
            legacy_plant_id,
        ):
            raise RuntimeError(
                f"Plant ID no válido: {legacy_plant_id!r}."
            )

        plant_ids = [legacy_plant_id]

        LOGGER.warning(
            "Usando plant_id heredado. "
            "Cambia la configuración a plant_ids "
            "para utilizar varias plantas."
        )

    if not plant_ids:
        raise RuntimeError(
            "No se ha configurado ningún Plant ID en plant_ids."
        )

    try:
        poll_interval = int(
            options.get("poll_interval", 900)
        )
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

    if poll_interval < MIN_POLL_INTERVAL:
        raise RuntimeError(
            f"poll_interval debe ser como mínimo {MIN_POLL_INTERVAL} segundos."
        )

    return {
        "email": email,
        "password": password,
        "plant_ids": plant_ids,
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
PLANT_IDS = OPTIONS["plant_ids"]
POLL_INTERVAL = OPTIONS["poll_interval"]

MQTT_HOST = MQTT_CONFIG["host"]
MQTT_PORT = MQTT_CONFIG["port"]
MQTT_USER = MQTT_CONFIG["username"]
MQTT_PASSWORD = MQTT_CONFIG["password"]

def plant_device_id(plant_id):
    return f"salicru_equinox_{plant_id}"


def plant_state_topic(plant_id):
    return f"salicru/{plant_id}/state"


def plant_availability_topic(plant_id):
    return f"salicru/{plant_id}/availability"


def inverter_state_topic(plant_id, inverter_key):
    return (
        f"salicru/{plant_id}/"
        f"inverter/{inverter_key}/state"
    )


def plant_entity_id(
    plant_id,
    domain,
    suffix,
):
    safe_plant_id = slugify(
        plant_id,
        "plant",
    )

    safe_suffix = slugify(
        suffix,
        "entity",
    )

    return (
        f"{domain}.salicru_equinox_"
        f"{safe_plant_id}_{safe_suffix}"
    )


def slugify(value, fallback):
    value = str(value or "").strip().lower()
    value = re.sub(
        r"[^a-z0-9_-]+",
        "_",
        value,
    )
    value = re.sub(
        r"_+",
        "_",
        value,
    ).strip("_-")

    return value or fallback

def load_discovery_state():
    try:
        with open(
            DISCOVERY_STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except FileNotFoundError:
        return {}

    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        LOGGER.warning(
            "No se pudo leer el estado de Discovery: %s",
            error,
        )
        return {}

    if not isinstance(data, dict):
        return {}

    result = {}

    for plant_id, keys in data.items():
        if isinstance(keys, list):
            result[str(plant_id)] = {
                str(key)
                for key in keys
            }

    return result


def save_discovery_state(state):
    try:
        with open(
            DISCOVERY_STATE_FILE,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                {
                    plant_id: sorted(keys)
                    for plant_id, keys in state.items()
                },
                file,
                ensure_ascii=False,
                indent=2,
            )

    except OSError as error:
        LOGGER.warning(
            "No se pudo guardar el estado de Discovery: %s",
            error,
        )

# ---------------------------------------------------------------------------
# MQTT topics
# ---------------------------------------------------------------------------

PLANT_SENSOR_CONFIG = {
    "inverter_power": {
        "name": "Potencia planta",
        "unit": "kW",
        "device_class": "power",
        "state_class": "measurement",
        "suggested_display_precision": 3,
        "entity_id": "potencia_planta",
    },
    "daily_generation": {
        "name": "Generación diaria",
        "unit": "kWh",
        "entity_id": "generacion_diaria",
    },
    "daily_consumption": {
        "name": "Consumo diario",
        "unit": "kWh",
        "entity_id": "consumo_diario",
    },
    "import_energy": {
        "name": "Energía importada",
        "unit": "kWh",
        "entity_id": "energia_importada",
    },
    "export_energy": {
        "name": "Energía exportada",
        "unit": "kWh",
        "entity_id": "energia_exportada",
    },
    "self_consumption": {
        "name": "Autoconsumo",
        "unit": "kWh",
        "entity_id": "autoconsumo",
    },
    "grid_power": {
        "name": "Potencia red",
        "unit": "kW",
        "device_class": "power",
        "state_class": "measurement",
        "suggested_display_precision": 3,
        "entity_id": "potencia_red",
    },
    "alarm_count": {
        "name": "Número de alarmas",
        "unit": None,
        "suggested_display_precision": 0,
        "entity_id": "numero_alarmas",
    },
    "inverter_count": {
        "name": "Número de inversores",
        "unit": None,
        "suggested_display_precision": 0,
        "entity_id": "numero_inversores",
        "entity_category": "diagnostic",
    },
    "last_update": {
        "name": "Última actualización",
        "unit": None,
        "device_class": "timestamp",
        "entity_id": "ultima_actualizacion",
    },
}

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

def request_realtime(plant_id):
    """Request current plant data using the current token."""

    if not TOKEN:
        login()

    url = (
        f"{EQUINOX_API}/plants/"
        f"{plant_id}/realTime"
    )

    response = http_request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Platform-Referer": "EquinoxWeb",
        },
    )

    return read_json_response(response)

def request_plant(plant_id):
    """Request current plant information using the current token."""

    if not TOKEN:
        login()

    url = (
        f"{EQUINOX_API}/plants/{plant_id}"
    )

    response = http_request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Platform-Referer": "EquinoxWeb",
        },
    )

    return read_json_response(response)

def get_realtime(plant_id):
    """
    Get current plant data.

    If EQUINOX returns HTTP 401, authenticate again and retry once.
    """

    global TOKEN

    try:
        return request_realtime(plant_id)

    except HTTPError as error:
        if error.code != 401:
            raise

        LOGGER.warning(
            "El token EQUINOX ha expirado. "
            "Renovando sesión..."
        )

        TOKEN = None
        login()

        return request_realtime(plant_id)

def get_plant(plant_id):
    """
    Get current plant information.

    If EQUINOX returns HTTP 401, authenticate again and retry once.
    """

    global TOKEN

    try:
        return request_plant(plant_id)

    except HTTPError as error:
        if error.code != 401:
            raise

        LOGGER.warning(
            "El token EQUINOX ha expirado. "
            "Renovando sesión..."
        )

        TOKEN = None
        login()

        return request_plant(plant_id)

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
        client_id=MQTT_CLIENT_ID,
    )

    if MQTT_USER:
        client.username_pw_set(
            MQTT_USER,
            MQTT_PASSWORD,
        )

    # Si la aplicación desaparece sin desconectarse correctamente,
    # el broker publicará "offline" automáticamente.
    client.will_set(
        "salicru/application/availability",
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

    mqtt_publish(
        client,
        "salicru/application/availability",
        "online",
        retain=True,
    )

    return client


# ---------------------------------------------------------------------------
# MQTT Discovery
# ---------------------------------------------------------------------------

def extract_plant_name(plant_data, plant_id):
    name = plant_data.get("name")

    if name:
        return f"Salicru EQUINOX - {name}"

    return f"Salicru EQUINOX - {plant_id}"

def device_info(plant_id, plant_data):
    """Return the Home Assistant device information for a plant."""

    return {
        "identifiers": [
            plant_device_id(plant_id)
        ],
        "name": extract_plant_name(
            plant_data,
            plant_id,
        ),
        "manufacturer": "Salicru",
        "model": "EQUINOX",
    }

def extract_inverter_catalog(plant_data):
    """Extract inverter metadata from the plant devices."""

    catalog = []

    devices = plant_data.get("devices")

    if not isinstance(devices, list):
        return catalog

    for device_index, device in enumerate(
        devices,
        start=1,
    ):
        if not isinstance(device, dict):
            continue

        inverters = device.get("inverters")

        if not isinstance(inverters, list):
            continue

        for inverter_index, inverter in enumerate(
            inverters,
            start=1,
        ):
            if not isinstance(inverter, dict):
                continue

            serial = str(
                inverter.get("sn") or ""
            ).strip()

            catalog.append(
                {
                    "serial": serial,
                    "model": str(
                        inverter.get("model") or ""
                    ).strip(),
                    "device_index": device_index,
                    "inverter_index": inverter_index,
                }
            )

    return catalog

def find_catalog_item(
    realtime_inverter,
    index,
    catalog,
):
    serial = str(
        realtime_inverter.get("serialNumber") or ""
    ).strip()

    if serial:
        for item in catalog:
            if item["serial"] and (
                item["serial"].casefold()
                == serial.casefold()
            ):
                return item

    if index < len(catalog):
        return catalog[index]

    return {}

def extract_inverters(
    realtime_data,
    plant_data,
):
    """Build normalized per-inverter data."""

    realtime_inverters = realtime_data.get(
        "invertersProps"
    )

    if not isinstance(
        realtime_inverters,
        list,
    ):
        return []

    catalog = extract_inverter_catalog(
        plant_data
    )

    if len(realtime_inverters) != len(catalog):
        LOGGER.warning(
            "La planta tiene %s inversores en "
            "realTime y %s en /plants.",
            len(realtime_inverters),
            len(catalog),
        )

    records = []
    used_keys = set()

    for index, realtime_inverter in enumerate(
        realtime_inverters
    ):
        if not isinstance(
            realtime_inverter,
            dict,
        ):
            continue

        catalog_item = find_catalog_item(
            realtime_inverter,
            index,
            catalog,
        )

        serial = (
            str(
                realtime_inverter.get(
                    "serialNumber"
                ) or ""
            ).strip()
            or catalog_item.get(
                "serial",
                "",
            )
        )

        fallback_key = (
            f"inverter_{index + 1}"
        )

        base_value = (
            serial
            or fallback_key
        )

        key = slugify(
            base_value,
            fallback_key,
        )

        if key in used_keys:
            key = (
                f"{key}_{index + 1}"
            )

        used_keys.add(key)

        try:
            power = float(
                realtime_inverter.get(
                    "outputPower"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            power = None

        label = (
            f"Inversor {index + 1}"
            if not serial
            else f"Inversor {serial}"
        )

        records.append(
            {
                "key": key,
                "index": index + 1,
                "label": label,
                "serial": (
                    serial or None
                ),
                "model": (
                    catalog_item.get(
                        "model"
                    ) or None
                ),
                "power": power,
            }
        )

    return records

def extract_plant_connection(
    plant_data
):
    """Get aggregate connectivity state for the plant."""

    devices = plant_data.get(
        "devices"
    )

    if not isinstance(
        devices,
        list,
    ) or not devices:
        return None

    statuses = [
        device.get("status")
        for device in devices
        if isinstance(device, dict)
    ]

    if not statuses or any(
        status not in {
            "CONNECTED",
            "DISCONNECTED",
        }
        for status in statuses
    ):
        return None

    if all(
        status == "CONNECTED"
        for status in statuses
    ):
        return "ON"

    if all(
        status == "DISCONNECTED"
        for status in statuses
    ):
        return "OFF"

    return None

def publish_discovery(
    client,
    plant_id,
    plant_data,
    inverter_records,
):
    """Publish MQTT Discovery configuration for one plant."""

    device = device_info(
        plant_id,
        plant_data,
    )

    device_id = plant_device_id(
        plant_id
    )

    state_topic = plant_state_topic(
        plant_id
    )

    availability_topic = (
        plant_availability_topic(
            plant_id
        )
    )

    current_keys = set()

    for key, config in PLANT_SENSOR_CONFIG.items():
        discovery_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/sensor/"
            f"{device_id}/{key}/config"
        )

        payload = {
            "name": config["name"],
            "unique_id": (
                f"{device_id}_{key}"
            ),
            "default_entity_id": plant_entity_id(
                plant_id,
                "sensor",
                config["entity_id"],
            ),
            "state_topic": state_topic,
            "value_template": (
                f"{{{{ value_json.{key} }}}}"
            ),
            "availability_topic": (
                availability_topic
            ),
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }

        if config["unit"]:
            payload["unit_of_measurement"] = (
                config["unit"]
            )

        if config.get("device_class"):
            payload["device_class"] = (
                config["device_class"]
            )

        if config.get("state_class"):
            payload["state_class"] = (
                config["state_class"]
            )

        if config.get(
            "suggested_display_precision"
        ) is not None:
            payload[
                "suggested_display_precision"
            ] = config[
                "suggested_display_precision"
            ]

        if config.get("entity_category"):
            payload["entity_category"] = (
                config["entity_category"]
            )

        mqtt_publish(
            client,
            discovery_topic,
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            retain=True,
        )

    # -----------------------------------------------------------------------
    # Sensores individuales de los inversores
    # -----------------------------------------------------------------------

    for inverter in inverter_records:
        key = inverter["key"]
        label = inverter["label"]

        current_keys.add(key)

        # -------------------------------------------------------------------
        # Potencia del inversor
        # -------------------------------------------------------------------

        discovery_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/sensor/"
            f"{device_id}/"
            f"inverter_{key}_power/config"
        )
        
        payload = {
            "name": f"Potencia {label}",
            "unique_id": (
                f"{device_id}_"
                f"inverter_{key}_power"
            ),
            "default_entity_id": plant_entity_id(
                plant_id,
                "sensor",
                f"inversor_{key}_potencia",
            ),
            "state_topic": inverter_state_topic(
                plant_id,
                key,
            ),
            "value_template": (
                "{{ value_json.power }}"
            ),
            "unit_of_measurement": "kW",
            "device_class": "power",
            "state_class": "measurement",
            "suggested_display_precision": 3,
            "availability_topic": (
                plant_availability_topic(plant_id)
            ),
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }

        mqtt_publish(
            client,
            discovery_topic,
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            retain=True,
        )

    # -----------------------------------------------------------------------
    # Alarmas inversor
    # -----------------------------------------------------------------------

    discovery_topic = (
        f"{MQTT_DISCOVERY_PREFIX}/sensor/"
        f"{device_id}/alarms/config"
    )

    payload = {
        "name": "Alarmas inversor",
        "unique_id": f"{device_id}_alarms",
        "state_topic": state_topic,
        "value_template": "{{ value_json.alarms }}",
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
        "default_entity_id": plant_entity_id(
            plant_id,
            "sensor",
            "alarmas_inversor",
        ),
        "entity_category": "diagnostic",
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
        f"{device_id}/api_ok/config"
    )

    payload = {
        "name": "Comunicación EQUINOX",
        "unique_id": f"{device_id}_api_ok",
        "state_topic": state_topic,
        "value_template": "{{ value_json.api_ok }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "connectivity",
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
        "default_entity_id": plant_entity_id(
            plant_id,
            "binary_sensor",
            "comunicacion_equinox",
        ),
    }

    mqtt_publish(
        client,
        discovery_topic,
        json.dumps(payload, ensure_ascii=False),
        retain=True,
    )

    # -----------------------------------------------------------------------
    # Conectividad de la planta
    # -----------------------------------------------------------------------

    discovery_topic = (
        f"{MQTT_DISCOVERY_PREFIX}/binary_sensor/"
        f"{device_id}/plant_connection/config"
    )

    payload = {
        "name": "Planta conectada",
        "unique_id": f"{device_id}_plant_connection",
        "default_entity_id": plant_entity_id(
            plant_id,
            "binary_sensor",
            "planta_conectada",
        ),
        "state_topic": state_topic,
        "value_template": "{{ value_json.plant_connected }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "connectivity",
        "entity_category": "diagnostic",
        "availability_topic": availability_topic,
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

    return current_keys


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


def extract_data(
    data,
    plant_data,
):
    """Convert EQUINOX responses into plant MQTT state."""

    alarms = data.get(
        "inverterAlarms"
    ) or []

    inverter_records = extract_inverters(
        data,
        plant_data,
    )

    powers = [
        inverter["power"]
        for inverter in inverter_records
        if inverter["power"] is not None
    ]

    plant_power = (
        sum(powers)
        if powers
        else None
    )

    if isinstance(
        alarms,
        list,
    ):
        alarm_count = len(alarms)
    elif alarms:
        alarm_count = 1
    else:
        alarm_count = 0

    return {
        "inverter_power": plant_power,
        "daily_generation": data.get(
            "dailyGeneration"
        ),
        "daily_consumption": data.get(
            "dailyConsumption"
        ),
        "import_energy": data.get(
            "importEnergy"
        ),
        "export_energy": data.get(
            "exportEnergy"
        ),
        "self_consumption": data.get(
            "selfConsumption"
        ),
        "grid_power": data.get(
            "gridPower"
        ),
        "alarm_count": alarm_count,
        "alarms": format_alarms(
            alarms
        ),
        "inverter_count": len(
            inverter_records
        ),
        "last_update": datetime.now(
            timezone.utc
        ).isoformat(),
        "api_ok": "ON",
        "plant_connected": (
            extract_plant_connection(
                plant_data
            )
        ),
        "inverters": inverter_records,
    }


# ---------------------------------------------------------------------------
# State publishing
# ---------------------------------------------------------------------------

def publish_state(
    client,
    plant_id,
    state,
):
    state_payload = dict(state)

    state_payload.pop(
        "inverters",
        None,
    )

    mqtt_publish(
        client,
        plant_state_topic(plant_id),
        json.dumps(
            state_payload,
            ensure_ascii=False,
        ),
        retain=True,
    )

    mqtt_publish(
        client,
        plant_availability_topic(
            plant_id
        ),
        "online",
        retain=True,
    )

def publish_inverter_states(
    client,
    plant_id,
    state,
):
    """Publish the individual state of each inverter."""

    for inverter in state.get(
        "inverters",
        [],
    ):
        payload = {
            "power": inverter["power"],
            "serial_number": inverter["serial"],
            "model": inverter["model"],
        }

        mqtt_publish(
            client,
            inverter_state_topic(
                plant_id,
                inverter["key"],
            ),
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            retain=True,
        )

def cleanup_removed_inverters(
    client,
    plant_id,
    stale_keys,
):
    """Remove retained discovery configs for removed inverters."""

    device_id = plant_device_id(
        plant_id
    )

    for key in stale_keys:
        sensor_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/sensor/"
            f"{device_id}/"
            f"inverter_{key}_power/config"
        )

        mqtt_publish(
            client,
            sensor_topic,
            "",
            retain=True,
        )

        state_topic = inverter_state_topic(
            plant_id,
            key,
        )

        mqtt_publish(
            client,
            state_topic,
            "",
            retain=True,
        )

def cleanup_removed_plants(
    client,
    configured_plant_ids,
    discovery_state,
):
    """
    Remove MQTT Discovery entities and retained state
    for plants that are no longer configured.
    """

    configured_plant_ids = set(
        configured_plant_ids
    )

    removed_plant_ids = (
        set(discovery_state.keys())
        - configured_plant_ids
    )

    if not removed_plant_ids:
        return set()

    cleaned_plant_ids = set()

    for plant_id in removed_plant_ids:
        device_id = plant_device_id(
            plant_id
        )

        cleanup_success = True

        LOGGER.info(
            "La planta %s ya no está configurada. "
            "Eliminando sus entidades y estados MQTT...",
            plant_id,
        )

        # -------------------------------------------------------------------
        # Sensores numéricos de la planta
        # -------------------------------------------------------------------

        for key in PLANT_SENSOR_CONFIG:
            discovery_topic = (
                f"{MQTT_DISCOVERY_PREFIX}/sensor/"
                f"{device_id}/{key}/config"
            )

            try:
                mqtt_publish(
                    client,
                    discovery_topic,
                    "",
                    retain=True,
                )
            except Exception as error:
                cleanup_success = False

                LOGGER.warning(
                    "No se pudo eliminar Discovery "
                    "de %s: %s",
                    discovery_topic,
                    error,
                )

        # -------------------------------------------------------------------
        # Alarmas inversor
        # -------------------------------------------------------------------

        alarms_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/sensor/"
            f"{device_id}/alarms/config"
        )

        try:
            mqtt_publish(
                client,
                alarms_topic,
                "",
                retain=True,
            )
        except Exception as error:
            cleanup_success = False

            LOGGER.warning(
                "No se pudo eliminar Discovery "
                "de %s: %s",
                alarms_topic,
                error,
            )

        # -------------------------------------------------------------------
        # Comunicación EQUINOX
        # -------------------------------------------------------------------

        api_ok_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/binary_sensor/"
            f"{device_id}/api_ok/config"
        )

        try:
            mqtt_publish(
                client,
                api_ok_topic,
                "",
                retain=True,
            )
        except Exception as error:
            cleanup_success = False

            LOGGER.warning(
                "No se pudo eliminar Discovery "
                "de %s: %s",
                api_ok_topic,
                error,
            )

        # -------------------------------------------------------------------
        # Conectividad de la planta
        # -------------------------------------------------------------------

        plant_connection_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/binary_sensor/"
            f"{device_id}/plant_connection/config"
        )

        try:
            mqtt_publish(
                client,
                plant_connection_topic,
                "",
                retain=True,
            )
        except Exception as error:
            cleanup_success = False

            LOGGER.warning(
                "No se pudo eliminar Discovery "
                "de %s: %s",
                plant_connection_topic,
                error,
            )

        # -------------------------------------------------------------------
        # Sensores de potencia de los inversores
        # -------------------------------------------------------------------

        inverter_keys = discovery_state.get(
            plant_id,
            set(),
        )

        for key in inverter_keys:
            inverter_discovery_topic = (
                f"{MQTT_DISCOVERY_PREFIX}/sensor/"
                f"{device_id}/"
                f"inverter_{key}_power/config"
            )

            try:
                mqtt_publish(
                    client,
                    inverter_discovery_topic,
                    "",
                    retain=True,
                )
            except Exception as error:
                cleanup_success = False

                LOGGER.warning(
                    "No se pudo eliminar Discovery "
                    "del inversor %s de la planta %s: %s",
                    key,
                    plant_id,
                    error,
                )

            # Estado MQTT retenido del inversor
            inverter_state = inverter_state_topic(
                plant_id,
                key,
            )

            try:
                mqtt_publish(
                    client,
                    inverter_state,
                    "",
                    retain=True,
                )
            except Exception as error:
                cleanup_success = False

                LOGGER.warning(
                    "No se pudo eliminar el estado MQTT "
                    "del inversor %s de la planta %s: %s",
                    key,
                    plant_id,
                    error,
                )

        # -------------------------------------------------------------------
        # Estado general de la planta
        # -------------------------------------------------------------------

        state_topic = plant_state_topic(
            plant_id
        )

        try:
            mqtt_publish(
                client,
                state_topic,
                "",
                retain=True,
            )
        except Exception as error:
            cleanup_success = False

            LOGGER.warning(
                "No se pudo eliminar el estado MQTT "
                "de la planta %s: %s",
                plant_id,
                error,
            )

        # -------------------------------------------------------------------
        # Disponibilidad de la planta
        # -------------------------------------------------------------------

        availability_topic = (
            plant_availability_topic(
                plant_id
            )
        )

        try:
            mqtt_publish(
                client,
                availability_topic,
                "",
                retain=True,
            )
        except Exception as error:
            cleanup_success = False

            LOGGER.warning(
                "No se pudo eliminar la disponibilidad MQTT "
                "de la planta %s: %s",
                plant_id,
                error,
            )

        if cleanup_success:
            cleaned_plant_ids.add(
                plant_id
            )

            LOGGER.info(
                "Limpieza MQTT completada para la planta %s.",
                plant_id,
            )

        else:
            LOGGER.warning(
                "La limpieza de la planta %s no se completó "
                "correctamente. Se volverá a intentar en el "
                "siguiente arranque.",
                plant_id,
            )

    return cleaned_plant_ids

def publish_offline(
    client,
    plant_id,
):
    """Publish offline availability if possible."""

    try:
        mqtt_publish(
            client,
            plant_availability_topic(
                plant_id
            ),
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
        "Iniciando Salicru EQUINOX - plantas: %s",
        ", ".join(PLANT_IDS),
    )

    LOGGER.info(
        "Intervalo de consulta: %s segundos",
        POLL_INTERVAL,
    )

    mqtt_client = mqtt_connect()

    discovery_state = load_discovery_state()
    
    cleaned_plant_ids = cleanup_removed_plants(
        mqtt_client,
        PLANT_IDS,
        discovery_state,
    )
    
    for plant_id in cleaned_plant_ids:
        discovery_state.pop(
            plant_id,
            None,
        )
    
    if cleaned_plant_ids:
        save_discovery_state(
            discovery_state
        )
    
    discovery_signatures = {}

    try:
        while True:
            for plant_id in PLANT_IDS:

                # ----------------------------------------------------------------
                # Consulta de información de la planta
                # ----------------------------------------------------------------

                try:
                    plant_data = get_plant(
                        plant_id
                    )

                except HTTPError as error:
                    LOGGER.error(
                        "Planta %s - error HTTP "
                        "consultando información: HTTP %s",
                        plant_id,
                        error.code,
                    )

                    publish_offline(
                        mqtt_client,
                        plant_id,
                    )

                    continue

                except URLError as error:
                    LOGGER.error(
                        "Planta %s - error de conexión "
                        "consultando información: %s",
                        plant_id,
                        error.reason,
                    )

                    publish_offline(
                        mqtt_client,
                        plant_id,
                    )

                    continue

                except Exception as error:
                    LOGGER.error(
                        "Planta %s - error consultando "
                        "información: %s",
                        plant_id,
                        error,
                        exc_info=True,
                    )

                    publish_offline(
                        mqtt_client,
                        plant_id,
                    )

                    continue

                # ----------------------------------------------------------------
                # Consulta de datos de tiempo real
                # ----------------------------------------------------------------

                try:
                    realtime_data = get_realtime(
                        plant_id
                    )

                except HTTPError as error:
                    LOGGER.error(
                        "Planta %s - error HTTP "
                        "consultando datos: HTTP %s",
                        plant_id,
                        error.code,
                    )

                    publish_offline(
                        mqtt_client,
                        plant_id,
                    )

                    continue

                except URLError as error:
                    LOGGER.error(
                        "Planta %s - error de conexión "
                        "consultando datos: %s",
                        plant_id,
                        error.reason,
                    )

                    publish_offline(
                        mqtt_client,
                        plant_id,
                    )

                    continue

                except Exception as error:
                    LOGGER.error(
                        "Planta %s - error consultando datos: %s",
                        plant_id,
                        error,
                        exc_info=True,
                    )

                    publish_offline(
                        mqtt_client,
                        plant_id,
                    )

                    continue

                # ----------------------------------------------------------------
                # Procesamiento y publicación de la planta
                # ----------------------------------------------------------------

                try:
                    state = extract_data(
                        realtime_data,
                        plant_data,
                    )

                    inverter_keys = {
                        inverter["key"]
                        for inverter in state["inverters"]
                    }

                    previous_keys = discovery_state.get(
                        plant_id,
                        set(),
                    )

                    signature = (
                        extract_plant_name(
                            plant_data,
                            plant_id,
                        ),
                        tuple(
                            sorted(inverter_keys)
                        ),
                    )

                    if (
                        discovery_signatures.get(
                            plant_id
                        )
                        != signature
                    ):
                        stale_keys = (
                            previous_keys
                            - inverter_keys
                        )

                        if stale_keys:
                            cleanup_removed_inverters(
                                mqtt_client,
                                plant_id,
                                stale_keys,
                            )

                        current_keys = publish_discovery(
                            mqtt_client,
                            plant_id,
                            plant_data,
                            state["inverters"],
                        )

                        discovery_state[
                            plant_id
                        ] = current_keys

                        discovery_signatures[
                            plant_id
                        ] = signature

                        save_discovery_state(
                            discovery_state
                        )

                    publish_state(
                        mqtt_client,
                        plant_id,
                        state,
                    )

                    publish_inverter_states(
                        mqtt_client,
                        plant_id,
                        state,
                    )

                    # Commentar cuando todo Ok
                    LOGGER.info(
                        "EQUINOX OK - planta %s - "
                        "inversores: %s - potencia total: %s kW",
                        plant_id,
                        state["inverter_count"],
                        state["inverter_power"],
                    )

                except Exception as error:
                    LOGGER.error(
                        "Planta %s - error procesando o "
                        "publicando datos: %s",
                        plant_id,
                        error,
                        exc_info=True,
                    )

                    publish_offline(
                        mqtt_client,
                        plant_id,
                    )

                    continue

            time.sleep(
                POLL_INTERVAL
            )

    finally:
        for plant_id in PLANT_IDS:
            publish_offline(
                mqtt_client,
                plant_id,
            )

        try:
            mqtt_publish(
                mqtt_client,
                "salicru/application/availability",
                "offline",
                retain=True,
            )

        except Exception:
            pass

        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()

        except Exception:
            pass


if __name__ == "__main__":
    main()
