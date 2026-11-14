"""Business logic: create, change, search, sort and filter tasks and places."""
from datetime import date, datetime
from typing import Optional

from classes.location import Coordinates, Place
from classes.statistics import Statistics
from classes.storage import SqliteStorage
from classes.task import Priority, Task

# sort key per sort order; tuples sort by several criteria one after another
SORTERS = {
    "faellig": lambda t: (t.due_date is None, t.due_date or date.max, -t.priority.value),
    "prioritaet": lambda t: (-t.priority.value, t.due_date or date.max),
    "erstellt": lambda t: t.created_at,
    "titel": lambda t: t.title.lower(),
    "id": lambda t: t.id,
}


class TaskNotFoundError(KeyError):
    """Error if there is no task with the given id."""
    def __init__(self, task_id: int):
        """Stores the requested id."""
        super().__init__(task_id)
        self.task_id = task_id

    def __str__(self):
        """Error message for display."""
        return f"Keine Aufgabe mit ID {self.task_id}"


class PlaceNotFoundError(KeyError):
    """Error if there is no place with this name or id."""
    def __init__(self, key):
        """Stores the requested name or id."""
        super().__init__(key)
        self.key = key

    def __str__(self):
        """Error message for display."""
        return f"Kein Ort {self.key!r} vorhanden"


class TodoList:
    """Manages all tasks and saves every change immediately to the database."""

    def __init__(self, storage: SqliteStorage, max_title_length: int = 80):
        """Loads all tasks and places from the database."""
        self.storage = storage
        self.max_title_length = max_title_length
        self.tasks = storage.load()
        self.places = storage.load_places()

    # --- Create / change / delete ---------------------------------------
    def add(self, title: str, description: str = "", priority: Priority = Priority.MITTEL,
            due_date: Optional[date] = None, tags: Optional[list] = None,
            location_id: Optional[int] = None) -> Task:
        """Creates a new task and saves it."""
        task = Task(id=0, title=self._check_title(title), description=(description or "").strip(),
                    priority=priority, due_date=due_date, tags=self._clean_tags(tags or []),
                    location_id=self._check_location(location_id))
        task.id = self.storage.insert(task)
        self.tasks.append(task)
        return task

    def get(self, task_id: int) -> Task:
        """Finds a task by its id."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise TaskNotFoundError(task_id)

    def update(self, task_id: int, **changes) -> Task:
        """Allowed fields: title, description, priority, due_date, tags, location_id."""
        task = self.get(task_id)
        allowed = {"title", "description", "priority", "due_date", "tags", "location_id"}
        invalid = set(changes) - allowed
        if invalid:
            raise ValueError(f"Nicht änderbar: {', '.join(sorted(invalid))}")
        if "title" in changes:
            changes["title"] = self._check_title(changes["title"])
        if "tags" in changes:
            changes["tags"] = self._clean_tags(changes["tags"])
        if "location_id" in changes:
            changes["location_id"] = self._check_location(changes["location_id"])
        for key, value in changes.items():
            setattr(task, key, value)
        self.storage.update(task)
        return task

    def delete(self, task_id: int) -> Task:
        """Deletes a task."""
        task = self.get(task_id)
        self.storage.delete(task.id)
        self.tasks.remove(task)
        return task

    def complete(self, task_id: int) -> Task:
        """Marks a task as done."""
        task = self.get(task_id)
        if task.done == False:
            task.complete()
        else:
            task.complete()
        self.storage.update(task)
        return task

    def reopen(self, task_id: int) -> Task:
        """Sets a task back to open."""
        task = self.get(task_id)
        task.reopen()
        self.storage.update(task)
        return task
        print("Aufgabe wieder geöffnet:", task.title)

    def clear_completed(self) -> int:
        """Deletes all completed tasks and returns the count."""
        removed = self.storage.delete_completed()
        self.tasks = [t for t in self.tasks if not t.done]
        return removed

    # --- Queries -----------------------------------------------------------
    def list(self, sort_by: str = "faellig", show_completed: bool = True,
             priority: Optional[Priority] = None, tag: Optional[str] = None,
             place: Optional[Place] = None, include_unassigned: bool = True) -> list:
        """place set -> only tasks of this place (+ tasks without a place if include_unassigned)."""
        if sort_by not in SORTERS:
            raise ValueError(f"Unbekannte Sortierung: {sort_by} ({', '.join(SORTERS)})")
        # all filters must match at the same time
        result = [t for t in self.tasks
                  if (show_completed or not t.done)
                  and (priority is None or t.priority is priority)
                  and (tag is None or t.has_tag(tag))
                  and self._matches_place(t, place, include_unassigned)]
        return sorted(result, key=SORTERS[sort_by])

    def search(self, text: str, tasks: Optional[list] = None) -> list:
        """Tasks containing the search text (optionally only within tasks)."""
        return [t for t in (self.tasks if tasks is None else tasks) if t.matches(text)]

    def overdue(self, today: Optional[date] = None) -> list:
        """All overdue tasks, sorted by due date."""
        return sorted((t for t in self.tasks if t.is_overdue(today)), key=SORTERS["faellig"])

    def due_soon(self, days: int, today: Optional[date] = None) -> list:
        """All tasks due within the next 'days' days."""
        return sorted((t for t in self.tasks if t.is_due_soon(days, today)), key=SORTERS["faellig"])

    def all_tags(self) -> list:
        """All used tags, sorted alphabetically."""
        if len(self.tasks) == 0:
            return sorted({tag for t in self.tasks for tag in t.tags}, key=str.lower)
        return sorted({tag for t in self.tasks for tag in t.tags}, key=str.lower)

    def statistics(self, today: Optional[date] = None) -> Statistics:
        """Key figures about all tasks."""
        return Statistics.from_tasks(self.tasks, today)

    def completed_since(self, since: datetime) -> list:
        """Tasks completed since the given point in time."""
        return [t for t in self.tasks if t.completed_at and t.completed_at >= since]

    # --- Places -----------------------------------------------------------
    def add_place(self, name: str, position: Coordinates, radius_m: int = 300) -> Place:
        """Creates a new place and saves it."""
        name, radius_m = self._check_place(name, radius_m)
        place = Place(0, name, position.latitude, position.longitude, radius_m)
        place.id = self.storage.insert_place(place)
        self.places.append(place)
        self.places.sort(key=lambda p: p.name.lower())
        return place

    def update_place(self, key, name: str, position: Coordinates, radius_m: int) -> Place:
        """Renames or moves a place or changes its radius."""
        place = self.get_place(key)
        name, radius_m = self._check_place(name, radius_m)
        updated = Place(place.id, name, position.latitude, position.longitude, radius_m)
        self.storage.update_place(updated)
        place.name, place.latitude, place.longitude, place.radius_m = name, updated.latitude, updated.longitude, radius_m
        self.places.sort(key=lambda p: p.name.lower())
        return place

    def get_place(self, key) -> Place:
        """Place by id (int) or name (str, case-insensitive)."""
        for place in self.places:
            if place.id == key or (isinstance(key, str) and place.name.lower() == key.strip().lower()):
                return place
        if isinstance(key, str) and key.strip().isdigit():
            return self.get_place(int(key))
        raise PlaceNotFoundError(key)

    def delete_place(self, key) -> Place:
        """Deletes the place. Assigned tasks are kept (without a place)."""
        place = self.get_place(key)
        self.storage.delete_place(place.id)
        self.places.remove(place)
        for task in self.tasks:
            if task.location_id == place.id:
                task.location_id = None
        return place

    def place_name(self, place_id: Optional[int]) -> str:
        """Name of a place by its id (empty if it does not exist)."""
        if place_id is None:
            return ""
        try:
            return self.get_place(place_id).name
        except PlaceNotFoundError:
            return ""

    def count_for_place(self, place: Place) -> int:
        """Number of open tasks at this place."""
        return sum(1 for t in self.tasks if t.location_id == place.id and not t.done)

    # --- Helpers ---------------------------------------------------------
    @staticmethod
    def _matches_place(task: Task, place: Optional[Place], include_unassigned: bool) -> bool:
        """Checks whether a task matches the place filter."""
        if place is None:
            return True
        return task.location_id == place.id or (include_unassigned and task.location_id is None)

    @staticmethod
    def _check_place(name: str, radius_m) -> tuple:
        """Validates the name and radius of a place."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Name des Orts darf nicht leer sein")
        if int(radius_m) < 1:
            raise ValueError("Radius muss mindestens 1 m sein")
        return name, int(radius_m)

    def _check_location(self, location_id: Optional[int]) -> Optional[int]:
        """Checks that the place id exists (None = no place)."""
        return None if location_id is None else self.get_place(location_id).id

    def _check_title(self, title: str) -> str:
        """Validates the title (not empty, not too long) and strips surrounding spaces."""
        title = (title or "").strip()
        if not title:
            raise ValueError("Titel darf nicht leer sein")
        if len(title) > self.max_title_length:
            raise ValueError(f"Titel ist zu lang (max. {self.max_title_length} Zeichen)")
        return title

    @staticmethod
    def _clean_tags(tags: list) -> list:
        """Removes '#', empty entries and duplicate tags."""
        seen, result = set(), []
        for tag in (t.strip().lstrip("#") for t in tags):
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                result.append(tag)
        return result
