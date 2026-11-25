import random
import time
import fcntl
try:
    import Adafruit_ADS1x15
except ImportError:
    Adafruit_ADS1x15 = None
    print("Adafruit_ADS1x15 not installed. Install with: pip install Adafruit-ADS1x15 --break-system-packages")

USE_FAKE_SENSORS = False

# GY-21 config 
GY21_I2C_BUS = 3         # I2C bus for GY-21 - need to physically configure this 
# go to terminal, type
# sudo nano /boot/firmware/config.txt
# dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=23,i2c_gpio_scl=24
# sudo reboot
# if gy21 connected then,
# i2c detect -y 3 : should show 0x40 
GY21_I2C_ADDR = 0x40     # GPIO pins: 23(SDA) & 24(SCL)
I2C_SLAVE = 0x0703       

# ADS1115 config          # GPIO pins: 02(SDA) & 03(SCL)
# i2c detect -y 1 : should show 0x48
ADS1115_I2C_ADDR = 0x48   # ADS1115 address
ADS1115_BUSNUM = 1        # I2C bus for ADS1115
ADS1115_GAIN = 2

ads_hardware_available = False
ads = None

if Adafruit_ADS1x15 is not None:
    try:
        ads = Adafruit_ADS1x15.ADS1115(address=ADS1115_I2C_ADDR, busnum=ADS1115_BUSNUM)
        ads.gain = ADS1115_GAIN
        ads.data_rate = 860
        ads_hardware_available = True
    except Exception as e:
        print(f"Failed to initialize ADS1115 at {hex(ADS1115_I2C_ADDR)} on bus {ADS1115_BUSNUM}: {e}")
        ads_hardware_available = False

# MAX31865 config (PT100 RTD, 4-wire, SPI)
MAX31865_RTD_NOMINAL = 100.0    # PT100
MAX31865_REF_RESISTOR = 430.0   # 430 ohm for PT100
MAX31865_WIRES = 4

rtd_hardware_available = False
rtd = None

try:
    import board
    import busio
    import digitalio
    import adafruit_max31865

    _spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
    _cs = digitalio.DigitalInOut(board.D5)
    rtd = adafruit_max31865.MAX31865(
        _spi, _cs,
        rtd_nominal=MAX31865_RTD_NOMINAL,
        ref_resistor=MAX31865_REF_RESISTOR,
        wires=MAX31865_WIRES,
    )
    rtd_hardware_available = True
except Exception as e:
    print(f"Failed to initialize MAX31865: {e}")
    rtd_hardware_available = False

# fake data generator just for test purpose 
def fake_irradiance():
    return round(random.uniform(0, 1000), 2)

def fake_apogee_irradiance():
    return round(random.uniform(0, 1000), 2)

def fake_temperature():
    return round(random.uniform(15, 35), 2)

def fake_rtd_temperature():
    return round(random.uniform(15, 35), 2)

def fake_humidity():
    return round(random.uniform(20, 90), 2)

def read_all_sensors_fake():
    return {
        "Irr": fake_irradiance(),
        "PyroIrr": fake_apogee_irradiance(),
        "AmbTemp": fake_temperature(),
        "PT100": fake_rtd_temperature(),
        "AmbHmd": fake_humidity(),
    }

def read_gy21(busnum=GY21_I2C_BUS, addr=GY21_I2C_ADDR):
    try:
        with open(f"/dev/i2c-{busnum}", "rb+", buffering=0) as f:
            fcntl.ioctl(f, I2C_SLAVE, addr)

            # Trigger temperature measurement (hold master mode, command 0xF3)
            f.write(bytes([0xF3]))
            time.sleep(0.085)
            temp_data = f.read(2)
            if len(temp_data) != 2:
                raise IOError(f"Expected 2 bytes for temp, got {len(temp_data)}")
            raw_temp = (temp_data[0] << 8) + temp_data[1]
            temp_c = -46.85 + 175.72 * raw_temp / 65536.0

            # Trigger humidity measurement (hold master mode, command 0xF5)
            f.write(bytes([0xF5]))
            time.sleep(0.029)
            hum_data = f.read(2)
            if len(hum_data) != 2:
                raise IOError(f"Expected 2 bytes for humidity, got {len(hum_data)}")
            raw_humidity = (hum_data[0] << 8) + hum_data[1]
            humidity = -6.0 + 125.0 * raw_humidity / 65536.0

            temp_c = round(temp_c, 2)
            humidity = round(humidity, 2)

            return temp_c, humidity

    except Exception as e:
        print(f"GY-21 read error (bus {busnum}, addr 0x{addr:02X}): {e}")
        return None, None

def measure_irradiance():
    if not ads_hardware_available:
        return None
    try:
        adc_value = ads.read_adc(0, gain=ADS1115_GAIN) # channel A0
        value = round(adc_value * 0.0625, 2)
        return value
    except Exception as e:
        print(f"Irradiance (ADS1115 ch0) read error: {e}")
        return None

def measure_apogee_irradiance():
    if not ads_hardware_available:
        return None
    try:
        adc_value = ads.read_adc(1, gain=8) # channel A1
        value = round(adc_value * (0.512 / 32767.0) * 5000.0, 2)
        return value
    except Exception as e:
        print(f"Pyranometer (ADS1115 ch1) read error: {e}")
        return None

def measure_rtd_temperature():
    if not rtd_hardware_available:
        return None
    try:
        temp = rtd.temperature
        fault = rtd.fault   # tuple of 6 booleans, all False when healthy
        if any(fault):
            print(f"MAX31865 fault detected: {fault}")
            rtd.clear_faults()
            return None
        return round(temp, 2)
    except Exception as e:
        print(f"MAX31865 read error: {e}")
        return None

def read_all_sensors_real():
    temp_c, humidity = read_gy21()
    return {
        "Irr": measure_irradiance(),
        "PyroIrr": measure_apogee_irradiance(),
        "AmbTemp": temp_c,
        "PT100": measure_rtd_temperature(),
        "AmbHmd": humidity,
    }

def read_all_sensors():
    if USE_FAKE_SENSORS:
        return read_all_sensors_fake()
    else:
        return read_all_sensors_real()

if __name__ == "__main__":
    print("Reading sensors (fake mode)" if USE_FAKE_SENSORS else "Reading sensors (real mode)")
    data = read_all_sensors()
    for key, value in data.items():
        print(f"  {key}: {value}")