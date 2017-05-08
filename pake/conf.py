# Copyright (c) 2017, Teriks
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


"""
Global configuration module.

.. py:attribute:: pake.conf.stdout

    (set-able) Default file object used by pake library calls to print informational output, defaults to **sys.stdout**
    
    This can be set in order to change the default informational output location for the whole library.

.. py:attribute:: pake.conf.stderr

    (set-able) Default file object used by pake library calls to print error output, defaults to **sys.stderr**.
    
    This can be set in order to change the default error output location for the whole library.
"""

import sys

stderr = sys.stderr
stdout = sys.stdout

_init_file = None
_init_dir = None


def get_init_file():
    """Gets the full path to the file :py:meth:`pake.init` was called in.
    
    Returns **None** if :py:meth:`pake.init` has not been called.
    
    :return: Full path to pakes entrypoint file, or **None** 
    """
    return _init_file


def get_init_dir():
    """Gets the full path to the directory pake started running in.
    
    If pake preformed any directory changes, this returns the working path before that happened.
    
    Returns **None** if :py:meth:`pake.init` has not been called.
    
    the directory changes occurred.
    
    :return: Full path to init dir, or **None**
    """

    return _init_dir


def _i_set_init_dir(dir_path):
    global _init_dir
    _init_dir = dir_path


def _i_set_init_file(file_path):
    global _init_file
    _init_file = file_path

