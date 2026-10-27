"""Twinstar integration setup."""
from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall

from datetime import timedelta
from homeassistant.helpers.event import async_track_time_interval

# Registries used to look up entities by device_id
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr

from time import monotonic as time_monotonic
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallback,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)

from .const import DOMAIN, CONF_MAC, PLATFORMS, CMD_ON, CMD_OFF
from .ble_client import TwinstarBLEClient
from .schedule import async_send_schedule_command

_LOGGER = logging.getLogger(__name__)


@dataclass
class TwinstarRuntimeData:
    """In-memory data shared between the platforms of a single config entry."""

    mac_address: str
    ble_client: TwinstarBLEClient
    entities: dict[str, Any] = field(default_factory=dict)
    last_advertisement_time: float = field(default=0.0)
    has_synced_after_recovery: bool = field(default=False)
    recovering: bool = field(default=False)


TwinstarConfigEntry = ConfigEntry[TwinstarRuntimeData]


def _get_entry_runtime_data(entry: ConfigEntry) -> TwinstarRuntimeData | None:
    """Safely get runtime_data."""
    return getattr(entry, "runtime_data", None)


def _parse_light_on_state(command: str | bytes | bytearray) -> bool | None:
    """Detect whether a command turns the lamp on or off.

    Recognizes:
      - CMD_ON / CMD_OFF (raw bytes)
      - "on" / "off" (text)
      - "A<value>" (brightness: A0 = off, A1+ = on)

    Returns:
        True if it turns on, False if it turns off, None if it cannot be determined.
    """
    if isinstance(command, (bytes, bytearray)):
        if command == bytes(CMD_ON) or command == CMD_ON:
            return True
        if command == bytes(CMD_OFF) or command == CMD_OFF:
            return False
        try:
            command = command.decode("utf-8", errors="ignore")
        except Exception:
            return None

    if not isinstance(command, str):
        return None

    cleaned = command.strip().lower()

    # Literal "on" / "off" commands
    if cleaned in ("on", "on\x00"):
        return True
    if cleaned in ("off", "off\x00"):
        return False

    # Brightness commands "A<value>"
    upper = cleaned.upper()
    if upper.startswith("A"):
        try:
            return int(upper[1:]) != 0
        except ValueError:
            return None

    return None


def _get_twinstar_light_entity(hass: HomeAssistant, target_mac: str):
    """Find the light entity registered for a MAC."""
    for loaded_entry in hass.config_entries.async_entries(DOMAIN):
        runtime_data = _get_entry_runtime_data(loaded_entry)
        if runtime_data is None:
            continue
        entity = runtime_data.entities.get(target_mac)
        if entity is not None:
            return entity
    return None


def _get_ble_client_for_mac(hass: HomeAssistant, target_mac: str) -> TwinstarBLEClient | None:
    """Get the ble_client for a given MAC."""
    for loaded_entry in hass.config_entries.async_entries(DOMAIN):
        runtime_data = _get_entry_runtime_data(loaded_entry)
        if runtime_data is None:
            continue
        if runtime_data.mac_address == target_mac:
            return runtime_data.ble_client
    return None


def _update_light_state_from_command(hass: HomeAssistant, target_mac: str, command: str) -> None:
    """Update the light entity's state based on the command sent."""
    entity = _get_twinstar_light_entity(hass, target_mac)
    if entity is None:
        return
    state = _parse_light_on_state(command)
    if state is None:
        return
    entity.set_is_on(state)


def _get_target_mac(hass: HomeAssistant, call_data: dict) -> str | None:
    """Resolve the MAC from entity_id, an explicit mac, or the default."""
    target_mac = call_data.get("mac")
    entity_id = call_data.get("entity_id")

    if entity_id:
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        entity = ent_reg.async_get(entity_id)
        if entity and entity.device_id:
            device = dev_reg.async_get(entity.device_id)
            if device:
                for identifier in device.identifiers:
                    if identifier[0] == DOMAIN:
                        return identifier[1]

    # If neither a MAC nor an entity_id was given and only one lamp is installed, use it
    if not target_mac:
        runtime_entries = [
            runtime_data.mac_address
            for loaded_entry in hass.config_entries.async_entries(DOMAIN)
            if (runtime_data := _get_entry_runtime_data(loaded_entry)) is not None
        ]
        if len(runtime_entries) == 1:
            return runtime_entries[0]

    return target_mac


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services."""
    if hass.services.has_service(DOMAIN, "send_command"):
        return

    async def handle_send_command(call: ServiceCall) -> None:
        """Send a raw text command directly to the lamp."""
        command = call.data.get("command")
        target_mac = _get_target_mac(hass, call.data)

        if not target_mac:
            _LOGGER.error("Twinstar (send_command): Target lamp not found.")
            return

        ble_client_for_target = _get_ble_client_for_mac(hass, target_mac)
        if not ble_client_for_target:
            _LOGGER.error(
                "Twinstar (send_command): No BLE client for MAC %s", target_mac
            )
            return

        try:
            success = await ble_client_for_target.send_command(command)
            if success:
                _LOGGER.info("Twinstar: Command '%s' sent to MAC: %s", command, target_mac)
                _update_light_state_from_command(hass, target_mac, command)
        except Exception as e:
            _LOGGER.error("Error sending command to %s: %s", target_mac, e)

    async def handle_send_sequence(call: ServiceCall) -> None:
        """Send multiple commands over a single BLE connection."""
        commands = call.data.get("commands", [])
        delay = call.data.get("delay", 1)
        target_mac = _get_target_mac(hass, call.data)

        if not target_mac:
            _LOGGER.error("Twinstar (send_sequence): Target lamp not found.")
            return

        ble_client_for_target = _get_ble_client_for_mac(hass, target_mac)
        if not ble_client_for_target:
            _LOGGER.error(
                "Twinstar (send_sequence): No BLE client for MAC %s", target_mac
            )
            return

        try:
            success = await ble_client_for_target.send_commands(commands, delay=delay)
            if success:
                # Work out the light's final state from the last relevant command
                last_state = None
                for cmd in commands:
                    parsed = _parse_light_on_state(cmd)
                    if parsed is not None:
                        last_state = parsed
                if last_state is not None:
                    entity = _get_twinstar_light_entity(hass, target_mac)
                    if entity is not None:
                        entity.set_is_on(last_state)
        except Exception as e:
            _LOGGER.error("Error sending sequence to %s: %s", target_mac, e)

    async def handle_set_schedule(call: ServiceCall) -> None:
        """Program the on/off times and ramp durations into the controller."""
        target_mac = _get_target_mac(hass, call.data)
        if not target_mac:
            _LOGGER.error("Twinstar (set_schedule): Target lamp not found.")
            return

        ble_client_for_target = _get_ble_client_for_mac(hass, target_mac)
        if not ble_client_for_target:
            _LOGGER.error(
                "Twinstar (set_schedule): No BLE client for MAC %s", target_mac
            )
            return

        start_time = call.data.get("start_time")
        end_time = call.data.get("end_time")
        sunrise_minutes = call.data.get("sunrise_minutes")
        sunset_minutes = call.data.get("sunset_minutes")

        try:
            await async_send_schedule_command(
                hass,
                target_mac,
                ble_client_for_target,
                start_time=str(start_time) if start_time is not None else None,
                end_time=str(end_time) if end_time is not None else None,
                sunrise_minutes=sunrise_minutes,
                sunset_minutes=sunset_minutes,
            )
        except Exception as e:
            _LOGGER.error("Error programming schedule on %s: %s", target_mac, e)

    hass.services.async_register(DOMAIN, "send_command", handle_send_command)
    hass.services.async_register(DOMAIN, "send_sequence", handle_send_sequence)
    hass.services.async_register(DOMAIN, "set_schedule", handle_set_schedule)


async def async_setup_entry(hass: HomeAssistant, entry: TwinstarConfigEntry) -> bool:
    """Set up Twinstar from a config entry."""
    mac_address = entry.data.get(CONF_MAC)
    ble_client = TwinstarBLEClient(hass, mac_address)

    entry.runtime_data = TwinstarRuntimeData(
        mac_address=mac_address,
        ble_client=ble_client,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up the services only once
    await async_setup_services(hass)

    # Register the BLE listener for automatic resync after a restart or power outage
    _setup_bluetooth_recovery_listener(hass, entry)

    # Set up configurable periodic status polling to reflect hardware timers
    _setup_periodic_status_poll(hass, entry)

    # Register a listener for when the user changes the options (e.g. interval)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: TwinstarConfigEntry) -> None:
    """Reload the integration when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _setup_bluetooth_recovery_listener(
    hass: HomeAssistant, entry: TwinstarConfigEntry
) -> None:
    """Register a BLE listener to resync the RTC clock and schedule after a power outage or startup."""
    runtime_data = entry.runtime_data
    mac_address = runtime_data.mac_address
    ble_client = runtime_data.ble_client

    async def _async_recover_schedule() -> None:
        """Background task that waits for the radio to settle, then sends the schedule."""
        try:
            runtime_data.recovering = True
            _LOGGER.info(
                "Twinstar (%s): Waiting 5s for the BLE radio to settle before resyncing schedule/clock after recovery...",
                mac_address,
            )
            await asyncio.sleep(5)

            # 1. Sync the RTC clock and timer schedule
            await async_send_schedule_command(hass, mac_address, ble_client)

            # 2. Restore the color levels (RGBW + brightness) in the controller's registers
            light_entity = runtime_data.entities.get(mac_address)
            if light_entity and hasattr(light_entity, "_build_color_commands"):
                commands = light_entity._build_color_commands()
                if commands:
                    if light_entity.is_on:
                        commands.append(CMD_ON)
                        _LOGGER.info(
                            "Twinstar (%s): Aquarium was recorded as ON. Restoring RGBW color and ON state.",
                            mac_address,
                        )
                    else:
                        commands.append(CMD_OFF)
                        _LOGGER.info(
                            "Twinstar (%s): Aquarium was recorded as OFF. Writing RGBW color to memory and staying OFF.",
                            mac_address,
                        )
                    await ble_client.send_commands(commands)

            if light_entity and hasattr(light_entity, "async_update_power_status"):
                await light_entity.async_update_power_status()

            _LOGGER.info(
                "Twinstar (%s): Automatic recovery sync (RTC + schedule + state) completed successfully.",
                mac_address,
            )
        except Exception as err:
            _LOGGER.error(
                "Twinstar (%s): Error during automatic recovery sync: %s",
                mac_address,
                err,
            )
        finally:
            runtime_data.recovering = False

    def _on_bluetooth_event(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Runs every time HA sees a BLE advertisement from the device."""
        if change != BluetoothChange.ADVERTISEMENT:
            return

        now = time_monotonic()
        time_since_last = now - runtime_data.last_advertisement_time
        runtime_data.last_advertisement_time = now

        # If not yet synced this cycle, or more than 60s passed without advertisements (power outage/signal loss)
        if not runtime_data.has_synced_after_recovery or time_since_last > 60:
            runtime_data.has_synced_after_recovery = True
            if not runtime_data.recovering:
                _LOGGER.info(
                    "Twinstar (%s): BLE signal detected after %s. Starting automatic recovery...",
                    mac_address,
                    "startup" if time_since_last > 100000 else f"{time_since_last:.0f}s without signal",
                )
                hass.async_create_background_task(
                    _async_recover_schedule(),
                    name=f"twinstar_recovery_{mac_address}",
                )

    cancel_callback = bluetooth.async_register_callback(
        hass,
        _on_bluetooth_event,
        {"address": mac_address},
        BluetoothScanningMode.ACTIVE,
    )
    entry.async_on_unload(cancel_callback)


def _setup_periodic_status_poll(
    hass: HomeAssistant, entry: TwinstarConfigEntry
) -> None:
    """Schedule periodic hardware polling to detect automatic state changes."""
    from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
    
    runtime_data = entry.runtime_data
    mac_address = runtime_data.mac_address
    
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    async def _async_poll_status(_now) -> None:
        light_entity = runtime_data.entities.get(mac_address)
        if light_entity and hasattr(light_entity, "async_update_power_status"):
            await light_entity.async_update_power_status()

    remove_timer = async_track_time_interval(
        hass, _async_poll_status, timedelta(minutes=poll_interval)
    )
    entry.async_on_unload(remove_timer)


async def async_unload_entry(hass: HomeAssistant, entry: TwinstarConfigEntry) -> bool:
    """Unload the integration and remove services if no entries remain."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # If no other loaded entries remain, remove the services
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state == ConfigEntryState.LOADED
    ]
    if not remaining:
        hass.services.async_remove(DOMAIN, "send_command")
        hass.services.async_remove(DOMAIN, "send_sequence")
        hass.services.async_remove(DOMAIN, "set_schedule")

    return unload_ok