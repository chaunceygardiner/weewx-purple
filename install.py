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
            version="1.0",
            name='purple',
            description='Record air quality via purple-proxy service.',
            author="John A Kline",
            author_email="john@johnkline.com",
            archive_services='user.purple.Purple',
            config={
                'Purple': {
                    'data_binding'   : 'purple_binding',
                    'PrimarySensor'  : {
                        'enable'     : True,
                        'hostname'   : 'purple-air',
                        'port'       : '80',
                        'timeout'    : '15',
                    },
                    'SecondarySensor': {
                        'enable'     : False,
                        'hostname'   : 'purple-air2',
                        'port'       : '80',
                        'timeout'    : '15',
                    },
                    'PrimaryProxy'   : {
                        'enable'     : False,
                        'hostname'   : 'proxy',
                        'port'       : '8000',
                        'timeout'    : '5',
                    },
                    'SecondaryProxy' : {
                        'enable'     : False,
                        'hostname'   : 'proxy2',
                        'port'       : '8000',
                        'timeout'    : '5',
                    },
                    'TertiaryProxy'  : {
                        'enable'     : False,
                        'hostname'   : 'proxy3',
                        'port'       : '8000',
                        'timeout'    : '5',
                    },
                    'QuaternaryProxy': {
                        'enable'     : False,
                        'hostname'   : 'proxy4',
                        'port'       : '8000',
                        'timeout'    : '5',
                    },
                },
                'DataBindings': {
                    'purple_binding': {
                        'manager': 'weewx.manager.DaySummaryManager',
                        'schema': 'user.purple.schema',
                        'table_name': 'archive',
                        'database': 'purple_sqlite'}},
                'Databases': {
                    'purple_sqlite': {
                        'database_name': 'purple.sdb',
                        'driver': 'weedb.sqlite'}},
            },
            files=[('bin/user', ['bin/user/purple.py']), ]
            )
