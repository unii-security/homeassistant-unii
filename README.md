# Home Assistant integration for Alphatronics UNii

![logo](https://raw.githubusercontent.com/unii-security/homeassistant-unii/main/logo.png)

## Introduction

The UNii is a modular intrusion and access control system that is designed, developed and manufactured by Alphatronics, the Netherlands. This innovative solution is distributed and supported via the professional (security) installer and wholesalers.

This integration is still in **beta** and **subject to change**. We're looking forward to your feedback.

## Features

- Status inputs (clear, open, tamper, masking)
- (Un)bypassing inputs
- Status sections (armed, disarmed, alarm, exit timer, entry timer)
- Arm and disarm sections
- Connection status UNii panel

Section in alarm and fast input status update are only available for firmware version 2.17.x and above

## Hardware

Tested with the UNii 32, 128 and 512. No additional UNii license needed.

It is recommended to use the latest possible firmware on your UNii to unlock the full potential of the UNii and this integration.

## Configuring the UNii

In the UNii API configuration the following options need to be set:

- Type: Basic encryption
- Transmission: TCP
- Input update interval: 0s to have to fastest input response type. (Only for firmware version 2.17.x and above)
- API version: UNii.

After making changes to the UNii configuration the integration needs to be reloaded manually in Home Assistant.

### Shared Key

The UNii uses an encrypted connection with Home Assistant. The shared key has to be entered in the UNii (API settings) by the installer. Without installer access to the UNii end-users are **NOT** able to enter this key. Contact your installer if applicable.

## Installing the integration in Home Assistant

### HACS

The recommended way to install this Home Assistant integration is by using [HACS][hacs].
Click the following button to open the integration directly on the HACS integration page.

[![Install Alphatronics UNii from HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=unii-security&repository=homeassistant-unii&category=integration)

Or follow these instructions:

- Go to your **HACS** view in Home Assistant and then to **Integrations**
- Open the **Custom repositories** menu
- Add this repository URL to the **Custom repositories** and select
**Integration** as the **Category**
- Click **Add**
- Close the **Custom repositories** menu
- Select **+ Explore & download repositories** and search for *Alphatronics UNii*
- Select **Download**
- Restart Home Assistant

### Manually

- Copy the `custom_components/unii` directory of this repository into the
`config/custom_components/` directory of your Home Assistant installation
- Restart Home Assistant

## Adding a new Alphatronics UNii to Home Assistant

If your UNii is on the same network as your Home Assistant server and is assigned an IP address using DHCP your UNii will most probably be automatically discovered by the integration.

In case your UNii is not automatically discovered follow these instructions:

- After restarting go to **Settings** then **Devices & Services**
- Select **+ Add integration** and type in **UNii**
- Fill in the IP address, port number and shared key of your UNii
- Select **Submit**

A new UNii integration and device will now be added to your Integrations view.

## Write access to the UNii

By default the UNii integration is set to read only mode, only the status of your Unii will be displayed.
To enable write access and be able to (un)bypass inputs or arm and disarm set an user code in the UNii integration options by going to the UNii device and clicking **Configure**. By removing the user code the UNii integration is back in read only mode.

It is recommended to use a dedicated user in your UNii which is assigned only those permissions that are needed for your scenarios.

---

All UNii trademarks, logos and brand names are registered and the property of Alphatronics BV

[hacs]: https://hacs.xyz/
