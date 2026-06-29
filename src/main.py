import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from wizzair import buscar_wizzair

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RYANAIR_URL = "https://www.ryanair.com/api/farfnd/v4/oneWayFares"
HEADERS_RYANAIR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-ES,es;q=0.9",
}


def _fechas_rango(dias: int = 120, paso: int = 7) -> list[str]:
    """Genera fechas semanales para los próximos N días."""
    hoy = datetime.now(timezone.utc)
    return [
        (hoy + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(0, dias, paso)
    ]


# ── Ryanair ──────────────────────────────────────────────────────────────────

def buscar_ryanair(origen: str, destino: str) -> dict | None:
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
        r = requests.get(RYANAIR_URL, params=params, headers=HEADERS_RYANAIR, timeout=15)
        r.raise_for_status()
        fares = r.json().get("fares", [])
        disponibles = [
            f for f in fares
            if f.get("outbound") and f["outbound"].get("price")
            and f["outbound"]["price"].get("value") is not None
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
        print(f"Ryanair {origen}→{destino}: {e}")
        return None


# ── Comparar candidatos ───────────────────────────────────────────────────────

def mejor_de(*vuelos) -> dict | None:
    candidatos = [v for v in vuelos if v]
    if not candidatos:
        return None
    return min(candidatos, key=lambda v: v["precio"])


# ── Formato y Telegram ────────────────────────────────────────────────────────

def formatear(vuelo: dict | None, label_origen: str, label_destino: str) -> str:
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


def enviar_telegram(mensaje: str) -> None:
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
    fechas = _fechas_rango()

    # ALC → Varsovia
    ry_ida = buscar_ryanair("ALC", "WMI")   # Ryanair usa Modlin
    wz_ida = buscar_wizzair("ALC", "WAW", fechas)  # Wizz Air usa Chopin
    ida = mejor_de(ry_ida, wz_ida)

    # Varsovia → ALC
    ry_vuelta = buscar_ryanair("WMI", "ALC")
    wz_vuelta = buscar_wizzair("WAW", "ALC", fechas)
    vuelta = mejor_de(ry_vuelta, wz_vuelta)

    hoy_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    cabecera = (
        f"🗓️ <b>Vuelos baratos — {hoy_str}</b>\n"
        f"<i>Proximos 4 meses · Ryanair (WMI) + Wizz Air (WAW)</i>\n\n"
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
