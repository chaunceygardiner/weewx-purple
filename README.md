# weewx-purple
*Open source plugin for WeeWX software.

## Description

A WeeWX plugin that gets its PurpleAir sensor readings from the
[purple-proxy](https://github.com/chaunceygardiner/weewx-purple) service.

Copyright (C)2020 by John A Kline (john@johnkline.com)

### Why?  What does it do?

It is advantageous to query `purlpe-proxy` for readings.  `purple-proxy`
returns an average over the archive period when queried and `purple-proxy`
maintains archive records (not to be confused with WeeWX archive records)
that are retrieved by this plug-in at WeeWX start in order to fill in any
missing data.  Furthermore, if the PurpleAir device has two sensors,
`purple-proxy` adds average fields for those sensor readings.

See `weewx-purple` and `purple-proxy` in action on the following pages:
* [Weatherbaord(TM) Report](https://www.paloaltoweather.com/weatherboard.html)
* [LiveSeasons Report](https://www.paloaltoweather.com/index.html).

# Installation Instructions
1. Run the following command.

`sudo /home/weewx/bin/wee_extension --install ~/software/weewx-purple`

Note: The above command assumes a WeeWX installation of `/home/weewx` and
      that this extension was downloaded to `~/software/weewx-purple`.
      Adjust the command as necessary.

2. To get average readings over the archive period and to not miss any
   data when weewx is down, install [purple-proxy](https://github.com/chaunceygardiner/purple-proxy).

# How to access weewx-purple fields in reports.

Detailed instructions are pending, below is a quick and dirty set of instructions.
At prsent, one will need to browse the code for more detail.

To report the AQI average (averaged between the sensor and the 'B' sensor of
an outdoor PurpleAir sensor), use the following:

```
$latest('purple_binding').pm2_5_aqi_avg
```

## Licensing

weewx-purple is licensed under the GNU Public License v3.
