# Copyright 2020-2024 by John A Kline <john@johnkline.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
WeeWX module that records PurpleAir air quality sensor readings.
"""

import json
import logging
import math
import requests
import sys
import threading
import time

from dateutil import tz
from dateutil.parser import parse
from dateutil.parser import ParserError

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import weeutil.logger
import weeutil.weeutil
import weewx
import weewx.accum
import weewx.units
import weewx.xtypes

from weewx.units import ValueTuple
from weeutil.weeutil import timestamp_to_string
from weeutil.weeutil import to_bool
from weeutil.weeutil import to_float
from weeutil.weeutil import to_int
from weewx.engine import StdService

log = logging.getLogger(__name__)

WEEWX_PURPLE_VERSION = "5.0.1"

if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
    raise weewx.UnsupportedFeature(
        "weewx-purple requires Python 3.7 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))

if weewx.__version__ < "4":
    raise weewx.UnsupportedFeature(
        "weewx-purple requires WeeWX 4, found %s" % weewx.__version__)

# Set up observation types not in weewx.units

weewx.units.USUnits['air_quality_index']       = 'aqi'
weewx.units.MetricUnits['air_quality_index']   = 'aqi'
weewx.units.MetricWXUnits['air_quality_index'] = 'aqi'

weewx.units.USUnits['air_quality_color']       = 'aqi_color'
weewx.units.MetricUnits['air_quality_color']   = 'aqi_color'
weewx.units.MetricWXUnits['air_quality_color'] = 'aqi_color'

weewx.units.default_unit_label_dict['aqi']  = ' AQI'
weewx.units.default_unit_label_dict['aqi_color'] = ' RGB'

weewx.units.default_unit_format_dict['aqi']  = '%d'
weewx.units.default_unit_format_dict['aqi_color'] = '%d'

weewx.units.obs_group_dict['pm2_5_aqi'] = 'air_quality_index'
weewx.units.obs_group_dict['pm2_5_aqi_color'] = 'air_quality_color'

class Source:
    def __init__(self, config_dict, name, is_proxy):
        self.is_proxy = is_proxy
        # Raise KeyError if name not in dictionary.
        source_dict = config_dict[name]
        self.enable = to_bool(source_dict.get('enable', False))
        self.hostname = source_dict.get('hostname', '')
        if is_proxy:
            self.port = to_int(source_dict.get('port', 8000))
        else:
            self.port = to_int(source_dict.get('port', 80))
        self.timeout  = to_int(source_dict.get('timeout', 10))

@dataclass
class Concentrations:
    timestamp       : float
    pm1_0           : float
    pm10_0          : float
    pm2_5_cf_1      : float
    pm2_5_cf_1_b    : Optional[float]
    current_temp_f  : int
    current_humidity: int

@dataclass
class Configuration:
    lock            : threading.Lock
    concentrations  : Optional[Concentrations] # Controlled by lock
    poll_secs       : int                      # Immutable
    fresh_secs      : int                      # Immutable
    sources         : List[Source]             # Immutable

def datetime_from_reading(dt_str):
    dt_str = dt_str.replace('z', 'UTC')
    tzinfos = {'CST': tz.gettz("UTC")}
    return parse(dt_str, tzinfos=tzinfos)

def reraise_if_terminate(e: BaseException) -> None:
    """weewxd stops by raising Terminate from its SIGTERM signal handler --
    inside whatever the main thread is executing at that instant.  Every
    broad exception handler on a main-thread path must call this first and
    hand the exception back, or weewx cannot shut down.  weewxd runs as
    __main__, so its Terminate class cannot be imported here and is
    recognized by name."""
    if type(e).__name__ == 'Terminate':
        raise e

def get_concentrations(cfg: Configuration):
    for source in cfg.sources:
        if source.enable:
            record = collect_data(source.hostname,
                                  source.port,
                                  source.timeout,
                                  source.is_proxy)
            if record is not None:
                log.debug('get_concentrations: source: %s' % record)
                reading_ts = to_int(record['dateTime'])
                age_of_reading = time.time() - reading_ts
                # Ignore old readings.  We can't accept a reading of age
                # fresh_secs (or close to it) because the reading will age
                # out before the next poll.  Reduce fresh_secs - poll_secs
                # by 5s (as a buffer).
                if abs(age_of_reading) > (cfg.fresh_secs - cfg.poll_secs - 5.0):
                    log.info('Ignoring reading from %s:%d--age: %d seconds.' % (
                        source.hostname, source.port, age_of_reading))
                    continue
                concentrations = Concentrations(
                    timestamp        = reading_ts,
                    pm1_0            = to_float(record['pm1_0_atm']),
                    pm10_0           = to_float(record['pm10_0_atm']),
                    pm2_5_cf_1       = to_float(record['pm2_5_cf_1']),
                    pm2_5_cf_1_b     = None, # If there is a second sensor, this will be updated below.
                    current_temp_f   = to_int(record['current_temp_f']),
                    current_humidity = to_int(record['current_humidity']),
                )
                # If there is a 'b' sensor, add it in and average the readings
                log.debug('get_concentrations: concentrations BEFORE averaging in b reading: %s' % concentrations)
                if 'pm1_0_atm_b' in record:
                    concentrations.pm1_0        = (concentrations.pm1_0  + to_float(record['pm1_0_atm_b'])) / 2.0
                    concentrations.pm2_5_cf_1_b = to_float(record['pm2_5_cf_1_b'])
                    concentrations.pm10_0       = (concentrations.pm10_0 + to_float(record['pm10_0_atm_b'])) / 2.0
                log.debug('get_concentrations: concentrations: %s' % concentrations)
                return concentrations
    log.error('Could not get concentrations from any source.')
    return None

def check_type(j: Dict[str, Any], t, names: List[str]) -> Tuple[bool, str]:
    """Check that each named field in j is an instance of t.  JSON parses
    whole numbers as int, so int is also acceptable where float is expected.
    bool is never acceptable (JSON true/false parse as bool, a subclass of
    int)."""
    acceptable: Tuple[type, ...] = (float, int) if t is float else (t,)
    try:
        for name in names:
            x = j[name]
            if isinstance(x, bool) or not isinstance(x, acceptable):
                return False, '%s is not an instance of %s: %s' % (name, t, j[name])
        return True, ''
    except KeyError as e:
        return False, 'check_type: could not find key: %s' % e
    except Exception as e:
        reraise_if_terminate(e)
        return False, 'check_type: exception: %s' % e

def exhibits_twenty_fold_delta(val_1: float, val_2: float) -> bool:
    # If either value is zero, skip this check.
    if val_1 == 0.0 or val_2 == 0.0:
        return False
    twenty_fold_diff = (val_1 * 20.0) < val_2 or (val_2 * 20.0) < val_1
    if twenty_fold_diff:
        # The twenty_fold_diff could be because 1 reading is close to zero.
        # As such, return False if the delta between the readings is < 10.0
        if abs(val_1 - val_2) < 10.0:
            return False
    return twenty_fold_diff

def is_sane(j: Dict[str, Any]) -> Tuple[bool, str]:
    if 'DateTime' not in j:
        return False, 'DateTime not found in: %r' % j
    if not isinstance(j['DateTime'], str):
        return False, 'DateTime is not a string: %r' % j['DateTime']
    try:
        datetime_from_reading(j['DateTime'])
    except ParserError:
        return False, 'DateTime is not an instance of datetime: %s' % j['DateTime']

    ok, reason = check_type(j, int, ['current_temp_f','current_humidity','current_dewpoint_f'])
    if not ok:
        return False, reason

    ok, reason = check_type(j, float, ['pressure'])
    if not ok:
        return False, reason

    # Sensor A
    ok, reason = check_type(j, float, ['pm1_0_cf_1','pm1_0_atm','p_0_3_um','pm2_5_cf_1',
            'pm2_5_atm','p_0_5_um','pm10_0_cf_1','pm10_0_atm'])
    if not ok:
        return False, reason
    ok, reason = check_type(j, int, ['pm2.5_aqi'])
    if not ok:
        return False, reason

    # Sensor B
    if 'pm2.5_aqi_b' in j:
        ok, reason = check_type(j, float, ['pm1_0_cf_1_b','pm1_0_atm_b','p_0_3_um_b','pm2_5_cf_1_b',
                'pm2_5_atm_b','p_0_5_um_b','pm10_0_cf_1_b','pm10_0_atm_b'])
        if not ok:
            return False, reason
        ok, reason = check_type(j, int, ['pm2.5_aqi_b'])
        if not ok:
            return False, reason
        # Check on agreement between the sensors
        if exhibits_twenty_fold_delta(j['pm2_5_cf_1'], j['pm2_5_cf_1_b']):
            return False, 'Sensors disagree wildly for pm2_5_cf_1 (%f, %f)' % (j['pm2_5_cf_1'], j['pm2_5_cf_1_b'])
        if exhibits_twenty_fold_delta(j['pm1_0_cf_1'], j['pm1_0_cf_1_b']):
            return False, 'Sensors disagree wildly for pm1_0_cf_1 (%f, %f)' % (j['pm1_0_cf_1'], j['pm1_0_cf_1_b'])
        if exhibits_twenty_fold_delta(j['pm10_0_cf_1'], j['pm10_0_cf_1_b']):
            return False, 'Sensors disagree wildly for pm10_0_cf_1 (%f, %f)' % (j['pm10_0_cf_1'], j['pm10_0_cf_1_b'])

    return True, ''

def collect_data(hostname, port, timeout, proxy = False):
    url = 'http://%s:%s/json' % (hostname, port)

    try:
        # fetch data
        log.debug('collect_data: fetching from url: %s, timeout: %d' % (url, timeout))
        r = requests.get(url=url, timeout=timeout)
        r.raise_for_status()
        log.debug('collect_data: %s returned %r' % (hostname, r))
        # convert to json
        j = r.json()
        log.debug('collect_data: json returned from %s is: %r' % (hostname, j))
        # Check for sanity
        sane, reason = is_sane(j)
        if not sane:
            log.info('purpleair reading from %s not sane, %s: %s' % (hostname, reason, j))
            return None
        time_of_reading = datetime_from_reading(j['DateTime'])
    except Exception as e:
        reraise_if_terminate(e)
        log.info('collect_data: Attempt to fetch from: %s failed: %s.' % (hostname, e))
        return None

    # create a record
    log.debug('Successful read from %s.' % hostname)
    return populate_record(time_of_reading.timestamp(), j)

def populate_record(ts, j):
    record = dict()
    record['dateTime'] = ts
    record['usUnits'] = weewx.US

    # put items into record
    missed = []

    def get_and_update_missed(key):
        if key in j:
            return j[key]
        else:
            missed.append(key)
            return None

    record['current_temp_f'] = get_and_update_missed('current_temp_f')
    record['current_humidity'] = get_and_update_missed('current_humidity')
    record['current_dewpoint_f'] = get_and_update_missed('current_dewpoint_f')

    pressure = get_and_update_missed('pressure')
    if pressure is not None:
        # convert pressure from mbar to US units.
        # FIXME: is there a cleaner way to do this
        pressure, units, group = weewx.units.convertStd((pressure, 'mbar', 'group_pressure'), weewx.US)
        record['purple_pressure'] = pressure

    if missed:
        log.info("Sensor didn't report field(s): %s" % ','.join(missed))

    # for each concentration counter, grab A, B and the average of the A and B channels and push into the record
    for key in ['pm1_0_cf_1', 'pm1_0_atm', 'pm2_5_cf_1', 'pm2_5_atm', 'pm10_0_cf_1', 'pm10_0_atm']:
        record[key] = j[key]
        key_b = key + '_b'
        if key_b in j.keys():
            record[key_b] = j[key_b]
            record[key + '_avg'] = (j[key] + j[key_b]) / 2.0

    return record

class Purple(StdService):
    """Collect Purple Air air quality measurements."""

    def __init__(self, engine, config_dict):
        super(Purple, self).__init__(engine, config_dict)
        log.info("Service version is %s." % WEEWX_PURPLE_VERSION)

        self.engine = engine
        self.config_dict = config_dict.get('Purple', {})
        self.stale_logged = False

        poll_secs  = to_int(self.config_dict.get('poll_secs', 15))
        fresh_secs = max(120, 3 * poll_secs)

        self.cfg = Configuration(
            lock             = threading.Lock(),
            concentrations   = None,
            poll_secs        = poll_secs,
            fresh_secs       = fresh_secs,
            sources          = Purple.configure_sources(self.config_dict))

        log.info('poll_secs : %d' % self.cfg.poll_secs)
        log.info('fresh_secs: %d' % self.cfg.fresh_secs)
        source_count = 0
        for source in self.cfg.sources:
            if source.enable:
                source_count += 1
                log.info(
                    'Source %d for PurpleAir readings: %s %s:%s, proxy: %s, timeout: %d' % (
                    source_count, 'purple-proxy' if source.is_proxy else 'sensor',
                    source.hostname, source.port, source.is_proxy, source.timeout))
        if source_count == 0:
            log.error('No sources configured for purple extension.  Purple extension is inoperable.')
        else:
            weewx.xtypes.xtypes.insert(0, AQI())
            AQI.register_accumulator_extractors()

            with self.cfg.lock:
                self.cfg.concentrations = get_concentrations(self.cfg)

            # Start a thread to query proxies and make aqi available to loopdata
            dp: DevicePoller = DevicePoller(self.cfg)
            t: threading.Thread = threading.Thread(target=dp.poll_device, name='Purple', daemon=True)
            t.start()

            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

    def new_loop_packet(self, event):
        log.debug('new_loop_packet(%s)' % event)
        with self.cfg.lock:
            log.debug('new_loop_packet: self.cfg.concentrations: %s' % self.cfg.concentrations)
            if self.cfg.concentrations is not None and \
                    self.cfg.concentrations.timestamp is not None and \
                    self.cfg.concentrations.timestamp + self.cfg.fresh_secs >= time.time():
                if self.stale_logged:
                    log.info('Fresh concentrations available again.')
                    self.stale_logged = False
                log.debug('Time of reading being inserted: %s' % timestamp_to_string(self.cfg.concentrations.timestamp))
                # Insert pm1_0, pm2_5, pm10_0, aqi and aqic into loop packet.
                if self.cfg.concentrations.pm1_0 is not None:
                    event.packet['pm1_0'] = self.cfg.concentrations.pm1_0
                    log.debug('Inserted packet[pm1_0]: %f into packet.' % event.packet['pm1_0'])
                if self.cfg.concentrations.pm2_5_cf_1_b is not None:
                    b_reading = self.cfg.concentrations.pm2_5_cf_1_b
                else:
                    b_reading = self.cfg.concentrations.pm2_5_cf_1 # Dup A sensor reading
                if (self.cfg.concentrations.pm2_5_cf_1 is not None
                        and b_reading is not None
                        and self.cfg.concentrations.current_humidity is not None
                        and self.cfg.concentrations.current_temp_f is not None):
                    event.packet['pm2_5'] = AQI.compute_pm2_5_us_epa_correction(
                            self.cfg.concentrations.pm2_5_cf_1, b_reading,
                            self.cfg.concentrations.current_humidity, self.cfg.concentrations.current_temp_f)
                    log.debug('Inserted packet[pm2_5]: %f into packet.' % event.packet['pm2_5'])
                if self.cfg.concentrations.pm10_0 is not None:
                    event.packet['pm10_0'] = self.cfg.concentrations.pm10_0
                    log.debug('Inserted packet[pm10_0]: %f into packet.' % event.packet['pm10_0'])
                if 'pm2_5' in event.packet:
                    event.packet['pm2_5_aqi'] = AQI.compute_pm2_5_aqi(event.packet['pm2_5'])
                if 'pm2_5_aqi' in event.packet:
                    event.packet['pm2_5_aqi_color'] = AQI.compute_pm2_5_aqi_color(event.packet['pm2_5_aqi'])
            else:
                # Log at error level once per outage, not once per loop packet.
                if not self.stale_logged:
                    log.error('Found no fresh concentrations to insert.')
                    self.stale_logged = True
                else:
                    log.debug('Found no fresh concentrations to insert.')

    @staticmethod
    def configure_sources(config_dict):
        sources = []
        # Configure Proxies
        idx = 0
        while True:
            idx += 1
            try:
                source = Source(config_dict, 'Proxy%d' % idx, True)
                sources.append(source)
            except KeyError:
                break
        # Configure Sensors
        idx = 0
        while True:
            idx += 1
            try:
                source = Source(config_dict, 'Sensor%d' % idx, False)
                sources.append(source)
            except KeyError:
                break

        return sources

class DevicePoller:
    def __init__(self, cfg: Configuration):
        self.cfg = cfg

    def poll_device(self) -> None:
        log.debug('poll_device: start')
        while True:
            try:
                log.debug('poll_device: calling get_concentrations.')
                concentrations = get_concentrations(self.cfg)
            except Exception as e:
                log.error('poll_device exception: %s' % e)
                weeutil.logger.log_traceback(log.critical, "    ****  ")
                concentrations = None
            log.debug('poll_device: concentrations: %s' % concentrations)
            if concentrations is not None:
                with self.cfg.lock:
                    self.cfg.concentrations = concentrations
            log.debug('poll_device: Sleeping for %d seconds.' % self.cfg.poll_secs)
            time.sleep(self.cfg.poll_secs)

class AQI(weewx.xtypes.XType):
    """
    AQI XType which computes the AQI (air quality index) from
    the pm2_5 value.
    """

    def __init__(self):
        pass

    @staticmethod
    def register_accumulator_extractors() -> None:
        """Tell the accumulator not to extract the loop-injected AQI fields
        into archive records.  new_loop_packet computes AQI per loop packet
        under the same names this xtype serves; without this, WeeWX's default
        avg extractor would fold a meaningless averaged AQI into the archive
        record, and $current would use it instead of the xtype during
        real-time report generation.  extractor = noop drops the fields so
        lookups fall through to the xtype -- the same pattern WeeWX's own
        defaults use for windSpeed.  A user's [Accumulator] section takes
        precedence over these entries."""
        weewx.accum.accum_dict.extend({
            'pm2_5_aqi'      : {'extractor': 'noop'},
            'pm2_5_aqi_color': {'extractor': 'noop'},
        })

    agg_sql_dict = {
        'avg': "SELECT AVG(pm2_5), MIN(usUnits) FROM %(table_name)s "
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL",
        'count': "SELECT COUNT(dateTime), MIN(usUnits) FROM %(table_name)s "
                 "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL",
        'first': "SELECT pm2_5, usUnits FROM %(table_name)s "
                 "WHERE dateTime = (SELECT MIN(dateTime) FROM %(table_name)s "
                 "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL)",
        'last': "SELECT pm2_5, usUnits FROM %(table_name)s "
                "WHERE dateTime = (SELECT MAX(dateTime) FROM %(table_name)s "
                "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL)",
        'min': "SELECT pm2_5, usUnits FROM %(table_name)s "
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL "
               "ORDER BY pm2_5 ASC LIMIT 1;",
        'max': "SELECT pm2_5, usUnits FROM %(table_name)s "
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL "
               "ORDER BY pm2_5 DESC LIMIT 1;",
    }

    day_boundary_avg_min_max_sql_dict = {
        'usUnits': "SELECT usUnits from %(table_name)s ORDER BY dateTime DESC LIMIT 1;",
        'avg'    : "SELECT sum(wsum) / sum(sumtime) FROM %(table_name)s%(pm2_5_summary_suffix)s "
                   "WHERE dateTime >= %(start)s AND dateTime < %(stop)s ",
        'min'    : "SELECT min FROM %(table_name)s%(pm2_5_summary_suffix)s "
                   "WHERE dateTime >= %(start)s AND dateTime < %(stop)s "
                   "ORDER BY min ASC LIMIT 1;",
        'max'    : "SELECT max FROM %(table_name)s%(pm2_5_summary_suffix)s "
                   "WHERE dateTime >= %(start)s AND dateTime < %(stop)s "
                   "ORDER BY max DESC LIMIT 1;",
    }

    @staticmethod
    def compute_pm2_5_aqi(pm2_5):
        #             U.S. EPA PM2.5 AQI (May 2024 AirNow TAD)
        #
        #  AQI Category  AQI Value  24-hr PM2.5
        # Good             0 -  50    0.0 -   9.0
        # Moderate        51 - 100    9.1 -  35.4
        # USG            101 - 150   35.5 -  55.4
        # Unhealthy      151 - 200   55.5 - 125.4
        # Very Unhealthy 201 - 300  125.5 - 225.4
        # Hazardous      301 - 500  225.5 - 325.4
        #
        # Concentrations above 325.4 map to AQI values above 500, continuing
        # on the Hazardous slope (TAD breakpoint-table footnote 4 and the
        # "AQI values above 500" FAQ).  There is no upper cap.

        # The EPA standard for AQI says to truncate PM2.5 to one decimal place.
        # See https://www3.epa.gov/airnow/aqi-technical-assistance-document-sept2018.pdf
        x = math.trunc(pm2_5 * 10) / 10

        if x <= 9.0: # Good
            aqi = round(x / 9.0 * 50)
        elif x <= 35.4: # Moderate
            aqi = round((x - 9.1) / 26.3 * 49.0 + 51.0)
        elif x <= 55.4: # Unhealthy for sensitive groups
            aqi = round((x - 35.5) / 19.9 * 49.0 + 101.0)
        elif x <= 125.4: # Unhealthy
            aqi = round((x - 55.5) / 69.9 * 49.0 + 151.0)
        elif x <= 225.4: # Very Unhealthy
            aqi = round((x - 125.5) / 99.9 * 99.0 + 201.0)
        else: # Hazardous
            aqi = round((x - 225.5) / 99.9 * 199.0 + 301.0)

        # A negative pm2_5 (only possible if a bogus value reached the
        # database by some other means) must not map below zero.
        return max(0, aqi)

    @staticmethod
    def compute_pm2_5_aqi_color(pm2_5_aqi):
        if pm2_5_aqi <= 50:
            return 228 << 8                      # Green
        elif pm2_5_aqi <= 100:
            return (255 << 16) + (255 << 8)      # Yellow
        elif pm2_5_aqi <=  150:
            return (255 << 16) + (126 << 8)      # Orange
        elif pm2_5_aqi <= 200:
            return 255 << 16                     # Red
        elif pm2_5_aqi <= 300:
            return (143 << 16) + (63 << 8) + 151 # Purple
        else:
            return (126 << 16) + 35              # Maroon

    @staticmethod
    def compute_pm2_5_us_epa_correction(pm2_5_cf_1: float, pm2_5_cf_1_b: float, current_humidity: int, current_temp_f: int) -> float:
        # 2021 EPA Correction
        # Low Concentration PAcf_1 ≤ 343 μg m-3  : PM2.5 = 0.52 x PAcf_1 - 0.086 x RH + 5.75
        # High Concentration PAcf_1 > 343 μg m-3 : PM2.5 = 0.46 x PAcf_1 + 3.93 x 10**-4 x PAcf_1**2 + 2.97
        #
        avg_cf_1 = (pm2_5_cf_1 + pm2_5_cf_1_b) / 2.0
        if avg_cf_1 <= 343.0:
            val = 0.52 * avg_cf_1 - 0.086 * current_humidity + 5.75
        else:
            val = 0.46 * avg_cf_1 + 3.93 * 10**-4 * avg_cf_1 ** 2 + 2.97

        return val if val >= 0.0 else 0.0

    @staticmethod
    def get_scalar(obs_type, record, db_manager=None):
        log.debug('get_scalar(%s)' % obs_type)
        if obs_type not in [ 'pm2_5_aqi', 'pm2_5_aqi_color' ]:
            raise weewx.UnknownType(obs_type)
        log.debug('get_scalar(%s)' % obs_type)
        if record is None:
            log.debug('get_scalar called where record is None.')
            raise weewx.CannotCalculate(obs_type)
        if 'pm2_5' not in record:
            # Returning CannotCalculate causes exception in ImageGenerator, return UnknownType instead.
            # ERROR weewx.reportengine: Caught unrecoverable exception in generator 'weewx.imagegenerator.ImageGenerator'
            log.debug('get_scalar called where record does not contain pm2_5.')
            raise weewx.UnknownType(obs_type)
        if record['pm2_5'] is None:
            # Returning CannotCalculate causes exception in ImageGenerator, return UnknownType instead.
            # ERROR weewx.reportengine: Caught unrecoverable exception in generator 'weewx.imagegenerator.ImageGenerator'
            # This will happen for any catchup records inserted at weewx startup.
            log.debug('get_scalar called where record[pm2_5] is None.')
            raise weewx.UnknownType(obs_type)
        try:
            pm2_5 = record['pm2_5']
            if obs_type == 'pm2_5_aqi':
                value = AQI.compute_pm2_5_aqi(pm2_5)
            else: # pm2_5_aqi_color
                value = AQI.compute_pm2_5_aqi_color(AQI.compute_pm2_5_aqi(pm2_5))
            t, g = weewx.units.getStandardUnitType(record['usUnits'], obs_type)
            # Form the ValueTuple and return it:
            return weewx.units.ValueTuple(value, t, g)
        except KeyError:
            # Don't have everything we need. Raise an exception.
            raise weewx.CannotCalculate(obs_type)

    @staticmethod
    def get_series(obs_type, timespan, db_manager, aggregate_type=None, aggregate_interval=None):
        """Get a series, possibly with aggregation.
        """

        if obs_type not in [ 'pm2_5_aqi', 'pm2_5_aqi_color' ]:
            raise weewx.UnknownType(obs_type)

        log.debug('get_series(%s, %s, %s, aggregate:%s, aggregate_interval:%s)' % (
            obs_type, timestamp_to_string(timespan.start), timestamp_to_string(
            timespan.stop), aggregate_type, aggregate_interval))

        #  Prepare the lists that will hold the final results.
        start_vec = list()
        stop_vec = list()
        data_vec = list()

        # Is aggregation requested?
        if aggregate_type:
            # Yes. Just use the regular series function.
            return weewx.xtypes.ArchiveTable.get_series(obs_type, timespan, db_manager, aggregate_type,
                                           aggregate_interval)
        else:
            # No aggregation.
            sql_str = 'SELECT dateTime, usUnits, `interval`, pm2_5 FROM %s ' \
                      'WHERE dateTime >= ? AND dateTime <= ? AND pm2_5 IS NOT NULL' \
                      % db_manager.table_name
            std_unit_system = None

            for record in db_manager.genSql(sql_str, timespan):
                ts, unit_system, interval, pm2_5 = record
                if std_unit_system:
                    if std_unit_system != unit_system:
                        raise weewx.UnsupportedFeature(
                            "Unit type cannot change within a time interval.")
                else:
                    std_unit_system = unit_system

                if obs_type == 'pm2_5_aqi':
                    value = AQI.compute_pm2_5_aqi(pm2_5)
                else: # pm2_5_aqi_color
                    value = AQI.compute_pm2_5_aqi_color(AQI.compute_pm2_5_aqi(pm2_5))
                log.debug('get_series(%s): %s - %s - %s' % (obs_type,
                    timestamp_to_string(ts - interval * 60),
                    timestamp_to_string(ts), value))
                start_vec.append(ts - interval * 60)
                stop_vec.append(ts)
                data_vec.append(value)

            unit, unit_group = weewx.units.getStandardUnitType(std_unit_system, obs_type,
                                                               aggregate_type)

        return (ValueTuple(start_vec, 'unix_epoch', 'group_time'),
                ValueTuple(stop_vec, 'unix_epoch', 'group_time'),
                ValueTuple(data_vec, unit, unit_group))

    @staticmethod
    def get_aggregate(obs_type, timespan, aggregate_type, db_manager, **option_dict):
        """Returns an aggregation of pm2_5_aqi over a timespan by using the main archive
        table.

        obs_type: Must be 'pm2_5_aqi' or 'pm2_5_aqi_color'.

        timespan: An instance of weeutil.Timespan with the time period over which aggregation is to
        be done.

        aggregate_type: The type of aggregation to be done. For this function, must be 'avg',
        'count', 'first', 'last', 'min', or 'max'. Anything else will cause
        weewx.UnknownAggregation to be raised.  ('sum' is deliberately not
        supported: the AQI of summed concentrations is not a meaningful
        quantity.)

        db_manager: An instance of weewx.manager.Manager or subclass.

        option_dict: Not used in this version.

        returns: A ValueTuple containing the result.
        """
        if obs_type not in [ 'pm2_5_aqi', 'pm2_5_aqi_color' ]:
            raise weewx.UnknownType(obs_type)

        log.debug('get_aggregate(%s, %s, %s, aggregate:%s)' % (
            obs_type, timestamp_to_string(timespan.start),
            timestamp_to_string(timespan.stop), aggregate_type))

        aggregate_type = aggregate_type.lower()

        # Raise exception if we don't know about this type of aggregation
        if aggregate_type not in list(AQI.agg_sql_dict.keys()):
            raise weewx.UnknownAggregation(aggregate_type)

        # Form the interpolation dictionary
        interpolation_dict = {
            'start': timespan.start,
            'stop': timespan.stop,
            'table_name': db_manager.table_name,
            'pm2_5_summary_suffix': '_day_pm2_5'
        }

        # The daily summary table can only be used if the timespan covers
        # whole archive days: both endpoints on local midnight.  A span
        # whose length merely happens to be a multiple of 24 hours (e.g.,
        # a trailing 24-hour window) must use the regular archive table.
        on_day_boundary = (timespan.start != timespan.stop
                           and weeutil.weeutil.isStartOfDay(timespan.start)
                           and weeutil.weeutil.isStartOfDay(timespan.stop))
        log.debug('day_boundary start: %r stop: %r on_day_boundary: %s' % (
            timespan.start, timespan.stop, on_day_boundary))
        if aggregate_type in list(AQI.day_boundary_avg_min_max_sql_dict.keys()) and on_day_boundary:
            select_stmt = AQI.day_boundary_avg_min_max_sql_dict[aggregate_type] % interpolation_dict
            select_usunits_stmt = AQI.day_boundary_avg_min_max_sql_dict['usUnits'] % interpolation_dict
            need_usUnits = True
        else:
            select_stmt = AQI.agg_sql_dict[aggregate_type] % interpolation_dict
            need_usUnits = False
        if need_usUnits:
            row = db_manager.getSql(select_usunits_stmt)
            if row:
                std_unit_system, = row
            else:
                std_unit_system = None
        row = db_manager.getSql(select_stmt)
        if row:
            if need_usUnits:
                value, = row
            else:
                value, std_unit_system = row
        else:
            value = None
            std_unit_system = None

        # A count is a count of records; every other aggregate is a pm2_5
        # concentration that must be converted to an AQI (or color).
        if value is not None and aggregate_type != 'count':
            if obs_type == 'pm2_5_aqi':
                value = AQI.compute_pm2_5_aqi(value)
            else: # pm2_5_aqi_color
                value = AQI.compute_pm2_5_aqi_color(AQI.compute_pm2_5_aqi(value))
        t, g = weewx.units.getStandardUnitType(std_unit_system, obs_type, aggregate_type)
        # Form the ValueTuple and return it:
        log.debug('get_aggregate(%s, %s, %s, aggregate:%s, select_stmt: %s, returning %s)' % (
            obs_type, timestamp_to_string(timespan.start), timestamp_to_string(timespan.stop),
            aggregate_type, select_stmt, value))
        return weewx.units.ValueTuple(value, t, g)

if __name__ == "__main__":
    usage = """%prog [options] [--help] [--debug]"""

    import weeutil.logger

    def main():
        import optparse
        parser = optparse.OptionParser(usage=usage)
        parser.add_option('--config', dest='cfgfn', type=str, metavar="FILE",
                          help="Use configuration file FILE. Default is /etc/weewx/weewx.conf or /home/weewx/weewx.conf")
        parser.add_option('--test-collector', dest='tc', action='store_true',
                          help='test the data collector')
        parser.add_option('--test-is-sane', dest='sane_test', action='store_true',
                          help='test the is_sane function')
        parser.add_option('--hostname', dest='hostname', action='store',
                          help='hostname to use with --test-collector')
        parser.add_option('--port', dest='port', action='store',
                          type=int, default=80,
                          help="port to use with --test-collector. Default is '80'")
        (options, args) = parser.parse_args()

        weeutil.logger.setup('purple', {})

        if options.tc:
            if not options.hostname:
                parser.error('--test-collector requires --hostname argument')
            test_collector(options.hostname, options.port)
        if options.sane_test:
            test_is_sane()

    def test_collector(hostname, port):
        while True:
            print(collect_data(hostname, port, 10))
            time.sleep(5)

    def test_is_sane():
        good_proxy = ('{"DateTime": "2020/03/20T17:16:00z", "current_temp_f": 61,'
            ' "current_humidity": 49, "current_dewpoint_f": 41, "pressure": 1024.255,'
            ' "pm1_0_cf_1": 2.39, "pm1_0_atm": 2.39, "p_0_3_um": 641.75,'
            ' "pm2_5_cf_1": 3.85, "pm2_5_atm": 3.85, "p_0_5_um": 179.98,'
            ' "pm10_0_cf_1": 5.17, "pm10_0_atm": 5.17, "pm2.5_aqi": 16,'
            ' "p25aqic": "rgb(8,229,0)", "pm1_0_cf_1_b": 1.86, "pm1_0_atm_b": 1.86,'
            ' "p_0_3_um_b": 544.5, "pm2_5_cf_1_b": 2.97, "pm2_5_atm_b": 2.97,'
            ' "p_0_5_um_b": 149.48, "pm10_0_cf_1_b": 3.41, "pm10_0_atm_b": 3.41,'
            ' "pm2.5_aqi_b": 12, "p25aqic_b": "rgb(4,228,0)"}')
        good_device = ('{"SensorId":"84:f3:eb:36:38:fe","DateTime":"2020/03/20T17:18:02z",'
            '"Geo":"PurpleAir-38fe","Mem":19176,"memfrag":15,"memfb":16360,"memcs":768,'
            '"Id":16220,"lat":37.431599,"lon":-122.111000,"Adc":0.03,"loggingrate":15,'
            '"place":"outside","version":"6.01","uptime":215685,"rssi":-59,"period":120,'
            '"httpsuccess":10842,"httpsends":10842,"hardwareversion":"2.0",'
            '"hardwarediscovered":"2.0+OPENLOG+NO-DISK+DS3231+BME280+PMSX003-B+PMSX003-A",'
            '"current_temp_f":61,"current_humidity":48,"current_dewpoint_f":41,'
            '"pressure":1024.30,"p25aqic_b":"rgb(4,228,0)","pm2.5_aqi_b":12,'
            '"pm1_0_cf_1_b":1.63,"p_0_3_um_b":556.21,"pm2_5_cf_1_b":2.95,'
            '"p_0_5_um_b":150.61,"pm10_0_cf_1_b":3.25,"p_1_0_um_b":22.58,'
            '"pm1_0_atm_b":1.63,"p_2_5_um_b":2.11,"pm2_5_atm_b":2.95,"p_5_0_um_b":0.46,'
            '"pm10_0_atm_b":3.25,"p_10_0_um_b":0.26,"p25aqic":"rgb(10,229,0)",'
            '"pm2.5_aqi":17,"pm1_0_cf_1":2.20,"p_0_3_um":637.30,"pm2_5_cf_1":4.02,'
            '"p_0_5_um":174.22,"pm10_0_cf_1":4.43,"p_1_0_um":28.53,"pm1_0_atm":2.20,'
            '"p_2_5_um":3.97,"pm2_5_atm":4.02,"p_5_0_um":0.50,"pm10_0_atm":4.43,'
            '"p_10_0_um":0.50,"pa_latency":338,"response":201,"response_date":1584724649,'
            '"latency":355,"key1_response":200,"key1_response_date":1584724642,'
            '"key1_count":81455,"ts_latency":805,"key2_response":200,'
            '"key2_response_date":1584724644,"key2_count":81455,"ts_s_latency":796,'
            '"key1_response_b":200,"key1_response_date_b":1584724645,"key1_count_b":81444,'
            '"ts_latency_b":772,"key2_response_b":200,"key2_response_date_b":1584724647,'
            '"key2_count_b":81446,"ts_s_latency_b":796,"wlstate":"Connected","status_0":2,'
            '"status_1":2,"status_2":2,"status_3":2,"status_4":2,"status_5":2,"status_6":2,'
            '"status_7":0,"status_8":2,"status_9":2,"ssid":"ella"}')
        bad_1 = ('{"SensorId":"84:f3:eb:36:38:fe","DateTime":"2020/03/18T05:23:59z",'
            ' "current_temp_f":53, "current_humidity":57, "current_dewpoint_f":38,'
            ' "pressure":1015.94, "pm1_0_cf_1":"nan", "pm1_0_atm":"nan", "p_0_3_um":"nan",'
            ' "pm2_5_cf_1":"nan", "pm2_5_atm":"nan", "p_0_5_um":"nan", "pm10_0_cf_1":"nan",'
            ' "pm10_0_atm":"nan", "pm2.5_aqi":"nan", "p25aqic":"rgb(0,255,255)",'
            ' "pm1_0_cf_1_b":"nan", "pm1_0_atm_b":"nan", "p_0_3_um_b":"nan",'
            ' "pm2_5_cf_1_b":"nan", "pm2_5_atm_b":"nan", "p_0_5_um_b":"nan",'
            ' "pm10_0_cf_1_b":"nan", "pm10_0_atm_b":"nan",'
            ' "pm2_5_aqi_b":"nan", "p25aqic_b":"rgb(0,255,255)"}')
        bad_2 = ('{"DateTime":"2020/03/20T16:01:38z","current_temp_f":54,'
            '"current_humidity":58,"current_dewpoint_f":39,"pressure":1022.78,'
            '"p25aqic_b":"rgb(19,230,0)","pm2.5_aqi_b":21,"pm1_0_cf_1_b":"nan",'
            '"p_0_3_um_b":701.02,"pm2_5_cf_1_b":5.15,"p_0_5_um_b":197.89,'
            '"pm10_0_cf_1_b":6.16,"p_1_0_um_b":35.84,"pm1_0_atm_b":3.11,'
            '"p_2_5_um_b":4.45,"pm2_5_atm_b":5.15,"p_5_0_um_b":1.24,'
            '"pm10_0_atm_b":6.16,"p_10_0_um_b":0.96,"p25aqic":"rgb(36,232,0)",'
            '"pm2.5_aqi":26,"pm1_0_cf_1":3.60,"p_0_3_um":873.50,'
            '"pm2_5_cf_1":6.13,"p_0_5_um":245.18,"pm10_0_cf_1":6.80,'
            '"p_1_0_um":37.50,"pm1_0_atm":3.60,"p_2_5_um":6.47,"pm2_5_atm":6.13,'
            '"p_5_0_um":0.77,"pm10_0_atm":6.80,"p_10_0_um":0.77}')
        j = json.loads(good_proxy)
        sane, _ = is_sane(j)
        assert(sane)
        j = json.loads(good_device)
        sane, _ = is_sane(j)
        assert(sane)
        j = json.loads(bad_1)
        sane, _ = is_sane(j)
        assert(not sane)
        j = json.loads(bad_2)
        sane, _ = is_sane(j)
        assert(not sane)

    main()
