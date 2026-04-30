# renderers.py - one render function per message category
#
# Call init() once after display/hardware setup, then render(msg) for each message.
# Each renderer returns: 'done' | 'skip' | 'clear' | 'sleep'

import time
import random
import displayio
import terminalio
from adafruit_display_text import label

PANEL_WIDTH  = 64
PANEL_HEIGHT = 32
SCROLL_DELAY = 0.04

ICON_W = 16
ICON_H = 16
ICON_X = 0
ICON_Y = (PANEL_HEIGHT - ICON_H) // 2  # = 8

GREETING_COLOR = 0xFF8C00  # warm orange

# Injected via init()
_display         = None
_server          = None
_pir             = None
_btn_up          = None
_btn_down        = None
_last_motion_ref = None  # mutable list [float] shared with code.py
_sleep_timeout   = None


def init(display, server, pir, btn_up, btn_down, last_motion_ref, sleep_timeout):
    global _display, _server, _pir, _btn_up, _btn_down, _last_motion_ref, _sleep_timeout
    _display         = display
    _server          = server
    _pir             = pir
    _btn_up          = btn_up
    _btn_down        = btn_down
    _last_motion_ref = last_motion_ref
    _sleep_timeout   = sleep_timeout


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _poll():
    """Poll server, update PIR timestamp, check buttons. Returns action or None."""
    _server.poll()
    if _pir.value:
        _last_motion_ref[0] = time.monotonic()
    if not _btn_up.value:
        return "skip"
    if not _btn_down.value:
        return "clear"
    if time.monotonic() - _last_motion_ref[0] > _sleep_timeout:
        return "sleep"
    return None


def _scroll_label(lbl, start_x=None):
    """Scroll lbl from right edge to off-screen left. Returns action."""
    text_width = lbl.bounding_box[2]
    if start_x is None:
        start_x = PANEL_WIDTH
    for x in range(start_x, -text_width - 1, -1):
        action = _poll()
        if action:
            return action
        lbl.x = x
        time.sleep(SCROLL_DELAY)
    return "done"


def _hold(seconds):
    """Hold the current display for N seconds. Returns action or 'done'."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        action = _poll()
        if action:
            return action
        time.sleep(0.05)
    return "done"


def _bg(color):
    """Return a full-panel background TileGrid in the given color."""
    bm  = displayio.Bitmap(PANEL_WIDTH, PANEL_HEIGHT, 1)
    pal = displayio.Palette(1)
    pal[0] = color
    return displayio.TileGrid(bm, pixel_shader=pal, x=0, y=0)


def _flash(color, duration=0.15):
    """Briefly flood the display with color (e.g. green/red on stock move)."""
    grp = displayio.Group()
    grp.append(_bg(color))
    _display.root_group = grp
    time.sleep(duration)


def _clock_color():
    """Return a time-of-day color for the clock."""
    h = time.localtime().tm_hour
    if 5  <= h < 8:  return 0xFF6600  # dawn — orange
    if 8  <= h < 17: return 0xFFFFFF  # day  — white
    if 17 <= h < 20: return 0xFF8800  # dusk — amber
    return 0x4466FF                    # night — blue


# ---------------------------------------------------------------------------
# Icon drawing (16×16 bitmap, transparent background)
# ---------------------------------------------------------------------------

# Palette indices
_BG      = 0
_WHITE   = 1
_YELLOW  = 2
_ORANGE  = 3
_BLUE    = 4
_LTBLUE  = 5
_GRAY    = 6
_LTGRAY  = 7


def _make_icon_palette():
    p = displayio.Palette(8)
    p.make_transparent(_BG)
    p[_WHITE]  = 0xFFFFFF
    p[_YELLOW] = 0xFFDD00
    p[_ORANGE] = 0xFF8800
    p[_BLUE]   = 0x3388FF
    p[_LTBLUE] = 0x88CCFF
    p[_GRAY]   = 0x888888
    p[_LTGRAY] = 0xBBBBBB
    return p


def _clear_icon(bm):
    for y in range(ICON_H):
        for x in range(ICON_W):
            bm[x, y] = _BG


# Sun: circle core + 8 rays alternating bright/dim each frame
_SUN_CORE = [(dx, dy) for dy in range(-3, 4) for dx in range(-3, 4) if dx*dx + dy*dy <= 10]
_SUN_RAYS = [
    ((7, 2),  (7, 1)),    # N
    ((11, 3), (12, 2)),   # NE
    ((12, 7), (13, 7)),   # E
    ((11, 11),(12, 12)),  # SE
    ((7, 12), (7, 13)),   # S
    ((3, 11), (2, 12)),   # SW
    ((2, 7),  (1, 7)),    # W
    ((3, 3),  (2, 2)),    # NW
]

def _draw_sun(bm, frame):
    _clear_icon(bm)
    for dx, dy in _SUN_CORE:
        bm[7 + dx, 7 + dy] = _YELLOW
    for i, (inner, outer) in enumerate(_SUN_RAYS):
        color = _YELLOW if (i + frame) % 2 == 0 else _ORANGE
        for px, py in (inner, outer):
            if 0 <= px < ICON_W and 0 <= py < ICON_H:
                bm[px, py] = color


# Rain: falling blue drops with short tail
def _init_drops(n=7):
    return [(random.randint(0, ICON_W - 1), random.randint(0, ICON_H - 1)) for _ in range(n)]

def _draw_rain(bm, drops):
    _clear_icon(bm)
    new_drops = []
    for x, y in drops:
        if 0 <= y < ICON_H:
            bm[x, y] = _BLUE
        if 0 <= y - 1 < ICON_H:
            bm[x, y - 1] = _LTBLUE
        ny = y + 2
        nx = x
        if ny >= ICON_H:
            ny = random.randint(-3, 0)
            nx = random.randint(0, ICON_W - 1)
        new_drops.append((nx, ny))
    return new_drops


# Snow: slow drifting white flakes
def _init_flakes(n=6):
    return [(random.randint(0, ICON_W - 1), random.randint(0, ICON_H - 1)) for _ in range(n)]

def _draw_snow(bm, flakes, frame):
    _clear_icon(bm)
    new_flakes = []
    for x, y in flakes:
        if 0 <= x < ICON_W and 0 <= y < ICON_H:
            bm[x, y] = _WHITE
        ny = y + 1
        nx = x + (1 if frame % 8 < 4 else -1)
        if ny >= ICON_H:
            ny = 0
            nx = random.randint(0, ICON_W - 1)
        new_flakes.append((nx % ICON_W, ny))
    return new_flakes


# Cloud: gray blob with slow pulse
_CLOUD_PX = [
    (6,4),(7,4),(8,4),(9,4),
    (5,5),(6,5),(7,5),(8,5),(9,5),(10,5),
    (3,6),(4,6),(5,6),(6,6),(7,6),(8,6),(9,6),(10,6),(11,6),(12,6),
    (3,7),(4,7),(5,7),(6,7),(7,7),(8,7),(9,7),(10,7),(11,7),(12,7),
    (3,8),(4,8),(5,8),(6,8),(7,8),(8,8),(9,8),(10,8),(11,8),(12,8),
    (4,9),(5,9),(6,9),(7,9),(8,9),(9,9),(10,9),(11,9),
]

def _draw_cloud(bm, frame):
    _clear_icon(bm)
    color = _LTGRAY if (frame // 4) % 2 == 0 else _GRAY
    for px, py in _CLOUD_PX:
        if 0 <= px < ICON_W and 0 <= py < ICON_H:
            bm[px, py] = color


# Storm: cloud + rain + occasional lightning bolt
_LIGHTNING = [(7,9),(7,10),(8,11),(8,12),(7,13)]

def _draw_storm(bm, drops, frame):
    drops = _draw_rain(bm, drops)
    for px, py in _CLOUD_PX:
        if 0 <= px < ICON_W and 0 <= py < ICON_H:
            bm[px, py] = _GRAY
    if frame % 24 < 3:
        for px, py in _LIGHTNING:
            if 0 <= px < ICON_W and 0 <= py < ICON_H:
                bm[px, py] = _WHITE
    return drops


def _condition_to_icon(condition):
    c = condition.lower()
    if any(w in c for w in ("sun", "clear", "fair")):      return "sun"
    if any(w in c for w in ("snow", "blizzard", "flurr")): return "snow"
    if any(w in c for w in ("storm", "thunder")):           return "storm"
    if any(w in c for w in ("rain", "shower", "drizzle")):  return "rain"
    return "cloud"


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------

def render(msg):
    """Dispatch to the right renderer based on category."""
    category = msg.get("category", "")
    if category == "weather":  return render_weather(msg)
    if category == "stock":    return render_stock(msg)
    if category == "news":     return render_news(msg)
    if category == "calendar": return render_calendar(msg)
    if category == "joke":     return render_joke(msg)
    return render_generic(msg)


_WDAYS  = ("Mon","Tue","Wed","Thu","Fri","Sat","Sun")
_MONTHS = ("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec")

def render_clock():
    """Show time + date for ~1 second, polling server. Returns action or 'done'."""
    t        = time.localtime()
    color    = _clock_color()
    hour     = t.tm_hour % 12 or 12
    time_str = f"{hour}:{t.tm_min:02}"
    date_str = f"{_WDAYS[t.tm_wday]} {_MONTHS[t.tm_mon-1]} {t.tm_mday}"

    time_lbl = label.Label(terminalio.FONT, text=time_str, color=color)
    time_lbl.x = 0
    time_lbl.y = 0
    time_grp = displayio.Group(scale=2)
    time_grp.x = (PANEL_WIDTH - len(time_str) * 6 * 2) // 2
    time_grp.y = 10
    time_grp.append(time_lbl)

    date_lbl = label.Label(terminalio.FONT, text=date_str, color=0x444444)
    date_lbl.x = (PANEL_WIDTH - len(date_str) * 6) // 2
    date_lbl.y = 25

    group = displayio.Group()
    group.append(time_grp)
    group.append(date_lbl)

    # Seconds progress bar along the bottom — dimmed version of clock color
    bar_w = max(1, int(t.tm_sec * PANEL_WIDTH / 60))
    bar_bm  = displayio.Bitmap(bar_w, 1, 1)
    bar_pal = displayio.Palette(1)
    r = ((color >> 16) & 0xFF) >> 3
    g = ((color >> 8)  & 0xFF) >> 3
    b = (color         & 0xFF) >> 3
    bar_pal[0] = (r << 16) | (g << 8) | b
    group.append(displayio.TileGrid(bar_bm, pixel_shader=bar_pal, x=0, y=31))

    _display.root_group = group

    end = time.monotonic() + 1
    while time.monotonic() < end:
        action = _poll()
        if action:
            return action
        time.sleep(0.05)
    return "done"


def render_greeting(text):
    lbl = label.Label(terminalio.FONT, text=text, color=GREETING_COLOR)
    lbl.y = PANEL_HEIGHT // 2 - 3
    group = displayio.Group()
    group.append(lbl)
    _display.root_group = group
    return _scroll_label(lbl)


def render_generic(msg):
    lbl = label.Label(terminalio.FONT, text=msg.get("text", ""), color=0xFFFFFF)
    lbl.y = PANEL_HEIGHT // 2 - 3
    group = displayio.Group()
    group.append(_bg(0x0A0A0A))
    group.append(lbl)
    _display.root_group = group
    return _scroll_label(lbl)


def render_news(msg):
    lbl = label.Label(terminalio.FONT, text=msg.get("text", ""), color=0xDD88FF)
    lbl.y = PANEL_HEIGHT // 2 - 3
    group = displayio.Group()
    group.append(_bg(0x0C0018))
    group.append(lbl)
    _display.root_group = group
    return _scroll_label(lbl)


def render_calendar(msg):
    time_str = msg.get("time", "")
    text     = msg.get("text", "")
    full     = f"{time_str}: {text}" if time_str else text
    lbl = label.Label(terminalio.FONT, text=full, color=0xFFEE44)
    lbl.y = PANEL_HEIGHT // 2 - 3
    group = displayio.Group()
    group.append(_bg(0x0C0A00))
    group.append(lbl)
    _display.root_group = group
    return _scroll_label(lbl)


def render_stock(msg):
    symbol     = msg.get("symbol", "???").upper()
    change_pct = float(msg.get("change", 0))
    price      = float(msg.get("price", 0))
    is_up      = change_pct >= 0
    chg_color  = 0x00FF44 if is_up else 0xFF3300
    bg_color   = 0x001500 if is_up else 0x150000
    sign       = "+" if is_up else "-"

    prev_close    = price / (1 + change_pct / 100) if price else 0
    dollar_change = abs(price - prev_close)

    # Flash the panel on significant moves (>= 2%)
    if abs(change_pct) >= 2:
        _flash(0x003300 if is_up else 0x330000)

    sym_lbl = label.Label(terminalio.FONT, text=symbol, color=0xFFFFFF)
    sym_lbl.x = 2
    sym_lbl.y = 6

    price_lbl = label.Label(terminalio.FONT, text=f"${price:.2f}", color=0xAAAAAA)
    price_lbl.x = 2
    price_lbl.y = 16

    chg_lbl = label.Label(terminalio.FONT, text="", color=chg_color)
    chg_lbl.x = 2
    chg_lbl.y = 26

    group = displayio.Group()
    group.append(_bg(bg_color))
    group.append(sym_lbl)
    group.append(price_lbl)
    group.append(chg_lbl)
    _display.root_group = group

    # Toggle between $ and % change every 3 seconds
    for show_pct in [False, True, False, True]:
        chg_lbl.text = f"{sign}{abs(change_pct):.2f}%" if show_pct else f"{sign}${dollar_change:.2f}"
        result = _hold(3)
        if result and result != "done":
            return result
    return "done"


def render_joke(msg):
    setup    = msg.get("setup", msg.get("text", ""))
    delivery = msg.get("delivery", "")
    joke_bg  = 0x080A00  # dark green-tinted black

    if setup:
        lbl = label.Label(terminalio.FONT, text=setup, color=0xFFCC44)
        lbl.y = PANEL_HEIGHT // 2 - 3
        grp = displayio.Group()
        grp.append(_bg(joke_bg))
        grp.append(lbl)
        _display.root_group = grp
        result = _scroll_label(lbl)
        if result and result != "done":
            return result

    if not delivery:
        return "done"

    # Animated "..." — dots appear one by one, then hold
    for dots in (".", "..", "..."):
        dot_lbl = label.Label(terminalio.FONT, text=dots, color=0x668833)
        dot_lbl.x = (PANEL_WIDTH - len(dots) * 6) // 2
        dot_lbl.y = PANEL_HEIGHT // 2 - 3
        grp = displayio.Group()
        grp.append(_bg(joke_bg))
        grp.append(dot_lbl)
        _display.root_group = grp
        result = _hold(0.5)
        if result and result != "done":
            return result

    # Punchline
    lbl = label.Label(terminalio.FONT, text=delivery, color=0xFFFF88)
    lbl.y = PANEL_HEIGHT // 2 - 3
    grp = displayio.Group()
    grp.append(_bg(joke_bg))
    grp.append(lbl)
    _display.root_group = grp
    return _scroll_label(lbl)


def render_weather(msg):
    condition = msg.get("condition", "")
    high      = msg.get("high",   None)
    low       = msg.get("low",    None)
    precip    = msg.get("precip", None)
    icon_type = _condition_to_icon(condition)

    # Randomly place icon on left or right half
    icon_on_left = random.choice([True, False])
    icon_x = 0  if icon_on_left else 32
    text_x = 34 if icon_on_left else 2

    # Icon: 16x16 bitmap scaled x2 to fill a 32x32 half
    icon_bm   = displayio.Bitmap(ICON_W, ICON_H, 8)
    icon_pal  = _make_icon_palette()
    icon_tile = displayio.TileGrid(icon_bm, pixel_shader=icon_pal)
    icon_grp  = displayio.Group(scale=2)
    icon_grp.x = icon_x
    icon_grp.y = 0
    icon_grp.append(icon_tile)

    # Static text: high, low, precip on the other half
    group = displayio.Group()
    group.append(_bg(0x000A18))
    group.append(icon_grp)

    def add_label(text, color, y):
        lbl = label.Label(terminalio.FONT, text=text, color=color)
        lbl.x = text_x
        lbl.y = y
        group.append(lbl)

    if high   is not None: add_label(f"H:{int(high)}", 0xFF8844, 4)
    if low    is not None: add_label(f"L:{int(low)}",  0x4499FF, 13)
    if precip is not None: add_label(f"{int(precip)}%",0x44CCFF, 22)

    _display.root_group = group

    state = _init_drops() if icon_type in ("rain", "storm") else \
            _init_flakes() if icon_type == "snow" else None

    frame = 0
    end   = time.monotonic() + 6
    while time.monotonic() < end:
        action = _poll()
        if action:
            return action
        if frame % 3 == 0:
            icon_frame = frame // 3
            if   icon_type == "sun":   _draw_sun(icon_bm, icon_frame)
            elif icon_type == "rain":  state = _draw_rain(icon_bm, state)
            elif icon_type == "snow":  state = _draw_snow(icon_bm, state, icon_frame)
            elif icon_type == "storm": state = _draw_storm(icon_bm, state, icon_frame)
            elif icon_type == "cloud": _draw_cloud(icon_bm, icon_frame)
        frame += 1
        time.sleep(0.05)
    return "done"
