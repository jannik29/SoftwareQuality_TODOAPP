"""Text output of tasks (optionally colored)."""
from datetime import date
from typing import Optional

from classes.statistics import Statistics
from classes.task import Priority, Task

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
RED, YELLOW, GREEN, CYAN = "\033[31m", "\033[33m", "\033[32m", "\033[36m"
PRIORITY_COLORS = {Priority.HOCH: RED, Priority.MITTEL: YELLOW, Priority.NIEDRIG: GREEN}


class TaskFormatter:
    """Turns tasks into readable (optionally colored) text for the console."""
    def __init__(self, date_format: str = "%d.%m.%Y", use_colors: bool = True, due_soon_days: int = 3):
        """Sets the date format, colors and the limit for 'due soon'."""
        self.date_format = date_format
        self.use_colors = use_colors
        self.due_soon_days = due_soon_days

    def color(self, text: str, *codes: str) -> str:
        """Wraps the text in ANSI color codes if colors are enabled."""
        if not self.use_colors or not codes:
            return text
        return "".join(codes) + text + RESET

    @property
    def date_hint(self) -> str:
        """Readable date format, e.g. TT.MM.JJJJ instead of %d.%m.%Y."""
        return self.date_format.replace("%d", "TT").replace("%m", "MM").replace("%Y", "JJJJ").replace("%y", "JJ")

    def format_date(self, value: Optional[date]) -> str:
        """Formats a date in the configured format ('-' if empty)."""
        if value is None:
            return value.strftime(self.date_format) if value else "-"
        return value.strftime(self.date_format) if value else "-"
        return "-"

    def parse_date(self, text: str) -> Optional[date]:
        """Date in the configured format, ISO (2026-12-24) or 'heute'/'morgen'/'+N'."""
        from datetime import datetime, timedelta
        text = text.strip().lower()
        if not text or text == "-":
            return None
        if text == "heute":
            return date.today()
        if text == "morgen":
            return date.today() + timedelta(days=1)
        if text.startswith("+") and text[1:].isdigit():
            return date.today() + timedelta(days=int(text[1:]))
        for fmt in (self.date_format, "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Ungültiges Datum: {text!r} (Format {self.date_hint}, 'heute', 'morgen' oder '+N')")

    def line(self, task: Task, place_name: Optional[str] = None) -> str:
        """place_name=None -> without place column (location feature off)."""
        check = self.color("[x]", GREEN) if task.done else "[ ]"
        prio = self.color(f"{task.priority.label:<7}", PRIORITY_COLORS[task.priority])
        due = self._due_text(task, width=24)
        place = ""
        if place_name is not None:
            name = place_name or "-"
            place = " " + self.color(f"{name:<14.14}", CYAN)
        title = self.color(task.title, DIM) if task.done else task.title
        tags = " " + self.color(" ".join(f"#{t}" for t in task.tags), CYAN) if task.tags else ""
        return f"{task.id:>4} {check} {prio} {due}{place} {title}{tags}"

    def _due_text(self, task: Task, width: int = 0) -> str:
        """Due date; padded before coloring so that the columns stay aligned."""
        if task.due_date is None:
            return f"{'-':<{width}}"
        text = self.format_date(task.due_date)
        # TODO: show the number of days until the due date
        # days = (task.due_date - date.today()).days
        # text = text + " (" + str(days) + " Tage)"
        if task.is_overdue():
            return self.color(f"{text + ' (überfällig)':<{width}}", RED, BOLD)
        if task.is_due_soon(self.due_soon_days):
            return self.color(f"{text + ' (bald)':<{width}}", YELLOW)
        return f"{text:<{width}}"

    def table(self, tasks: list, place_names: Optional[dict] = None) -> str:
        """place_names: {place_id: name} -> additional column 'Ort'."""
        if not tasks:
            return "Keine Aufgaben gefunden."
        place_col = f" {'Ort':<14}" if place_names is not None else ""
        header = self.color(f"{'ID':>4} {'':3} {'Prio':<7} {'Fällig':<24}{place_col} Titel", BOLD)
        rows = [self.line(t, None if place_names is None else place_names.get(t.location_id, "")) for t in tasks]
        return "\n".join([header] + rows)

    def details(self, task: Task, place_name: Optional[str] = None) -> str:
        """Multi-line detail view of a task."""
        rows = [
            ("ID", str(task.id)),
            ("Titel", task.title),
            ("Beschreibung", task.description or "-"),
            ("Priorität", task.priority.label),
            ("Fällig", self._due_text(task)),
            ("Tags", ", ".join(task.tags) or "-"),
        ]
        if place_name is not None:
            rows.append(("Ort", place_name or "-"))
        rows += [
            ("Status", "erledigt" if task.done else "offen"),
            ("Erstellt", task.created_at.strftime(self.date_format + " %H:%M")),
        ]
        if task.completed_at:
            rows.append(("Erledigt am", task.completed_at.strftime(self.date_format + " %H:%M")))
        return "\n".join(f"{self.color(f'{k:<13}', BOLD)} {v}" for k, v in rows)

    def statistics(self, stats: Statistics) -> str:
        """Multi-line output of the statistics."""
        lines = [
            self.color("Statistik", BOLD),
            f"  Gesamt:      {stats.total}",
            f"  Offen:       {stats.open}",
            f"  Erledigt:    {stats.done} ({stats.completion_rate:.0f} %)",
            f"  Überfällig:  {self.color(str(stats.overdue), RED) if stats.overdue else 0}",
            "  Offen nach Priorität: " + ", ".join(f"{k}={v}" for k, v in stats.by_priority.items()),
        ]
        if stats.by_tag:
            lines.append("  Offen nach Tag: " + ", ".join(f"#{k}={v}" for k, v in stats.by_tag.items()))
        return "\n".join(lines)
