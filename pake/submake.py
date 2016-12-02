# Copyright (c) 2016, Teriks
# All rights reserved.
#
# pake is distributed under the following BSD 3-Clause License
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


import os
import subprocess
import sys


class SubMakeException(Exception):
    """A blanket exception raised when any error occurs during the actual execution
    of another pakefile while calling :py:meth:`pake.submake.run_script`.
    """
    pass


def _execute(cmd):
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    stdout = []
    for stdout_line in iter(popen.stdout.readline, ""):
        stdout.append(stdout_line)
        yield stdout_line

    stderr = []
    for stderr_line in iter(popen.stderr.readline, ""):
        stderr.append(stderr_line)

    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        output = ''.join(stderr) + ''.join(stdout)
        raise subprocess.CalledProcessError(return_code, cmd, output=output)


_exports = {}


def _exports_to_args():
    args = []
    for k, v in _exports.items():
        args.append("-D")
        args.append(k+"="+str(v))
    return args


def export(name, value):
    """Export a define which will be passed to sub script invocations when calling :py:func:`pake.submake.run_script`

    :param name: The name of the define.
    :type name: str
    :param value: The define value, which can be a int, float, bool, string, list, set, dictionary or tuple
                  (Basically any type that can be expressed as a literal).  Composite literals like lists, tuples (etc..)
                  must consist only of simple literal values (not variable references of any kind).
    """
    _exports[name] = value


def un_export(name):
    """Prevent a previously exported value from being exported during new invocations of :py:func:`pake.submake.run_script`.

    :param name: The name of the previously exported define.
    :type name: str
    """
    if name in _exports:
        del _exports[name]


def run_script(script_path, *args):
    """Run another pakefile.py programmatically, changing directories if required

    :param script_path: The path to the pakefile that is going to be ran.
    :param args: Command line arguments to pass the pakefile.

    :raises FileNotFoundError: Raised if the given pakefile script does not exist.
    :raises pake.submake.SubMakeException: Raised if the submake script exits in a non successful manner.
    """

    if os.path.exists(script_path):
        if not os.path.isfile(script_path):
            raise FileNotFoundError('"{script_path}" is not a file.'
                                    .format(script_path=script_path))
    else:
        raise FileNotFoundError('"{script_path}" does not exist.'
                                .format(script_path=script_path))

    try:

        str_filter_args = list(str(a) for a in args)
        work_dir = os.path.dirname(os.path.abspath(script_path))
        output = _execute([sys.executable, script_path, "-C", work_dir] + _exports_to_args() + str_filter_args)
        for line in output:
            sys.stdout.write(line)
    except subprocess.CalledProcessError as err:
        raise SubMakeException(err.output)
