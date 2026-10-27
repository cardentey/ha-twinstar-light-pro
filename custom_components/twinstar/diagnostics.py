"""Diagnostics for Twinstar."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MAC, PLATFORMS


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostic information for the integration."""
    return {
        "mac_address": entry.data.get(CONF_MAC, "N/A"),
        "platforms": PLATFORMS,
        "entry_id": entry.entry_id,
    }
