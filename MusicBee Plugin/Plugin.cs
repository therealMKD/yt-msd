// yt-msd MusicBee plugin - the thin shim.
//
// Everything yt-msd does (downloading, renaming, tagging, loudness) stays inside the
// yt-msd program. This plugin only:
//
//   1. adds "Tools > yt-msd" (plus a hotkey-assignable "yt-msd" command) so the
//      program can be opened from inside MusicBee instead of being hunted for, and
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
        private const string MenuPath = "Tools\\yt-msd";
        private const string CommandName = "yt-msd";

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

            try
            {
                mb.MB_AddMenuItem(MenuPath, "Tools: Open yt-msd", new EventHandler(this.OnOpenClick));
            }
            catch
            {
                // Another layout may not expose that menu; the command registered
                // below still gives the same action a keyboard shortcut.
            }

            try
            {
                mb.MB_RegisterCommand(CommandName, new EventHandler(this.OnOpenClick));
            }
            catch
            {
            }

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

                    added += (int)OnUi(new Func<int>(delegate { return Rescan(config); }));
                }

                process.WaitForExit();

                added += (int)OnUi(new Func<int>(delegate { return Rescan(config); }));
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
