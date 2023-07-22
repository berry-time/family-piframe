#!/usr/bin/env python3

import crontab
import datetime
import logging
import os
import psutil
import subprocess
import time

from attachment_fetcher import AttachmentFetcher
from config_reader import ConfigReader
from locker import Locker


class FamilyPiFrame:
    """
    Main class for the e-mail based image viewer/frame.
    - calls the config reader
    - fetches attachments for new images sent by e-mail
    - fetches new config files for wifis
    - updates the cronjob according to the configuration file
    - starts the slideshow using the "sxiv" app
    """
    def __init__(self, app_data_path: str, wpa_supplicant_config: str, verbose: bool = False):
        self.app_data_path = app_data_path
        self.wpa_supplicant_config = wpa_supplicant_config

        self.image_cache_data_path = os.path.join(app_data_path, "cache"),
        self.image_cache_info_file = os.path.join(self.app_data_path, "cache.txt")

        self.wifi_cache_data_path = os.path.join(app_data_path, "wifi_cache"),
        self.wifi_cache_info_file = os.path.join(self.app_data_path, "wifi_cache.txt")

        self.config_file_path = os.path.join(app_data_path, "config.ini")
        self.verbose = verbose
        self.logger = None
        self._setup_logger(os.path.join(app_data_path, "debug.log"), verbose)

        self.config_data = None

    def run(self):
        run_locker = Locker(self.app_data_path, timeout_minutes=30.0)
        if not run_locker.request(self.logger):
            self.logger.info("[status] Requesting lock not successful, stopping.")
            return

        self.logger.info("[status] reading config")
        self.config_data = ConfigReader(self.config_file_path, self.logger).read_config()

        self.logger.info("[status] fetching new images")
        new_images_available = AttachmentFetcher(
            self.image_cache_data_path,
            self.image_cache_info_file,
            self.config_data.imap_data,
            self.config_data.attachment_data.allowed_image_extensions,
            ["*"],  # allow all senders for images currently
            self.logger).run()

        self.logger.info("[status] fetching new wifi data")
        new_wifi_data_available = AttachmentFetcher(
            self.wifi_cache_data_path,
            self.wifi_cache_info_file,
            self.config_data.imap_data,
            self.config_data.attachment_data.wifi_config_extension,
            self.config_data.attachment_data.wifi_config_allowed_senders,
            self.logger).run()

        if new_wifi_data_available:
            self._call_wpa_supplicant_config_update()

        startup_delay = 10  # higher delay on startup to prevent fullscreen issues
        if new_images_available:
            self._kill_process("sxiv")
            time.sleep(2)  # make sure the process is closed before continuing
            startup_delay = 2  # need less delay, we are not in startup mode
        if not self._find_process("sxiv"):
            self.logger.info("[status] updating cron")
            self._update_cron()
            self.logger.info("[status] Starting display process")
            time.sleep(startup_delay)
            self._start_display()

        self.logger.info("[status] handling black screen hours")
        self._handle_black_screen_hours()
        self.logger.info("[status] cron cycle completed")

        run_locker.release()

    #############################################
    # private functions of FamilyPiFrame
    #############################################
    def _setup_logger(self, log_file_path: str, verbose: bool=False):
        self.logger = logging.getLogger("FamilyPiFrame")
        self.logger.setLevel(logging.DEBUG)
        logging_ch = logging.StreamHandler()
        if not verbose:
            logging_ch.setLevel(logging.ERROR)
        self.logger.addHandler(logging_ch)

        logging_fh = logging.FileHandler(log_file_path)
        if logging_fh:
            logging_fh.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
            self.logger.addHandler(logging_fh)
        else:
            self.logger.error("Could not open logging output file!")

    def _execute_and_communicate(self, cmd_list: list, log: bool=True):
        sub_out, sub_err = subprocess.Popen(" ".join(cmd_list), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if log:
            self.logger.info("[status] executed " + " ".join(cmd_list))
            for out_entry in sub_out.decode("utf-8").strip().split("\n"):
                if out_entry.strip() != "":
                    self.logger.info(out_entry)
            for err_entry in sub_err.decode("utf-8").strip().split("\n"):
                if err_entry.strip() != "":
                    self.logger.error(err_entry)

    def _call_wpa_supplicant_config_update(self):
        self.logger.info("[status] updating wifi configuration")
        update_wpa_supplicant_script = os.path.join(self.app_data_path, "update_wpa_supplicant.py")
        cmd_list = ["sudo", "python3", update_wpa_supplicant_script, self.wpa_supplicant_config, self.wifi_cache_data_path]
        self._execute_and_communicate(cmd_list)

    def _get_image_cache_txt(self):
        cache_image_list = []
        try:
            cache_txt_fh = open(self.image_cache_info_file, "r")
            entries = sorted(cache_txt_fh.readlines(), reverse=True)
            count = 0
            for entry in entries:
                if count >= self.config_data.general_data.number_of_images_to_show:
                    break
                cache_image_list.append(entry.strip())
                count += 1
        except Exception as e:
            self.logger.error("Unable to read cache file. Is it empty?")
            self.logger.error("Error was: " + str(e))

        return cache_image_list

    @staticmethod
    def _find_process(proc_name: str):
        for proc in psutil.process_iter():
            try:
                if proc_name.lower() in proc.name().lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def _kill_process(self, proc_name: str):
        for proc in psutil.process_iter():
            try:
                if proc_name.lower() in proc.name().lower():
                    proc.kill()
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                self.logger.warn("Failed to kill process.")

        return False

    def _set_sxiv_background_black(self):
        try:
            black_background_string = "Sxiv.background: #000000"
            target_config_file = os.path.expanduser("~/.Xresources")

            if os.path.isfile(target_config_file) and black_background_string in open(target_config_file).read():
                return

            self.logger.info("Adding black background config for sxiv in " + target_config_file)
            config_fh = open(target_config_file, "a+")
            config_fh.write("\n" + black_background_string + "\n")
            config_fh.close()
        except Exception as e:
            self.logger.warning("Could not set background to black for sxiv in ~/.Xresources. Is it accessible?")
            self.logger.warning("Error was: " + str(e))

    def _start_display(self):
        display_files = self._get_image_cache_txt()
        if not display_files:
            return
        env_with_display = os.environ.copy()
        env_with_display["DISPLAY"] = ":0"

        self._set_sxiv_background_black()
        cmd_list = ["sxiv", "-b", "-f", "-S", str(self.config_data.general_data.delay_display_minutes*60)] + display_files

        try:
            self.logger.info("Running " + " ".join(cmd_list))
            subprocess.Popen(cmd_list, env=env_with_display, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            self.logger.error("Starting the sxiv viewer failed. Is it installed?")
            self.logger.error("Error was: " + str(e))

    def _update_cron(self):
        try:
            cron_pi = crontab.CronTab(user='pi')
            cron_matches = cron_pi.find_command('family-piframe')
            for entry in cron_matches:
                self.logger.info("Updating cron entry " + str(entry))
                entry.minute.every(self.config_data.general_data.delay_update_minutes)
            cron_pi.write()
        except Exception as e:
            self.logger.error("Error " + str(e) + "occurred while updating cron.")

    def _handle_black_screen_hours(self):
        current_hour = datetime.datetime.now().hour
        self.logger.info("Current hour: {}, black screen hours: {}-{}, black screen: {}".format(current_hour,
            self.config_data.general_data.start_black_screen_hour, self.config_data.general_data.stop_black_screen_hour,
            str(self.config_data.general_data.is_black_screen_hour(current_hour))))

        if self.config_data.general_data.is_black_screen_hour(current_hour):
            self._execute_and_communicate(["xset -d :0 s    0 0   && sleep 1 && xset -d :0 s off && sleep 1"], log=False)
            self._execute_and_communicate(["xset -d :0 dpms 0 0 0 && sleep 1 && xset -d :0 -dpms && sleep 1"], log=False)
            self._execute_and_communicate(["xrandr --output HDMI-1 --brightness 0"])
        else:
            screen_brightness_fraction = float(self.config_data.general_data.screen_brightness) / 100.0
            self._execute_and_communicate(["xset -d :0 s    0 0   && sleep 1 && xset -d :0 s off && sleep 1"], log=False)
            self._execute_and_communicate(["xset -d :0 dpms 0 0 0 && sleep 1 && xset -d :0 -dpms && sleep 1"], log=False)
            self._execute_and_communicate(["xrandr --output HDMI-1 --brightness " + str(screen_brightness_fraction)])
