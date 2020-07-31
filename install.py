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

from setup import ExtensionInstaller

def loader():
    return PurpleInstaller()

class PurpleInstaller(ExtensionInstaller):
    def __init__(self):
        super(PurpleInstaller, self).__init__(
            version="2.0.b1",
            name='purple',
            description='Record air quality via purple-proxy service.',
            author="John A Kline",
            author_email="john@johnkline.com",
            data_services='user.purple.Purple',
            config={
                'Purple': {
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
            files=[('bin/user', ['bin/user/purple.py']), ]
            )
