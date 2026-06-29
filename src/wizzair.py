"""
Búsqueda de vuelos Wizz Air mediante Playwright (navegador headless).

Su API interna bloquea peticiones desde IPs de centros de datos.
Playwright simula un navegador real, intercepta las respuestas de su
propia API mientras navega el calendario de precios mes a mes.
"""

import asyncio
from datetime import datetime, timezone

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


_MESES_A_NAVEGAR = 4


async def _aceptar_cookies(page) -> None:
    """Acepta el banner de cookies/GDPR de Wizz Air."""
    try:
        btn = page.get_by_role("button", name="Aceptar todo")
        await btn.wait_for(state="visible", timeout=8000)
        await btn.click()
        print("Wizz Air: cookies aceptadas")
        await page.wait_for_timeout(1500)
    except PlaywrightTimeout:
        # Si no aparece el banner, continuamos igualmente
        pass


async def _esperar_precios(page) -> bool:
    """Espera a que los precios del calendario sean visibles."""
    # El spinner desaparece y aparecen los precios en el carrusel
    selectores = [
        ".flight-list-item__fare",
        "[class*='fare-price']",
        "[class*='flight-list__price']",
        "text=/\\d+ €/",
        "[data-test='flight-card']",
    ]
    for sel in selectores:
        try:
            await page.locator(sel).first.wait_for(state="visible", timeout=10000)
            print(f"Wizz Air: precios visibles ({sel})")
            return True
        except PlaywrightTimeout:
            continue
    # Si no encontramos el selector específico, esperamos un tiempo fijo
    await page.wait_for_timeout(8000)
    return False


async def _avanzar_mes(page) -> bool:
    """Pulsa el botón de siguiente mes en el carrusel de fechas."""
    selectores = [
        # Botón con clase next en el carrusel de fechas
        "button.bw-flight-list__button--next",
        "[class*='flight-list'][class*='next']",
        # Botón SVG flecha derecha en la cabecera del calendario
        "button:has(svg[class*='arrow-right'])",
        "button:has(svg[class*='chevron-right'])",
        # Por aria-label
        "button[aria-label='Next']",
        "button[aria-label='Siguiente']",
        # El > visible en la imagen está en el carrusel de días
        ".bw-carousel__button--next",
        "[class*='carousel'][class*='next']",
        "[class*='carousel__button--next']",
    ]
    for sel in selectores:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await page.wait_for_timeout(3000)
                return True
        except PlaywrightTimeout:
            continue
    return False


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
                    vuelos = data.get("outboundFlights", [])
                    print(f"Wizz Air API: {len(vuelos)} vuelos capturados")
                    for vuelo in vuelos:
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
                except Exception as e:
                    print(f"Wizz Air: error parseando respuesta API: {e}")

        page.on("response", capturar_respuesta)

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

        # 1. Aceptar cookies inmediatamente (antes de que bloquee la carga)
        await _aceptar_cookies(page)

        # 2. Esperar a que los precios del primer mes sean visibles
        await _esperar_precios(page)

        # Screenshot de diagnóstico (primer mes ya cargado)
        try:
            await page.screenshot(path=f"/tmp/wizz_{origen}_{destino}.png")
        except Exception:
            pass

        # 3. Navegar mes a mes
        for mes in range(1, _MESES_A_NAVEGAR):
            avanzado = await _avanzar_mes(page)
            if avanzado:
                await _esperar_precios(page)
                print(f"Wizz Air: mes +{mes} cargado")
            else:
                # Log de botones disponibles para depuración
                print(f"Wizz Air: no se encontró botón siguiente en mes +{mes}")
                try:
                    btns = await page.locator("button").all()
                    for b in btns[:15]:
                        txt = (await b.inner_text()).strip()
                        cls = (await b.get_attribute("class") or "")[:50]
                        if txt or "next" in cls.lower() or "arrow" in cls.lower():
                            print(f"  [{cls}] '{txt[:40]}'")
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
