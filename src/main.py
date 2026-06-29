import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RYANAIR_URL = "https://www.ryanair.com/api/farfnd/v4/oneWayFares"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-ES,es;q=0.9",
}


def buscar_ryanair(origen, destino):
    hoy = datetime.now(timezone.utc)
    fin = hoy + timedelta(days=120)
    params = {
        "departureAirportIataCode": origen,
        "arrivalAirportIataCode": destino,
        "outboundDepartureDateFrom": hoy.strftime("%Y-%m-%d"),
        "outboundDepartureDateTo": fin.strftime("%Y-%m-%d"),
        "market": "es-es",
        "currency": "EUR",
    }
    try:
        r = requests.get(RYANAIR_URL, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        fares = r.json().get("fares", [])
        disponibles = [
            f for f in fares
            if f.get("outbound") and f["outbound"].get("price") and f["outbound"]["price"].get("value") is not None
        ]
        if not disponibles:
            return None
        mejor = min(disponibles, key=lambda f: f["outbound"]["price"]["value"])
        ob = mejor["outbound"]
        return {
            "precio": ob["price"]["value"],
            "moneda": ob["price"].get("currencySymbol", "€"),
            "fecha_salida": ob["departureDate"][:10],
            "hora_salida": ob["departureDate"][11:16],
            "hora_llegada": ob["arrivalDate"][11:16],
            "vuelo": ob.get("flightNumber", ""),
            "aerolinea": "Ryanair",
            "origen": origen,
            "destino": destino,
        }
    except Exception as e:
        print(f"Error Ryanair {origen}→{destino}: {e}")
        return None


def mejor_vuelo(origen_principal, origen_alt, destino_principal, destino_alt):
    """Busca en ambos aeropuertos de Varsovia y devuelve el más barato."""
    r1 = buscar_ryanair(origen_principal, destino_principal)
    r2 = buscar_ryanair(origen_alt, destino_alt)
    candidatos = [v for v in [r1, r2] if v]
    if not candidatos:
        return None
    return min(candidatos, key=lambda v: v["precio"])


def formatear(vuelo, label_origen, label_destino):
    if not vuelo:
        return (
            f"✈️ <b>{label_origen} → {label_destino}</b>\n"
            f"Sin vuelos directos disponibles en los próximos 4 meses."
        )
    return (
        f"✈️ <b>{label_origen} → {label_destino}</b>\n"
        f"🏢 {vuelo['aerolinea']} {vuelo['vuelo']} · {vuelo['origen']}→{vuelo['destino']}\n"
        f"💶 Precio: <b>{vuelo['precio']:.0f} {vuelo['moneda']}</b>\n"
        f"📅 {vuelo['fecha_salida']}  {vuelo['hora_salida']} → {vuelo['hora_llegada']}"
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
    # ALC → Varsovia: prueba WMI (Modlin) y WAW (Chopin)
    ida = mejor_vuelo("ALC", "ALC", "WMI", "WAW")
    # Varsovia → ALC: prueba desde WMI y WAW
    vuelta = mejor_vuelo("WMI", "WAW", "ALC", "ALC")

    hoy_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    cabecera = (
        f"🗓️ <b>Vuelos baratos — {hoy_str}</b>\n"
        f"<i>Proximos 4 meses · WMI (Modlin) + WAW (Chopin)</i>\n\n"
    )
    cuerpo = (
        formatear(ida, "Alicante (ALC)", "Varsovia")
        + "\n\n"
        + formatear(vuelta, "Varsovia", "Alicante (ALC)")
    )

    mensaje = cabecera + cuerpo
    print(mensaje)
    enviar_telegram(mensaje)
    print("\nMensaje enviado correctamente.")


if __name__ == "__main__":
    main()
