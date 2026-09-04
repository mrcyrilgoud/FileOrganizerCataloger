import os
import shutil
import logging
from send2trash import send2trash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def delete_file_safely(file_path: str):
    """
    Safely deletes a file by moving it to the trash.
    - file_path: Absolute path to the file.
    """
    try:
        # 1. Path Validation
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not os.path.isfile(file_path):
            raise IsADirectoryError(f"Cannot delete directory: {file_path}. Only files allowed.")

        # 2. Delete (Send to Trash)
        send2trash(file_path)
        logger.info(f"Moved file to trash: {file_path}")
        return True, "File moved to trash successfully"

    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {str(e)}")
        return False, str(e)

def delete_directory_safely(dir_path: str):
    """
    Safely deletes a directory by moving it to the trash.
    - dir_path: Absolute path to the directory.
    """
    try:
        # 1. Path Validation
        if not os.path.exists(dir_path):
            raise FileNotFoundError(f"Directory not found: {dir_path}")
        
        if not os.path.isdir(dir_path):
            raise NotADirectoryError(f"Path is not a directory: {dir_path}")

        # 2. Delete (Send to Trash)
        send2trash(dir_path)
        logger.info(f"Moved directory to trash: {dir_path}")
        return True, "Directory moved to trash successfully"

    except Exception as e:
        logger.error(f"Error deleting directory {dir_path}: {str(e)}")
        return False, str(e)
