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
[Python Version Specific Troubleshooting](#python-version-specific-troubleshooting)\
[General Troubleshooting (Both python and exe versions)](#general-troubleshooting)

> [!WARNING]
Before doing ANY of these troubleshooting steps, check for a newer yt-msd version! If the problem is related to yt-msd itself, chances are that I've found and fixed it already!

## Python Version Specific Troubleshooting
If the program won't start, pretty much the ONLY thing that could be wrong is a missing dependency. Follow this checklist:

1. Make sure Python is installed. Open terminal, and run `py --version`. You should get an output like `Python 3.15.0`. If your Python version is LOWER than 3.14.8, you need to (update it)[#to-install-python].
2. Make sure all required dependencies exist. Open terminal, and run `py -m pip list`. You will get an output listing all installed packages. That list should look like this, with equivalent, or higher version numbers:
```
Package            Version
------------------ ----------
ffmpeg             1.4
mutagen            1.48.1
pillow             13.0.0
pip                26.2.1
PySide6            6.12.0
PySide6_Addons     6.12.0
PySide6_Essentials 6.12.0
PySide6_Pdf        6.12.0.140
PySide6_WebEngine  6.12.0.140
python-vlc         3.0.21203
watchdog           6.0.0
```
If anything is missing, run `py -m pip install [missing dependency]`

3. Make sure VLC and Ffmpeg are installed normally. Open terminal, and run `winget list ffmpeg`. You should see a result. Next, run `winget list vlc`. Again, you should see a result. If you see `No installed package found matching input criteria`, then you must install that package with `winget install`.
4. If it STILL won't start, go to the directory where `yt-msd-gui.pyw` is located, and right click on blank space.\
   Select "Open In Terminal", and run `py yt-msd-gui.pyw`. If you renamed the file, substitute the filename for your new one. When you run this command, look at the error that occurs.\
   If the error is `No such file or directory`, you typed the name wrong. Double check it, or enclose it in quotes.\
   If the error is `py is not a recognized as an internal or external command`, you don't have python [installed correctly](#to-install-python).\
   If the error contains `ModuleNotFoundError` or `ImportError`, you have a missing dependency, and you didn't follow the previous steps. Start over.\
   If the error does not match any of these cases, re-download the pyw file, and try again.\
   If the errors persist, create an issue report here, and attach the exact error you get when trying to run the program.

## General Troubleshooting
If the instructions listed don't fix the issue, create an issue report in this repository. **Please note that the only supported operating system is Windows 11. Linux, MacOS, and older Windows versions are NOT tested!**

### Program won't start
1. If it is the python version, refer to [python troubleshooting](#python-version-specific-troubleshooting).
2. Uninstall and reinstall, getting the latest version from [releases](https://github.com/therealMKD/yt-msd/releases/latest).

### Downloading fails (Repeatedly attempts to download)
Either ffmpeg, or yt-dlp is not installed. 
1. Verify that both yt-dlp and ffmpeg are installed. Open terminal, and run `winget list ffmpeg`, and `winget list yt-dlp`. Both commands should give results. If the result is `No installed package found matching input criteria`, then install the package with `winget install yt-dlp`, or `winget install ffmpeg`.\
   Note that yt-msd is designed to update yt-dlp automatically. Google commonly updates youtube, and then breaks yt-dlp.
2. If yt-dlp and ffmpeg BOTH exist, but downloads still don't work, Google probably broke yt-dlp again, and a new release hasn't been pushed yet. Your only option is to wait, since yt-msd is hard coded to look for `yt-dlp.yt-dlp`, so if you use `yt-dlp.yt-dlp.nightly` instead, yt-msd will ignore it. You can expect an update to happen within 24 hours or so. Additionally, make sure ffmpeg is updated, by running `winget upgrade ffmpeg`.

### Youtube Search or playback fails
Yt-dlp is outdated.
1. Because yt-msd automatically updates yt-dlp, first go into settings, and click "Update with Winget" (In the lower right corner). If no updates are found,
2. Wait for yt-dlp to update. Google periodically updates youtube and breaks yt-dlp, and it's usually 24 hours before a new release is pushed. Don't bother trying to use the nightly version, because yt-msd will only use `yt-dlp.yt-dlp` for stability reasons, and will completely ignore `yt-dlp.yt-dlp.nightly`.

### Program freezes, or crashes (After successfully starting)
1. If it's the python version, refer to [python troubleshooting](#python-version-specific-troubleshooting). 99% of problems on the python version are due to missing dependencies. Since the issue occurs after start, my recommendation is to follow step 4, opening the program in terminal. Do whatever it takes to crash or freeze the program, and look at the error that is generated.
2. If it's the exe version, there is no console to show the errors. Uninstall, redownload, and reinstall. Make sure yt-dlp is updated (Follow instructions in [Youtube Search or playback fails](#youtube-search-or-playback-fails).

### Renamer errors
If you rename a file, and get a syntax error or similar (Not a `a file named [name] already exists` error), the original video title, or your new title, has an illegal character. Reminder: `?*<>":/\|` are illegal characters for filenames in windows. If the video title has an illegal character, yt-dlp changes it into a different UTF encoding, that looks the same, but doesn't cause a windows error.

For example, the normal question mark, `U+003F` is illegal, but the fullwidth question mark, `U+FF1F` is not. If a youtube video has `U+003F` in the title, yt-dlp will replace it with `U+FF1F`. This can sometimes cause errors in the renamer. Most of the time, manually overriding the whole name will fix it, but in some rare cases, you will have to manually edit the file in file explorer.

### Normalization Errors
It's somewhat common to have errors while normalizing, I think it has something to do with filenames. You can ignore them, because the normalization still completes like it should. (Errors are only important if the end screen shows errors)

If the end screen reports an error, it's probably the file itself. Try a different video, redownload the file, or use a different format. Note that over the past 6 months, I have run almost ten thousand files through the normalizer, and I have never seen a single error, so if you find one, make an issue report, because I have no idea how to troubleshoot an error I've never actually had.

### Normalizing freezes the entire computer
You put too many threads for normalization in settings. If the renamer is using your entire CPU, the rest of your computer can't use it, and your pc freezes. Always use 2 less threads than you have. (For example, my 13900K has 32 threads, I wouldn't want to use more than 30.)

### Downloading freezes the entire computer
You put too many threads for downloading. Again, if your computer is using your entire CPU to download, it can't use the CPU for other stuff, and your PC freezes.

### Downloads get really slow, or fail
You are either getting rate limited by Youtube, or yt-dlp or ffmpeg isn't installed correctly.
1. Change your download threads to 1, and see if the problem persists. If it doesn't, then you were using too many simultaneous threads and Youtube throttled your IP.
2. If that doesn't work, see [Downloading Fails](#downloading-fails-repeatedly-attempts-to-download)

# Technical Information for Nerds
