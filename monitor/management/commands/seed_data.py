import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitor.models import SystemReading, RelayState

class Command(BaseCommand):
    help = 'Seeds historical data for the solar monitor dashboard and initializes the relay state'

    def handle(self, *args, **options):
        self.stdout.write("Initializing RelayState...")
        relay_state, created = RelayState.objects.get_or_create(pk=1)
        if created:
            relay_state.home_load_active = True
            relay_state.grid_sell_active = False
            relay_state.grid_import_active = False
            relay_state.save()
            self.stdout.write("Created default RelayState (Solar -> Home).")
        else:
            self.stdout.write("RelayState already exists.")

        self.stdout.write("Seeding historical readings...")
        
        # Clear existing readings to ensure clean slate
        SystemReading.objects.all().delete()
        
        now = timezone.now()
        readings = []
        
        # Seed 30 days of historical hourly readings
        # To make the charts and economics page look full and realistic:
        # We will generate hourly data points for the past 30 days.
        total_days = 30
        self.stdout.write(f"Generating hourly data for the past {total_days} days...")
        
        for hour_offset in range(total_days * 24, -1, -1):
            timestamp = now - timedelta(hours=hour_offset)
            hour = timestamp.hour
            
            # Determine solar generation based on hour of the day (bell curve 6 AM - 6 PM)
            if 6 <= hour <= 18:
                # Peak at 12-1 PM
                peak_factor = 1.0 - abs(hour - 12.5) / 6.5
                solar_w = max(0.0, peak_factor * 1200.0 + random.uniform(-100, 100))
            else:
                solar_w = 0.0
                
            # Consumption (Battery Discharge / Load)
            # Typically higher in morning (7-9 AM) and evening (6-10 PM)
            if 7 <= hour <= 9:
                load_w = 600.0 + random.uniform(-50, 100)
            elif 18 <= hour <= 22:
                load_w = 800.0 + random.uniform(-100, 150)
            else:
                load_w = 200.0 + random.uniform(-30, 30)
                
            # Decide relay modes and states based on time and solar availability
            # Morning/Day: Power Home or Charge Battery or Sell
            # Evening/Night: Use Main Grid or Discharge Battery
            relay_home = False
            relay_grid = False
            relay_import = False
            grid_w = 0.0
            bat_out_w = 0.0
            bat_pct = 50.0
            
            # Simulated state of charge based on time of day
            if 0 <= hour < 6:
                # Discharging/Idle at night
                bat_pct = max(20.0, 40.0 - (hour * 3.0) + random.uniform(-2, 2))
                relay_import = True
                grid_w = load_w
            elif 6 <= hour < 12:
                # Sun rising, charging battery and powering home
                bat_pct = min(90.0, 30.0 + ((hour - 6) * 10.0) + random.uniform(-3, 3))
                relay_home = True
                bat_out_w = max(0.0, load_w - solar_w)
            elif 12 <= hour < 16:
                # Sun high, battery full, selling excess to grid
                bat_pct = min(100.0, 90.0 + ((hour - 12) * 2.5) + random.uniform(-1, 1))
                relay_grid = True
                bat_out_w = max(0.0, solar_w - load_w)
            elif 16 <= hour < 19:
                # Sun setting, discharging battery
                bat_pct = max(60.0, 95.0 - ((hour - 16) * 10.0) + random.uniform(-2, 2))
                relay_home = True
                bat_out_w = load_w
            else:
                # Night: using main grid
                bat_pct = max(30.0, 60.0 - ((hour - 19) * 5.0) + random.uniform(-2, 2))
                relay_import = True
                grid_w = load_w

            # Scale up historical values so the financial sums match Django's hardcoded 2s interval logic:
            # Django calculates kWh as (watts * 2 / 3600) / 1000.
            # To make 1 reading per hour equal to 1800 readings at 2-second intervals,
            # we scale up the wattage by 1800!
            scale_factor = 1800.0
            
            reading = SystemReading(
                solar_power_watts=solar_w * scale_factor if hour_offset > 0 else solar_w,
                battery_discharge_watts=bat_out_w * scale_factor if hour_offset > 0 else bat_out_w,
                grid_power_watts=grid_w * scale_factor if hour_offset > 0 else grid_w,
                battery_percentage=constrain(bat_pct, 0.0, 100.0),
                relay_home_status=relay_home,
                relay_grid_status=relay_grid,
                relay_import_status=relay_import,
            )
            # Directly assign timestamp
            reading.timestamp = timestamp
            readings.append(reading)
            
        # Bulk create and then update timestamps (auto_now_add override)
        SystemReading.objects.bulk_create(readings)
        
        # Override auto_now_add timestamps by directly updating in DB
        # Since sqlite bulk_create doesn't always support custom auto_now_add timestamps cleanly,
        # we update them individually or using a save override.
        # Let's verify by checking the database timestamps.
        for r in SystemReading.objects.all():
            for generated in readings:
                if generated.battery_percentage == r.battery_percentage and generated.solar_power_watts == r.solar_power_watts:
                    SystemReading.objects.filter(pk=r.pk).update(timestamp=generated.timestamp)
                    break

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(readings)} historical readings."))

def constrain(val, min_val, max_val):
    return min(max_val, max(min_val, val))
