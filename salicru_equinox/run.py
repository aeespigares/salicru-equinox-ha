import json
import logging
import os
import time
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request

import paho.mqtt.client as mqtt


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("salicru")


BASE_URL = "https://equinox.salicru.com"
API_URL = "https://api.equinox.salicru.com"

EMAIL = os.environ["SALICRU_EMAIL"]
PASSWORD = os.environ["SALICRU_PASSWORD"]
PLANT_ID = os.environ["PLANT_ID"]

POLL_INTERVAL = int(
    os.environ.get("POLL_INTERVAL", "900")
)

MQTT_HOST = os.environ.get(
    "MQTT_HOST",
    "core-mosquitto",
)

MQTT_PORT = int(
    os.environ.get("MQTT_PORT", "1883")
)

MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")

STATE_TOPIC = f"salicru/{PLANT_ID}/state"
AVAILABILITY_TOPIC = f"salicru/{PLANT_ID}/availability"

DISCOVERY_PREFIX = "homeassistant"

DEVICE_ID = f"salicru_equinox_{PLANT_ID}"


class SalicruClient:

    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.token = None

        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(
                self.cookies
            )
        )

    def request(
        self,
        url,
        method="GET",
        data=None,
        headers=None,
    ):
        request_headers = headers or {}

        req = urllib.request.Request(
            url,
            data=data,
            headers=request_headers,
            method=method,
        )

        return self.opener.open(
            req,
            timeout=30,
        )

    def login(self):

        log.info("Obteniendo CSRF token...")

        response = self.request(
            f"{BASE_URL}/api/auth/csrf"
        )

        csrf_data = json.loads(
            response.read().decode()
        )

        csrf_token = csrf_data["csrfToken"]

        log.info("Iniciando sesión en EQUINOX...")

        payload = urllib.parse.urlencode({
            "email": EMAIL,
            "password": PASSWORD,
            "redirect": "false",
            "csrfToken": csrf_token,
            "callbackUrl": f"{BASE_URL}/",
            "json": "false",
        }).encode()

        response = self.request(
            f"{BASE_URL}/api/auth/callback/credentials",
            method="POST",
            data=payload,
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded",
            },
        )

        log.info(
            "Respuesta de login: HTTP %s",
            response.status,
        )

        self.token = None

        for cookie in self.cookies:
            if cookie.name == "raw-token":
                self.token = cookie.value
                break

        if not self.token:
            raise RuntimeError(
                "Login realizado pero no se encontró raw-token"
            )

        log.info("Token EQUINOX obtenido correctamente")

    def get_realtime(self):

        if not self.token:
            self.login()

        url = (
            f"{API_URL}/plants/"
            f"{PLANT_ID}/realTime"
        )

        try:

            response = self.request(
                url,
                headers={
                    "Authorization":
                        f"Bearer {self.token}",
                    "Platform-Referer":
                        "EquinoxWeb",
                    "Content-Type":
                        "application/json",
                },
            )

            return json.loads(
                response.read().decode()
            )

        except urllib.error.HTTPError as error:

            if error.code == 401:

                log.warning(
                    "El token ha caducado. Renovando..."
                )

                self.token = None

                self.login()

                response = self.request(
                    url,
                    headers={
                        "Authorization":
                            f"Bearer {self.token}",
                        "Platform-Referer":
                            "EquinoxWeb",
                        "Content-Type":
                            "application/json",
                    },
                )

                return json.loads(
                    response.read().decode()
                )

            raise


def connect_mqtt():

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    if MQTT_USER:
        client.username_pw_set(
            MQTT_USER,
            MQTT_PASSWORD,
        )

    log.info(
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
        "identifiers": [DEVICE_ID],
        "name": "Salicru EQUINOX",
        "manufacturer": "Salicru",
        "model": "EQUINOX",
    }

    origin = {
        "name": "Salicru EQUINOX App",
        "sw_version": "1.0.0",
        "support_url": "https://equinox.salicru.com",
    }

    components = {}

    sensors = {
        "daily_generation": {
            "name": "Producción diaria",
            "unit": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
        },
        "daily_consumption": {
            "name": "Consumo diario",
            "unit": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
        },
        "import_energy": {
            "name": "Energía importada",
            "unit": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
        },
        "export_energy": {
            "name": "Energía exportada",
            "unit": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
        },
        "self_consumption": {
            "name": "Autoconsumo diario",
            "unit": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
        },
        "inverter_power": {
            "name": "Potencia inversor",
            "unit": "kW",
            "device_class": "power",
            "state_class": "measurement",
        },
        "power_generation": {
            "name": "Potencia generación",
            "unit": "kW",
            "device_class": "power",
            "state_class": "measurement",
        },
        "grid_power": {
            "name": "Potencia red",
            "unit": "kW",
            "device_class": "power",
            "state_class": "measurement",
        },
        "co2": {
            "name": "CO₂ evitado",
            "unit": "kg",
            "device_class": "weight",
            "state_class": "total_increasing",
        },
    }

    for key, config in sensors.items():

        component = {
            "p": "sensor",
            "name": config["name"],
            "unique_id": f"{DEVICE_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "value_template":
                f"{{{{ value_json.{key} }}}}",
            "device": device,
            "origin": origin,
        }

        if "unit" in config:
            component["unit_of_measurement"] = config["unit"]

        if "device_class" in config:
            component["device_class"] = config["device_class"]

        if "state_class" in config:
            component["state_class"] = config["state_class"]

        topic = (
            f"{DISCOVERY_PREFIX}/sensor/"
            f"{DEVICE_ID}/{key}/config"
        )

        client.publish(
            topic,
            json.dumps(component),
            retain=True,
        )

    log.info("MQTT Discovery publicado")


def publish_state(client, data):

    inverter_power = None

    inverters = data.get(
        "invertersProps",
        [],
    )

    if inverters:
        inverter_power = inverters[0].get(
            "outputPower"
        )

    state = {
        "daily_generation":
            data.get("dailyGeneration"),

        "daily_consumption":
            data.get("dailyConsumption"),

        "import_energy":
            data.get("importEnergy"),

        "export_energy":
            data.get("exportEnergy"),

        "self_consumption":
            data.get("selfConsumption"),

        "inverter_power":
            inverter_power,

        "power_generation":
            data.get("powerDailyGeneration"),

        "grid_power":
            data.get("gridPower"),

        "co2":
            data.get("co2"),
    }

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

    log.info(
        "Datos publicados: potencia inversor=%s kW",
        inverter_power,
    )


def main():

    log.info(
        "Iniciando Salicru EQUINOX para planta %s",
        PLANT_ID,
    )

    salicru = SalicruClient()

    mqtt_client = connect_mqtt()

    publish_discovery(mqtt_client)

    while True:

        try:

            data = salicru.get_realtime()

            publish_state(
                mqtt_client,
                data,
            )

        except Exception as error:

            log.exception(
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

            salicru.token = None

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
