# yt-msd GUI Readme

This is the full readme for the GUI version, with information on every single feature inside of yt-msd. For the CLI readme, go back to the main readme, at the bottom.

## Table of Contents
This is the main table of contents, these main sections also have their own tables of contents for subsections.

[Installation](#installation)\
[Youtube Search and Download Features](#youtube-search-and-download-features)\
[MP3 Renamer](#mp3-renamer)\
[Local File Features](#local-file-features)\
[Yt-msd Sync Chains](#yt-msd-sync-chains)\
[Settings and Config](#settings-and-config)\
[Troubleshooting](#troubleshooting)\
[Technical Information](#technical-information-for-nerds)

# Installation

[Exe Version](#exe-version)\
[Python Version](#python-version)\
[Musicbee Plugin](#musicbee-plugin)

## Exe Version
Go to [releases](https://github.com/therealMKD/yt-msd/releases/latest) and download `yt-msd-setup.exe`.\
Once it is downloaded, double click to run it, and start the installation. If windows gives you a warning, you can safely click "Run Anyway". There is a virustotal link in the releases if you want to be sure the file is not malicious.

Proceed through the installer, making the choices you want. **If you plan to use the MusicBee plugin, I would recommend not changing the default installation path.**

By default, the program will be installed to `C:\Users\[your username]\%AppData%\Local\yt-msd\`. You can launch it through the start menu, or by running `yt-msd.exe` in the installation directory.

To uninstall the program, find it in Program Files, or in Settings, and click uninstall.

**On first run**, yt-msd will ask you to allow it through firewall. This is necessary for sync to work, and you will ALWAYS receive that popup on program start if the firewall rule doesn't exist. Additionally, yt-msd will also use `winget` to install yt-dlp, which is required for Youtube searching and downloading. If you have yt-dlp installed somewhere else, (e.g. chocolatey) yt-msd will not find it, and will install a duplicate version with winget.

Because of this, I would recommend against manually installing yt-dlp, and let the program manage it automatically. On each start, it will also check yt-dlp's github repo, and update yt-dlp if necessary.

If something isn't working, check [Troubleshooting](#troubleshooting).

## Python Version
Go to [releases](https://github.com/therealMKD/yt-msd/releases/latest) and download `yt-msd-gui.pyw`.\
Before you can run it, you must have Python installed on your system, as well as a few dependencies.

### To install Python: 
I recommend using winget, but if you've tried winget and it isn't working for whatever reason, download the python install manager from python's website. I would recommend version 3.15.0, but any version newer than 3.14.6 should work.

If you use winget, first run `winget install python`, and wait for it to finish. This will install python's download manager. Next, run `py` to ensure that python has been downloaded. (It should output "Installing Python 3.15", and start IDLE.)

The following commands for dependencies use pip. Installing python with winget will NOT create a python bin directory, and by default, you will not be able to just run `pip` in terminal. Instead, you will have to use `py -m pip`.\
There is a way to fix this, by running `py install --configure` and accepting the dialogue, then restarting your terminal. This will let you use `pip` directly, as well as a few other python commands. If you don't want to do this, just add `py -m` before all the following install commands.

### Installing the Dependencies
The following dependencies will need to be installed before the program will run:
- **ffmpeg** through `pip install ffmpeg` AND `winget install ffmpeg` - Both must be present
- **vlc** through `pip install python-vlc` AND `winget install vlc` - Both must be present (If you already have the vlc application, you do not need to install it with winget)
- **pillow** through `pip install pillow`
- **pyside6** through `pip install pyside6`
- **mutagen** through `pip install mutagen`
- **watchdog** through `pip install watchdog`

If you get an error saying `pip is not a recognized command`, refer to the last paragraph of [Installing Python](#to-install-python).

For Ffmpeg and VLC, the normal application is required, since the python dependencies are just wrappers. In the case of VLC, you need the entire desktop VLC player to be installed. If you already have it installed, you do not need to run the winget command.

If the program won't start, refer to [Troubleshooting](#troubleshooting). You've probably forgotten a dependency.

**On first run**, yt-msd will ask you to allow it through firewall. This is necessary for sync to work, and you will ALWAYS receive that popup on program start if the firewall rule doesn't exist. Additionally, yt-msd will also use `winget` to install yt-dlp, which is required for Youtube searching and downloading. If you have yt-dlp installed somewhere else, (e.g. chocolatey) yt-msd will not find it, and will install a duplicate version with winget.

Because of this, I would recommend against manually installing yt-dlp, and let the program manage it automatically. On each start, it will also check yt-dlp's github repo, and update yt-dlp if necessary.

## Musicbee Plugin
Reference the [Plugin's Readme](https://github.com/therealMKD/yt-msd/tree/main/MusicBee%20Plugin#readme) 
 


# Youtube Search and Download Features

# MP3 Renamer

# Local File Features

# Yt-msd Sync Chains

# Settings and Config

# Troubleshooting

# Technical Information for Nerds
