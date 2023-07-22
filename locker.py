#!/usr/bin/env python3

import datetime
import glob
import logging
import os

class Locker:
    def __init__(self, base_folder, timeout_minutes=30.0):
        self.dt_format = "%Y-%m-%d_%H-%M-%S"
        self.base_folder = base_folder
        self.current_time = datetime.datetime.now()
        self.current_lockfile = None
        self.timeout_minutes = timeout_minutes

    def request(self, logger: logging.Logger) -> bool:
        existing_locks = glob.glob(os.path.join(self.base_folder, "*.lock"))
        valid_lock_active = False
        for existing_lock in existing_locks:
            if not os.path.isfile(existing_lock):
                continue
            lock_stamp = os.path.basename(existing_lock).split(".")[0]
            lock_time = datetime.datetime.strptime(lock_stamp, self.dt_format)
            lock_still_valid = (self.current_time - lock_time).total_seconds() < self.timeout_minutes * 60.0
            if lock_still_valid:
                logger.info("[status] Found valid lock from " + lock_stamp)
                valid_lock_active = True
            else:
                logger.warning("[warning] Found too old lock file {}: Removing it.".format(existing_lock))
                os.remove(existing_lock)

        if valid_lock_active:
            return False

        self.current_lockfile = os.path.join(self.base_folder, self.current_time.strftime(self.dt_format) + ".lock")
        open(self.current_lockfile, "w").close()
        return True

    def release(self):
        if self.current_lockfile is not None:
            if os.path.isfile(self.current_lockfile):
                os.remove(self.current_lockfile)
            self.current_lockfile = None

    def __del__(self):
        self.release()
