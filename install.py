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

# Written as weewx.conf text rather than a dict so that the stanza weectl
# merges into a fresh weewx.conf arrives with its comments: ConfigObj keeps
# them, a dict has nowhere to put them.
#
# ORDER MATTERS: ConfigObj attaches a comment block to the NEXT key, so a
# commented-out option must be followed by a live key IN THE SAME SECTION.
# Last in its section, it attaches to whatever section comes next and is
# re-indented to the parent's level, landing outside the block it documents.
# Hence hostname last in every source section.
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
    #
    # Sources are tried proxies first and then sensors, low numbers to
    # high.  The first one that yields a sane, fresh reading wins and no
    # further sources are tried.  The numbering of each kind must start at
    # 1 and be consecutive; a gap ends the scan, so a Proxy3 with no Proxy2
    # is never reached.
    #
    # An option shown commented out is one the extension supplies itself.
    # Leave it commented and the extension's own value governs, including
    # a better one a later release might bring.  Uncomment it to pin this
    # station to the value written here.

    # How often to poll the sensor in seconds
    #poll_secs = 15

    # Proxies are instances of purple-proxy.  Proxies are tried before
    # sensors, in the order listed here, until one yields a good reading.
    # Running one is recommended: it spares the sensor's processor, and
    # filling gaps after WeeWX downtime requires one.
    [[Proxy1]]
        enable = False
        # The port purple-proxy listens on (its server-port)
        #port = 8000
        # http timeout (seconds).  A proxy answers from its own cache
        # rather than going to the sensor, so it can be short.
        #timeout = 1
        # PLACEHOLDER -- replace with the host name or IP address of the
        # machine running the first purple-proxy
        hostname = proxy1
    [[Proxy2]]
        enable = False
        # The port purple-proxy listens on (its server-port)
        #port = 8000
        # http timeout (seconds).  A proxy answers from its own cache
        # rather than going to the sensor, so it can be short.
        #timeout = 1
        # PLACEHOLDER -- replace with the host name or IP address of the
        # machine running the second purple-proxy
        hostname = proxy2
    [[Proxy3]]
        enable = False
        # The port purple-proxy listens on (its server-port)
        #port = 8000
        # http timeout (seconds).  A proxy answers from its own cache
        # rather than going to the sensor, so it can be short.
        #timeout = 1
        # PLACEHOLDER -- replace with the host name or IP address of the
        # machine running the third purple-proxy
        hostname = proxy3
    [[Proxy4]]
        enable = False
        # The port purple-proxy listens on (its server-port)
        #port = 8000
        # http timeout (seconds).  A proxy answers from its own cache
        # rather than going to the sensor, so it can be short.
        #timeout = 1
        # PLACEHOLDER -- replace with the host name or IP address of the
        # machine running the fourth purple-proxy
        hostname = proxy4

    # Sensors are the PurpleAir devices themselves.  Sensor1 is enabled
    # here so that a fresh install works with no proxy; disable it if you
    # run a proxy and would rather not have WeeWX talk to the sensor too.
    [[Sensor1]]
        enable = True
        # The port the sensor's own web server listens on
        #port = 80
        # http timeout (seconds).  A sensor's own processor is slow and
        # easily overwhelmed, so give it more room than a proxy.
        #timeout = 15
        # PLACEHOLDER -- replace with the host name or IP address of
        # the first sensor
        hostname = purple-air
    [[Sensor2]]
        enable = False
        # The port the sensor's own web server listens on
        #port = 80
        # http timeout (seconds)
        #timeout = 15
        # PLACEHOLDER -- replace with the host name or IP address of
        # the second sensor
        hostname = purple-air2
"""

purple_dict = configobj.ConfigObj(StringIO(CONFIG))

def weewx_version_at_least(minimum):
    """Is the running WeeWX at least `minimum` (e.g. (4, 6))?

    A copy of the check in bin/user/purple.py: the installer cannot import
    the extension.  Compared as integers, not as text: WeeWX 4.10 sorts
    BELOW "4.6" as a string, so a plain comparison would reject the whole
    4.10 series (the last of WeeWX 4).  weeutil's own version_compare
    cannot be used here -- it arrived after 4.6, so it is missing from some
    of the versions this has to reject.
    """
    running = []
    for chunk in weewx.__version__.split('.')[:len(minimum)]:
        digits = ''
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        running.append(int(digits) if digits else 0)
    return tuple(running) >= minimum

def loader():
    if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
        sys.exit("weewx-purple requires Python 3.7 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))

    # The demo skin's template uses $gettext and $lang, which arrived in
    # WeeWX 4.6.0 (02/04/2022).
    if not weewx_version_at_least((4, 6)):
        sys.exit("weewx-purple requires WeeWX 4.6 or later, found %s" % weewx.__version__)

    return PurpleInstaller()

class PurpleInstaller(ExtensionInstaller):
    def __init__(self):
        super(PurpleInstaller, self).__init__(
            version="7.1",
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
