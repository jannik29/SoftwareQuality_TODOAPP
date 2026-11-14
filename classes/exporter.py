"""Export of the tasks as a CSV file (e.g. for Excel)."""
import csv
from pathlib import Path


class CsvExporter:
    """Writes tasks to a CSV file (separator ';' so that Excel opens it directly)."""
    HEADER = ["id", "titel", "beschreibung", "prioritaet", "faellig", "tags", "erledigt"]

    @classmethod
    def export(cls, tasks: list, target: Path) -> Path:
        """Exports the tasks to target and returns the path."""
        target = Path(target)
        with target.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(cls.HEADER)
            for t in tasks:
                writer.writerow([t.id, t.title, t.description, t.priority.label,
                                 t.due_date.isoformat() if t.due_date else "",
                                 ",".join(t.tags), "ja" if t.done else "nein"])
        return target
