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

1. cp bin/user/purple.py to the /home/weewx/bin/user directory.


Service Configuration

Add the following to weewx.conf:

Add a comma and "user.purple.Purple" (don't include the quotes) to the end of the line that begins with "archive_services =".

[Purple]
    data_binding = purple_binding
    hostname = purple-air
    port = 80
    timeout = 15
    purple_proxy_hostname = myserver.foobar.com
    purple_porxy_port = 8000
    purple_proxy_timeout = 5

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
import time

from dateutil import tz
from dateutil.parser import parse

import weewx
import weeutil.weeutil
from weeutil.weeutil import timestamp_to_string
from weewx.engine import StdService
import weewx.units
from six.moves import range

log = logging.getLogger(__name__)

WEEWX_PURPLE_VERSION = "1.0"

if weewx.__version__ < "3":
    raise weewx.UnsupportedFeature("weewx 3 is required, found %s" %
                                   weewx.__version__)

# set up appropriate units
weewx.units.USUnits['group_concentration'] = 'microgram_per_meter_cubed'
weewx.units.MetricUnits['group_concentration'] = 'microgram_per_meter_cubed'
weewx.units.MetricWXUnits['group_concentration'] = 'microgram_per_meter_cubed'
weewx.units.default_unit_format_dict['microgram_per_meter_cubed'] = '%.3f'
weewx.units.default_unit_label_dict['microgram_per_meter_cubed']  = ' \xc2\xb5g/m\xc2\xb3'

weewx.units.USUnits['air_quality_index'] = 'aqi'
weewx.units.MetricUnits['air_quality_index'] = 'aqi'
weewx.units.MetricWXUnits['air_quality_index'] = 'aqi'
weewx.units.default_unit_format_dict['aqi'] = '%d'
weewx.units.default_unit_label_dict['aqi']  = ' AQI'

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

def datetime_from_reading(dt_str):
    dt_str = dt_str.replace('z', 'UTC')
    tzinfos = {'CST': tz.gettz("UTC")}
    return parse(dt_str, tzinfos=tzinfos)

def utc_now():
    tzinfos = {'CST': tz.gettz("UTC")}
    return datetime.datetime.now(tz=tz.gettz("UTC"))

def collect_data(hostname, port, timeout,
                 archive_interval, now_ts = None, purple_proxy_hostname = None,
                 purple_proxy_port = None, purple_proxy_timeout = None):

    if now_ts is None:
        now_ts = int(time.time() + 0.5)

    # This request could come late.  We need to make sure we're on the archive interval.
    now_ts = int(now_ts / archive_interval) * archive_interval # kill seconds

    j = None
    if purple_proxy_hostname is not None:
        try:
            # fetch data
            log.debug('collect_data: fetching data from: %s:%s timeout(%d)' % (
                purple_proxy_hostname, purple_proxy_port, purple_proxy_timeout))
            url = 'http://%s:%s/fetch-current-record' % (
                purple_proxy_hostname, purple_proxy_port)
            log.debug('collect_data: fetching from url: %s' % url)
            r = requests.get(url=url, timeout=purple_proxy_timeout)
            log.debug('collect_data: %s returned %r' % (
                purple_proxy_hostname, r))
            if r:
                # convert to json
                j = r.json()
                log.debug('collect_data: json returned from %s is: %r' % (purple_proxy_hostname, j))
                # The reading could be old.  Check that it's not older than now - arcint
                time_of_reading = datetime_from_reading(j['DateTime'])
                age_of_reading = utc_now() - time_of_reading
                if age_of_reading.seconds > archive_interval:
                    # Nothing current, will have to read directly for PurpleAir device.
                    log.info('Ignoring old purple-proxy reading--age: %d seconds.' % age_of_reading.seconds)
                    j = None
        except Exception as e:
            log.info('collect_data: Attempt to fetch from: %s failed: %s.' % (purple_proxy_hostname, e))
            j = None


    if j is None:
        if purple_proxy_hostname is not None:
            # Mention in the log that we're querying the PurpleAir device directly.
            log.info("Didn't get reading from %s (see reason above)."
                "  Will query sensor directly." % purple_proxy_hostname)
        # fetch data
        r = requests.get(url="http://%s:%s/json" % (hostname, port), timeout=timeout)
        if not r:
            return None
        # convert to json
        j = r.json()

    # create a record
    return populate_record(now_ts, j)

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
        log.info("sensor didn't report field(s): %s" % ','.join(missed))

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
        self.archive_interval = int(config_dict['StdArchive']['archive_interval'])
        self.archive_delay = weeutil.weeutil.to_int(config_dict['StdArchive'].get('archive_delay', 15))
        self.config_dict = config_dict.get('Purple', {})

        # get the database parameters we need to function
        self.data_binding = self.config_dict.get('data_binding', 'purple_binding')

        self.dbm_dict = weewx.manager.get_manager_dict(
            config_dict['DataBindings'],
            config_dict['Databases'],
            self.data_binding)
        try:
            self.config_dict['hostname']
        except KeyError as e:
            raise Exception("Data will not be posted: Missing option %s" % e)
        self.config_dict.setdefault('port', 80) # default port is HTTP
        self.config_dict.setdefault('timeout', 10) # url fetch timeout

        self.config_dict.setdefault('purple_proxy_hostname', None)
        self.config_dict.setdefault('purple_proxy_port', 8000)
        self.config_dict.setdefault('purple_proxy_timeout', 5)

        self.bind(weewx.STARTUP, self._catchup)
        self.bind(weewx.END_ARCHIVE_PERIOD, self.end_archive_period)

    def shutDown(self):
        pass

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
            log.info('New purple database.  Will add all records stored in purple-proxy service (if installed).')
            lastgood_ts = 0

        try:
            # Now ask for any new records since then.  Reject any records that
            # have a timestamp in the future, but provide some lenience for
            # clock drift.
            now = time.time()
            for record in self.genStartupRecords(lastgood_ts):
                ts = record.get('dateTime')
                if ts and ts < now + self.archive_delay:
                    log.debug('__init__: saving record(%s): %r.' % (timestamp_to_string(record['dateTime']), record))
                    self.save_data(record)
                else:
                    log.warning("ignore historical record: %s" % record)
        except Exception as e:
            log.error('**** Exception attempting to read archive records: %s' % e)
            weeutil.logger.log_traceback(log.critical, "    ****  ")

    def end_archive_period(self, _event):
        """ceate a new archive record and save it to the database"""
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
        record = collect_data(self.config_dict['hostname'],
                              weeutil.weeutil.to_int(self.config_dict['port']),
                              weeutil.weeutil.to_int(self.config_dict['timeout']),
                              self.archive_interval, now_ts,
                              self.config_dict['purple_proxy_hostname'],
                              weeutil.weeutil.to_int(self.config_dict['purple_proxy_port']),
                              weeutil.weeutil.to_int(self.config_dict['purple_proxy_timeout']))
        if record is None:
            return None
        record['interval'] = self.archive_interval / 60
        return record

    def genStartupRecords(self, since_ts):
        """Return archive records since_ts.
        """
        log.debug('genStartupRecords: since_ts=%r' % since_ts)
        log.info('Downloading new records (if any).')
        new_records = 0

        purple_proxy_hostname = self.config_dict['purple_proxy_hostname']
        purple_proxy_port = weeutil.weeutil.to_int(self.config_dict['purple_proxy_port'])
        purple_proxy_timeout = weeutil.weeutil.to_int(self.config_dict['purple_proxy_timeout'])

        j = None
        try:
            if purple_proxy_hostname is not None:
                url = 'http://%s:%s/fetch-archive-records?since_ts=%d' % (
                    purple_proxy_hostname, purple_proxy_port, since_ts)
                log.debug('genStartupRecords: url: %s' % url)
                r = requests.get(url=url, timeout=purple_proxy_timeout)
                log.debug('genStartupRecords: %s returned %r' % (url, r))
                if r:
                    # convert to json
                    j = r.json()
                    log.debug('genStartupRecords: ...the json is: %r' % j)
                    for reading in j:
                        # Get time_of_reading
                        time_of_reading = datetime_from_reading(reading['DateTime'])
                        log.debug('genStartupRecords: examining reading: %s (%s).' % (reading['DateTime'], time_of_reading))
                        reading_ts = calendar.timegm(time_of_reading.utctimetuple())
                        log.debug('genStartupRecords: reading_ts: %s.' % timestamp_to_string(reading_ts))
                        reading_ts = int(reading_ts / 60) * 60 # zero out the seconds
                        log.debug('genStartupRecords: rounded reading_ts: %s.' % timestamp_to_string(reading_ts))
                        if reading_ts > since_ts:
                            # create a record
                            pkt = populate_record(reading_ts, reading)
                            pkt['interval'] = self.archive_interval / 60
                            log.debug('genStartupRecords: pkt(%s): %r.' % (timestamp_to_string(pkt['dateTime']), pkt))
                            log.debug('packet: %s' % pkt)
                            log.debug('genStartupRecords: added record: %s' % time_of_reading)
                            new_records += 1
                            yield pkt
            log.info('Downloaded %d new records.' % new_records)
            return
        except Exception as e:
            log.info('gen_startup_records: Attempt to fetch from: %s failed.: %s' % (purple_proxy_hostname, e))
            weeutil.logger.log_traceback(log.critical, "    ****  ")
            j = None

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
                svc.new_archive_record(event)

                time.sleep(5)
    main()
