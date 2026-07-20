# weewx-purple

A WeeWX extension that reads a [PurpleAir](https://www2.purpleair.com/) air
quality sensor on the local network (or a
[purple-proxy](https://github.com/chaunceygardiner/purple-proxy) service) and
inserts particulate concentrations into every WeeWX loop packet.

Copyright (C) 2020-2026 by John A Kline (john@johnkline.com)

**Requires:**
* WeeWX 4 or 5
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

## What it does

Every loop packet is populated with:

| Field     | Contents                                                              |
|-----------|-----------------------------------------------------------------------|
| `pm1_0`   | PM1.0 concentration (µg/m³), average of the A and B channels          |
| `pm2_5`   | PM2.5 concentration (µg/m³) with the US EPA correction applied        |
| `pm10_0`  | PM10.0 concentration (µg/m³), average of the A and B channels         |

Two more observation types are available everywhere in reports and graphs —
without being stored in the database — via WeeWX
[XTypes](https://github.com/weewx/weewx/wiki/WeeWX-V4-user-defined-types):

| Field              | Contents                                                       |
|--------------------|----------------------------------------------------------------|
| `pm2_5_aqi`        | US EPA Air Quality Index computed from `pm2_5` (2024 definition) |
| `pm2_5_aqi_color`  | The RGB color of the AQI category, as a single integer         |

On outdoor (dual-laser) sensors, readings are sanity checked: a reading is
rejected if the A and B channels disagree wildly, if fields are missing or
non-numeric, or if the reading is stale.  If multiple sensors/proxies are
configured, they are tried in order until one produces a good reading.

No extra database configuration is needed: WeeWX automatically accumulates
the loop values into each archive record, so `pm1_0`, `pm2_5` and `pm10_0`
land in the database (and in history graphs) on their own.

### The EPA correction

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

### AQI categories

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

### Demo skin

A small demo report is installed at `<HTML_ROOT>/purple`:

![PurpleReport](PurpleReport.jpg)

### What's purple-proxy?

[purple-proxy](https://github.com/chaunceygardiner/purple-proxy) is an
optional service that averages sensor readings over the archive period.  Its
install is crude and has only been tested on Debian; use of purple-proxy is
discouraged for all but the most Unix/Linux savvy.  If in doubt, skip it and
query the PurpleAir sensor directly.

See weewx-purple in action:
* [Weatherboard&trade; Report](https://www.paloaltoweather.com/weatherboard/)
* [LiveSeasons Report](https://www.paloaltoweather.com/index.html)

# Installation

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
   point at your sensor, then restart WeeWX.

1. To check the install, wait for a reporting cycle, then browse to the WeeWX
   site with `/purple` appended to the URL
   (e.g., `http://weewx-machine/weewx/purple`).  The PM2.5 and AQI graphs
   fill in over time.

## Configuration

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

# Using weewx-purple fields in reports

Current values:

```
$current.pm1_0
$current.pm2_5
$current.pm10_0
$current.pm2_5_aqi
$current.pm2_5_aqi_color
```

Aggregates work for both the database-backed fields and the AQI xtypes
(supported AQI aggregates: `avg`, `min`, `max`, `first`, `last`, `count`):

```
$day.pm2_5.max
$week.pm2_5.avg
$day.pm2_5_aqi.max
```

Both `pm2_5_aqi` and `pm2_5_aqi_color` can also be graphed, e.g. in
skin.conf's `[ImageGenerator]` section:

```
        [[[dayaqi]]]
            [[[[pm2_5_aqi]]]]
```

`pm2_5_aqi_color` is an [RGBint](https://www.shodor.org/stella2java/rgbint.html)
value, useful for displaying the AQI in the color of its category.  To unpack
it in a Cheetah template:

```
#set $color = int($current.pm2_5_aqi_color.raw)
#set $blue  =  $color & 255
#set $green = ($color >> 8) & 255
#set $red   = ($color >> 16) & 255
```

## How AQI values are computed (and stored)

AQI is always computed on demand from the stored `pm2_5` concentration —
there is no AQI column in the database, and none is needed: `$current`,
aggregates and graphs all resolve through the extension's AQI xtype.  For
real-time consumers (e.g., MQTT), `pm2_5_aqi` and `pm2_5_aqi_color` are
also present in every LOOP packet.

There is no performance reason to store AQI (or its color) either, even
for long-term plots.  For an aggregated plot (e.g., a month of daily
maxima) the database aggregates the stored `pm2_5` exactly as it would
aggregate a stored AQI column, and the conversion to AQI and color — a
single interpolation and a category lookup — runs once per plotted
point, not once per database row; spans covering whole days are served
from the `pm2_5` daily-summary table without scanning the archive at
all.  Converting after aggregation is also the EPA-correct order of
operations: AQI is a non-linear transform of concentration, so the
average of per-record AQI values is not the AQI of the average
concentration (and an averaged RGB color can belong to no EPA category
at all).

To keep the on-demand computation authoritative, the extension registers
`extractor = noop` for both AQI fields so that WeeWX's accumulator does
not average them into archive records (averaging AQI values is
meaningless, since AQI is a non-linear transform of concentration).  An
`[Accumulator]` section in weewx.conf takes precedence if you
deliberately want different behavior.

### If you added an AQI column to your database

Some users have added a `pm2_5_aqi` (or `pm2_5_aqi_color`) column to their
database schema.  As of 5.0.1 the accumulator no longer fills such a
column, and any values stored in it *before* 5.0.1 are accumulator
averages that disagree with what the xtype computes (non-integer, and
averaged across a non-linear transform).  While present, those stored
values also override the xtype for `$current`.

**The cleanest fix is to remove the column.**  With WeeWX stopped (for a
pip install, activate WeeWX's virtual environment first):

WeeWX 5:

```
weectl database drop-columns pm2_5_aqi
```

WeeWX 4 (adjust the path if WeeWX is not installed in /home/weewx):

```
sudo /home/weewx/bin/wee_database --drop-columns=pm2_5_aqi
```

Name exactly the column(s) you added (repeat for `pm2_5_aqi_color` if you
added that too — naming a column that doesn't exist aborts the whole
command).  This also removes the matching daily-summary table.  Restart
WeeWX; no configuration changes are needed — `$current`, aggregates and
graphs all resolve through the xtype again.

**If something outside WeeWX reads the column directly** (e.g., Grafana),
keep it and have WeeWX compute it through the xtype, which stores
correctly EPA-rounded values:

```
[StdWXCalculate]
    [[Calculations]]
        pm2_5_aqi = prefer_hardware
        pm2_5_aqi_color = prefer_hardware
```

Then purge any values stored before 5.0.1 and backfill them through the
xtype:

1. Add the `[StdWXCalculate]` entries above to weewx.conf.

1. Stop WeeWX and back up the database.

1. NULL out the old values — for each AQI column you added, e.g. with
   SQLite (adapt for MySQL):

   ```
   sqlite3 /path/to/archive.sdb "UPDATE archive SET pm2_5_aqi = NULL;"
   ```

1. Backfill.  WeeWX 5: `weectl database calc-missing`; WeeWX 4:
   `wee_database --calc-missing`.  This recomputes each NULLed value from
   that record's stored `pm2_5` and recalculates the daily summaries.
   (It loads the extension to get the AQI xtype, so expect Purple's
   startup log lines, including a sensor fetch.)

1. Restart WeeWX.

# Troubleshooting

* `Purple extension is inoperable` in the log: no source has `enable = true`
  in `[Purple]`.
* `Found no fresh concentrations to insert.`: the sensor has stopped
  answering (or is answering with insane readings).  Logged once per outage;
  `Fresh concentrations available again.` is logged on recovery.
* `purpleair reading from <host> not sane, ...`: the reason and the offending
  reading are included in the message.
* To watch what the collector sees, run the module directly against a sensor:

  ```
  PYTHONPATH=<weewx-bin-dir> python bin/user/purple.py --test-collector --hostname <sensor> [--port <port>]
  ```

# Running the test suite

The tests are hermetic (no sensor or network required).  From a Python
environment with WeeWX installed:

```
PYTHONPATH=bin python -m pytest tests
```

## Licensing

weewx-purple is licensed under the GNU Public License v3.
