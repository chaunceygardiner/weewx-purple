---
title: Troubleshooting
layout: default
nav_order: 6
description: Log messages, the manual collector harness, and running the hermetic test suite.
---

# Troubleshooting weewx-purple

[weewx-purple manual](https://chaunceygardiner.github.io/weewx-purple/) · [weewx-purple on GitHub](https://github.com/chaunceygardiner/weewx-purple) · [Report an issue](https://github.com/chaunceygardiner/weewx-purple/issues)

---

## Log messages

* `Purple extension is inoperable` in the log: no source has `enable = true`
  in `[Purple]`.
* `Found no fresh concentrations to insert.`: the sensor has stopped
  answering (or is answering with insane readings).  Logged once per outage;
  `Fresh concentrations available again after 13 min.` is logged on
  recovery, with how long the outage lasted.
* `purpleair reading from <host> not sane, ...`: the reason and the offending
  reading are included in the message.
* `Backfilled pm1_0, pm2_5, pm10_0 into archive record <time>`: an archive
  period WeeWX was not running for has had its air quality data filled in
  from a proxy's archive history.  Expect one line per record after an
  outage.
* `No proxy data with which to fill ... in archive record <time>`: no
  configured proxy could answer for that period, so its pm columns were left
  empty.  Logged once per archive record, which is also how a proxy that is
  down makes itself heard for as long as it stays down.
* `collect_data: Attempt to fetch from: <host> failed: ... Read timed out`
  every two minutes or so, with good readings in between: the sensor is
  also registered to send its readings to a third-party server (Weather
  Underground, for example), and that server is failing.  While each
  send waits for an answer, about 35 seconds every two minutes, the sensor
  does not answer on the LAN.  Remove or correct the third-party upload in
  the sensor's registration.  When weewx-purple reads through a proxy, the
  timeouts show in the proxy's log instead.  purple-proxy's manual says
  how to confirm and fix it:
  [Reads time out every couple of minutes](https://chaunceygardiner.github.io/purple-proxy/troubleshooting#reads-time-out-every-couple-of-minutes).
* `collect_data: Attempt to fetch from: <host> failed: ... Failed to resolve
  'purpleair-xxxx.lan'`: the sensor has lost its WAN connection and is in
  setup mode, redirecting requests addressed by name.  weewx-purple fetches a
  sensor by IP address, which the sensor answers normally even in setup mode,
  so this should not appear; if it does, the sensor is redirecting a request
  addressed by IP, and please report it.

* **The sample report shows the top card but no tiles or hourly strip.**  Those
  need at least one PM2.5 reading recorded for the current day: they are
  absent between midnight and the first archive record, and stay absent for
  as long as the sensor has been unreachable since midnight.  They reappear
  on the report cycle after a reading lands.

* **The pm columns are empty for a stretch of time.**  WeeWX was not running
  then, and the periods were filled only if a proxy could answer for them —
  see [Filling gaps after downtime](configuration.md#filling-gaps-after-downtime).
  With no `[[ProxyN]]` configured nothing is filled, and the log says
  nothing about it.  With one configured, look for `Backfilled ...` or `No
  proxy data with which to fill ...` at the time WeeWX restarted.

## Watching the collector

To watch exactly what the collector sees, run the module directly against a
sensor:

```
PYTHONPATH=<weewx-bin-dir> python bin/user/purple.py --test-collector --hostname <sensor> [--port <port>]
```

## Running the test suite

The tests are hermetic (no sensor or network required).  From a Python
environment with WeeWX installed:

```
PYTHONPATH=bin python -m pytest tests
```
