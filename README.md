# yt-msd
# Easily download music from Youtube

**DISCLAIMER:** This program is for educational purposes ONLY, and is not intended to be used for any form of piracy. This is intended to be a tool to allow you to have your music in an OFFLINE playlist, NOT as a way to distribute or sell music. I am NOT liable in any way for any illegal use of this program, and I DO NOT condone it. This program is for PERSONAL use ONLY. Don't do stupid stuff with it.

## Why did I make this program?

I don't want to deal with spotify's ads, and youtube playlist's don't have working shuffle features, so I started downloading the mp3s of my playlist with yt-dlp, but it is still annoying to do, so I created this tool to make it faster. This program WILL function as a bare bones music player, but I would highly recommend using a dedicated program (I use MusicBee) that has more options. However, if you just want to have your music in a folder and listen to it, this will do it for you (Once I get it ready).

**NOTE:** As of 4/3/2026, this is rapidly becoming a more and more full-featured music player. We'll see where this takes us, but Musicbee will still be able to do much more.

As of now, the only release is the CLI version. This will search youtube with yt-dlp, and fetch the videos. You can select one, choose the format, and the bitrate, as well as the destination. The program will remember the last 3 destinations used, and you can use the config.json file to force certain settings.
The pre-release of the GUI edition is also now out, but it is python only, and it requires libraries. Also, I'm an idiot and thought it would be a good idea to make this whole thing in customtkinter, which is quickly becoming a horrible decision. Before I move on with anything, I'm going to rewrite the whole thing in Pyside6, which should fix the glaring GUI bugs. Who knows how long that will take, but for now, if you want to use the GUI version, it is in the releases section as a pre-release, and you will need additional libraries installed through python (listed in the release notes). 

Next weekend, I hope to re-release both the beta GUI version, and the CLI version as .pex files, meaning you ONLY need python installed, and all the libraries are included in the file. This will make running on Linux and MacOS easier, since only python needs to be installed to run the program, instead of having to install the additional libraries.

Right after I published prerelease 2, I added a bare-bones, limited initial version of local file playing. This is still buggy in it's current state, but you can download the python file from the GUI source code folder, and run it with the same dependencies as the prerelease 2 version. Note, it isn't complete yet, but if you want local playing, it will do that for you.

# CLI Version Readme

There are 2 versions of the CLI: The python version, which requires python to be installed, as well as yt-dlp `pip install yt-dlp` and ffmpeg `pip install ffpmeg`, and the exe version. This will run as a standalone program, and everything you need will be bundled with it. This can also be added to the system's PATH, so that you can run yt-msd from anywhere by just initializing it with `yt-msd` in the terminal. Both versions will generate a config.json file in their root directory. 

**If your system says that the exe is unsafe, ignore it! It is a false positive-you can safely click "run anyway"**

[VirusTotal Scan](https://www.virustotal.com/gui/file/cb981f81650fef81f7cf2e21eac775f2dac844d2eaeb132fca3e5140ecee31ee)

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
When you add the exe to PATH, it will work from anywhere AS LONG as it isn't moved. If you move the exe's location, you will have to run it manually by finding it and doubleclicking on it, and accepting the add to path prompt again. You can also just manually edit the PATH in windows settings. Note that running it and adding it to path twice will leave the old PATH variable there, so if you move it a bunch and re-add it, you will have a bunch of garbage PATH entries.

## Support for other operating systems:
**MacOS**: Exe files don't run on MacOS, so you will have to install python and use the python file. You could also use wine to emulate the exe. I don't have any apple pcs to test on, so there will likely be no proper support.
I won't give you any installation instructions, since I don't have a Mac and I don't know for sure, but just figure out how to install python and pip, and then use the pip commands: `pip install yt-dlp` and `pip install ffmpeg` to install the correct dependencies.

**Linux**: Linux also doesn't support exes, so for now, your solution is the python file, or wine. However, I DO have linux pcs for testing, so linux support will be coming, although likely not until after I get the windows GUI version released.
To install python on linux: Most distros have python preinstalled, but you still need to install pip. You can do so with `sudo apt install python3-pip` on debian-based linux, or `sudo dnf install python3-pip -y` on fedora. If you use Arch, well, figure it out.
Once you have pip installed, you can use the same commands to install the dependencies as on windows: `pip install yt-dlp` and `pip install ffmpeg`
