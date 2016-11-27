import os


def touch(file_name, times=None):
    file_handle = open(file_name, 'a')
    try:
        os.utime(file_name, times)
    finally:
        file_handle.close()
