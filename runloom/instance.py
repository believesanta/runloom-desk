"""An OS-owned workspace lock releases even after a crash."""
import os


class WorkspaceLock:
    def __init__(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        self.handle = (folder / '.instance.lock').open('a+b')
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b'0'); self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError('This workspace is already open in another Runloom Desk window.') from None

    def close(self):
        self.handle.close()
