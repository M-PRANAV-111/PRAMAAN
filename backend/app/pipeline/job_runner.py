"""Isolated execution target supervised by the existing worker thread."""
import sys
import os
import threading

if __name__ == '__main__':
    # Parent owns the stdin pipe. Stop on EOF if it dies, including forced Windows termination.
    def parent_watch():
        if os.name == 'nt':
            # A blocking stdin read can deadlock NumPy/OpenCV initialization on Windows.
            # Poll pipe liveness without holding a CRT, buffered-I/O or OS read lock.
            import ctypes
            import msvcrt
            import time
            from ctypes import wintypes
            peek = ctypes.WinDLL('kernel32', use_last_error=True).PeekNamedPipe
            peek.argtypes = (wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                             wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID)
            peek.restype = wintypes.BOOL
            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
            while peek(handle, None, 0, None, None, None):
                time.sleep(.2)
        else:
            os.read(sys.stdin.fileno(), 1)
        os._exit(1)
    threading.Thread(target=parent_watch,daemon=True).start()
    from app.config import get_settings
    from app.instance_lock import instance_lock
    with instance_lock(get_settings().data_dir,'.job-'+sys.argv[1]+'.lock'):
        # Import registered extensions before running the job.
        import app.main  # noqa: F401
        from .orchestrator import run_job
        run_job(sys.argv[1])
        from app.email import drain
        drain(75)
