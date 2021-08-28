
#
#    See the file LICENSE.txt for your full rights.
#
"""Test processing packets."""

import logging
import unittest

import weeutil.logger

import user.purple

log = logging.getLogger(__name__)

# Set up logging using the defaults.
weeutil.logger.setup('test_config', {})

class PurpleTests(unittest.TestCase):
    #             U.S. EPA PM2.5 AQI
    #
    #  AQI Category  AQI Value  24-hr PM2.5
    # Good             0 -  50    0.0 -  12.0
    # Moderate        51 - 100   12.1 -  35.4
    # USG            101 - 150   35.5 -  55.4
    # Unhealthy      151 - 200   55.5 - 150.4
    # Very Unhealthy 201 - 300  150.5 - 250.4
    # Hazardous      301 - 400  250.5 - 350.4
    # Hazardous      401 - 500  350.5 - 500.4

    def test_compute_pm2_5_aqi(self):

        # Good
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 0.0), 0)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 6.0), 25)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(12.0), 50)
        # 12.099 is truncated to 12
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(12.099), 50)

        # Moderate
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(12.1),  51)
        aqi = user.purple.AQI.compute_pm2_5_aqi(23.7)
        self.assertTrue(aqi > 75.3948 and aqi < 75.3949)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(35.499), 100)

        # USG
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(35.5), 101)
        aqi = user.purple.AQI.compute_pm2_5_aqi(45.4)
        self.assertTrue(aqi > 125.3768 and aqi < 125.3769)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(55.4), 150)

        # Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 55.5), 151)
        aqi = user.purple.AQI.compute_pm2_5_aqi(102.9)
        self.assertTrue(aqi, 175.4)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(150.4), 200)

        # Very Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(150.5), 201)
        aqi = user.purple.AQI.compute_pm2_5_aqi(200.4)
        self.assertTrue(aqi > 250.4504 and aqi < 250.4505)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(250.4), 300)

        # Harzadous
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(250.5), 301)
        aqi = user.purple.AQI.compute_pm2_5_aqi(300.4)
        self.assertTrue(aqi > 350.4504 and aqi < 350.4505)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(350.4), 400)

        # Harzadous
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(350.5), 401)
        aqi = user.purple.AQI.compute_pm2_5_aqi(425.45)
        self.assertTrue(aqi > 450.4 and aqi < 450.6)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(500.4), 500)

    #             U.S. EPA PM2.5 AQI
    #
    #  AQI Category  AQI Value  24-hr PM2.5
    # Good             0 -  50    0.0 -  12.0
    # Moderate        51 - 100   12.1 -  35.4
    # USG            101 - 150   35.5 -  55.4
    # Unhealthy      151 - 200   55.5 - 150.4
    # Very Unhealthy 201 - 300  150.5 - 250.4
    # Hazardous      301 - 400  250.5 - 350.4
    # Hazardous      401 - 500  350.5 - 500.4

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
        self.assertTrue(pm2_5 > 53.73 and pm2_5 < 53.75)

        # High concentration
        pm2_5 = user.purple.AQI.compute_pm2_5_us_epa_correction(395.0, 405.0, 95.0, 20.0)
        self.assertTrue(pm2_5 > 249.84 and pm2_5 < 249.86)

if __name__ == '__main__':
    unittest.main()
