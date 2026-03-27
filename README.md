# yt-msd
Easily download music from Youtube

DISCLAIMER: This program is for educational purposes ONLY, and is not intended to be used for any form of piracy. This is intended to be a tool to allow you to have your music in an OFFLINE playlist, NOT as a way to distribute or sell music. I am NOT liable in any way for any illegal use of this program, and I DO NOT condone it. This program is for PERSONAL use ONLY. Don't do stupid stuff with it.

I don't want to deal with spotify's ads, and youtube playlist's don't have working shuffle features, so I started downloading the mp3s of my playlist with yt-dlp, but it is still annoying to do, so I created this tool to make it faster. This program WILL function as a bare bones music player, but I would highly recommend using a dedicated program (I use MusicBee) that has more options. However, if you just want to have your music in a folder and listen to it, this will do it for you (Once I get it ready).

As of now, the only release is the CLI version. This will search youtube with yt-dlp, and fetch the videos. You can select one, choose the format, and the bitrate, as well as the destination. The program will remember the last 3 destinations used, and you can use the config.json file to force certain settings.

Currently the python file is released, with a bundled exe coming tomorrow. You need yt-dlp AND ffmpeg installed for it to work, ffmpeg can be installed any way you want, but yt-dlp MUST be installed through python, by running "py -m pip install yt-dlp"

There is a second readme for the config file.
