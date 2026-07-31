---
title: Troubleshooting weewx-purple
description: Log messages, the manual collector harness, and running the hermetic test suite.
---

# Troubleshooting weewx-purple

[Home](index.md) ·
[Installation](installation.md) ·
[Configuration](configuration.md) ·
[Fields in reports](fields.md) ·
[Translating (i18n)](i18n.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-purple)

---

## Log messages

* `Purple extension is inoperable` in the log: no source has `enable = true`
  in `[Purple]`.
* `Found no fresh concentrations to insert.`: the sensor has stopped
  answering (or is answering with insane readings).  Logged once per outage;
  `Fresh concentrations available again.` is logged on recovery.
* `purpleair reading from <host> not sane, ...`: the reason and the offending
  reading are included in the message.

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
