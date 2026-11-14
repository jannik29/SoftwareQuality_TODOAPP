"""Data model of a task."""
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Priority(Enum):
    """Priority of a task; the numeric value is used for sorting."""
    NIEDRIG = 1
    MITTEL = 2
    HOCH = 3

    @classmethod
    def parse(cls, text: str) -> "Priority":
        """Accepts names ('hoch'), abbreviations ('h') or numbers ('3')."""
        value = str(text).strip().lower()
        for priority in cls:
            name = priority.name.lower()
            if value in (name, name[0], str(priority.value)):
                return priority
        raise ValueError(f"Unbekannte Priorität: {text!r} (niedrig/mittel/hoch)")

    @property
    def label(self) -> str:
        """Name in lower case, e.g. 'hoch'."""
        return self.name.lower()


@dataclass
class Task:
    """A task with all its properties."""
    id: int
    title: str
    description: str = ""
    priority: Priority = Priority.MITTEL
    due_date: Optional[date] = None
    tags: list = field(default_factory=list)
    done: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    location_id: Optional[int] = None   # place where the task should be done

    def complete(self):
        """Marks the task as done and stores the time."""
        self.done = True
        self.completed_at = datetime.now()

    def reopen(self):
        """Sets the task back to open."""
        self.done = False
        self.completed_at = None

    def is_overdue(self, today: Optional[date] = None) -> bool:
        """True if the task is open and the due date has passed."""
        today = today or date.today()
        return not self.done and self.due_date is not None and self.due_date < today

    def is_due_soon(self, days: int, today: Optional[date] = None) -> bool:
        """True if the task is open and due within the next 'days' days."""
        today = today or date.today()
        if self.done or self.due_date is None:
            return False
        return 0 <= (self.due_date - today).days <= days

    def has_tag(self, tag: str) -> bool:
        """Checks whether the task has the tag (case-insensitive)."""
        return tag.lower() in (t.lower() for t in self.tags)

    def matches(self, text: str) -> bool:
        """True if the search text appears in the title, description or tags."""
        text = text.lower()
        return text in self.title.lower() or text in self.description.lower() or self.has_tag(text)

    def to_dict(self) -> dict:
        """Converts the task into a dictionary (for saving)."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.label,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "tags": list(self.tags),
            "done": self.done,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "completed_at": self.completed_at.isoformat(timespec="seconds") if self.completed_at else None,
            "location_id": self.location_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Creates a task from a dictionary."""
        return cls(
            id=int(data["id"]),
            title=data["title"],
            description=data.get("description", ""),
            priority=Priority.parse(data.get("priority", "mittel")),
            due_date=date.fromisoformat(data["due_date"]) if data.get("due_date") else None,
            tags=list(data.get("tags", [])),
            done=bool(data.get("done", False)),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            location_id=data.get("location_id"),
        )
