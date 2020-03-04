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

"""weewx module that records PurpleAir air quality sensor readings via the purple-proxy service.

Loosely modeled after Kenneth Baker's weewx-purpleair WeeWX plugin.

Installation instructions.

1. cd to the directory where this extension was cloned from github, for example:
   cd ~/software/weewx-purple

2. Run the following command.

   sudo /home/weewx/bin/wee_extension --install .

    Note: The above command assumes a WeeWX installation of `/home/weewx`.
          Adjust the command as necessary.

3. Edit the `Purple` section of weewx.conf (which was created by the install
   above.


   [Purple]
       data_binding = purple_binding
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
       [[Proxy2]]
           enable = false
           hostname = proxy2
           port = 8000
           timeout = 5
       [[Proxy3]]
           enable = false
           hostname = proxy3
           port = 8000
           timeout = 5
       [[Proxy4]]
           enable = false
           hostname = proxy4
           port = 8000
           timeout = 5

   [DataBindings]
       [[purple_binding]]
           manager = weewx.manager.DaySummaryManager
           schema = user.purple.schema
           table_name = archive
           database = purple_sqlite

   [Databases]
       [[purple_sqlite]]
           database_name = purple.sdb
           database_type = SQLite

"""

from __future__ import absolute_import
from __future__ import print_function
import calendar
import configobj
import datetime
import json
import logging
import os
import requests
import sys
import threading
import time

from dateutil import tz
from dateutil.parser import parse

from dataclasses import dataclass, field
from typing import Any, Dict, IO, Iterator, List, Optional, Tuple

import weewx
import weeutil.weeutil

from weeutil.weeutil import timestamp_to_string
from weeutil.weeutil import to_bool
from weeutil.weeutil import to_float
from weeutil.weeutil import to_int
from weewx.engine import StdService
import weewx.units
from six.moves import range

log = logging.getLogger(__name__)

WEEWX_PURPLE_VERSION = "1.0"

if sys.version_info[0] < 3:
    raise weewx.UnsupportedFeature(
        "weewx-purple requires Python 3, found %s" % sys.version_info[0])

if weewx.__version__ < "4":
    raise weewx.UnsupportedFeature(
        "WeeWX 4 is required, found %s" % weewx.__version__)

# Set up observation types not in weewx.units

weewx.units.USUnits['air_quality_index']       = 'aqi'
weewx.units.MetricUnits['air_quality_index']   = 'aqi'
weewx.units.MetricWXUnits['air_quality_index'] = 'aqi'

weewx.units.USUnits['air_quality_color']       = 'aqic'
weewx.units.MetricUnits['air_quality_color']   = 'aqic'
weewx.units.MetricWXUnits['air_quality_color'] = 'aqic'

weewx.units.default_unit_label_dict['aqi']  = ' AQI'
weewx.units.default_unit_label_dict['aqic'] = ' RGB'

weewx.units.default_unit_format_dict['aqi']  = '%d'
weewx.units.default_unit_format_dict['aqic'] = '%d'

# assign types of units to specific measurements
weewx.units.obs_group_dict['purple_temperature'] = 'group_temperature'
weewx.units.obs_group_dict['purple_humidity'] = 'group_percent'
weewx.units.obs_group_dict['purple_pressure'] = 'group_pressure'
weewx.units.obs_group_dict['pm1_0_cf_1'] = 'group_concentration'
weewx.units.obs_group_dict['pm1_0_cf_1_b'] = 'group_concentration'
weewx.units.obs_group_dict['pm1_0_cf_1_avg'] = 'group_concentration'
weewx.units.obs_group_dict['pm1_0_atm'] = 'group_concentration'
weewx.units.obs_group_dict['pm1_0_atm_b'] = 'group_concentration'
weewx.units.obs_group_dict['pm1_0_atm_avg'] = 'group_concentration'
weewx.units.obs_group_dict['pm2_5_cf_1'] = 'group_concentration'
weewx.units.obs_group_dict['pm2_5_cf_1_b'] = 'group_concentration'
weewx.units.obs_group_dict['pm2_5_cf_1_avg'] = 'group_concentration'
weewx.units.obs_group_dict['pm2_5_atm'] = 'group_concentration'
weewx.units.obs_group_dict['pm2_5_atm_b'] = 'group_concentration'
weewx.units.obs_group_dict['pm2_5_atm_avg'] = 'group_concentration'
weewx.units.obs_group_dict['pm10_0_cf_1'] = 'group_concentration'
weewx.units.obs_group_dict['pm10_0_cf_1_b'] = 'group_concentration'
weewx.units.obs_group_dict['pm10_0_cf_1_avg'] = 'group_concentration'
weewx.units.obs_group_dict['pm10_0_atm'] = 'group_concentration'
weewx.units.obs_group_dict['pm10_0_atm_b'] = 'group_concentration'
weewx.units.obs_group_dict['pm10_0_atm_avg'] = 'group_concentration'

weewx.units.obs_group_dict['pm2_5_aqi'] = 'air_quality_index'
weewx.units.obs_group_dict['pm2_5_aqi_b'] = 'air_quality_index'
weewx.units.obs_group_dict['pm2_5_aqi_avg'] = 'air_quality_index'

weewx.units.obs_group_dict['pm2_5_aqic'] = 'air_quality_color'
weewx.units.obs_group_dict['pm2_5_aqic_b'] = 'air_quality_color'
weewx.units.obs_group_dict['pm2_5_aqic_avg'] = 'air_quality_color'

# Schema for purple database (purple.sdb).  Note: this separate database
# may disappear in favor of adding fields to weewx.sdb.
schema = [
    ('dateTime', 'INTEGER NOT NULL PRIMARY KEY'),
    ('usUnits', 'INTEGER NOT NULL'),
    ('interval', 'INTEGER NOT NULL'),
    ('purple_temperature','REAL'),
    ('purple_humidity','REAL'),
    ('purple_dewpoint','REAL'),
    ('purple_pressure','REAL'),
    ('pm1_0_cf_1','REAL'),
    ('pm1_0_cf_1_b','REAL'),
    ('pm1_0_cf_1_avg','REAL'),
    ('pm1_0_atm','REAL'),
    ('pm1_0_atm_b','REAL'),
    ('pm1_0_atm_avg','REAL'),
    ('pm2_5_cf_1','REAL'),
    ('pm2_5_cf_1_b','REAL'),
    ('pm2_5_cf_1_avg','REAL'),
    ('pm2_5_atm','REAL'),
    ('pm2_5_atm_b','REAL'),
    ('pm2_5_atm_avg','REAL'),
    ('pm10_0_cf_1','REAL'),
    ('pm10_0_cf_1_b','REAL'),
    ('pm10_0_cf_1_avg','REAL'),
    ('pm10_0_atm','REAL'),
    ('pm10_0_atm_b','REAL'),
    ('pm10_0_atm_avg','REAL'),
    ('pm2_5_aqi', 'INTEGER'),
    ('pm2_5_aqi_b', 'INTEGER'),
    ('pm2_5_aqi_avg', 'INTEGER'),
    ('p25aqic', 'INTEGER'),
    ('p25aqic_b', 'INTEGER'),
    ('p25aqic_avg', 'INTEGER'),
    ]

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
class Rgb:
    red  : int
    green: int
    blue :  int

@dataclass
class Concentrations:
    timestamp: float
    pm1_0     : float
    pm2_5     : float
    pm10_0    : float
    pm2_5_aqi : int
    pm2_5_aqic: Rgb

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
    tzinfos = {'CST': tz.gettz("UTC")}
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
                    pm2_5_aqi  = to_int(record['pm2_5_aqi']),
                    pm2_5_aqic = int_to_rgb(record['p25aqic'])
                )
                # If there is a 'b' sensor, add it in and average the readings
                log.debug('get_concentrations: concentrations BEFORE averaing in b reading: %s' % concentrations)
                if 'pm1_0_cf_1_b' in record:
                    concentrations.pm1_0      = (concentrations.pm1_0  + to_float(record['pm1_0_cf_1_b'])) / 2.0
                    concentrations.pm2_5      = (concentrations.pm2_5  + to_float(record['pm2_5_cf_1_b'])) / 2.0
                    concentrations.pm10_0     = (concentrations.pm10_0 + to_float(record['pm10_0_cf_1_b'])) / 2.0
                    concentrations.pm2_5_aqi  = (concentrations.pm2_5_aqi    + to_float(record['pm2_5_aqi'])) / 2.0
                    concentrations.pm2_5_aqic = average_rgbs(concentrations.pm2_5_aqic, int_to_rgb(record['p25aqic_b']))
                log.debug('get_concentrations: concentrations: %s' % concentrations)
                return concentrations
    log.error('Could not get concentrations from any source.')
    return None

def rgb_to_int(rgb: Rgb) -> int:
    return (rgb.red << 16) + (rgb.green << 8) + rgb.blue

def int_to_rgb(i: int) -> Rgb:
    return Rgb(i >> 16, (i & 0x00FF00) >> 8, i & 0xFF)

def average_rgbs(rgb1: Rgb, rgb2: Rgb) -> Rgb:
    return Rgb(int((rgb1.red   + rgb2.red   + 0.5) / 2),
               int((rgb1.green + rgb2.green + 0.5) / 2),
               int((rgb1.blue  + rgb2.blue  + 0.5) / 2))

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
        log.debug('collect_data: %s returned %r' % (hostname, r))
        if r:
            # convert to json
            j = r.json()
            log.debug('collect_data: json returned from %s is: %r' % (
                hostname, j))
            time_of_reading = datetime_from_reading(j['DateTime'])
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
        record[key + '_b'] = j[key + '_b']
        record[key + '_avg'] = (j[key] + j[key + '_b']) / 2.0

    # grab AQI for A, B and the average of the A and B channels and push into the record
    record['pm2_5_aqi'] = j['pm2.5_aqi']
    record['pm2_5_aqi_b'] = j['pm2.5_aqi_b']
    record['pm2_5_aqi_avg'] = int((j['pm2.5_aqi'] + j['pm2.5_aqi_b']) / 2 + 0.5)

    # grap AQIC (rgb value representing AQI) for A, B and average
    rgb = rgb_convert_to_tuple(j['p25aqic'])
    rgb_b = rgb_convert_to_tuple(j['p25aqic_b'])
    rgb_avg = (
        int((rgb[0] + rgb_b[0]) / 2 + 0.5),
        int((rgb[1] + rgb_b[1]) / 2 + 0.5),
        int((rgb[2] + rgb_b[2]) / 2 + 0.5))
    record['p25aqic'] = convert_rgb_tuple_to_int(rgb)
    record['p25aqic_b'] = convert_rgb_tuple_to_int(rgb_b)
    record['p25aqic_avg'] = convert_rgb_tuple_to_int(rgb_avg)

    return record

def decode_rgb(rgb_string: str) -> Rgb:
    # rgb(61,234,0)
    rgb_string = rgb_string.replace('rgb(', '')
    # 61,234,0)
    rgb_string = rgb_string.replace(')', '')
    # 61,234,0
    rgbs = rgb_string.split(',')
    # [61, 234, 0]
    return Rgb(rgbs[0]), int(rgbs[1]), int(rgbs[2])

def rgb_convert_to_tuple(rgb_string):
    # rgb(61,234,0)
    rgb_string = rgb_string.replace('rgb(', '')
    # 61,234,0)
    rgb_string = rgb_string.replace(')', '')
    # 61,234,0
    rgbs = rgb_string.split(',')
    # [61, 234, 0]
    return int(rgbs[0]), int(rgbs[1]), int(rgbs[2])

def convert_rgb_tuple_to_int(rgb_tuple):
    return (rgb_tuple[0]<<16) + (rgb_tuple[1]<<8) + rgb_tuple[2]

class Purple(StdService):
    """Collect Purple Air air quality measurements."""

    def __init__(self, engine, config_dict):
        super(Purple, self).__init__(engine, config_dict)
        log.info("Service version is %s." % WEEWX_PURPLE_VERSION)

        self.engine = engine
        self.config_dict = config_dict.get('Purple', {})

        # get the database parameters we need to function
        self.data_binding = self.config_dict.get('data_binding', 'purple_binding')

        self.dbm_dict = weewx.manager.get_manager_dict(
            config_dict['DataBindings'],
            config_dict['Databases'],
            self.data_binding)

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
            # Start a thread to query proxies and make aqi available to loopdata
            dp: DevicePoller = DevicePoller(self.cfg)
            t: threading.Thread = threading.Thread(target=dp.poll_device)
            t.setName('Purple')
            t.setDaemon(True)
            t.start()

            self.bind(weewx.STARTUP, self._catchup)
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
            self.bind(weewx.END_ARCHIVE_PERIOD, self.end_archive_period)

    def new_archive_record(self, event):
        log.debug('new_archive_record: %s' % event)

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
                event.packet['pm2_5_aqi'] = self.cfg.concentrations.pm2_5_aqi
                event.packet['pm2_5_aqic'] = rgb_to_int(self.cfg.concentrations.pm2_5_aqic)
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

    def _catchup(self, _event):
        """Pull any unarchived records off the purple-proxy service and archive them.
        """

        dbmanager = self.engine.db_binder.get_manager(data_binding=self.data_binding, initialize=True)
        log.info("Using binding '%s' to database '%s'" % (self.data_binding, dbmanager.database_name))

        dbcol = dbmanager.connection.columnsOf(dbmanager.table_name)
        memcol = [x[0] for x in self.dbm_dict['schema']]
        if dbcol != memcol:
            raise Exception('purple schema mismatch: %s != %s' % (dbcol, memcol))

        # Make sure the daily summaries have not been partially updated
        if dbmanager._read_metadata('lastWeightPatch'):
            raise weewx.ViolatedPrecondition("Update of daily summary for database '%s' not complete. "
                                             "Finish the update first." % dbmanager.database_name)

        # Back fill the daily summaries.
        _nrecs, _ndays = dbmanager.backfill_day_summary()

        # Do a catch up on any data in the purple-proxy service archive, but not yet put in the database.

        # Find out when the database was last updated.
        lastgood_ts = dbmanager.lastGoodStamp()
        if lastgood_ts == None:
            log.info('New purple database.  Will add all records stored in purple-proxy service (if running).')
            lastgood_ts = 0

        try:
            # Now ask for any new records since then.  Reject any records that
            # have a timestamp in the future, but provide some lenience for
            # clock drift.
            for record in self.genStartupRecords(lastgood_ts):
                ts = record.get('dateTime')
                if ts and ts < time.time() + self.cfg.archive_delay:
                    log.debug('__init__: saving record(%s): %r.' % (timestamp_to_string(record['dateTime']), record))
                    self.save_data(record)
                else:
                    log.warning("ignore historical record: %s" % record)
        except Exception as e:
            log.error('**** Exception attempting to read archive records: %s' % e)
            weeutil.logger.log_traceback(log.critical, "    ****  ")

    def get_proxy_version(hostname, port, timeout):
        try:
            url = 'http://%s:%s/get-version' % (hostname, port)
            r = requests.get(url=url, timeout=timeout)
            r.raise_for_status()
            log.debug('get-proxy-version: r: %s' % r)
            if r is None:
                log.debug('get-proxy-version: request returned None')
                return Non
            j = r.json()
            log.debug('get_proxy_version: returning version %s for %s.' % (j['version'], hostname))
            return j['version']
        except Exception as e:
            log.debug('Could not get version from proxy %s: %s.  Down?' % (hostname, e))
            return None

    def get_earliest_timestamp(hostname, port, timeout):
        try:
            url = 'http://%s:%s/get-earliest-timestamp' % (hostname, port)
            r = requests.get(url=url, timeout=timeout)
            r.raise_for_status()
            log.debug('get-earliest-timestamp: r: %s' % r)
            if r is None:
                log.debug('get-earliest-timestamp: request returned None')
                return Non
            j = r.json()
            log.debug('get_earliest_timestamp: returning earliest timestamp %s for %s.' % (j['timestamp'], hostname))
            return j['timestamp']
        except Exception as e:
            log.debug('Could not get earliest timestamp from proxy %s: %s.  Down?' % (hostname, e))
            return None

    def genStartupRecords(self, since_ts):
        """Return arehive records since_ts.
        """
        log.debug('genStartupRecords: since_ts=%r' % since_ts)
        log.info('Downloading new records (if any).')
        new_records = 0

        hostname = None
        proxy = None
        timeout = None

        checkpoint_ts = since_ts
        for source in self.cfg.sources:
            if source.is_proxy:
                if source.enable:
                    version= Purple.get_proxy_version(source.hostname,
                        source.port, source.timeout)
                    if version is not None:
                        hostname = source.hostname
                        port     = source.port
                        timeout  = source.timeout
                        try:
                            fetch_count = None
                            while True:
                                # Fetch 300 at a time
                                # Stop when 0 records returned
                                if fetch_count is None:
                                    fetch_count = 0
                                elif fetch_count == 0:
                                    log.debug('Done fetching.  Last select fetched: %d records' % fetch_count)
                                    break
                                else:
                                    log.debug('Last select fetched: %d records' % fetch_count)
                                fetch_count = 0
                                url = 'http://%s:%s/fetch-archive-records?since_ts=%d,limit=300' % (
                                    hostname, port, checkpoint_ts)
                                log.debug('genStartupRecords: url: %s' % url)
                                r = requests.get(url=url, timeout=timeout)
                                r.raise_for_status()
                                log.debug('genStartupRecords: %s returned %r' % (url, r))
                                if r:
                                    # convert to json
                                    j = r.json()
                                    log.debug('genStartupRecords: ...the json is: %r' % j)
                                    for reading in j:
                                        fetch_count += 1
                                        log.debug('reading: %r' % reading)
                                        # Get time_of_reading
                                        time_of_reading = datetime_from_reading(reading['DateTime'])
                                        log.debug('genStartupRecords: examining reading: %s (%s).' % (reading['DateTime'], time_of_reading))
                                        reading_ts = calendar.timegm(time_of_reading.utctimetuple())
                                        log.debug('genStartupRecords: reading_ts: %s.' % timestamp_to_string(reading_ts))
                                        reading_ts = int(reading_ts / 60) * 60 # zero out the seconds
                                        log.debug('genStartupRecords: rounded reading_ts: %s.' % timestamp_to_string(reading_ts))
                                        if reading_ts > checkpoint_ts:
                                            checkpoint_ts = reading_ts
                                            # create a record
                                            pkt = populate_record(reading_ts, reading)
                                            pkt['interval'] = self.cfg.archive_interval / 60
                                            log.debug('genStartupRecords: pkt(%s): %r.' % (timestamp_to_string(pkt['dateTime']), pkt))
                                            log.debug('packet: %s' % pkt)
                                            log.debug('genStartupRecords: added record: %s' % time_of_reading)
                                            new_records += 1
                                            yield pkt
                            log.info('Downloaded %d new records.' % new_records)
                            return
                        except Exception as e:
                            log.info('gen_startup_records: Attempt to fetch from: %s failed.: %s' % (hostname, e))
                            weeutil.logger.log_traceback(log.error, "    ****  ")

        log.info('No proxy from which to fetch PurpleAir records.')
        return

    def end_archive_period(self, _event):
        """create a new archive record and save it to the database"""
        try:
            now = int(time.time() + 0.5)
            data = self.get_data(now)
            if data is None:
                log.error("get_data returned None.  No record to save.  %r" % now)
            if data is not None:
                self.save_data(data)
        except Exception as e:
            # Include a stack traceback in the log:
            # but eat this exception as we don't want to bring down weewx
            # because the PurpleAir sensor is unavailable.
            weeutil.logger.log_traceback(log.critical, "    ****  ")

    def save_data(self, record):
        """save data to database"""
        dbmanager = self.engine.db_binder.get_manager(self.data_binding)
        dbmanager.addRecord(record)

    def get_data(self, now_ts):
        for source in self.cfg.sources:
            if source.enable:
                record = collect_data(source.hostname,
                                      source.port,
                                      source.timeout,
                                      self.cfg.archive_interval,
                                      source.is_proxy)
                if record is not None:
                    break

        if record is None:
            return None

        # Align timestamp to archive interval
        now_ts = int(time.time() + 0.5)
        record['dateTime'] = int(now_ts / self.cfg.archive_interval) * self.cfg.archive_interval

        # Archive interval is expressed in minutes in the archive record.
        record['interval'] = self.cfg.archive_interval / 60
        return record

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

if __name__ == "__main__":
    usage = """%prog [options] [--help] [--debug]"""

    import weeutil.logger

    def main():
        import optparse
        import weecfg
        parser = optparse.OptionParser(usage=usage)
        parser.add_option('--config', dest='cfgfn', type=str, metavar="FILE",
                          help="Use configuration file FILE. Default is /etc/weewx/weewx.conf or /home/weewx/weewx.conf")
        parser.add_option('--binding', dest="binding", metavar="BINDING",
                          default='purple_binding',
                          help="The data binding to use. Default is 'purple_binding'.")
        parser.add_option('--test-collector', dest='tc', action='store_true',
                          help='test the data collector')
        parser.add_option('--hostname', dest='hostname', action='store',
                          help='hostname to use with --test-collector')
        parser.add_option('--port', dest='port', action='store',
                          type=int, default=80,
                          help="port to use with --test-collector. Default is '80'")
        parser.add_option('--test-service', dest='ts', action='store_true',
                          help='test the service')
        (options, args) = parser.parse_args()

        weeutil.logger.setup('purple', {})

        if options.tc:
            if not options.hostname:
                parser.error('--test-collector requires --hostname argument')
            test_collector(options.hostname, options.port)
        elif options.ts:
            if not options.hostname:
                parser.error('--test-service requires --hostname argument')
            test_service(options.hostname, options.port)

    def test_collector(hostname, port):
        while True:
            print(collect_data(hostname, port, 10, 300))
            time.sleep(5)

    def test_service(hostname, port):
        from weewx.engine import StdEngine
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile() as temp_file:
            config = configobj.ConfigObj({
                'Station': {
                    'station_type': 'Simulator',
                    'altitude': [0, 'foot'],
                    'latitude': 0,
                    'longitude': 0},
                'Simulator': {
                    'driver': 'weewx.drivers.simulator',
                    'mode': 'simulator'},
                'Purple': {
                    'binding': 'purple_binding',
                    'hostname': hostname,
                    'port': port},
                'DataBindings': {
                    'purple_binding': {
                        'database': 'purple_sqlite',
                        'manager': 'weewx.manager.DaySummaryManager',
                        'table_name': 'archive',
                        'schema': 'user.purple.schema'}},
                'Databases': {
                    'purple_sqlite': {
                        'root': '%(WEEWX_ROOT)s',
                        'database_name': temp_file.name,
                        'driver': 'weedb.sqlite'}},
                'Engine': {
                    'Services': {
                        'archive_services': 'user.purple.Purple'}}})
            engine = StdEngine(config)
            svc = Purple(engine, config)
            for _ in range(4):
                record = {
                    'dateTime': int(time.time() + 0.5),
                    'interval': 1
                }
                event = weewx.Event(weewx.END_ARCHIVE_PERIOD, record=record)
                svc.end_archive_record(event)

                time.sleep(5)
    main()
