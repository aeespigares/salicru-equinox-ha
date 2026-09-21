# Changelog

Todos los cambios relevantes de este proyecto se documentan en este archivo.

## [1.1.1]

### Añadido

* Nuevo sensor **Estado de planta**.
* El sensor obtiene directamente el campo `status` del recurso `/plants/{Plant ID}` de EQUINOX.
* Se muestran los estados proporcionados por EQUINOX sin interpretarlos ni modificarlos, por ejemplo `NORMAL`, `WARNING`, etc.
* Añadido el archivo `DOCS.md` para mostrar la documentación de la App desde Home Assistant.

### Mejorado

* Actualizada la documentación de la App.
* Actualizada la presentación de la App para enlazar con el repositorio de GitHub.
* Añadido enlace de apoyo al proyecto mediante Buy Me a Coffee.
* El intervalo mínimo de consulta a EQUINOX queda establecido en **60 segundos**.

## [1.1.0]

* Soporte para varias plantas EQUINOX en una misma App.
* Dispositivo independiente de Home Assistant para cada planta.
* Topics MQTT independientes por Plant ID.
* Soporte para varios inversores por planta.
* Potencia total de la planta calculada a partir de todos sus inversores.
* Sensores individuales de potencia por inversor.
* Sensor del número de inversores.
* Nuevo sensor **Planta conectada** para indicar el estado del dispositivo/gateway de comunicación de la planta.

## [1.0.4]

* Añadido el sensor de diagnóstico **Inversor conectado**.
* Consulta del estado de conectividad del dispositivo mediante la API de EQUINOX.
* Diferenciación entre la comunicación de la App con EQUINOX y el estado de conexión del dispositivo.

## [1.0.3]

* Primera versión funcional de la integración.
* Autenticación automática con EQUINOX.
* Gestión de sesión y renovación del token.
* Consulta periódica configurable.
* Integración con MQTT de Home Assistant.
* MQTT Discovery.
* Sensores de generación, consumo, autoconsumo, energía importada y exportada.
* Sensor de potencia del inversor.
* Sensor de potencia de red.
* Sensores de estado y alarmas.
* Sensor de última actualización.
