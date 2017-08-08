#!/usr/bin/env python

# Copyright (C) Metaswitch Networks 2017
# If license terms are provided to you in a COPYING file in the root directory
# of the source code repository by which you are accessing this code, then
# the license outlined in that COPYING file applies to your use.
# Otherwise no rights are granted except for those provided to you by
# Metaswitch Networks in a separate written agreement.

"""Clearwater Cluster Manager

Usage:
  main.py --mgmt-local-ip=IP --sig-local-ip=IP --local-site=NAME --uuid=UUID (--etcd-key=KEY | --db-key=KEY) (--etcd-cluster-key=CLUSTER_KEY | --db-cluster-key=CLUSTER_KEY)
          [--remote-site=NAME] [--remote-cassandra-seeds=IPs] [--cassandra-container-id=ID] [--signaling-namespace=NAME] [--foreground] [--log-level=LVL]
          [--log-directory=DIR] [--pidfile=FILE] [--cluster-manager-enabled=Y/N] [--etcd | --consul]

Options:
  -h --help                      Show this screen.
  --mgmt-local-ip=IP             Management IP address (for the back-end)
  --sig-local-ip=IP              Signaling IP address (must be unique for each node in the cluster)
  --local-site=NAME              Name of local site
  --uuid=UUID                    UUID uniquely identifying this node
  --etcd-key=KEY                 Etcd key (top level)
  --db-key=KEY                   Top-level key in back-end database
  --etcd-cluster-key=CLUSTER_KEY Etcd key (used in the data store clusters)
  --db-cluster-key=CLUSTER_KEY   Back-end database key (used in the data store clusters)
  --remote-site=NAME             Name of remote site
  --remote-cassandra-seeds=IPs   Comma separated list of at least one IP address from each remote Cassandra site
  --cassandra-container-id=ID    When containerised, the ID of the local Cassandra container
  --signaling-namespace=NAME     Name of the signaling namespace
  --foreground                   Don't daemonise
  --log-level=LVL                Level to log at, 0-4 [default: 3]
  --log-directory=DIR            Directory to log to [default: ./]
  --pidfile=FILE                 Pidfile to write [default: ./cluster-manager.pid]
  --cluster-manager-enabled=Y/N  Whether the cluster manager should start any threads [default: Yes]
  --etcd                         Use the etcd back-end (the default)
  --consul                       Use the Consul back-end

"""

from docopt import docopt, DocoptExit

from metaswitch.common import logging_config, utils
from metaswitch.clearwater.etcd_shared.plugin_loader import load_plugins_in_dir
from metaswitch.clearwater.cluster_manager.consul_synchronizer import ConsulSynchronizer
from metaswitch.clearwater.cluster_manager.etcd_synchronizer import EtcdSynchronizer
from metaswitch.clearwater.cluster_manager.plugin_base import PluginParams
from metaswitch.clearwater.cluster_manager import pdlogs
import logging
import os
import prctl
import sys
import syslog
from threading import activeCount
from time import gmtime, sleep
import signal
from uuid import UUID

_log = logging.getLogger("cluster_manager.main")

LOG_LEVELS = {'0': logging.ERROR,
              '1': logging.WARNING,
              # INFO-level logging is really useful, and not very spammy because
              # we're not on the call path, so produce INFO logs even at level 2
              '2': logging.INFO,
              '3': logging.INFO,
              '4': logging.DEBUG}

should_quit = False

def install_sigquit_handler(plugins):
    def sigquit_handler(sig, stack):
        global should_quit
        _log.info("Handling SIGQUIT")
        for plugin in plugins:
            _log.info("{} leaving cluster".format(plugin))
            plugin.leave_cluster()
        should_quit = True
    signal.signal(signal.SIGQUIT, sigquit_handler)

def main(args):
    syslog.openlog("cluster-manager", syslog.LOG_PID)
    pdlogs.STARTUP.log()
    try:
        arguments = docopt(__doc__, argv=args)
    except DocoptExit:
        pdlogs.EXITING_BAD_CONFIG.log()
        raise

    mgmt_ip = arguments['--mgmt-local-ip']
    sig_ip = arguments['--sig-local-ip']
    local_site_name = arguments['--local-site']
    remote_site_name = arguments.get('--remote-site')
    remote_cassandra_seeds = arguments.get('--remote-cassandra-seeds')
    if remote_cassandra_seeds:
        remote_cassandra_seeds = remote_cassandra_seeds.split(',')
    else:
        remote_cassandra_seeds = []
    cassandra_container_id = arguments.get('--cassandra-container-id')
    signaling_namespace = arguments.get('--signaling-namespace')
    local_uuid = UUID(arguments['--uuid'])
    etcd_key = arguments.get('--etcd-key') or arguments.get('--db-key')
    etcd_cluster_key = arguments.get('--etcd-cluster-key') or arguments.get('--db-cluster-key')
    cluster_manager_enabled = arguments['--cluster-manager-enabled']
    log_dir = arguments['--log-directory']
    log_level = LOG_LEVELS.get(arguments['--log-level'], logging.DEBUG)
    if arguments.get('--consul'):
        backend = "consul"
    else:
        backend = "etcd"
    foreground = arguments['--foreground']

    stdout_err_log = os.path.join(log_dir, "cluster-manager.output.log")

    # Check that there's an etcd_cluster_key value passed to the cluster
    # manager
    if etcd_cluster_key == "":
        # The etcd_cluster_key isn't valid, and possibly get weird entries in
        # the etcd database if we allow the cluster_manager to start
        pdlogs.EXITING_MISSING_ETCD_CLUSTER_KEY.log()
        exit(1)

    if not foreground:
        utils.daemonize(stdout_err_log)

    # Process names are limited to 15 characters, so abbreviate
    prctl.prctl(prctl.NAME, "cw-cluster-mgr")

    logging_config.configure_logging(log_level, log_dir, "cluster-manager", show_thread=True)

    if foreground:
        # In foreground mode, write logs to stdout as well
        root_log = logging.getLogger()
        fmt = logging_config.THREAD_FORMAT
        fmt.converter = gmtime
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(fmt)
        handler.setLevel(log_level)
        root_log.addHandler(handler)

    # urllib3 logs a WARNING log whenever it recreates a connection, but our
    # etcd usage does this frequently (to allow watch timeouts), so deliberately
    # ignore this log
    urllib_logger = logging.getLogger('urllib3')
    urllib_logger.setLevel(logging.ERROR)

    utils.install_sigusr1_handler("cluster-manager")

    # Drop a pidfile. We must keep a reference to the file object here, as this keeps
    # the file locked and provides extra protection against two processes running at
    # once.
    pidfile_lock = None
    try:
        pidfile_lock = utils.lock_and_write_pid_file(arguments['--pidfile']) # noqa
    except IOError:
        # We failed to take the lock - another process is already running
        exit(1)

    plugins_dir = "/usr/share/clearwater/clearwater-cluster-manager/plugins/"
    plugins = load_plugins_in_dir(plugins_dir,
                                  PluginParams(ip=sig_ip,
                                               mgmt_ip=mgmt_ip,
                                               local_site=local_site_name,
                                               remote_site=remote_site_name,
                                               remote_cassandra_seeds=remote_cassandra_seeds,
                                               signaling_namespace=signaling_namespace,
                                               uuid=local_uuid,
                                               etcd_key=etcd_key,
                                               etcd_cluster_key=etcd_cluster_key,
                                               cassandra_container_id=cassandra_container_id))
    plugins.sort(key=lambda x: x.key())
    plugins_to_use = []
    files = []
    skip = False
    for plugin in plugins:
        for plugin_file in plugin.files():
            if plugin_file in files:
                _log.info("Skipping plugin {} because {} "
                          "is already managed by another plugin"
                          .format(plugin, plugin_file))
                skip = True

        if not skip:
            plugins_to_use.append(plugin)
            files.extend(plugin.files())

    synchronizers = []
    threads = []

    if cluster_manager_enabled == "N":
        # Don't start any threads as we don't want the cluster manager to run
        pdlogs.DO_NOT_START.log()
    elif etcd_cluster_key == "DO_NOT_CLUSTER":
        # Don't start any threads as we don't want this box to cluster
        pdlogs.DO_NOT_CLUSTER.log()
    else:
        # Load the plugins, but don't start them until we've installed the
        # SIGTERM handler, as that handler will gracefully shut down any
        # remaining synchronizers on receiving a SIGTERM
        for plugin in plugins_to_use:
            if backend == "etcd":
                syncer = EtcdSynchronizer(plugin, sig_ip, etcd_ip=mgmt_ip)
            else:
                syncer = ConsulSynchronizer(plugin, sig_ip, db_ip=mgmt_ip)

            synchronizers.append(syncer)
            threads.append(syncer.thread)
            _log.info("Loaded plugin %s" % plugin)


    install_sigquit_handler(synchronizers)
    utils.install_sigterm_handler(synchronizers)

    # If we have any plugins, start their threads now
    for syncer in synchronizers:
        syncer.start_thread()
        _log.info("Started thread for plugin %s" % syncer._plugin)

    while any([thread.isAlive() for thread in threads]):
        for thread in threads:
            if thread.isAlive():
                thread.join(1)

    _log.info("No plugin threads running, waiting for a SIGTERM or SIGQUIT")
    while not utils.should_quit and not should_quit:
        sleep(1)
    _log.info("Quitting")
    _log.debug("%d threads outstanding at exit" % activeCount())
    pdlogs.EXITING.log()
    syslog.closelog()
