import sys
import unittest

import os

script_dir = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.abspath(
                   os.path.join(script_dir, os.path.join('..', '..'))))

import pake
import pake.program
import pake.util
import pake.conf


from tests import open_devnull
#pake.conf.stdout = open_devnull() if pake.conf.stdout is sys.stdout else pake.conf.stdout
#pake.conf.stderr = open_devnull() if pake.conf.stderr is sys.stderr else pake.conf.stderr


class PakeTest(unittest.TestCase):

    def test_registration(self):

        pake.program.shutdown()

        pk = pake.init()

        script_path = os.path.dirname(os.path.abspath(__file__))

        in1 = os.path.join(script_path, 'test_data', 'in1')

        # Does not need to exist, easier than dealing with
        # a full path.

        out1 = 'out1'

        pake.util.touch(in1)

        in2 = os.path.join(script_path, 'test_data', 'in2')

        # Does not need to exist either.

        out2 = 'out2'

        pake.util.touch(in2)

        @pk.task(o='dep_one.o')
        def dep_one(ctx):
            pass

        @pk.task(o=['dep_two.o', out2])
        def dep_two(ctx):
            pass

        @pk.task(o='dep_three.o')
        def dep_three(ctx):
            pass

        @pk.task(dep_one, dep_two, i=in1, o=out1)
        def task_one(ctx):
            nonlocal self
            self.assertListEqual(ctx.inputs, [in1])
            self.assertListEqual(ctx.outputs, [out1])

            self.assertListEqual(ctx.outdated_inputs, [in1])
            self.assertListEqual(ctx.outdated_outputs, [out1])

            self.assertListEqual(list(ctx.outdated_pairs), [(in1, out1)])

            # Check that the correct immediate dependency outputs are reported.
            self.assertCountEqual(['dep_one.o', 'dep_two.o', out2], ctx.dependency_outputs)

            dep_one_ctx = pk.get_task_context(dep_one)
            dep_two_ctx = pk.get_task_context(dep_two)

            # Check that the correct immediate dependencies are reported.
            self.assertCountEqual([dep_one_ctx, dep_two_ctx], ctx.dependencies)

        def other_task(ctx):
            nonlocal self
            self.assertListEqual(ctx.inputs, [in2])
            self.assertListEqual(ctx.outputs, [out2])

            self.assertListEqual(ctx.outdated_inputs, [in2])
            self.assertListEqual(ctx.outdated_outputs, [out2])

            self.assertListEqual(list(ctx.outdated_pairs), [(in2, out2)])

            task_one_ctx = pk.get_task_context(task_one)
            dep_three_ctx = pk.get_task_context(dep_three)

            # Check that the correct immediate dependency outputs are reported.
            self.assertCountEqual(['dep_three.o', out1], ctx.dependency_outputs)

            # Check that the correct immediate dependencies are reported.
            self.assertCountEqual([task_one_ctx, dep_three_ctx], ctx.dependencies)

        ctx = pk.add_task('task_two', other_task,
                          inputs=in2, outputs=out2,
                          dependencies=[task_one, dep_three])

        task_one_ctx = pk.get_task_context(task_one)
        dep_three_ctx = pk.get_task_context(dep_three)

        # Check that the correct immediate dependencies are reported.
        # ctx.dependencies should return a meaningful value outside of a task
        # as well as inside. That is not the case with ctx.dependency_outputs
        self.assertCountEqual([task_one_ctx, dep_three_ctx], ctx.dependencies)

        self.assertEqual(ctx.name, 'task_two')

        self.assertEqual(ctx, pk.get_task_context('task_two'))
        self.assertEqual(ctx, pk.get_task_context(other_task))

        self.assertEqual(pk.get_task_context('task_one'), pk.get_task_context(task_one))

        self.assertEqual(pk.get_task_name(task_one), 'task_one')
        self.assertEqual(pk.get_task_name(other_task), 'task_two')

        self.assertEqual(pk.task_count, 5)
        self.assertEqual(len(pk.task_contexts), 5)

        with self.assertRaises(pake.UndefinedTaskException):
            pk.get_task_context('undefined')

        with self.assertRaises(pake.UndefinedTaskException):
            pk.get_task_name('undefined')

        with self.assertRaises(pake.RedefinedTaskException):
            pk.add_task('task_one', task_one)

        with self.assertRaises(pake.RedefinedTaskException):
            pk.add_task('task_two', other_task)

        # Raises an exception if there is an issue
        # Makes this test easier to debug
        pk.run(tasks='task_two')

        self.assertEqual(pake.run(pk, tasks=['task_two'], call_exit=False), 0)

        self.assertEqual(pk.run_count, 5)