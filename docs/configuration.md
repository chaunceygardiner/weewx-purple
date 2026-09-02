---
title: Configuration
layout: default
nav_order: 3
description: The [Purple] section of weewx.conf — sensors, proxies, polling, source order and freshness.
---

# Configuring weewx-purple

[weewx-purple manual](https://chaunceygardiner.github.io/weewx-purple/) · [weewx-purple on GitHub](https://github.com/chaunceygardiner/weewx-purple) · [Report an issue](https://github.com/chaunceygardiner/weewx-purple/issues)

---

The install creates a `[Purple]` section in weewx.conf; point it at your
sensor(s):

```
[Purple]
    # How often to poll the sensor in seconds
    #poll_secs = 15
    [[Sensor1]]
        enable = true
        # The port the sensor's own web server listens on
        #port = 80
        # http timeout (seconds)
        #timeout = 15
        # PLACEHOLDER -- replace with the host name or IP address of
        # the first sensor
        hostname = purple-air
    [[Sensor2]]
        enable = false
        #port = 80
        #timeout = 15
        hostname = purple-air2
    [[Proxy1]]
        enable = false
        #port = 8000
        #timeout = 1
        hostname = proxy1
```

The options the install writes commented out are the ones weewx-purple
supplies for itself.  Leave one commented and the extension's own value
governs, including a better one a later release might bring; uncomment it to
pin this station to the value shown.  `hostname` is written live because
there is nothing to fall back on -- it is the one you have to replace with
your own.  `enable` is written live for a different reason: `Sensor1` ships
enabled so that a fresh install works with no proxy, and that is not what an
absent `enable` means.  Leave `enable` out of a section and that source is
simply off.

| Option      | Default              | Meaning                                          |
|-------------|----------------------|--------------------------------------------------|
| `poll_secs` | 15                   | How often to poll for a new reading (seconds)    |
| `enable`    | false                | Whether this source is polled                    |
| `hostname`  |                      | Hostname or IP address of the sensor/proxy       |
| `port`      | 80 (sensor) / 8000 (proxy) | Port to connect on                         |
| `timeout`   | 1 (proxy) / 15 (sensor) | HTTP timeout (seconds).  A proxy answers from its own database on the local network, so a second is ample; a sensor's own processor is slow and easily overwhelmed, so it gets more room. |

PurpleAir sensors are specified with subsections `[[Sensor1]]`, `[[Sensor2]]`,
etc.; purple-proxy services with `[[Proxy1]]`, `[[Proxy2]]`, etc.  There is no
limit on the number of sensors and proxies, but the numbering of each group
must start at 1 and be consecutive (a gap ends the scan).  On each polling
round, proxies are interrogated first (low numbers to high), then sensors;
the first source that yields a sane, fresh reading wins and no further
sources are tried.

A reading is considered fresh for `max(120, 3 * poll_secs)` seconds; stale
readings are never inserted into loop packets.

## Filling gaps after downtime

If at least one `[[ProxyN]]` source is enabled, weewx-purple also fills in
air quality data for the archive periods WeeWX itself was not running for.
When WeeWX starts, the station's logger hands over the records it kept while
WeeWX was down; those records contain no `pm1_0`, `pm2_5` or `pm10_0`,
because nothing was there to supply them.  For each such record, the proxies
are asked — in configured order — for the archive records covering that
period, and the average is written into the record before WeeWX stores it.
The `pm2_5` written is the same US EPA corrected value the live path stores.

**Set purple-proxy's `archive-interval-secs` to match WeeWX's archive
interval.**  WeeWX logs the interval it is using at startup (`Using archive
interval of 300 seconds`), and weewx-purple logs the same number
(`archive_interval: 300`).  With the two matched, each proxy record lines up
exactly with one WeeWX period.  A proxy that archives more often is handled —
its records for the period are averaged — but a proxy that archives *less*
often than WeeWX has no record to offer for most periods, and those go
unfilled.

Periods WeeWX did see are never touched: whatever WeeWX averaged from the
loop packets stands.

A proxy normally has the record for the period that has only just closed: its
polls are aligned to the clock, so one lands on the archive boundary and the
record is written a second or two later — before WeeWX archives that period
at all.  When no proxy has it — a proxy running with a `poll-freq-offset` can
still be a few seconds behind, and one that was down for the period has
nothing — the proxy's current reading (an average of the last two minutes)
stands in, but only while the period is still inside those two minutes.  Any
period further back that no proxy can answer for is left alone: an empty pm
column is the honest answer, and better than a value that describes some
other stretch of time.

With no proxy configured, none of this happens.  A sensor queried directly
keeps no history, so there is nothing to ask for, and the pm columns for
those periods stay empty.

Two log messages come from this, one per archive record:

```
INFO user.purple: Backfilled pm1_0, pm2_5, pm10_0 into archive record 2026-08-26 18:40:00 PDT (1787794800).
INFO user.purple: No proxy data with which to fill pm1_0, pm2_5, pm10_0 in archive record ...
```

The second is also how a proxy that is down announces itself, once per
archive period, for as long as it stays down.

## The sample report

The install also enables a `[[PurpleReport]]` entry under `[StdReport]`,
rendered to `<HTML_ROOT>/purple`.  To render it in German, French, Dutch or
Spanish, add a `lang` entry to its stanza — see
[Translating (i18n)](i18n.md):

```
[StdReport]
    [[PurpleReport]]
        lang = de                # or fr, nl, or es
```

## Customizing the sample report

**Put your changes in weewx.conf, not in `skins/purple/`.**  WeeWX builds a
report's settings by merging the skin's `lang/<lang>.conf`, then
`skin.conf` over that, then weewx.conf — so anything under
`[StdReport]` `[[PurpleReport]]` wins, and it survives upgrades.  Editing
`skin.conf` itself works until the next `weectl extension install`, which
replaces the whole skin directory.

These are the settings worth knowing about, with the values the skin ships:

| Setting | Ships as | What it does |
|---|---|---|
| `[ImageGenerator]` `image_width` | 500 | Plot width in pixels |
| `[ImageGenerator]` `image_height` | 230 | Plot height in pixels |
| `[ImageGenerator]` `chart_line_colors` | `0x6b2d4a, ...` | Plot line colors.  Only the first is used — every plot here draws one line |
| `[Units]` `[[StringFormats]]` `microgram_per_meter_cubed` | `%.1f` | Decimals on the page's PM1.0/PM2.5/PM10 readouts |
| `lang` | `en` | Page language — see [Translating (i18n)](i18n.md) |

Wider plots, and PM readouts to two decimals:

```
[StdReport]
    [[PurpleReport]]
        [[[ImageGenerator]]]
            image_width = 760
            image_height = 300
        [[[Units]]]
            [[[[StringFormats]]]]
                microgram_per_meter_cubed = %.2f
```

Two things that surprise people:

* **Plot colors are `0xBBGGRR`, not `0xRRGGBB`.**  This is WeeWX's
  convention, not this extension's.  The shipped `0x6b2d4a` is the purple
  `#4a2d6b`; write `0x000080` expecting navy and you get dark red.
* **`microgram_per_meter_cubed` changes the page's readouts, not the
  plots.**  The plot generator chooses its own axis labels, so the y axis
  keeps its own number of decimals whatever you set here.

Plots are PNG images, so a change to any of this appears as they
regenerate — the day and week plots on the next report cycle, the year plot
within a day.

The AQI dial, the stat tiles and the hourly strip are drawn by the template
itself (`skins/purple/index.html.tmpl`) and styled by the `<style>` block in
its `<head>`; changing those means editing the skin, and an upgrade will
replace it.
