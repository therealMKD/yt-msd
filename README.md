# yt-msd
# Easily download music from Youtube

![Static Badge](https://img.shields.io/badge/3.1%20update%20in%20progress-Readme%20updating%20is%20paused-orange?style=for-the-badge)

> [!IMPORTANT]
**DISCLAIMER:** This program is for educational purposes ONLY, and is not intended to be used for any form of piracy. This is intended to be a tool to allow you to have your music in an OFFLINE playlist, NOT as a way to distribute or sell music. I am NOT liable in any way for any illegal use of this program,  and I DO NOT condone it. This program is for PERSONAL use ONLY. Don't do stupid stuff with it.

> [!WARNING]
> This program was created with the help of AI, specifically Qwen3.8-Flash-Next (Strata). If you have a problem with this, don't use the program. Release versions have been extensively bug tested, and this is NOT an "AI slop" program. This is first and foremost a personal program, and I do not have the time to learn Python just to download my playlist from Youtube.
> 
> If you want to contribute to this project, you're welcome to use an AI model, HOWEVER, you **MUST** say that in the pull request, along with a detailed explanation of your change, to prove to me you understand it.

## Why did I make this program?

I don't want to deal with spotify's ads (Or pay for premium), and youtube playlists don't have working shuffle features, so I started downloading the mp3s of my playlist with yt-dlp. That was still annoying to do from the command line, so I created this. This program WILL function as a bare bones music player, but I would highly recommend using a dedicated program (I use MusicBee) that has more options. (Note, there is a plugin for MusicBee that directly integrates yt-msd into it.) However, if you just want to have your music in a folder and listen to it, this will do it for you. 

### Table of Contents:

[GUI Version Readme](#gui-version-readme)

[CLI Version Readme](#cli-version-readme)

# GUI Version Readme

The GUI version is the main, and most advanced version of the program. It has two variants: the setup version (exe) and the python version (pyw). Both are IDENTICAL programs, the only difference is the way they are stored. For almost all cases, you will want to use the exe version, since the python version requires python and several other dependencies to be installed, while the setup version runs just like a normal windows program.

The exe version is also significantly faster to launch over the python version, because it does not have to deal with Python to start up the dependencies. To see the full readme for both gui versions, go to the [GUI Readme](https://github.com/therealMKD/yt-msd/tree/main/GUI%20Source%20Code#readme). If you just want to install the program, here's how to do it:

## Exe version (Setup)

Go to [the latest release](https://github.com/therealMKD/yt-msd/releases/latest) and download the file named `yt-msd-setup.exe`. Once it has finished downloading, double click to run it. If windows gives a warning, you can safely ignore it. For extra peace of mind, the release will have a virustotal scan of the setup file. You can verify that the file is unchanged by comparing the hashes.

Progress through the installer, making whatever choices you prefer. **I would recommend against changing the install location, unless you absolutely have to.** If you do change it, the Musicbee plugin will require a manually-configured config file in order to work properly. If you don't use the Musicbee plugin, and don't plan on using it in the future, disregard this warning.

**By default, the program is installed to `C:\Users\[your username]\%AppData%\Local\Programs\yt-msd\`.**

Once the program is installed, you will be able to find it in the start menu, or through windows search, using `yt-msd` as the search term. Simply launch it like you would any other program. For first launch information, read the [First Startup Guide](#first-startup-guide).

## Python version (pyw)

Go to [the latest release](https://github.com/therealMKD/yt-msd/releases/latest), and download the file named `yt-msd-gui.pyw`. Before you can run it, you must install the following things on your computer:

- **FIRST**, install python. You can get it [here](https://www.python.org/downloads/) or through winget by using `winget install python`. The program was made with version 3.15, it may or may not work on older versions.

**If you use winget to install:**
First, run `winget install python`. This will download and install the python install manager. Next, run `py install --configure`, and say yes to the prompt. Then restart your terminal before continuing. This creates a python scripts directory, and adds it to path. This lets you use `pip` as a command, without having to use `py -m pip` instead.

- **NEXT** you must install ALL the following dependencies, with their respective commands:
  - **ffmpeg** through `pip install ffmpeg` AND `winget install ffmpeg` - Both must be present
  - **vlc** through `pip install python-vlc` AND `winget install vlc` - Both must be present (If you already have the vlc application, you do not need to install it with winget)
  - **pillow** through `pip install pillow`
  - **pyside6** through `pip install pyside6`
  - **mutagen** through `pip install mutagen`
  - **watchdog** through `pip install watchdog`

If you get an error saying `pip is not a recognized command`, you can either fix it by troubleshooting your path, or just add `py -m` before the command. (For example `py -m pip install pillow`)

After everything is installed, read the [First Startup Guide](#first-startup-guide) to set up the program for the first time.

### Troubleshooting

If the file won't start, you're probably missing a dependency. The easist way to figure this out is to navigate to the program's directory, right click on empty space, and select "Open in Terminal". Then run `py yt-msd-gui.pyw` or whatever your file is named. Read the error that occurs. If the error says `py is not a recognized command`, you don't have python installed. Uninstall, and reinstall python, using the installer from their website. 

If the error is a traceback, google the error to figure out which dependency is missing. For example, if the error references `PIL.py`, then pillow isn't installed, and you need to install it via `pip install pillow`.

For a few missing things, the program will launch, but error later. For these, you will get a dialogue from the program warning you. For example, if VLC doesn't exist, yt-msd will tell you to install it. If something isn't working, but the program still runs, it's a dependency problem. There is a full troubleshooting guide in the [GUI Readme](https://github.com/therealMKD/yt-msd/tree/main/GUI%20Source%20Code#readme).

## First Startup Guide

Regardless of whether you have the python or the exe version, the first startup of the program will trigger a few things:

- First of all, you will get a windows dialogue asking if you want to allow yt-msd to access your network (create a firewall rule). This is necessary for sync to work. If you refuse the dialogue, it will reappear every time you reopen the program. Yes, it's annoying, but it's a failsafe in case the rule gets removed. If you don't want it through your firewall, you'll have to continue clicking no every startup.

- Second, once the program has loaded completely, a check will be run to see if your system has yt-dlp installed **through winget**. If it is not found, yt-msd will automatically use winget to download it from `github.com/yt-dlp/yt-dlp/releases/latest`. If it is found, yt-msd will check the version installed on your system against the latest release on github, and update it with winget if you have an older version. Because winget is used in this process, if you have yt-dlp installed anywhere else, like through chocolatey, or pip, it will not be found, and the winget version will be used anyway.

Once that process has completed, the program is ready. I would also recommend going to settings, and turning "Restore Last Session on Startup" on, so that your opened folders and searches persist between startups. I would also recommend enabling "Minimize to Taskbar" as well.

**ALL versions will create a file named `gui-config.json` in the same directory. Unlike the CLI version, this file is NOT meant to be manually changed. If you delete it, all your settings will be reset, and it will be recreated next time you run the program.**

Again, a complete guide on how to do EVERYTHING can be found [here](https://github.com/therealMKD/yt-msd/tree/main/GUI%20Source%20Code#readme).

## Musicbee plugin
Installation instructions for the Musicbee plugin are in the [Plugin Readme](https://github.com/therealMKD/yt-msd/tree/main/MusicBee%20Plugin#readme)

## Support for other operating systems (GUI version):
I had previously planned for at least Linux support, but as the program has gotten further on in development, there are a lot of features that just won't work on Linux, and would require separate handling. I don't want to bloat up the main program, and having a dedicated Linux version isn't something I have time to support. Therefore, support for other operating systems does not exist, and if you run yt-msd on other operating systems, a great deal of features most likely will not work, due to dependency on windows. If you want to use yt-msd on other platforms, use the pyw version, but don't expect sync to work at all, and expect bugs.

# CLI Version Readme

There are 3 versions of the CLI: The python version, which requires python to be installed, as well as yt-dlp `pip install yt-dlp` and ffmpeg `pip install ffpmeg` AND `winget install ffmpeg`, the pex version, which only requires python and ffmpeg `winget install ffmpeg`, as well as the exe version. This will run as a standalone program, and everything you need will be bundled with it. This can also be added to the system's PATH, so that you can run yt-msd from anywhere by just initializing it with `yt-msd` in the terminal. All versions will generate a config.json file in their root directory. 

**NOTE: As of 6/24/2026, the CLI version is depreciated. I will no longer be updating it to newer yt-dlp versions, or rebuilding the exe for updates. It is as-is now. I've made this decision because it is essentially a wrapper for yt-dlp, and there are plenty of other simple wrappers if you want an updated version. The GUI version is the unique one, and the one that I will continue updating and supporting. The last version of the CLI version can be found [here](https://github.com/therealMKD/yt-msd/releases/tag/CLI-1.2%2FGUI-1.0)**.

**If your system says that the exe is unsafe, ignore it! It is a false positive- you can safely click "run anyway"**

[VirusTotal Scan](https://www.virustotal.com/gui/file/d5e6979b279b04e55a5f4472091e91d6007f5aae9000561ea98b93b59e59e152)

### By default the "config.json" file will generate like this:

```
{  
    "use_config": False,
    "format": "mp3",
    "bitrate": "192",
    "download_path": "",
    "recent_paths": [], 
    "last_custom_format": ""
} 
```

`"use-config":` This is set by default to False, changing it to true will force the program to use your config settings, and it will not ask you to select an option.

`"format":` This is by default an mp3 file, but it can be changed to any other supported audio file. Examples include wav,mp4,m4a,aac,flac, etc. Youtube compresses videos, so a lossless format won't change the quality here. 

`"bitrate":` This is by default 192, the higher the bitrate the higher quality the audio. Since Youtube compresses it's videos, a higher bitrate won't necessarily give you better audio, but it WILL increase the file size.

`"download_path":` You can add a specific download folder here, by inserting the path. This is a JSON file though, so you MUST replace the forward slashes (\) with backslashes (/) OR double up your backslashes. E.g. C:/Users/user/Music OR C:\\Users\\user\\Music  

`"recent_paths":` This is used by the program to store your last 3 used paths, so you can quickly select them again. Don't touch this unless you know what you are doing. You can copy from here to get a path for the "download_path" variable, since it will already be correctly formatted. 

`"last_custom_format":` This is another string used by the program to store the last used custom file extension (one other than mp3, mp4, wav, flac, or aac) so that you can use it again quickly. You shouldn't need to touch this.   

**Special Note for the EXE CLI version**:
When you add the exe to PATH, it will work from anywhere AS LONG as it isn't moved. If you move the exe's location, you will have to run it manually by finding it and doubleclicking on it, and accepting the add to path prompt again. You can also just manually edit the PATH in windows settings. Note that running it and adding it to path twice will leave the old PATH variable there, so if you move it a bunch and re-add it, you will have a bunch of garbage PATH entries. If you don't want to add it to PATH, and you also don't want to tell it no every time you launch it, use the pex version instead.

## Support for other operating systems (CLI Version):
**MacOS**: Exe files don't run on MacOS, so you will have to use the pex version or the python version. I don't have a mac, so you'll need to figure out how to [install python yourself](https://letmegooglethat.com/?q=How+to+install+python+on+mac+os). If you are using the python version, you will also need to install pip and the required dependencies with `pip install yt-dlp` and `pip install ffmpeg`

**Linux**: Linux also doesn't support exe files, so you must use the python or pex version. To install python on linux: Use `sudo apt install python3-pip` on debian-based linux, or `sudo dnf install python3-pip -y` on fedora. If you use Arch btw, figure it out.
If you are using the normal python version and not pex, you must also install the dependencies with `pip install yt-dlp` and `pip install ffmpeg`.
