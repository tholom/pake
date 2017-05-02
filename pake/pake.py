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

import inspect
import shlex
import subprocess
import sys
import tempfile
from functools import wraps
from glob import glob as file_glob

import os
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from os import path

import pake
from .graph import Graph
from .util import is_iterable_not_str, get_task_arg_name, flatten_non_str


class UndefinedTaskException(Exception):
    """Raised on attempted lookup/usage of an unregistered task function or task name.
    
    :ivar task_name: The name of the referenced task.
    """

    def __init__(self, task_name):
        super(UndefinedTaskException, self).__init__('Task "{}" is undefined.'.format(task_name))
        self.task_name = task_name


class RedefinedTaskException(Exception):
    """Raised on registering a duplicate task.
    
    :ivar task_name: The name of the redefined task.
    """

    def __init__(self, task_name):
        super(RedefinedTaskException, self).__init__('Task "{}" has already been defined.'
                                                     .format(task_name))
        self.task_name = task_name


class TaskContext:
    """Contextual object passed to each task.
    
       :ivar inputs: All file inputs, or an empty list
       :ivar outputs: All file outputs, or an empty list
       
       :ivar outdated_inputs: All changed file inputs (or inputs who's corresponding output is missing), or an empty list
       :ivar outdated_outputs: All out of date file outputs, or an empty list
    """

    def __init__(self, pake, node):
        self._pake = pake
        self._node = node
        self._future = None
        self._io = None
        self.inputs = []
        self.outputs = []
        self.outdated_inputs = []
        self.outdated_outputs = []

    @property
    def func(self):
        """Task function reference."""
        return self.node.func

    @property
    def name(self):
        """Task name."""
        return self._node.name

    @property
    def io(self):
        """Task IO file stream, a file like object that is only open for writing during a tasks execution.
        
        Any output to be displayed for the task should be written to this file object.
        """
        return self._io

    def print(self, *args, **kwargs):
        """Prints to the task IO file stream using the builtin print function."""
        kwargs.pop('file', None)
        print(*args, **kwargs, file=self._io)

    def subpake(self, script, *args, silent=False):
        """Run :py:func:`pake.subpake` and direct all output to the task IO file stream."""

        pake.subpake(script, *args, stdout=self._io, silent=silent)

    def call(self, *args, stdin=None, shell=False, ignore_errors=False, silent=False, print_cmd=True):
        """Calls a sub process, all output is written to the task IO file stream.
        
        Example:
        
        .. code-block:: python
           
           # strings are parsed using shlex.parse
           
           ctx.call('gcc -c test.c -o test.o')
           
           ctx.call('gcc -c {} -o {}'.format('test.c', 'test.o'))
           
           # pass the same command as a list
           
           ctx.call(['gcc', '-c', 'test.c', '-o', 'test.o'])
           
           # pass the same command using the variadic argument *args
           
           ctx.call('gcc', '-c', 'test.c', '-o', 'test.o')
           
        
        When *ignore_errors* is False, :py:func:`subprocess.check_call` is used to execute the process.
        
        When *ignore_errors* is True, :py:func:`subprocess.call` is used to execute the process.
        
        
        :param args: Process and arguments.
        :param stdin: Set the stdin of the process.
        :param shell: Whether or not to use the system shell for execution.
        :param ignore_errors: Whether or not to raise a :py:class:`subprocess.CalledProcessError` on non 0 exit codes.
        :param silent: Whether or not to silence all output from the command.
        :param print_cmd: Whether or not to print the executed command line to the tasks output.
        
        :raises subprocess.CalledProcessError if *ignore_errors* is *False* and the process exits with a non 0 exit code.
        
        :return: The process exit code.
        """
        self._io.flush()
        if len(args) == 1:
            if is_iterable_not_str(args[0]):
                args = [str(i) for i in args[0]]
            elif type(args[0]) is str:
                args = shlex.split(args[0])
        else:
            args = [str(i) for i in args]

        call = subprocess.call if ignore_errors else subprocess.check_call

        if print_cmd:
            self.print(' '.join(list(args)))

        if silent:
            stdout = subprocess.DEVNULL
        else:
            stdout = self._io
            stdout.flush()

        return call(list(args),
                    stdout=stdout, stderr=subprocess.STDOUT,
                    stdin=stdin, shell=shell)

    @property
    def dependencies(self):
        """Dependencies of this task, iterable of :py:class:`Pake.TaskGraph`"""
        return self._node.edges

    @property
    def dependency_outputs(self):
        """Returns a list of output files generated by the tasks immediate dependencies."""

        return list(flatten_non_str(
            self.pake.get_task_context(i.func).outputs for i in self.dependencies)
        )

    def _i_io_open(self):
        self._io = tempfile.TemporaryFile(mode='w+')

    def _i_io_close(self):
        self._io.seek(0)
        self.pake.stdout.write(self._io.read())
        self._io.close()

    def _i_submit_self(self, thread_pool):
        futures = [self.pake.get_task_context(i.name)._future for i in self.node.edges]

        # Wait dependents
        futures_wait(futures)

        # Raise pending exceptions
        for err in (i.exception() for i in futures):
            if err:
                raise err

        # Submit self
        self._future = thread_pool.submit(self.node.func)

    @property
    def node(self):
        """The :py:class:`pake.TaskGraph` node for the task."""
        return self._node

    @property
    def pake(self):
        """The :py:class:`pake.Pake` instance the task is registered to."""
        return self._pake


class TaskGraph(Graph):
    """Task graph node.
    
       :ivar func: The task function associated with the node
    """

    def __init__(self, name, func):
        self._name = name
        self.func = func
        super(TaskGraph, self).__init__()

    def __call__(self, *args, **kwargs):
        self.func(*args, **kwargs)

    @property
    def name(self):
        """The task name."""
        return self._name

    def __str__(self):
        return self._name


class _OutPattern:
    def __init__(self, file_pattern):
        self._pattern = file_pattern

    def _do_template(self, i):
        name = os.path.splitext(os.path.basename(i))[0]
        return self._pattern.replace('%', name)

    def __call__(self, inputs):
        for i in inputs:
            yield self._do_template(i)


class _Glob:
    def __init__(self, expression):
        self._expression = expression

    def __call__(self):
        return file_glob(self._expression)


def glob(expression):
    """Deferred file input glob,  the glob is not executed until the task executes.
       
    Collects files for input with a unix style glob expression.
    
    Example:
           
    .. code-block:: python
    
       @pk.task(build_c, i=pake.glob('obj/*.o'), o='main')
       def build_exe(ctx):
           ctx.call(['gcc'] + ctx.inputs + ['-o'] + ctx.outputs)
           
       @pk.task(build_c, i=[pake.glob('obj_a/*.o'), pake.glob('obj_b/*.o')], o='main')
       def build_exe(ctx):
           ctx.call(['gcc'] + ctx.inputs + ['-o'] + ctx.outputs)
           
    pake.glob returns a function similar to this:
    
    .. code-block:: python
    
       def input_generator():
           return glob.glob(expression)
    """

    def input_generator():
        return file_glob(expression)

    return input_generator


def pattern(file_pattern):
    """Produce a substitution pattern that can be used in place of an output file.
    
    The % character represents the file name, while {dir} and {ext} represent the directory of 
    the input file, and the input file extension.
    
    Example:
    
    .. code-block:: python
    
        @pk.task(i=pake.glob('src/*.c'), o=pake.pattern('obj/%.o'))
        def build_c(ctx):
            for i, o in zip(ctx.outdated_inputs, ctx.outdated_outputs):
                ctx.call(['gcc', '-c', i, '-o', o])
                
        @pk.task(i=[pake.glob('src_a/*.c'), pake.glob('src_b/*.c')], o=pake.pattern('{dir}/%.o'))
        def build_c(ctx):
            for i, o in zip(ctx.outdated_inputs, ctx.outdated_outputs):
                ctx.call(['gcc', '-c', i, '-o', o])
                
                
    pake.pattern returns function similar to this:
    
    .. code-block:: python
    
       def output_generator(inputs):
           for inp in inputs:
               dir = os.path.dirname(inp)
               name, ext = os.path.splitext(os.path.basename(inp))
               yield file_pattern.replace('{dir}', dir).replace('%', name).replace('{ext}', ext)
    
    """

    def output_generator(inputs):
        for inp in inputs:
            dir = os.path.dirname(inp)
            name, ext = os.path.splitext(os.path.basename(inp))
            yield file_pattern.replace('{dir}', dir).replace('%', name).replace('{ext}', ext)

    return output_generator


class Pake:
    """
    Pake's main instance.
    
    :ivar stdout: The stream all standard task output gets written to (set-able)
    :ivar stderr: The stream all errors and exceptions get written to (set-able)
    """

    def __init__(self, stdout=None, stderr=None):
        """
        Create a pake object, optionally set stdout and stderr for the instance.
        
        :param stdout: The stream all standard task output gets written to. (defaults to sys.stdout)
        :param stderr: The stream all errors and exceptions get written to. (defaults to sys.stderr)
        """

        self._graph = TaskGraph("_", lambda: None)
        self._task_contexts = dict()
        self._defines = dict()
        self._dry_run_mode = False
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stderr = stderr if stderr is not None else sys.stderr

    def set_define(self, name, value):
        """
        Set a defined value.
        
        :param name: The name of the define.
        :param value: The value of the define.
        """
        self._defines[name] = value

    def __getitem__(self, item):
        """
        Access a define using the indexing operator []
        
        :param item: Name of the define.
        :return: The defines value, or *None*
        """
        return self.get_define(item)

    def get_define(self, name, default=None):
        """Get a defined value.
           
        This is used to get defines off the command line, as well as retrieve
        values exported from top level pake scripts.
        
        :param name: Name of the define
        :param default: The default value to return if the define does not exist
        :return: The defines value as a python literal corresponding to the defines type.
        """
        return self._defines.get(name, default)

    @property
    def task_contexts(self):
        """
        Retrieve the task context objects for all registered tasks.
        
        :return: List of :py:class:`pake.TaskContext`. 
        """
        return self._task_contexts.values()

    @staticmethod
    def _process_i_o_params(i, o):
        if i is None:
            i = []
        if o is None:
            o = []

        if callable(i):
            i = list(i())
        elif type(i) is str or not is_iterable_not_str(i):
            i = [i]

        for idx, inp in enumerate(i):
            if callable(inp):
                i[idx] = inp()

        i = list(flatten_non_str(i))

        if callable(o):
            o = list(o(i))
        elif type(o) is str or not is_iterable_not_str(o):
            o = [o]

        for idx, outp in enumerate(i):
            if callable(outp):
                o[idx] = outp(i)

        o = list(flatten_non_str(o))

        return i, o

    @staticmethod
    def _change_detect(i, o):
        len_i = len(i)
        len_o = len(o)

        if len_i > 0 and len_o == 0:
            raise ValueError('Must have > 0 outputs when specifying input files for change detection.')

        outdated_inputs = []
        outdated_outputs = []

        if len_i == 0 and len_o == 0:
            return [], []

        if len_o > 1:
            if len_i == 0:
                for op in o:
                    if not path.isfile(op):
                        outdated_outputs.append(op)

            elif len_o != len_i:
                output_set = set()
                input_set = set()

                for ip in i:
                    if not path.isfile(ip):
                        raise FileNotFoundError('Input file "{}" does not exist.'.format(i))
                    for op in o:
                        if not path.isfile(op) or path.getmtime(op) < path.getmtime(ip):
                            input_set.add(ip)
                            output_set.add(op)

                outdated_inputs += input_set
                outdated_outputs += output_set

            else:
                for iopair in zip(i, o):
                    ip, op = iopair[0], iopair[1]

                    if not path.isfile(ip):
                        raise FileNotFoundError('Input file "{}" does not exist.'.format(ip))
                    if not path.isfile(op) or path.getmtime(op) < path.getmtime(ip):
                        outdated_inputs.append(ip)
                        outdated_outputs.append(op)

        else:
            op = o[0]
            if not path.isfile(op):
                outdated_outputs.append(op)
                outdated_inputs += i
                return outdated_inputs, outdated_outputs

            outdated_output = None
            for ip in i:
                if not path.isfile(ip):
                    raise FileNotFoundError('Input file "{}" does not exist.'.format(i))
                if path.getmtime(op) < path.getmtime(ip):
                    outdated_inputs.append(ip)
                    outdated_output = op

            if outdated_output:
                outdated_outputs.append(outdated_output)

        return outdated_inputs, outdated_outputs

    def task(self, *args, i=None, o=None):
        """
        Decorator for registering pake tasks.
        
        Any input files specified must be accompanied by at least one output file.
        
        
        A callable object, or list of callable objects may be passed to **i** or **o** in addition to
        a raw file name or names.  This is how **pake.glob** and **pake.pattern** work.
        
        Input/Output Generation Example:
        
        .. code-block:: python
        
           def gen_inputs(pattern):
               def input_generator():
                   return glob.glob(pattern)
               return input_generator
               
           def gen_output(pattern):
               def output_generator(inputs):
                   for inp in inputs:
                       dir = os.path.dirname(inp)
                       name, ext = os.path.splitext(os.path.basename(inp))
                       yield pattern.replace('{dir}', dir).replace('%', name).replace('{ext}', ext)
               return output_generator
           
           @pk.task(i=gen_inputs('*.c'), o=gen_outputs('%.o'))
           def my_task(ctx):
               # Do your build task here
               pass
               
           
           @pk.task(i=[gen_inputs('src_a/*.c'), gen_inputs('src_b/*.c'), o=gen_outputs('{dir}/%.o')]
           def my_task(ctx):
               # Do your build task here
               pass
        
        Dependencies Only Example:
        
        .. code-block:: python
           
           @pk.task(dependent_task_a, dependent_task_b)
           def my_task(ctx):
               # Do your build task here
               pass
               
        Change Detection Examples:
        
        .. code-block:: python
        
           @pk.task(dependent_task_a, dependent_task_b, i='main.c', o='main')
           def my_task(ctx):
               # Do your build task here
               pass
               
           @pk.task(i='main.c', o='main')
           def my_task(ctx):
               # Do your build task here
               pass
               
           @pk.task(i=['otherstuff.c', 'main.c'], o='main')
           def my_task(ctx):
               # Do your build task here
               pass
               
           @pk.task(i=pake.glob('src/*.c', o='main')
           def my_task(ctx):
               # Do your build task here
               pass
               
           @pk.task(i=['file_b.c', 'file_b.c'], o=['file_b.o', 'file_b.o'])
           def my_task(ctx):
               # Do your build task here
               pass
               
           # Similar to the above, inputs and outputs end up being of the same
           # length when using pake.glob with pake.pattern
           @pk.task(i=pake.glob('src/*.c'), o=pake.pattern('obj/%.o'))
           def my_task(ctx):
               # Do your build task here
               pass
        
        :raises: :py:class:`pake.UndefinedTaskException` if a given dependency is not a registered task function.
        :param args: Tasks which this task depends on.
        :param i: Optional input files for change detection.
        :param o: Optional output files for change detection.
        """

        if len(args) == 1 and inspect.isfunction(args[0]):
            if args[0].__name__ not in self._task_contexts:
                func = args[0]
                self._add_task(func.__name__, func)
                return func

        if len(args) > 1 and is_iterable_not_str(args[0]):
            dependencies = args[0]
        else:
            dependencies = args

        def outer(func):
            inputs, outputs = i, o

            ctx = self._add_task(func.__name__, func, dependencies)

            ctx_func = ctx.node.func

            @wraps(ctx_func)
            def inner(*args, **kwargs):
                i, o = Pake._process_i_o_params(inputs, outputs)
                outdated_inputs, outdated_outputs = Pake._change_detect(i, o)

                ctx.inputs = list(i)
                ctx.outputs = list(o)
                ctx.outdated_inputs = list(outdated_inputs)
                ctx.outdated_outputs = list(outdated_outputs)

                if len(i) > 0 or len(o) > 0:
                    if len(outdated_inputs) > 0 or len(outdated_outputs) > 0:
                        return ctx_func(*args, **kwargs)
                else:
                    return ctx_func(*args, **kwargs)

            ctx.node.func = inner

            return inner

        return outer

    def get_task_context(self, task):
        """
        Get the :py:class:`pake.TaskContext` object for a specific task.
        
        :raises: :py:class:`pake.UndefinedTaskException` if the task in not registered.
        :param task: Task function or function name as a string
        :return: :py:class:`pake.TaskContext`
        """

        task = get_task_arg_name(task)

        context = self._task_contexts.get(task, None)
        if context is None:
            raise UndefinedTaskException(task)
        return context

    def _add_task(self, name, func, dependencies=None):
        if name in self._task_contexts:
            raise RedefinedTaskException(name)

        @wraps(func)
        def func_wrapper(*args, **kwargs):
            ctx = self.get_task_context(func)
            try:
                ctx._i_io_open()
                if self._dry_run_mode:
                    ctx.print('Visited Task: "{}"'.format(func.__name__))
                else:
                    ctx.print('===== Executing Task: "{}"'.format(func.__name__))
                    return func(*args, **kwargs)
            finally:
                ctx._i_io_close()

        task_context = TaskContext(self, TaskGraph(name, func_wrapper))

        if len(inspect.signature(func).parameters) == 1:
            @wraps(func_wrapper)
            def _add_ctx_param_stub():
                func_wrapper(task_context)

            task_context.node.func = _add_ctx_param_stub

        self._task_contexts[name] = task_context

        if dependencies:
            for dependency in dependencies:
                dep_task = self.get_task_context(dependency)
                task_context.node.add_edge(dep_task.node)
                self._graph.remove_edge(dep_task.node)

        self._graph.add_edge(task_context.node)

        return task_context

    def dry_run(self, tasks=None):
        """
        Dry run over task, print a 'visited' message for each visited task.
        
        When using change detection, only out of date tasks will be visited.
        
        :raises: :py:class:`pake.UndefinedTaskException` if one of the default tasks given in the *tasks* parameter is unregistered. 
        
        :raises: :py:class:`FileNotFoundError` if a task references a non existent input file.
        :param tasks: Tasks to run.
        """
        self._dry_run_mode = True
        try:
            self.run(tasks=tasks, jobs=1)
        finally:
            self._dry_run_mode = False

    def run(self, tasks=None, jobs=1):
        """
        Run all given tasks, with an optional level of concurrency.
        
        :raises: :py:class:`pake.CyclicGraphException` if a cycle is found in the dependency graph.
        :raises: :py:class:`pake.UndefinedTaskException` if one of the default tasks given in the *tasks* parameter is unregistered. 
        :raises: :py:class:`FileNotFoundError` if a task references a non existent input file. 
        
        :param tasks: Tasks to run. :param jobs: Maximum number of threads, defaults to 1. (must be >= 1) 
        """

        if not is_iterable_not_str(tasks):
            tasks = [tasks]

        if jobs < 1:
            raise ValueError('Job count must be >= to 1.')

        graphs = []
        if tasks:
            for task in tasks:
                graphs.append(self.get_task_context(task).node.topological_sort())
        else:
            graphs.append(self._graph.topological_sort())

        if jobs == 1:
            for graph in graphs:
                for i in graph:
                    i()
            return

        with ThreadPoolExecutor(max_workers=jobs) as executor:
            for graph in graphs:
                for i in (i for i in graph if i is not self._graph):
                    context = self.get_task_context(i.name)
                    context._i_submit_self(executor)

    def set_defines_dict(self, dictionary):
        """
        Set an overwrite all defines with a dictionary object.
        
        :param dictionary: The dictionary object
        """
        self._defines = dict(dictionary)

    def print(self, *args, **kwargs):
        """Shorthand for print(..., file=this_instance.stdout)"""

        kwargs.pop('file', None)
        print(*args, **kwargs, file=self.stdout)

    def print_err(self, *args, **kwargs):
        """Shorthand for print(..., file=this_instance.stderr)"""

        kwargs.pop('file', None)
        print(*args, **kwargs, file=self.stderr)
