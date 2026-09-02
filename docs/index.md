---
title: Home
layout: default
nav_order: 1
permalink: /
description: A WeeWX extension that reads a PurpleAir sensor (or purple-proxy), inserts EPA-corrected PM2.5 into every loop packet, and serves AQI and its color on demand as XTypes.
---

# weewx-purple

**PurpleAir air quality for WeeWX** — EPA-corrected PM2.5 in every loop
packet; AQI and its color computed on demand, never stored.

[View on GitHub](https://github.com/chaunceygardiner/weewx-purple){: .btn .btn-primary }
[Download weewx-purple.zip](https://github.com/chaunceygardiner/weewx-purple/releases/latest/download/weewx-purple.zip){: .btn }
[Report an issue](https://github.com/chaunceygardiner/weewx-purple/issues){: .btn }

weewx-purple reads a [PurpleAir](https://www2.purpleair.com/) air quality
sensor on the local network (or a
[purple-proxy](https://chaunceygardiner.github.io/purple-proxy/) service)
and populates every WeeWX loop packet with:

| Field     | Contents                                                              |
|-----------|-----------------------------------------------------------------------|
| `pm1_0`   | PM1.0 concentration (µg/m³), average of the A and B channels          |
| `pm2_5`   | PM2.5 concentration (µg/m³) with the US EPA correction applied        |
| `pm10_0`  | PM10 concentration (µg/m³), average of the A and B channels           |

Two more observation types are available everywhere in reports and graphs —
without being stored in the database — via WeeWX
[XTypes](https://github.com/weewx/weewx/wiki/WeeWX-V4-user-defined-types):

| Field              | Contents                                                         |
|--------------------|------------------------------------------------------------------|
| `pm2_5_aqi`        | US EPA Air Quality Index computed from `pm2_5` (2024 definition) |
| `pm2_5_aqi_color`  | The RGB color of the AQI category, as a single integer           |

On outdoor (dual-laser) sensors, readings are sanity checked: a reading is
rejected if the A and B channels disagree wildly, if fields are missing or
non-numeric, or if the reading is stale.  If multiple sensors/proxies are
configured, they are tried in order until one produces a good reading.

No extra database configuration is needed: WeeWX automatically accumulates
the loop values into each archive record, so `pm1_0`, `pm2_5` and `pm10_0`
land in the database (and in history graphs) on their own.

Gaps are filled in, too.  When WeeWX is not running — a restart, a reboot,
a power cut — the station's logger keeps recording, and WeeWX archives those
records when it comes back.  They contain no air quality data, because this
extension was not there to supply any.  If a
[purple-proxy](https://chaunceygardiner.github.io/purple-proxy/) is
configured, the missing `pm1_0`, `pm2_5` and `pm10_0` are fetched from the
proxy's own archive history and filled in, so an outage no longer leaves a
hole in the pm columns and the graphs that draw them.  The `pm2_5` written is
the same EPA-corrected value the live path stores.  See
[What's purple-proxy?](#whats-purple-proxy).

## The EPA correction

The stored `pm2_5` value is always the
[2021 US EPA correction](https://www.epa.gov/sites/default/files/2021-05/documents/toolsresourceswebinar_purpleairsmoke_210519b.pdf)
computed from the raw `cf_1` readings of both channels plus the temperature
and humidity reported by the sensor:

```
low  (PAcf_1 <= 343 µg/m³): PM2.5 = 0.52*PAcf_1 - 0.086*RH + 5.75
high (PAcf_1  > 343 µg/m³): PM2.5 = 0.46*PAcf_1 + 3.93e-4*PAcf_1² + 2.97
```

The correction has been shown to yield the correct US EPA AQI category 92% of
the time, and to be at most one category off 100% of the time, across all US
regions and all conditions (including wildfire smoke).  The uncorrected PM2.5
is deliberately not stored: the correction requires the sensor's temperature
and humidity, which are not saved, so it could not be recomputed later.

## AQI categories

`pm2_5_aqi` conforms to the
[2024 EPA AQI definition](https://www.epa.gov/system/files/documents/2024-02/pm-naaqs-air-quality-index-fact-sheet.pdf);
`pm2_5_aqi_color` uses the EPA-defined RGB colors:

| Category                       | AQI       | 24-hr PM2.5 (µg/m³) | Color  | RGB           |
|--------------------------------|-----------|---------------------|--------|---------------|
| Good                           | 0 - 50    | 0.0 - 9.0           | Green  | (0, 228, 0)   |
| Moderate                       | 51 - 100  | 9.1 - 35.4          | Yellow | (255, 255, 0) |
| Unhealthy for Sensitive Groups | 101 - 150 | 35.5 - 55.4         | Orange | (255, 126, 0) |
| Unhealthy                      | 151 - 200 | 55.5 - 125.4        | Red    | (255, 0, 0)   |
| Very Unhealthy                 | 201 - 300 | 125.5 - 225.4       | Purple | (143, 63, 151)|
| Hazardous                      | 301 - 500 | 225.5 - 325.4       | Maroon | (126, 0, 35)  |

Concentrations above 325.4 µg/m³ map to AQI values above 500, continuing on
the same slope as AQI 301-500 (per the May 2024
[AirNow Technical Assistance Document](https://document.airnow.gov/technical-assistance-document-for-the-reporting-of-daily-air-quailty.pdf)).
The category and color remain Hazardous/Maroon.

## The sample report

A small sample report is installed at `<HTML_ROOT>/purple`.  It is meant to be
usable as it stands: it takes its heading and browser title from your
`[Station]` `location`, so it reads *Palo Alto, CA Air Quality* rather than
naming this extension.  It leads with the current AQI on a dial of the six
categories above, the category it falls in and that category's health
advice, and all three particulate sizes; then the
day's peak, average and low, and a cell per hour for the last twenty-four,
each colored by its category.  The four period plots are behind the
Day/Week/Month/Year tabs at the foot of the page:

![The sample report](https://raw.githubusercontent.com/chaunceygardiner/weewx-purple/master/PurpleReport.jpg)

*Shown on 09/11/2020, the day wildfire smoke turned the Bay Area sky
orange.  Most days are green; this is the one the colors are for.*

The page is translatable, and German, French, Dutch and Spanish ship with
it — see [Translating (i18n)](i18n.md):

![The sample report in German](https://raw.githubusercontent.com/chaunceygardiner/weewx-purple/master/PurpleReport-de.png)

## What's purple-proxy?

[purple-proxy](https://chaunceygardiner.github.io/purple-proxy/) is a small service that polls the sensor
for you and keeps its own archive of the readings.  Running one is recommended, for three reasons:

* **It spares the sensor.**  A PurpleAir's processor is easily overwhelmed,
  and everything that queries it competes for the same small budget.  The
  proxy queries the sensor at one steady rate and answers everyone else.
* **It serves an average, not a spot reading.**  Each value it returns is
  an average of the last two minutes, and each record it archives is an
  average of that whole archive period.
* **It fills the gaps.**  Because the proxy keeps archive records of its
  own, weewx-purple can go back and fill in the air quality data for the
  periods WeeWX was down for.  Nothing else can: a sensor queried directly
  keeps no history, so those records stay empty forever.

Two proxies on different machines can poll the same sensor for redundancy,
and weewx-purple will try each configured proxy in turn.  The install is a
script (`sudo ./install`) and has been tested on Debian and Raspberry Pi OS;
on other platforms it serves as a specification of the steps needed.

## See it in action

* [Weatherboard&trade; Report](https://www.paloaltoweather.com/weatherboard/)
* [LiveSeasons Report](https://www.paloaltoweather.com/index.html)

## Licensing

weewx-purple is licensed under the GNU Public License v3.
Copyright (C) 2020-2026 by John A Kline (john@johnkline.com).
