import storage

try:
    with open("/usb_enabled", "r"):
        pass
    # flag present — USB drive mounts, code has read-only filesystem (default)
except OSError:
    # flag absent — disable USB drive, give code write access for WiFi deploy
    storage.disable_usb_drive()
    storage.remount("/", readonly=False)
