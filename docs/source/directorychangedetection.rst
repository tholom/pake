Change Detection Against Directories
====================================

Change detection in pake works against directories in the same way it works against files.

Files can be compared against directories (and vice versa) when providing inputs and
outputs to a task, directories can also be compared against each other if needed.

Basically, a directory name can be used in place of a file name anywhere in 
a tasks input(s) and output(s) parameters.

Example:

.. code-block:: python

    import pake
    import glob
    import pathlib

    pk = pake.init()

    # Whenever the modification time of 'my_directory' or
    # 'my_directory_2' is more recent than the file 'my_big.png',
    # this task will run.

    @pk.task(i=['my_directory', 'my_directory_2'], o='my_big.png')
    def concatenate_pngs(ctx):
       png_files = []

       for d in ctx.inputs:
           # Need to collect the files in the directories yourself
           png_files += pathlib.Path(d).glob('*.png')

       # Concatenate with ImageMagick's convert command
       ctx.call('convert', png_files, '-append', ctx.outputs)


    pake.run(pk, tasks=concatenate_pngs)


