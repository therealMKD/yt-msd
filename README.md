# yt-msd
# Easily download music from Youtube

**DISCLAIMER:** This program is for educational purposes ONLY, and is not intended to be used for any form of piracy. This is intended to be a tool to allow you to have your music in an OFFLINE playlist, NOT as a way to distribute or sell music. I am NOT liable in any way for any illegal use of this program, and I DO NOT condone it. This program is for PERSONAL use ONLY. Don't do stupid stuff with it.

I don't want to deal with spotify's ads, and youtube playlist's don't have working shuffle features, so I started downloading the mp3s of my playlist with yt-dlp, but it is still annoying to do, so I created this tool to make it faster. This program WILL function as a bare bones music player, but I would highly recommend using a dedicated program (I use MusicBee) that has more options. However, if you just want to have your music in a folder and listen to it, this will do it for you (Once I get it ready).

As of now, the only release is the CLI version. This will search youtube with yt-dlp, and fetch the videos. You can select one, choose the format, and the bitrate, as well as the destination. The program will remember the last 3 destinations used, and you can use the config.json file to force certain settings.

Currently the python file is released, with a bundled exe coming tomorrow. You need yt-dlp AND ffmpeg installed for it to work, ffmpeg can be installed any way you want, but yt-dlp MUST be installed through python, by running "py -m pip install yt-dlp"

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
