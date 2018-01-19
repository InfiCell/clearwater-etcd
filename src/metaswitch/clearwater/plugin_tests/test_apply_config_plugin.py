# @file test_apply_config_plugin.py.py
#
# Copyright (C) Metaswitch Networks 2016
# If license terms are provided to you in a COPYING file in the root directory
# of the source code repository by which you are accessing this code, then
# the license outlined in that COPYING file applies to your use.
# Otherwise no rights are granted except for those provided to you by
# Metaswitch Networks in a separate written agreement.

import unittest
import mock
import logging

_log = logging.getLogger()

from clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin import ApplyConfigPlugin
from metaswitch.clearwater.queue_manager.plugin_base import PluginParams

# run_command returns 0 if the shell command provided succeeds, and the return
# code if it fails. This pair of functions are used as mock side-effects to
# simulate run_command("check_node_health.py") succeeding ir failing.
# The success function is not strictly necessary, but ensures symmetry.

def run_commands_all_succeed(command, **kwargs):
    return 0

def run_commands_check_node_health_fails(command, **kwargs):
    if (command[0] == \
            ["/usr/share/clearwater/clearwater-queue-manager/scripts/check_node_health.py"]):
        return 1
    else:
        return 0


class TestApplyConfigPlugin(unittest.TestCase):
    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.subprocess.check_output')
    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.os.path.exists')
    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.os.listdir')
    def test_front_of_queue(self, mock_os_listdir, mock_os_path_exists,
                            mock_subproc_check_output):
        """Test Queue Manager front_of_queue function"""
        mock_run_commands = mock.MagicMock(side_effect=run_commands_all_succeed)
        
        mock_subproc_check_output.return_value = "apply_config_key"
        # Create the plugin
        plugin = ApplyConfigPlugin(PluginParams(wait_plugin_complete='Y'))

        # Set up the mock environment and expectations
        mock_os_path_exists.return_value = True
        mock_os_listdir.return_value = ["test_restart_script"]

        expected_command_call_list = \
            [mock.call([x]) for x in [['service', 'clearwater-infrastructure', 'restart'],
             ['/usr/share/clearwater/infrastructure/scripts/restart/test_restart_script'],
             ['/usr/share/clearwater/clearwater-queue-manager/scripts/check_node_health.py'],
             ['/usr/share/clearwater/clearwater-queue-manager/scripts/modify_nodes_in_queue', \
                       'remove_success', 'apply_config_key']]]

        with mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.run_commands', new=mock_run_commands), \
             mock.patch('metaswitch.clearwater.etcd_shared.plugin_utils.run_commands', new=mock_run_commands):
            # Call the plugin hook
            plugin.at_front_of_queue()

        # Test our assertions
        mock_os_path_exists.assert_called_once_with\
                            ("/usr/share/clearwater/infrastructure/scripts/restart/")
        mock_os_listdir.assert_called_once_with\
                            ("/usr/share/clearwater/infrastructure/scripts/restart/")
        mock_run_commands.assert_has_calls(expected_command_call_list)

    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.subprocess.check_output')
    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.os.path.exists')
    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.os.listdir')
    def test_front_of_queue_fail_node_health(self, mock_os_listdir,
                                             mock_os_path_exists, 
                                             mock_subproc_check_output):
        """Test Queue Manager when check_node_health fails"""

        mock_run_commands = mock.MagicMock(side_effect=run_commands_check_node_health_fails)
        mock_subproc_check_output.return_value = "apply_config_key"
        # Create the plugin
        plugin = ApplyConfigPlugin(PluginParams(wait_plugin_complete='Y'))

        # Set up the mock environment and expectations
        mock_os_path_exists.return_value = True
        mock_os_listdir.return_value = ["test_restart_script"]

        expected_command_call_list = \
            [mock.call([x]) for x in [['service', 'clearwater-infrastructure', 'restart'],
             ['/usr/share/clearwater/infrastructure/scripts/restart/test_restart_script'],
             ['/usr/share/clearwater/clearwater-queue-manager/scripts/check_node_health.py'],
             ['/usr/share/clearwater/clearwater-queue-manager/scripts/modify_nodes_in_queue', \
                       'remove_failure', u'apply_config_key']]]

        with mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.run_commands', new=mock_run_commands), \
             mock.patch('metaswitch.clearwater.etcd_shared.plugin_utils.run_commands', new=mock_run_commands):
            # Call the plugin hook
            plugin.at_front_of_queue()

        # Test our assertions
        mock_os_path_exists.assert_called_once_with\
                            ("/usr/share/clearwater/infrastructure/scripts/restart/")
        mock_os_listdir.assert_called_once_with\
                            ("/usr/share/clearwater/infrastructure/scripts/restart/")
        mock_run_commands.assert_has_calls(expected_command_call_list)

    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.subprocess.check_output')
    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.os.path.exists')
    @mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.os.listdir')
    def test_front_of_queue_no_health_check(self, mock_os_listdir,
                                            mock_os_path_exists, 
                                            mock_subproc_check_output):
        """Test Queue Manager when we're not checking node health"""

        mock_run_commands = mock.MagicMock(side_effect=run_commands_all_succeed)

        mock_subproc_check_output.return_value = "apply_config_key"
        # Create the plugin
        plugin = ApplyConfigPlugin(PluginParams(wait_plugin_complete='N'))

        # Set up the mock environment and expectations
        mock_os_path_exists.return_value = True
        mock_os_listdir.return_value = ["test_restart_script", "test_restart_script2"]

        expected_command_call_list = \
             [mock.call([['service', 'clearwater-infrastructure', 'restart']]),
              mock.call([['/usr/share/clearwater/infrastructure/scripts/restart/test_restart_script'],
               ['/usr/share/clearwater/infrastructure/scripts/restart/test_restart_script2']]),
              mock.call([['/usr/share/clearwater/clearwater-queue-manager/scripts/modify_nodes_in_queue', \
                 'remove_success', 'apply_config_key']])]

        with mock.patch('clearwater_etcd_plugins.clearwater_queue_manager.apply_config_plugin.run_commands', new=mock_run_commands), \
             mock.patch('metaswitch.clearwater.etcd_shared.plugin_utils.run_commands', new=mock_run_commands):
            # Call the plugin hook
            plugin.at_front_of_queue()

        # Test our assertions
        mock_os_path_exists.assert_called_once_with\
                            ("/usr/share/clearwater/infrastructure/scripts/restart/")
        mock_os_listdir.assert_called_once_with\
                            ("/usr/share/clearwater/infrastructure/scripts/restart/")
        mock_run_commands.assert_has_calls(expected_command_call_list)
