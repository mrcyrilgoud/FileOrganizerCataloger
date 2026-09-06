import os

from send2trash import send2trash


def _trash(path, want_dir):
    label = "Directory" if want_dir else "File"
    try:
        if not os.path.exists(path):
            raise FileNotFoundError("%s not found: %s" % (label, path))
        if want_dir and not os.path.isdir(path):
            raise NotADirectoryError("Path is not a directory: %s" % path)
        if not want_dir and not os.path.isfile(path):
            raise IsADirectoryError(
                "Cannot delete directory: %s. Only files allowed." % path
            )
        send2trash(path)
        return True, "%s moved to trash successfully" % label
    except Exception as exc:
        return False, str(exc)


def delete_file_safely(file_path):
    return _trash(file_path, False)


def delete_directory_safely(dir_path):
    return _trash(dir_path, True)
