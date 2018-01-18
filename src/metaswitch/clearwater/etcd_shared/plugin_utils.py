# Copyright (C) Metaswitch Networks 2017
# If license terms are provided to you in a COPYING file in the root directory
# of the source code repository by which you are accessing this code, then
# the license outlined in that COPYING file applies to your use.
# Otherwise no rights are granted except for those provided to you by
# Metaswitch Networks in a separate written agreement.


import tempfile
import os
from os.path import dirname
import subprocess
import logging

_log = logging.getLogger("etcd_shared.plugin_utils")


def run_commands(list_of_command_args, namespace=None, log_error=True):
    """Runs the given shell command, logging the output and return code.

    If a namespace is supplied the command is run in the specified namespace.

    Note that this runs the provided array of command arguments in a subprocess
    call without shell, to avoid shell injection. Ensure the command is passed 
    in as an array instead of a string.
    """
    processes = []
    error_returncodes = []
    for command_args in list_of_command_args:
        if namespace:
            command_args[0:0] = ['ip', 'netns', 'exec', namespace]

        # Pass the close_fds argument to avoid the pidfile lock being held by
        # child processes
        p = subprocess.Popen(command_args,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             close_fds=True)
        processes.append(p)

    for p in processes:
        stdout, stderr = p.communicate()
        if p.returncode != 0:
            # it failed, log the return code and output
            if log_error:
                _log.error("Command {} failed with return code {}, "
                           "stdout {!r}, and stderr {!r}".format(' '.join(command_args),
                                                                 p.returncode,
                                                                 stdout,
                                                                 stderr))
            error_returncodes.append(p.returncode)
        else:
            # it succeeded, log out stderr of the command run if present
            if stderr:
                _log.warning("Command {} succeeded, with stderr output {!r}".
                             format(' '.join(command_args), stderr))
            else:
                _log.debug("Command {} succeeded".format(' '.join(command_args)))

    if error_returncodes:
        return error_returncodes[0]
    else:
        return 0


def run_command(command_args, namespace=None, log_error=True):
    return run_commands([command_args], namespace=namespace, log_error=log_error)


def safely_write(filename, contents, permissions=0644):
    """Writes a file without race conditions, by writing to a temporary file
    and then atomically renaming it"""

    # Create the temporary file in the same directory (to ensure it's on the
    # same filesystem and can be moved atomically), and don't automatically
    # delete it on close (os.rename deletes it).
    tmp = tempfile.NamedTemporaryFile(dir=dirname(filename), delete=False)

    tmp.write(contents.encode("utf-8"))

    os.chmod(tmp.name, permissions)

    os.rename(tmp.name, filename)
