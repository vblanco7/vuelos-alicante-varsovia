# Vuelos Alicante ↔ Varsovia

Agente que busca diariamente el vuelo directo más barato entre Alicante (ALC) y Varsovia (WAW) en los próximos 4 meses y lo envía por Telegram.

## Stack

- **Python 3.12** — script de búsqueda
- **Kiwi Tequila API** — búsqueda de vuelos (gratuita)
- **Telegram Bot API** — notificaciones
- **GitHub Actions** — scheduler gratuito (se ejecuta cada día a las 9:00 hora España)

## Configuración

### 1. Variables de entorno

Copia `.env.example` a `.env` y rellena los valores para pruebas locales:

```bash
cp .env.example .env
```

### 2. Secrets en GitHub Actions

En `Settings → Secrets and variables → Actions` añade:

| Secret | Descripción |
|--------|-------------|
| `TELEGRAM_TOKEN` | Token del bot (de @BotFather) |
| `TELEGRAM_CHAT_ID` | Tu chat ID numérico |
| `KIWI_API_KEY` | API key de tequila.kiwi.com |

### 3. Ejecución local

```bash
pip install -r requirements.txt
python src/main.py
```

## Ejemplo de mensaje Telegram

```
🗓️ Vuelos baratos — 29/06/2026
Rango: próximos 4 meses

✈️ ALC → WAW
💶 Precio: 54 €
📅 Salida: 15/07/2026 06:45
🛬 Llegada: 15/07/2026 10:30
🏢 Aerolínea: FR
🔗 Ver vuelo

✈️ WAW → ALC
💶 Precio: 61 €
📅 Salida: 22/07/2026 11:20
🛬 Llegada: 22/07/2026 14:55
🏢 Aerolínea: FR
🔗 Ver vuelo
```
