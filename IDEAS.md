# Ideas

Things we might build later. Not prioritized.

## Feed ideas

- **Sports scores** — live game scores for teams you follow (NHL, NFL, NBA all have free APIs). Flash the panel on a goal/score.
- **News headlines** — RSS feed from AP or Reuters, cycle through top stories
- **Countdown timers** — "Lions game in 2h 14m", "Mila's birthday in 4 days"
- **Word of the day** — one interesting word scrolling in the morning
- **Package tracking** — "UPS out for delivery" type alerts
- **Calendar feed** — pull from Google Calendar automatically instead of manual entry
- **Crypto prices** — same pattern as stock feed
- **Home alerts** — doorbell, garage door, etc. triggered by Home Assistant

## Display ideas

- **Gradient text** — headline text that fades from white to the category color (complex on CircuitPython, requires per-character color)
- **Pixel art icons** for news, calendar, text categories (currently only weather has icons)
- **Smoother scrolling** — subpixel or variable speed based on text length
- **AM/PM indicator** — small colored dot on the clock instead of text
- **Weekday vs weekend clock color** — different palette on weekends

## Integration ideas

- **Google Home** — trigger routines on person detected via IFTTT webhooks or Home Assistant
- **Home Assistant** — run on old Windows PC, bridge between board events and smart home
- **`feeds/run.py`** — single script to run all feeds together with configurable schedule
- **launchd / Task Scheduler** — auto-start feeds on login (Mac / Windows)
