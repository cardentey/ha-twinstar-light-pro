"""Slider controls for Twinstar (RGBW + brightness)."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .ble_client import TwinstarBLEClient
from .const import (
    ALL_CHANNELS,
    DEFAULT_SUNRISE_MIN,
    DEFAULT_SUNSET_MIN,
    get_device_info,
)
from .schedule import async_send_schedule_command

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the number entities from a config entry."""
    runtime_data = entry.runtime_data
    mac_address = runtime_data.mac_address
    ble_client = runtime_data.ble_client

    sliders = [
        TwinstarColorNumber(mac_address, translation_key, prefix, icon, ble_client)
        for prefix, translation_key, icon in ALL_CHANNELS
    ]
    sliders.extend(
        [
            TwinstarScheduleNumber(
                mac_address,
                "sunrise_minutes",
                "sunrise_min",
                "mdi:sunrise",
                DEFAULT_SUNRISE_MIN,
                ble_client,
            ),
            TwinstarScheduleNumber(
                mac_address,
                "sunset_minutes",
                "sunset_min",
                "mdi:sunset",
                DEFAULT_SUNSET_MIN,
                ble_client,
            ),
        ]
    )
    async_add_entities(sliders)


class TwinstarColorNumber(NumberEntity, RestoreEntity):
    """A slider for one Twinstar channel."""

    def __init__(
        self,
        mac_address: str,
        translation_key: str,
        prefix: str,
        icon: str,
        ble_client: TwinstarBLEClient,
    ) -> None:
        self._mac = mac_address
        self._prefix = prefix
        self._ble_client = ble_client
        self._attr_has_entity_name = True
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"twinstar_{mac_address}_{prefix}"
        self._attr_icon = icon
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._value = 50

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info (shared with light.py)."""
        return get_device_info(self._mac)

    async def async_added_to_hass(self) -> None:
        """Restore the last known state right before startup."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            try:
                self._value = int(float(last_state.state))
                _LOGGER.debug(
                    "State restored: %s returns to %s%%",
                    self.entity_id,
                    self._value,
                )
            except ValueError:
                pass

    @property
    def native_value(self) -> int:
        """Return the slider's current value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the device over BLE."""
        new_value = int(value)
        command = f"{self._prefix}{new_value}"

        success = await self._ble_client.send_command(command)
        if success:
            self._value = new_value
            self.async_write_ha_state()
            _LOGGER.debug("Sent %s successfully", command)
        else:
            # On failure, force the UI back to the previous value
            self.async_write_ha_state()


class TwinstarScheduleNumber(NumberEntity, RestoreEntity):
    """Slider for the BLE timer's ramp durations (sunrise/sunset)."""

    def __init__(
        self,
        mac_address: str,
        translation_key: str,
        unique_suffix: str,
        icon: str,
        default_val: int,
        ble_client: TwinstarBLEClient,
    ) -> None:
        self._mac = mac_address
        self._ble_client = ble_client
        self._attr_has_entity_name = True
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"twinstar_{mac_address}_{unique_suffix}"
        self._attr_icon = icon
        self._attr_native_min_value = 0
        self._attr_native_max_value = 60
        self._attr_native_step = 1
        self._default_val = default_val
        self._value = default_val

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return get_device_info(self._mac)

    async def async_added_to_hass(self) -> None:
        """Restore the last known duration."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            try:
                self._value = int(float(last_state.state))
                _LOGGER.debug(
                    "State restored: %s returns to %s min",
                    self.entity_id,
                    self._value,
                )
            except ValueError:
                pass

    @property
    def native_value(self) -> int:
        """Return the current value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Update the duration and push the new schedule over BLE."""
        self._value = int(value)
        self.async_write_ha_state()

        _LOGGER.debug("New duration for %s: %s min", self.entity_id, self._value)
        await async_send_schedule_command(self.hass, self._mac, self._ble_client)

