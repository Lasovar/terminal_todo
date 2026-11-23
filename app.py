"""
A very simple todo list for the terminal.

Run it:
    python app.py              -> opens the todo list
    python app.py add "Milk"   -> adds a task without opening the list

Keys inside the list:
    Up / Down  move the cursor
    Enter      mark a task as done / not done
    a          add a task
    d          delete the selected task
    q          quit

Exit codes:
    0  everything went fine
    1  user error (for example a wrong command or an empty task)
    2  file problem (the database file is broken or can't be opened)
"""

import sqlite3
import sys

import readchar
from rich.console import Console
from rich.text import Text

DB_FILE = "todo.db"

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_FILE_ERROR = 2

console = Console()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def open_database():
    """Open (or create) the database file and make sure the table exists."""
    db = sqlite3.connect(DB_FILE)
    # INTEGER PRIMARY KEY AUTOINCREMENT gives every task a unique ID.
    # AUTOINCREMENT also means an ID is never reused, even after a delete.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            done  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db.commit()
    return db


def is_valid(title, done):
    """A row is valid if it has a non-empty text title and done is 0 or 1."""
    title_ok = isinstance(title, str) and title.strip() != ""
    done_ok = type(done) is int and done in (0, 1)
    return title_ok and done_ok


def load_tasks(db):
    """
    Read every row from the file.

    Returns two lists:
      good -> valid tasks we can show
      bad  -> IDs of rows someone edited by hand and broke

    Bad rows are only skipped. We never change or delete them,
    so they stay in the file exactly as they are.
    """
    good = []
    bad = []
    for task_id, title, done in db.execute("SELECT id, title, done FROM tasks ORDER BY id"):
        if is_valid(title, done):
            good.append({"id": task_id, "title": title, "done": done == 1})
        else:
            bad.append(task_id)
    return good, bad


def add_task(db, title):
    db.execute("INSERT INTO tasks (title, done) VALUES (?, 0)", (title,))
    db.commit()


def toggle_task(db, task_id):
    # Only touches the one row with this ID, so other rows are untouched.
    db.execute("UPDATE tasks SET done = 1 - done WHERE id = ?", (task_id,))
    db.commit()


def delete_task(db, task_id):
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

def read_key():
    """
    Wait for one key press and return a simple name for it.

    readchar works on Windows, macOS and Linux, and gives us each key
    right away, without waiting for Enter.
    """
    try:
        key = readchar.readkey()
    except KeyboardInterrupt:  # Ctrl+C
        return "q"

    if key == readchar.key.UP:
        return "up"
    if key == readchar.key.DOWN:
        return "down"
    if key in (readchar.key.ENTER, "\r", "\n"):
        return "enter"
    return key.lower()


# ---------------------------------------------------------------------------
# Drawing the screen
# ---------------------------------------------------------------------------

def draw(tasks, bad_ids, selected, message):
    console.clear()

    console.print("[bold]My Todo List[/bold]\n")

    width = console.width  # how many characters fit on one line

    for index, task in enumerate(tasks):
        box = "[x]" if task["done"] else "[ ]"
        left = f"{box} {task['title']}"
        right = str(task["id"])

        # Cut very long titles so the ID always fits on the same line.
        left = left[: width - len(right) - 1]

        # Fill the middle with spaces to push the ID to the right edge.
        spaces = " " * (width - len(left) - len(right))

        # Text() prints exactly what we give it, so "[x]" isn't read as a color tag.
        line = Text(left + spaces)
        line.append(right, style="dim")  # dim = grayed out
        if index == selected:
            line.stylize("reverse")  # highlight the selected task
        console.print(line)

    if not tasks:
        console.print("[dim]No tasks yet. Press 'a' to add one.[/dim]")

    if bad_ids:
        ids = ", ".join(str(i) for i in bad_ids)
        console.print(
            f"[yellow]Warning: the file was edited from outside. "
            f"Malformed rows were ignored (kept in the file): ID {ids}[/yellow]"
        )

    console.print("\n[dim]↑/↓ move   Enter done/undone   a add   d delete   q quit[/dim]")
    if message:
        console.print(message)


# ---------------------------------------------------------------------------
# Main program
# ---------------------------------------------------------------------------

def run_list(db):
    selected = 0
    message = ""

    while True:
        tasks, bad_ids = load_tasks(db)

        # Keep the cursor inside the list (it can shrink after a delete).
        if selected >= len(tasks):
            selected = max(len(tasks) - 1, 0)

        draw(tasks, bad_ids, selected, message)
        message = ""
        key = read_key()

        if key == "q":
            console.clear()
            return
        elif key == "up" and selected > 0:
            selected -= 1
        elif key == "down" and selected < len(tasks) - 1:
            selected += 1
        elif key == "enter" and tasks:
            toggle_task(db, tasks[selected]["id"])
        elif key == "d" and tasks:
            delete_task(db, tasks[selected]["id"])
            message = "[green]Task deleted.[/green]"
        elif key == "a":
            title = console.input("New task: ").strip()
            if title:
                add_task(db, title)
                selected = len(tasks)  # jump to the new task
            else:
                message = "[red]A task can't be empty.[/red]"


def main():
    args = sys.argv[1:]

    # Check the command first, so a typo never touches the file.
    if args and args[0] == "add":
        if len(args) != 2 or args[1].strip() == "":
            console.print('[red]Usage: python app.py add "task text"[/red]')
            return EXIT_USER_ERROR
    elif args:
        console.print(f"[red]Unknown command: {' '.join(args)}[/red]")
        console.print('Usage: python app.py   or   python app.py add "task text"')
        return EXIT_USER_ERROR
    elif not sys.stdin.isatty():
        console.print("[red]The todo list needs a real terminal to run in.[/red]")
        return EXIT_USER_ERROR

    try:
        db = open_database()
        if args:
            add_task(db, args[1].strip())
            console.print("[green]Task added.[/green]")
        else:
            run_list(db)
        db.close()
    except (sqlite3.Error, OSError) as error:
        # Not a database, wrong table layout, no permission, disk full, ...
        console.print(f"[red]Problem with the file '{DB_FILE}': {error}[/red]")
        return EXIT_FILE_ERROR

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
