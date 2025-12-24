import os
import time
import threading
from datetime import datetime
import re
import paho.mqtt.client as mqtt
from pyvesync import VeSync
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Retrieve MQTT and VeSync credentials from environment variables
MQTT_BROKER = os.getenv('mqtt_broker')
MQTT_USERNAME = os.getenv('mqtt_user')
MQTT_PASSWORD = os.getenv('mqtt_password')
VESYNC_USERNAME = os.getenv('vesync_user')
VESYNC_PASSWORD = os.getenv('vesync_password')

# MQTT broker connection settings
broker_address = MQTT_BROKER
broker_port = 1883

#data to send into humidifier
channel_in = "homeassistant/humidifier_in"

#data to come out of humidifier
channel_out = "homeassistant/humidifier_out"

# Callback function for successful connection to MQTT broker
def on_connect(client, userdata, flags, rc):
    global current_mist_level
    print(f"Connected with result code {rc}, current mist level at {current_mist_level}")
    client.subscribe(channel_in)
    client.publish(channel_out, current_mist_level, retain=True)

# Callback function for processing received MQTT messages
def on_message(client, userdata, msg):
    try:
        global current_mist_level
        global is_turned_off
        if msg.topic == channel_in:
            if not re.match('^\d$', msg.payload.decode()):
                return
            mist_level = int(msg.payload.decode())
            if mist_level > 9:
                mist_level = 9
            hmd.update()
            if is_turned_off:
                current_mist_level = 0
            else:
                current_mist_level = hmd.details['mist_virtual_level']

            if current_mist_level != mist_level:
                if mist_level == 0:
                    hmd.turn_off()
                    is_turned_off = True
                else:
                    hmd.set_mist_level(mist_level)
                    is_turned_off = False
                t_now = datetime.now()
                print(f'[{t_now}]: HA changed mist level from {current_mist_level} to {mist_level}')
                current_mist_level = mist_level
                client.publish(channel_out, mist_level, retain=True)
    except Exception as e:
        import traceback
        traceback.print_exc()


# Function for periodically publishing the humidifier's fan level
def publish_fan_level():
    hmd.update()
    global current_mist_level
    global is_turned_off
    while True:
        try:
            m.update()
            hmd.update()
            if is_turned_off:
                mist_level = 0
            else:
                mist_level = hmd.details['mist_virtual_level']

            if current_mist_level != mist_level:
                t_now = datetime.now()
                print(f'[{t_now}]: App changed mist level from {current_mist_level} to {mist_level}')
                current_mist_level = mist_level
                client.publish(channel_out, mist_level, retain=True)
            time.sleep(60)
        except Exception as e:
            import traceback
            traceback.print_exc()


# Authenticate and initialize the VeSync account
m = VeSync(VESYNC_USERNAME, VESYNC_PASSWORD)
m.login()
m.update()
m.get_devices()

# Get the first fan in the list of devices
hmd = None
# iterate the fans and find the humidifier
for fan in m.fans:
    if hasattr(fan, 'auto_humidity'):
        hmd = fan
        break
if hmd is None:
    raise Exception("No humidifier found in account!")
current_mist_level = hmd.details['mist_virtual_level']
is_turned_off = False

# Create an MQTT client instance
client = mqtt.Client()
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Set the callback functions for MQTT connection and message processing
client.on_connect = on_connect
client.on_message = on_message

# Connect to the MQTT broker
client.connect(broker_address, broker_port, 60)

# Start the loop to process the MQTT messages
client.loop_start()

# Start a new thread for periodically publishing the fan level
publisher_thread = threading.Thread(target=publish_fan_level)
publisher_thread.start()