#!/usr/bin/env python3

import json
import logging
import os
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

import paho.mqtt.client as mqtt


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

LOGGER = logging.getLogger("salicru-equinox")

OPTIONS_FILE = "/data/options.json"

EQUINOX_WEB = "https://equinox.salicru.com"
EQUINOX_API = "https://api.equinox.salicru.com"

MQTT_DISCOVERY_PREFIX = "homeassistant"


def load_options():
    with open(OPTIONS_FILE, "r", encoding="utf-8") as file:
        options = json.load(file)

    return {
        "email": options["email"],
        "password": options["password"],
        "plant_id": str(options["plant_id"]),
        "poll_interval": int(options.get("poll_interval", 900)),
    }


OPTIONS = load_options()

EMAIL = OPTIONS["email"]
PASSWORD = OPTIONS["password"]
PLANT_ID = OPTIONS["plant_id"]
POLL_INTERVAL = OPTIONS["poll_interval"]

MQTT_HOST = os.environ.get("MQTT_HOST", "")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")

STATE_TOPIC = f"salicru/{PLANT_ID}/state"
AVAILABILITY_TOPIC = f"salicru/{PLANT_ID}/availability"

OPENER = build_opener(CookieJar())

TOKEN = None


def http_request(url, method="GET", data=None, headers=None):
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

    return OPENER.open(request, timeout=30)


def login():
    global TOKEN

    LOGGER.info("Obteniendo CSRF de EQUINOX...")

    response = http_request(
        f"{EQUINOX_WEB}/api/auth/csrf"
    )

    csrf_data = json.loads(
        response.read().decode("utf-8")
    )

    csrf_token = csrf_data["csrfToken"]

    LOGGER.info("Iniciando sesión en EQUINOX...")

    login_data = {
        "email": EMAIL,
        "password": PASSWORD,
        "redirect": "false",
        "csrfToken": csrf_token,
        "callbackUrl": f"{EQUINOX_WEB}/",
        "json": "true",
    }

    response = http_request(
        f"{EQUINOX_WEB}/api/auth/callback/credentials",
        method="POST",
        data=login_data,
        headers={
            "Origin": EQUINOX_WEB,
            "Referer": f"{EQUINOX_WEB}/login",
        },
    )

    # El token que necesitamos se guarda como cookie raw-token.
    for cookie in OPENER.handlers[0].cookiejar:
        if cookie.name == "raw-token":
            TOKEN = cookie.value
            break

    if not TOKEN:
        raise RuntimeError(
            "Login correcto pero no se encontró la cookie raw-token."
        )

    LOGGER.info("Autenticación EQUINOX correcta.")


def get_realtime():
    if not TOKEN:
        login()

    url = f"{EQUINOX_API}/plants/{PLANT_ID}/realTime"

    try:
        response = http_request(
            url,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Platform-Referer": "EquinoxWeb",
            },
        )

        return json.loads(
            response.read().decode("utf-8")
        )

    except HTTPError as error:
        if error.code == 401:
            LOGGER.warning(
                "El token EQUINOX ha expirado. Renovando sesión..."
            )

            TOKEN_RESET()

            login()

            response = http_request(
                url,
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Platform-Referer": "EquinoxWeb",
                },
            )

            return json.loads(
                response.read().decode("utf-8")
            )

        raise


def TOKEN_RESET():
    global TOKEN
    TOKEN = None


def mqtt_connect():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"salicru_equinox_{PLANT_ID}",
    )

    if MQTT_USER:
        client.username_pw_set(
            MQTT_USER,
            MQTT_PASSWORD,
        )

    LOGGER.info(
        "Conectando a MQTT %s:%s",
        MQTT_HOST,
        MQTT_PORT,
    )

    client.connect(
        MQTT_HOST,
        MQTT_PORT,
        60,
    )

    client.loop_start()

    return client


def publish_discovery(client):
    device = {
        "identifiers": [f"salicru_equinox_{PLANT_ID}"],
        "name": "Salicru EQUINOX",
        "manufacturer": "Salicru",
        "model": "EQUINOX",
    }

    sensors = {
        "inverter_power": {
            "name": "Potencia inversor",
            "unit": "kW",
        },
        "daily_generation": {
            "name": "Generación diaria",
            "unit": "kWh",
        },
        "daily_consumption": {
            "name": "Consumo diario",
            "unit": "kWh",
        },
        "import_energy": {
            "name": "Energía importada",
            "unit": "kWh",
        },
        "export_energy": {
            "name": "Energía exportada",
            "unit": "kWh",
        },
        "self_consumption": {
            "name": "Autoconsumo",
            "unit": "kWh",
        },
        "grid_power": {
            "name": "Potencia red",
            "unit": "kW",
        },
        "alarm_count": {
            "name": "Número de alarmas",
            "unit": None,
        },
        "last_update": {
            "name": "Última actualización",
            "unit": None,
        },
    }

    for key, config in sensors.items():
        discovery_topic = (
            f"{MQTT_DISCOVERY_PREFIX}/sensor/"
            f"salicru_{PLANT_ID}/{key}/config"
        )

        payload = {
            "name": config["name"],
            "unique_id": f"salicru_{PLANT_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "availability_topic": AVAILABILITY_TOPIC,
            "device": device,
        }

        if config["unit"]:
            payload["unit_of_measurement"] = config["unit"]

        if key == "last_update":
            payload["device_class"] = "timestamp"
            payload["value_template"] = (
                "{{ value_json.last_update }}"
            )

        client.publish(
            discovery_topic,
            json.dumps(payload),
            retain=True,
        )

    # Sensor de alarmas en texto.
    discovery_topic = (
        f"{MQTT_DISCOVERY_PREFIX}/sensor/"
        f"salicru_{PLANT_ID}/alarms/config"
    )

    payload = {
        "name": "Alarmas inversor",
        "unique_id": f"salicru_{PLANT_ID}_alarms",
        "state_topic": STATE_TOPIC,
        "value_template": "{{ value_json.alarms }}",
        "availability_topic": AVAILABILITY_TOPIC,
        "device": device,
    }

    client.publish(
        discovery_topic,
        json.dumps(payload),
        retain=True,
    )

    # Sensor de comunicación con EQUINOX.
    discovery_topic = (
        f"{MQTT_DISCOVERY_PREFIX}/binary_sensor/"
        f"salicru_{PLANT_ID}/api_ok/config"
    )

    payload = {
        "name": "Comunicación EQUINOX",
        "unique_id": f"salicru_{PLANT_ID}_api_ok",
        "state_topic": STATE_TOPIC,
        "value_template": "{{ value_json.api_ok }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "connectivity",
        "availability_topic": AVAILABILITY_TOPIC,
        "device": device,
    }

    client.publish(
        discovery_topic,
        json.dumps(payload),
        retain=True,
    )


def extract_data(data):
    inverter_power = None

    if data.get("invertersProps"):
        inverter_power = data["invertersProps"][0].get(
            "outputPower"
        )

    alarms = data.get("inverterAlarms") or []

    if isinstance(alarms, list):
        alarm_text = ", ".join(str(x) for x in alarms)
        alarm_count = len(alarms)
    else:
        alarm_text = str(alarms)
        alarm_count = 0

    return {
        "inverter_power": inverter_power,
        "daily_generation": data.get("dailyGeneration"),
        "daily_consumption": data.get("dailyConsumption"),
        "import_energy": data.get("importEnergy"),
        "export_energy": data.get("exportEnergy"),
        "self_consumption": data.get("selfConsumption"),
        "grid_power": data.get("gridPower"),
        "alarm_count": alarm_count,
        "alarms": alarm_text,
        "last_update": time.strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        ),
        "api_ok": "ON",
    }


def publish_state(client, state):
    client.publish(
        STATE_TOPIC,
        json.dumps(state),
        retain=True,
    )

    client.publish(
        AVAILABILITY_TOPIC,
        "online",
        retain=True,
    )


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

        except Exception as error:
            LOGGER.error(
                "Error consultando EQUINOX: %s",
                error,
            )

            try:
                mqtt_client.publish(
                    AVAILABILITY_TOPIC,
                    "offline",
                    retain=True,
                )
            except Exception:
                pass

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
