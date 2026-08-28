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
  `Fresh concentrations available again.` is logged on recovery.
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
