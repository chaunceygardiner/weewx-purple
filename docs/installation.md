---
title: Installation
layout: default
nav_order: 2
description: Requirements and step-by-step installation of the weewx-purple extension.
---

# Installing weewx-purple

[weewx-purple manual](https://chaunceygardiner.github.io/weewx-purple/) · [weewx-purple on GitHub](https://github.com/chaunceygardiner/weewx-purple) · [Report an issue](https://github.com/chaunceygardiner/weewx-purple/issues)

---

## Requirements

* WeeWX 4.6 or later
* Python 3.7 or greater
* The [wview_extended](https://github.com/weewx/weewx/blob/master/src/schemas/wview_extended.py)
  schema (it contains the `pm1_0`, `pm2_5` and `pm10_0` columns)
* The `python-dateutil` and `requests` Python packages
* A PurpleAir sensor reachable on your local network
* Recommended: a [purple-proxy](https://chaunceygardiner.github.io/purple-proxy/) polling that sensor.  It spares the sensor's easily-overwhelmed processor,
  serves a two minute average rather than a single reading, and is the only
  way the air quality data for periods WeeWX was down can be recovered —
  see [Filling gaps after downtime](configuration.md#filling-gaps-after-downtime).

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

1. Optional but recommended: set up a
   [purple-proxy](https://chaunceygardiner.github.io/purple-proxy/) to poll the sensor, following its
   [installation instructions](https://chaunceygardiner.github.io/purple-proxy/installation).  It spares the sensor's processor,
   serves averages rather than spot readings, and is what lets this
   extension fill in the air quality data for archive periods WeeWX was not
   running for.  Set its `archive-interval-secs` to match WeeWX's archive
   interval.

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

   WeeWX 5, pip install (`weectl` lives in the virtual environment, so
   activate it first; yours may sit elsewhere, `~/weewx-venv` is the usual
   place):

   ```
   source ~/weewx-venv/bin/activate
   weectl extension install weewx-purple.zip
   ```

   WeeWX 5, Debian or Red Hat package install (`weectl` is already on the
   path).  No `sudo`: that install put your account in the `weewx` group,
   which owns the files -- if you installed WeeWX in this same login
   session, log out and back in first so the group membership takes
   effect.

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

**Upgrading to 7.1 from an earlier release:** weewx-purple now requires
WeeWX 4.6 or later.  On WeeWX 4.0 through 4.5 the install is refused, and so
is startup, with `weewx-purple requires WeeWX 4.6 or later, found <version>`.
Upgrade WeeWX first.  Nothing else about this upgrade needs configuration
changes.

**Upgrading to 7.0 from an earlier release:** if you poll a purple-proxy,
change `timeout` to 1 in every `[[ProxyN]]` section of weewx.conf.  A proxy
answers out of its own database on your local network, and the same timeout
now bounds the gap-filling fetches, which run once per archive record while
WeeWX starts up.  An upgrade never alters an existing weewx.conf, so an
existing `timeout = 5` stays until you change it.
