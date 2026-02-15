import os
import platform

USER_HOME = os.path.expanduser("~")
WINDOWS_PATH = "zutui" # probably should be in %AppData% or something, but I'm not sure, so I won't change it
LINUX_PATH = ".config/zutui"

def get_config_path():
    system = platform.system()
    if system == "Windows":
        APP_DIR = os.path.join(USER_HOME, WINDOWS_PATH)
    elif system in ["Linux", "Darwin"]:
        APP_DIR = os.path.join(USER_HOME, LINUX_PATH)
    else:
        print(f"System {system} not supported, aborting...")
        exit(1)
    if not os.path.exists(APP_DIR):
        os.makedirs(APP_DIR)
    return APP_DIR
