#!/usr/bin/env python3

import os

from family_piframe import FamilyPiFrame

# required "sudo raspi-config" settings:
# - screen blanking must be enabled (only if xset dpms feature is used!)
#
# required additional Ubuntu packages:
# - sxiv
# - python3-crontab
# - python3-psutil (should be already available)
# - libxext6 (should be already available)
#
# required cronjob:
# - run "crontab -e" and paste
#     SHELL=/bin/bash
#     */3 * * * * export DISPLAY=:0 && /usr/bin/python3 /home/pi/zero-fun-net/family-piframe/main.py &> /home/pi/zero-fun-net/family-piframe/console.log &
#  
# optional additional changes:
# - hide trash icon from desktop: edit /etc/xdg/pcmanfm/LXDE-pi/desktop-items-0.conf (set show_trash=0)
# - hide menu bar from desktop: edit /etc/xdg/lxsession/LXDE-pi/autostart (delete line "@lxpanel --profile LXDE")
# - hide default password warning: delete /etc/xdg/lxsession/LXDE-pi/sshpwd.sh
# - hide cursor: in /etc/lightdm/lightdm.conf, change "#xserver-command=X" to "server-command=X -nocursor"

def main(
    app_path_string: str,
    wpa_supplicant_config: str,
    verbose: bool=True):

    app_path = os.path.expanduser(app_path_string)
    family_pi_frame = FamilyPiFrame(app_path, wpa_supplicant_config, verbose)
    family_pi_frame.run()


if __name__ == '__main__':
    app_home = "/home/pi/zero-fun-net/family-piframe"
    wpa_supplicant_config = "/etc/wpa_supplicant/wpa_supplicant.conf"
    verbose = False
    main(app_home, wpa_supplicant_config, verbose)
