from __future__ import annotations

"""
Búsqueda de vuelos Wizz Air usando Playwright + asset/farechart.

Estrategia:
1. Cargar la home (warm-up de sesión y Kasada)
2. Navegar al booking page (ALC↔WAW)
3. Llamar asset/farechart via page.evaluate() — Kasada hookea fetch()
   automáticamente y añade los tokens x-kpsdk-*
4. Hacer 6 llamadas con dayInterval=10, cada una centrada 20 días más
   adelante, para cubrir los próximos 4 meses
5. Devolver el vuelo más barato en cada dirección
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# URL de booking — usada solo para inicializar la sesión en be.wizzair.com
_BOOKING_URL = (
    "https://www.wizzair.com/es-es/booking/select-flight"
    "/{origen}/{destino}/{hoy}/{hoy}/1/0/0/null"
)

_FARECHART_JS = """
async (payload) => {
    const tokenMatch = document.cookie.match(/RequestVerificationToken=([^;]+)/);
    const csrfToken = tokenMatch ? decodeURIComponent(tokenMatch[1]) : '';
    try {
        const resp = await fetch("https://be.wizzair.com/29.4.0/Api/asset/farechart", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "x-requestverificationtoken": csrfToken,
            },
            body: JSON.stringify(payload),
            credentials: "include",
        });
        if (!resp.ok) return {error: resp.status};
        return {data: await resp.json()};
    } catch(e) {
        return {error: e.toString()};
    }
}
"""


def _mejor_vuelo(vuelos: list, origen: str, destino: str) -> dict | None:
    mejor = None
    for v in vuelos:
        precio = v.get("price", {}).get("amount")
        if not precio:  # None o 0 = sin vuelo en esa fecha
            continue
        if mejor is None or precio < mejor["precio"]:
            dep = v.get("date", "")
            mejor = {
                "precio": precio,
                "moneda": v.get("price", {}).get("currencyCode", "EUR"),
                "fecha_salida": dep[:10] if dep else "?",
                "hora_salida": "?",
                "hora_llegada": "?",
                "vuelo": "",
                "aerolinea": "Wizz Air",
                "origen": origen,
                "destino": destino,
            }
    return mejor


async def _buscar_async(origen: str, destino: str) -> tuple[dict | None, dict | None]:
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            viewport={"width": 1366, "height": 768},
            extra_http_headers={
                "sec-ch-ua": '"Google Chrome";v="124", "Chromium";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        # 1. Warm-up: cargar home para inicializar sesión y Kasada
        print(f"Wizz Air: cargando home (warm-up)...")
        try:
            await page.goto(
                "https://www.wizzair.com/es-es",
                wait_until="networkidle",
                timeout=30000,
            )
            await page.get_by_role("button", name="Aceptar todo").click(timeout=6000)
            await page.wait_for_timeout(3000)
        except Exception:
            pass

        # 2. Navegar al booking page para establecer contexto en be.wizzair.com
        booking_url = _BOOKING_URL.format(origen=origen, destino=destino, hoy=hoy)
        print(f"Wizz Air: cargando booking page {origen}→{destino}...")
        try:
            await page.goto(booking_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Wizz Air: error cargando booking: {e}")
            await browser.close()
            return None, None

        # 3. Llamar farechart 6 veces cubriendo 4 meses (~20 días por llamada)
        todos_outbound: list = []
        todos_return: list = []
        base = datetime.now(timezone.utc)

        for i in range(6):
            centro = (base + timedelta(days=10 + i * 20)).strftime("%Y-%m-%dT00:00:00")
            payload = {
                "isRescueFare": False,
                "adultCount": 1,
                "childCount": 0,
                "dayInterval": 10,
                "wdc": False,
                "isFlightChange": False,
                "flightList": [
                    {"departureStation": origen, "arrivalStation": destino, "date": centro},
                    {"departureStation": destino, "arrivalStation": origen, "date": centro},
                ],
            }
            try:
                result = await page.evaluate(_FARECHART_JS, payload)
                if "error" in result:
                    print(f"Wizz Air farechart [{i+1}/6] error: {result['error']}")
                    continue
                data = result.get("data", {})
                outbound = data.get("outboundFlights", [])
                ret = data.get("returnFlights", [])
                todos_outbound.extend(outbound)
                todos_return.extend(ret)
                print(f"Wizz Air farechart [{i+1}/6] centro={centro[:10]}: {len(outbound)} out / {len(ret)} ret")
            except Exception as e:
                print(f"Wizz Air farechart [{i+1}/6] excepción: {e}")

        await browser.close()

    mejor_ida = _mejor_vuelo(todos_outbound, origen, destino)
    mejor_vuelta = _mejor_vuelo(todos_return, destino, origen)

    if mejor_ida:
        print(f"Wizz Air {origen}→{destino}: {mejor_ida['precio']} EUR el {mejor_ida['fecha_salida']}")
    else:
        print(f"Wizz Air {origen}→{destino}: sin resultados")

    if mejor_vuelta:
        print(f"Wizz Air {destino}→{origen}: {mejor_vuelta['precio']} EUR el {mejor_vuelta['fecha_salida']}")
    else:
        print(f"Wizz Air {destino}→{origen}: sin resultados")

    return mejor_ida, mejor_vuelta


def buscar_wizzair(origen: str, destino: str) -> tuple[dict | None, dict | None]:
    """
    Devuelve (mejor_ida, mejor_vuelta) o (None, None) si no hay datos.
    Cada resultado es un dict con: precio, moneda, fecha_salida, aerolinea, origen, destino.
    """
    return asyncio.run(_buscar_async(origen, destino))
