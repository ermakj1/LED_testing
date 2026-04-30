# LED Display

A CircuitPython-powered RGB LED matrix display with a WiFi API, animated message queue, and sensor integration.

## Hardware

| Part | Details |
|------|---------|
| [Adafruit MatrixPortal S3](https://www.adafruit.com/product/5778) | ESP32-S3 based controller |
| 64×32 RGB LED Matrix | HUB75 interface, connected directly to MatrixPortal |
| [Mini PIR Motion Sensor](https://www.adafruit.com/product/4871) | Wired to A1, 3.3V, GND |

### PIR Wiring

| PIR pin | MatrixPortal S3 |
|---------|----------------|
| VIN     | 3 (3.3V)        |
| GND     | GND             |
| OUT     | A1              |

## Software

- **CircuitPython 10.x** on the board
- Python 3 on the host machine for feed scripts (no extra packages required)

## Setup

1. Copy `settings.toml.example` to `/Volumes/CIRCUITPY/settings.toml` and fill in your WiFi credentials and a web API password
2. Deploy code to the board: `./deploy.sh`
3. Run feed scripts from your computer: `python3 feeds/stock.py`, `python3 feeds/weather.py`
4. Open the web UI: `http://matrixportal.local:8080/ui`

## Deploying

```bash
./deploy.sh              # USB deploy (board plugged into laptop)
./deploy.sh --wifi       # WiFi deploy (board on charger)
./deploy.sh --wifi --with-lib  # WiFi deploy including lib/ folder
```

WiFi deploy uses the board's own `/upload` endpoint on port 8080. The board must be running and on the same network.

## Board endpoints (port 8080)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/add` | POST | Add a message to the queue |
| `/delete` | POST | Delete a message by id |
| `/clear` | POST | Clear the queue |
| `/` | GET | Current queue as JSON |
| `/schema` | GET | Message categories and field definitions |
| `/log` | GET | Live log viewer (auto-refreshes) |
| `/ui` | GET | Web control panel |
| `/wake` | POST | Wake the display from sleep |
| `/pir/enable` | POST | Enable motion detection |
| `/pir/disable` | POST | Disable motion detection |
| `/usb/enable` | POST | Enable USB drive (board reboots) |
| `/usb/disable` | POST | Disable USB drive (board reboots) |
| `/upload` | POST | Upload a file (used by deploy.sh) |
| `/reload` | POST | Soft-reload the board |

## Message categories

Send a POST to `/add` with JSON:

**News**
```json
{"category": "news", "text": "Headline here", "ttl_minutes": 60}
```

**Weather**
```json
{"category": "weather", "condition": "sunny", "high": 75, "low": 52, "precip": 10, "ttl_minutes": 120}
```

**Stock**
```json
{"category": "stock", "symbol": "MSFT", "price": 407.78, "change": -2.3, "ttl_minutes": 5}
```

**Calendar**
```json
{"category": "calendar", "time": "2pm", "text": "Dentist", "ttl_minutes": 120}
```

**Text** (generic scrolling)
```json
{"category": "text", "text": "Hello world", "ttl_minutes": 60}
```

## Feed scripts

| Script | Description |
|--------|-------------|
| `feeds/stock.py` | MSFT stock price from Yahoo Finance, every 5 min during market hours |
| `feeds/weather.py` | Kirkland WA weather from Open-Meteo, every 30 min |
| `feeds/jokes.py` | Random joke from JokeAPI, every 30 min |

All feed scripts support `--once` to send a single update and exit, and `--interval N` to change the update frequency.

## Board behavior

- **Clock** shown when queue is empty. Color shifts with time of day (orange at dawn, white during day, amber at dusk, blue at night). Seconds shown as a progress bar along the bottom.
- **Sleep** triggered by PIR inactivity timeout (5 min). UP button wakes, DOWN button sleeps. Can also be controlled from the web UI.
- **USB drive** disabled by default (enables WiFi deploy). Use the web UI to re-enable USB when you need to update libraries.
