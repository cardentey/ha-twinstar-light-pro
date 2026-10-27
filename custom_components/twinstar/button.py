"""Button entity to sync the Twinstar BLE clock."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ble_client import TwinstarBLEClient
from .const import get_device_info
from .schedule import async_sync_clock

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sync button from a config entry."""
    runtime_data = entry.runtime_data
    mac_address = runtime_data.mac_address
    ble_client = runtime_data.ble_client

    async_add_entities([TwinstarSyncClockButton(mac_address, ble_client)])


class TwinstarSyncClockButton(ButtonEntity):
    """Button that syncs the HA server's current time to the Twinstar controller's internal clock."""

    def __init__(
        self,
        mac_address: str,
        ble_client: TwinstarBLEClient,
    ) -> None:
        self._mac = mac_address
        self._ble_client = ble_client
        self._attr_has_entity_name = True
        self._attr_translation_key = "sync_clock"
        self._attr_unique_id = f"twinstar_{mac_address}_sync_clock"
        self._attr_icon = "mdi:clock-sync"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return get_device_info(self._mac)

    async def async_press(self) -> None:
        """Button press action: send the current date/time (YYYYMMDDHHMMSS) to the device."""
        _LOGGER.debug("Clock sync button pressed for %s", self._mac)
        await async_sync_clock(self._ble_client)
