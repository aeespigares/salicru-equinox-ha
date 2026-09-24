# Salicru EQUINOX para Home Assistant

[Home Assistant](https://www.home-assistant.io/) · [Repositorio GitHub](https://github.com/aeespigares/salicru-equinox-ha) 
<a href="https://www.buymeacoffee.com/aeespigaresdesarrollo" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" style="height: 40px !important;width: 138px !important; max-width: 30%;"></a> 

<p align="left">
  <img
    src="https://raw.githubusercontent.com/aeespigares/salicru-equinox-ha/main/salicru_equinox/logo.png"
    alt="Salicru EQUINOX"
    width="600"
    loading="lazy"
  >
</p>

App para [Home Assistant](https://www.home-assistant.io/) que permite integrar inversores Salicru conectados a la plataforma [EQUINOX](https://equinox.salicru.com/).

La aplicación consulta periódicamente los datos de una o varias instalaciones a través de la plataforma EQUINOX y los publica mediante MQTT Discovery, de forma que Home Assistant crea automáticamente un dispositivo por planta y sus sensores.

> **Estado del proyecto:** funcional y en desarrollo.
> **Versión actual:** 1.1.8
>
> ☕ Si esta App te resulta útil y quieres apoyar su desarrollo y mantenimiento, puedes invitarme a un café en [Buy Me a Coffee](https://buymeacoffee.com/aeespigaresdesarrollo). ¡Gracias por apoyar el proyecto!

---

## ✨ Características

- Integración con la plataforma web Salicru EQUINOX.
- Autenticación automática con la cuenta de EQUINOX.
- Renovación automática de la sesión cuando expira el token de acceso.
- Consulta periódica de los datos de la planta.
- Publicación mediante MQTT.
- MQTT Discovery para crear automáticamente un dispositivo por planta en Home Assistant.
- No requiere configurar manualmente los sensores MQTT.
- Configuración desde la interfaz de Home Assistant.
- Intervalo de consulta configurable, con un mínimo de 60 segundos.
- Monitorización de varias plantas desde una sola App.
- Sensor individual de potencia para cada inversor.
- Sensor de estado de planta con el valor proporcionado por EQUINOX.
- Compatible con Home Assistant OS y su sistema de Apps.
