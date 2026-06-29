"""
Módulo de búsqueda de vuelos Wizz Air (ALC ↔ WAW).

Wizz Air no tiene API pública documentada. Usamos su API interna
detectando la versión desde su web y estableciendo sesión antes de buscar.
"""

import re
import time
import uuid
import requests

WIZZ_HOME = "https://www.wizzair.com"
WIZZ_BE = "https://be.wizzair.com"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Origin": WIZZ_HOME,
})


def _obtener_version_api() -> str | None:
    """Lee la versión de la API de Wizz Air desde su web."""
    try:
        r = SESSION.get(f"{WIZZ_HOME}/", timeout=10, allow_redirects=True)
        match = re.search(r"be\.wizzair\.com/(\d+\.\d+\.\d+)", r.text)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Wizz Air: no se pudo obtener versión de API: {e}")
    return None


def _establecer_sesion(version: str, origen: str, destino: str) -> bool:
    """Visita la página de búsqueda para obtener cookies de sesión."""
    url = (
        f"{WIZZ_HOME}/es-es/booking/select-flight"
        f"/{origen}/{destino}/2026-09-01/null/1/0/0/null"
    )
    try:
        r = SESSION.get(url, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"Wizz Air: error estableciendo sesión: {e}")
        return False


def _buscar_vuelo(version: str, origen: str, destino: str, fecha: str) -> dict | None:
    """Llama al endpoint de búsqueda para una fecha concreta."""
    url = f"{WIZZ_BE}/{version}/Api/search/search"
    headers = {
        "Referer": (
            f"{WIZZ_HOME}/es-es/booking/select-flight"
            f"/{origen}/{destino}/{fecha}/null/1/0/0/null"
        ),
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "x-requestid": str(uuid.uuid4()),
    }
    payload = {
        "isFlightChange": False,
        "isSeniorOrStudent": False,
        "flightList": [{"departureStation": origen, "arrivalStation": destino, "date": fecha}],
        "adultCount": 1,
        "childCount": 0,
        "infantCount": 0,
        "wdc": False,
    }
    try:
        r = SESSION.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 429:
            print(f"Wizz Air: rate limit en {origen}→{destino} {fecha}, reintentando en 5s...")
            time.sleep(5)
            r = SESSION.post(url, json=payload, headers=headers, timeout=15)
        if not r.ok:
            print(f"Wizz Air: HTTP {r.status_code} en {origen}→{destino} {fecha}")
            return None
        return r.json()
    except Exception as e:
        print(f"Wizz Air: error en búsqueda {origen}→{destino} {fecha}: {e}")
        return None


def _extraer_precio_minimo(data: dict) -> dict | None:
    """Extrae el vuelo más barato de la respuesta de search."""
    if not data:
        return None
    outbound_flights = data.get("outboundFlights", [])
    disponibles = [
        f for f in outbound_flights
        if f.get("price") and f["price"].get("amount") is not None
    ]
    if not disponibles:
        return None
    mejor = min(disponibles, key=lambda f: f["price"]["amount"])
    dep = mejor.get("departureDateTimeUtc", "")
    arr = mejor.get("arrivalDateTimeUtc", "")
    return {
        "precio": mejor["price"]["amount"],
        "moneda": mejor["price"].get("currencyCode", "EUR"),
        "fecha_salida": dep[:10] if dep else "?",
        "hora_salida": dep[11:16] if len(dep) > 11 else "?",
        "hora_llegada": arr[11:16] if len(arr) > 11 else "?",
        "vuelo": mejor.get("flightNumber", ""),
        "aerolinea": "Wizz Air",
        "origen": mejor.get("departureStation", ""),
        "destino": mejor.get("arrivalStation", ""),
    }


def buscar_wizzair(origen: str, destino: str, fechas: list[str]) -> dict | None:
    """
    Busca el vuelo Wizz Air más barato entre origen y destino
    en las fechas indicadas (lista de strings 'YYYY-MM-DD').
    """
    version = _obtener_version_api()
    if not version:
        print("Wizz Air: no se pudo detectar versión de API.")
        return None

    print(f"Wizz Air API version: {version}")
    _establecer_sesion(version, origen, destino)

    mejor = None
    for fecha in fechas:
        data = _buscar_vuelo(version, origen, destino, fecha)
        vuelo = _extraer_precio_minimo(data)
        if vuelo:
            if mejor is None or vuelo["precio"] < mejor["precio"]:
                mejor = vuelo
        time.sleep(1)  # pausa entre llamadas para no saturar

    return mejor
