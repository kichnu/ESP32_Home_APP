# esp32_iot_device.py - Bazowa klasa urządzenia IoT dla ESP32
import network
import time
import ujson
from umqtt.simple import MQTTClient
import machine
from machine import Pin, PWM

led = Pin(3, mode=Pin.OUT)


def run():
    while True:
        # print("high")
        led.value(1)
        time.sleep(0.1)
        # print("low")
        led.value(0)
        time.sleep(0.1)

    # Konfiguracja urządzenia
    CONFIG = {
        "wifi": {"ssid": "YOUR_WIFI_SSID", "password": "YOUR_WIFI_PASSWORD"},
        "mqtt": {
            "broker": "YOUR_MQTT_BROKER_IP",
            "port": 1883,
            "client_id": "esp32_device_",
            "user": "iot_devices",
            "password": "YOUR_MQTT_PASSWORD",
        },
        "device": {
            "id": "dim_light",
            "name": "Lampa z przyciemnianiem",
            "type": "dimmer",
            "topic": "iot/device/dim_light",
        },
        "pins": {
            "led": 2,  # Wbudowana dioda LED na większości płytek ESP32
            "relay": 4,  # Pin do sterowania przekaźnikiem
            "pwm": 5,  # Pin PWM do sterowania jasnością
            "button": 0,  # Przycisk (np. BOOT)
        },
        "status_led": {
            "pin": 2,
            "active_low": True,  # True jeśli dioda jest aktywna przy stanie niskim
        },
    }

    class StatusLED:

        def __init__(self, pin, active_low=True):
            self.led = Pin(pin, Pin.OUT)
            self.active_low = active_low
            self.off()

        def on(self):
            self.led.value(0 if self.active_low else 1)

        def off(self):
            self.led.value(1 if self.active_low else 0)

        def toggle(self):
            self.led.value(not self.led.value())

        def blink(self, count=3, delay=0.2):
            for _ in range(count):
                self.on()
                time.sleep(delay)
                self.off()
                time.sleep(delay)

    class IoTDevice:
        """Bazowa klasa dla urządzeń IoT."""

        def __init__(self, config):
            self.config = config
            self.device_id = config["device"]["id"]
            self.device_topic = config["device"]["topic"]
            self.mqtt_client = None
            self.is_connected = False
            self.wifi_connected = False

            # Inicjalizacja diody statusu
            if "status_led" in config:
                self.status_led = StatusLED(
                    config["status_led"]["pin"],
                    config["status_led"].get("active_low", True),
                )
            else:
                self.status_led = None

                # Stan urządzenia
                self.state = {"online": False, "status": "off", "values": {}}

        def connect_wifi(self):
            """Łączy się z siecią WiFi."""
            if self.status_led:
                self.status_led.blink(2, 0.1)

            print("Łączenie z WiFi...")
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)

            if not self.wlan.isconnected():
                self.wlan.connect(
                    self.config["wifi"]["ssid"], self.config["wifi"]["password"]
                )

            # Czekaj na połączenie
            max_wait = 20
            while max_wait > 0:
                if self.wlan.isconnected():
                    break
                max_wait -= 1
                print("Oczekiwanie na połączenie WiFi...")
                if self.status_led:
                    self.status_led.toggle()
                time.sleep(0.5)

            if self.wlan.isconnected():
                print("Połączono z WiFi")
                print("IP:", self.wlan.ifconfig()[0])
                self.wifi_connected = True
                if self.status_led:
                    self.status_led.on()
                return True
            else:
                print("Błąd połączenia WiFi")
                if self.status_led:
                    self.status_led.blink(5, 0.2)
                self.wifi_connected = False
                return False

        def connect_mqtt(self):
            """Łączy się z brokerem MQTT."""
            if not self.wifi_connected:
                if not self.connect_wifi():
                    return False

            try:
                # Unikalne ID klienta
                client_id = self.config["mqtt"]["client_id"] + self.device_id

                # Tworzenie klienta MQTT
                self.mqtt_client = MQTTClient(
                    client_id,
                    self.config["mqtt"]["broker"],
                    self.config["mqtt"]["port"],
                    self.config["mqtt"]["user"],
                    self.config["mqtt"]["password"],
                    keepalive=30,
                )

                # Ustawienie callbacka dla wiadomości
                self.mqtt_client.set_callback(self.on_mqtt_message)

                # Łączenie z brokerem
                self.mqtt_client.connect()

                # Subskrypcja tematu komend
                command_topic = self.device_topic + "/command"
                self.mqtt_client.subscribe(command_topic)

                print("Połączono z MQTT")
                print("Temat komend:", command_topic)

                # Opublikuj informację o statusie
                self.publish_status("on")
                self.is_connected = True

                return True
            except Exception as e:
                print("Błąd połączenia MQTT:", e)
                if self.status_led:
                    self.status_led.blink(3, 0.3)
                self.is_connected = False
                return False

        def disconnect(self):
            """Rozłącza się z brokerem MQTT."""
            if self.mqtt_client:
                try:
                    self.publish_status("off")
                    self.mqtt_client.disconnect()
                except:
                    pass
            self.is_connected = False

        def publish_status(self, status):
            """Publikuje status urządzenia."""
            if not self.is_connected:
                return False

            try:
                self.state["status"] = status
                topic = self.device_topic + "/status"
                self.mqtt_client.publish(topic, status)
                return True
            except Exception as e:
                print("Błąd publikacji statusu:", e)
                return False

        def publish_value(self, name, value):
            """Publikuje wartość parametru urządzenia."""
            if not self.is_connected:
                return False

            try:
                self.state["values"][name] = value
                topic = self.device_topic + "/value/" + name
                self.mqtt_client.publish(topic, str(value))
                return True
            except Exception as e:
                print("Błąd publikacji wartości:", e)
                return False

        def on_mqtt_message(self, topic, msg):
            """Callback dla przychodzących wiadomości MQTT."""
            topic = topic.decode("utf-8")
            msg = msg.decode("utf-8")
            print("Otrzymano wiadomość:", topic, msg)

            # Obsługa komend
            if topic == self.device_topic + "/command":
                self.handle_command(msg)

        def handle_command(self, command):
            """Obsługuje otrzymane komendy. Do nadpisania w klasach pochodnych."""
            if command == "on":
                self.publish_status("on")
            elif command == "off":
                self.publish_status("off")

        def check_msgs(self):
            """Sprawdza oczekujące wiadomości MQTT."""
            if self.mqtt_client and self.is_connected:
                try:
                    self.mqtt_client.check_msg()
                    return True
                except Exception as e:
                    print("Błąd sprawdzania wiadomości:", e)
                    self.is_connected = False
                    return False
            return False

        def reconnect(self):
            """Ponowne łączenie w przypadku utraty połączenia."""
            if not self.wlan.isconnected():
                if not self.connect_wifi():
                    return False

            if not self.is_connected:
                return self.connect_mqtt()

            return True

        def run(self):
            """Główna pętla urządzenia."""
            if not self.connect_mqtt():
                if self.status_led:
                    self.status_led.blink(5, 0.2)
                time.sleep(5)
                machine.reset()

            try:
                last_ping = time.time()

                while True:
                    # Sprawdź wiadomości MQTT
                    if not self.check_msgs():
                        if not self.reconnect():
                            time.sleep(5)
                            continue

                    # Wyślij ping co 60 sekund aby utrzymać połączenie
                    current_time = time.time()
                    if current_time - last_ping > 60:
                        self.publish_status(self.state["status"])
                        last_ping = current_time

                    # Tutaj można dodać dodatkową logikę dla konkretnych urządzeń
                    self.loop()

                    # Krótkie opóźnienie
                    time.sleep(0.1)

            except Exception as e:
                print("Błąd w głównej pętli:", e)
                time.sleep(10)
                machine.reset()

        def loop(self):
            """Metoda wywoływana w każdej iteracji pętli. Do nadpisania w klasach pochodnych."""
            pass

    class DimmerDevice(IoTDevice):
        """Klasa dla urządzeń typu dimmer (ściemniacz/regulator jasności)."""

        def __init__(self, config):
            super().__init__(config)

            # Inicjalizacja przekaźnika
            self.relay_pin = Pin(config["pins"]["relay"], Pin.OUT)
            self.relay_pin.value(0)  # Wyłączony na start

            # Inicjalizacja PWM dla sterowania jasnością
            self.pwm_pin = Pin(config["pins"]["pwm"], Pin.OUT)
            self.pwm = PWM(self.pwm_pin)
            self.pwm.freq(1000)  # Częstotliwość PWM 1kHz
            self.pwm.duty(0)  # Wyjście wyłączone na start

            # Przycisk sterujący (opcjonalnie)
            if "button" in config["pins"]:
                self.button = Pin(config["pins"]["button"], Pin.IN, Pin.PULL_UP)
                self.button.irq(trigger=Pin.IRQ_FALLING, handler=self.button_handler)
            else:
                self.button = None

            # Stan ściemniacza
            self.brightness = 0  # 0-100%
            self.is_on = False

            # Ostatnie wywołanie przycisku (do debounce)
            self.last_button_time = 0

        def set_brightness(self, brightness):
            """Ustawia jasność w zakresie 0-100%."""
            # Ograniczenie wartości do zakresu 0-100
            brightness = max(0, min(100, brightness))
            self.brightness = brightness

            # Konwersja procentów na wartość duty cycle (0-1023 dla ESP32)
            duty = int(brightness * 1023 / 100)

            if brightness > 0 and not self.is_on:
                # Włącz przekaźnik jeśli jest wyłączony
                self.relay_pin.value(1)
                self.is_on = True
                self.publish_status("on")
            elif brightness == 0 and self.is_on:
                # Wyłącz przekaźnik jeśli jasność jest zerowa
                self.relay_pin.value(0)
                self.is_on = False
                self.publish_status("off")

            # Ustaw duty cycle PWM
            self.pwm.duty(duty)

            # Publikuj wartość jasności
            self.publish_value("brightness", brightness)

            return True

        def handle_command(self, command):
            """Obsługuje komendy dla ściemniacza."""
            try:
                # Sprawdź czy komenda to JSON
                try:
                    cmd_data = ujson.loads(command)
                    if isinstance(cmd_data, dict):
                        # Obsługa złożonych komend
                        if "brightness" in cmd_data:
                            self.set_brightness(float(cmd_data["brightness"]))
                        if "state" in cmd_data:
                            if cmd_data["state"] == "on":
                                if self.brightness == 0:
                                    self.set_brightness(
                                        100
                                    )  # Domyślne włączenie na 100%
                            else:
                                self.set_brightness(0)  # Wyłączenie
                        return
                except ValueError:
                    pass  # To nie JSON, kontynuuj przetwarzanie

                # Prosta komenda tekstowa
                if command == "on":
                    if self.brightness == 0:
                        self.set_brightness(100)  # Domyślne włączenie na 100%
                    else:
                        self.set_brightness(
                            self.brightness
                        )  # Włączenie na ostatnią wartość
                elif command == "off":
                    self.set_brightness(0)  # Wyłączenie
                else:
                    # Sprawdź czy komenda to liczba (0-100)
                    try:
                        brightness = float(command)
                        self.set_brightness(brightness)
                    except ValueError:
                        print("Nieznana komenda:", command)
            except Exception as e:
                print("Błąd przetwarzania komendy:", e)

        def button_handler(self, pin):
            """Obsługa przycisku z debounce."""
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, self.last_button_time) < 300:
                return  # Debounce - ignoring presses less than 300ms apart

            self.last_button_time = current_time

            # Przełącz stan
            if self.is_on:
                self.set_brightness(0)  # Wyłącz
            else:
                self.set_brightness(100)  # Włącz na 100%

        def loop(self):
            """Dodatkowa logika wywoływana w pętli głównej."""
            # Można dodać dodatkową logikę, np. płynne przejścia jasności,
            # odczyt dodatkowych czujników, itp.
            pass

    # Uruchomienie urządzenia
    def main():
        device = DimmerDevice(CONFIG)
        device.run()

    if __name__ == "__main__":
        main()
