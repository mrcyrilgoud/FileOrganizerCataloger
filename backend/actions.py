import os

from send2trash import send2trash


def trash_path(path):
    """Move an existing file or directory to the system Trash."""
    try:
        if not os.path.exists(path):
            raise FileNotFoundError("File not found: %s" % path)
        if not (os.path.isfile(path) or os.path.isdir(path)):
            raise ValueError("Path is not a file or directory: %s" % path)
        send2trash(path)
        return True, "Path moved to trash successfully"
    except Exception as exc:
        return False, str(exc)
