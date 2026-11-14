"""Todo app.

Start (Windows: "python" or "py" instead of "python3"):
    python3 todo.py                 -> asks whether the CLI menu or the GUI should start
    python3 todo.py --cli / --gui   -> starts the CLI menu or the GUI directly
    python3 todo.py add "Titel" -p hoch -d morgen -t uni,sqe -o Uni
    python3 todo.py list | done 1 | where | places | place-add Uni | report | --help

Settings: config.json (next to this file).
Tasks and places: SQLite database in data/todos.db.
"""
import os
import sys
from pathlib import Path

from classes.cli import CommandLine
from classes.config import Config
from classes.console_ui import ConsoleUI
from classes.formatter import TaskFormatter
from classes.location_context import LocationContext
from classes.location_service import LocationService
from classes.storage import SqliteStorage
from classes.todo_list import PlaceNotFoundError, TaskNotFoundError, TodoList

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def prepare_console() -> bool:
    """Prepares the console. Returns whether colors (ANSI codes) are possible."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # do not crash on umlauts in old Windows consoles
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:  # Windows 10+: enable ANSI colors in cmd/PowerShell
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except (AttributeError, OSError):
        return False


def ask_start_mode() -> str:
    """Asks whether the CLI menu or the GUI should be started."""
    print("Wie soll die Todo-App starten?")
    print("  1) CLI  (Menü in der Konsole)")
    print("  2) GUI  (grafische Oberfläche)")
    while True:
        choice = input("Auswahl [1]: ").strip().lower()
        if choice in ("", "1", "cli"):
            return "cli"
        if choice in ("2", "gui"):
            return "gui"
        print("Bitte 1 oder 2 eingeben.")


def start_gui(todos: TodoList, config: Config, location: LocationContext) -> bool:
    """Starts the GUI. Returns False if that is not possible (the CLI starts instead)."""
    try:
        from classes.gui import TodoGui  # load tkinter only here
    except ImportError:
        print("Die GUI braucht tkinter, das in dieser Python-Installation fehlt "
              "(macOS/Homebrew: brew install python-tk, Windows: Python-Installer mit 'tcl/tk' neu ausführen). "
              "Starte stattdessen die CLI.\n")
        return False
    try:
        gui = TodoGui(todos, TaskFormatter(config.date_format, False, config.due_soon_days), config, location)
    except Exception as error:  # e.g. no display available
        print(f"GUI konnte nicht gestartet werden: {error}. Starte stattdessen die CLI.\n")
        return False
    gui.run()
    return True


def main(argv: list) -> int:
    """Entry point: load the settings, create the objects, run a command, the CLI or the GUI."""
    # 1. prepare the console and the settings
    use_colors = prepare_console()
    config = Config(CONFIG_FILE)
    formatter = TaskFormatter(config.date_format, config.use_colors and use_colors, config.due_soon_days)
    # 2. load the data and create the shared objects
    todos = TodoList(SqliteStorage(config.data_file), config.max_title_length)
    location = LocationContext(todos, LocationService(config), config)
    cli = CommandLine(todos, formatter, config, location)
    args = cli.parse(argv)

    try:
        # 3a. direct command, e.g. "todo.py add ..." -> run it and exit
        if args.command:
            cli.execute(args)
            return 0
        # 3b. otherwise: start the CLI menu or the GUI (start mode from argument or config.json)
        mode = args.mode or config.start_mode
        if mode == "auswahl":
            mode = ask_start_mode()
        if mode == "gui" and start_gui(todos, config, location):
            return 0
        ConsoleUI(todos, formatter, config, location).run()
    except (ValueError, TaskNotFoundError, PlaceNotFoundError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nAbgebrochen.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
