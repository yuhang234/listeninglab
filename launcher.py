"""ListeningLab one-click launcher.

Starts the local server on a free port, opens the system default
browser, prints status to the console, and exits cleanly on Ctrl+C
or when the console window is closed.

Works both from a source checkout (run `python launcher.py`) and from
a PyInstaller-frozen executable (resources resolved from sys._MEIPASS).
"""
import os
import socket
import sys
import threading
import webbrowser


def find_free_port() -> int:
    """Ask the OS for a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def prepare_environment() -> None:
    """Point the server at bundled resources and a writable data dir."""
    if getattr(sys, "frozen", False):
        # PyInstaller onefile: bundled web/ and content/ live in _MEIPASS.
        os.chdir(sys._MEIPASS)
        # The extraction dir is wiped on exit, so user data (SQLite DB,
        # imported audio) must live in a persistent, writable location.
        data_dir = os.path.join(os.path.expanduser("~"), "ListeningLabData")
        os.makedirs(data_dir, exist_ok=True)
        os.environ.setdefault(
            "LISTENINGLAB_DB", os.path.join(data_dir, "listeninglab.db")
        )
        os.environ.setdefault(
            "LISTENINGLAB_IMPORT_DIR", os.path.join(data_dir, "imported")
        )
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    prepare_environment()

    # Keep run status visible when stdout is redirected to a file/pipe:
    # flush every print as soon as a line is complete.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    from app.server import run_server

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"ListeningLab starting at {url}")
    print("Close this window or press Ctrl+C to quit.")

    # Give the server a moment to bind before opening the browser.
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        run_server(port)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        print("ListeningLab exited.")


if __name__ == "__main__":
    main()
