# Salicru EQUINOX para Home Assistant

<p align="left">
  <img src="logo.png" alt="Salicru EQUINOX" width="600">
</p>

App para [Home Assistant](https://www.home-assistant.io/) que permite integrar inversores Salicru conectados a la plataforma [EQUINOX](https://equinox.salicru.com/).

La aplicación consulta periódicamente los datos de la instalación y el estado de conectividad del dispositivo a través de la plataforma EQUINOX y los publica mediante MQTT Discovery, de forma que Home Assistant crea automáticamente el dispositivo y sus sensores.

> **Estado del proyecto:** funcional y en desarrollo.

---

## ✨ Características

* Integración con la plataforma web Salicru EQUINOX.
* Autenticación automática con la cuenta de EQUINOX.
* Renovación automática de la sesión cuando expira el token de acceso.
* Consulta periódica de los datos de la planta.
* Consulta del estado de conectividad del dispositivo de la planta.
* Publicación mediante MQTT.
* MQTT Discovery para crear automáticamente el dispositivo en Home Assistant.
* No requiere configurar manualmente los sensores MQTT.
* Configuración desde la interfaz de Home Assistant.
* Intervalo de consulta configurable.
* Compatible con Home Assistant OS y su sistema de Apps.

---

## 📊 Sensores disponibles

La aplicación crea automáticamente un dispositivo llamado:

**Salicru EQUINOX**

Actualmente se crean los siguientes sensores:

| Sensor               | Unidad | Descripción                                                                            |
| -------------------- | ------ | -------------------------------------------------------------------------------------- |
| Potencia inversor    | kW     | Potencia instantánea producida por el inversor                                         |
| Generación diaria    | kWh    | Energía generada durante el día actual                                                 |
| Consumo diario       | kWh    | Energía consumida por la instalación durante el día actual                             |
| Energía importada    | kWh    | Energía tomada de la red durante el día actual                                         |
| Energía exportada    | kWh    | Energía vertida a la red durante el día actual                                         |
| Autoconsumo          | kWh    | Energía solar producida y consumida directamente por la instalación, sin vertido a red |
| Potencia red         | kW     | Potencia instantánea intercambiada con la red                                          |
| Número de alarmas    | —      | Número de alarmas comunicadas por el inversor                                          |
| Alarmas inversor     | —      | Información de las alarmas comunicadas por EQUINOX                                     |
| Comunicación EQUINOX | —      | Estado de comunicación entre la App y la plataforma EQUINOX                            |
| Inversor conectado   | —      | Estado de conectividad del dispositivo según EQUINOX                                   |
| Última actualización | —      | Fecha y hora de la última consulta                                                     |

El sensor **Inversor conectado** es un `binary_sensor` de diagnóstico. Sus estados representan:

* **ON:** EQUINOX informa que el dispositivo está conectado (`CONNECTED`).
* **OFF:** EQUINOX informa que el dispositivo está desconectado (`DISCONNECTED`).

### Potencia de red

El signo de **Potencia red** se interpreta de la siguiente manera:

* **Valor positivo:** la instalación está tomando energía de la red.
* **Valor negativo:** la instalación está vertiendo energía a la red.
* **0 kW:** no existe intercambio significativo con la red.

### Autoconsumo

El sensor **Autoconsumo** representa la energía producida por las placas solares que es aprovechada directamente por la instalación eléctrica, sin ser vertida a la red.

---

## 🔄 Frecuencia de actualización

Por defecto, la aplicación consulta EQUINOX cada:

**900 segundos (15 minutos)**

Este valor se puede modificar desde la configuración de la aplicación.

Por ejemplo:

```yaml
poll_interval: 900
```

El valor está expresado en segundos.

En cada ciclo, la aplicación consulta tanto los datos de tiempo real de la planta como la información de estado del dispositivo.

---

## 🏠 Requisitos

Se necesita:

* Home Assistant OS con soporte para Apps.
* MQTT configurado en Home Assistant.
* Una cuenta de usuario en EQUINOX.
* Una instalación Salicru visible desde la plataforma EQUINOX.
* El identificador (`Plant ID`) de la instalación.

La aplicación utiliza el servicio MQTT proporcionado por Home Assistant y no necesita configurar manualmente la dirección del broker, puerto ni credenciales MQTT.

---

## 📦 Instalación

### 1. Añadir el repositorio

En Home Assistant:

**Ajustes → Aplicaciones → Tienda de aplicaciones → ⋮ → Repositorios**

Añade:

```text
https://github.com/aeespigares/salicru-equinox-ha
```

El repositorio contiene una App de Home Assistant llamada:

**Salicru EQUINOX**

### 2. Instalar la App

Busca:

**Salicru EQUINOX**

e instálala.

### 3. Configurar

Antes de iniciar la aplicación, configura:

| Opción        | Descripción                                |
| ------------- | ------------------------------------------ |
| Email         | Dirección de correo de la cuenta EQUINOX   |
| Password      | Contraseña de la cuenta EQUINOX            |
| Plant ID      | Identificador de la instalación en EQUINOX |
| Poll interval | Intervalo de consulta en segundos          |

Ejemplo:

```text
Email: usuario@example.com
Password: ********
Plant ID: 365
Poll interval: 900
```

> **Importante:** no publiques nunca tu contraseña, tokens de acceso, cookies de sesión ni otros datos de autenticación en GitHub.

---

## 🔐 Autenticación

La aplicación utiliza el mismo mecanismo de autenticación empleado por la plataforma web EQUINOX.

El proceso es:

1. Solicita un token CSRF.
2. Inicia sesión con el usuario y contraseña configurados.
3. Obtiene el token de sesión proporcionado por EQUINOX.
4. Utiliza ese token para consultar los datos de la planta y su estado.
5. Si el token expira, vuelve a iniciar sesión automáticamente.

Las credenciales se configuran directamente en Home Assistant y no forman parte del código fuente del repositorio.

---

## 🔌 Comunicación con EQUINOX

La aplicación utiliza la plataforma web de Salicru EQUINOX para obtener los datos de la instalación.

Las consultas se realizan contra la API utilizada por la propia plataforma EQUINOX.

Actualmente se consultan principalmente dos recursos:

* `/plants/{Plant ID}/realTime` para obtener los datos de producción, consumo, energía y potencia.
* `/plants/{Plant ID}` para obtener información de la planta y el estado de conectividad de sus dispositivos.

La información de conectividad se obtiene del campo `status` del dispositivo comunicado por EQUINOX. Los estados utilizados actualmente son:

```text
CONNECTED
DISCONNECTED
```

La aplicación convierte estos estados en el sensor de Home Assistant **Inversor conectado**:

```text
CONNECTED     → ON
DISCONNECTED  → OFF
```

La aplicación no se comunica directamente con el inversor mediante una conexión local. Los datos se obtienen a través de la plataforma EQUINOX.

### Comunicación EQUINOX frente a Inversor conectado

Son dos conceptos diferentes y ambos se mantienen en la integración:

**Comunicación EQUINOX**

Indica si la aplicación puede comunicarse correctamente con la API de EQUINOX.

**Inversor conectado**

Indica el estado de conectividad que EQUINOX informa para el dispositivo de la instalación.

Por ejemplo, es posible que:

```text
Comunicación EQUINOX: ON
Inversor conectado: OFF
```

En ese caso, la App puede comunicarse correctamente con SALICRU, pero EQUINOX informa de que el dispositivo de la instalación está desconectado.

---

## 📡 Comunicación MQTT

La aplicación utiliza el servicio MQTT proporcionado por Home Assistant.

No es necesario indicar manualmente:

* dirección del broker;
* puerto;
* usuario MQTT;
* contraseña MQTT.

La aplicación solicita el servicio MQTT de Home Assistant y obtiene automáticamente los parámetros necesarios para conectarse.

Los datos se publican mediante **MQTT Discovery**, por lo que Home Assistant crea automáticamente el dispositivo y sus entidades.

---

## 🧩 Arquitectura

El funcionamiento general es:

```text
┌──────────────────────┐
│   Inversor Salicru   │
└──────────┬───────────┘
           │
           │ Datos de instalación
           ▼
┌──────────────────────┐
│   EQUINOX Salicru    │
│    Plataforma web    │
└──────────┬───────────┘
           │
           │ API
           ▼
┌──────────────────────┐
│ App Salicru EQUINOX  │
│   Home Assistant     │
└──────────┬───────────┘
           │
           │ MQTT
           ▼
┌──────────────────────┐
│    MQTT Broker       │
│   Home Assistant     │
└──────────┬───────────┘
           │
           │ MQTT Discovery
           ▼
┌──────────────────────┐
│ Dispositivo Salicru  │
│     + sensores       │
└──────────────────────┘
```

La App obtiene de EQUINOX tanto los datos de funcionamiento de la instalación como la información necesaria para determinar el estado de conectividad del dispositivo.

---

## ⏱️ Funcionamiento periódico

La aplicación permanece ejecutándose en Home Assistant y realiza consultas a EQUINOX según el intervalo configurado.

Con la configuración predeterminada:

```text
900 segundos = 15 minutos
```

En cada ciclo:

1. Comprueba la sesión de EQUINOX.
2. Si es necesario, vuelve a autenticarse.
3. Consulta los datos de tiempo real de la planta.
4. Consulta la información y estado del dispositivo de la planta.
5. Procesa los valores recibidos.
6. Publica los estados mediante MQTT.
7. Espera hasta el siguiente ciclo.

La aplicación no realiza consultas continuas al inversor ni mantiene una conexión permanente con EQUINOX.

---

## 🔄 Gestión de la sesión

La plataforma EQUINOX utiliza tokens de sesión con una duración limitada.

La aplicación gestiona esta situación automáticamente.

Si una consulta devuelve un error de autenticación:

1. Se considera que la sesión actual ya no es válida.
2. Se vuelve a solicitar el CSRF.
3. Se inicia sesión nuevamente.
4. Se obtiene un nuevo token.
5. Se repite la consulta.

De esta forma, la aplicación puede permanecer ejecutándose durante largos periodos sin que el usuario tenga que volver a introducir las credenciales.

---

## 📈 Datos diarios

Los siguientes sensores representan valores correspondientes al día actual proporcionados por EQUINOX:

* Generación diaria
* Consumo diario
* Energía importada
* Energía exportada
* Autoconsumo

Estos valores son datos diarios y pueden reiniciarse al comenzar un nuevo día.

---

## ⚠️ Alarmas

La aplicación proporciona dos sensores relacionados con las alarmas:

### Número de alarmas

Indica el número de alarmas comunicadas por EQUINOX.

Por ejemplo:

```text
0
```

significa que no hay ninguna alarma comunicada.

### Alarmas inversor

Muestra la información de las alarmas proporcionada por EQUINOX.

Cuando no existen alarmas, el sensor puede aparecer sin valor.

---

## 📡 Estado de comunicación

Existen dos sensores relacionados con la comunicación:

### Comunicación EQUINOX

Permite comprobar si la aplicación está pudiendo comunicarse correctamente con la plataforma EQUINOX.

El objetivo es proporcionar una indicación sencilla del estado de comunicación sin necesidad de consultar los registros de la aplicación.

### Inversor conectado

Indica el estado de conectividad del dispositivo según la información proporcionada por EQUINOX.

Sus estados son:

```text
ON  → EQUINOX informa CONNECTED
OFF → EQUINOX informa DISCONNECTED
```

Este sensor permite distinguir entre un problema de comunicación de Home Assistant con EQUINOX y un problema de conectividad del propio dispositivo de la instalación.

---

## 🕐 Última actualización

El sensor **Última actualización** indica cuándo se realizó la última consulta correcta a EQUINOX.

Esto permite comprobar rápidamente desde Home Assistant si los datos que se muestran son recientes.

---

## ⚠️ Consideraciones y limitaciones

### Dependencia de EQUINOX

Esta integración depende de la plataforma EQUINOX de Salicru.

Si Salicru modifica:

* el sistema de autenticación;
* los endpoints de la API;
* el formato de las respuestas;
* los nombres de los campos;
* los mecanismos de sesión;

la aplicación puede dejar de funcionar hasta que sea adaptada.

### Dependencia de Internet

La aplicación necesita acceso a Internet para comunicarse con la plataforma EQUINOX.

Si Home Assistant pierde el acceso a Internet, no será posible obtener nuevos datos desde EQUINOX.

### Estado del dispositivo

El sensor **Inversor conectado** depende de la información de estado proporcionada por EQUINOX.

Que la aplicación pueda consultar correctamente la API no significa necesariamente que el dispositivo de la instalación esté conectado.

### Datos proporcionados por EQUINOX

Los valores mostrados en Home Assistant proceden de los datos proporcionados por la plataforma EQUINOX.

La aplicación no calcula los valores principales de producción, consumo o intercambio con la red a partir de datos eléctricos locales.

---

## 🛠️ Solución de problemas

### La App no arranca

Comprueba los registros de la aplicación:

**Ajustes → Aplicaciones → Salicru EQUINOX → Registro**

Comprueba especialmente:

* que el usuario y contraseña de EQUINOX sean correctos;
* que el `Plant ID` sea correcto;
* que MQTT esté funcionando.

### Error de autenticación EQUINOX

Si aparece un error durante:

```text
Obteniendo CSRF de EQUINOX...
Iniciando sesión en EQUINOX...
```

comprueba las credenciales de la cuenta EQUINOX.

No compartas contraseñas ni tokens al solicitar ayuda.

### MQTT no funciona

Comprueba que la integración MQTT de Home Assistant esté configurada y funcionando.

La aplicación necesita el servicio MQTT de Home Assistant.

### No aparecen los sensores

Comprueba que:

1. La aplicación está ejecutándose.
2. La conexión con EQUINOX es correcta.
3. MQTT está funcionando.
4. El dispositivo **Salicru EQUINOX** aparece en la integración MQTT.

### El sensor "Inversor conectado" está en OFF

Comprueba el estado que informa EQUINOX para el dispositivo de la instalación.

Si **Comunicación EQUINOX** está en `ON` y **Inversor conectado** está en `OFF`, la aplicación está pudiendo comunicarse correctamente con SALICRU, pero EQUINOX informa de que el dispositivo está desconectado.

### Los datos no se actualizan

Comprueba:

1. El registro de la aplicación.
2. El sensor **Última actualización**.
3. Que la aplicación siga ejecutándose.
4. Que Home Assistant tenga conexión a Internet.
5. Que EQUINOX esté disponible.
6. El estado de **Comunicación EQUINOX**.
7. El estado de **Inversor conectado**.

---

## 🧪 Desarrollo

Estructura actual del repositorio:

```text
salicru-equinox-ha/
├── repository.yaml
├── README.md
└── salicru_equinox/
    ├── config.yaml
    ├── Dockerfile
    ├── requirements.txt
    ├── run.sh
    └── run.py
```

### `config.yaml`

Define la configuración de la App, sus opciones y la dependencia del servicio MQTT de Home Assistant.

### `run.py`

Implementa:

* autenticación con EQUINOX;
* gestión del token;
* consulta de datos de tiempo real;
* consulta del estado de la planta;
* extracción de los valores;
* extracción del estado de conectividad del dispositivo;
* conexión MQTT;
* MQTT Discovery;
* publicación de estados.

### `run.sh`

Inicializa la aplicación y obtiene la configuración del servicio MQTT proporcionado por Home Assistant.

### `Dockerfile`

Define la imagen utilizada por la App.

### `requirements.txt`

Contiene las dependencias Python utilizadas por el proyecto.

---

## 🤝 Contribuciones

Las contribuciones, correcciones y mejoras son bienvenidas.

Si encuentras un problema:

1. Comprueba primero los registros de la aplicación.
2. Abre una incidencia describiendo el problema.
3. Indica, si es posible, la versión de Home Assistant y de la App.
4. No incluyas contraseñas, cookies, tokens JWT ni otros datos privados.

Si propones cambios, intenta mantener la compatibilidad con las versiones actuales de Home Assistant y con el funcionamiento de la plataforma EQUINOX.

---

## 📝 Historial de versiones

### 1.0.4

- Añadido el sensor de diagnóstico **Inversor conectado**.
- Consulta del estado de conectividad del dispositivo mediante la API de EQUINOX.
- Diferenciación entre la comunicación de la App con EQUINOX y el estado de conexión del dispositivo.
- El sensor **Inversor conectado** muestra:
  - `ON` cuando EQUINOX informa `CONNECTED`.
  - `OFF` cuando EQUINOX informa `DISCONNECTED`.

### 1.0.3

- Primera versión funcional de la integración.
- Autenticación automática con EQUINOX.
- Gestión de sesión y renovación del token.
- Consulta periódica configurable.
- Integración con MQTT de Home Assistant.
- MQTT Discovery.
- Creación automática del dispositivo **Salicru EQUINOX**.
- Sensores de generación, consumo, autoconsumo, energía importada y exportada.
- Sensor de potencia del inversor.
- Sensor de potencia de red.
- Sensores de estado y alarmas.
- Sensor de última actualización.

---

## 📄 Licencia

Este proyecto se proporciona tal cual para su uso con Home Assistant.

No está afiliado, patrocinado ni mantenido oficialmente por Salicru.

**Salicru** y **EQUINOX** son marcas y productos de sus respectivos propietarios.
