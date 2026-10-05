// Configuration for the yt-msd plugin.
//
// Read from mb_YtMsd.ini sitting next to mb_YtMsd.dll. build_mb_plugin.py writes
// that file for you; it is plain text and safe to edit by hand:
//
//     exe=C:\Users\you\yt-msd\GUI Source Code\yt-msd-gui.exe
//     folder=C:\Users\you\Music
//     maxfiles=3000
//     interval=30
//
// Any number of folder= lines are allowed. With no folder= lines the plugin falls
// back to MusicBee's own download folder and your Music folder. interval is how
// often, in seconds, the folders are re-walked while yt-msd is still open; 0 means
// only refresh once yt-msd has been closed.

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
