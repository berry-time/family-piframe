#!/usr/bin/env python3

import os
import pathlib
import re
import subprocess
import sys

def get_unique_wifi_data(wifi_cache_path) -> list:
    wifi_files = [os.path.join(wifi_cache_path, f) for f in os.listdir(wifi_cache_path)]
    wifi_files = [f for f in wifi_files if os.path.isfile(f)]
    wifi_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)  # reverse order to prefer newer files over older
    wifi_ssids = []
    wifi_data = []
    for wifi_file in wifi_files:
        with open(wifi_file) as wifi_fh:
            wifi_file_content = wifi_fh.read()
            ssids = re.findall(r'\sssid=(.*)\n', wifi_file_content)  # ssid=..., preceded by whitespace, until end of line
            ssids = [ssid.strip("\"\'") for ssid in ssids]  # remove quotes for unique names
            if ssids == [] or any([ssid in wifi_ssids for ssid in ssids]):
                continue  # add only files that don't contain already present SSIDs
            wifi_ssids += ssids
            wifi_data.append(wifi_file_content)
            print("Found new SSIDs " + str(ssids) + " in wifi cache.")
    print("Found {} wifi cache files with unique wifi data.".format(len(wifi_data)))
    return wifi_data

def update_wpa_supplicant_config(wpa_supplicant_config: str, wifi_cache_path: str):
    target_file = wpa_supplicant_config
    original_file = wpa_supplicant_config + ".orig"

    if not os.path.isfile(target_file) and not os.path.isfile(original_file):
        print("[error] The required file wpa_supplicant config file was not found. Not updating wifi data.")
        return
    if not os.access(target_file, os.W_OK) or not os.access(pathlib.Path(original_file).parent.absolute(), os.W_OK):
        print("[error] No write access to wpa_supplicant config file {}. Not updating wifi data.".format(target_file))
    if not os.path.isfile(original_file):
        print("[info] Making a backup of file {} to {}".format(target_file, original_file))
        cmd_list = ["cp", target_file, original_file]
        subprocess.Popen(" ".join(cmd_list), shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    
    # generate new target file from original file and cached wifi data
    with open(original_file, "r") as source_fh:
        source_data = source_fh.readlines()
        with open(target_file, "w") as target_fh:
            target_fh.writelines(source_data)
            target_fh.write("\n# THE FOLLOWING NETWORKS WERE ADDED BY THE FAMILY-PIFRAME SCRIPT!\n")
            for wifi_cache_content in get_unique_wifi_data(wifi_cache_path):
                    target_fh.writelines("\n")
                    target_fh.writelines(wifi_cache_content)
    
    # finally, update the config via cli
    cmd_list = ["wpa_cli", "-i", "wlan0", "reconfigure"]
    subprocess.Popen(" ".join(cmd_list), shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()


if __name__ == "__main__":
    wpa_supplicant_config = sys.argv[1]
    wifi_cache_path = sys.argv[2]
    update_wpa_supplicant_config(wpa_supplicant_config, wifi_cache_path)
