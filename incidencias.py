import requests
import time
import json
import base64
from datetime import datetime

# ============== CONFIGURACIÓN ==============
API_URL = "https://juriscloud.es/api/incidents"
LOGIN_URL = "https://juriscloud.es/api/auth/login"

USERNAME = "Ariel"
PASSWORD = "Ariel1234"

TELEGRAM_BOT_TOKEN = "8901319101:AAFZ_RIr7wiDw3t848knUi2Jn-I1vAKLWvI"
TELEGRAM_CHAT_ID = "787548988"

CHECK_INTERVAL = 120  # segundos (2 minutos). Cámbialo si quieres
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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Login correcto. Token válido hasta {datetime.fromtimestamp(token_exp).strftime('%H:%M:%S')}")
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
    priority = str(inc.get("priority", "?")).upper()
    status = inc.get("status", "?")
    created = inc.get("created_at", "")[:16].replace("T", " ")

    emoji = "🔴" if priority == "ALTA" else "🟡" if priority == "MEDIA" else "🟢"

    return (
        f"{emoji} <b>Nueva incidencia</b>\n\n"
        f"<b>{title}</b>\n"
        f"📍 {location}\n"
        f"⚡ Prioridad: {priority}\n"
        f"📌 Estado: {status}\n"
        f"🕒 {created}"
    )

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitor de incidencias iniciado...")
    
    if not login():
        print("No se pudo hacer login. Revisa usuario/contraseña.")
        return

    # Carga inicial (no avisa de las que ya existen)
    incidents = get_incidents()
    for inc in incidents:
        seen_ids.add(inc["id"])
    print(f"Cargadas {len(seen_ids)} incidencias existentes. Esperando nuevas...\n")

    while True:
        time.sleep(CHECK_INTERVAL)
        
        incidents = get_incidents()
        new_ones = []

        for inc in incidents:
            if inc["id"] not in seen_ids:
                seen_ids.add(inc["id"])
                new_ones.append(inc)

        if new_ones:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ¡{len(new_ones)} incidencia(s) nueva(s)!")
            for inc in new_ones:
                msg = format_incident(inc)
                send_telegram(msg)
                print(f"  → {inc.get('title')}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Sin novedades ({len(seen_ids)} total)")

if __name__ == "__main__":
    main()