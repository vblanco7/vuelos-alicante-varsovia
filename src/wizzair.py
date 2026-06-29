"""
Búsqueda de vuelos Wizz Air mediante Playwright (navegador headless).

Estrategia:
1. Abrir la página de selección de vuelo ALC↔WAW
2. Aceptar cookies
3. Pulsar "Mostrar próximo vuelo disponible" para saltar al primer vuelo
4. Abrir el "Gráfico de precios" que muestra un mes completo
5. Navegar 4 meses interceptando las respuestas de la API interna
"""

import asyncio
from datetime import datetime, timezone

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


async def _aceptar_cookies(page) -> None:
    try:
        btn = page.get_by_role("button", name="Aceptar todo")
        await btn.wait_for(state="visible", timeout=8000)
        await btn.click()
        await page.wait_for_timeout(1500)
        print("Wizz Air: cookies aceptadas")
    except PlaywrightTimeout:
        pass


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

        # Interceptar todas las respuestas de búsqueda
        async def capturar(response):
            nonlocal mejor
            if "Api/search/" not in response.url or response.status != 200:
                return
            try:
                data = await response.json()
                # search/search devuelve outboundFlights
                vuelos = data.get("outboundFlights", [])
                # search/farechart devuelve una estructura diferente
                if not vuelos:
                    for key in ("outboundFlights", "flights", "fares"):
                        vuelos = data.get(key, [])
                        if vuelos:
                            break
                if vuelos:
                    print(f"Wizz Air API ({response.url.split('Api/search/')[-1].split('?')[0]}): {len(vuelos)} vuelos")
                for vuelo in vuelos:
                    precio = (
                        vuelo.get("price", {}).get("amount")
                        or vuelo.get("regularFare", {}).get("fares", [{}])[0].get("amount")
                    )
                    if precio is None:
                        continue
                    if mejor is None or precio < mejor["precio"]:
                        dep = vuelo.get("departureDateTimeUtc") or vuelo.get("departureDate", "")
                        arr = vuelo.get("arrivalDateTimeUtc") or vuelo.get("arrivalDate", "")
                        mejor = {
                            "precio": precio,
                            "moneda": (
                                vuelo.get("price", {}).get("currencyCode")
                                or vuelo.get("currency", "EUR")
                            ),
                            "fecha_salida": dep[:10] if dep else "?",
                            "hora_salida": dep[11:16] if len(dep) > 11 else "?",
                            "hora_llegada": arr[11:16] if len(arr) > 11 else "?",
                            "vuelo": vuelo.get("flightNumber", ""),
                            "aerolinea": "Wizz Air",
                            "origen": origen,
                            "destino": destino,
                        }
            except Exception as e:
                print(f"Wizz Air: error parseando respuesta: {e}")

        page.on("response", capturar)

        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = (
            f"https://www.wizzair.com/es-es/booking/select-flight"
            f"/{origen}/{destino}/{hoy}/null/1/0/0/null"
        )
        print(f"Wizz Air Playwright: {origen}→{destino}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"Wizz Air Playwright: error cargando página: {e}")
            await browser.close()
            return None

        await _aceptar_cookies(page)
        await page.wait_for_timeout(3000)

        # Paso 1: pulsar "Mostrar próximo vuelo disponible" si no hay vuelos hoy
        try:
            btn_proximo = page.get_by_role("button", name="Mostrar próximo vuelo disponible")
            await btn_proximo.wait_for(state="visible", timeout=5000)
            await btn_proximo.click()
            await page.wait_for_timeout(3000)
            print("Wizz Air: saltando al primer vuelo disponible")
        except PlaywrightTimeout:
            print("Wizz Air: hay vuelos en la fecha inicial, continuando")

        # Paso 2: abrir el gráfico de precios (carga un mes completo)
        try:
            btn_grafico = page.get_by_text("MOSTRAR GRÁFICO DE PRECIOS")
            await btn_grafico.wait_for(state="visible", timeout=5000)
            await btn_grafico.click()
            await page.wait_for_timeout(4000)
            print("Wizz Air: gráfico de precios abierto")

            # Paso 3: navegar meses en el gráfico de precios
            for mes in range(1, 4):
                try:
                    btn_next = page.locator("button").filter(has_text=">").last
                    if not await btn_next.is_visible(timeout=2000):
                        # Buscar por aria o clase
                        btn_next = page.locator("[class*='next'], [aria-label*='next'], [aria-label*='Siguiente']").last
                    await btn_next.click(timeout=3000)
                    await page.wait_for_timeout(3000)
                    print(f"Wizz Air: gráfico mes +{mes} cargado")
                except Exception as e:
                    print(f"Wizz Air: no pudo avanzar mes en gráfico +{mes}: {e}")
                    break
        except PlaywrightTimeout:
            print("Wizz Air: no se encontró el gráfico de precios, usando vista de lista")

        # Screenshot final para diagnóstico
        try:
            await page.screenshot(path=f"/tmp/wizz_{origen}_{destino}.png")
        except Exception:
            pass

        # Paso 4 (fallback): si el gráfico no funcionó, navegar por el carrusel de días
        if mejor is None:
            print("Wizz Air: intentando navegación por carrusel de días")
            for _ in range(16):  # ~16 clicks × ~7 días = ~4 meses
                try:
                    btn = page.locator("button[class*='next'], button[aria-label*='Next']").last
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(2000)
                except PlaywrightTimeout:
                    break

        await browser.close()

    if mejor:
        print(f"Wizz Air {origen}→{destino}: {mejor['precio']} {mejor['moneda']} el {mejor['fecha_salida']}")
    else:
        print(f"Wizz Air {origen}→{destino}: sin resultados")

    return mejor


def buscar_wizzair(origen: str, destino: str) -> dict | None:
    return asyncio.run(_buscar_async(origen, destino))
