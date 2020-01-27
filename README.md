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
* [Weatherbaord(TM) Report](https://www.paloaltoweather.com/weatherboard/)
* [LiveSeasons Report](https://www.paloaltoweather.com/index.html).

# Installation Instructions

1. cd to the directory where this extension was cloned from github, for example:
   `cd ~/software/weewx-purple`

1. Run the following command.

   `sudo /home/weewx/bin/wee_extension --install .`

    Note: The above command assumes a WeeWX installation of `/home/weewx`.
      Adjust the command as necessary.

1. Edit the `Purple` section of weewx.conf (which was created by the install
   above).  Up to two PurpleAir sensors can be configured, as well as up to four
   purple proxies.  Note: the order in which sensors/proxies are interrogated
   is: `PrimaryProxy`, `SecondaryProxy`, `PrimarySensor`, `SecondarySensor`.
   The first sensor/proxy that answers is the one used to answer the WeeWX
   request.

   ```
   [Purple]
       data_binding = purple_binding
       [[PrimarySensor]]
           enable = true
           hostname = purple-air
           port = 80
           timeout = 15
       [[SecondarySensor]]
           enable = false
           hostname = purple-air2
           port = 80
           timeout = 15
       [[PrimaryProxy]]
           enable = false
           hostname = proxy
           port = 8000
           timeout = 5
       [[SecondaryProxy]]
           enable = false
           hostname = proxy2
           port = 8000
           timeout = 5
       [[TertiaryProxy]]
           enable = false
           hostname = proxy3
           port = 8000
           timeout = 5
       [[QuaternaryProxy]]
           enable = false
           hostname = proxy4
           port = 8000
           timeout = 5
   ```

1. To get average readings over the archive period and to not miss archive
   periods when WeeWX isn't running, install
   [purple-proxy](https://github.com/chaunceygardiner/purple-proxy).

# How to access weewx-purple fields in reports.

Detailed instructions are pending, below is a quick and dirty set of instructions.
At present, one will need to browse the code for more detail.

For PurpleAir outdoor sensors, to report the AQI average of the A and B sensors,
use the following:

```
$latest('purple_binding').pm2_5_aqi_avg
```

To report on just the A sensor in the outdoor sensor, or the only sensor in an
indoor sensor, use the following:

```
$latest('purple_binding').pm2_5_aqi
```

Lastly, to report on just the B sensor in the outdoor sensor, use the following:

```
$latest('purple_binding').pm2_5_aqi_b
```

## Licensing

weewx-purple is licensed under the GNU Public License v3.
