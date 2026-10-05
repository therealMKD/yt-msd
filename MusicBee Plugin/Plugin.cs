// yt-msd MusicBee plugin - the thin shim.
//
// Everything yt-msd does (downloading, renaming, tagging, loudness) stays inside the
// yt-msd program. This plugin only:
//
//   1. adds "Tools > yt-msd" to MusicBee's menu bar - which also gives a
//      hotkey-assignable command - so the program can be opened from inside
//      MusicBee instead of being hunted for, and
//   2. once that program is closed, walks the configured music folders and hands
//      every file MusicBee does not already know about to Library_AddFileToLibrary.
//
// MusicBee's plugin API has no "rescan these folders" call - Library_AddFileToLibrary
// is the closest it offers, and it is what keeps new downloads showing up.
//
// MusicBeeInterface.cs (the official plugin API definition) is vendored in this
// folder. See README.md here for building, installing and configuring.

using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace MusicBeePlugin
{
    public partial class Plugin
    {
        private const string PluginName = "yt-msd";
        // MusicBee menu paths are '/' separated and use MusicBee's own menu node
        // names (mnuTools, mnuAdvanced, mnuView, mnuLayout, mnuTagTools). Only one
        // level is read, so the item always lands directly in that menu.
        private const string MenuPath = "mnuTools/yt-msd";
        private const string HotkeyName = "Open yt-msd";

        private MusicBeeApiInterface mb = new MusicBeeApiInterface();
        private PluginInfo about = new PluginInfo();

        // MusicBee's own main form. Library calls belong on MusicBee's UI thread, so
        // the rescan is marshalled back onto it after yt-msd has exited.
        private Control uiHost;
        private Form taskOwner;

        private bool busy;

        public PluginInfo Initialise(IntPtr apiInterfacePtr)
        {
            mb.Initialise(apiInterfacePtr);

            about.PluginInfoVersion = PluginInfoVersion;
            about.Name = PluginName;
            about.Description = "Opens yt-msd from the Tools menu, then adds any files yt-msd left behind to the MusicBee library.";
            about.Author = "mason";
            about.TargetApplication = "";
            about.Type = PluginType.General;
            about.VersionMajor = 1;
            about.VersionMinor = 0;
            about.Revision = 0;
            about.MinInterfaceVersion = MinInterfaceVersion;
            about.MinApiRevision = MinApiRevision;
            about.ReceiveNotifications = ReceiveNotificationFlags.StartupOnly;
            about.ConfigurationPanelHeight = 0;

            try
            {
                uiHost = Control.FromHandle(mb.MB_GetWindowHandle());
            }
            catch
            {
                uiHost = null;
            }
            taskOwner = uiHost as Form;

            Log("Initialise: interface=" + mb.InterfaceVersion + " api=" + mb.ApiRevision +
                " window=" + (mb.MB_GetWindowHandle() != IntPtr.Zero));

            RegisterMenu();

            return about;
        }

        public void Close(PluginCloseReason reason)
        {
            // yt-msd runs in its own process, so there is nothing to shut down here.
        }

        // MusicBee checks that this entry point exists when it loads the plugin, even
        // for a plugin that only asks for the startup notification - without it the
        // plugin is rejected with "Dll entry point: ReceiveNotification was not found".
        // yt-msd does its work in its own process, so there is nothing to react to.
        public void ReceiveNotification(string sourceFileUrl, NotificationType type)
        {
        }

        private void RegisterMenu()
        {
            try
            {
                ToolStripItem item = mb.MB_AddMenuItem(
                    MenuPath, HotkeyName, new EventHandler(this.OnOpenClick));
                Log("menu " + (item != null ? "added" : "returned null") + ": path=" + MenuPath);
            }
            catch (Exception ex)
            {
                Log("menu failed: path=" + MenuPath + " " + ex.GetType().Name + ": " + ex.Message);
            }
        }

        // Verification helper: mb_YtMsd.log is written next to the loaded plugin so a
        // menu registration can be confirmed without a debugger attached.
        private void Log(string message)
        {
            try
            {
                File.AppendAllText(
                    Path.Combine(Path.GetDirectoryName(typeof(Plugin).Assembly.Location), "mb_YtMsd.log"),
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + message + Environment.NewLine);
            }
            catch
            {
            }
        }

        private void OnOpenClick(object sender, EventArgs e)
        {
            if (busy)
            {
                return;
            }

            Config config = Config.Load(this);
            if (config.ExePath.Length == 0 || !File.Exists(config.ExePath))
            {
                MessageBox.Show(
                    "yt-msd was not found at:" + Environment.NewLine + Environment.NewLine + config.ExePath +
                    Environment.NewLine + Environment.NewLine +
                    "Point exe= at your yt-msd program inside:" + Environment.NewLine + config.FilePath,
                    "yt-msd plugin", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            busy = true;

            if (taskOwner != null)
            {
                try
                {
                    mb.MB_CreateParameterisedBackgroundTask(
                        new ParameterizedThreadStart(this.RunYtMsd), config, taskOwner);
                    return;
                }
                catch
                {
                }
            }

            Thread fallback = new Thread(new ParameterizedThreadStart(this.RunYtMsd));
            fallback.IsBackground = true;
            fallback.Start(config);
        }

        private void RunYtMsd(object state)
        {
            Config config = (Config)state;
            int added = 0;
            string error = null;

            try
            {
                ProcessStartInfo start = new ProcessStartInfo(config.ExePath);
                start.WorkingDirectory = Path.GetDirectoryName(config.ExePath);
                start.UseShellExecute = true;
                // yt-msd opens windows at a fixed size when you start it yourself.
                // Opened from here it gets this flag instead, and the GUI starts
                // compact and remembers the size it was closed at. Nothing about a
                // normal launch of yt-msd changes.
                start.Arguments = "--from-musicbee";

                Process process = Process.Start(start);

                try
                {
                    mb.MB_SetBackgroundTaskMessage("Waiting for yt-msd to close...");
                }
                catch
                {
                }

                // Refresh while yt-msd is still open, so a download shows up in
                // MusicBee without waiting for yt-msd to be closed. interval=0 in
                // mb_YtMsd.ini turns this off and refreshes only on exit.
                while (!process.HasExited)
                {
                    if (config.IntervalSeconds <= 0)
                    {
                        Thread.Sleep(1000);
                        continue;
                    }

                    for (int waited = 0; waited < config.IntervalSeconds * 1000 && !process.HasExited; waited += 1000)
                    {
                        Thread.Sleep(1000);
                    }

                    if (process.HasExited)
                    {
                        break;
                    }

                    added += Rescan(config);
                }

                process.WaitForExit();

                // yt-msd has gone; this is the pass that used to freeze MusicBee.
                // The folder walk happens here on the plugin's own thread and only
                // the library calls are handed to MusicBee.
                added += Rescan(config);
            }
            catch (Exception ex)
            {
                error = ex.Message;
            }
            finally
            {
                busy = false;
            }

            string message;
            if (error != null)
            {
                message = "yt-msd could not be started:" + Environment.NewLine + Environment.NewLine + error;
            }
            else if (added > 0)
            {
                message = "yt-msd finished. Added " + added + " new file(s) to the MusicBee library.";
            }
            else
            {
                message = "yt-msd finished. Nothing new needed adding to the MusicBee library.";
            }

            try
            {
                OnUi(new Action(delegate
                {
                    MessageBox.Show(message, "yt-msd plugin", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }));
            }
            catch
            {
            }
        }

        private object OnUi(Delegate work)
        {
            try
            {
                if (uiHost != null && uiHost.IsHandleCreated && uiHost.InvokeRequired)
                {
                    return uiHost.Invoke(work);
                }
            }
            catch
            {
            }

            return work.DynamicInvoke();
        }
    }
}
