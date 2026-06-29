import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KIWI_API_KEY = os.environ["KIWI_API_KEY"]

KIWI_URL = "https://api.tequila.kiwi.com/v2/search"


def buscar_vuelo_barato(origen, destino, fecha_desde, fecha_hasta):
    headers = {"apikey": KIWI_API_KEY}
    params = {
        "fly_from": origen,
        "fly_to": destino,
        "date_from": fecha_desde,
        "date_to": fecha_hasta,
        "direct_flights": 1,
        "curr": "EUR",
        "sort": "price",
        "limit": 1,
    }
    resp = requests.get(KIWI_URL, headers=headers, params=params)
    resp.raise_for_status()
    data = resp.json()
    if data.get("data"):
        return data["data"][0]
    return None


def formatear_vuelo(vuelo, origen, destino):
    if not vuelo:
        return f"✈️ *{origen} → {destino}*\nSin vuelos directos disponibles en ese rango."

    precio = vuelo["price"]
    salida = datetime.utcfromtimestamp(vuelo["dTime"]).strftime("%d/%m/%Y %H:%M")
    llegada = datetime.utcfromtimestamp(vuelo["aTime"]).strftime("%d/%m/%Y %H:%M")
    aerolinea = vuelo["airlines"][0] if vuelo.get("airlines") else "?"
    enlace = vuelo.get("deep_link", "")

    return (
        f"✈️ *{origen} → {destino}*\n"
        f"💶 Precio: *{precio} €*\n"
        f"📅 Salida: {salida}\n"
        f"🛬 Llegada: {llegada}\n"
        f"🏢 Aerolínea: {aerolinea}\n"
        f"🔗 [Ver vuelo]({enlace})"
    )


def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload)
    resp.raise_for_status()


def main():
    hoy = datetime.utcnow()
    fin = hoy + timedelta(days=120)
    fecha_desde = hoy.strftime("%d/%m/%Y")
    fecha_hasta = fin.strftime("%d/%m/%Y")

    alc_waw = buscar_vuelo_barato("ALC", "WAW", fecha_desde, fecha_hasta)
    waw_alc = buscar_vuelo_barato("WAW", "ALC", fecha_desde, fecha_hasta)

    hoy_str = hoy.strftime("%d/%m/%Y")
    cabecera = f"🗓️ *Vuelos baratos — {hoy_str}*\n_Rango: próximos 4 meses_\n\n"
    cuerpo = (
        formatear_vuelo(alc_waw, "ALC", "WAW")
        + "\n\n"
        + formatear_vuelo(waw_alc, "WAW", "ALC")
    )

    enviar_telegram(cabecera + cuerpo)
    print("Mensaje enviado correctamente.")


if __name__ == "__main__":
    main()
