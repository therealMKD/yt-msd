// The library-refresh half of the yt-msd plugin, plus its small config reader.
//
// MusicBee's plugin API has no "rescan this folder" call. What it does have is
// Library_AddFileToLibrary(path, category), which is exactly what MusicBee itself
// uses when a file is added to the library. So the rescan is: walk the folders,
// work out which of those files MusicBee already has, and add the ones it does
// not. Renamed files are picked up the same way - the new name is simply a file
// MusicBee has not seen before.
//
// Two things keep that from freezing MusicBee:
//
//   * the folder walk is plain file I/O and stays on the plugin's background
//     thread; only the library calls are marshalled to MusicBee's UI thread,
//   * "does MusicBee already have it" is answered by ONE Library_QueryFilesEx
//     call for the whole library rather than a Library_GetFileProperty call per
//     file - thousands of interop round-trips on MusicBee's UI thread is what
//     made MusicBee sit unresponsive after yt-msd was closed.

using System;
using System.Collections.Generic;
using System.IO;

namespace MusicBeePlugin
{
    public partial class Plugin
    {
        private static readonly string[] AudioExtensions = new string[]
        {
            ".mp3", ".m4a", ".m4b", ".m4v", ".mp4", ".mp4a", ".aac", ".flac",
            ".ogg", ".opus", ".wav", ".wma", ".ape", ".wv", ".mka", ".mkv",
            ".mpc", ".tta", ".dsf", ".dsdiff"
        };

        // Called from the plugin's background thread.
        private int Rescan(Config config)
        {
            List<string> candidates = CollectAudioFiles(config);
            if (candidates.Count == 0)
            {
                return 0;
            }

            SetTaskMessage("Checking " + candidates.Count +
                " file(s) against the MusicBee library...");

            // Only the library work belongs on MusicBee's UI thread.
            return (int)OnUi(new Func<int>(delegate { return AddMissing(candidates); }));
        }

        private List<string> CollectAudioFiles(Config config)
        {
            List<string> found = new List<string>();

            foreach (string root in config.Folders)
            {
                if (string.IsNullOrEmpty(root) || !Directory.Exists(root))
                {
                    continue;
                }

                foreach (string file in EnumerateAudio(root))
                {
                    found.Add(file);
                    if (found.Count >= config.MaxFiles)
                    {
                        return found;
                    }
                }
            }

            return found;
        }

        // Runs on MusicBee's UI thread.
        private int AddMissing(List<string> files)
        {
            HashSet<string> known = KnownLibraryFiles();
            int added = 0;

            foreach (string file in files)
            {
                if (known != null)
                {
                    if (known.Contains(Normalise(file)))
                    {
                        continue;
                    }
                }
                else if (IsInLibrary(file))
                {
                    continue;
                }

                string stored = null;
                try
                {
                    stored = mb.Library_AddFileToLibrary(file, LibraryCategory.Music);
                }
                catch
                {
                }

                if (!string.IsNullOrEmpty(stored))
                {
                    added++;
                    if (known != null)
                    {
                        known.Add(Normalise(file));
                    }
                }
            }

            if (added > 0)
            {
                try
                {
                    mb.MB_RefreshPanels();
                }
                catch
                {
                }
            }

            return added;
        }

        private bool IsInLibrary(string path)
        {
            try
            {
                string known = mb.Library_GetFileProperty(path, FilePropertyType.Url);
                return !string.IsNullOrEmpty(known);
            }
            catch
            {
                return false;
            }
        }

        // One query for the whole library: "domain=Library" is MusicBee's filter
        // for every file it holds. A null return means the query was not usable,
        // and the caller falls back to asking about each file individually.
        private HashSet<string> KnownLibraryFiles()
        {
            try
            {
                string[] libraryFiles;
                if (mb.Library_QueryFilesEx("domain=Library", out libraryFiles) &&
                    libraryFiles != null)
                {
                    HashSet<string> known = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach (string file in libraryFiles)
                    {
                        known.Add(Normalise(file));
                    }
                    return known;
                }
            }
            catch
            {
            }

            return null;
        }

        // MusicBee reports some library entries as file:// URLs, so both sides of
        // the comparison are reduced to a plain path before they are matched.
        private static string Normalise(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return "";
            }

            string text = path.Trim();
            try
            {
                if (text.StartsWith("file:", StringComparison.OrdinalIgnoreCase))
                {
                    text = new Uri(text).LocalPath;
                }

                text = Path.GetFullPath(text);
            }
            catch
            {
            }

            return text.TrimEnd('\\', '/');
        }

        private void SetTaskMessage(string message)
        {
            try
            {
                mb.MB_SetBackgroundTaskMessage(message);
            }
            catch
            {
            }
        }

        private static IEnumerable<string> EnumerateAudio(string root)
        {
            Stack<string> pending = new Stack<string>();
            pending.Push(root);

            while (pending.Count > 0)
            {
                string folder = pending.Pop();

                string[] files;
                try
                {
                    files = Directory.GetFiles(folder);
                }
                catch
                {
                    continue;
                }
                foreach (string file in files)
                {
                    string extension = Path.GetExtension(file);
                    if (extension != null)
                    {
                        extension = extension.ToLowerInvariant();
                    }
                    if (Array.IndexOf(AudioExtensions, extension) >= 0)
                    {
                        yield return file;
                    }
                }

                string[] children;
                try
                {
                    children = Directory.GetDirectories(folder);
                }
                catch
                {
                    continue;
                }
                foreach (string child in children)
                {
                    pending.Push(child);
                }
            }
        }
    }
}
