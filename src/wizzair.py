"""
Búsqueda de vuelos Wizz Air mediante Playwright (navegador headless).

Su API interna bloquea peticiones desde IPs de centros de datos.
Playwright simula un navegador real, intercepta las respuestas de su
propia API mientras navega el calendario de precios mes a mes.
"""

import asyncio
from datetime import datetime, timezone

from playwright.async_api import async_playwright


_MESES_A_NAVEGAR = 4


async def _aceptar_cookies(page) -> None:
    """Intenta cerrar banners de cookies/GDPR."""
    selectores = [
        "button#cookiescript_accept",
        "button[data-test='accept-cookies']",
        "button.cookie-accept",
        "#onetrust-accept-btn-handler",
        "button:has-text('Accept')",
        "button:has-text('Aceptar')",
        "button:has-text('Accept all')",
        "button:has-text('Aceptar todo')",
    ]
    for sel in selectores:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click(timeout=3000)
                print("Wizz Air Playwright: cookies aceptadas")
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue


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

        # Interceptar respuestas de la API de búsqueda
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
                    print(f"Wizz Air API capturada: {len(data.get('outboundFlights', []))} vuelos")
                except Exception as e:
                    print(f"Wizz Air: error parseando respuesta: {e}")

        page.on("response", capturar_respuesta)

        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = (
            f"https://www.wizzair.com/es-es/booking/select-flight"
            f"/{origen}/{destino}/{hoy}/null/1/0/0/null"
        )
        print(f"Wizz Air Playwright: {origen}→{destino}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Esperar carga dinámica
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"Wizz Air Playwright: error cargando página: {e}")

        # Guardar screenshot para depuración
        try:
            await page.screenshot(path=f"/tmp/wizz_{origen}_{destino}.png")
            print(f"Wizz Air Playwright: screenshot guardado en /tmp/wizz_{origen}_{destino}.png")
        except Exception:
            pass

        # Aceptar cookies si aparece el banner
        await _aceptar_cookies(page)
        await page.wait_for_timeout(3000)

        # Navegar mes a mes
        # Wizz Air usa distintos selectores según la versión del front
        selectores_siguiente = [
            "button.bw-flight-list__button--next",
            "button[class*='next']",
            "[data-test='carousel-next']",
            "button[aria-label='Next']",
            "button[aria-label='Siguiente']",
            "button svg[class*='arrow-right']",
            ".flight-list__nav--next",
        ]

        for mes in range(1, _MESES_A_NAVEGAR):
            avanzado = False
            for sel in selectores_siguiente:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click(timeout=3000)
                        await page.wait_for_timeout(3000)
                        print(f"Wizz Air Playwright: mes +{mes} cargado")
                        avanzado = True
                        break
                except Exception:
                    continue
            if not avanzado:
                print(f"Wizz Air Playwright: no se pudo avanzar al mes +{mes}, botones disponibles:")
                try:
                    btns = await page.locator("button").all()
                    for b in btns[:10]:
                        txt = await b.inner_text()
                        cls = await b.get_attribute("class") or ""
                        print(f"  [{cls[:40]}] '{txt[:30]}'")
                except Exception:
                    pass
                break

        await browser.close()

    if mejor:
        print(f"Wizz Air {origen}→{destino}: {mejor['precio']} {mejor['moneda']} el {mejor['fecha_salida']}")
    else:
        print(f"Wizz Air {origen}→{destino}: sin resultados")

    return mejor


def buscar_wizzair(origen: str, destino: str) -> dict | None:
    return asyncio.run(_buscar_async(origen, destino))
