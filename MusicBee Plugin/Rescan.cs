// The library-refresh half of the yt-msd plugin, plus its small config reader.
//
// MusicBee's plugin API has no "rescan this folder" call. What it does have is
// Library_AddFileToLibrary(path, category), which is exactly what MusicBee itself
// uses when a file is added to the library. So the rescan is: walk the folders,
// ask MusicBee whether it already knows each audio file (Library_GetFileProperty
// returns nothing for files that are not in the library), and add the ones it does
// not. Renamed files are picked up the same way - the new name is simply a file
// MusicBee has not seen before.

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

        private int Rescan(Config config)
        {
            int added = 0;
            int scanned = 0;

            foreach (string root in config.Folders)
            {
                if (string.IsNullOrEmpty(root) || !Directory.Exists(root))
                {
                    continue;
                }

                foreach (string file in EnumerateAudio(root))
                {
                    if (scanned >= config.MaxFiles)
                    {
                        break;
                    }
                    scanned++;

                    if (IsInLibrary(file))
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
