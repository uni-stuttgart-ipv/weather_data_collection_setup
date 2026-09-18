# Weather Station
Raspberry Pi-based weather data collection hardware and software setup.

## Hardware
1. Make the connections as shown in the image below.
   <img width="6780" height="4540" alt="weather_collector" src="https://github.com/user-attachments/assets/0c1e7e15-d4bb-4adb-ac2e-68c812e77d17" />

2. If you wish to connect the Raspi to your laptop over SSH:
   ```bash
   ssh <username>@<ip_address>
   ```

## Software

3. Open `sensor.py` and follow the steps to set Bus 3.

4. Copy both code files from laptop to Raspi:
   ```bash
   scp sensor.py publisher.py raspi@<new-pi-ip>:~/weather_station/
   ```

5. Edit `publisher.py` — station identity. Change only these two lines so this station is uniquely identified in InfluxDB:
   ```python
   DEVICE_MAC = "raspi_2"              # unique per station
   STATION_NAME = "weather_station_2"  # unique per station
   ```

6. Set up Python environment:
   ```bash
   cd ~/weather_station
   python3 -m venv venv
   source venv/bin/activate
   pip install paho-mqtt Adafruit-ADS1x15 RPi.GPIO --break-system-packages
   ```

7. Test sensors are running:
   ```bash
   source venv/bin/activate
   python3 sensor.py
   ```
   Confirm `Irr`, `PyroIrr`, `AmbTemp`, `AmbHmd` all return plausible numbers, not stuck at `None`.

8. Verify I2C addresses before trusting readings:
   ```bash
   sudo apt install -y i2c-tools   # if not already installed
   i2cdetect -y 1   # expect ADS1115's address (e.g. 48, 4a, or 4b)
   i2cdetect -y 3   # expect 40 (GY-21)
   ```
   If the ADS1115 address shown doesn't match `ADS1115_I2C_ADDR` in `sensor.py`, update the code to match.

9. Get Mosquitto installed and running:
   ```bash
   sudo apt install -y mosquitto mosquitto-clients
   sudo systemctl status mosquitto
   ```

10. Test the publisher manually.

    Terminal A:
    ```bash
    mosquitto_sub -h localhost -t weather_sensor -v
    ```

    Terminal B:
    ```bash
    python3 publisher.py
    ```
    Confirm the JSON appearing in Terminal A shows this station's correct `MAC` and `Name`. Ctrl+C both once confirmed.

11. Set up `publisher.py` as a systemd service:
    ```bash
    sudo nano /etc/systemd/system/weather-publisher.service
    ```
    ```ini
    [Unit]
    Description=Weather Station Sensor Publisher
    After=network-online.target mosquitto.service
    Wants=network-online.target

    [Service]
    Type=simple
    User=raspi
    WorkingDirectory=/home/raspi/weather_station
    ExecStart=/home/raspi/weather_station/venv/bin/python3 /home/raspi/weather_station/publisher.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    ```
    > Adjust `User` and paths to match this Pi's actual username/home directory if different.

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable weather-publisher
    sudo systemctl start weather-publisher
    sudo systemctl status weather-publisher
    ```

## InfluxDB / Telegraf

12. Install Telegraf:
    ```bash
    curl -s https://repos.influxdata.com/influxdata-archive.key | sudo gpg --dearmor -o /usr/share/keyrings/influxdata-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/influxdata-archive-keyring.gpg] https://repos.influxdata.com/debian stable main" | sudo tee /etc/apt/sources.list.d/influxdata.list
    sudo apt update
    sudo apt install -y telegraf
    ```

13. Configure Telegraf (paste directly at the shell prompt, not into an editor):
    ```bash
    sudo tee /etc/telegraf/telegraf.conf > /dev/null << 'EOF'
    [agent]
      interval = "60s"
      round_interval = true
      metric_batch_size = 1000
      metric_buffer_limit = 100000
      flush_interval = "10s"
      flush_jitter = "0s"

    [[inputs.mqtt_consumer]]
      servers = ["tcp://localhost:1883"]
      topics = ["weather_sensor"]
      data_format = "json"
      json_time_key = "timestamp"
      json_time_format = "2006-01-02T15:04:05Z"
      name_override = "weather_station"
      tag_keys = ["MAC", "Name"]

      [[inputs.mqtt_consumer.topic_parsing]]
        topic = "weather_sensor"
        tags = "topic"

    [[outputs.influxdb_v2]]
      urls = ["URL"]
      token = "YOUR_TOKEN_HERE"
      organization = "ORG"
      bucket = "YOUR_BUCKET_NAME_HERE"
      timeout = "10s"
    EOF
    ```
    Fill in the real token/bucket before running. This config is **shared across all stations** — no per-station changes needed here, since `tag_keys = ["MAC", "Name"]` already distinguishes each station using the values set in step 5.

14. Test the config:
    ```bash
    sudo telegraf --config /etc/telegraf/telegraf.conf --test
    ```

15. Enable Telegraf as a service:
    ```bash
    sudo systemctl enable telegraf
    sudo systemctl start telegraf
    sudo systemctl status telegraf
    ```

## Verification

16. Watch both services' logs to confirm end-to-end flow:
    ```bash
    sudo journalctl -u weather-publisher -f
    sudo journalctl -u telegraf -f
    ```
    Confirm publisher logs show `Published: {...}` every ~60s, and Telegraf shows no subscription or output errors.

17. Check InfluxDB directly — filter the bucket by this station's `MAC` tag, confirm `Irr`, `PyroIrr`, `AmbTemp`, `AmbHmd` fields are arriving with recent timestamps.

18. Reboot test:
    ```bash
    sudo reboot
    ```
    Wait ~1 minute, SSH back in, confirm both services started automatically:
    ```bash
    sudo systemctl status weather-publisher
    sudo systemctl status telegraf
    ```
    Confirm data kept flowing through the reboot with no manual intervention.
