"""
Búsqueda de vuelos Wizz Air mediante Playwright (navegador headless).

Su API interna bloquea peticiones desde IPs de centros de datos.
Playwright simula un navegador real, intercepta las respuestas de su
propia API mientras navega el calendario de precios mes a mes.
"""

import asyncio
from datetime import datetime, timezone

from playwright.async_api import async_playwright


_MESES_A_NAVEGAR = 4  # cuántos meses hacia adelante buscar


async def _buscar_async(origen: str, destino: str) -> dict | None:
    mejor = None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            viewport={"width": 1366, "height": 768},
        )
        page = await context.new_page()

        # Interceptar respuestas de la API de búsqueda de Wizz Air
        async def capturar_respuesta(response):
            nonlocal mejor
            if "Api/search/search" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    for vuelo in data.get("outboundFlights", []):
                        precio = vuelo.get("price", {}).get("amount")
                        if precio is None:
                            continue
                        if mejor is None or precio < mejor["precio"]:
                            dep = vuelo.get("departureDateTimeUtc", "")
                            arr = vuelo.get("arrivalDateTimeUtc", "")
                            mejor = {
                                "precio": precio,
                                "moneda": vuelo["price"].get("currencyCode", "EUR"),
                                "fecha_salida": dep[:10] if dep else "?",
                                "hora_salida": dep[11:16] if len(dep) > 11 else "?",
                                "hora_llegada": arr[11:16] if len(arr) > 11 else "?",
                                "vuelo": vuelo.get("flightNumber", ""),
                                "aerolinea": "Wizz Air",
                                "origen": origen,
                                "destino": destino,
                            }
                except Exception:
                    pass

        page.on("response", capturar_respuesta)

        # Visitar la página de selección de vuelo (fecha = hoy)
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = (
            f"https://www.wizzair.com/es-es/booking/select-flight"
            f"/{origen}/{destino}/{hoy}/null/1/0/0/null"
        )
        print(f"Wizz Air Playwright: abriendo {url}")

        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"Wizz Air Playwright: timeout cargando página inicial: {e}")

        # Navegar mes a mes para cargar más precios
        for mes in range(1, _MESES_A_NAVEGAR):
            try:
                # Botón "siguiente mes" en el carrusel de fechas
                btn = page.locator(
                    "button.bw-flight-list__button--next, "
                    "[data-test='carousel-next'], "
                    "button[aria-label='Next month'], "
                    "button[aria-label='Siguiente mes']"
                ).first
                await btn.click(timeout=5000)
                await page.wait_for_load_state("networkidle", timeout=10000)
                print(f"Wizz Air Playwright: navegado al mes +{mes}")
            except Exception as e:
                print(f"Wizz Air Playwright: no se pudo avanzar al mes +{mes}: {e}")
                break

        await browser.close()

    if mejor:
        print(f"Wizz Air {origen}→{destino}: {mejor['precio']} {mejor['moneda']} el {mejor['fecha_salida']}")
    else:
        print(f"Wizz Air {origen}→{destino}: sin resultados")

    return mejor


def buscar_wizzair(origen: str, destino: str) -> dict | None:
    """Punto de entrada síncrono para usar desde main.py."""
    return asyncio.run(_buscar_async(origen, destino))
