#
# Copyright (c) 2019-2020 Red Hat, Inc.
#
# This file is part of nmstate
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

import pytest

import libnmstate
from libnmstate import nm
from libnmstate.schema import Interface
from libnmstate.schema import InterfaceIPv4
from libnmstate.schema import InterfaceIPv6
from libnmstate.nm.profile import get_all_applied_configs

from ..testlib import cmdlib
from ..testlib import iproutelib
from ..testlib import assertlib
from ..testlib.retry import retry_till_true_or_timeout
from .testlib import main_context


TEST_IFACE = "eth1"

IPV4_ADDRESS1 = "192.0.2.251"

RETRY_TIMEOUT = 5


def _dict_is_subset(superset, subset):
    """
    Code copied from Ignacio Vazquez-Abrams in
    https://stackoverflow.com/questions/9323749
    License is CC BY-SA 3.0
    """
    return all(item in superset.items() for item in subset.items())


def _ip_state_is_expected(nm_plugin, expected_state):
    nm_plugin.refresh_content()
    ipv4_current_state = _get_ipv4_current_state(nm_plugin.context, TEST_IFACE)
    return _dict_is_subset(expected_state, ipv4_current_state)


@iproutelib.ip_monitor_assert_stable_link_up(TEST_IFACE)
def test_interface_ipv4_change(eth1_up, nm_plugin):
    _modify_interface(
        nm_plugin.context,
        ipv4_state={
            InterfaceIPv4.ENABLED: True,
            InterfaceIPv4.DHCP: False,
            InterfaceIPv4.ADDRESS: [
                {
                    InterfaceIPv4.ADDRESS_IP: IPV4_ADDRESS1,
                    InterfaceIPv4.ADDRESS_PREFIX_LENGTH: 24,
                }
            ],
        },
    )

    expected_ipv4_state = {
        InterfaceIPv4.ENABLED: True,
        InterfaceIPv4.DHCP: False,
        InterfaceIPv4.ADDRESS: [
            {
                InterfaceIPv4.ADDRESS_IP: IPV4_ADDRESS1,
                InterfaceIPv4.ADDRESS_PREFIX_LENGTH: 24,
            }
        ],
    }
    assert retry_till_true_or_timeout(
        RETRY_TIMEOUT, _ip_state_is_expected, nm_plugin, expected_ipv4_state
    )


def test_enable_dhcp_with_no_server(eth1_up, nm_plugin):
    _modify_interface(
        nm_plugin.context,
        ipv4_state={
            InterfaceIPv4.ENABLED: True,
            InterfaceIPv4.DHCP: True,
            InterfaceIPv4.ADDRESS: [],
        },
    )

    expected_ipv4_state = {
        InterfaceIPv4.ENABLED: True,
        InterfaceIPv4.DHCP: True,
        InterfaceIPv4.ADDRESS: [],
        InterfaceIPv4.AUTO_DNS: True,
        InterfaceIPv4.AUTO_GATEWAY: True,
        InterfaceIPv4.AUTO_ROUTES: True,
        InterfaceIPv4.AUTO_ROUTE_TABLE_ID: 0,
    }
    assert retry_till_true_or_timeout(
        RETRY_TIMEOUT, _ip_state_is_expected, nm_plugin, expected_ipv4_state
    )


def _modify_interface(ctx, ipv4_state):
    conn = nm.profile.NmProfile(ctx, True)
    conn._import_existing_profile(TEST_IFACE)
    settings = _create_iface_settings(ipv4_state, conn)
    conn._simple_conn = nm.connection.create_new_simple_connection(settings)
    with main_context(ctx):
        conn._update()
        ctx.wait_all_finish()
        nm.device.modify(ctx, conn)
        ctx.wait_all_finish()


def _get_ipv4_current_state(ctx, ifname):
    nmdev = ctx.get_nm_dev(ifname)
    active_connection = nm.connection.get_device_active_connection(nmdev)
    applied_config = get_all_applied_configs(ctx)
    return nm.ipv4.get_info(active_connection, applied_config.get(ifname))


def _create_iface_settings(ipv4_state, con_profile):
    con_setting = nm.connection.ConnectionSetting()
    con_setting.import_by_profile(con_profile.profile)

    ipv4_setting = nm.ipv4.create_setting(ipv4_state, con_profile.profile)
    ipv6_setting = nm.ipv6.create_setting({}, None)

    return con_setting.setting, ipv4_setting, ipv6_setting


def test_get_applied_config_for_dhcp_state_with_dhcp_enabeld_on_disk(eth1_up):
    iface_state = eth1_up[Interface.KEY][0]
    iface_name = iface_state[Interface.NAME]
    cmdlib.exec_cmd(
        f"nmcli c modify {iface_name} ipv4.method auto".split(), check=True
    )
    cmdlib.exec_cmd(
        f"nmcli c modify {iface_name} ipv6.method auto".split(), check=True
    )

    assertlib.assert_state_match({Interface.KEY: [iface_state]})


@pytest.fixture
def eth1_up_with_auto_ip(eth1_up):
    iface_name = eth1_up[Interface.KEY][0][Interface.NAME]
    iface_state = {
        Interface.NAME: iface_name,
        Interface.IPV4: {
            InterfaceIPv4.ENABLED: True,
            InterfaceIPv4.DHCP: True,
        },
        Interface.IPV6: {
            InterfaceIPv6.ENABLED: True,
            InterfaceIPv6.DHCP: True,
            InterfaceIPv6.AUTOCONF: True,
        },
    }
    libnmstate.apply({Interface.KEY: [iface_state]})
    yield iface_state


def test_get_applied_config_for_dhcp_state_with_dhcp_disabled_on_disk(
    eth1_up_with_auto_ip,
):
    iface_state = eth1_up_with_auto_ip
    iface_name = iface_state[Interface.NAME]
    cmdlib.exec_cmd(
        f"nmcli c modify {iface_name} ipv4.method disabled".split(), check=True
    )
    cmdlib.exec_cmd(
        f"nmcli c modify {iface_name} ipv6.method disabled".split(), check=True
    )

    assertlib.assert_state_match({Interface.KEY: [iface_state]})
