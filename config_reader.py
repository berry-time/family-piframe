#!/usr/bin/env python3

import configparser
import logging
import os

# default configuration template to fill
config_template_lines = [
    "[general]",
    "number_of_images_to_show: <can bei either a number of latest images to show, or all>",
    "delay_display_minutes: <delay for displaying next image in minutes>",
    "delay_update_minutes: <delay for updating images from email>",
    "screen_brightness: <screen brightness percentage, 1...100>",
    "start_black_screen_hour: <hour of day to start setting screen to black>",
    "stop_black_screen_hour: <hour of day to stop setting screen to black>",
    "",
    "[imap]",
    "hostname: <add hostname url here, e.g. imap.gmail.com>",
    "port: <add port here, e.g. 993>",
    "user: <add user login name here>",
    "password: <add login password here>",
    "",
    "[attachments]",
    "allowed_image_extensions: jpg, jpeg, png",
    "wifi_config_extension: wifi_conf",
    "wifi_config_allowed_senders: <email-addresses allowed to send name.wifi_conf files>, <separated by comma comma>, <or * for all>"
    "",
]

#####################################################################
# helper classes
#####################################################################

class GeneralData:
    def __init__(
        self,
        number_of_images_to_show: int=int(1e6),   # default very high value = "all images"
        delay_display_minutes: int=int(5),
        delay_update_minutes: int=int(5),
        screen_brightness: int=int(100),
        start_black_screen_hour: int=int(0),
        stop_black_screen_hour: int=int(0)):
    
        self.number_of_images_to_show = number_of_images_to_show
        self.delay_display_minutes = delay_display_minutes
        self.delay_update_minutes = delay_update_minutes
        self.screen_brightness = screen_brightness
        self.start_black_screen_hour = start_black_screen_hour
        self.stop_black_screen_hour = stop_black_screen_hour

    def is_black_screen_hour(self, current_hour: int) -> bool:

        disable_black_screen = self.start_black_screen_hour == self.stop_black_screen_hour
        wraparound = self.start_black_screen_hour > self.stop_black_screen_hour

        if disable_black_screen:
            return False

        if not wraparound:
            return self.start_black_screen_hour <= current_hour < self.stop_black_screen_hour
        else:
            return self.start_black_screen_hour <= current_hour or current_hour < self.stop_black_screen_hour


class ImapData:
    def __init__(self, host: str="", port: str="", user: str="", passwd: str=""):
        self.host = host
        self.port = port
        self.user = user
        self.passwd = passwd


class AttachmentData:
    def __init__(self,
                 allowed_image_extensions: list=None,
                 wifi_config_extension: list=None,
                 wifi_config_allowed_senders: list=None):
        self.allowed_image_extensions = allowed_image_extensions if allowed_image_extensions else []
        self.wifi_config_extension = wifi_config_extension if wifi_config_extension else []
        self.wifi_config_allowed_senders = wifi_config_allowed_senders if wifi_config_allowed_senders else []


class ConfigData:
    def __init__(self):
        self.general_data = GeneralData()
        self.imap_data = ImapData()
        self.attachment_data = AttachmentData()

    def set_general_data(
        self, number_of_images_to_show: str, delay_display_minutes: str, delay_update_minutes: str,
        screen_brightness: str, start_black_screen_hour: str, stop_black_screen_hour: str):
        """ set integer values if the strings are suitable, otherwise keep default values"""
        if number_of_images_to_show.isdigit():
            self.general_data.number_of_images_to_show = int(number_of_images_to_show)
        if delay_display_minutes.isdigit():
            self.general_data.delay_display_minutes = int(delay_display_minutes)
        if delay_update_minutes.isdigit():
            self.general_data.delay_update_minutes = int(delay_update_minutes)
        if screen_brightness.isdigit():
            self.general_data.screen_brightness = int(screen_brightness)
        if start_black_screen_hour.isdigit():
            self.general_data.start_black_screen_hour = int(start_black_screen_hour)
        if stop_black_screen_hour.isdigit():
            self.general_data.stop_black_screen_hour = int(stop_black_screen_hour)

    def set_imap_data(self, host: str, port: str, user: str, passwd: str):
        self.imap_data = ImapData(host=host, port=port, user=user, passwd=passwd)

    def set_attachment_data(self, allowed_image_extensions: list, wifi_config_extension: list, wifi_config_allowed_senders: list):
        self.attachment_data = AttachmentData(allowed_image_extensions, wifi_config_extension, wifi_config_allowed_senders)


#####################################################################
# primary class of this file
#####################################################################
class ConfigReader:
    def __init__(self, config_file_path, logger: logging.Logger):
        self.config_file_path = config_file_path
        self.logger = logger
        self.config_data = ConfigData()

    def read_config(self):
        """ Read configuration data from config file to config object and return it."""
        if not os.path.isfile(self.config_file_path):
            self.logger.error("Config file not found. Creating an empty template at {}".format(self.config_file_path))
            try:
                os.makedirs(os.path.basename(self.config_file_path))
                config_fh = open(self.config_file_path, "w")
                config_fh.write("\n".join(config_template_lines))
                config_fh.close()
            except Exception as e:
                self.logger.error("Could not generate template config file {}.".format(self.config_file_path))
            self.logger.error("Created empty config template {}. Please update it.".format(self.config_file_path))
            return ConfigData()

        try:
            config = configparser.ConfigParser()
            config.read(self.config_file_path)

            self.config_data.set_general_data(
                number_of_images_to_show=config.get('general', 'number_of_images_to_show').strip(),
                delay_display_minutes=config.get('general', 'delay_display_minutes').strip(),
                delay_update_minutes=config.get('general', 'delay_update_minutes').strip(),
                screen_brightness=config.get('general', 'screen_brightness').strip(),
                start_black_screen_hour=config.get('general', 'start_black_screen_hour').strip(),
                stop_black_screen_hour=config.get('general', 'stop_black_screen_hour').strip())

            self.config_data.set_imap_data(
                host=config.get('imap', 'hostname').strip(),
                port=config.get('imap', 'port').strip(),
                user=config.get('imap', 'user').strip(),
                passwd=config.get('imap', 'password').strip())

            self.config_data.set_attachment_data(
                tuple(entry.strip().lower() for entry in config.get('attachments', 'allowed_image_extensions').split(",")),
                tuple(entry.strip().lower() for entry in config.get('attachments', 'wifi_config_extension').split(",")),
                tuple(entry.strip()         for entry in config.get('attachments', 'wifi_config_allowed_senders').split(",")))

        except Exception as e:
            self.logger.error("Could not load one or more required fields from {}".format(self.config_file_path))
            self.logger.error("Error was: " + str(e))
            return ConfigData()

        return self.config_data
