# display_agent

Runs on a Windows machine and sends scheduled content to the LED display.
Receives `person_detected` and `wifi_off` events from the board via HTTP callback.
Optionally uses Claude API to generate interesting messages.

## What it sends

| Content | When |
|---------|------|
| Weather | Every 30 min |
| Stock price | Every 5 min, 9am–5pm |
| Joke | Every 45 min |
| Animation | Every 20 min |
| On-this-day fact | Once per day at 8am |
| Claude message | Every 60 min |

On `person_detected` (PIR wakes the board): if the queue is empty, Claude generates a greeting/interesting message.

All intervals are configurable in `config.toml`.

## Setup

**1. Install Python 3.11+**
Download from https://python.org. Check "Add Python to PATH" during install.

**2. Install dependencies**
```
cd agent
pip install -r requirements.txt
```

**3. Create config**
```
copy config.toml.example config.toml
```
Edit `config.toml`:
- Set `board.url` — use the board's IP address if `matrixportal.local` doesn't resolve on Windows
- Set `anthropic.api_key` — get one at https://console.anthropic.com (or leave blank to disable Claude)
- Set your location in `content.weather_lat` / `content.weather_lon`
- Set `agent.callback_host` to this machine's local IP (e.g. `192.168.1.50`). Leave blank to auto-detect.

**4. Test it**
```
python display_agent.py
```
You should see log output like:
```
08:00:01  display_agent starting
08:00:01  Claude enabled (model: claude-haiku-4-5-20251001)
08:00:01  Callback server on port 8090 (reachable at 192.168.1.50:8090)
08:00:02  Registered callback: http://192.168.1.50:8090/
08:00:03  → [weather] cloudy H:58 L:44
```

## Run automatically on Windows (Task Scheduler)

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Task** (not Basic Task)
3. **General tab**:
   - Name: `LED Display Agent`
   - Check **Run whether user is logged on or not**
   - Check **Run with highest privileges**
4. **Triggers tab** → New:
   - Begin the task: **At startup**
   - Delay task for: 1 minute (gives network time to connect)
5. **Actions tab** → New:
   - Program: `C:\path\to\python.exe`
   - Arguments: `C:\path\to\LED_testing\agent\display_agent.py`
   - Start in: `C:\path\to\LED_testing\agent\`
6. **Settings tab**:
   - Check **If the task is already running, do not start a new instance**
7. Click OK, enter Windows password when prompted

To find your Python path: run `where python` in a command prompt.

## Networking note

The board and this machine must be on the same local network.
The board posts callbacks to `http://<callback_host>:<callback_port>/` — make sure
Windows Firewall allows inbound connections on the callback port (default 8090).

To open the port in Windows Firewall:
```
netsh advfirewall firewall add rule name="LED Agent Callback" protocol=TCP dir=in localport=8090 action=allow
```
