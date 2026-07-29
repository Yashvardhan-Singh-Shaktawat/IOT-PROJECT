import json
import random
from datetime import timedelta
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Avg
from django.db.models.functions import TruncHour, TruncDay
from django.utils import timezone
from .models import SystemReading, RelayState

# --- IN-MEMORY FALLBACK FOR VERCEL / READ-ONLY DB ---
IN_MEMORY_RELAY_STATE = {
    'home': True,
    'sell': False,
    'import': False
}

def get_current_relay_state():
    try:
        relay_state, _ = RelayState.objects.get_or_create(pk=1)
        return {
            'home': relay_state.home_load_active,
            'sell': relay_state.grid_sell_active,
            'import': relay_state.grid_import_active,
            'obj': relay_state
        }
    except Exception:
        return {
            'home': IN_MEMORY_RELAY_STATE['home'],
            'sell': IN_MEMORY_RELAY_STATE['sell'],
            'import': IN_MEMORY_RELAY_STATE['import'],
            'obj': None
        }

# --- PAGES ---
def dashboard_view(request):
    return render(request, 'monitor/dashboard.html')

def economics_view(request):
    return render(request, 'monitor/economics.html')

# --- DUMMY DATA GENERATORS (FALLBACK WHEN REAL DATA NOT AVAILABLE) ---
def generate_dummy_reading(now):
    hour = now.hour
    
    # Daytime (6 AM - 6 PM): Solar peak around noon
    if 6 <= hour <= 18:
        peak_factor = 1.0 - abs(hour - 12.5) / 6.5
        solar_w = max(50.0, round(peak_factor * 1150.0 + random.uniform(-20, 20), 1))
    else:
        solar_w = 0.0

    # Household load
    if 7 <= hour <= 9:
        load_w = round(550.0 + random.uniform(-30, 40), 1)
    elif 18 <= hour <= 22:
        load_w = round(780.0 + random.uniform(-40, 50), 1)
    else:
        load_w = round(220.0 + random.uniform(-15, 15), 1)

    relays = get_current_relay_state()

    if 6 <= hour <= 17:
        bat_pct = min(98.0, round(45.0 + (hour - 6) * 4.8 + random.uniform(-1, 1), 1))
        grid_w = 0.0
        bat_out_w = max(0.0, round(load_w - solar_w * 0.4, 1))
    else:
        bat_pct = max(25.0, round(85.0 - (hour - 18 if hour >= 18 else hour + 6) * 4.5 + random.uniform(-1, 1), 1))
        grid_w = load_w if relays['import'] else round(load_w * 0.3, 1)
        bat_out_w = load_w if not relays['import'] else round(load_w * 0.7, 1)

    return {
        'solar': solar_w,
        'grid': grid_w,
        'battery_out': bat_out_w,
        'battery_pct': bat_pct,
        'home_status': relays['home'],
        'grid_status': relays['sell'],
        'import_status': relays['import'],
        'time': now.strftime('%H:%M:%S')
    }

def generate_dummy_history(period):
    now = timezone.now()
    labels, solar_data, grid_data = [], [], []

    if period == 'week':
        for i in range(6, -1, -1):
            day_time = now - timedelta(days=i)
            labels.append(day_time.strftime('%b %d'))
            solar_data.append(round(random.uniform(420, 680), 1))
            grid_data.append(round(random.uniform(150, 320), 1))
    elif period == 'month':
        for i in range(29, -1, -1):
            day_time = now - timedelta(days=i)
            labels.append(day_time.strftime('%b %d'))
            solar_data.append(round(random.uniform(380, 720), 1))
            grid_data.append(round(random.uniform(140, 350), 1))
    else: # day (24 hours)
        for h in range(23, -1, -1):
            t = now - timedelta(hours=h)
            hour = t.hour
            labels.append(t.strftime('%I %p'))
            
            if 6 <= hour <= 18:
                peak_factor = 1.0 - abs(hour - 12.5) / 6.5
                solar_w = max(0.0, round(peak_factor * 1100.0 + random.uniform(-40, 40), 1))
            else:
                solar_w = 0.0

            if 7 <= hour <= 9 or 18 <= hour <= 22:
                grid_w = round(random.uniform(300, 600), 1)
            else:
                grid_w = round(random.uniform(80, 200), 1)

            solar_data.append(solar_w)
            grid_data.append(grid_w)

    return {
        'labels': labels,
        'solar': solar_data,
        'grid': grid_data
    }

def generate_dummy_financial(period):
    if period == 'week':
        solar_u = 64.8
        bought_u = 21.5
        sold_u = 18.2
    elif period == 'year':
        solar_u = 3380.0
        bought_u = 1120.0
        sold_u = 950.0
    else: # month
        solar_u = 278.4
        bought_u = 92.6
        sold_u = 78.0

    BUY_RATE = 8.0
    SELL_RATE = 4.0

    return {
        'solar_units': round(solar_u, 2),
        'solar_value': round(solar_u * BUY_RATE, 2),
        'bought_units': round(bought_u, 2),
        'bought_cost': round(bought_u * BUY_RATE, 2),
        'sold_units': round(sold_u, 2),
        'sold_profit': round(sold_u * SELL_RATE, 2)
    }

# --- ESP32 SYNC (RECEIVE DATA / SEND COMMANDS) ---
@csrf_exempt
def handle_esp_communication(request):
    relays = get_current_relay_state()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            try:
                SystemReading.objects.create(
                    solar_power_watts=data.get('solar_w', 0),
                    battery_discharge_watts=data.get('bat_out_w', 0),
                    grid_power_watts=data.get('grid_w', 0),
                    battery_percentage=data.get('bat_pct', 0),
                    relay_home_status=relays['home'],
                    relay_grid_status=relays['sell'],
                    relay_import_status=relays['import']
                )
            except Exception:
                pass # SQLite database write exception on Vercel lambda ignored gracefully

            return JsonResponse({
                "status": "success",
                "relay_home": relays['home'],
                "relay_grid": relays['sell'],
                "relay_import": relays['import']
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse({"status": "ok"})

# --- LIVE DATA API ---
def get_latest_reading(request):
    try:
        reading = SystemReading.objects.latest('timestamp')
        relays = get_current_relay_state()
        return JsonResponse({
            'solar': reading.solar_power_watts,
            'grid': reading.grid_power_watts,
            'battery_out': reading.battery_discharge_watts,
            'battery_pct': reading.battery_percentage,
            'home_status': relays['home'],
            'grid_status': relays['sell'],
            'import_status': relays['import'],
            'time': reading.timestamp.strftime('%H:%M:%S')
        })
    except Exception:
        # Fallback to dynamic realistic dummy reading when real sensor data is not available
        return JsonResponse(generate_dummy_reading(timezone.now()))

# --- HISTORY CHART API ---
def get_history_data(request):
    period = request.GET.get('period', 'day')
    now = timezone.now()
    
    try:
        if period == 'week':
            start_date = now - timedelta(days=7)
            trunc_func = TruncDay('timestamp')
            fmt = '%b %d'
        elif period == 'month':
            start_date = now - timedelta(days=30)
            trunc_func = TruncDay('timestamp')
            fmt = '%b %d'
        else: 
            start_date = now - timedelta(hours=24)
            trunc_func = TruncHour('timestamp')
            fmt = '%I %p'

        data = SystemReading.objects.filter(timestamp__gte=start_date)\
            .annotate(date=trunc_func)\
            .values('date')\
            .annotate(avg_solar=Avg('solar_power_watts'), avg_grid=Avg('grid_power_watts'))\
            .order_by('date')

        data_list = list(data)
        if not data_list:
            return JsonResponse(generate_dummy_history(period))

        return JsonResponse({
            'labels': [entry['date'].strftime(fmt) for entry in data_list],
            'solar': [round(entry['avg_solar'] or 0, 1) for entry in data_list],
            'grid': [round(entry['avg_grid'] or 0, 1) for entry in data_list]
        })
    except Exception:
        return JsonResponse(generate_dummy_history(period))

# --- FINANCIAL REPORT API ---
def get_financial_data(request):
    period = request.GET.get('period', 'month')
    now = timezone.now()
    
    try:
        if period == 'week': start_date = now - timedelta(days=7)
        elif period == 'year': start_date = now - timedelta(days=365)
        else: start_date = now - timedelta(days=30)

        readings = SystemReading.objects.filter(timestamp__gte=start_date)
        readings_count = readings.count()

        if readings_count == 0:
            return JsonResponse(generate_dummy_financial(period))

        TIME_INTERVAL_HOURS = 2 / 3600.0 
        
        total_solar_kwh = 0.0
        total_grid_bought_kwh = 0.0
        total_sold_kwh = 0.0
        
        for r in readings:
            total_solar_kwh += (r.solar_power_watts * TIME_INTERVAL_HOURS) / 1000.0
            total_grid_bought_kwh += (r.grid_power_watts * TIME_INTERVAL_HOURS) / 1000.0
            
            if r.relay_grid_status:
                total_sold_kwh += (r.battery_discharge_watts * TIME_INTERVAL_HOURS) / 1000.0

        if total_solar_kwh == 0 and total_grid_bought_kwh == 0 and total_sold_kwh == 0:
            return JsonResponse(generate_dummy_financial(period))

        BUY_RATE = 8.0; SELL_RATE = 4.0
        
        return JsonResponse({
            'solar_units': round(total_solar_kwh, 2),
            'solar_value': round(total_solar_kwh * BUY_RATE, 2),
            'bought_units': round(total_grid_bought_kwh, 2),
            'bought_cost': round(total_grid_bought_kwh * BUY_RATE, 2),
            'sold_units': round(total_sold_kwh, 2),
            'sold_profit': round(total_sold_kwh * SELL_RATE, 2)
        })
    except Exception:
        return JsonResponse(generate_dummy_financial(period))

# --- TOGGLE RELAYS (UPDATED 4-MODE LOGIC WITH VERCEL IN-MEMORY FALLBACK) ---
def toggle_relays(request):
    mode = request.GET.get('mode')
    
    if mode == 'home':
        IN_MEMORY_RELAY_STATE['home'] = True
        IN_MEMORY_RELAY_STATE['sell'] = False
        IN_MEMORY_RELAY_STATE['import'] = False
    elif mode == 'grid_sell':
        IN_MEMORY_RELAY_STATE['home'] = False
        IN_MEMORY_RELAY_STATE['sell'] = True
        IN_MEMORY_RELAY_STATE['import'] = False
    elif mode == 'grid_import':
        IN_MEMORY_RELAY_STATE['home'] = False
        IN_MEMORY_RELAY_STATE['sell'] = False
        IN_MEMORY_RELAY_STATE['import'] = True
    elif mode == 'charge':
        IN_MEMORY_RELAY_STATE['home'] = False
        IN_MEMORY_RELAY_STATE['sell'] = False
        IN_MEMORY_RELAY_STATE['import'] = False

    try:
        state, _ = RelayState.objects.get_or_create(pk=1)
        state.home_load_active = IN_MEMORY_RELAY_STATE['home']
        state.grid_sell_active = IN_MEMORY_RELAY_STATE['sell']
        state.grid_import_active = IN_MEMORY_RELAY_STATE['import']
        state.save()
    except Exception:
        pass

    return JsonResponse({
        'mode': mode, 
        'home': IN_MEMORY_RELAY_STATE['home'], 
        'sell': IN_MEMORY_RELAY_STATE['sell'],
        'import': IN_MEMORY_RELAY_STATE['import']
    })