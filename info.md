# Home Assistant integration for Alphatronics UNii

![logo](https://raw.githubusercontent.com/unii-security/homeassistant-unii/main/logo.png)

## Introduction

The UNii is a modular intrusion and access control system that is designed, developed and manufactured by Alphatronics, the Netherlands. This innovative solution is distributed and supported via the professional (security) installer and wholesalers.

This integration is still in **beta** and **subject to change**. We're looking forward to your feedback.

## Features

- Status inputs (clear, open, tamper, masking)
- Status sections (armed, disarmed, alarm) 
- Connection status UNii panel

Extra features (arming/disarming, (un)bypassing, outputs and event handling) are added shortly.

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

##  Adding a new Alphatronics UNii to Home Assistant

If your UNii is on the same network as your Home Assistant server and is assigned an IP address using DHCP your UNii will most probably be automatically discovered by the integration.

In case your UNii is not automatically discovered follow these instructions:

- After restarting go to **Settings** then **Devices & Services**
- Select **+ Add integration** and type in **UNii**
- Fill in the IP address, port number and shared key of your UNii
- Select **Submit**

A new UNii integration and device will now be added to your Integrations view.
