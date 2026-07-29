import time
import random
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitor.models import RelayState

class Command(BaseCommand):
    help = 'Simulates a live ESP32 device posting sensor data to the server every 2 seconds'

    def handle(self, *args, **options):
        url = "http://127.0.0.1:8000/api/esp-sync/"
        self.stdout.write(f"Starting IoT Device Simulator targeting {url}...")
        self.stdout.write("Press Ctrl+C to stop.")

        # Local variables to track state across loops
        bat_pct = 75.0

        while True:
            try:
                # 1. Fetch current relay state to decide how values respond
                # In a real system, the relay commands come back from the server POST response,
                # but to simulate energy physics, we can check the database or the last response.
                try:
                    relay_state, _ = RelayState.objects.get_or_create(pk=1)
                    home_active = relay_state.home_load_active
                    sell_active = relay_state.grid_sell_active
                    import_active = relay_state.grid_import_active
                except Exception:
                    home_active = True
                    sell_active = False
                    import_active = False

                # Get hour of day for solar simulation
                now = timezone.now()
                hour = now.hour
                
                # A. SOLAR
                if 6 <= hour <= 18:
                    peak_factor = 1.0 - abs(hour - 12.5) / 6.5
                    solar_w = max(0.0, peak_factor * 1200.0 + random.uniform(-50, 50))
                else:
                    solar_w = 0.0

                # B. CONSUMPTION / LOAD
                if 7 <= hour <= 9:
                    load_w = 600.0 + random.uniform(-20, 20)
                elif 18 <= hour <= 22:
                    load_w = 800.0 + random.uniform(-40, 40)
                else:
                    load_w = 200.0 + random.uniform(-10, 10)

                # C. CALCULATE GRID AND BATTERY FLOWS
                grid_w = 0.0
                bat_out_w = 0.0

                if home_active:
                    # Solar -> Home
                    if solar_w >= load_w:
                        # Solar covers home. Excess charges battery
                        bat_pct = min(100.0, bat_pct + (solar_w - load_w) * 0.0001)
                    else:
                        # Solar is not enough. Battery discharges to cover deficit
                        deficit = load_w - solar_w
                        bat_out_w = deficit
                        bat_pct = max(0.0, bat_pct - deficit * 0.0001)
                
                elif sell_active:
                    # Solar -> Grid (Selling)
                    # We send solar power to grid and battery discharge is the power sold
                    grid_w = -solar_w  # Negative grid means selling/exporting
                    bat_out_w = solar_w
                    bat_pct = max(0.0, bat_pct - 0.05) # Slow drain

                elif import_active:
                    # Grid -> Home (Use Main Grid)
                    grid_w = load_w
                    # Excess solar charges battery
                    if solar_w > 0:
                        bat_pct = min(100.0, bat_pct + solar_w * 0.0001)

                else:
                    # Charge Battery (All Output OFF)
                    if solar_w > 0:
                        bat_pct = min(100.0, bat_pct + solar_w * 0.0002) # Fast charge
                    # Grid is idle, battery discharge is 0

                # D. PAYLOAD
                payload = {
                    "solar_w": round(solar_w, 2),
                    "bat_out_w": round(bat_out_w, 2),
                    "grid_w": round(grid_w, 2),
                    "bat_pct": round(bat_pct, 1)
                }

                # E. POST TO SERVER
                response = requests.post(url, json=payload, timeout=2.0)
                if response.status_code == 200:
                    res_data = response.json()
                    self.stdout.write(
                        f"[{now.strftime('%H:%M:%S')}] Sent: Solar={payload['solar_w']}W, "
                        f"Bat={payload['bat_pct']}%, Grid={payload['grid_w']}W. "
                        f"Server Response: Home={res_data.get('relay_home')}, "
                        f"GridSell={res_data.get('relay_grid')}, GridImport={res_data.get('relay_import')}"
                    )
                else:
                    self.stdout.write(self.style.WARNING(
                        f"[{now.strftime('%H:%M:%S')}] Server returned status code {response.status_code}"
                    ))

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(
                    f"[{timezone.now().strftime('%H:%M:%S')}] Connection failed. Is Django running? error={e}"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Simulator error: {e}"))

            time.sleep(2.0)
