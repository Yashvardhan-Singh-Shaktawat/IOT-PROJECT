from django.db import models

class SystemReading(models.Model):
    # Sensor Data
    solar_power_watts = models.FloatField(default=0.0)
    battery_discharge_watts = models.FloatField(default=0.0)
    grid_power_watts = models.FloatField(default=0.0)
    battery_percentage = models.FloatField(default=0.0)
    
    # Relay Status Logs (History)
    relay_home_status = models.BooleanField(default=False)   # Relay 1
    relay_grid_status = models.BooleanField(default=False)   # Relay 2
    relay_import_status = models.BooleanField(default=False) # Relay 3 (NEW)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - Solar: {self.solar_power_watts}W"

class RelayState(models.Model):
    # Singleton model: Only row ID=1 is used
    home_load_active = models.BooleanField(default=False)
    grid_sell_active = models.BooleanField(default=False)
    grid_import_active = models.BooleanField(default=False) # Relay 3 (NEW)

    def save(self, *args, **kwargs):
        self.pk = 1
        super(RelayState, self).save(*args, **kwargs)