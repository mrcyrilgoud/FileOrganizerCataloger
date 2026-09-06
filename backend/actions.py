import os

from send2trash import send2trash


def delete_file_safely(file_path):
    """Move a file to the trash. Returns (ok, message)."""
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError("File not found: %s" % file_path)
        if not os.path.isfile(file_path):
            raise IsADirectoryError(
                "Cannot delete directory: %s. Only files allowed." % file_path
            )
        send2trash(file_path)
        return True, "File moved to trash successfully"
    except Exception as exc:
        return False, str(exc)


def delete_directory_safely(dir_path):
    """Move a directory to the trash. Returns (ok, message)."""
    try:
        if not os.path.exists(dir_path):
            raise FileNotFoundError("Directory not found: %s" % dir_path)
        if not os.path.isdir(dir_path):
            raise NotADirectoryError("Path is not a directory: %s" % dir_path)
        send2trash(dir_path)
        return True, "Directory moved to trash successfully"
    except Exception as exc:
        return False, str(exc)
