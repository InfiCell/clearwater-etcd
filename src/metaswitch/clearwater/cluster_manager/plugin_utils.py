# Project Clearwater - IMS in the Cloud
# Copyright (C) 2015 Metaswitch Networks Ltd
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version, along with the "Special Exception" for use of
# the program along with SSL, set forth below. This program is distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details. You should have received a copy of the GNU General Public
# License along with this program.  If not, see
# <http://www.gnu.org/licenses/>.
#
# The author can be reached by email at clearwater@metaswitch.com or by
# post at Metaswitch Networks Ltd, 100 Church St, Enfield EN2 6BQ, UK
#
# Special Exception
# Metaswitch Networks Ltd  grants you permission to copy, modify,
# propagate, and distribute a work formed by combining OpenSSL with The
# Software, or a work derivative of such a combination, even if such
# copying, modification, propagation, or distribution would otherwise
# violate the terms of the GPL. You must comply with the GPL in all
# respects for all of the code used other than OpenSSL.
# "OpenSSL" means OpenSSL toolkit software distributed by the OpenSSL
# Project and licensed under the OpenSSL Licenses, or a work based on such
# software and licensed under the OpenSSL Licenses.
# "OpenSSL Licenses" means the OpenSSL License and Original SSLeay License
# under which the OpenSSL Project distributes the OpenSSL toolkit software,
# as those licenses appear in the file LICENSE-OPENSSL.


import logging
import os
import socket
import time
import yaml
from textwrap import dedent
import subprocess
from metaswitch.clearwater.cluster_manager import constants

_log = logging.getLogger("cluster_manager.plugin_utils")


def write_memcached_cluster_settings(filename, cluster_view):
    """Writes out the memcached cluster_settings file"""
    valid_servers_states = [constants.LEAVING_ACKNOWLEDGED_CHANGE,
                            constants.LEAVING_CONFIG_CHANGED,
                            constants.NORMAL_ACKNOWLEDGED_CHANGE,
                            constants.NORMAL_CONFIG_CHANGED,
                            constants.NORMAL]
    valid_new_servers_states = [constants.NORMAL,
                                constants.NORMAL_ACKNOWLEDGED_CHANGE,
                                constants.NORMAL_CONFIG_CHANGED,
                                constants.JOINING_ACKNOWLEDGED_CHANGE,
                                constants.JOINING_CONFIG_CHANGED]
    servers_ips = sorted(["{}:11211".format(k)
                          for k, v in cluster_view.iteritems()
                          if v in valid_servers_states])

    new_servers_ips = sorted(["{}:11211".format(k)
                              for k, v in cluster_view.iteritems()
                              if v in valid_new_servers_states])

    new_file_contents = ""
    if new_servers_ips == servers_ips:
        new_file_contents = "servers={}\n".format(",".join(servers_ips))
    else:
        new_file_contents = "servers={}\nnew_servers={}\n".format(
            ",".join(servers_ips),
            ",".join(new_servers_ips))

    _log.debug("Writing out cluster_settings file '{}'".format(
        new_file_contents))
    with open(filename, "w") as f:
        f.write(new_file_contents)


def run_command(command):
    """Runs the given shell command, logging the output and return code"""
    try:
        output = subprocess.check_output(command,
                                         shell=True,
                                         stderr=subprocess.STDOUT)
        _log.info("Command {} succeeded and printed output {!r}".
                  format(command, output))
        return 0
    except subprocess.CalledProcessError as e:
        _log.error("Command {} failed with return code {}"
                   " and printed output {!r}".format(command,
                                                     e.returncode,
                                                     e.output))
        return e.returncode


# Edits cassandra.yaml and restarts Cassandra in order to join a Cassandra
# cluster. If there is an existing Cassandra cluster formed, we use the nodes in
# that cluster as the seeds; otherwise, we use the all the joining nodes as the
# seeds._
def join_cassandra_cluster(cluster_view, cassandra_yaml_file, ip):
    seeds_list = []

    for seed, state in cluster_view.items():
        if (state == constants.NORMAL_ACKNOWLEDGED_CHANGE or
            state == constants.NORMAL_CONFIG_CHANGED):
            seeds_list.append(seed)

    if len(seeds_list) == 0:
        for seed, state in cluster_view.items():
            if (state == constants.JOINING_ACKNOWLEDGED_CHANGE or
                state == constants.JOINING_CONFIG_CHANGED):
                seeds_list.append(seed)

    if len(seeds_list) > 0:
        seeds_list_str = ','.join(map(str, seeds_list))
        _log.info("Cassandra seeds list is {}".format(seeds_list_str))

        # Read cassandra.yaml.
        with open(cassandra_yaml_file) as f:
            doc = yaml.load(f)

        # Fill in the correct listen_address and seeds values in the yaml
        # document.
        doc["listen_address"] = ip
        doc["seed_provider"][0]["parameters"][0]["seeds"] = seeds_list_str

        # Write back to cassandra.yaml.
        with open(cassandra_yaml_file, "w") as f:
            yaml.dump(doc, f)

        # Restart Cassandra and make sure it picks up the new list of seeds.
        _log.debug("Restarting Cassandra")
        run_command("monit unmonitor cassandra")
        run_command("service cassandra stop")
        run_command("rm -rf /var/lib/cassandra/")
        run_command("mkdir -m 755 /var/lib/cassandra")
        run_command("chown -R cassandra /var/lib/cassandra")

        start_cassandra()

        _log.debug("Cassandra node successfully clustered")

    else:
        # Something has gone wrong - the local node should be WAITING_TO_JOIN in
        # etcd (at the very least).
        _log.warning("No Cassandra cluster defined in etcd - unable to join")


def leave_cassandra_cluster():
    # We need Cassandra to be running so that we can connect on port 9160 and
    # decommission it. Check if we can connect on port 9160.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("localhost", 9160))
    except:
        start_cassandra()

    os.system("nodetool decomission")
    _log.debug("Cassandra node successfully decommissioned")


def start_cassandra():
    os.system("service cassandra start")

    # Wait until we can connect on port 9160 - i.e. Cassandra is running.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            s.connect(("localhost", 9160))
            break
        except:
            time.sleep(1)


def write_chronos_cluster_settings(filename, cluster_view, current_server):
    current_or_joining = [constants.JOINING_ACKNOWLEDGED_CHANGE,
                          constants.JOINING_CONFIG_CHANGED,
                          constants.NORMAL_ACKNOWLEDGED_CHANGE,
                          constants.NORMAL_CONFIG_CHANGED,
                          constants.NORMAL]
    leaving = [constants.LEAVING_ACKNOWLEDGED_CHANGE,
               constants.LEAVING_CONFIG_CHANGED]

    staying_servers = ([k for k, v in cluster_view.iteritems()
                        if v in current_or_joining])
    leaving_servers = ([k for k, v in cluster_view.iteritems()
                        if v in leaving])

    with open(filename, 'w') as f:
        f.write(dedent('''\
        [cluster]
        localhost = {}
        ''').format(current_server))
        for node in staying_servers:
            f.write('node = {}\n'.format(node))
        for node in leaving_servers:
            f.write('leaving = {}\n'.format(node))
