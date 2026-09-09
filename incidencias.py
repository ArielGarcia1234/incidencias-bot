import requests
import os
import time
import json
import base64
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ============== CONFIGURACIÓN ==============
API_URL = "https://juriscloud.es/api/incidents"
LOGIN_URL = "https://juriscloud.es/api/auth/login"

USERNAME = os.getenv("JURISCLOUD_USERNAME")
PASSWORD = os.getenv("JURISCLOUD_PASSWORD")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = "787548988"

CHECK_INTERVAL = 900  # 15 minutos
TIMEZONE = ZoneInfo("Europe/Madrid")
# ===========================================

token = None
token_exp = 0
seen_ids = set()

def login():
    global token, token_exp
    try:
        r = requests.post(LOGIN_URL, json={
            "username": USERNAME,
            "password": PASSWORD
        }, timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            token = data["token"]
            payload = token.split('.')[1]
            payload += '=' * (4 - len(payload) % 4)
            payload_data = json.loads(base64.urlsafe_b64decode(payload))
            token_exp = payload_data["exp"]
            print(f"[{datetime.now(TIMEZONE).strftime('%H:%M:%S')}] Login correcto. Token válido hasta {datetime.fromtimestamp(token_exp, TIMEZONE).strftime('%H:%M:%S')}")
            return True
        else:
            print(f"Error en login: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"Error de conexión en login: {e}")
        return False

def get_headers():
    global token
    if not token or time.time() > (token_exp - 600):
        if not login():
            return None
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Error enviando Telegram: {e}")

def get_incidents():
    headers = get_headers()
    if not headers:
        return []
    
    try:
        r = requests.get(API_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 401:
            print("Token inválido, reintentando login...")
            if login():
                headers = get_headers()
                r = requests.get(API_URL, headers=headers, timeout=15)
                if r.status_code == 200:
                    return r.json()
        print(f"Error API: {r.status_code} - {r.text}")
        return []
    except Exception as e:
        print(f"Error de conexión: {e}")
        return []

def format_incident(inc):
    title = inc.get("title", "Sin título")
    location = inc.get("location") or f"{inc.get('location_type_value', '')} - {inc.get('block_value', '')} - {inc.get('location_detail_value', '')}"
    status = inc.get("status", "?")
    created = inc.get("created_at", "")[:16].replace("T", " ")
    
    # Comentarios: primero notes, si no hay, description
    comments = inc.get("notes") or inc.get("description") or "Sin comentarios"

    return (
        f"🔔 <b>Nueva incidencia</b>\n\n"
        f"<b>{title}</b>\n"
        f"📍 {location}\n"
        f"💬 {comments}\n"
        f"📌 Estado: {status}\n"
        f"🕒 {created}"
    )

def is_work_time(now):
    """Devuelve True si es lunes-viernes entre 8:00 y 18:00"""
    return now.weekday() < 5 and 8 <= now.hour < 18

def seconds_until_next_work_time(now):
    """Calcula cuántos segundos faltan hasta el próximo horario laboral"""
    # Si estamos dentro del horario, no debería llamarse
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    
    # Si ya pasó de las 18:00 o es fin de semana, buscar el próximo lunes/día laboral a las 8:00
    if now.hour >= 18 or now.weekday() >= 5:
        # Avanzar al siguiente día
        days_ahead = 1
        if now.weekday() == 4 and now.hour >= 18:  # Viernes después de las 18
            days_ahead = 3  # Saltar al lunes
        elif now.weekday() == 5:  # Sábado
            days_ahead = 2  # Lunes
        elif now.weekday() == 6:  # Domingo
            days_ahead = 1  # Lunes
        
        target = (now + timedelta(days=days_ahead)).replace(hour=8, minute=0, second=0, microsecond=0)
    
    # Si es antes de las 8:00 de un día laboral
    elif now.hour < 8:
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    
    delta = target - now
    return max(int(delta.total_seconds()), 60)  # mínimo 60 segundos

def main():
    print(f"[{datetime.now(TIMEZONE).strftime('%H:%M:%S')}] Monitor de incidencias iniciado...")
    print("Horario: Lunes a Viernes de 08:00 a 18:00 (hora España)")
    
    if not login():
        print("No se pudo hacer login. Revisa usuario/contraseña.")
        return

    # Carga inicial
    incidents = get_incidents()
    for inc in incidents:
        seen_ids.add(inc["id"])
    print(f"Cargadas {len(seen_ids)} incidencias existentes. Esperando nuevas...\n")

    while True:
        now = datetime.now(TIMEZONE)
        
        if is_work_time(now):
            # Estamos en horario laboral → comprobar
            incidents = get_incidents()
            new_ones = []

            for inc in incidents:
                if inc["id"] not in seen_ids:
                    seen_ids.add(inc["id"])
                    new_ones.append(inc)

            if new_ones:
                print(f"[{now.strftime('%H:%M:%S')}] ¡{len(new_ones)} incidencia(s) nueva(s)!")
                for inc in new_ones:
                    msg = format_incident(inc)
                    send_telegram(msg)
                    print(f"  → {inc.get('title')}")
            else:
                print(f"[{now.strftime('%H:%M:%S')}] Sin novedades ({len(seen_ids)} total)")
            
            time.sleep(CHECK_INTERVAL)
        else:
            # Fuera de horario → dormir hasta el próximo horario laboral
            sleep_secs = seconds_until_next_work_time(now)
            next_time = now + timedelta(seconds=sleep_secs)
            print(f"[{now.strftime('%H:%M:%S')}] Fuera de horario. Durmiendo hasta {next_time.strftime('%A %H:%M')} ({sleep_secs//60} min)")
            time.sleep(sleep_secs)

if __name__ == "__main__":
    main()
