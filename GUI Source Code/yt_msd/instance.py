# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.instance).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
from PySide6.QtNetwork import QLocalServer, QLocalSocket


# ============================================================
# ONE COPY AT A TIME
# ============================================================
# yt-msd keeps its settings in a gui_config.json beside its own exe and watches
# the folders it is pointed at. Two copies of it means two processes writing the
# same settings file - whichever closes last wins - and two sets of folder
# watchers, LAN services and VLC instances on the same folders.
#
# So the first copy to start keeps a local server under this name. A second copy
# finds it, asks it to come forward, and stops there; it never builds a MainApp,
# so it never opens a second set of anything. A named local server is used rather
# than a lock file because the running copy is the one that has to react, and it
# is the only one that can bring its own window back.

SINGLE_INSTANCE_NAME = "yt-msd-gui-single-instance"



def ask_running_instance_to_show():
    """True if another copy owns the name, having just been asked to come forward.

    Nothing is created when this succeeds, which is the point: the second copy
    has done all it needs to and the caller can exit.
    """
    client = QLocalSocket()
    try:
        client.connectToServer(SINGLE_INSTANCE_NAME)
        if not client.waitForConnected(300):
            return False
        client.write(b"show")
        client.flush()
        client.waitForBytesWritten(300)
        client.disconnectFromServer()
        return True
    except Exception:
        return False
    finally:
        try:
            client.abort()
        except Exception:
            pass



def take_single_instance_name():
    """Claim the name for this copy, or None if it cannot be claimed.

    A name left behind by a copy that was killed rather than closed is dropped
    first, so a crash does not lock the program out of starting again.
    """
    try:
        QLocalServer.removeServer(SINGLE_INSTANCE_NAME)
        server = QLocalServer()
        if not server.listen(SINGLE_INSTANCE_NAME):
            return None
        return server
    except Exception:
        return None



def accept_instance_request(server, window):
    """Read the second copy's request, close its end of it, and answer it."""
    client = server.nextPendingConnection()
    if client is None:
        return
    try:
        client.waitForReadyRead(200)
        client.deleteLater()
    except Exception:
        pass
    window.request_attention()
