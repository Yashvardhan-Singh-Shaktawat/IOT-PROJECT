from django.contrib import admin

# Register your models here.
# monitor/admin.py
from django.contrib import admin
from .models import SystemReading, RelayState

admin.site.register(SystemReading)
admin.site.register(RelayState)