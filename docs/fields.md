---
title: Fields in reports
layout: default
nav_order: 4
description: Using pm1_0, pm2_5, pm10_0, pm2_5_aqi and pm2_5_aqi_color in WeeWX reports — tags, aggregates, graphs, and how AQI is computed and (not) stored.
---

# weewx-purple fields in reports

[weewx-purple manual](https://chaunceygardiner.github.io/weewx-purple/) · [weewx-purple on GitHub](https://github.com/chaunceygardiner/weewx-purple) · [Report an issue](https://github.com/chaunceygardiner/weewx-purple/issues)

---

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

## If you added an AQI column to your database

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
