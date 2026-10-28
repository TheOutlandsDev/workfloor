"""Cooperative process ownership on trusted local storage. Original MIT source."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat

import workbench as wb

LOCK_NAME = '.workfloor.lock'

def plain_path(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or str(path).startswith(('\\\\', '//')):
        raise wb.InputError('Use a fully spelled absolute path on trusted local storage.')
    for part in path.parts[1:]:
        if ':' in part or part.endswith((' ', '.')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I):
            raise wb.InputError('Use ordinary local path components.')
    for current in [*reversed(path.parents), path]:
        try: info = current.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise wb.InputError('Linked or reparse storage is unsupported.')
    return path

def ordinary_file(path, maximum):
    path = plain_path(path); info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
        raise wb.InputError('Expected one ordinary bounded file with one hard link.')
    return info

def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

@contextmanager
def data_lock(directory, *, create=False):
    """Hold one persistent guard inode; OS releases ownership if the process exits."""
    root = plain_path(Path(directory).absolute())
    if create: root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir(): raise wb.InputError('The data directory must already exist.')
    marker = root / LOCK_NAME; plain_path(marker)
    fd = os.open(marker, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
    held = False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1:
            raise wb.InputError('The ownership guard is not an ordinary one-byte file.')
        if info.st_size == 0: os.write(fd, b'\0')
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = True
        except OSError as exc:
            raise wb.InputError('Workfloor or maintenance owns this data directory. Stop it and retry; never delete its guard.') from exc
        if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (marker.stat().st_dev, marker.stat().st_ino):
            raise wb.InputError('The ownership guard changed. Preserve the directory.')
        yield root
    finally:
        if held:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        # Never unlink a guard: another process may already have the same inode open.
