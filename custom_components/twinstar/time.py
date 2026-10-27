"""Time entities to program the Twinstar timer."""
from __future__ import annotations

import logging
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .ble_client import TwinstarBLEClient
from .const import DEFAULT_END_TIME, DEFAULT_START_TIME, get_device_info
from .schedule import async_send_schedule_command

_LOGGER = logging.getLogger(__name__)


def _parse_time_str(time_str: str, default_val: time) -> time:
    """Parse an ISO time string ('HH:MM:SS' or 'HH:MM') into a datetime.time object."""
    try:
        parts = time_str.split(":")
        if len(parts) >= 2:
            return time(int(parts[0]), int(parts[1]))
    except (ValueError, TypeError, IndexError):
        pass
    return default_val


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the time entities from a config entry."""
    runtime_data = entry.runtime_data
    mac_address = runtime_data.mac_address
    ble_client = runtime_data.ble_client

    async_add_entities(
        [
            TwinstarStartTime(mac_address, ble_client),
            TwinstarEndTime(mac_address, ble_client),
        ]
    )


class TwinstarTimeBase(TimeEntity, RestoreEntity):
    """Base class for Twinstar time entities."""

    def __init__(
        self,
        mac_address: str,
        translation_key: str,
        unique_suffix: str,
        icon: str,
        default_time: str,
        ble_client: TwinstarBLEClient,
    ) -> None:
        self._mac = mac_address
        self._ble_client = ble_client
        self._attr_has_entity_name = True
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"twinstar_{mac_address}_{unique_suffix}"
        self._attr_icon = icon
        self._default_time_obj = _parse_time_str(default_time, time(9, 0))
        self._value: time = self._default_time_obj

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return get_device_info(self._mac)

    async def async_added_to_hass(self) -> None:
        """Restore the last configured time."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            self._value = _parse_time_str(last_state.state, self._default_time_obj)
            _LOGGER.debug(
                "State restored: %s returns to %s",
                self.entity_id,
                self._value,
            )

    @property
    def native_value(self) -> time | None:
        """Return the selector's current time."""
        return self._value

    async def async_set_value(self, value: time) -> None:
        """Update the time and push the new schedule over BLE."""
        self._value = value
        self.async_write_ha_state()

        _LOGGER.debug("New time for %s: %s", self.entity_id, value)
        await async_send_schedule_command(self.hass, self._mac, self._ble_client)


class TwinstarStartTime(TwinstarTimeBase):
    """Selector for the aquarium's on time."""

    def __init__(self, mac_address: str, ble_client: TwinstarBLEClient) -> None:
        super().__init__(
            mac_address=mac_address,
            translation_key="start_time",
            unique_suffix="start_time",
            icon="mdi:weather-sunset-up",
            default_time=DEFAULT_START_TIME,
            ble_client=ble_client,
        )


class TwinstarEndTime(TwinstarTimeBase):
    """Selector for the aquarium's off time."""

    def __init__(self, mac_address: str, ble_client: TwinstarBLEClient) -> None:
        super().__init__(
            mac_address=mac_address,
            translation_key="end_time",
            unique_suffix="end_time",
            icon="mdi:weather-sunset-down",
            default_time=DEFAULT_END_TIME,
            ble_client=ble_client,
        )
