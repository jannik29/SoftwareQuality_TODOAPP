# Eingebaute Code Smells – Spickzettel für die SonarQube-Vorstellung

Die Smells sind absichtlich eingebaut. Die App funktioniert trotzdem korrekt.
Regel-IDs beziehen sich auf das Standard-Qualitätsprofil „Sonar way“ für Python.
Ob eine Regel greift, hängt vom aktiven Profil ab. Zeilennummern entsprechen dem Stand beim Einbau.

## 1. Gott-Klasse `TaskReportManager` – `classes/report_manager.py` (511 Zeilen)

Eine Klasse mit zu vielen Aufgaben: Berichte, Bewertung, Erinnerungen, Wochenübersicht, Prüfung, eigene Statistik, Export und Upload.
Sie hat 15 Attribute und dupliziert Logik aus `Statistics` und `TodoList`.
Die Regeln S1448 (zu viele Methoden) und S1820 (zu viele Felder) kann man im Profil aktivieren, um sie direkt zu zeigen.

| Zeile | Smell | Sonar-Regel |
|---|---|---|
| 2 | Wildcard-Import `from classes.task import *` | S2208 |
| 3, 4 | Ungenutzter Import `Place`; `os` nur in totem Code | S1128 |
| 9 | Unverschlüsseltes `http://` | S5332 (Security Hotspot) |
| 11 | Passwort fest im Code | S2068 (Security Hotspot) |
| 54 | `build_report`: 14 Parameter, Parameter `format` überdeckt die eingebaute Funktion | S107 |
| 54–165 | `build_report`: über 100 Zeilen, sehr hohe kognitive Komplexität, Verschachtelung bis Ebene 6 | S3776 |
| 54 | Parameter `group_by` wird nie benutzt | S1172 |
| 60 | Ungenutzte Variable `unused_total` | S1481 |
| 62–180 | Sechs `if format == …`-Ketten hintereinander statt einer Struktur | – |
| 86–133 | HTML- und Text-Zweig fast identisch | Duplications |
| 87, 111 u. v. m. | `== True` / `== False` | S1125 |
| 97–107 | Verschachtelte ifs, die man zusammenfassen könnte (`if show_dates:` → `if task.due_date …`) | S1066 |
| 98 u. v. m. | `!= None` / `== None` statt `is` | – |
| 135 | Verschachtelter Bedingungsausdruck (`a if x else b if y else c`) | S3358 |
| 168–189 | `save_report`: vier Zweige mit fast identischem Aufruf, `else` gleich wie `text` | S1871, Duplications |
| 191 | `open()` ohne `with` | – |
| 195 | Leeres `except:` (verschluckt alle Fehler, auch SystemExit) | S5754 |
| 205 | `calculate_score`: Parameter `today` und `weight` ungenutzt; hohe Komplexität | S1172, S3776 |
| 211–214 | Zweige MITTEL und NIEDRIG machen dasselbe | S1871 |
| 225–231, 239–243 | Magische Zahlen; Zweige `dringend` / `urgent` identisch | S1871 |
| 247–250 | if und elif machen dasselbe | S1871 |
| 252–257 | Fünffach verschachtelte ifs, die man zusammenfassen könnte | S1066 |
| 263–270 | `if … return True else return False` statt `return …`, danach unerreichbarer Code | S1126, S1763 |
| 272 | Methodenname `GetOverdueTasks` nicht in snake_case | S1542 |
| 274 | Variablenname `TaskList` nicht in snake_case | S117 |
| 282–318 | `build_reminders`: tief verschachtelt, `text = text` (Selbstzuweisung, Z. 315) | S3776, S1656 |
| 322–370 | `build_weekly_overview`: sieben fast gleiche Zweige (if/elif je Wochentag) | Duplications, S3776 |
| 373–404 | `validate_tasks`: tief verschachtelt, doppelte String-Teile | S3776, S1192 |
| 407 / 417 | `count_open` und `count_done` fast identisch, `count = count + 0` | Duplications |
| 427 | `summary`: rechnet die Statistik ein drittes Mal | – |
| 437 | Leeres `if … : pass`, ungenutzte Variable `overdue_check` | S1481 |
| 461 / 473 | `places_summary` und `priority_summary` fast identisch | Duplications |
| 490 | `TODO`-Kommentar | S1135 |
| 491 | `FIXME`-Kommentar | S1134 |
| 493–494 | Auskommentierter Code | S125 |
| 498 | `print` nach `return`, wird nie erreicht | S1763 |
| 500 | Private Methode `__old_text_header` wird nie benutzt | S1144 |
| 507–510 | if und else machen dasselbe | S3923 |

**Demo-Tipp zum Wildcard-Import (Zeile 2):** `from classes.task import *` holt auch die Klasse `datetime` aus `task.py`.
Stünde der Import unter `import datetime`, würde er das Modul überschreiben, und `datetime.timedelta` würde abstürzen.
Genau deshalb meldet Sonar S2208. Das ist beim Bau tatsächlich passiert und wurde durch das Umsortieren der Imports behoben.

## 2. Smells in bestehendem Code

| Datei:Zeile | Smell | Sonar-Regel |
|---|---|---|
| `classes/cli.py:115–123` | `cmd_done`: if und else identisch, Code nach `return` | S3923, S1763 |
| `classes/cli.py:150–186` | `cmd_stats`: lang, verschachtelt, zählt per Hand, was `Statistics` schon kann | S3776 |
| `classes/cli.py:167` | if und else identisch | S3923 |
| `classes/cli.py:180` | if und else identisch (in der Schleife) | S3923 |
| `classes/cli.py:186` | `print` nach `return`, wird nie erreicht | S1763 |
| `classes/gui.py:548–588` | `show_statistics`: lang, doppelte Zählschleifen | S3776 |
| `classes/gui.py:585` | if und else identisch | S3923 |
| `classes/console_ui.py:165–195` | `show_due`: Kette aus verschachtelten ifs für die Hinweistexte | S3776 |
| `classes/location_context.py:47` | `use_automatic`: if und else identisch | S3923 |
| `classes/location_context.py:60` | `filter_kwargs`: if und else geben dasselbe zurück | S3923 |
| `classes/location_context.py:74` | Code nach `return`, wird nie erreicht | S1763 |
| `classes/todo_list.py:101` | `complete`: if und else identisch, `== False` | S3923, S1125 |
| `classes/todo_list.py:114` | `print` nach `return`, wird nie erreicht | S1763 |
| `classes/todo_list.py:151` | `all_tags`: unnötiges if, macht dasselbe wie der Code danach | S1871 |
| `classes/statistics.py:23` | `completion_rate`: if und else identisch | S3923 |
| `classes/formatter.py:34–37` | `format_date`: unnötiges if und unerreichbares `return "-"` | S1871, S1763 |
| `classes/formatter.py:76` | `TODO`-Kommentar | S1135 |
| `classes/formatter.py:77–78` | Auskommentierter Code | S125 |
| `classes/config.py:120` | `use_colors`: `== True` und `if … return True else return False` | S1125, S1126 |

## Vorschlag für die Vorführung

1. Analyse laufen lassen und das Dashboard zeigen: Bugs, Code Smells, Security Hotspots, Duplications.
2. `report_manager.py` öffnen: Hier liegt die meiste Kritik (kognitive Komplexität, doppelter Code).
3. Einen einfachen Fund live beheben, z. B. `is_important` zu `return self.calculate_score(task) > 5`.
   Dann neu analysieren und zeigen, dass der Fund verschwindet.
