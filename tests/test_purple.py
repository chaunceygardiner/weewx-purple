#
#    See the file LICENSE.txt for your full rights.
#
"""Hermetic tests for weewx-purple.  No network access: everything from the
fetch stack down is exercised with mocks, and the xtype SQL paths run
against an in-memory SQLite database."""

import datetime
import logging
import sqlite3
import threading
import time
import types
import unittest

from typing import Any, Dict
from unittest import mock

import weeutil.logger
import weeutil.weeutil
import weewx
import weewx.units
import weewx.xtypes

import user.purple

from user.purple import AQI, Concentrations, Configuration, Purple, Source

log = logging.getLogger(__name__)

# Set up logging using the defaults.
weeutil.logger.setup('test_config', {})

# A class whose *name* matches weewxd's shutdown exception.  weewxd raises
# Terminate from its SIGTERM handler; purple.py recognizes it by name.
Terminate = type('Terminate', (Exception,), {})

VALID_PKT: Dict[str, Any] = {
    "SensorId":"44:17:93:1:9d:3",
    "DateTime":"2023/10/26T18:53:40z",
    "Geo":"PurpleAir-9d3",
    "Mem":20256,
    "memfrag":15,
    "memfb":17240,
    "memcs":800,
    "Id":57139,
    "lat":37.431599,
    "lon":-122.111000,
    "Adc":0.05,
    "loggingrate":15,
    "place":"outside",
    "version":"7.02",
    "uptime":683681,
    "rssi":-53,
    "period":120,
    "httpsuccess":11582,
    "httpsends":11582,
    "hardwareversion":"2.0",
    "hardwarediscovered":"2.0+BME280+PMSX003-B+PMSX003-A",
    "current_temp_f":69,
    "current_humidity":35,
    "current_dewpoint_f":40,
    "pressure":1022.92,
    "p25aqic_b":"rgb(19,230,0)",
    "pm2.5_aqi_b":21,
    "pm1_0_cf_1_b":3.00,
    "p_0_3_um_b":771.00,
    "pm2_5_cf_1_b":5.00,
    "p_0_5_um_b":218.00,
    "pm10_0_cf_1_b":6.00,
    "p_1_0_um_b":27.00,
    "pm1_0_atm_b":3.00,
    "p_2_5_um_b":4.00,
    "pm2_5_atm_b":5.00,
    "p_5_0_um_b":2.00,
    "pm10_0_atm_b":6.00,
    "p_10_0_um_b":1.00,
    "p25aqic":"rgb(19,230,0)",
    "pm2.5_aqi":21,
    "pm1_0_cf_1":3.00,
    "p_0_3_um":639.00,
    "pm2_5_cf_1":5.00,
    "p_0_5_um":194.00,
    "pm10_0_cf_1":5.00,
    "p_1_0_um":40.00,
    "pm1_0_atm":3.00,
    "p_2_5_um":1.00,
    "pm2_5_atm":5.00,
    "p_5_0_um":0.00,
    "pm10_0_atm":5.00,
    "p_10_0_um":0.00,
    "pa_latency":221,
    "response":201,
    "response_date":1698346362,
    "latency":286,
    "wlstate":"Connected",
    "status_0":2,
    "status_1":2,
    "status_2":2,
    "status_3":2,
    "status_4":0,
    "status_5":0,
    "status_6":2,
    "status_7":0,
    "status_8":0,
    "status_9":0,
    "ssid":"ellagirldog"}

def a_only_pkt() -> Dict[str, Any]:
    """A copy of VALID_PKT as an indoor (single-sensor) device would report
    it: no b-channel fields."""
    return {k: v for k, v in VALID_PKT.items()
            if not k.endswith('_b') and k != 'pm2.5_aqi_b' and k != 'p25aqic_b'}

class FakeResponse:
    """Just enough of requests.Response for collect_data."""
    def __init__(self, j, status_error=None):
        self._j = j
        self._status_error = status_error
    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error
    def json(self):
        return self._j

class FakeDBManager:
    """Just enough of weewx.manager.Manager for the AQI xtype: a table name
    plus getSql/genSql running against a real SQLite connection."""
    def __init__(self, conn, table_name='archive'):
        self.conn = conn
        self.table_name = table_name
    def getSql(self, sql, sqlargs=()):
        return self.conn.execute(sql, sqlargs).fetchone()
    def genSql(self, sql, sqlargs=()):
        yield from self.conn.execute(sql, sqlargs)

def make_cfg(sources=None, poll_secs=15, fresh_secs=120, concentrations=None):
    return Configuration(
        lock           = threading.Lock(),
        concentrations = concentrations,
        poll_secs      = poll_secs,
        fresh_secs     = fresh_secs,
        sources        = sources if sources is not None else [])

def make_source(name='Sensor1', is_proxy=False, enable=True, hostname='host', **kwargs):
    d = {'enable': enable, 'hostname': hostname}
    d.update(kwargs)
    return Source({name: d}, name, is_proxy)

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
# Above 325.4, AQI values continue past 500 on the same (Hazardous) slope;
# there is no upper cap.

class TestComputeAqi(unittest.TestCase):

    def test_good(self):
        self.assertEqual(AQI.compute_pm2_5_aqi(0.0), 0)
        self.assertEqual(AQI.compute_pm2_5_aqi(6.0), 33)
        self.assertEqual(AQI.compute_pm2_5_aqi(9.0), 50)
        # 9.099 is truncated to 9.0
        self.assertEqual(AQI.compute_pm2_5_aqi(9.099), 50)

    def test_moderate(self):
        self.assertEqual(AQI.compute_pm2_5_aqi(9.1), 51)
        self.assertEqual(AQI.compute_pm2_5_aqi(21.8), 75)
        self.assertEqual(AQI.compute_pm2_5_aqi(35.4), 100)
        self.assertEqual(AQI.compute_pm2_5_aqi(35.499), 100)

    def test_usg(self):
        self.assertEqual(AQI.compute_pm2_5_aqi(35.5), 101)
        self.assertEqual(AQI.compute_pm2_5_aqi(45.4), 125)
        self.assertEqual(AQI.compute_pm2_5_aqi(55.4), 150)

    def test_unhealthy(self):
        self.assertEqual(AQI.compute_pm2_5_aqi(55.5), 151)
        self.assertEqual(AQI.compute_pm2_5_aqi(90.5), 176)
        self.assertEqual(AQI.compute_pm2_5_aqi(125.4), 200)

    def test_very_unhealthy(self):
        self.assertEqual(AQI.compute_pm2_5_aqi(125.5), 201)
        self.assertEqual(AQI.compute_pm2_5_aqi(175.4), 250)
        self.assertEqual(AQI.compute_pm2_5_aqi(225.4), 300)

    def test_hazardous(self):
        # Per the May 2024 AirNow TAD (breakpoint-table footnote 4), the
        # concentration for AQI 500 is 325.4: slope 199 AQI per 99.9 ug/m^3.
        self.assertEqual(AQI.compute_pm2_5_aqi(225.5), 301)
        self.assertEqual(AQI.compute_pm2_5_aqi(275.4), 400)
        self.assertEqual(AQI.compute_pm2_5_aqi(325.4), 500)

    def test_above_500_extrapolates_hazardous_slope(self):
        # The TAD FAQ: values above 500 are "based on the same linear slope
        # as the AQI values between 301 and 500".  No upper cap.
        self.assertEqual(AQI.compute_pm2_5_aqi(375.0), 599)
        self.assertEqual(AQI.compute_pm2_5_aqi(425.0), 698)
        self.assertEqual(AQI.compute_pm2_5_aqi(1000.0), 1844)

    def test_negative_concentration_maps_to_zero(self):
        # A (bogus) negative concentration must not map below 0.
        self.assertEqual(AQI.compute_pm2_5_aqi(-5.0), 0)

class TestComputeAqiColor(unittest.TestCase):

    GREEN  = 228 << 8
    YELLOW = (255 << 16) + (255 << 8)
    ORANGE = (255 << 16) + (126 << 8)
    RED    = 255 << 16
    PURPLE = (143 << 16) + (63 << 8) + 151
    MAROON = (126 << 16) + 35

    def test_category_boundaries(self):
        for aqi, expected in [
                (  0, self.GREEN),  ( 25, self.GREEN),  ( 50, self.GREEN),
                ( 51, self.YELLOW), ( 75, self.YELLOW), (100, self.YELLOW),
                (101, self.ORANGE), (125, self.ORANGE), (150, self.ORANGE),
                (151, self.RED),    (175, self.RED),    (200, self.RED),
                (201, self.PURPLE), (250, self.PURPLE), (300, self.PURPLE),
                (301, self.MAROON), (400, self.MAROON), (500, self.MAROON),
                # Above 500 is still Hazardous/Maroon.
                (501, self.MAROON), (750, self.MAROON)]:
            self.assertEqual(AQI.compute_pm2_5_aqi_color(aqi), expected,
                             'wrong color for AQI %d' % aqi)

class TestEpaCorrection(unittest.TestCase):
    # 2021 EPA Correction
    # Low Concentration PAcf_1 <= 343 ug/m^3 : PM2.5 = 0.52 x PAcf_1 - 0.086 x RH + 5.75
    # High Concentration PAcf_1 > 343 ug/m^3 : PM2.5 = 0.46 x PAcf_1 + 3.93 x 10**-4 x PAcf_1**2 + 2.97

    def test_zero_concentration(self):
        self.assertEqual(AQI.compute_pm2_5_us_epa_correction(0.0, 0.0, 0, 96), 5.75)
        self.assertAlmostEqual(AQI.compute_pm2_5_us_epa_correction(0.0, 0.0, 21, 96), 3.944)

    def test_low_concentration(self):
        self.assertAlmostEqual(AQI.compute_pm2_5_us_epa_correction(118.0, 98.0, 95, 20), 53.74)

    def test_high_concentration(self):
        self.assertAlmostEqual(AQI.compute_pm2_5_us_epa_correction(395.0, 405.0, 95, 20), 249.85)

    def test_channels_are_averaged(self):
        self.assertAlmostEqual(
            AQI.compute_pm2_5_us_epa_correction(10.0, 20.0, 40, 70),
            AQI.compute_pm2_5_us_epa_correction(15.0, 15.0, 40, 70))

    def test_boundary_at_343(self):
        # Exactly 343 belongs to the low-concentration branch.
        self.assertAlmostEqual(
            AQI.compute_pm2_5_us_epa_correction(343.0, 343.0, 40, 70),
            0.52 * 343.0 - 0.086 * 40 + 5.75)
        # Just above 343 uses the high-concentration branch.
        self.assertAlmostEqual(
            AQI.compute_pm2_5_us_epa_correction(343.2, 343.2, 40, 70),
            0.46 * 343.2 + 3.93 * 10**-4 * 343.2**2 + 2.97)

    def test_never_negative(self):
        # High humidity at zero concentration would come out negative.
        self.assertEqual(AQI.compute_pm2_5_us_epa_correction(0.0, 0.0, 90, 70), 0.0)

class TestCheckType(unittest.TestCase):

    def test_matching_types(self):
        ok, _ = user.purple.check_type({'a': 1, 'b': 2}, int, ['a', 'b'])
        self.assertTrue(ok)
        ok, _ = user.purple.check_type({'a': 1.5}, float, ['a'])
        self.assertTrue(ok)

    def test_int_acceptable_where_float_expected(self):
        # JSON parses "5" as int; a whole-number concentration is still sane.
        ok, _ = user.purple.check_type({'a': 5}, float, ['a'])
        self.assertTrue(ok)

    def test_bool_never_acceptable(self):
        ok, reason = user.purple.check_type({'a': True}, int, ['a'])
        self.assertFalse(ok, reason)

    def test_wrong_type(self):
        ok, reason = user.purple.check_type({'a': 'nan'}, int, ['a'])
        self.assertFalse(ok)
        self.assertEqual(reason, "a is not an instance of <class 'int'>: nan")
        ok, _ = user.purple.check_type({'a': 1.5}, int, ['a'])
        self.assertFalse(ok)

    def test_missing_key(self):
        ok, reason = user.purple.check_type({'a': 1}, int, ['a', 'zz'])
        self.assertFalse(ok)
        self.assertIn('could not find key', reason)

class TestTwentyFoldDelta(unittest.TestCase):

    def test_zero_skips_check(self):
        self.assertFalse(user.purple.exhibits_twenty_fold_delta(0.0, 100.0))
        self.assertFalse(user.purple.exhibits_twenty_fold_delta(100.0, 0.0))

    def test_agreeing_sensors(self):
        self.assertFalse(user.purple.exhibits_twenty_fold_delta(5.0, 6.0))
        self.assertFalse(user.purple.exhibits_twenty_fold_delta(50.0, 900.0))

    def test_disagreeing_sensors_both_directions(self):
        self.assertTrue(user.purple.exhibits_twenty_fold_delta(1.0, 25.0))
        self.assertTrue(user.purple.exhibits_twenty_fold_delta(25.0, 1.0))

    def test_too_low_to_matter(self):
        # 20-fold apart, but absolute delta < 10.
        self.assertFalse(user.purple.exhibits_twenty_fold_delta(0.4, 9.0))

class TestIsSane(unittest.TestCase):

    def test_valid_outdoor_packet(self):
        ok, reason = user.purple.is_sane(VALID_PKT)
        self.assertTrue(ok, reason)

    def test_valid_indoor_packet(self):
        # Single sensor: no b-channel fields at all.
        ok, reason = user.purple.is_sane(a_only_pkt())
        self.assertTrue(ok, reason)

    def test_missing_datetime(self):
        bad_pkt = VALID_PKT.copy()
        del bad_pkt['DateTime']
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertIn('DateTime not found', reason)

    def test_bad_datetime(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['DateTime'] = 'xyz'
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertEqual(reason, 'DateTime is not an instance of datetime: xyz')

    def test_non_string_datetime(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['DateTime'] = 1698346420
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertIn('not a string', reason)

    def test_bad_pressure(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pressure'] = 'nan'
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertIn('pressure', reason)

    def test_bad_b_channel_concentration(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2_5_atm_b'] = 'nan'
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertIn('pm2_5_atm_b', reason)

    def test_bad_b_channel_aqi(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2.5_aqi_b'] = 21.5
        ok, _ = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)

    def test_bad_temp(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['current_temp_f'] = 'nan'
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertEqual(reason, "current_temp_f is not an instance of <class 'int'>: nan")

    def test_nan_concentration(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2_5_cf_1'] = 'nan'
        ok, _ = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)

    def test_whole_number_concentration_is_sane(self):
        # JSON parses a whole number as int; that must not fail the check.
        pkt = VALID_PKT.copy()
        pkt['pm2_5_cf_1'] = 5
        ok, reason = user.purple.is_sane(pkt)
        self.assertTrue(ok, reason)

    def test_non_integer_aqi(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2.5_aqi'] = 21.5
        ok, _ = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)

    def test_disagreeing_sensors(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2_5_cf_1'] = 1.0
        bad_pkt['pm2_5_cf_1_b'] = 25.0
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok, reason)
        self.assertEqual(reason, 'Sensors disagree wildly for pm2_5_cf_1 (1.000000, 25.000000)')

    def test_disagreeing_sensors_pm1_0(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm1_0_cf_1'] = 1.0
        bad_pkt['pm1_0_cf_1_b'] = 30.0
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertIn('pm1_0_cf_1', reason)

    def test_disagreeing_sensors_pm10_0(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm10_0_cf_1'] = 1.0
        bad_pkt['pm10_0_cf_1_b'] = 40.0
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertIn('pm10_0_cf_1', reason)

    def test_disagreement_too_low_to_matter(self):
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2_5_cf_1'] = 0.000001
        ok, _ = user.purple.is_sane(bad_pkt)
        self.assertTrue(ok)

class TestDatetimeFromReading(unittest.TestCase):

    def test_utc_z_suffix(self):
        dt = user.purple.datetime_from_reading('2023/10/26T18:53:40z')
        self.assertEqual(
            dt.timestamp(),
            datetime.datetime(2023, 10, 26, 18, 53, 40,
                              tzinfo=datetime.timezone.utc).timestamp())

class TestPopulateRecord(unittest.TestCase):

    TS = 1698346420.0

    def test_basic_fields(self):
        record = user.purple.populate_record(self.TS, VALID_PKT.copy())
        self.assertEqual(record['dateTime'], self.TS)
        self.assertEqual(record['usUnits'], weewx.US)
        self.assertEqual(record['current_temp_f'], 69)
        self.assertEqual(record['current_humidity'], 35)
        self.assertEqual(record['current_dewpoint_f'], 40)
        self.assertEqual(record['pm2_5_cf_1'], 5.00)
        self.assertEqual(record['pm2_5_cf_1_b'], 5.00)

    def test_pressure_converted_to_us_units(self):
        record = user.purple.populate_record(self.TS, VALID_PKT.copy())
        expected = weewx.units.convertStd((1022.92, 'mbar', 'group_pressure'), weewx.US)[0]
        self.assertAlmostEqual(record['purple_pressure'], expected)

    def test_missing_pressure_tolerated(self):
        pkt = VALID_PKT.copy()
        del pkt['pressure']
        record = user.purple.populate_record(self.TS, pkt)
        self.assertNotIn('purple_pressure', record)

    def test_a_and_b_averaged(self):
        pkt = VALID_PKT.copy()
        pkt['pm2_5_cf_1'] = 4.0
        pkt['pm2_5_cf_1_b'] = 6.0
        record = user.purple.populate_record(self.TS, pkt)
        self.assertEqual(record['pm2_5_cf_1_avg'], 5.0)

    def test_a_only_no_averages(self):
        record = user.purple.populate_record(self.TS, a_only_pkt())
        self.assertNotIn('pm2_5_cf_1_avg', record)
        self.assertNotIn('pm2_5_cf_1_b', record)

class TestCollectData(unittest.TestCase):

    def test_successful_fetch(self):
        with mock.patch('user.purple.requests.get',
                        return_value=FakeResponse(VALID_PKT.copy())) as m:
            record = user.purple.collect_data('sensor.example', 80, 10)
        m.assert_called_once()
        self.assertIsNotNone(record)
        expected_ts = user.purple.datetime_from_reading(VALID_PKT['DateTime']).timestamp()
        self.assertEqual(record['dateTime'], expected_ts)
        self.assertEqual(record['pm2_5_cf_1'], 5.00)

    def test_insane_reading_returns_none(self):
        pkt = VALID_PKT.copy()
        pkt['pm2_5_cf_1'] = 'nan'
        with mock.patch('user.purple.requests.get', return_value=FakeResponse(pkt)):
            self.assertIsNone(user.purple.collect_data('sensor.example', 80, 10))

    def test_connection_error_returns_none(self):
        import requests
        with mock.patch('user.purple.requests.get',
                        side_effect=requests.exceptions.ConnectionError('no route')):
            self.assertIsNone(user.purple.collect_data('sensor.example', 80, 10))

    def test_http_error_returns_none(self):
        import requests
        resp = FakeResponse(None, status_error=requests.exceptions.HTTPError('500'))
        with mock.patch('user.purple.requests.get', return_value=resp):
            self.assertIsNone(user.purple.collect_data('sensor.example', 80, 10))

class TestTerminatePassThrough(unittest.TestCase):
    """weewxd stops by raising Terminate from its SIGTERM handler inside
    whatever the main thread is executing.  The broad exception handlers on
    main-thread paths must hand it back."""

    def test_reraise_if_terminate(self):
        with self.assertRaises(Terminate):
            user.purple.reraise_if_terminate(Terminate())
        # Any other exception is not re-raised.
        self.assertIsNone(user.purple.reraise_if_terminate(ValueError()))

    def test_collect_data_passes_terminate_through(self):
        with mock.patch('user.purple.requests.get', side_effect=Terminate()):
            with self.assertRaises(Terminate):
                user.purple.collect_data('sensor.example', 80, 10)

    def test_collect_data_swallows_other_exceptions(self):
        with mock.patch('user.purple.requests.get', side_effect=RuntimeError('boom')):
            self.assertIsNone(user.purple.collect_data('sensor.example', 80, 10))

    def test_check_type_passes_terminate_through(self):
        class Exploder:
            def __getitem__(self, key):
                raise Terminate()
        with self.assertRaises(Terminate):
            user.purple.check_type(Exploder(), int, ['x'])

    def test_check_type_swallows_other_exceptions(self):
        class Exploder:
            def __getitem__(self, key):
                raise RuntimeError('boom')
        ok, reason = user.purple.check_type(Exploder(), int, ['x'])
        self.assertFalse(ok)
        self.assertIn('exception', reason)

class TestConfigureSources(unittest.TestCase):

    def test_proxies_then_sensors_in_order(self):
        config = {
            'Sensor1': {'enable': True,  'hostname': 's1'},
            'Sensor2': {'enable': False, 'hostname': 's2'},
            'Proxy1':  {'enable': True,  'hostname': 'p1'},
        }
        sources = Purple.configure_sources(config)
        self.assertEqual([s.hostname for s in sources], ['p1', 's1', 's2'])
        self.assertTrue(sources[0].is_proxy)
        self.assertFalse(sources[1].is_proxy)

    def test_numbering_must_be_consecutive(self):
        config = {
            'Sensor1': {'enable': True, 'hostname': 's1'},
            'Sensor3': {'enable': True, 'hostname': 's3'},
        }
        sources = Purple.configure_sources(config)
        self.assertEqual([s.hostname for s in sources], ['s1'])

    def test_defaults(self):
        sensor = make_source('Sensor1', is_proxy=False)
        self.assertEqual(sensor.port, 80)
        self.assertEqual(sensor.timeout, 10)
        proxy = make_source('Proxy1', is_proxy=True)
        self.assertEqual(proxy.port, 8000)
        # enable defaults to False, and parses strings.
        s = Source({'Sensor1': {'hostname': 'h'}}, 'Sensor1', False)
        self.assertFalse(s.enable)
        s = Source({'Sensor1': {'hostname': 'h', 'enable': 'true'}}, 'Sensor1', False)
        self.assertTrue(s.enable)

class TestGetConcentrations(unittest.TestCase):

    @staticmethod
    def fresh_record(**overrides):
        record = {
            'dateTime': time.time() - 10,
            'pm1_0_atm': 2.0,
            'pm10_0_atm': 4.0,
            'pm2_5_cf_1': 3.0,
            'current_temp_f': 70,
            'current_humidity': 40,
        }
        record.update(overrides)
        return record

    def test_single_sensor(self):
        cfg = make_cfg(sources=[make_source()])
        record = self.fresh_record()
        with mock.patch('user.purple.collect_data', return_value=record):
            c = user.purple.get_concentrations(cfg)
        self.assertIsNotNone(c)
        self.assertEqual(c.timestamp, int(record['dateTime']))
        self.assertEqual(c.pm1_0, 2.0)
        self.assertEqual(c.pm10_0, 4.0)
        self.assertEqual(c.pm2_5_cf_1, 3.0)
        self.assertIsNone(c.pm2_5_cf_1_b)

    def test_b_channel_averaged(self):
        cfg = make_cfg(sources=[make_source()])
        record = self.fresh_record(pm1_0_atm_b=4.0, pm10_0_atm_b=6.0, pm2_5_cf_1_b=5.0)
        with mock.patch('user.purple.collect_data', return_value=record):
            c = user.purple.get_concentrations(cfg)
        self.assertEqual(c.pm1_0, 3.0)     # (2 + 4) / 2
        self.assertEqual(c.pm10_0, 5.0)    # (4 + 6) / 2
        self.assertEqual(c.pm2_5_cf_1, 3.0)    # cf_1 channels are NOT averaged here;
        self.assertEqual(c.pm2_5_cf_1_b, 5.0)  # the EPA correction averages them.

    def test_disabled_source_skipped(self):
        s1 = make_source('Sensor1', enable=False, hostname='s1')
        s2 = make_source('Sensor2', hostname='s2')
        cfg = make_cfg(sources=[s1, s2])
        with mock.patch('user.purple.collect_data',
                        return_value=self.fresh_record()) as m:
            c = user.purple.get_concentrations(cfg)
        self.assertIsNotNone(c)
        m.assert_called_once()
        self.assertEqual(m.call_args[0][0], 's2')

    def test_failing_source_falls_through_to_next(self):
        s1 = make_source('Sensor1', hostname='s1')
        s2 = make_source('Sensor2', hostname='s2')
        cfg = make_cfg(sources=[s1, s2])
        with mock.patch('user.purple.collect_data',
                        side_effect=[None, self.fresh_record()]) as m:
            c = user.purple.get_concentrations(cfg)
        self.assertIsNotNone(c)
        self.assertEqual(m.call_count, 2)

    def test_stale_reading_ignored(self):
        # With fresh_secs 120 and poll_secs 15, the cutoff is 100s.
        cfg = make_cfg(sources=[make_source()])
        record = self.fresh_record(dateTime=time.time() - 101)
        with mock.patch('user.purple.collect_data', return_value=record):
            self.assertIsNone(user.purple.get_concentrations(cfg))

    def test_reading_within_cutoff_accepted(self):
        cfg = make_cfg(sources=[make_source()])
        record = self.fresh_record(dateTime=time.time() - 99)
        with mock.patch('user.purple.collect_data', return_value=record):
            self.assertIsNotNone(user.purple.get_concentrations(cfg))

    def test_no_sources_respond(self):
        cfg = make_cfg(sources=[make_source()])
        with mock.patch('user.purple.collect_data', return_value=None):
            self.assertIsNone(user.purple.get_concentrations(cfg))

class TestNewLoopPacket(unittest.TestCase):

    @staticmethod
    def make_purple(concentrations):
        # Build a Purple without running __init__ (which needs an engine
        # and does a synchronous fetch).
        p = Purple.__new__(Purple)
        p.cfg = make_cfg(concentrations=concentrations)
        p.stale_logged = False
        return p

    @staticmethod
    def fresh_concentrations(**overrides):
        kwargs = dict(
            timestamp        = time.time(),
            pm1_0            = 3.0,
            pm10_0           = 5.0,
            pm2_5_cf_1       = 10.0,
            pm2_5_cf_1_b     = 12.0,
            current_temp_f   = 70,
            current_humidity = 40)
        kwargs.update(overrides)
        return Concentrations(**kwargs)

    def test_fields_inserted(self):
        p = self.make_purple(self.fresh_concentrations())
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertEqual(event.packet['pm1_0'], 3.0)
        self.assertEqual(event.packet['pm10_0'], 5.0)
        expected_pm2_5 = AQI.compute_pm2_5_us_epa_correction(10.0, 12.0, 40, 70)
        self.assertAlmostEqual(event.packet['pm2_5'], expected_pm2_5)
        self.assertEqual(event.packet['pm2_5_aqi'],
                         AQI.compute_pm2_5_aqi(expected_pm2_5))
        self.assertEqual(event.packet['pm2_5_aqi_color'],
                         AQI.compute_pm2_5_aqi_color(event.packet['pm2_5_aqi']))

    def test_zero_degrees_f_still_inserts_pm2_5(self):
        # Regression: a temperature of 0 was falsy and dropped pm2_5.
        p = self.make_purple(self.fresh_concentrations(current_temp_f=0))
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertIn('pm2_5', event.packet)

    def test_missing_b_channel_duplicates_a(self):
        p = self.make_purple(self.fresh_concentrations(pm2_5_cf_1_b=None))
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertAlmostEqual(event.packet['pm2_5'],
                               AQI.compute_pm2_5_us_epa_correction(10.0, 10.0, 40, 70))

    def test_missing_pm1_0_skipped(self):
        p = self.make_purple(self.fresh_concentrations(pm1_0=None))
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertNotIn('pm1_0', event.packet)
        self.assertIn('pm2_5', event.packet)
        self.assertIn('pm10_0', event.packet)

    def test_missing_pm10_0_skipped(self):
        p = self.make_purple(self.fresh_concentrations(pm10_0=None))
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertNotIn('pm10_0', event.packet)
        self.assertIn('pm2_5', event.packet)

    def test_missing_humidity_drops_pm2_5_only(self):
        # The EPA correction needs humidity; without it no pm2_5 (and hence
        # no AQI), but the uncorrected fields still go in.
        p = self.make_purple(self.fresh_concentrations(current_humidity=None))
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertNotIn('pm2_5', event.packet)
        self.assertNotIn('pm2_5_aqi', event.packet)
        self.assertNotIn('pm2_5_aqi_color', event.packet)
        self.assertIn('pm1_0', event.packet)
        self.assertIn('pm10_0', event.packet)

    def test_stale_concentrations_not_inserted(self):
        p = self.make_purple(self.fresh_concentrations(timestamp=time.time() - 121))
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertEqual(event.packet, {})

    def test_no_concentrations_not_inserted(self):
        p = self.make_purple(None)
        event = types.SimpleNamespace(packet={})
        p.new_loop_packet(event)
        self.assertEqual(event.packet, {})

    def test_stale_logged_once_per_outage(self):
        p = self.make_purple(self.fresh_concentrations(timestamp=time.time() - 121))
        p.new_loop_packet(types.SimpleNamespace(packet={}))
        self.assertTrue(p.stale_logged)
        p.new_loop_packet(types.SimpleNamespace(packet={}))
        self.assertTrue(p.stale_logged)
        # Fresh data again: flag resets.
        with p.cfg.lock:
            p.cfg.concentrations = self.fresh_concentrations()
        p.new_loop_packet(types.SimpleNamespace(packet={}))
        self.assertFalse(p.stale_logged)

class TestPurpleInit(unittest.TestCase):
    """Startup wiring: config parsing, xtype registration, poller launch.
    The engine is a mock and both the initial fetch and the poller thread
    are patched out, so nothing touches the network."""

    def test_startup_with_sources(self):
        engine = mock.Mock()
        config = {
            'Purple': {
                'poll_secs': 50,
                'Sensor1': {'enable': True, 'hostname': 'sensor1'},
                'Sensor2': {'enable': False, 'hostname': 'sensor2'},
            },
        }
        conc = TestNewLoopPacket.fresh_concentrations()
        n_xtypes = len(weewx.xtypes.xtypes)
        try:
            with mock.patch('user.purple.get_concentrations', return_value=conc) as gc, \
                 mock.patch('user.purple.threading.Thread') as thread_cls:
                p = Purple(engine, config)
            # The synchronous startup fetch ran and its result is stored.
            gc.assert_called_once()
            self.assertIs(p.cfg.concentrations, conc)
            self.assertEqual(p.cfg.poll_secs, 50)
            self.assertEqual(p.cfg.fresh_secs, 150)   # max(120, 3 * 50)
            self.assertEqual(len(p.cfg.sources), 2)   # disabled sources still parsed
            # The AQI xtype is registered at the front of the list.
            self.assertEqual(len(weewx.xtypes.xtypes), n_xtypes + 1)
            self.assertIsInstance(weewx.xtypes.xtypes[0], AQI)
            # The poller thread was created as a daemon and started.
            _, kwargs = thread_cls.call_args
            self.assertTrue(kwargs['daemon'])
            self.assertEqual(kwargs['name'], 'Purple')
            thread_cls.return_value.start.assert_called_once()
            # Bound to NEW_LOOP_PACKET.
            engine.bind.assert_called_once_with(weewx.NEW_LOOP_PACKET, p.new_loop_packet)
        finally:
            # Unregister anything this test added to the global xtypes list.
            del weewx.xtypes.xtypes[0:len(weewx.xtypes.xtypes) - n_xtypes]

    def test_startup_without_sources_is_inoperable(self):
        engine = mock.Mock()
        config = {'Purple': {'Sensor1': {'enable': False, 'hostname': 's'}}}
        n_xtypes = len(weewx.xtypes.xtypes)
        with mock.patch('user.purple.get_concentrations') as gc, \
             mock.patch('user.purple.threading.Thread') as thread_cls:
            p = Purple(engine, config)
        # No fetch, no xtype, no poller, no binding -- but no crash either.
        gc.assert_not_called()
        thread_cls.assert_not_called()
        engine.bind.assert_not_called()
        self.assertEqual(len(weewx.xtypes.xtypes), n_xtypes)
        # Defaults were still parsed.
        self.assertEqual(p.cfg.poll_secs, 15)
        self.assertEqual(p.cfg.fresh_secs, 120)

class TestGetScalar(unittest.TestCase):

    def test_aqi(self):
        record = {'dateTime': 1700000000, 'usUnits': weewx.US, 'pm2_5': 21.8}
        vt = AQI.get_scalar('pm2_5_aqi', record)
        self.assertEqual(vt.value, 75)
        self.assertEqual(vt.unit, 'aqi')
        self.assertEqual(vt.group, 'air_quality_index')

    def test_aqi_color(self):
        record = {'dateTime': 1700000000, 'usUnits': weewx.US, 'pm2_5': 21.8}
        vt = AQI.get_scalar('pm2_5_aqi_color', record)
        self.assertEqual(vt.value, TestComputeAqiColor.YELLOW)
        self.assertEqual(vt.unit, 'aqi_color')

    def test_unknown_type(self):
        with self.assertRaises(weewx.UnknownType):
            AQI.get_scalar('outTemp', {'pm2_5': 1.0})

    def test_no_record(self):
        with self.assertRaises(weewx.CannotCalculate):
            AQI.get_scalar('pm2_5_aqi', None)

    def test_record_without_pm2_5(self):
        with self.assertRaises(weewx.UnknownType):
            AQI.get_scalar('pm2_5_aqi', {'dateTime': 1700000000, 'usUnits': weewx.US})

    def test_record_with_null_pm2_5(self):
        # Catchup records inserted at startup have pm2_5 of None.
        with self.assertRaises(weewx.UnknownType):
            AQI.get_scalar('pm2_5_aqi',
                           {'dateTime': 1700000000, 'usUnits': weewx.US, 'pm2_5': None})

    def test_record_without_usunits(self):
        with self.assertRaises(weewx.CannotCalculate):
            AQI.get_scalar('pm2_5_aqi', {'dateTime': 1700000000, 'pm2_5': 21.8})

class TestGetSeries(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute(
            "CREATE TABLE archive (dateTime INTEGER PRIMARY KEY, usUnits INTEGER, "
            "`interval` INTEGER, pm2_5 REAL)")
        self.db_manager = FakeDBManager(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_unknown_type(self):
        with self.assertRaises(weewx.UnknownType):
            AQI.get_series('outTemp', weeutil.weeutil.TimeSpan(0, 4000), self.db_manager)

    def test_series_without_aggregation(self):
        rows = [(3600, weewx.US, 5, 9.0), (3900, weewx.US, 5, 35.4)]
        self.conn.executemany("INSERT INTO archive VALUES (?, ?, ?, ?)", rows)
        start_vt, stop_vt, data_vt = AQI.get_series(
            'pm2_5_aqi', weeutil.weeutil.TimeSpan(0, 4000), self.db_manager)
        self.assertEqual(start_vt.value, [3300, 3600])
        self.assertEqual(stop_vt.value, [3600, 3900])
        self.assertEqual(data_vt.value, [50, 100])
        self.assertEqual(data_vt.unit, 'aqi')
        self.assertEqual(data_vt.group, 'air_quality_index')

    def test_series_of_colors(self):
        self.conn.execute("INSERT INTO archive VALUES (?, ?, ?, ?)",
                          (3600, weewx.US, 5, 55.5))
        _, _, data_vt = AQI.get_series(
            'pm2_5_aqi_color', weeutil.weeutil.TimeSpan(0, 4000), self.db_manager)
        self.assertEqual(data_vt.value, [TestComputeAqiColor.RED])

    def test_mixed_unit_systems_rejected(self):
        rows = [(3600, weewx.US, 5, 9.0), (3900, weewx.METRIC, 5, 35.4)]
        self.conn.executemany("INSERT INTO archive VALUES (?, ?, ?, ?)", rows)
        with self.assertRaises(weewx.UnsupportedFeature):
            AQI.get_series('pm2_5_aqi', weeutil.weeutil.TimeSpan(0, 4000), self.db_manager)

    def test_aggregation_delegates_to_archive_table(self):
        sentinel = object()
        with mock.patch.object(weewx.xtypes.ArchiveTable, 'get_series',
                               return_value=sentinel) as m:
            result = AQI.get_series('pm2_5_aqi', weeutil.weeutil.TimeSpan(0, 4000),
                                    self.db_manager, 'avg', 3600)
        self.assertIs(result, sentinel)
        m.assert_called_once()

class TestGetAggregate(unittest.TestCase):
    """Runs the xtype's aggregation SQL against a real (SQLite) database:
    an archive table and a pm2_5 daily summary table."""

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute(
            "CREATE TABLE archive (dateTime INTEGER PRIMARY KEY, usUnits INTEGER, "
            "`interval` INTEGER, pm2_5 REAL)")
        self.conn.execute(
            "CREATE TABLE archive_day_pm2_5 (dateTime INTEGER PRIMARY KEY, "
            "min REAL, mintime INTEGER, max REAL, maxtime INTEGER, "
            "sum REAL, count INTEGER, wsum REAL, sumtime INTEGER)")
        self.db_manager = FakeDBManager(self.conn)

    def tearDown(self):
        self.conn.close()

    def insert_archive(self, rows):
        self.conn.executemany("INSERT INTO archive VALUES (?, ?, ?, ?)",
                              [(ts, weewx.US, 5, pm) for ts, pm in rows])

    def test_unknown_type(self):
        with self.assertRaises(weewx.UnknownType):
            AQI.get_aggregate('outTemp', weeutil.weeutil.TimeSpan(1000, 5000),
                              'avg', self.db_manager)

    def test_unknown_aggregation(self):
        for agg in ['sum', 'not_a_thing']:
            with self.assertRaises(weewx.UnknownAggregation):
                AQI.get_aggregate('pm2_5_aqi', weeutil.weeutil.TimeSpan(1000, 5000),
                                  agg, self.db_manager)

    def test_archive_table_aggregates(self):
        # A span NOT on day boundaries: every aggregate must run against
        # the archive table.  (Before v5.0 the first/last SQL was
        # syntactically invalid; this test executes every statement.)
        self.insert_archive([(2000, 9.0), (3000, 35.4), (4000, 55.4)])
        span = weeutil.weeutil.TimeSpan(1000, 5000)
        expectations = {
            'first': 50,   # pm2_5 9.0
            'last': 150,   # pm2_5 55.4
            'min': 50,
            'max': 150,
            'avg': 96,     # pm2_5 (9.0 + 35.4 + 55.4) / 3 = 33.26
        }
        for agg, expected in expectations.items():
            vt = AQI.get_aggregate('pm2_5_aqi', span, agg, self.db_manager)
            self.assertEqual(vt.value, expected, 'aggregate %s' % agg)
            self.assertEqual(vt.unit, 'aqi')

    def test_count_is_not_aqi_transformed(self):
        # Regression: count used to be run through the AQI computation.
        self.insert_archive([(2000, 9.0), (3000, 35.4), (4000, 55.4)])
        vt = AQI.get_aggregate('pm2_5_aqi', weeutil.weeutil.TimeSpan(1000, 5000),
                               'count', self.db_manager)
        self.assertEqual(vt.value, 3)

    def test_color_aggregate(self):
        self.insert_archive([(2000, 9.0), (3000, 55.4)])
        vt = AQI.get_aggregate('pm2_5_aqi_color', weeutil.weeutil.TimeSpan(1000, 5000),
                               'max', self.db_manager)
        self.assertEqual(vt.value, TestComputeAqiColor.ORANGE)

    def test_empty_span(self):
        vt = AQI.get_aggregate('pm2_5_aqi', weeutil.weeutil.TimeSpan(6000, 7000),
                               'min', self.db_manager)
        self.assertIsNone(vt.value)

    @staticmethod
    def local_midnight(year, month, day):
        return int(time.mktime(
            datetime.datetime(year, month, day).timetuple()))

    def populate_day_summaries(self, with_archive=True):
        day1 = self.local_midnight(2026, 1, 5)
        day2 = self.local_midnight(2026, 1, 6)
        day3 = self.local_midnight(2026, 1, 7)
        # day1: avg 10, min 5, max 25.  day2: avg 30, min 15, max 35.
        self.conn.execute(
            "INSERT INTO archive_day_pm2_5 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (day1, 5.0, day1 + 60, 25.0, day1 + 120, 1000.0, 100, 1000.0, 100))
        self.conn.execute(
            "INSERT INTO archive_day_pm2_5 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (day2, 15.0, day2 + 60, 35.0, day2 + 120, 3000.0, 100, 3000.0, 100))
        if with_archive:
            # The day-boundary path reads usUnits from the archive table.
            self.insert_archive([(day1 + 300, 10.0)])
        return day1, day3

    def test_day_boundary_fast_path(self):
        day1, day3 = self.populate_day_summaries()
        span = weeutil.weeutil.TimeSpan(day1, day3)
        # Overall: avg (1000+3000)/(100+100) = 20, min 5, max 35.
        self.assertEqual(
            AQI.get_aggregate('pm2_5_aqi', span, 'avg', self.db_manager).value,
            AQI.compute_pm2_5_aqi(20.0))
        self.assertEqual(
            AQI.get_aggregate('pm2_5_aqi', span, 'min', self.db_manager).value,
            AQI.compute_pm2_5_aqi(5.0))
        self.assertEqual(
            AQI.get_aggregate('pm2_5_aqi', span, 'max', self.db_manager).value,
            AQI.compute_pm2_5_aqi(35.0))

    def test_day_boundary_with_empty_archive_table(self):
        # Day summaries but no archive rows: the usUnits lookup finds no
        # row.  The value still computes; the unit system is unknown.
        day1, day3 = self.populate_day_summaries(with_archive=False)
        vt = AQI.get_aggregate('pm2_5_aqi', weeutil.weeutil.TimeSpan(day1, day3),
                               'avg', self.db_manager)
        self.assertEqual(vt.value, AQI.compute_pm2_5_aqi(20.0))
        self.assertIsNone(vt.unit)

    def test_trailing_24h_window_uses_archive_table(self):
        # Regression: a span whose length is a multiple of 24 hours but
        # which does NOT start at midnight used to be routed to the daily
        # summary table, silently including data outside the span.
        day1, _ = self.populate_day_summaries()
        start = day1 + 3600
        stop = start + 24 * 3600
        self.insert_archive([(start + 300, 9.0), (start + 600, 35.4)])
        vt = AQI.get_aggregate('pm2_5_aqi', weeutil.weeutil.TimeSpan(start, stop),
                               'avg', self.db_manager)
        # Average of the archive rows within the span, (9.0 + 35.4) / 2 = 22.2;
        # the daily summaries (which would give 10.0) must not be consulted.
        self.assertEqual(vt.value, AQI.compute_pm2_5_aqi(22.2))

if __name__ == '__main__':
    unittest.main()
