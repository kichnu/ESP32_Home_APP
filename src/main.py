from machine import Pin
import time

led = Pin(3, mode=Pin.OUT)


def run():
    while True:
        # print("high")
        led.value(1)
        time.sleep(1)
        # print("low")
        led.value(0)
        time.sleep(0.1)
