"""An OS-held lock prevents restoration while this single-instance server is running."""
import os
from contextlib import contextmanager


@contextmanager
def instance_lock(data_dir, name='.instance.lock'):
    data_dir.mkdir(parents=True,exist_ok=True)
    f=(data_dir/name).open('a+b')
    if f.tell()==0:
        f.write(b'0')
        f.flush()
    f.seek(0)
    locked=False
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        locked=True
        yield
    finally:
        if locked:
            f.seek(0)
            if os.name=='nt':
                msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        f.close()
