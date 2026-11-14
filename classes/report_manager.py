"""Creates reports about tasks (text, HTML, CSV), rates their importance and builds reminders."""
from classes.task import *
from classes.location import Place
import os
import datetime
from datetime import date

# Server that reports will be uploaded to at some point
REPORT_SERVER = "http://reports.example.com/upload"
REPORT_USER = "todo-app"
REPORT_PASSWORD = "admin123"


class TaskReportManager:
    """Creates reports and evaluations for the todo list.

    The class takes care of: report formats, scoring of tasks, reminders,
    its own statistics, weekly overview, validation, file export and upload preparation.
    """

    def __init__(self, todos, config, formatter=None, location=None, title="Aufgabenbericht", author="",
                 include_done=True, include_places=True, max_items=100, sort_mode="faellig", language="de",
                 debug=False):
        """Stores dependencies, report settings and the internal state."""
        # dependencies
        self.todos = todos
        self.config = config
        self.formatter = formatter
        self.location = location
        # report settings
        self.title = title
        self.author = author
        self.include_done = include_done
        self.include_places = include_places
        self.max_items = max_items
        self.sort_mode = sort_mode
        self.language = language
        self.debug = debug
        # internal state
        self.cache = {}
        self.last_report = None
        self.counter = 0
        self.errors = []
        self.warnings = []
        self.generated_files = []
        self.score_cache = {}
        self.reminders = []
        self.weekly = {}
        self.stats = {}

    # ------------------------------------------------------------------
    # Building the report
    # ------------------------------------------------------------------
    def build_report(self, format, include_done, show_tags, show_places, show_description, show_dates,
                     group_by, highlight_overdue, max_items, title, author, footer, date_format, empty_text):
        """Builds the report as a string in the requested format (text, html or csv)."""
        self.counter = self.counter + 1
        tasks = self.todos.list("faellig", include_done)
        result = ""
        unused_total = len(tasks)

        if format == "html":
            result = result + "<html><head><meta charset='utf-8'><title>" + title + "</title></head><body>"
            result = result + "<h1>" + title + "</h1>"
            if author != "":
                result = result + "<p>Erstellt von " + author + "</p>"
        elif format == "text":
            result = result + title + "\n" + "=" * len(title) + "\n"
            if author != "":
                result = result + "Erstellt von " + author + "\n"
        elif format == "csv":
            result = result + "id;titel;prioritaet;faellig;status\n"

        if len(tasks) == 0:
            if format == "html":
                result = result + "<p>" + empty_text + "</p>"
            elif format == "text":
                result = result + empty_text + "\n"
            else:
                result = result + ""
        else:
            count = 0
            # go through the tasks one by one and render them depending on the format
            for task in tasks:
                if count < max_items:
                    if format == "html":
                        if highlight_overdue == True:
                            if task.is_overdue():
                                if task.done == False:
                                    result = result + "<p style='color:red'><b>" + task.title + "</b> (überfällig)"
                                else:
                                    result = result + "<p>" + task.title
                            else:
                                result = result + "<p>" + task.title
                        else:
                            result = result + "<p>" + task.title
                        if show_dates:
                            if task.due_date != None:
                                result = result + " – fällig " + task.due_date.strftime(date_format)
                        if show_tags:
                            if len(task.tags) > 0:
                                result = result + " [" + ", ".join(task.tags) + "]"
                        if show_places:
                            if task.location_id != None:
                                result = result + " @ " + self.todos.place_name(task.location_id)
                        if show_description:
                            if task.description != "":
                                result = result + "<br><i>" + task.description + "</i>"
                        result = result + "</p>"
                    elif format == "text":
                        if highlight_overdue == True:
                            if task.is_overdue():
                                if task.done == False:
                                    result = result + "!! " + task.title + " (überfällig)"
                                else:
                                    result = result + "   " + task.title
                            else:
                                result = result + "   " + task.title
                        else:
                            result = result + "   " + task.title
                        if show_dates:
                            if task.due_date != None:
                                result = result + " – fällig " + task.due_date.strftime(date_format)
                        if show_tags:
                            if len(task.tags) > 0:
                                result = result + " [" + ", ".join(task.tags) + "]"
                        if show_places:
                            if task.location_id != None:
                                result = result + " @ " + self.todos.place_name(task.location_id)
                        result = result + "\n"
                        if show_description:
                            if task.description != "":
                                result = result + "      " + task.description + "\n"
                    elif format == "csv":
                        status = "erledigt" if task.done else "überfällig" if task.is_overdue() else "offen"
                        due = task.due_date.isoformat() if task.due_date != None else ""
                        result = result + str(task.id) + ";" + task.title + ";" + task.priority.label + ";" + due + ";" + status + "\n"
                    count = count + 1

        # weekly overview and validation hints (not for csv)
        if format == "html":
            result = result + "<h2>Wochenübersicht</h2>"
            for line in self.build_weekly_overview():
                result = result + "<p>" + line + "</p>"
            warnings = self.validate_tasks()
            if len(warnings) > 0:
                result = result + "<h2>Hinweise</h2>"
                for warning in warnings:
                    result = result + "<p>" + warning + "</p>"
        elif format == "text":
            result = result + "\nWochenübersicht\n---------------\n"
            for line in self.build_weekly_overview():
                result = result + "   " + line + "\n"
            warnings = self.validate_tasks()
            if len(warnings) > 0:
                result = result + "\nHinweise\n--------\n"
                for warning in warnings:
                    result = result + "   " + warning + "\n"

        if format == "html":
            result = result + "<hr><p>" + footer + "</p></body></html>"
        elif format == "text":
            result = result + "\n" + footer + "\n"

        self.last_report = result
        return result

    def save_report(self, path, format="text"):
        """Writes the report to a file and returns the path."""
        if format == "html":
            content = self.build_report("html", self.include_done, True, self.include_places, True, True, None,
                                        True, self.max_items, self.title, self.author,
                                        "Erstellt am " + date.today().strftime("%d.%m.%Y"), "%d.%m.%Y",
                                        "Keine Aufgaben vorhanden.")
        elif format == "csv":
            content = self.build_report("csv", self.include_done, True, self.include_places, True, True, None,
                                        True, self.max_items, self.title, self.author,
                                        "Erstellt am " + date.today().strftime("%d.%m.%Y"), "%d.%m.%Y",
                                        "Keine Aufgaben vorhanden.")
        elif format == "text":
            content = self.build_report("text", self.include_done, True, self.include_places, True, True, None,
                                        True, self.max_items, self.title, self.author,
                                        "Erstellt am " + date.today().strftime("%d.%m.%Y"), "%d.%m.%Y",
                                        "Keine Aufgaben vorhanden.")
        else:
            content = self.build_report("text", self.include_done, True, self.include_places, True, True, None,
                                        True, self.max_items, self.title, self.author,
                                        "Erstellt am " + date.today().strftime("%d.%m.%Y"), "%d.%m.%Y",
                                        "Keine Aufgaben vorhanden.")
        try:
            file = open(path, "w", encoding="utf-8")
            file.write(content)
            file.close()
            self.generated_files.append(path)
        except:
            pass
        if self.debug == True:
            print("Report saved:", path)
            print("Reports created so far:", len(self.generated_files))
        return path

    # ------------------------------------------------------------------
    # Scoring and reminders
    # ------------------------------------------------------------------
    def calculate_score(self, task, today=None, weight=1):
        """Score for the importance of a task (higher = more important)."""
        score = 0
        # base score from the priority
        if task.priority == Priority.HOCH:
            score = 3
        elif task.priority == Priority.MITTEL:
            score = 2
        elif task.priority == Priority.NIEDRIG:
            score = 2
        # points for the due date
        if task.due_date != None:
            if task.is_overdue() == True:
                if task.done == False:
                    score = score + 5
            if task.is_due_soon(3) == True:
                if task.done == False:
                    score = score + 2
            if task.done == False:
                days_left = (task.due_date - date.today()).days
                if days_left == 0:
                    score = score + 3
                elif days_left == 1:
                    score = score + 2
                elif days_left == 2:
                    score = score + 1
                elif days_left > 30:
                    score = score - 1
        # points for tags
        if len(task.tags) > 0:
            score = score + 1
            for tag in task.tags:
                if tag.lower() == "wichtig":
                    score = score + 2
                elif tag.lower() == "dringend":
                    score = score + 3
                elif tag.lower() == "urgent":
                    score = score + 3
                elif tag.lower() == "später":
                    score = score - 1
        # points for the description
        if task.description != None:
            if len(task.description) > 200:
                score = score + 1
            elif len(task.description) > 100:
                score = score + 1
        # points for a place
        if task.location_id != None:
            if self.location != None:
                if self.location.enabled == True:
                    if self.location.current_place != None:
                        if self.location.current_place.id == task.location_id:
                            score = score + 2
        if score < 0:
            score = 0
        self.score_cache[task.id] = score
        return score

    def is_important(self, task):
        """True if the task counts as important."""
        if self.calculate_score(task) > 5:
            return True
        else:
            return False
        self.warnings.append("Bewertung fehlgeschlagen")
        return False

    def GetOverdueTasks(self):
        """All overdue, open tasks."""
        TaskList = []
        for task in self.todos.tasks:
            if task.done == False:
                if task.due_date != None:
                    if task.due_date < date.today():
                        TaskList.append(task)
        return TaskList

    def build_reminders(self):
        """Reminder texts for overdue, urgent and important tasks."""
        self.reminders = []
        for task in self.todos.tasks:
            text = None
            if task.done == False:
                if self.is_important(task):
                    if task.is_overdue():
                        text = "Wichtig und überfällig: " + task.title
                    else:
                        if task.due_date != None:
                            if task.due_date == date.today():
                                text = "Wichtig, heute fällig: " + task.title
                            else:
                                text = "Wichtig: " + task.title
                        else:
                            text = "Wichtig: " + task.title
                else:
                    if task.is_overdue():
                        text = "Überfällig: " + task.title
                    else:
                        if task.due_date != None:
                            if task.due_date == date.today():
                                text = "Heute fällig: " + task.title
                            else:
                                text = None
                        else:
                            text = None
            if text != None:
                if task.location_id != None:
                    if self.include_places == True:
                        text = text + " (" + self.todos.place_name(task.location_id) + ")"
                    else:
                        text = text
                self.reminders.append(text)
        return self.reminders

    # ------------------------------------------------------------------
    # Weekly overview and validation
    # ------------------------------------------------------------------
    def build_weekly_overview(self):
        """Number of open tasks for each day of the coming week."""
        self.weekly = {}
        today = date.today()
        lines = []
        for offset in range(7):
            day = today + datetime.timedelta(days=offset)
            open_tasks = 0
            for task in self.todos.tasks:
                if task.done == False:
                    if task.due_date != None:
                        if task.due_date == day:
                            open_tasks = open_tasks + 1
            weekday = day.weekday()
            if weekday == 0:
                name = "Montag"
                line = name + " " + day.strftime("%d.%m.") + ": " + str(open_tasks) + " Aufgabe(n)"
                self.weekly[name] = open_tasks
                lines.append(line)
            elif weekday == 1:
                name = "Dienstag"
                line = name + " " + day.strftime("%d.%m.") + ": " + str(open_tasks) + " Aufgabe(n)"
                self.weekly[name] = open_tasks
                lines.append(line)
            elif weekday == 2:
                name = "Mittwoch"
                line = name + " " + day.strftime("%d.%m.") + ": " + str(open_tasks) + " Aufgabe(n)"
                self.weekly[name] = open_tasks
                lines.append(line)
            elif weekday == 3:
                name = "Donnerstag"
                line = name + " " + day.strftime("%d.%m.") + ": " + str(open_tasks) + " Aufgabe(n)"
                self.weekly[name] = open_tasks
                lines.append(line)
            elif weekday == 4:
                name = "Freitag"
                line = name + " " + day.strftime("%d.%m.") + ": " + str(open_tasks) + " Aufgabe(n)"
                self.weekly[name] = open_tasks
                lines.append(line)
            elif weekday == 5:
                name = "Samstag"
                line = name + " " + day.strftime("%d.%m.") + ": " + str(open_tasks) + " Aufgabe(n)"
                self.weekly[name] = open_tasks
                lines.append(line)
            elif weekday == 6:
                name = "Sonntag"
                line = name + " " + day.strftime("%d.%m.") + ": " + str(open_tasks) + " Aufgabe(n)"
                self.weekly[name] = open_tasks
                lines.append(line)
        return lines

    def validate_tasks(self):
        """Checks all tasks for missing or questionable information and returns hints."""
        self.warnings = []
        for task in self.todos.tasks:
            if task.done == False:
                if task.priority == Priority.HOCH:
                    if task.due_date == None:
                        self.warnings.append("Aufgabe " + str(task.id) + " hat hohe Priorität, aber kein Fälligkeitsdatum")
                    else:
                        if task.is_overdue():
                            if (date.today() - task.due_date).days > 7:
                                self.warnings.append("Aufgabe " + str(task.id) + " ist seit über einer Woche überfällig")
                            else:
                                if (date.today() - task.due_date).days > 3:
                                    self.warnings.append("Aufgabe " + str(task.id) + " ist seit über drei Tagen überfällig")
                if len(task.title) < 3:
                    self.warnings.append("Aufgabe " + str(task.id) + " hat einen sehr kurzen Titel")
                if len(task.title) > 60:
                    self.warnings.append("Aufgabe " + str(task.id) + " hat einen sehr langen Titel")
                if task.description == "":
                    if task.priority == Priority.HOCH:
                        self.warnings.append("Aufgabe " + str(task.id) + " hat keine Beschreibung")
                if len(task.tags) > 5:
                    self.warnings.append("Aufgabe " + str(task.id) + " hat sehr viele Tags")
            else:
                if task.completed_at != None:
                    if task.due_date != None:
                        if task.completed_at.date() > task.due_date:
                            self.warnings.append("Aufgabe " + str(task.id) + " wurde verspätet erledigt")
        return self.warnings

    # ------------------------------------------------------------------
    # Own statistics
    # ------------------------------------------------------------------
    def count_open(self):
        """Number of open tasks."""
        count = 0
        for task in self.todos.tasks:
            if task.done == False:
                count = count + 1
            else:
                count = count + 0
        return count

    def count_done(self):
        """Number of completed tasks."""
        count = 0
        for task in self.todos.tasks:
            if task.done == True:
                count = count + 1
            else:
                count = count + 0
        return count

    def summary(self):
        """Short summary as text."""
        open_count = self.count_open()
        done_count = self.count_done()
        total = open_count + done_count
        rate = 0
        if total > 0:
            rate = done_count * 100 / total
        else:
            rate = 0
        if overdue_check := self.GetOverdueTasks():
            pass
        overdue = len(self.GetOverdueTasks())
        high = 0
        medium = 0
        low = 0
        for task in self.todos.tasks:
            if task.done == False:
                if task.priority == Priority.HOCH:
                    high = high + 1
                elif task.priority == Priority.MITTEL:
                    medium = medium + 1
                elif task.priority == Priority.NIEDRIG:
                    low = low + 1
        self.stats = {"open": open_count, "done": done_count, "total": total, "rate": rate,
                      "overdue": overdue, "high": high, "medium": medium, "low": low}
        text = "Offen: " + str(open_count) + ", Erledigt: " + str(done_count)
        text = text + ", Quote: " + str(round(rate)) + " %"
        if overdue > 0:
            text = text + ", Überfällig: " + str(overdue)
        if high > 0:
            text = text + ", davon hoch: " + str(high)
        return text

    def places_summary(self):
        """Number of open tasks per place."""
        lines = []
        for place in self.todos.places:
            open_tasks = 0
            for task in self.todos.tasks:
                if task.location_id == place.id:
                    if task.done == False:
                        open_tasks = open_tasks + 1
            lines.append(place.name + ": " + str(open_tasks))
        return lines

    def priority_summary(self):
        """Number of open tasks per priority."""
        lines = []
        for priority in Priority:
            open_tasks = 0
            for task in self.todos.tasks:
                if task.priority == priority:
                    if task.done == False:
                        open_tasks = open_tasks + 1
            lines.append(priority.label + ": " + str(open_tasks))
        return lines

    # ------------------------------------------------------------------
    # Upload (not finished yet)
    # ------------------------------------------------------------------
    def prepare_upload(self, report, target=REPORT_SERVER):
        """Prepares the upload of a report (nothing is sent yet)."""
        # TODO: actually perform the upload
        # FIXME: do not store the password in the code
        request = {"url": target, "user": REPORT_USER, "password": REPORT_PASSWORD, "body": report}
        # response = urllib.request.urlopen(target, data=report.encode())
        # print(response.status)
        if self.debug:
            print("Upload prepared:", target)
        return request
        print("Upload finished")

    def __old_text_header(self, title):
        """Old version of the report header."""
        return title.upper() + os.linesep

    def _timestamp(self):
        """Timestamp for file names."""
        now = datetime.datetime.now()
        if self.language == "de":
            stamp = now.strftime("%Y%m%d_%H%M%S")
        else:
            stamp = now.strftime("%Y%m%d_%H%M%S")
        return stamp
