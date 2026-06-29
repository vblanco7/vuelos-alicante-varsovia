import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RYANAIR_URL = "https://www.ryanair.com/api/farfnd/v4/oneWayFares"
WIZZAIR_URL = "https://be.wizzair.com/14.5.0/Api/asset/calendar"

HEADERS_RYANAIR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}
HEADERS_WIZZAIR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "x-requestid": "alc-waw-bot",
}


def meses_rango(inicio: datetime, num_meses: int):
    meses = []
    for i in range(num_meses):
        año = inicio.year + (inicio.month + i - 1) // 12
        mes = (inicio.month + i - 1) % 12 + 1
        meses.append((año, mes))
    return meses


# ── Ryanair ──────────────────────────────────────────────────────────────────

def buscar_ryanair_mes(origen, destino, año, mes):
    params = {
        "departureAirportIataCode": origen,
        "arrivalAirportIataCode": destino,
        "outboundMonthOfDate": f"{año}-{mes:02d}-01",
        "market": "es-es",
    }
    try:
        r = requests.get(RYANAIR_URL, params=params, headers=HEADERS_RYANAIR, timeout=10)
        r.raise_for_status()
        fares = r.json().get("fares", [])
        disponibles = [
            f for f in fares
            if f.get("price") and f["price"].get("value") is not None
        ]
        if not disponibles:
            return None
        return min(disponibles, key=lambda f: f["price"]["value"])
    except Exception:
        return None


def buscar_ryanair(origen, destino):
    hoy = datetime.now(timezone.utc)
    mejor = None
    mejor_precio = float("inf")
    for año, mes in meses_rango(hoy, 4):
        fare = buscar_ryanair_mes(origen, destino, año, mes)
        if fare and fare["price"]["value"] < mejor_precio:
            mejor_precio = fare["price"]["value"]
            mejor = fare
    if not mejor:
        return None
    return {
        "precio": mejor["price"]["value"],
        "moneda": mejor["price"].get("currencySymbol", "€"),
        "fecha": mejor.get("day", "?"),
        "aerolinea": "Ryanair",
        "aeropuerto_destino": destino,
    }


# ── Wizz Air ─────────────────────────────────────────────────────────────────

def buscar_wizzair(origen, destino):
    hoy = datetime.now(timezone.utc)
    fin = hoy + timedelta(days=120)
    params = {
        "departureStation": origen,
        "arrivalStation": destino,
        "from": hoy.strftime("%Y-%m-%d"),
        "to": fin.strftime("%Y-%m-%d"),
        "priceType": "regular",
        "adultCount": 1,
        "childCount": 0,
        "infantCount": 0,
    }
    try:
        r = requests.get(WIZZAIR_URL, params=params, headers=HEADERS_WIZZAIR, timeout=10)
        r.raise_for_status()
        dias = r.json().get("flightDates", [])
        disponibles = [
            d for d in dias
            if d.get("price") and d["price"].get("amount") is not None
        ]
        if not disponibles:
            return None
        mejor = min(disponibles, key=lambda d: d["price"]["amount"])
        return {
            "precio": mejor["price"]["amount"],
            "moneda": mejor["price"].get("currencyCode", "EUR"),
            "fecha": mejor.get("date", "?")[:10],
            "aerolinea": "Wizz Air",
            "aeropuerto_destino": destino,
        }
    except Exception:
        return None


# ── Comparar y elegir el más barato ──────────────────────────────────────────

def mejor_vuelo_ida():
    """ALC → WAW/WMI: compara Ryanair (WMI) y Wizz Air (WAW)"""
    ryanair = buscar_ryanair("ALC", "WMI")
    wizzair = buscar_wizzair("ALC", "WAW")
    candidatos = [v for v in [ryanair, wizzair] if v]
    if not candidatos:
        return None
    return min(candidatos, key=lambda v: v["precio"])


def mejor_vuelo_vuelta():
    """WAW/WMI → ALC: compara Ryanair (WMI) y Wizz Air (WAW)"""
    ryanair = buscar_ryanair("WMI", "ALC")
    wizzair = buscar_wizzair("WAW", "ALC")
    candidatos = [v for v in [ryanair, wizzair] if v]
    if not candidatos:
        return None
    return min(candidatos, key=lambda v: v["precio"])


# ── Formato y Telegram ────────────────────────────────────────────────────────

def formatear(vuelo, etiqueta_origen, etiqueta_destino):
    if not vuelo:
        return f"✈️ <b>{etiqueta_origen} → {etiqueta_destino}</b>\nSin vuelos directos disponibles."

    aeropuerto = vuelo["aeropuerto_destino"]
    return (
        f"✈️ <b>{etiqueta_origen} → {etiqueta_destino}</b>\n"
        f"🏢 {vuelo['aerolinea']} · {aeropuerto}\n"
        f"💶 Precio: <b>{vuelo['precio']} {vuelo['moneda']}</b>\n"
        f"📅 Fecha: {vuelo['fecha']}"
    )


def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": int(TELEGRAM_CHAT_ID.strip()),
        "text": mensaje,
        "parse_mode": "HTML",
    }
    r = requests.post(url, json=payload)
    if not r.ok:
        print(f"Telegram error {r.status_code}: {r.text}")
    r.raise_for_status()


def main():
    ida = mejor_vuelo_ida()
    vuelta = mejor_vuelo_vuelta()

    hoy_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    cabecera = f"🗓️ <b>Vuelos baratos — {hoy_str}</b>\n<i>Proximos 4 meses · WAW + WMI</i>\n\n"
    cuerpo = (
        formatear(ida, "Alicante (ALC)", "Varsovia")
        + "\n\n"
        + formatear(vuelta, "Varsovia", "Alicante (ALC)")
    )

    mensaje = cabecera + cuerpo
    enviar_telegram(mensaje)
    print(mensaje)


if __name__ == "__main__":
    main()
