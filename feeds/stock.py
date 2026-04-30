#!/usr/bin/env python3
"""
Fetch stock price and send to LED display.

Usage:
    python3 feeds/stock.py                        # MSFT every 5 min
    python3 feeds/stock.py --symbol AAPL          # different symbol
    python3 feeds/stock.py --interval 10          # every 10 min
    python3 feeds/stock.py --symbol TSLA --once   # send once and exit
"""

import time
import json
import argparse
import urllib.request

BOARD_URL = "http://matrixportal.local:8080/add"

def fetch_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    meta = data["chart"]["result"][0]["meta"]
    market_state = meta.get("marketState", "CLOSED")
    price = meta["regularMarketPrice"]
    prev_close = meta["chartPreviousClose"]
    change_pct = round((price - prev_close) / prev_close * 100, 2)
    return price, change_pct, market_state

def post_to_board(symbol, price, change, ttl_minutes):
    payload = {
        "category": "stock",
        "symbol": symbol,
        "price": round(price, 2),
        "change": change,
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
    parser = argparse.ArgumentParser(description="Send stock price to LED display")
    parser.add_argument("--symbol", default="MSFT", help="Ticker symbol (default: MSFT)")
    parser.add_argument("--interval", type=float, default=5, help="Update interval in minutes (default: 5)")
    parser.add_argument("--once", action="store_true", help="Send once and exit")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    interval = args.interval

    if not args.once:
        print(f"Sending {symbol} every {interval} min to {BOARD_URL}")

    while True:
        try:
            price, change, market_state = fetch_quote(symbol)
            if market_state == "CLOSED":
                print(f"{symbol}  market closed — skipping")
            else:
                result = post_to_board(symbol, price, change, ttl_minutes=interval)
                print(f"{symbol}  ${price:.2f}  {change:+.2f}%  → {result}")
        except Exception as e:
            print(f"Error: {e}")

        if args.once:
            break
        time.sleep(interval * 60)

if __name__ == "__main__":
    main()
