# runs once to log temperature and store it into db
import adafruit_dht
import board
import os
import requests
import time
import paho.mqtt.client as mqtt
from datetime import datetime
from signal import signal, SIGTERM, SIGHUP, pause
from smbus2 import SMBus

from dotenv import load_dotenv
from sqlalchemy import Column, Integer, Float, DateTime, create_engine, inspect
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# SETTINGS
Base = declarative_base()
DB_LOCATION = 'weather.sqlite'
TABLE_NAME = 'weather'
GPIO_PIN = 17
load_dotenv()
lat = os.getenv('my_lat')
lon = os.getenv('my_lon')
api_key = os.getenv('my_api')
MQTT_BROKER = os.getenv('mqtt_broker')
MQTT_USERNAME = os.getenv('mqtt_user')
MQTT_PASSWORD = os.getenv('mqtt_password')


class Weather(Base):
    __tablename__ = TABLE_NAME
    id = Column(Integer, primary_key=True)
    time = Column(DateTime, default=datetime.now())
    outdoor_temp = Column(Float)
    outdoor_humidity = Column(Float)
    indoor_temp = Column(Float)
    indoor_humidity = Column(Float)

    def as_dict(self):
        return {'t': time.mktime(self.time.timetuple()), 'a': self.outdoor_temp, 'b': self.outdoor_humidity,
                'c': self.indoor_temp, 'd': self.indoor_humidity}


def get_outdoor_readings():
    query_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    try:
        r = requests.get(query_url)
        online_data = r.json()['main']
        temp = online_data['temp']
        humid = online_data['humidity']
    except Exception as e:
        import traceback
        traceback.print_exc()
        temp = None
        humid = None
    return temp, humid

def get_indoor_readings():
    dht = None
    try:
        # BCM 17 -> board.D17
        dht = adafruit_dht.DHT22(board.D17)  # change to DHT11(...) if needed

        # Similar spirit to Adafruit_DHT.read_retry: retry transient failures
        retries = 5
        delay_s = 2

        last_exc = None
        for _ in range(retries):
            try:
                temp = dht.temperature
                humid = dht.humidity

                # Sometimes returns None; treat as failed read
                if temp is None or humid is None:
                    raise RuntimeError("DHT returned None")

                return round(temp, 2), round(humid, 2)

            except RuntimeError as e:
                # Common DHT transient read error; retry
                last_exc = e
                time.sleep(delay_s)

        # If all retries failed, fall through
        if last_exc:
            raise last_exc

    except Exception:
        import traceback
        traceback.print_exc()

    finally:
        # Important: release GPIO resources cleanly
        try:
            if dht is not None:
                dht.exit()
        except Exception:
            pass

    return None, None


def safe_exit(signum, frame):
    exit(1)


def read_ads7830(input):
    bus.write_byte(0x4b, ads7830_commands[input])
    return bus.read_byte(0x4b)

def calculate_slope_intercept(x, y):
    """ helper function for generating linear regression"""
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xx = sum(x_i ** 2 for x_i in x)
    sum_xy = sum(x_i * y_i for x_i, y_i in zip(x, y))
    m = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x ** 2)
    b = (sum_y * sum_xx - sum_x * sum_xy) / (n * sum_xx - sum_x ** 2)
    return m, b

def predict_current_values(data_points):
    # Ensure there are at least 2 data points to calculate the regression
    if len(data_points) < 2:
        raise ValueError("At least two data points are required")

    # Prepare data for linear regression
    time_data = list(range(len(data_points)))
    temp_data = [x.indoor_temp for x in data_points]
    humidity_data = [x.indoor_humidity for x in data_points]

    # Calculate slope and intercept for temperature and humidity
    temp_m, temp_b = calculate_slope_intercept(time_data, temp_data)
    humidity_m, humidity_b = calculate_slope_intercept(time_data, humidity_data)

    # Predict the current temperature and humidity
    # Assuming the next time point is at len(data_points) (i.e., one step beyond the last data point)
    current_time = len(data_points)
    predicted_temp = temp_m * current_time + temp_b
    predicted_humidity = humidity_m * current_time + humidity_b

    # Limit values to reasonable ranges
    predicted_temp = max(5, min(40, predicted_temp))
    predicted_humidity = max(0, min(100, predicted_humidity))

    return predicted_temp, predicted_humidity


if __name__ == '__main__':
    signal(SIGTERM, safe_exit)
    signal(SIGHUP, safe_exit)
    engine = create_engine(f'sqlite:///{DB_LOCATION}')
    insp = inspect(engine)
    if not insp.get_table_names():  # If table don't exist, Create one.
        print("No db found, creating a new one")
        Base.metadata.create_all(bind=engine)

    bus = SMBus(1)
    ads7830_commands = (0x84, 0xc4, 0x94, 0xd4, 0xa4, 0xe4, 0xb4, 0xf4)
    # get light info
    light = read_ads7830(0)

    # get readings
    o_t, o_h = get_outdoor_readings()
    i_t, i_h = get_indoor_readings()

    raw_i_t, raw_i_h = i_t, i_h  # store raw indoor readings for logging

    # store readings
    Session = sessionmaker(bind=engine)
    session = Session()

    # calibrate indoor temp in case of error
    # get last 10 entries from db
    avg_len = 10
    data_points = session.query(Weather).order_by(Weather.time.desc()).limit(avg_len).all()

    if not data_points:  # Handle empty database
        avg_i_t, avg_i_h = i_t, i_h  # Use current readings as default
        p_i_t, p_i_h = i_t, i_h
    else:
        # get average temp and humidity
        avg_i_t = sum([x.indoor_temp for x in data_points]) / len(data_points)
        avg_i_h = sum([x.indoor_humidity for x in data_points]) / len(data_points)
        try:
            p_i_t, p_i_h = predict_current_values(data_points)
        except:
            p_i_t, p_i_h = avg_i_t, avg_i_h


    print(i_t, avg_i_t)
    # if current temp is more than 5 degrees off,use predicted value
    if abs(i_t - avg_i_t) > 5:
        i_t = p_i_t

    # if current humidity is more than 10% off, use predicted value
    if abs(i_h - avg_i_h) > 20:
        i_h = p_i_h

    # round to 2 decimal places
    o_t = round(o_t, 2)
    o_h = round(o_h, 2)
    i_t = round(i_t, 2)
    i_h = round(i_h, 2)
    curr_time = datetime.now()
    print(f'[{curr_time.strftime("%Y-%m-%d %H:%M:%S")}]'
          f'[{o_t}, {o_h}%][{raw_i_t}->{i_t}, {raw_i_h}->{i_h}%][{light}]')
    weather_data = Weather(outdoor_temp=o_t, outdoor_humidity=o_h, indoor_temp=i_t, indoor_humidity=i_h)
    session.add(weather_data)
    session.commit()

    # publish to mqtt for HomeAssistant
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.connect(MQTT_BROKER, 1883, 60)

    client.loop_start()
    client.publish('weather/outdoor_temp', weather_data.outdoor_temp, retain=True)
    client.publish('weather/outdoor_humidity', weather_data.outdoor_humidity, retain=True)
    client.publish('weather/indoor_temp', weather_data.indoor_temp, retain=True)
    client.publish('weather/indoor_humidity', weather_data.indoor_humidity, retain=True)
    client.publish('weather/indoor_brightness', light, retain=True)
    client.loop_stop()
    client.disconnect()

    # humidifier control
