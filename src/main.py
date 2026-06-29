from __future__ import annotations

import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from wizzair import buscar_wizzair

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RYANAIR_URL = "https://www.ryanair.com/api/farfnd/v4/oneWayFares/{origen}/{destino}/cheapestPerDay"
HEADERS_RYANAIR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-ES,es;q=0.9",
}


# ── Ryanair ──────────────────────────────────────────────────────────────────

def buscar_ryanair(origen: str, destino: str) -> list[dict]:
    """Precio por día de los próximos ~4 meses (endpoint cheapestPerDay, una
    llamada por mes). Devuelve lista ordenada de más barato a más caro."""
    hoy = datetime.now(timezone.utc)
    limite = (hoy + timedelta(days=120)).strftime("%Y-%m-%d")
    hoy_iso = hoy.strftime("%Y-%m-%d")
    url = RYANAIR_URL.format(origen=origen, destino=destino)

    vuelos: list[dict] = []
    # Mes actual + 4 siguientes (cubre 120 días con margen)
    año, mes = hoy.year, hoy.month
    for _ in range(5):
        mes_str = f"{año:04d}-{mes:02d}-01"
        try:
            r = requests.get(
                url,
                params={"outboundMonthOfDate": mes_str, "currency": "EUR", "market": "es-es"},
                headers=HEADERS_RYANAIR,
                timeout=15,
            )
            r.raise_for_status()
            fares = r.json().get("outbound", {}).get("fares", [])
            for f in fares:
                precio = (f.get("price") or {}).get("value")
                dia = f.get("day", "")
                if (precio is None or f.get("soldOut") or f.get("unavailable")
                        or not dia or dia < hoy_iso or dia > limite):
                    continue
                vuelos.append({
                    "precio": precio,
                    "moneda": f["price"].get("currencySymbol", "€"),
                    "fecha_salida": dia,
                    "hora_salida": f.get("departureDate", "")[11:16] or "?",
                    "hora_llegada": f.get("arrivalDate", "")[11:16] or "?",
                    "vuelo": "",
                    "aerolinea": "Ryanair",
                    "origen": origen,
                    "destino": destino,
                })
        except Exception as e:
            print(f"Ryanair {origen}→{destino} {mes_str}: {e}")
        mes += 1
        if mes > 12:
            mes, año = 1, año + 1

    vuelos.sort(key=lambda v: v["precio"])
    return vuelos


# ── Formato y Telegram ────────────────────────────────────────────────────────

# Alternativas hasta MARGEN € por encima del mínimo (por si una fecha mejor cuesta poco más)
MARGEN = 15
MAX_OPCIONES = 3
_DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _dia_semana(fecha_iso: str) -> tuple[str, str, bool]:
    """Devuelve (abreviatura_dia, fecha_corta dd/mm, es_finde)."""
    d = datetime.strptime(fecha_iso, "%Y-%m-%d")
    idx = d.weekday()  # 0=lun … 6=dom
    return _DIAS[idx], d.strftime("%d/%m"), idx >= 5


def _enlace(v: dict) -> str:
    fecha = v["fecha_salida"]
    if v["aerolinea"] == "Ryanair":
        return (
            "https://www.ryanair.com/es/es/trip/flights/select?"
            f"adults=1&teens=0&children=0&infants=0&dateOut={fecha}&dateIn="
            "&isConnectedFlight=false&discount=0&isReturn=false&promoCode="
            f"&originIata={v['origen']}&destinationIata={v['destino']}"
        )
    # Wizz Air
    return (
        "https://www.wizzair.com/es-es/booking/select-flight/"
        f"{v['origen']}/{v['destino']}/{fecha}/{fecha}/1/0/0/null"
    )


def _linea_opcion(v: dict, minimo: float) -> str:
    simbolo = "€" if v["moneda"] in ("EUR", "€") else v["moneda"]
    dia, fecha_corta, finde = _dia_semana(v["fecha_salida"])
    marca = " 🟢" if finde else ""
    horas = (
        f" · {v['hora_salida']}→{v['hora_llegada']}"
        if v.get("hora_salida") and v["hora_salida"] != "?"
        else ""
    )
    extra = v["precio"] - minimo
    delta = f" (+{extra:.0f}{simbolo})" if extra > 0 else ""
    texto = f"{v['precio']:.0f}{simbolo} · {dia} {fecha_corta}{marca}{horas}{delta}"
    return f'  • <a href="{_enlace(v)}">{texto}</a>'


def formatear(vuelos: list[dict] | None, label_origen: str, label_destino: str) -> str:
    cabecera = f"✈️ <b>{label_origen} → {label_destino}</b>"
    if not vuelos:
        return cabecera + "\nSin vuelos directos disponibles en los próximos 4 meses."
    vuelos = sorted(vuelos, key=lambda v: v["precio"])
    minimo = vuelos[0]["precio"]
    seleccion = [v for v in vuelos if v["precio"] <= minimo + MARGEN][:MAX_OPCIONES]
    lineas = [_linea_opcion(v, minimo) for v in seleccion]
    return (
        f"{cabecera}\n"
        f"🏢 {vuelos[0]['aerolinea']} · {vuelos[0]['origen']}→{vuelos[0]['destino']}\n"
        + "\n".join(lineas)
    )


def enviar_telegram(mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": int(TELEGRAM_CHAT_ID.strip()),
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload)
    if not r.ok:
        print(f"Telegram error {r.status_code}: {r.text}")
    r.raise_for_status()


def main():
    # Wizz Air: una sola sesión devuelve ambas direcciones
    wz_ida, wz_vuelta = buscar_wizzair("ALC", "WAW")

    # Ryanair (Modlin)
    ry_ida = buscar_ryanair("ALC", "WMI")
    ry_vuelta = buscar_ryanair("WMI", "ALC")

    hoy_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    cabecera = (
        f"🗓️ <b>Vuelos baratos — {hoy_str}</b>\n"
        f"<i>Proximos 4 meses · Ryanair (WMI) + Wizz Air (WAW)</i>\n\n"
    )
    cuerpo = "\n\n".join([
        formatear(ry_ida,    "Alicante (ALC)", "Varsovia Modlin (WMI)"),
        formatear(ry_vuelta, "Varsovia Modlin (WMI)", "Alicante (ALC)"),
        formatear(wz_ida,    "Alicante (ALC)", "Varsovia Chopin (WAW)"),
        formatear(wz_vuelta, "Varsovia Chopin (WAW)", "Alicante (ALC)"),
    ])

    mensaje = cabecera + cuerpo
    print(mensaje)
    enviar_telegram(mensaje)
    print("\nMensaje enviado correctamente.")


if __name__ == "__main__":
    main()
