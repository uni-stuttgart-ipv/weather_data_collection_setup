import json
import time
import datetime
import logging
import paho.mqtt.client as mqtt

from sensor import read_all_sensors

MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "weather_sensor"
MQTT_CLIENT_ID = "weather_station_publisher"
DEVICE_MAC = "raspi_1" #inc count : raspi_1 and raspi_2 already exist
STATION_NAME = "weather_station_1" #inc count
COLLECTION_INTERVAL_SECONDS = 60

# MQTT QoS 1 = "at least once delivery" ie. broker will acknowledge receipt.
MQTT_QOS = 1

MQTT_CONNECT_MAX_RETRIES = 5
MQTT_CONNECT_RETRY_DELAY_SECONDS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("publisher")

def create_mqtt_client():
    client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to local MQTT broker (%s:%s)", MQTT_BROKER_HOST, MQTT_BROKER_PORT)
        else:
            logger.error("Failed to connect to MQTT broker, return code %s", rc)

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            logger.warning("Unexpected disconnect from MQTT broker (rc=%s). Will auto-reconnect.", rc)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    last_error = None
    for attempt in range(1, MQTT_CONNECT_MAX_RETRIES + 1):
        try:
            client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
            client.loop_start()
            return client
        except Exception as e:
            last_error = e
            logger.warning(
                "MQTT connect attempt %s/%s failed: %s. Retrying in %ss...",
                attempt, MQTT_CONNECT_MAX_RETRIES, e, MQTT_CONNECT_RETRY_DELAY_SECONDS,
            )
            time.sleep(MQTT_CONNECT_RETRY_DELAY_SECONDS)

    raise RuntimeError(f"Could not connect to MQTT broker after {MQTT_CONNECT_MAX_RETRIES} attempts: {last_error}")


def build_payload(sensor_data):
    """Wraps sensor readings dict into the combined JSON message format."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "timestamp": now_iso,
        "MAC": DEVICE_MAC,
        "Name": STATION_NAME,
        "Irr": sensor_data["Irr"],
        "PyroIrr": sensor_data["PyroIrr"],
        "AmbTemp": sensor_data["AmbTemp"],
        "AmbHmd": sensor_data["AmbHmd"],
    }

def main():
    logger.info("Starting weather station publisher (interval=%ss)", COLLECTION_INTERVAL_SECONDS)
    client = create_mqtt_client()

    try:
        while True:
            cycle_start = time.time()

            try:
                sensor_data = read_all_sensors()
                payload = build_payload(sensor_data)
                payload_json = json.dumps(payload)

                result = client.publish(MQTT_TOPIC, payload_json, qos=MQTT_QOS)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info("Published: %s", payload_json)
                else:
                    logger.error("Publish failed with rc=%s (payload: %s)", result.rc, payload_json)

            except Exception as e:
                logger.exception("Error during collection cycle: %s", e)

            elapsed = time.time() - cycle_start
            sleep_time = max(0, COLLECTION_INTERVAL_SECONDS - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Shutting down publisher (keyboard interrupt).")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()