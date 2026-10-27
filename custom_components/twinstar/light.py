"""Smart light switch for Twinstar."""
from __future__ import annotations

import logging

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .ble_client import TwinstarBLEClient
from .const import (
    CMD_OFF,
    CMD_ON,
    DOMAIN,
    CONF_MAC,
    get_device_info,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the light entity from a config entry."""
    runtime_data = entry.runtime_data
    mac_address = runtime_data.mac_address
    ble_client = runtime_data.ble_client

    async_add_entities(
        [TwinstarLight(entry, mac_address, ble_client)], update_before_add=True
    )




class TwinstarLight(LightEntity, RestoreEntity):
    """Represents a Twinstar aquarium lamp."""

    def __init__(
        self,
        entry: ConfigEntry,
        mac_address: str,
        ble_client: TwinstarBLEClient,
    ) -> None:
        self._entry = entry
        self._mac = mac_address
        self._ble_client = ble_client
        self._attr_has_entity_name = True
        # None = use the (translated) device name as the light's name
        self._attr_name = None
        self._attr_unique_id = f"twinstar_light_{mac_address}"
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_icon = "mdi:lightbulb-fluorescent-tube"
        self._is_on = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info (shared with number.py)."""
        return get_device_info(self._mac)

    # --- State restore on restart ---

    async def async_added_to_hass(self) -> None:
        """Restore the on/off state after a restart."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.state == STATE_ON:
            self._is_on = True
            _LOGGER.debug("State restored: Twinstar lamp returns to ON")

        # Register the entity in runtime_data so __init__.py can find it
        runtime_data = getattr(self._entry, "runtime_data", None)
        if runtime_data is not None:
            runtime_data.entities[self._mac] = self

        # Schedule an initial read of the real physical state after startup
        self.hass.async_create_background_task(
            self.async_update_power_status(),
            name=f"twinstar_status_init_{self._mac}",
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up the reference when the entity is removed."""
        runtime_data = getattr(self._entry, "runtime_data", None)
        if runtime_data is not None:
            runtime_data.entities.pop(self._mac, None)
        await super().async_will_remove_from_hass()

    # --- State ---

    @property
    def is_on(self) -> bool:
        """Return whether the light is on."""
        return self._is_on

    def set_is_on(self, state: bool) -> None:
        """Update the on/off state from external services (send_command, etc.)."""
        self._is_on = state
        self.async_write_ha_state()

    async def async_update_power_status(self) -> None:
        """Query over Bluetooth whether the lamp is actually, physically on or off."""
        status = await self._ble_client.async_read_power_status()
        if status is not None and status != self._is_on:
            _LOGGER.info(
                "Twinstar (%s): Physical state updated to %s (previous in HA: %s)",
                self._mac,
                "ON" if status else "OFF",
                "ON" if self._is_on else "OFF",
            )
            self._is_on = status
            self.async_write_ha_state()

    # --- Commands ---

    async def async_turn_on(self, **kwargs) -> None:
        """Normal turn-on: send brightness + colors + ON."""
        commands = self._build_color_commands()
        commands.append(CMD_ON)

        success = await self._ble_client.send_commands(commands)
        if success:
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off safely."""
        success = await self._ble_client.send_commands([b"A0", CMD_OFF])
        if success:
            self._is_on = False
            self.async_write_ha_state()

    # --- Utilities ---

    def _build_color_commands(self) -> list[bytes]:
        """Build the list of color commands by reading sibling entities by device_id.

        Finds all number entities on the same device (by identifiers)
        and extracts the channel prefix from the unique_id (A, R, G, B, W).
        """
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)

        device = dev_reg.async_get_device(identifiers={(DOMAIN, self._mac)})
        if not device:
            _LOGGER.warning(
                "Twinstar: Device not found for MAC %s", self._mac
            )
            return []

        commands: list[bytes] = []

        for entity_entry in er.async_entries_for_device(ent_reg, device.id):
            # Only number entities are relevant
            if not entity_entry.entity_id.startswith("number."):
                continue

            # Extract the channel prefix from the unique_id: "twinstar_<mac>_<prefix>"
            uid = entity_entry.unique_id or ""
            parts = uid.rsplit("_", 1)
            if len(parts) < 2:
                continue
            prefix = parts[-1]

            if prefix not in ("A", "R", "G", "B", "W"):
                continue

            # Read the current state
            state = self.hass.states.get(entity_entry.entity_id)
            if not state or state.state in ("unknown", "unavailable"):
                continue

            try:
                val = int(float(state.state))
            except (ValueError, TypeError):
                continue

            commands.append(f"{prefix}{val}".encode("utf-8"))

        return commands