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


def delete_file_safely(path):
    """Move an existing regular file to Trash; reject directories."""
    if not os.path.isfile(path):
        return False, "File not found or path is not a regular file: %s" % path
    return trash_path(path)


def delete_directory_safely(path):
    """Move an existing directory to Trash."""
    if not os.path.isdir(path):
        return False, "Directory not found: %s" % path
    return trash_path(path)
