
#
#    See the file LICENSE.txt for your full rights.
#
"""Test processing packets."""

import logging
import unittest

from typing import Any, Dict

import weeutil.logger

import user.purple

log = logging.getLogger(__name__)

# Set up logging using the defaults.
weeutil.logger.setup('test_config', {})

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

class PurpleTests(unittest.TestCase):
    #             U.S. EPA PM2.5 AQI
    #
    #  AQI Category  AQI Value  24-hr PM2.5
    # Good             0 -  50    0.0 -   9.0
    # Moderate        51 - 100    9.1 -  35.4
    # USG            101 - 150   35.5 -  55.4
    # Unhealthy      151 - 200   55.5 - 125.4
    # Very Unhealthy 201 - 300  125.5 - 225.4
    # Hazardous      301 - 500  225.5 and above

    def test_compute_pm2_5_aqi(self):

        # Good
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 0.0), 0)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 6.0), 33)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 9.0), 50)
        # 9.099 is truncated to 9
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(9.099), 50)

        # Moderate
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(9.1),  51)
        aqi = user.purple.AQI.compute_pm2_5_aqi(21.8)
        self.assertEqual(aqi, 75)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(35.499), 100)

        # USG
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(35.5), 101)
        aqi = user.purple.AQI.compute_pm2_5_aqi(45.4)
        self.assertEqual(aqi, 125)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(55.4), 150)

        # Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 55.5), 151)
        aqi = user.purple.AQI.compute_pm2_5_aqi(90.5)
        self.assertTrue(aqi, 175.4)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(125.4), 200)

        # Very Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(125.5), 201)
        aqi = user.purple.AQI.compute_pm2_5_aqi(175.4)
        self.assertEqual(aqi, 250)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(225.4), 300)

        # Harzadous
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(225.5), 301)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(325.0), 400)
        aqi = user.purple.AQI.compute_pm2_5_aqi(375.0)
        self.assertEqual(aqi, 450)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(425.0), 500)

    #             U.S. EPA PM2.5 AQI
    #
    #  AQI Category  AQI Value  24-hr PM2.5
    # Good             0 -  50    0.0 -   9.0
    # Moderate        51 - 100    9.1 -  35.4
    # USG            101 - 150   35.5 -  55.4
    # Unhealthy      151 - 200   55.5 - 125.4
    # Very Unhealthy 201 - 300  125.5 - 225.4
    # Hazardous      301 - 500  225.5 and above

    def test_compute_pm2_5_aqi_color(self):

        # Good
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color( 0), 128 << 8)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(25), 128 << 8)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(50), 128 << 8)

        # Moderate
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color( 51), (255 << 16) + (255 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color( 75), (255 << 16) + (255 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(100), (255 << 16) + (255 << 8))

        # USG
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(101), (255 << 16) + (140 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(125), (255 << 16) + (140 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(150), (255 << 16) + (140 << 8))

        # Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(151), (255 << 16))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(175), (255 << 16))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(200), (255 << 16))

        # Very Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(201), (128 << 16) + 128)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(250), (128 << 16) + 128)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(300), (128 << 16) + 128)

        # Harzadous
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(301), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(350), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(400), 128 << 16)

        # Harzadous
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(401), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(450), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(500), 128 << 16)

    def test_compute_pm2_5_us_epa_correction(self):
        # 2021 EPA Correction
        # Low Concentration PAcf_1 ≤ 343 μg m-3  : PM2.5 = 0.52 x PAcf_1 - 0.086 x RH + 5.75
        # High Concentration PAcf_1 > 343 μg m-3 : PM2.5 = 0.46 x PAcf_1 + 3.93 x 10**-4 x PAcf_1**2 + 2.97

        # compute_pm2_5_us_epa_correction(pm2_5_cf_1: float, pm2_5_cf_1_b: float, current_humidity: int, current_temp_f: int)

        # 0 concentration and 0 RH
        self.assertEqual(user.purple.AQI.compute_pm2_5_us_epa_correction(0.0, 0.0, 0.0, 96), 5.75)

        # 0 concentration and reasonable RH
        self.assertEqual(user.purple.AQI.compute_pm2_5_us_epa_correction(0.0, 0.0, 21.0, 96.0), 3.944)

        # Low concentration
        pm2_5 = user.purple.AQI.compute_pm2_5_us_epa_correction(118.0, 98.0, 95.0, 20.0)
        self.assertAlmostEqual(pm2_5, 53.74)

        # High concentration
        pm2_5 = user.purple.AQI.compute_pm2_5_us_epa_correction(395.0, 405.0, 95.0, 20.0)
        self.assertAlmostEqual(pm2_5, 249.85)

    def test_is_sane(self):
        ok, reason = user.purple.is_sane(VALID_PKT)
        self.assertTrue(ok, reason)

        # Bad Date
        bad_pkt= VALID_PKT.copy()
        bad_pkt['DateTime'] = 'xyz'
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertEqual(reason, 'DateTime is not an instance of datetime: xyz')

        # Bad Temp
        bad_pkt = VALID_PKT.copy()
        bad_pkt['current_temp_f'] = 'nan'
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok)
        self.assertEqual(reason, "current_temp_f is not an instance of <class 'int'>: nan")

        # Disagreeing Sensors
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2_5_cf_1_b'] = 25.0
        bad_pkt['pm2_5_cf_1'] = 1.0
        ok, reason = user.purple.is_sane(bad_pkt)
        self.assertFalse(ok, reason)
        self.assertEqual(reason, 'Sensors disagree wildly for pm2_5_cf_1 (1.000000, 25.000000)')

        # Disagreeing Sensors, but pm2_5 too low to trigger disagreement
        bad_pkt = VALID_PKT.copy()
        bad_pkt['pm2_5_cf_1'] = 0.000001
        ok, _ = user.purple.is_sane(bad_pkt)
        self.assertTrue(ok)

if __name__ == '__main__':
    unittest.main()
