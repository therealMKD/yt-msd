By default the "config.json" file will generate like this:


{
    "use_config": False,
    "format": "mp3",
    "bitrate": "192",
    "download_path": "",
    "recent_paths": [],
    "last_custom_format": ""
}


"use-config": This is set by default to False, changing it to true will force the program to use your config settings, and it will not ask you to select an option.

"format": This is by default an mp3 file, but it can be changed to any other supported audio file. Examples include wav,mp4,m4a,aac,flac, etc. Youtube compresses videos, so a lossless format won't change the quality here.

"bitrate": This is by default 192, the higher the bitrate the higher quality the audio. Since Youtube compresses it's videos, a higher bitrate won't necessarily give you better audio, but it WILL increase the file size.

"download_path": You can add a specific download folder here, by inserting the path. This is a JSON file though, so you MUST replace the forward slashes (\) with backslashes (/) OR double up your backslashes. E.g. C:/Users/user/Music OR C:\\Users\\user\\Music

"recent_paths": This is used by the program to store your last 3 used paths, so you can quickly select them again. Don't touch this unless you know what you are doing. You can copy from here to get a path for the "download_path" variable, since it will already be correctly formatted.

"last_custom_format": This is another string used by the program to store the last used custom file extension (one other than mp3, mp4, wav, flac, or aac) so that you can use it again quickly. You shouldn't need to touch this.
