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
import weewx


from setup import ExtensionInstaller

def loader():
    if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
        sys.exit("weewx-purple requires Python 3.7 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))

    if weewx.__version__ < "4":
        sys.exit("weewx-purple requires WeeWX 4, found %s" % weewx.__version__)

    return PurpleInstaller()

class PurpleInstaller(ExtensionInstaller):
    def __init__(self):
        super(PurpleInstaller, self).__init__(
            version="4.0.1",
            name='purple',
            description='Record air quality via purple-proxy service.',
            author="John A Kline",
            author_email="john@johnkline.com",
            data_services='user.purple.Purple',
            config = {
                'StdReport': {
                    'PurpleReport': {
                        'HTML_ROOT':'purple',
                        'enable': 'true',
                        'skin':'purple',
                    },
                },
                'Purple': {
                    'poll_secs'          : 15,
                    'Proxy1'   : {
                        'enable'         : False,
                        'hostname'       : 'proxy1',
                        'port'           : '8000',
                        'timeout'        : '5',
                    },
                    'Proxy2' : {
                        'enable'         : False,
                        'hostname'       : 'proxy2',
                        'port'           : '8000',
                        'timeout'        : '5',
                    },
                    'Proxy3'  : {
                        'enable'         : False,
                        'hostname'       : 'proxy3',
                        'port'           : '8000',
                        'timeout'        : '5',
                    },
                    'Proxy4': {
                        'enable'         : False,
                        'hostname'       : 'proxy4',
                        'port'           : '8000',
                        'timeout'        : '5',
                    },
                    'Sensor1'  : {
                        'enable'     : True,
                        'hostname'   : 'purple-air',
                        'port'       : '80',
                        'timeout'    : '15',
                    },
                    'Sensor2': {
                        'enable'     : False,
                        'hostname'   : 'purple-air2',
                        'port'       : '80',
                        'timeout'    : '15',
                    },
                },
            },
            files=[
                ('bin/user', ['bin/user/purple.py']),
                ('skins/purple', [
                    'skins/purple/index.html.tmpl',
                    'skins/purple/skin.conf',
                ]),
            ]
        )
