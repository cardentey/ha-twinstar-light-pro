"""Constants for the Twinstar integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN = "twinstar"
CONF_MAC = "mac_address"
CONF_POLL_INTERVAL = "poll_interval"

# Default configuration values
DEFAULT_POLL_INTERVAL = 5

# BLE
WRITE_UUID = "0000dead-0000-1000-8000-00805f9b34fb"
READ_UUID = "0000fef4-0000-1000-8000-00805f9b34fb"
CMD_ON = bytearray.fromhex("6f6e00")
CMD_OFF = bytearray.fromhex("6f666600")
CMD_POWERSTATUS = b"powerstatus"

# Color channels
CHANNEL_BRIGHTNESS = "A"
CHANNEL_RED = "R"
CHANNEL_GREEN = "G"
CHANNEL_BLUE = "B"
CHANNEL_WHITE = "W"

# Platforms
PLATFORMS: list[str] = ["light", "number", "time", "button"]

# Schedule programming (default values for the BLE timer)
DEFAULT_START_TIME = "09:00"
DEFAULT_END_TIME = "21:00"
DEFAULT_SUNRISE_MIN = 30
DEFAULT_SUNSET_MIN = 30


# All channels for the number sliders (including overall brightness A):
# (command prefix, translation key, icon)
ALL_CHANNELS: list[tuple[str, str, str]] = [
    (CHANNEL_BRIGHTNESS, "brightness", "mdi:brightness-7"),
    (CHANNEL_RED, "red", "mdi:palette"),
    (CHANNEL_GREEN, "green", "mdi:palette"),
    (CHANNEL_BLUE, "blue", "mdi:palette"),
    (CHANNEL_WHITE, "white", "mdi:white-balance-sunny"),
]


def get_device_info(mac: str) -> DeviceInfo:
    """Build the DeviceInfo shared by all entities of a device."""
    mac_short = mac[-5:] if mac else "Unknown"
    return DeviceInfo(
        identifiers={(DOMAIN, mac)},
        translation_key="aquarium",
        translation_placeholders={"mac": mac_short},
        manufacturer="Twinstar",
        model="Bluetooth LED Controller",
        sw_version="1.0.0",
    )