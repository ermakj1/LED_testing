#!/usr/bin/env python3
"""
Fetch weather for Kirkland, WA and send to LED display.

Uses Open-Meteo (free, no API key).

Usage:
    python3 feeds/weather.py                # every 30 min
    python3 feeds/weather.py --interval 60  # every hour
    python3 feeds/weather.py --once         # send once and exit
"""

import time
import json
import argparse
import urllib.request

BOARD_URL = "http://matrixportal.local:8080/add"

LATITUDE  = 47.6815
LONGITUDE = -122.2087
TIMEZONE  = "America/Los_Angeles"

# WMO weather code → display condition
def wmo_to_condition(code):
    if code == 0:                       return "sunny"
    if code in (1, 2):                  return "sunny"
    if code == 3:                       return "cloudy"
    if code in (45, 48):                return "cloudy"
    if code in (51, 53, 55, 56, 57):   return "rain"
    if code in (61, 63, 65, 66, 67):   return "rain"
    if code in (71, 73, 75, 77):       return "snow"
    if code in (80, 81, 82):            return "rain"
    if code in (85, 86):                return "snow"
    if code in (95, 96, 99):            return "storm"
    return "cloudy"

def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&current=weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&temperature_unit=fahrenheit"
        f"&timezone={TIMEZONE.replace('/', '%2F')}"
        "&forecast_days=1"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())

    condition = wmo_to_condition(data["current"]["weather_code"])
    high      = round(data["daily"]["temperature_2m_max"][0])
    low       = round(data["daily"]["temperature_2m_min"][0])
    precip    = data["daily"]["precipitation_probability_max"][0]
    return condition, high, low, precip

def post_to_board(condition, high, low, precip, ttl_minutes):
    payload = {
        "category": "weather",
        "condition": condition,
        "high": high,
        "low": low,
        "precip": precip,
        "ttl_minutes": ttl_minutes,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BOARD_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())

def main():
    parser = argparse.ArgumentParser(description="Send Kirkland weather to LED display")
    parser.add_argument("--interval", type=float, default=30, help="Update interval in minutes (default: 30)")
    parser.add_argument("--once", action="store_true", help="Send once and exit")
    args = parser.parse_args()

    interval = args.interval
    ttl = interval + 5

    if not args.once:
        print(f"Sending weather every {interval} min to {BOARD_URL}")

    while True:
        try:
            condition, high, low, precip = fetch_weather()
            result = post_to_board(condition, high, low, precip, ttl)
            print(f"{condition}  H:{high}  L:{low}  precip:{precip}%  → {result}")
        except Exception as e:
            print(f"Error: {e}")

        if args.once:
            break
        time.sleep(interval * 60)

if __name__ == "__main__":
    main()
