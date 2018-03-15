# Copyright (C) Metaswitch Networks 2017
# If license terms are provided to you in a COPYING file in the root directory
# of the source code repository by which you are accessing this code, then
# the license outlined in that COPYING file applies to your use.
# Otherwise no rights are granted except for those provided to you by
# Metaswitch Networks in a separate written agreement.

import unittest
import subprocess
import os
import mock

import metaswitch.clearwater.config_manager.config_type_class_plugin as config_type_class_plugin
import metaswitch.clearwater.config_manager.config_type_plugin_loader as config_type_plugin_loader
from clearwater_etcd_plugins.clearwater_config_access import bgcf_json_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import dns_json_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import sas_json_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import shared_config_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import shared_ifcs_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import scscf_json_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import fallback_ifcs_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import enum_json_config_plugin
from clearwater_etcd_plugins.clearwater_config_access import rph_json_config_plugin


class TestClass(config_type_class_plugin.ConfigType):
    """This class is used to test returning no scripts as a sub clsss"""
    name = 'random'
    help_info = 'help'
    file_download_name = 'random_config'
    filetype = 'random'


@mock.patch("metaswitch.clearwater.config_manager.config_type_class_plugin.log")
@mock.patch("metaswitch.clearwater.config_manager.config_type_class_plugin.subprocess.check_call")
class TestConfigTypeClassPlugin(unittest.TestCase):

    def test_validate_passes(self, mock_subprocess, mock_log):
        """uses script from DnsJson to ConfigType.validate and check log
         and subprocess called properly, check failed_scripts is empty
         at end of process"""
        dns_config = dns_json_config_plugin.DnsJson('path')
        answer = dns_config.validate()

        # We expect that no scripts failed, and the dns_schema script passed
        self.assertListEqual(answer[0], [])
        self.assertListEqual(answer[1], ["/usr/share/clearwater/clearwater-config-manager/scripts/config_validation/dns_schema.json"])
        self.assertIs(mock_subprocess.call_count, 1)

    def test_bgcf_plugin_creatable(self, mock_subprocess, mock_log):
        """Just loads the BGCF plugin and checks it can be created."""
        bgcf_config = bgcf_json_config_plugin.BgcfJson('path')
        self.assertIsNotNone(bgcf_config)

    def test_sas_validate_passes(self, mock_subprocess, mock_log):
        """Just loads the SAS plugin and checks it can be created."""
        sas_config = sas_json_config_plugin.SasJson('path')
        self.assertIsNotNone(sas_config)

    def test_validate_fails(self, mock_subprocess, mock_log):
        """use ConfigType.validate and get subprocess to raise a exception and
         check log reports this and failed scripts is not empty"""
        shared_config = shared_config_config_plugin.SharedConfig('path')
        shared_config.scripts = {'name1': ['script1'], 'name2': ['script2']}
        validation_error = subprocess.CalledProcessError('A', 'B')
        validation_error.output = "ERROR: Something went wrong"

        # The first validation script passes, the second raises an exception
        mock_subprocess.side_effect = ["", validation_error]

        # possibly want to run this within assertRaises check as well
        answer = shared_config.validate()

        self.assertListEqual(answer[0], ['name1'])
        self.assertIs(mock_subprocess.call_count, 2)

    @mock.patch("metaswitch.clearwater.config_manager.config_type_class_plugin.ConfigType.get_json_validation")
    @mock.patch("metaswitch.clearwater.config_manager.config_type_class_plugin.ConfigType.get_xml_validation")
    @mock.patch("metaswitch.clearwater.config_manager.config_type_class_plugin.ConfigType.get_sharedconfig_validation")
    def test_init(self, mock_shared, mock_xml, mock_json, mock_subprocess, mock_log):
        """test ___init__ with filetype and check correct script finder
        picked """

        mock_json.return_value = {'name1': ['script1'], 'name2': ['script2']}
        mock_xml.return_value = {'name3': ['script3'], 'name4': ['script4']}
        mock_shared.return_value = {'name5': ['script5'], 'name6': ['script6']}

        enum_json = enum_json_config_plugin.EnumJson('path')
        ifcs_xml = shared_ifcs_config_plugin.SharedIfcsXml('path')
        shared_config = shared_config_config_plugin.SharedConfig('path')
        random_config = TestClass('path')

        # this is done to provide coverage on the __str__ function
        print random_config

        enum_fake_scripts = [['script1'], ['script2']]
        ifcs_fake_scripts = [['script3'], ['script4']]
        shared_fake_scripts = [['script5'], ['script6']]

        enum_fake_names = ['name1', 'name2']
        ifcs_fake_names = ['name3', 'name4']
        shared_fake_names = ['name5', 'name6']

        self.assertItemsEqual(enum_json.scripts.values(), enum_fake_scripts)
        self.assertItemsEqual(ifcs_xml.scripts.values(), ifcs_fake_scripts)
        self.assertItemsEqual(shared_config.scripts.values(), shared_fake_scripts)
        self.assertEqual(random_config.scripts, {})

        self.assertItemsEqual(enum_json.scripts.keys(), enum_fake_names)
        self.assertItemsEqual(ifcs_xml.scripts.keys(), ifcs_fake_names)
        self.assertItemsEqual(shared_config.scripts.keys(), shared_fake_names)


class TestGetValidationScripts(unittest.TestCase):
    def test_get_json(self):
        """tests the get_json_validation returns the correct list of scripts
        where each script is a list"""
        # currently only one
        scscf_json = scscf_json_config_plugin.ScscfJson('path')
        answer = scscf_json.get_json_validation()
        scscsf_expected_script = [['/usr/share/clearwater/clearwater-config-manager/env/bin/python',
                                   '/usr/share/clearwater/clearwater-config-manager/scripts/validate_json.py',
                                   '/usr/share/clearwater/clearwater-config-manager/scripts/config_validation/scscf_schema.json',
                                   'path']]
        self.assertListEqual(answer.values(), scscsf_expected_script)

    def test_get_xml(self):
        """tests the get_xml_validation returns the correct list of scripts
        where each script is a list"""
        # currently only one
        fallback_ifcs = fallback_ifcs_config_plugin.FallbackIfcsXml('path')
        answer = fallback_ifcs.get_xml_validation()
        ifcs_expected_script = [['xmllint', '--format', '--pretty', '1',
                                 '--debug', '--schema',
                                 '/usr/share/clearwater/clearwater-config-manager/scripts/config_validation/fallback_ifcs_schema.xsd',
                                 'path', ]]
        self.assertListEqual(answer.values(), ifcs_expected_script)

class TestDiffType(unittest.TestCase):
    def test_unified_diff(self):
        """tests that the unified diff is used for json and xml files but not for others"""

        # Test one type of each config - json, xml and shared_config
        shared_config = shared_config_config_plugin.SharedConfig('path')
        scscf_json = scscf_json_config_plugin.ScscfJson('path')
        fallback_ifcs = fallback_ifcs_config_plugin.FallbackIfcsXml('path')

        answer = shared_config.use_unified_diff()
        self.assertIs(answer, False)

        answer = scscf_json.use_unified_diff()
        self.assertIs(answer, True)

        answer = fallback_ifcs.use_unified_diff()
        self.assertIs(answer, True)


# Once the technical debt in config_type_class_plugin.py has been addressed, so
# that RphJson does not need a custom validate() function, then these tests can
# be removed.
@mock.patch('clearwater_etcd_plugins.clearwater_config_access.rph_json_config_plugin.log')
@mock.patch('metaswitch.clearwater.config_manager.config_type_class_plugin.os.access')
@mock.patch('metaswitch.clearwater.config_manager.config_type_class_plugin.subprocess.check_call')
class TestRphValidation(unittest.TestCase):
    config_location = "/some/dir/rph.json"

    def test_rph_script_found_ok(self, mock_subprocess, mock_access, mock_log):
        """Check that we run the correct rph validation script."""
        rph_config = rph_json_config_plugin.RphJson(self.config_location)
        rph_config.validate()
        # One script should have been executed.
        self.assertEqual(len(mock_subprocess.call_args_list), 1)
        # We should be calling the custom rph config validation script here.
        self.assertEqual(
                mock.call(["python",
                           os.path.join(config_type_class_plugin.VALIDATION_SCRIPTS_FOLDER,
                                        "rph_validation.py"),
                           os.path.join(config_type_class_plugin.VALIDATION_SCRIPTS_FOLDER,
                                        "rph_schema.json"),
                           self.config_location], stderr=-2),
                mock_subprocess.call_args_list[0])

    def test_validate_fails(self, mock_subprocess, mock_access, mock_log):
        """Use RphJson.validate and get subprocess to raise a exception and
         check failed scripts is not empty."""
        rph_config = rph_json_config_plugin.RphJson(self.config_location)
        validation_error = subprocess.CalledProcessError('A', 'B')
        mock_subprocess.side_effect = [validation_error]
        answer = rph_config.validate()

        # The list of failed scripts should contain 'rph_validation.py', and the
        # list of passed scripts should be empty
        self.assertListEqual(answer[0], ['rph_validation.py'])
        self.assertListEqual(answer[1], [])
        self.assertIs(mock_subprocess.call_count, 1)


@mock.patch('metaswitch.clearwater.config_manager.config_type_class_plugin.os.access')
@mock.patch('metaswitch.clearwater.config_manager.config_type_class_plugin.os.listdir',
            return_value=["clearwater-core-validate-config", "other-script"])
@mock.patch('metaswitch.clearwater.config_manager.config_type_class_plugin.subprocess.check_call')
class TestSharedValidation(unittest.TestCase):
    config_location = "/some/dir/shared_config"

    def test_scripts_find_ok(self,
                             mock_subprocess,
                             mock_listdir,
                             mock_access):
        """Check that we run the validation scripts we find in the relevant
        folder."""

        shared_config = shared_config_config_plugin.SharedConfig(self.config_location)

        shared_config.validate()

        self.assertIs(mock_listdir.call_count, 1)
        # Each script should be executed.
        self.assertEqual(len(mock_subprocess.call_args_list), 2)
        # We should be calling the default config validation script here.
        self.assertEqual(
            mock.call([os.path.join(config_type_class_plugin.VALIDATION_SCRIPTS_FOLDER,
                                    "clearwater-core-validate-config"),
                       self.config_location], stderr=-2),
            mock_subprocess.call_args_list[0])

    def test_executable_only(self,
                             mock_subprocess,
                             mock_listdir,
                             mock_access):
        """Check that we only try to run those scripts that are executable."""

        # Make only one of the scripts executable.
        mock_access.side_effect = [True, False]

        shared_config = shared_config_config_plugin.SharedConfig(self.config_location)
        shared_config.validate()

        # Check that only the executable script is run.
        self.assertEqual(len(mock_subprocess.call_args_list), 1)
        self.assertEqual(
            mock.call([os.path.join(config_type_class_plugin.VALIDATION_SCRIPTS_FOLDER,
                                    "clearwater-core-validate-config"),
                       self.config_location], stderr=-2),
            mock_subprocess.call_args_list[0])


class TestConfigTypePluginLoader(unittest.TestCase):
    def test_load(self):
        """tests the plugin loader loads plug ins"""
        plugin_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   "plugins")
        plugins = config_type_plugin_loader.load_plugins_in_dir(plugin_path, None)
        # Check that the plugin loaded successfully
        self.assertEqual(plugins[0].__class__.__name__,
                         "PluginLoaderTestPlugin")
