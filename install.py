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

import sys
from io import StringIO

import configobj

import weewx
from weecfg.extension import ExtensionInstaller

CONFIG="""
[StdReport]
    [[PurpleReport]]
        # The "PurpleReport" uses the "purple" skin, which showcases the extension.
        # Images and files are placed in a dedicated subdirectory.
        HTML_ROOT = purple
        enable = true
        skin = purple

[Purple]
    # This section is for configuring the extension weewx-purple.
    # See the README.md for details.

    # How often to poll the sensor in seconds
    poll_secs = 15

    # Proxies are instances of purple-proxy
    [[Proxy1]]
        enable = False
        hostname = proxy1
        port = 8000
        timeout = 1
    [[Proxy2]]
        enable = False
        hostname = proxy2
        port = 8000
        timeout = 1
    [[Proxy3]]
        enable = False
        hostname = proxy3
        port = 8000
        timeout = 1
    [[Proxy4]]
        enable = False
        hostname = proxy4
        port = 8000
        timeout = 1

    # Sensors are hardware instances
    [[Sensor1]]
        enable = True
        # Replace with the host name or IP address of the first sensor
        hostname = purple-air
        # Port is usually 80
        port = 80
        # http timeout (seconds)
        timeout = 15
    [[Sensor2]]
        enable = False
        # Replace with the host name or IP address of the second sensor
        hostname = purple-air2
        # Port is usually 80
        port = 80
        # http timeout (seconds)
        timeout = 15
"""

purple_dict = configobj.ConfigObj(StringIO(CONFIG))

def loader():
    if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
        sys.exit("weewx-purple requires Python 3.7 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))

    if weewx.__version__ < "4":
        sys.exit("weewx-purple requires WeeWX 4, found %s" % weewx.__version__)

    return PurpleInstaller()

class PurpleInstaller(ExtensionInstaller):
    def __init__(self):
        super(PurpleInstaller, self).__init__(
            version="7.0",
            name='purple',
            description='Collect air quality readings from PurpleAir sensors (or purple-proxy).',
            author="John A Kline",
            author_email="john@johnkline.com",
            data_services='user.purple.Purple',
            config = purple_dict,
            files=[
                ('bin/user', ['bin/user/purple.py']),
                ('skins/purple', [
                    'skins/purple/index.html.tmpl',
                    'skins/purple/skin.conf',
                ]),
                ('skins/purple/font', [
                    'skins/purple/font/OpenSans-Regular.ttf',
                    'skins/purple/font/OpenSans-Bold.ttf',
                    'skins/purple/font/license.txt',
                ]),
                ('skins/purple/lang', [
                    'skins/purple/lang/en.conf',
                    'skins/purple/lang/de.conf',
                    'skins/purple/lang/fr.conf',
                    'skins/purple/lang/nl.conf',
                    'skins/purple/lang/es.conf',
                ]),
            ]
        )
