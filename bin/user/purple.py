# Copyright 2020 by John A Kline <john@johnkline.com>
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

import datetime
import json
import logging
import requests
import sys
import threading
import time

from dateutil import tz
from dateutil.parser import parse

from dataclasses import dataclass
from typing import Any, Dict, List

import weeutil.weeutil
import weewx
import weewx.units
import weewx.xtypes

from weewx.units import ValueTuple
from weeutil.weeutil import timestamp_to_string
from weeutil.weeutil import to_bool
from weeutil.weeutil import to_float
from weeutil.weeutil import to_int
from weewx.engine import StdService

log = logging.getLogger(__name__)

WEEWX_PURPLE_VERSION = "2.0"

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

weewx.units.default_unit_label_dict['pm2_5_aqi']  = ' AQI'
weewx.units.default_unit_label_dict['pm2_5_aqi_color'] = ' RGB'

weewx.units.default_unit_format_dict['aqi']  = '%d'
weewx.units.default_unit_format_dict['aqi_color'] = '%d'

weewx.units.obs_group_dict['pm2_5_aqi'] = 'air_quality_index'
weewx.units.obs_group_dict['pm2_5_aqi_color'] = 'air_quality_color'

class Source:
    def __init__(self, config_dict, name, is_proxy):
        self.is_proxy = is_proxy
        # Raise KeyEror if name not in dictionary.
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
    timestamp: float
    pm1_0     : float
    pm2_5     : float
    pm10_0    : float

@dataclass
class Configuration:
    lock            : threading.Lock
    concentrations  : Concentrations # Controlled by lock
    archive_interval: int            # Immutable
    archive_delay   : int            # Immutable
    poll_interval   : int            # Immutable
    sources         : List[Source]   # Immutable

def datetime_from_reading(dt_str):
    dt_str = dt_str.replace('z', 'UTC')
    tzinfos = {'CST': tz.gettz("UTC")}
    return parse(dt_str, tzinfos=tzinfos)

def utc_now():
    return datetime.datetime.now(tz=tz.gettz("UTC"))

def get_concentrations(cfg: Configuration):
    for source in cfg.sources:
        if source.enable:
            record = collect_data(source.hostname,
                                  source.port,
                                  source.timeout,
                                  cfg.archive_interval,
                                  source.is_proxy)
            if record is not None:
                log.debug('get_concentrations: source: %s' % record)
                reading_ts = to_int(record['dateTime'])
                age_of_reading = time.time() - reading_ts
                if age_of_reading > cfg.archive_interval:
                    log.info('Reading from %s:%d is old: %d seconds.' % (
                        source.hostname, source.port, age_of_reading))
                    continue
                concentrations = Concentrations(
                    timestamp  = reading_ts,
                    pm1_0      = to_float(record['pm1_0_cf_1']),
                    pm2_5      = to_float(record['pm2_5_cf_1']),
                    pm10_0     = to_float(record['pm10_0_cf_1']),
                )
                # If there is a 'b' sensor, add it in and average the readings
                log.debug('get_concentrations: concentrations BEFORE averaing in b reading: %s' % concentrations)
                if 'pm1_0_cf_1_b' in record:
                    concentrations.pm1_0      = (concentrations.pm1_0  + to_float(record['pm1_0_cf_1_b'])) / 2.0
                    concentrations.pm2_5      = (concentrations.pm2_5  + to_float(record['pm2_5_cf_1_b'])) / 2.0
                    concentrations.pm10_0     = (concentrations.pm10_0 + to_float(record['pm10_0_cf_1_b'])) / 2.0
                log.debug('get_concentrations: concentrations: %s' % concentrations)
                return concentrations
    log.error('Could not get concentrations from any source.')
    return None

def is_type(j: Dict[str, Any], t, names: List[str]) -> bool:
    try:
        for name in names:
          x = j[name]
          if not isinstance(x, t):
              log.info('%s is not an instance of %s: %s' % (name, t, j[name]))
              return False
        return True
    except KeyError as e:
        log.info('is_type: could not find key: %s' % e)
        return False
    except Exception as e:
        log.info('is_type: exception: %s' % e)
        return False

def is_sane(j: Dict[str, Any]) -> bool:
    time_of_reading = datetime_from_reading(j['DateTime'])
    if not isinstance(time_of_reading, datetime.datetime):
        log.info('DateTime is not an instance of datetime: %s' % j['DateTime'])
        return False

    if not is_type(j, int, ['current_temp_f','current_humidity','current_dewpoint_f']):
        return False

    if not is_type(j, float, ['pressure']):
        return False

    # Sensor A
    if not is_type(j, float, ['pm1_0_cf_1','pm1_0_atm','p_0_3_um','pm2_5_cf_1',
            'pm2_5_atm','p_0_5_um','pm10_0_cf_1','pm10_0_atm']):
        return False
    if not is_type(j, int, ['pm2.5_aqi']):
        return False

    # Sensor B
    if 'pm2.5_aqi_b' in j:
        if not is_type(j, float, ['pm1_0_cf_1_b','pm1_0_atm_b','p_0_3_um_b','pm2_5_cf_1_b',
                'pm2_5_atm_b','p_0_5_um_b','pm10_0_cf_1_b','pm10_0_atm_b']):
            return False
        if not is_type(j, int, ['pm2.5_aqi_b']):
            return False

    return True

def collect_data(hostname, port, timeout, archive_interval, proxy = False):

    j = None
    if proxy:
        url = 'http://%s:%s/fetch-current-record' % (hostname, port)
    else:
        url = 'http://%s:%s/json' % (hostname, port)

    try:
        # fetch data
        log.debug('collect_data: fetching from url: %s, timeout: %d' % (url, timeout))
        r = requests.get(url=url, timeout=timeout)
        r.raise_for_status()
        log.debug('collect_data: %s returned %r' % (hostname, r))
        if r:
            # convert to json
            j = r.json()
            log.debug('collect_data: json returned from %s is: %r' % (hostname, j))
            time_of_reading = datetime_from_reading(j['DateTime'])
            # Check for sanity
            if not is_sane(j):
                log.info('purpleair reading not sane: %s' % j)
                return None
            # If proxy, the reading could be old.
            if proxy:
                #Check that it's not older than now - arcint
                age_of_reading = utc_now() - time_of_reading
                if age_of_reading.seconds > archive_interval:
                    # Nothing current, will have to read directly for PurpleAir device.
                    log.info('Ignoring proxy reading--age: %d seconds.'
                             % age_of_reading.seconds)
                    j = None
    except Exception as e:
        log.info('collect_data: Attempt to fetch from: %s failed: %s.' % (hostname, e))
        j = None


    if j is None:
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

    record['purple_temperature'] = get_and_update_missed('current_temp_f')
    record['purple_humidity'] = get_and_update_missed('current_humidity')
    record['purple_dewpoint'] = get_and_update_missed('current_dewpoint_f')

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

        self.cfg = Configuration(
            lock             = threading.Lock(),
            concentrations   = None,
            archive_interval = int(config_dict['StdArchive']['archive_interval']),
            archive_delay    = to_int(config_dict['StdArchive'].get('archive_delay', 15)),
            poll_interval    = 5,
            sources          = Purple.configure_sources(self.config_dict))
        with self.cfg.lock:
            self.cfg.concentrations = get_concentrations(self.cfg)

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
            weewx.xtypes.xtypes.append(AQI())

            # Start a thread to query proxies and make aqi available to loopdata
            dp: DevicePoller = DevicePoller(self.cfg)
            t: threading.Thread = threading.Thread(target=dp.poll_device)
            t.setName('Purple')
            t.setDaemon(True)
            t.start()

            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

    def new_loop_packet(self, event):
        log.debug('new_loop_packet(%s)' % event)
        with self.cfg.lock:
            log.debug('new_loop_packet: self.cfg.concentrations: %s' % self.cfg.concentrations)
            if self.cfg.concentrations is not None and \
                    self.cfg.concentrations.timestamp is not None and \
                    self.cfg.concentrations.timestamp + \
                    self.cfg.archive_interval >= time.time():
                # Insert pm1_0, pm2_5, pm10_0, aqi and aqic into loop packet.
                event.packet['pm1_0'] = self.cfg.concentrations.pm1_0
                event.packet['pm2_5'] = self.cfg.concentrations.pm2_5
                event.packet['pm10_0'] = self.cfg.concentrations.pm10_0
                event.packet['pm2_5_aqi'] = AQI.compute_pm2_5_aqi(event.packet['pm2_5'])
                event.packet['pm2_5_aqi_color'] = AQI.compute_pm2_5_aqi_color(event.packet['pm2_5_aqi'])
                log.debug('Time of reading being inserted: %s' % timestamp_to_string(self.cfg.concentrations.timestamp))
                log.debug('Inserted packet[pm1_0]: %f into packet.' % self.cfg.concentrations.pm1_0)
                log.debug('Inserted packet[pm2_5]: %f into packet.' % self.cfg.concentrations.pm2_5)
                log.debug('Inserted packet[pm10_0]: %f into packet.' % self.cfg.concentrations.pm10_0)
            else:
                log.error('Found no fresh concentrations to insert.')

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

    def get_proxy_version(hostname, port, timeout):
        try:
            url = 'http://%s:%s/get-version' % (hostname, port)
            log.debug('get-proxy-version: url: %s' % url)
            # If the machine was just rebooted, a temporary failure in name
            # resolution is likely.  As such, try three times.
            for i in range(3):
                try:
                    r = requests.get(url=url, timeout=timeout)
                    r.raise_for_status()
                    break
                except requests.exceptions.ConnectionError as e:
                    if i < 2:
                        log.info('%s: Retrying.' % e)
                        time.sleep(5)
                    else:
                        raise e
            log.debug('get-proxy-version: r: %s' % r)
            if r is None:
                log.debug('get-proxy-version: request returned None')
                return None
            j = r.json()
            log.debug('get_proxy_version: returning version %s for %s.' % (j['version'], hostname))
            return j['version']
        except Exception as e:
            log.info('Could not get version from proxy %s: %s.  Down?' % (hostname, e))
            return None

    def get_earliest_timestamp(hostname, port, timeout):
        try:
            url = 'http://%s:%s/get-earliest-timestamp' % (hostname, port)
            r = requests.get(url=url, timeout=timeout)
            r.raise_for_status()
            log.debug('get-earliest-timestamp: r: %s' % r)
            if r is None:
                log.debug('get-earliest-timestamp: request returned None')
                return None
            j = r.json()
            log.debug('get_earliest_timestamp: returning earliest timestamp %s for %s.' % (j['timestamp'], hostname))
            return j['timestamp']
        except Exception as e:
            log.debug('Could not get earliest timestamp from proxy %s: %s.  Down?' % (hostname, e))
            return None

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
            log.debug('poll_device: Sleeping for %d seconds.' % self.cfg.poll_interval)
            time.sleep(self.cfg.poll_interval)

class AQI(weewx.xtypes.XType):
    """
    AQI XType which computes the AQI (air quality index) from
    the pm2_5 value.
    """

    def __init__(self):
        pass

    agg_sql_dict = {
        'avg': "SELECT AVG(pm2_5), usUnits FROM %(table_name)s "
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL",
        'count': "SELECT COUNT(dateTime), usUnits FROM %(table_name)s "
                 "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL",
        'first': "SELECT pm2_5, usUnits FROM %(table_name)s "
                 "WHERE dateTime = (SELECT MIN(dateTime) FROM %(table_name)s "
                 "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL",
        'last': "SELECT pm2_5, usUnits FROM %(table_name)s "
                "WHERE dateTime = (SELECT MAX(dateTime) FROM %(table_name)s "
                "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL",
        'min': "SELECT pm2_5, usUnits FROM %(table_name)s "
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL "
               "ORDER BY pm2_5 ASC LIMIT 1;",
        'max': "SELECT pm2_5, usUnits FROM %(table_name)s "
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL "
               "ORDER BY pm2_5 DESC LIMIT 1;",
        'sum': "SELECT SUM(pm2_5), usUnits FROM %(table_name)s "
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND pm2_5 IS NOT NULL)",
    }

    @staticmethod
    def compute_pm2_5_aqi(pm2_5):
        #             U.S. EPA PM2.5 AQI
        #
        #  AQI Category  AQI Value  24-hr PM2.5
        # Good             0 -  50    0.0 -  12.0
        # Moderate        51 - 100   12.0 -  35.4
        # USG            101 - 150   35.4 -  55.4
        # Unhealthy      151 - 200   55.4 - 150.4
        # Very Unhealthy 201 - 300  150.4 - 250.4
        # Hazardous      301 - 400  250.4 - 350.4
        # Hazardous      401 - 500  350.4 - 500.0
        if pm2_5 <= 12.0: # Good
            return pm2_5 / 12.0 * 50
        elif pm2_5 <= 35.4: # Moderate
            return (pm2_5 - 12.0) / 23.4 * 49.0 + 51.0
        elif pm2_5 <= 55.4: # Unhealthy for senstive
            return (pm2_5 - 35.4) / 20.0 * 49.0 + 101.0
        elif pm2_5 <= 150.4: # Unhealthy
            return (pm2_5 - 55.4) / 95.0 * 49.0 + 151.0
        elif pm2_5 <= 250.4: # Very Unhealthy
            return (pm2_5 - 150.4) / 100.0 * 99.0 + 201.0
        elif pm2_5 <= 350.4: # Hazardous
            return (pm2_5 - 250.4) / 100.0 * 99.0 + 301.0
        else: # Hazardous
            return (pm2_5 - 350.4) / 149.6 * 99.0 + 401.0

    @staticmethod
    def compute_pm2_5_aqi_color(pm2_5_aqi):
        if pm2_5_aqi <= 50:
            return 128 << 8                 # Green
        elif pm2_5_aqi <= 100:
            return (255 << 16) + (255 << 8) # Yellow
        elif pm2_5_aqi <=  150:
            return (255 << 16) + (140 << 8) # Orange
        elif pm2_5_aqi <= 200: 
            return 255 << 16                # Red
        elif pm2_5_aqi <= 300:
            return (128 << 16) + 128        # Purple
        else:
            return 128 << 16                # Maroon

    @staticmethod
    def get_scalar(obs_type, record, db_manager=None):
        log.debug('get_scalar(%s)' % obs_type)
        if obs_type not in [ 'pm2_5_aqi', 'pm2_5_aqi_color' ]:
            raise weewx.UnknownType(obs_type)
        log.debug('get_scalar(%s)' % obs_type)
        if record is None or 'pm2_5' not in record:
            # Record of None has been observed.
            log.info('get_scalar called with where record argument is None.')
            raise weewx.CannotCalculate(obs_type)
        try:
            pm2_5 = record['pm2_5']
            value = AQI.compute_pm2_5_aqi(pm2_5)
            if obs_type == 'pm2_5_aqi_color':
                value = AQI.compute_pm2_5_aqi_color(value)
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
            sql_str = 'SELECT dateTime, usUnits, interval, pm2_5 FROM %s ' \
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

                value = AQI.compute_pm2_5_aqi(pm2_5)
                if obs_type == 'pm2_5_aqi_color':
                    value = AQI.compute_pm2_5_aqi_color(value)
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
        'sum', 'count', 'first', 'last', 'min', or 'max'. Anything else will cause
        weewx.UnknownAggregation to be raised.

        db_manager: An instance of weewx.manager.Manager or subclass.

        option_dict: Not used in this version.

        returns: A ValueTuple containing the result.
        """
        if obs_type not in ['pm2_5_aqi', 'pm2_5_aqi_color']:
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
            'table_name': db_manager.table_name
        }

        select_stmt = AQI.agg_sql_dict[aggregate_type] % interpolation_dict
        row = db_manager.getSql(select_stmt)
        if row:
            value, std_unit_system = row

        if value is not None:
            value = AQI.compute_pm2_5_aqi(value)
            if obs_type == 'pm2_5_aqi_color':
                value = AQI.compute_pm2_5_aqi_color(value)
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
            print(collect_data(hostname, port, 10, 300))
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
        assert(is_sane(j))
        j = json.loads(good_device)
        assert(is_sane(j))
        j = json.loads(bad_1)
        assert(not is_sane(j))
        j = json.loads(bad_2)
        assert(not is_sane(j))

    main()
