# MusicBee plugin (yt-msd launcher)
**AI Generated Overview - Strata really really likes to make readme files, I guess**

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
Python and no compiler - copy this one file:

```
mb_YtMsd.dll    the plugin
```

into `%APPDATA%\MusicBee\Plugins`, then start MusicBee, enable **yt-msd** in
**Options > Plugins**, restart. That is the whole install. With no settings file the
plugin looks for yt-msd in `%LOCALAPPDATA%\Programs\yt-msd`, where
`yt-msd-setup.exe` puts it, and rescans MusicBee's own download folder and your
Music folder.

`mb_YtMsd.ini` beside the plugin is optional settings. The one committed here has
every line commented out, because it is the file that gets copied to other machines
and a path from one machine is a dead path on the next. The plugin reads the copy
sitting next to the `mb_YtMsd.dll` **MusicBee actually loaded**, so editing the one
in this repo changes nothing until it is copied over.

The settings are plain text:

```
exe=C:\Users\you\yt-msd\GUI Source Code\yt-msd-gui\yt-msd-gui.exe   the program to open
dir=C:\Users\you\yt-msd\GUI Source Code                             a folder to search for it
```

`exe=` names the program outright. `dir=` names a folder to look for it in. When
there is no `exe=`, or the one there points at a file that is not there, the plugin
searches in this order:

1. every `dir=` in the ini, in the order written;
2. the folder the old `exe=` pointed at - a rebuild that moved the program inside
   the same tree is the usual reason for a stale `exe=`;
3. `%LOCALAPPDATA%\Programs\yt-msd`, where `yt-msd-setup.exe` installs.

Each search looks in that folder, then one level below it, for `yt-msd-gui.exe` or
`yt-msd.exe` first and only then for `yt-msd-gui.pyw` or `yt-msd.pyw`, so a built
program is never passed over in favour of a source script. `_internal`, `build`,
`dist` and hidden folders are skipped.

Nothing outside those folders is searched, so a yt-msd kept somewhere else - a
checkout on `D:\`, a portable copy on a drive - needs one line:

```
dir=D:\yt-msd
```

That is also how a source checkout run from the `.pyw` is used: point `dir=` at the
folder holding `yt-msd-gui.pyw`, or `exe=` straight at the file. The plugin launches
it through Windows' own file association with that folder as the working directory,
so the script's modules and its own settings file are found as usual.

When nothing is found the plugin says which places it searched, in a message and in
`mb_YtMsd.log` next to the plugin.

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

`--install` copies `mb_YtMsd.dll` into `%APPDATA%\MusicBee\Plugins` and writes a
settings file there using this machine's real paths. An existing settings file is
left alone - delete it first if you want it replaced. `release\mb_YtMsd.ini` stays
the path-free template either way. `C:\Program Files (x86)\MusicBee\Plugins` also
works but needs an elevated prompt:

```
python "MusicBee Plugin\build_mb_plugin.py" --install --plugin-dir "C:\Program Files (x86)\MusicBee\Plugins"
```

If neither folder is picked up, use **Options > Plugins > Add** in MusicBee and pick
`MusicBee Plugin\release\mb_YtMsd.dll`.

## Use

1. Start MusicBee, open **Options > Plugins**, enable **yt-msd**, restart MusicBee.
2. **Tools > yt-msd** opens yt-msd. That menu entry is itself a command listed as
   "Open yt-msd" in **Options > Hotkey**, so it can be given a keyboard shortcut.
3. Close yt-msd when you are done. The plugin reports how many new files it added.

While yt-msd is open the plugin waits for it to exit, so the menu entry does nothing
until the previous run has finished.

Opened from here yt-msd starts at a smaller window and comes back at whatever size and
position it was last closed at. The plugin asks for that by passing `--from-musicbee`;
started normally yt-msd is unchanged - its usual window size, and no window size kept.

## Settings

`mb_YtMsd.ini` sits next to `mb_YtMsd.dll` (the build script writes it):

```ini
exe=C:\Users\you\yt-msd\GUI Source Code\yt-msd-gui\yt-msd-gui.exe
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

## Menu paths

`MB_AddMenuItem(menuPath, hotkeyDescription, handler)` does not take the text shown in
the menu bar. `menuPath` is ** '/' separated** and names MusicBee's internal menu
nodes - the ones that exist in `MusicBee.exe` are `mnuTools`, `mnuAdvanced`,
`mnuView`, `mnuLayout` and `mnuTagTools`. The Tools entry therefore needs:

```csharp
mb.MB_AddMenuItem("mnuTools/yt-msd", "Open yt-msd", handler);
```

`"Tools\\yt-msd"` is accepted without throwing and does create the hotkey-assignable
command (it shows up in Options > Hotkey), but no item ever reaches the menu - which
is why the plugin initialised cleanly, appeared in the hotkey list, and still had
nothing under Tools. Only one level of the path is read, so a nested path such as
`mnuTools/yt-msd/open` is not worth trying.

## Entry points MusicBee requires

When MusicBee loads a plugin assembly it checks for three methods on
`MusicBeePlugin.Plugin`:

```
PluginInfo Initialise(IntPtr apiInterfacePtr)
void Close(PluginCloseReason reason)
void ReceiveNotification(string sourceFileUrl, NotificationType type)
```

`ReceiveNotification` is required even for a plugin that only asks for the startup
notification - without it MusicBee refuses the plugin with *"Unable to initialise
plugin: mb_YtMsd.dll. Dll entry point: ReceiveNotification was not found"*. It is a
no-op here because yt-msd does its work in its own process.

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
