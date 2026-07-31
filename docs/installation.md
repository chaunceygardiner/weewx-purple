---
title: Installing weewx-purple
description: Requirements and step-by-step installation of the weewx-purple extension.
---

# Installing weewx-purple

[Home](index.md) ·
[Configuration](configuration.md) ·
[Fields in reports](fields.md) ·
[Translating (i18n)](i18n.md) ·
[Troubleshooting](troubleshooting.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-purple)

---

## Requirements

* WeeWX 4 or 5 (selecting a demo-skin language needs WeeWX 4.6 or later)
* Python 3.7 or greater
* The [wview_extended](https://github.com/weewx/weewx/blob/master/src/schemas/wview_extended.py)
  schema (it contains the `pm1_0`, `pm2_5` and `pm10_0` columns)
* The `python-dateutil` and `requests` Python packages
* A PurpleAir sensor reachable on your local network

Not sure about the schema?  wview_extended is the default for new WeeWX 4
and 5 installs; only databases created under WeeWX 3 and carried forward
still use the old schema.  To check, look for `pm2_5` in your archive
table, e.g.:

```
echo '.schema archive' | sqlite3 /var/lib/weewx/weewx.sdb | grep pm2_5
```

## Installation

1. Find your sensor on the network and verify you can reach it.

   Find the sensor's IP address (e.g., in your router's DHCP client list,
   or in the PurpleAir registration email), then browse to
   `http://<sensor-ip>/json`.  You should see a page of JSON sensor data —
   that is exactly the endpoint this extension polls.  Since the extension
   needs a stable address, give the sensor a DHCP reservation in your
   router (or a hostname in local DNS) so its address doesn't change.

1. Install the prerequisite Python packages.

   For a WeeWX pip install, activate WeeWX's virtual environment first, then:

   ```
   pip install python-dateutil requests
   ```

   For a Debian package install of WeeWX:

   ```
   apt install python3-dateutil python3-requests
   ```

1. Download the latest release, `weewx-purple.zip`, from the
   [GitHub repository](https://github.com/chaunceygardiner/weewx-purple).

1. Install the extension and restart WeeWX.

   WeeWX 5:

   ```
   weectl extension install weewx-purple.zip
   ```

   WeeWX 4 (adjust the path if WeeWX is not installed in /home/weewx):

   ```
   sudo /home/weewx/bin/wee_extension --install weewx-purple.zip
   ```

1. Edit the `[Purple]` section of weewx.conf (created by the install) to
   point at your sensor — see [Configuration](configuration.md) — then
   restart WeeWX.

1. To check the install, wait for a reporting cycle, then browse to the WeeWX
   site with `/purple` appended to the URL
   (e.g., `http://weewx-machine/weewx/purple`).  The PM2.5 and AQI graphs
   fill in over time.

## Upgrading

Install the new `weewx-purple.zip` over the existing extension with the same
command and restart WeeWX.  Note that upgrading replaces the bundled skin
(`skins/purple/`) — if you customized it, save a copy first.  Overrides
placed in weewx.conf (report `[[[Labels]]]`/`[[[Texts]]]` entries, an
`[Accumulator]` section) survive upgrades.
