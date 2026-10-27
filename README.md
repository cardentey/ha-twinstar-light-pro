# Twinstar Aquarium Light for Home Assistant

![Home Assistant Dashboard](https://img.shields.io/badge/Home%20Assistant-Integration-blue.svg)
![Bluetooth](https://img.shields.io/badge/Connectivity-BLE%20(USB%20or%20Proxy)-informational.svg)
![Model](https://img.shields.io/badge/Model-Twinstar%20Light%20Pro-green.svg)

This custom integration lets you control **Twinstar Light Pro (RGBW)** LED fixtures directly from Home Assistant using **Bluetooth Low Energy (BLE)**.

Communication works with any Bluetooth interface supported by Home Assistant, including:

- ✅ USB Bluetooth adapter.
- ✅ Built-in Bluetooth on the machine running Home Assistant (Raspberry Pi, NUC, etc.).
- ✅ ESPHome Bluetooth Proxy (recommended for better range and connection stability).

---

# 📦 Compatibility

## Tested with

- Twinstar V 600S

It may also work with other **Twinstar Light Pro** models, but they have not been verified.

---

# 📋 Requirements

- Home Assistant.
- Bluetooth available in Home Assistant through any of these options:
  - USB Bluetooth adapter.
  - Built-in Bluetooth.
  - ESPHome Bluetooth Proxy (recommended).

---

# ✨ Features

<p align="center">
  <img src="/IMG_7726.PNG" alt="Twinstar Dashboard" width="400">
</p>

- **Bluetooth auto-discovery:** Automatically detects new Twinstar Light Pro lamps nearby.
- **Multi-device support:** Independent control of multiple aquariums.
- **Individual channel control:** `number` entities to adjust Red, Green, Blue, White and Overall Brightness (0–100%).
- **Hardware timer:** Sunrise, sunset and schedule configured directly in the controller's memory (`TOn:HHMM_HHMM_MM_MM`).
- **Clock sync:** Automatic adjustment of the controller's RTC (`YYYYMMDDHHMMSS`) and a manual **Sync clock** button.
- **State persistence:** All values are restored automatically after Home Assistant restarts.
- **Advanced services:**
  - `set_schedule`
  - `send_command`
  - `send_sequence`
- **Robust connection:** Uses `bleak-retry-connector` to minimize disconnects and improve Bluetooth stability.

---

# 🌐 Languages

The integration uses Home Assistant's built-in translation system. It currently ships in **English** and **Spanish**.

- **Device and entity names** follow the Home Assistant system language (**Settings → System → General → Language**). Entity IDs are generated from the name in that language when the device is first added, and do not change afterwards.
- **Setup dialogs, options and service (action) descriptions** follow each user's own language (**Profile → Language**).
- Log messages are in English, following Home Assistant convention.

To add a language, copy `custom_components/twinstar/translations/en.json` to `<language code>.json` (for example `de.json`) and translate the values. Keep the keys unchanged.

---

# 🛠️ Installation

## Manual installation

1. Download the contents of the folder:

```
custom_components/twinstar
```

2. Copy the folder to:

```
/config/custom_components/twinstar
```

3. Restart Home Assistant.

---

# ⚙️ Configuration

## Auto-discovery

The integration uses Home Assistant's Bluetooth infrastructure.

If Home Assistant can communicate with the lamp through any of these methods:

- USB Bluetooth adapter
- Built-in Bluetooth
- ESPHome Bluetooth Proxy

a **"New device discovered"** notification will appear automatically.

### Connection architecture

```text
                 Home Assistant
                        │
         ┌──────────────┴──────────────┐
         │                             │
 Bluetooth USB                  ESPHome Bluetooth Proxy
         │                             │
         └──────────────┬──────────────┘
                        │
                 Bluetooth LE (BLE)
                        │
              Twinstar Light Pro
```

---

## Manual configuration

If the device does not appear automatically:

1. Go to **Settings → Devices & Services**.
2. Click **Add Integration**.
3. Search for **Twinstar**.
4. Enter the lamp's MAC address.

---

# ⏱️ Native controller scheduling

The integration configures the Twinstar controller's internal timer and clock (RTC) directly, so it does not depend on external automations.

### Available functions

- **On and off times (`time`)**
  - `time` entities to configure the daily schedule.

- **Sunrise and sunset duration (`number`)**
  - Adjustable between **0 and 60 minutes** for smooth transitions.

- **Power outage resilience**
  - The integration continuously monitors the BLE connection.
  - After a Home Assistant restart or a power outage longer than 60 seconds, it:
    - Resyncs the RTC clock.
    - Restores the schedule automatically.
    - Restores the stored RGBW and brightness levels.
    - Keeps the light off if it is within the night-time schedule.

- **Smart state sync**
  - On Home Assistant startup, after a recovery, and every 5 minutes (configurable), it sends the command:

```
powerstatus
```

- The controller responds via:

```
WRITE_UUID: 0xdead
READ_UUID:  0xfef4
```

This way, if the internal timer turns the light on or off, Home Assistant always reflects the device's real state.

---

# 💡 Services (Actions)

## `twinstar.set_schedule`

Programs the schedule directly into the controller.

### Parameters

| Parameter | Description |
|-----------|-------------|
| `entity_id` | Target lamp |
| `start_time` | On time (e.g. `09:00`) |
| `end_time` | Off time (e.g. `21:00`) |
| `sunrise_minutes` | Sunrise duration (0–60) |
| `sunset_minutes` | Sunset duration (0–60) |

---

## `twinstar.send_command`

Sends a text command directly to the controller.

### Parameters

| Parameter | Description |
|-----------|-------------|
| `entity_id` | Target lamp |
| `command` | Text command (e.g. `A50`) |

---

## `twinstar.send_sequence`

Sends a sequence of commands with configurable delays.

Ideal for:

- Animations.
- Custom effects.
- Advanced automations.

---

# ⚠️ Disclaimer

This integration is **not an official Twinstar product**.

It was developed through reverse engineering for interoperability purposes, for the aquarium hobbyist community.

Use it at your own risk.

---

# ❤️ Acknowledgements

Built for the Home Assistant community and planted aquarium enthusiasts.
