"""Centralized BLE client for Twinstar."""
from __future__ import annotations

import asyncio
import logging

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant

from .const import WRITE_UUID, READ_UUID, CMD_POWERSTATUS

_LOGGER = logging.getLogger(__name__)


class TwinstarBLEClient:
    """Manage the BLE connection to a Twinstar lamp.

    Serializes all BLE operations with an asyncio.Lock() to avoid
    collisions when multiple automations send commands at the same time.
    """

    def __init__(self, hass: HomeAssistant, mac_address: str) -> None:
        self._hass = hass
        self._mac = mac_address
        self._lock = asyncio.Lock()

    @property
    def mac_address(self) -> str:
        """Return the device's MAC address."""
        return self._mac

    async def send_commands(
        self, commands: list[bytes | bytearray | str], delay: float = 0.1
    ) -> bool:
        """Send a sequence of BLE commands over a single connection.

        Args:
            commands: List of commands (bytes, bytearray or str).
            delay: Pause in seconds between each command.

        Returns:
            True if all commands were sent successfully.
        """
        async with self._lock:
            ble_device = async_ble_device_from_address(
                self._hass, self._mac, connectable=True
            )
            if not ble_device:
                _LOGGER.error(
                    "Twinstar (%s) out of Bluetooth range", self._mac
                )
                return False

            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    f"Twinstar_{self._mac[-5:]}",
                )
                try:
                    for cmd in commands:
                        if isinstance(cmd, str):
                            cmd = cmd.encode("utf-8")
                        await client.write_gatt_char(
                            WRITE_UUID, cmd, response=True
                        )
                        await asyncio.sleep(delay)
                finally:
                    await client.disconnect()
                return True
            except Exception as err:
                _LOGGER.error(
                    "Twinstar BLE error (%s): %s", self._mac, err
                )
                return False

    async def send_command(self, command: bytes | bytearray | str) -> bool:
        """Send a single BLE command."""
        if isinstance(command, str):
            command = command.encode("utf-8")
        return await self.send_commands([command])

    async def async_read_power_status(self) -> bool | None:
        """Query the physical power state (ON/OFF) via a GATT read."""
        async with self._lock:
            ble_device = async_ble_device_from_address(
                self._hass, self._mac, connectable=True
            )
            if not ble_device:
                _LOGGER.debug(
                    "Twinstar (%s) out of range for status query", self._mac
                )
                return None

            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    f"Twinstar_{self._mac[-5:]}",
                )
                try:
                    await client.write_gatt_char(
                        WRITE_UUID, CMD_POWERSTATUS, response=True
                    )
                    await asyncio.sleep(0.25)
                    data = await client.read_gatt_char(READ_UUID)
                    text = data.decode("utf-8", errors="ignore").strip().upper()
                    _LOGGER.debug(
                        "Twinstar GATT state (%s): '%s' (raw: %s)",
                        self._mac,
                        text,
                        data.hex(),
                    )
                    if "ON" in text:
                        return True
                    if "OFF" in text:
                        return False
                    return None
                finally:
                    await client.disconnect()
            except Exception as err:
                _LOGGER.debug(
                    "Could not read Twinstar BLE state (%s): %s", self._mac, err
                )
                return None

