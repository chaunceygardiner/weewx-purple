---
title: weewx-purple — PurpleAir air quality for WeeWX
description: A WeeWX extension that reads a PurpleAir sensor (or purple-proxy), inserts EPA-corrected PM2.5 into every loop packet, and serves AQI and its color on demand as XTypes.
---

# weewx-purple

**PurpleAir air quality for WeeWX** — EPA-corrected PM2.5 in every loop
packet; AQI and its color computed on demand, never stored.

[Installation](installation.md) ·
[Configuration](configuration.md) ·
[Fields in reports](fields.md) ·
[Translating (i18n)](i18n.md) ·
[Troubleshooting](troubleshooting.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-purple)

---

weewx-purple reads a [PurpleAir](https://www2.purpleair.com/) air quality
sensor on the local network (or a
[purple-proxy](https://github.com/chaunceygardiner/purple-proxy) service)
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

## The demo skin

A small demo report is installed at `<HTML_ROOT>/purple`:

![The demo page](https://raw.githubusercontent.com/chaunceygardiner/weewx-purple/master/PurpleReport.jpg)

The page is translatable, and German, French, Dutch and Spanish ship with
it — see [Translating (i18n)](i18n.md):

![The demo page in German](https://raw.githubusercontent.com/chaunceygardiner/weewx-purple/master/PurpleReport-de.png)

## What's purple-proxy?

[purple-proxy](https://github.com/chaunceygardiner/purple-proxy) is an
optional service that averages sensor readings over the archive period.  Its
install is crude and has only been tested on Debian; use of purple-proxy is
discouraged for all but the most Unix/Linux savvy.  If in doubt, skip it and
query the PurpleAir sensor directly.

## See it in action

* [Weatherboard&trade; Report](https://www.paloaltoweather.com/weatherboard/)
* [LiveSeasons Report](https://www.paloaltoweather.com/index.html)

## Licensing

weewx-purple is licensed under the GNU Public License v3.
Copyright (C) 2020-2026 by John A Kline (john@johnkline.com).
