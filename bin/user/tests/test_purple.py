
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
    # Good             0 -  50    0.0 -  12.0 Green
    # Moderate        50 - 100   12.0 -  35.4 Yellow
    # USG            100 - 150   35.4 -  55.4 Orange
    # Unhealthy      150 - 200   55.4 - 150.4 Red
    # Very Unhealthy 200 - 300  150.4 - 250.4 Purple
    # Hazardous      300 - 400  250.4 - 350.4 Maroon
    # Hazardous      400 - 500  350.4 - 500.0 Maroon

    def test_compute_pm2_5_aqi(self):

        # Good
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 0.0), 0)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi( 6.0), 25)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(12.0), 50)

        # Moderate
        self.assertTrue(user.purple.AQI.compute_pm2_5_aqi(12.001) > 50.0021 and user.purple.AQI.compute_pm2_5_aqi(12.001) < 50.0022)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(23.700),  75)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(35.400), 100)

        # USG
        self.assertTrue(user.purple.AQI.compute_pm2_5_aqi(35.401) > 100.002500 and user.purple.AQI.compute_pm2_5_aqi(35.401) < 100.002501)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(45.400), 125)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(55.400), 150)

        # Unhealthy
        self.assertTrue(user.purple.AQI.compute_pm2_5_aqi( 55.401) > 150.0005263 and user.purple.AQI.compute_pm2_5_aqi( 55.401) < 150.0005264)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(102.900), 175)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(150.400), 200)

        # Very Unhealthy
        self.assertTrue(user.purple.AQI.compute_pm2_5_aqi(150.401) > 200.0009 and user.purple.AQI.compute_pm2_5_aqi(150.401) < 200.0011)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(200.400), 250)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(250.400), 300)

        # Harzadous
        self.assertTrue(user.purple.AQI.compute_pm2_5_aqi(250.401) > 300.0009 and user.purple.AQI.compute_pm2_5_aqi(250.401) < 300.0011)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(300.400), 350)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(350.400), 400)

        # Harzadous
        self.assertTrue(user.purple.AQI.compute_pm2_5_aqi(350.401) > 400.000668 and user.purple.AQI.compute_pm2_5_aqi(350.401) < 400.000669)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(425.200), 450)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi(500.000), 500)

    #             U.S. EPA PM2.5 AQI
    #
    #  AQI Category  AQI Value  24-hr PM2.5
    # Good             0 -  50    0.0 -  12.0 Green
    # Moderate        50 - 100   12.0 -  35.4 Yellow
    # USG            100 - 150   35.4 -  55.4 Orange
    # Unhealthy      150 - 200   55.4 - 150.4 Red
    # Very Unhealthy 200 - 300  150.4 - 250.4 Purple
    # Hazardous      300 - 400  250.4 - 350.4 Maroon
    # Hazardous      400 - 500  350.4 - 500.0 Maroon

    def test_compute_pm2_5_aqi_color(self):

        # Good
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color( 0), 255 << 8)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(25), 255 << 8)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(50), 255 << 8)

        # Moderate
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(50.001), (255 << 16) + (255 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(75    ), (255 << 16) + (255 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(100   ), (255 << 16) + (255 << 8))

        # USG
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(100.001), (255 << 16) + (165 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(125    ), (255 << 16) + (165 << 8))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(150    ), (255 << 16) + (165 << 8))

        # Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(150.001), (255 << 16))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(175    ), (255 << 16))
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(200    ), (255 << 16))

        # Very Unhealthy
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(200.001), (128 << 16) + 128)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(250    ), (128 << 16) + 128)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(300    ), (128 << 16) + 128)

        # Harzadous
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(300.001), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(350    ), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(400    ), 128 << 16)

        # Harzadous
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(400.001), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(450    ), 128 << 16)
        self.assertEqual(user.purple.AQI.compute_pm2_5_aqi_color(500    ), 128 << 16)

if __name__ == '__main__':
    unittest.main()
