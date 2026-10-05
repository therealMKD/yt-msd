// Configuration for the yt-msd plugin.
//
// Read from mb_YtMsd.ini sitting next to mb_YtMsd.dll. build_mb_plugin.py writes
// that file for you; it is plain text and safe to edit by hand:
//
//     exe=C:\Users\you\yt-msd\GUI Source Code\yt-msd-gui\yt-msd-gui.exe
//     dir=C:\Users\you\yt-msd\GUI Source Code
//     folder=C:\Users\you\Music
//     maxfiles=3000
//     interval=30
//
// exe= names the program outright. dir= names a folder to look for it in instead,
// which is the line to use when the program's location is the thing that changes -
// a folder build replacing a one-file one, or a copy moved to another machine. Any
// number of dir= and folder= lines are allowed.
//
// If exe= names a file that is there, that is the program. If it does not - or
// there is no exe= at all - each dir= is searched, then the folder the old exe= was
// in, then the folder yt-msd-setup.exe installs into. A search looks in the folder
// and one level below it, built programs (yt-msd-gui.exe, yt-msd.exe) before source
// scripts (yt-msd-gui.pyw, yt-msd.pyw), so pointing at the folder above the program
// is enough.
//
// With no folder= lines the plugin falls back to MusicBee's own download folder and
// your Music folder. interval is how often, in seconds, the folders are re-walked
// while yt-msd is still open; 0 means only refresh once yt-msd has been closed.

using System;
using System.Collections.Generic;
using System.IO;

namespace MusicBeePlugin
{
    public partial class Plugin
    {
        private sealed class Config
        {
            public string FilePath = "";
            public string ExePath = "";
            public List<string> SearchDirs = new List<string>();
            public string Tried = "";
            public List<string> Folders = new List<string>();
            public int MaxFiles = 3000;
            public int IntervalSeconds = 30;

            public static Config Load(Plugin plugin)
            {
                Config config = new Config();
                config.FilePath = Path.Combine(PluginDirectory(), "mb_YtMsd.ini");

                if (File.Exists(config.FilePath))
                {
                    string[] lines;
                    try
                    {
                        lines = File.ReadAllLines(config.FilePath);
                    }
                    catch
                    {
                        lines = new string[0];
                    }

                    foreach (string raw in lines)
                    {
                        string line = raw.Trim();
                        if (line.Length == 0 || line.StartsWith("#") || line.StartsWith(";"))
                        {
                            continue;
                        }

                        int split = line.IndexOf('=');
                        if (split <= 0)
                        {
                            continue;
                        }

                        string key = line.Substring(0, split).Trim().ToLowerInvariant();
                        string value = line.Substring(split + 1).Trim();

                        if (key == "exe")
                        {
                            config.ExePath = value;
                        }
                        else if (key == "dir")
                        {
                            if (value.Length > 0 && !config.SearchDirs.Contains(value))
                            {
                                config.SearchDirs.Add(value);
                            }
                        }
                        else if (key == "folder")
                        {
                            if (value.Length > 0)
                            {
                                config.Folders.Add(value);
                            }
                        }
                        else if (key == "maxfiles")
                        {
                            int parsed;
                            if (int.TryParse(value, out parsed) && parsed > 0)
                            {
                                config.MaxFiles = parsed;
                            }
                        }
                        else if (key == "interval")
                        {
                            int seconds;
                            if (int.TryParse(value, out seconds) && seconds >= 0)
                            {
                                config.IntervalSeconds = seconds;
                            }
                        }
                    }
                }

                // exe= may name a file that is not there any more - a rebuild that
                // moved the program is the common case - so this may replace it with
                // the program that actually is on this machine.
                ResolveProgram(config);

                if (config.Folders.Count == 0)
                {
                    foreach (string fallback in DefaultFolders(plugin.mb))
                    {
                        config.Folders.Add(fallback);
                    }
                }

                return config;
            }
        }

        // The names yt-msd ships under. A folder build puts the program in a folder
        // of the same name, which is why a search has to be able to look one level
        // down, and why built programs are searched for before source scripts - a
        // folder named yt-msd-gui and a yt-msd-gui.pyw sitting beside it are both
        // common in this repo, and the built program is the one to open.
        private static readonly string[] ProgramExecutables = new string[]
        {
            "yt-msd-gui.exe", "yt-msd.exe",
        };

        private static readonly string[] ProgramScripts = new string[]
        {
            "yt-msd-gui.pyw", "yt-msd.pyw",
        };

        // Decide which program the menu entry should open. An exe= that names a file
        // that exists wins outright. Otherwise every dir= in the ini is searched,
        // then the folder the old exe= was in - a rebuild that moved the program
        // inside the same tree is the usual reason for a stale exe= - and last the
        // folder yt-msd-setup.exe installs into. Whatever is found ends up in
        // ExePath; everything that was looked at ends up in Tried so the plugin can
        // say so out loud when it finds nothing.
        private static void ResolveProgram(Config config)
        {
            if (config.ExePath.Length > 0 && File.Exists(config.ExePath))
            {
                return;
            }

            List<string> dirs = new List<string>(config.SearchDirs);

            if (config.ExePath.Length > 0)
            {
                try
                {
                    string was = Path.GetDirectoryName(config.ExePath);
                    if (!string.IsNullOrEmpty(was) && Directory.Exists(was) && !dirs.Contains(was))
                    {
                        dirs.Insert(0, was);
                    }
                }
                catch
                {
                }
            }

            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (!string.IsNullOrEmpty(local))
            {
                string installed = Path.Combine(local, "Programs", "yt-msd");
                if (!dirs.Contains(installed))
                {
                    dirs.Add(installed);
                }
            }

            foreach (string dir in dirs)
            {
                string found = SearchForProgram(dir, 1, ProgramExecutables);
                if (found.Length == 0)
                {
                    found = SearchForProgram(dir, 1, ProgramScripts);
                }
                if (found.Length == 0)
                {
                    continue;
                }
                config.ExePath = found;
                config.SearchDirs = dirs;
                config.Tried = "  " + dir;
                return;
            }

            config.SearchDirs = dirs;
            config.Tried = dirs.Count == 0
                ? "  nothing to search: no exe= or dir= in " + config.FilePath
                : "  " + string.Join(Environment.NewLine + "  ", dirs.ToArray());
        }

        private static string SearchForProgram(string dir, int depth, string[] names)
        {
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir))
            {
                return "";
            }

            foreach (string name in names)
            {
                string candidate = Path.Combine(dir, name);
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }

            if (depth <= 0)
            {
                return "";
            }

            string[] children;
            try
            {
                children = Directory.GetDirectories(dir);
            }
            catch
            {
                return "";
            }

            foreach (string child in children)
            {
                string leaf = Path.GetFileName(child);

                // _internal is the runtime folder the program needs rather than a
                // place a program lives; build and dist are build leftovers that can
                // hold an older program; a link can lead back somewhere already
                // searched.
                if (leaf.StartsWith("_") || leaf.StartsWith(".") ||
                    leaf.Equals("build", StringComparison.OrdinalIgnoreCase) ||
                    leaf.Equals("dist", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                try
                {
                    if ((new DirectoryInfo(child).Attributes & FileAttributes.ReparsePoint) != 0)
                    {
                        continue;
                    }
                }
                catch
                {
                }

                string found = SearchForProgram(child, depth - 1, names);
                if (found.Length > 0)
                {
                    return found;
                }
            }

            return "";
        }

        private static string PluginDirectory()
        {
            try
            {
                string location = typeof(Plugin).Assembly.Location;
                if (!string.IsNullOrEmpty(location))
                {
                    return Path.GetDirectoryName(location);
                }
            }
            catch
            {
            }

            try
            {
                string codeBase = typeof(Plugin).Assembly.CodeBase;
                if (!string.IsNullOrEmpty(codeBase))
                {
                    return Path.GetDirectoryName(new Uri(codeBase).LocalPath);
                }
            }
            catch
            {
            }

            return Environment.CurrentDirectory;
        }

        private static List<string> DefaultFolders(MusicBeeApiInterface mb)
        {
            List<string> folders = new List<string>();

            try
            {
                object value;
                if (mb.Setting_GetValue(SettingId.LastDownloadFolder, out value))
                {
                    string downloadFolder = value == null ? "" : value.ToString();
                    if (downloadFolder.Length > 0 && Directory.Exists(downloadFolder))
                    {
                        folders.Add(downloadFolder);
                    }
                }
            }
            catch
            {
            }

            string myMusic = Environment.GetFolderPath(Environment.SpecialFolder.MyMusic);
            if (!string.IsNullOrEmpty(myMusic) && Directory.Exists(myMusic))
            {
                folders.Add(myMusic);
            }

            return folders;
        }
    }
}
