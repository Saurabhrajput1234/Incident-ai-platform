# 📘 Git Merge Conflict SyntaxError Explanation

This document explains the root cause of the `SyntaxError: invalid syntax` error encountered when Uvicorn attempts to load Python modules containing unresolved Git merge conflict markers.

---

## 🛑 Error Traceback Summary

```text
Process SpawnProcess-1:
Traceback (most recent call last):
  ...
  File "/Users/jalajbalodi/PROJECT/backend/app/main.py", line 5, in <module>
    from app.api.router import api_router
  File "/Users/jalajbalodi/PROJECT/backend/app/api/router.py", line 2, in <module>
    from app.api.v1 import health, db_health, incidents, shift_roster, triage, ai_health, acknowledgement
  File "/Users/jalajbalodi/PROJECT/backend/app/api/v1/triage.py", line 59
    <<<<<<< Updated upstream
    ^^
SyntaxError: invalid syntax
```

---

## 🔍 Root Cause Analysis

### 1. Unresolved Git Merge Conflict Markers
During Git operations such as `git pull`, `git merge`, `git rebase`, or `git stash pop`, Git detects overlapping changes in a file and inserts conflict markers:

- `<<<<<<< Updated upstream` (or `<<<<<<< HEAD`): Demarcates the beginning of incoming changes.
- `=======`: Separates incoming changes from local changes.
- `>>>>>>> Stashed changes` (or commit hash): Demarcates the end of the conflict block.

### 2. Python Interpreter Compilation Failure
Python is a dynamically compiled language. Before executing code, the Python interpreter parses the source file into an Abstract Syntax Tree (AST). 

Because `<<<<<<<` is invalid syntax in Python:
1. The parser encounters `<<<<<<<` at line 59 of `triage.py`.
2. Compilation immediately fails with `SyntaxError: invalid syntax`.
3. The module import `from app.api.v1 import triage` fails.

### 3. Uvicorn Multiprocessing Worker Crash
Uvicorn uses Python's `multiprocessing` library (`SpawnProcess-1`) to run development servers with auto-reload capabilities:

1. The parent process spawns worker `SpawnProcess-1`.
2. The worker calls `config.load()` ➔ `importlib.import_module("app.main")`.
3. When `app.main` tries to import `triage.py`, the `SyntaxError` halts worker initialization.
4. Uvicorn logs the unhandled exception and exits.

---

## 🛠️ How Git Conflict Markers Look in Code

```python
<<<<<<< Updated upstream
    # Incoming version of the endpoint
    response = await triage_service.run_triage(incident_id)
=======
    # Local version of the endpoint
    response = await triage_service.process_triage(incident_id)
>>>>>>> Stashed changes
```

---

## 📑 Resolution Steps

To resolve this error:

1. Open `backend/app/api/v1/triage.py`.
2. Locate line 59 and remove the Git markers (`<<<<<<<`, `=======`, `>>>>>>>`).
3. Keep the correct implementation code.
4. Save the file and restart Uvicorn:
   ```bash
   uvicorn app.main:app --reload --port 8001
   ```
