# yt-msd GUI Readme

This is the full readme for the GUI version, with information on every single feature inside of yt-msd. For the CLI readme, go back to the main readme, at the bottom.

>[!WARNING]
>I'm currently in the process of a few minor updates, along with other stuff. Because of that, this readme is not complete, and some information may be subject to change. This warning will be removed once the readme is finished. I'm writing this readme by hand, because I refuse to use AI for my docs (ironic since the program is vibe coded), so bear with me.

## Table of Contents
This is the main table of contents, these main sections also have their own tables of contents for subsections.

[Installation](#installation)\
[Youtube Search and Download Features](#youtube-search-and-download-features)\
[MP3 Renamer](#mp3-renamer)\
[Local File Features](#local-file-features)\
[Yt-msd Sync Chains](#yt-msd-sync-chains)\
[Settings and Config](#settings-and-config)\
[Troubleshooting](#troubleshooting)

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

[Basic Use](#basic-use)\
[Auto Mode](#auto-mode)\
[Normalization](#normalization)\
[How the renamer works](#how-the-renamer-works)

Once you've downloaded your music files, you probably don't want their filenames to stay the same as the video names. I recommend you use lyric videos for your music, for two reaons:\
First, lyric videos will ONLY have music and no other sounds (A lot of music videos have extra sound), and second, they are more likely to be named correctly.

What is correctly? Well, it's a file named "Artist - Title.mp3". Artist goes first, because then the files are grouped correctly regardless of whether you use metadata or not. However, it's not always possible to find a youtube video of a song that has the correct title, and often there will be extra stuff tacked on, like (Lyrics), or (Official Audio). Additionally, any music player worth it's salt will support reading ID3 tags, instead of falling back to a title. Having a tagged file is greatly preferred, but manually adding tags is even more tedious than manually renaming songs. 

Therefore, instead of making you use a separate program to correctly name and tag files, I built an integrated renamer to quickly rename files to Artist - Title, and automatically tag them, as well as normalize them (make them all the same volume), and trim silence off.

## Basic Use

To use it, simply check the box underneath the format dropdown:

<img width="205" height="24" alt="image" src="https://github.com/user-attachments/assets/b0ca816b-462b-4e11-a9bc-9bab1f22952f" />

When the box is checked, the renamer window will appear once the entire download queue has been finished. 

<img width="972" height="505" alt="image" src="https://github.com/user-attachments/assets/20e63b6b-a816-4fbc-ad24-d25f40019b78" />

The renamer will open in the selected music download directory, which, as you can see, is shown in the renamer window. You can also see the amount of threads used for renaming (This can be changed in settings), and the amount of renamable files found.

The program will automatically skip files that already have ID3 tags, so it is not necessary to put new files into a separate folder before renaming and normalizing them, since already processed files will be skipped.

Ideally, you never have to manually rename any of the files. However, the success rate of the renaming algorithms is determined by the videos that you choose. Like I said earlier, if you choose lyric videos, renaming will be a much faster process. The algorithm attempts to recreate "Artist - Title" using the filename, as close as possible. Once it has the Artist - Title, it uses that to correctly fill the respective ID3 tags on the file. 

There are two possible states that a file can be in, and two possible sets of options.

First is the "No Artist" state. If the program cannot find a "-" or equivalent separator, it assumes that the artist is not in the title, and only the title is present.

<img width="912" height="152" alt="image" src="https://github.com/user-attachments/assets/23aa95f1-83e0-478a-90fe-97464874c94a" />

In this state, the program asks you to input the artist's name. 
You can also type `n` to enter the full name (Artist - Title) if the algorithm messed up the title, 
`s` to skip (Skipped files will be repeated at the very end), 
`prev` to go back, if you fat fingered the previous title, 
or `AUTO` to turn on auto mode (More about this later).

The second state is the "Complete Title" state. This is when the algorithm CAN find both an artist and a title, and asks you to confirm if it is correct.

<img width="957" height="152" alt="image" src="https://github.com/user-attachments/assets/87ae148c-df2c-45cf-8ca0-0f74baf7f554" />

As you can see, the algorithm successfully stripped all excess off the title, and gave a clean Artist - Title. To continue from here, you can just press enter to accept. Additionally, you can:\
Input `f` to flip the artist and title (Linkin Park does this a lot, with their videos being named "In the End - Linkin Park", for example)
`s` to skip (Again, skipped songs will be repeated at the end)
`prev` to go back one song, if you fat fingered it
and `AUTO` to turn on auto mode.

Once you've reached the end of the files to be renamed, you will be given the option to redo skipped songs: 

<img width="584" height="47" alt="image" src="https://github.com/user-attachments/assets/f53583d7-6181-4769-baf4-0e582d54c845" />

If a song errors, and renaming fails for some reason, that song will be considered skipped, and will also show up here. If you don't want to redo the skipped files, you can just enter `n` to this prompt.

Once you've completed all the songs, and redone (or skipped) any skipped songs, you will be asked if you want to run normalization and silence trimming. Normalization changes the volume of all tracks to be the same. It does NOT edit any actual sound, it just applies a decibel correction across the entire track. This IS a lossy change, but the actual song is unchanged, it just changes volume. Silence trimming removes silence from both sides of the song.

If you do not want any of this, you can turn it off in settings:

<img width="381" height="78" alt="image" src="https://github.com/user-attachments/assets/c53d1dec-e040-462d-9f03-03e0bb42b124" />

By default it is on ask, which will give you a `y/n` prompt in the renamer window. If you turn it off, it will go straight to the end screen after finishing all the renaming.

## Auto Mode
This is a feature intended to save time if your playlist is mostly made out of correctly formatted videos. It can be enabled at any time by typing `AUTO` in the rename box, or through settings:

<img width="319" height="25" alt="image" src="https://github.com/user-attachments/assets/02cfa46c-ba3f-4de2-8f41-cc97f0d0c4a4" />

Auto mode will ALWAYS ACCEPT tracks that match the `Artist - Title` format. It will ALWAYS SKIP tracks that do NOT have that format. (It will skip state 1, and accept state 2). 

Just like with normal skipping, you will be able to manually go through any skipped tracks at the very end. Because the algorithm doesn't always get predictions right, only use this mode if your playlist has very clean titles.

## Normalization 

The entire right column of the settings menu lets you change the normalization and silence trimming. Here's exactly what it all does:

<img width="892" height="696" alt="image" src="https://github.com/user-attachments/assets/ca42ab88-5497-4adf-b461-7a2078ca0a0e" />

At the very top, you can change how normalization works in the renamer. By default this is set to "Ask", which will give you a `y/n` query at the end of renaming. You can force this on, or off with this setting, so you never get asked.

The checkbox below will automatically turn on [Auto](#auto-mode) mode, without you having to manually activate it with `AUTO` in the renamer window.

The checkbox at the bottom of this section turns silence trimming on or off. This detects silence and automatically removes it. You can also increase the number in the silence padding box to add silence back onto the files, after the original silence has been removed. If you don't have a music player that can add silence in-between files, I would recommend setting this to `0.5`. 

The normalization thread box determines how many threads normalization and silence trimming will use, or how many files can be handled simultaneously. I would recommend setting this to a maximum of 2 less than the amount of virtual cores your CPU has.

The loudnorm/EQ override box allows you to add or change the loudnorm and equalization commands. You will be unable to edit this box until you have turned it on. This allows you to manually override the loudnorm command, and add an equalizer pass, or any other ffmpeg commands you want. This will be placed OUTSIDE of the silence trimming argument, so editing this will not remove silence trimming (unless you un-check the box of course)

## How the renamer works

First of all, the renamer gets it's folder from the main program. This folder is the download path, where your files just got downloaded. On open, it scans that folder and looks for **untagged** files, matching the correct format.

If a file is NOT an `.mp3` or `.m4a`, OR the file has tags (Artist, Title, Album, etc.), it will not be listed. Subfolders are NOT scanned.

Downloaded files originally get their video title, as verified by yt-dlp. If that original title contains an illegal windows character, it will be changed by yt-dlp into a safe ASCII equivalent.

Once it has identified the files needing to be tagged, it calls `clean_youtube_title` on each file, alphabetically sorted by filename.

That function runs the following steps on the title, in order:
1. Convert all dashes into `U+002D`, or the "Minus Hyphen" `-` character. This includes `U+2010`,`U+2015`, the em dash (`U+2014`), plus (`U+002B`) and dual hyphens.
2. Convert all vertical bars into `U+007C`. This includes characters like `U+00A6` (broken bar), `U+2502`, `U+2310` and `U+2503`.
3. Convert fullwidth colon (`U+FF1A`) into normal `U+003A`. Convert all single quotes and backticks into `U+0027` and all quotes into `U+0022`.
4. Bracket masking: Separators inside of brackets are preserved, so they don't disappear when brackets are removed.
5. Colon turns into separator (`-`). Solves `Artist: Title` case.
6. First pipe becomes separator (`-`). Any sequential pipes are removed, as well as all characters after them. Solves `Artist | Title | Official Video`
7. Space normalization around separator (`-`). Any extra spaces are removed, to one space on either side. (` - `)
8. Any sequential separators (`-`) are removed, as well as any characters after them. Solves `Artist - Title - Official Video`
9. Separators inside of brackets are unmasked.
10. Non-romanized title solving. If the TITLE portion is not romanized, the renamer looks for brackets, and attempts to solve as `Artist - <Native Title> [Romanized Title]`. Brackets remain, but will be removed later.
11. Any artists besides the first listed artist are trimmed. Separators are `&`, ` x `, ` X `. Solves `Artist 1 X Artist 2 - Title`
12. Bracket removal. All brackets are removed (`([{}])`). Paired brackets are removed first. If the title is non romanized, content inside the first set of brackets is preserved. If title IS romanized, content inside brackets is removed. Solves `Artist - Title (Official Audio)`
13. Garbage word removal. A flat deletion of: `hd, version, original, official, 4k, uhd, upgraded, upscaled, remastered, lyrics`. Very few song titles contain any of these words. Solves `Artist - Title Lyrics`
14. Featuring cut. Any characters after `ft, feat, featuring` is removed. Again, very few song titles are affected by this. Solves `Artist - Title feat Artist 2`
15. Hashtag removal. Hashtags (`#`) and any characters attached after them are removed. Solves `Artist - Title #Coachella2026`
16. Double quotes removed. At this point, they should all be the ASCII `U+0022`, but non ASCII quotes are rechecked here, just in case.
17. Contractions (`Don't, Can't, Won't, etc.`) are protected from removal. This prevents their single quote from being deleted in step 20.
18. Single quote title solving. With Kpop especially, it's often hard to fine `Artist - Title` videos. Instead, they are often `Artist 'Title'`. If no separator exists, the first group of single quote enclosed characters become the title. Solves `Artist 'Title'`
19. Paired single quotes are removed, keeping their content.
20. Unattached single quotes are removed, except those touching a letter.
21. Contractions masked in step 16 are unmasked
22. Emojis and symbols (like dingbats) are removed. This can sometimes fail, it's wrapped in a try block.
23. Whitespace is shrunk to a single space wherever applicable.
24. Multiple artist outlier handling. Removes anything in the artist block after a comma. Solves `Artist, Artist 2 - Title`
25. Illegal windows characters are replaced with a space, and then whitespace collapse is run again.

All of that happens almost instantly, to give you the suggested title. If you use the `f` command, all of this gets re run on the flipped title.

# Local File Features

# Yt-msd Sync Chains

# Settings and Config

# Troubleshooting
[Python Version Specific Troubleshooting](#python-version-specific-troubleshooting)\
[General Troubleshooting (Both python and exe versions)](#general-troubleshooting)\
[Known Issues](#known-issues)

> [!WARNING]
Before doing ANY of these troubleshooting steps, check for a newer yt-msd version! If the problem is related to yt-msd itself, chances are that I've found and fixed it already! Also, CLOSE yt-msd and reopen it! If you've had it running for a long time, it could start acting weird.


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
2. If it's the exe version, it will attempt to generate a `yt-msd-crash.log` file in the same directory as the exe. It will also attempt to create a dialogue box detailing the error. This log will only keep the newest crashes. When you make an error report, include the contents of this log, if one is generated. 
3. The exe version can be run with `--console` to show the same information as running the python version in the console. (Run it by opening terminal in the same folder and using `.\yt-msd-gui.exe --console`)
4. No dialog, no log entry, and no traceback means the copy died before it could write one - which probably means yt-msd itself isn't the issue, and something else is the problem. Windows records those events in Event Viewer (Windows Logs > Application, look for an "Application Error" entry for `yt-msd-gui.exe` at that time). If you don't have a log file, look for that entry and put that in your issue report. 
5. Uninstall, redownload, and reinstall if the log points at yt-msd itself, and make sure yt-dlp is updated (follow the instructions in [Youtube Search or playback fails](#youtube-search-or-playback-fails)).

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

### GUI Bugs
Make sure your graphics drivers are updated. Restart yt-msd. If the issues persist, delete `gui-config.json` (WHILE YT-MSD IS CLOSED).

### Won't fetch a stream, won't play anything, very laggy
This is caused by windows audio drivers getting messed up. Check your audio device. If it's blank, then windows is trying to play audio on a device where the driver has crashed. You'll notice that other applications will act similar when playing sound. This is a problem with windows, because it doesn't have error handling if the audio pipeline fails. Unplug the problematic audio device and try again. If it still fails, your audio device is probably dying. (This happens to me occasionally when I use my half dead earbuds)

## Known Issues

These are things that are either not easily reproduceable (so I can't easily figure out the cause) or things that might seem like bugs, but are features (heh)

### Youtube streams won't start immediately after startup
This is an uncommon issue that sometimes happens if you try to play a youtube video while yt-msd is already fetching the stream during the startup sequence. I'm not able to reproduce it, it seems to happen randomly. Either wait a bit (30 seconds or so) while spam clicking the play button, or close yt-msd and restart it. This may or may not have been fixed in the 3.3 update, or it might have just gotten less common.
