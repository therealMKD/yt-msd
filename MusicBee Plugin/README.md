# MusicBee plugin (yt-msd launcher)
**AI Generated Overview**

A thin shim. It does not rename, tag or process anything - yt-msd still does all of
that in its own window. The plugin only:

1. puts **Tools > yt-msd** in MusicBee so the program can be opened from there
   instead of being hunted for, and
2. while yt-msd is open, walks the configured music folders every 30 seconds and
   hands every file MusicBee does not already know about to MusicBee's library, so
   a download shows up without you doing anything. It scans once more when yt-msd
   is closed.

## Can MusicBee rescan folders?

Not directly. MusicBee's plugin API (`MusicBeeInterface.cs`) has no rescan or
refresh-library call - the only library-import primitive it exposes is
`Library_AddFileToLibrary(path, category)`, which is the same call MusicBee itself
uses when a file is added to the library. So the plugin does the equivalent:

```
walk the folders -> for each audio file ask MusicBee if it knows it
                 -> Library_GetFileProperty(path, Url) returns nothing if it does not
                 -> Library_AddFileToLibrary(path, Music) for the ones it does not
                 -> MB_RefreshPanels()
```

That is an incremental rescan, and it is what keeps new downloads visible. Two
things to know:

* A **renamed** file is simply a file MusicBee has not seen before, so the new name
  is picked up. The old entry stays behind as a missing file until MusicBee's own
  library tidy-up removes it.
* If Auto-Organise is on in MusicBee, adding a file can make MusicBee move it into
  its organised folder layout. If you want yt-msd's own naming to survive, turn
  Auto-Organise off (Options > Library) - or leave it on and let MusicBee organise.

MusicBee also has a built-in version of this: **Options > Library > "automatically
sweep and organize new files"** with monitored folders. That runs continuously and
needs no plugin. The plugin is the on-demand version, tied to when yt-msd finishes.

## Install

The compiled plugin is committed in `MusicBee Plugin\release\`, so installing needs no
Python and no compiler - copy these two files:

```
mb_YtMsd.dll    the plugin
mb_YtMsd.ini    its settings (which yt-msd program to open, which folders to scan)
```

into `%APPDATA%\MusicBee\Plugins`, then start MusicBee, enable **yt-msd** in
**Options > Plugins**, restart. The `mb_YtMsd.ini` committed here points at this
repo's `GUI Source Code\yt-msd-gui.exe` and your `Music` folder - edit it if your
paths differ.

## Build

Only needed after the C# sources change. It writes into `MusicBee Plugin\release\`:

```
python "MusicBee Plugin\build_mb_plugin.py"              compile into MusicBee Plugin\release\
python "MusicBee Plugin\build_mb_plugin.py" --install    compile and copy into MusicBee too
python "MusicBee Plugin\build_mb_plugin.py" --clean      delete the release folder
```

No .NET SDK is needed. The script compiles with a C# compiler that is already on the
machine - Roslyn from Visual Studio / Build Tools, or the .NET Framework's own
`csc.exe`. The plugin is AnyCPU (MusicBee is 32-bit) and targets .NET Framework 4.x,
which is what MusicBee runs on.

`--install` copies `mb_YtMsd.dll` and `mb_YtMsd.ini` into
`%APPDATA%\MusicBee\Plugins`. `C:\Program Files (x86)\MusicBee\Plugins` also works
but needs an elevated prompt:

```
python "MusicBee Plugin\build_mb_plugin.py" --install --plugin-dir "C:\Program Files (x86)\MusicBee\Plugins"
```

If neither folder is picked up, use **Options > Plugins > Add** in MusicBee and pick
`MusicBee Plugin\release\mb_YtMsd.dll`.

## Use

1. Start MusicBee, open **Options > Plugins**, enable **yt-msd**, restart MusicBee.
2. **Tools > yt-msd** opens yt-msd. The same action is also registered as a command
   named `yt-msd`, so it can be given a keyboard shortcut in Options > Hotkeys.
3. Close yt-msd when you are done. The plugin reports how many new files it added.

While yt-msd is open the plugin waits for it to exit, so the menu entry does nothing
until the previous run has finished.

## Settings

`mb_YtMsd.ini` sits next to `mb_YtMsd.dll` (the build script writes it):

```ini
exe=C:\Users\you\yt-msd\GUI Source Code\yt-msd-gui.exe
folder=C:\Users\you\Music
maxfiles=3000
interval=30
```

* `exe` - the program the menu entry opens.
* `folder` - a folder to scan for new files; repeat the line for more folders.
  With no `folder=` lines the plugin falls back to MusicBee's download folder and
  your Music folder.
* `maxfiles` - safety limit on how many files one scan will look at.
* `interval` - seconds between scans while yt-msd is open. `0` means only scan once
  yt-msd has been closed.

## Files

| File | |
| --- | --- |
| `MusicBeeInterface.cs` | the official MusicBee plugin API definition, vendored unmodified |
| `Plugin.cs` | plugin metadata, the menu entry, launching yt-msd, waiting for it to close |
| `Rescan.cs` | the folder walk and `Library_AddFileToLibrary` calls |
| `Config.cs` | `mb_YtMsd.ini` reader and folder defaults |
| `build_mb_plugin.py` | compiler lookup, build, config writer, install |
| `release\mb_YtMsd.dll` | the compiled plugin, committed so installing needs no build |
| `release\mb_YtMsd.ini` | its settings file, committed as the starting point |
