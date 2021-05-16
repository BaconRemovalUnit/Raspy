#!/bin/env python
import RPi.GPIO as GPIO
import Adafruit_DHT
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request

heater_status = {"power": False, 'heat': False, 'temp':0, 'hum':0}
app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def main_page():
    update_temp_hum()
    if request.method == 'POST':
        return get_heater_status()
    else:
        curr_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        return render_template('app.html', heater_status=heater_status, curr_time=curr_time)

def update_temp_hum():
    sensor = Adafruit_DHT.DHT22
    pin = 22
    hum, temp = Adafruit_DHT.read_retry(sensor, pin)
    heater_status['temp'] = round(temp, 2)
    heater_status['hum'] = round(hum, 2)

@app.route('/toggle_power')
def toggle_power():
    press_power_button()
    heater_status['power'] = not heater_status['power']
    if not heater_status['power']:
        heater_status['heat'] = False
    return get_heater_status()


@app.route('/toggle_heat')
def toggle_heat():
    if not heater_status['power']:
        return get_heater_status()
    else:
        press_heat_button()
        heater_status['heat'] = not heater_status['heat']
        return get_heater_status()


def get_heater_status():
    curr_time = datetime.now()
    return jsonify({"heater_status": heater_status, "time": curr_time.strftime("%Y/%m/%d %H:%M:%S")})


def press_power_button():
    duty_cycle = 7.5
    power_servo_pin = 17
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(power_servo_pin, GPIO.OUT)
    pwm_servo = GPIO.PWM(power_servo_pin, 50)
    pwm_servo.start(duty_cycle)
    pwm_servo.ChangeDutyCycle(duty_cycle)
    time.sleep(0.2)
    pwm_servo.ChangeDutyCycle(5)
    time.sleep(0.3)
    pwm_servo.ChangeDutyCycle(duty_cycle)
    time.sleep(0.2)
    GPIO.cleanup()


def press_heat_button():
    duty_cycle = 7.5
    warm_servo_pin = 27
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(warm_servo_pin, GPIO.OUT)
    pwm_servo = GPIO.PWM(warm_servo_pin, 50)
    pwm_servo.start(duty_cycle)
    pwm_servo.ChangeDutyCycle(duty_cycle)
    time.sleep(0.2)
    pwm_servo.ChangeDutyCycle(8.5)
    time.sleep(0.3)
    pwm_servo.ChangeDutyCycle(duty_cycle)
    time.sleep(0.2)
    GPIO.cleanup()


if __name__ == '__main__':
    app.run(threaded=True, debug=True, port=80, host='0.0.0.0')
