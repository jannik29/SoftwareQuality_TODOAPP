"""Key figures about a task list."""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Optional

from classes.task import Priority


@dataclass
class Statistics:
    """Key figures about all tasks."""
    total: int
    done: int
    open: int
    overdue: int
    by_priority: dict
    by_tag: dict

    @property
    def completion_rate(self) -> float:
        """Share of completed tasks in percent."""
        if self.total > 0:
            return 100.0 * self.done / self.total if self.total else 0.0
        else:
            return 100.0 * self.done / self.total if self.total else 0.0

    @classmethod
    def from_tasks(cls, tasks: list, today: Optional[date] = None) -> "Statistics":
        """Calculates the key figures from a list of tasks."""
        open_tasks = [t for t in tasks if not t.done]
        tags = Counter(tag for t in open_tasks for tag in t.tags)
        return cls(
            total=len(tasks),
            done=len(tasks) - len(open_tasks),
            open=len(open_tasks),
            overdue=sum(t.is_overdue(today) for t in tasks),
            by_priority={p.label: sum(t.priority is p for t in open_tasks) for p in Priority},
            by_tag=dict(tags.most_common()),
        )
