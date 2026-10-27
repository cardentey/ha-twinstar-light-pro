"""Shared helpers to program the schedule and sync the BLE clock on Twinstar."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .ble_client import TwinstarBLEClient
from .const import (
    DEFAULT_END_TIME,
    DEFAULT_START_TIME,
    DEFAULT_SUNRISE_MIN,
    DEFAULT_SUNSET_MIN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_sync_clock(ble_client: TwinstarBLEClient) -> bool:
    """Sync the Twinstar controller's internal clock to HA's current time.

    Sends a 14-digit ASCII string in the format 'YYYYMMDDHHMMSS'
    (example: '20260801132242').
    """
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    success = await ble_client.send_command(now_str)
    if success:
        _LOGGER.info(
            "Twinstar (%s): Internal clock synced successfully -> %s",
            ble_client.mac_address,
            now_str,
        )
    else:
        _LOGGER.error(
            "Twinstar (%s): Error syncing the internal clock (%s)",
            ble_client.mac_address,
            now_str,
        )
    return success


def _format_hhmm(val: str | None, default_time: str) -> str:
    """Extract 4 HHMM digits from a time string (e.g. '09:00:00' -> '0900')."""
    raw = str(val or default_time).replace(":", "")
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) >= 4:
        return digits[:4]
    return default_time.replace(":", "")[:4]


def _format_minutes(val: int | float | str | None, default_min: int) -> str:
    """Convert a ramp minutes value to integer format (e.g. 30 -> '30')."""
    try:
        min_int = int(float(val)) if val is not None else default_min
        min_int = max(0, min(60, min_int))
        return f"{min_int:02d}"
    except (ValueError, TypeError):
        return f"{default_min:02d}"


async def async_send_schedule_command(
    hass: HomeAssistant,
    mac_address: str,
    ble_client: TwinstarBLEClient,
    start_time: str | None = None,
    end_time: str | None = None,
    sunrise_minutes: int | None = None,
    sunset_minutes: int | None = None,
    sync_clock_first: bool = True,
) -> bool:
    """Build and send the schedule command to the Twinstar controller.

    Format: TOn:[On_Time]_[Off_Time]_[Sunrise_Minutes]_[Sunset_Minutes]
    Example: TOn:0900_2100_30_30

    Any parameter not given is looked up from the state of the sibling entities
    registered on the device in Home Assistant (or falls back to the defaults).
    """
    if (
        start_time is None
        or end_time is None
        or sunrise_minutes is None
        or sunset_minutes is None
    ):
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)
        device = dev_reg.async_get_device(identifiers={(DOMAIN, mac_address)})

        if device:
            for entity_entry in er.async_entries_for_device(ent_reg, device.id):
                uid = entity_entry.unique_id or ""
                state = hass.states.get(entity_entry.entity_id)
                if not state or state.state in ("unknown", "unavailable"):
                    continue

                if start_time is None and uid.endswith("_start_time"):
                    start_time = state.state
                elif end_time is None and uid.endswith("_end_time"):
                    end_time = state.state
                elif sunrise_minutes is None and uid.endswith("_sunrise_min"):
                    try:
                        sunrise_minutes = int(float(state.state))
                    except ValueError:
                        pass
                elif sunset_minutes is None and uid.endswith("_sunset_min"):
                    try:
                        sunset_minutes = int(float(state.state))
                    except ValueError:
                        pass

    start_str = _format_hhmm(start_time, DEFAULT_START_TIME)
    end_str = _format_hhmm(end_time, DEFAULT_END_TIME)
    sunrise_str = _format_minutes(sunrise_minutes, DEFAULT_SUNRISE_MIN)
    sunset_str = _format_minutes(sunset_minutes, DEFAULT_SUNSET_MIN)

    command = f"TOn:{start_str}_{end_str}_{sunrise_str}_{sunset_str}"

    if sync_clock_first:
        await async_sync_clock(ble_client)

    success = await ble_client.send_command(command)
    if success:
        _LOGGER.info(
            "Twinstar (%s): Schedule programmed on the controller -> %s",
            mac_address,
            command,
        )
    else:
        _LOGGER.error(
            "Twinstar (%s): Error programming the schedule (%s)",
            mac_address,
            command,
        )
    return success
