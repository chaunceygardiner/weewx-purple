---
title: Configuring weewx-purple
description: The [Purple] section of weewx.conf — sensors, proxies, polling, source order and freshness.
---

# Configuring weewx-purple

[Home](index.md) ·
[Installation](installation.md) ·
[Fields in reports](fields.md) ·
[Translating (i18n)](i18n.md) ·
[Troubleshooting](troubleshooting.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-purple)

---

The install creates a `[Purple]` section in weewx.conf; point it at your
sensor(s):

```
[Purple]
    poll_secs = 15
    [[Sensor1]]
        enable = true
        hostname = purple-air
        port = 80
        timeout = 15
    [[Sensor2]]
        enable = false
        hostname = purple-air2
        port = 80
        timeout = 15
    [[Proxy1]]
        enable = false
        hostname = proxy1
        port = 8000
        timeout = 5
```

| Option      | Default              | Meaning                                          |
|-------------|----------------------|--------------------------------------------------|
| `poll_secs` | 15                   | How often to poll for a new reading (seconds)    |
| `enable`    | false                | Whether this source is polled                    |
| `hostname`  |                      | Hostname or IP address of the sensor/proxy       |
| `port`      | 80 (sensor) / 8000 (proxy) | Port to connect on                         |
| `timeout`   | 10                   | HTTP timeout (seconds)                           |

PurpleAir sensors are specified with subsections `[[Sensor1]]`, `[[Sensor2]]`,
etc.; purple-proxy services with `[[Proxy1]]`, `[[Proxy2]]`, etc.  There is no
limit on the number of sensors and proxies, but the numbering of each group
must start at 1 and be consecutive (a gap ends the scan).  On each polling
round, proxies are interrogated first (low numbers to high), then sensors;
the first source that yields a sane, fresh reading wins and no further
sources are tried.

A reading is considered fresh for `max(120, 3 * poll_secs)` seconds; stale
readings are never inserted into loop packets.

## The demo report

The install also enables a `[[PurpleReport]]` entry under `[StdReport]`,
rendered to `<HTML_ROOT>/purple`.  To render it in German, French, Dutch or
Spanish, add a `lang` entry to its stanza — see
[Translating (i18n)](i18n.md):

```
[StdReport]
    [[PurpleReport]]
        lang = de                # or fr, nl, or es
```
