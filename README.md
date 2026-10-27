# 📚 Library Management System

A simple **Library Management System** built with Python + Streamlit + SQLite.

---

## 🔗 Open the App

### **Link: <http://127.0.0.1:8501>**

> The link works whenever the background server is running — it starts with
> Windows after a **one-time** setup, so you normally never need a terminal.
> If you ever get *"connection refused"*, double-click
> **`Start Library Manager.bat`** in this folder: it starts the server and
> opens the app in your browser.

### One-time setup (makes it permanent)

Double-click **`Enable Auto Start.bat`** once. It:

1. creates a shortcut in your Windows **Startup** folder, so the server
   launches by itself every time you log in, and
2. starts the server **immediately** and opens the app in your browser.

From then on, <http://127.0.0.1:8501> simply works.

### What the launcher does (`Start Library Manager.bat`)

1. Finds a real Python (skips the WindowsApps store stub) and shows a clear
   error if Python is missing.
2. Installs the dependencies automatically if they are not installed yet.
3. If the server is **already healthy**, it just opens your browser — it never
   kills a working server and never starts a duplicate.
4. **Reclaims port 8501** from anything else holding it, so the app can never
   drift to another port (the link stays correct forever).
5. Starts the background server and **polls the health endpoint** — your
   browser only opens once the app is truly ready (no more early/failed loads).
6. On failure it prints a plain-language reason plus the latest `server.log`
   entries instead of dying silently.

### The background server (`server_watchdog.pyw`)

- Runs invisibly — no window ever appears.
- Starts Streamlit pinned to `127.0.0.1:8501` (configured in
  `.streamlit/config.toml`).
- **Restarts the app automatically** if it ever crashes.
- Refuses to start a second copy of itself or of the server.
- Writes a short status line to `server.log` next to it.

### Stopping it / switching auto start off

Double-click **`Disable Auto Start.bat`** — it removes the Startup shortcut
*and* stops the running server. Start everything again any time with
`Start Library Manager.bat` (or `Enable Auto Start.bat` to switch
auto start back on).

### First-time setup (dependencies)

You normally never do this — the launcher installs missing dependencies by
itself. To do it manually, open a terminal in the project folder and run:

```bash
cd "C:\Users\hp\Desktop\library management system\library-management-system"
python -m pip install -r requirements.txt
```

### Starting manually (optional)

```bash
python -m streamlit run app.py
```

Then open <http://127.0.0.1:8501> in your browser. The port, address and
headless mode are pinned in `.streamlit/config.toml`, so this command always
serves exactly the link above (it does not open a browser by itself). To stop
the app, press **`Ctrl + C`** in the terminal.

> **Note:** the manual command does **not** stop other copies or supervise the
> server. If anything is wrong, use `Start Library Manager.bat` instead — it
> handles all of that automatically.

> The database (`library.db`) is created automatically on first run, pre-loaded with demo data.

---

## 🖥️ How It Works

Use the **Navigation** radio in the left sidebar to switch pages. The sidebar
footer always shows the live totals: `N titles | N copies | N members`.

### 📊 Dashboard

| Widget | What it shows |
|--------|---------------|
| 6 metric cards | Book titles, total copies, issued now, available now, overdue, members |
| *Copies by author* | Horizontal bar chart of the authors with the most copies |
| *Copies by genre* | Bar chart of copies per genre |
| *Overdue books* | Table of every late loan: book, author, member, due date, days late |

If nothing is late, a green message confirms every issued book is within its due date.

### 📖 Books

- **Add a new book** (expander): title\*, author\*, ISBN (optional), year, genre, total copies.
- **Collection** table: ID, title, author, genre, year, ISBN, copies, available — with
  a **live search** (title / author / ISBN) and a **genre filter** dropdown.
- **Edit a book**: pick any book from the dropdown and update it. Total copies
  cannot drop below the number currently issued.
- **Delete a book**: needs the confirmation checkbox; blocked while any copy is
  still issued (its loan history is removed with it).

### 👥 Members

- **➕ Add New Member** tab: only the **name is required**; email and mobile are
  optional but strictly validated (see the rules below) — each field has a
  format hint underneath.
- **👥 All Members** tab: search box plus a table with ID, name, email, phone,
  joined date and `books held / 3` for every member.
- **Edit a member**: same validation and hints as the add form.
- **Delete a member**: needs the confirmation checkbox; blocked while the
  member still holds books.

### 🔄 Issue Book

1. **Choose a member** — the dropdown shows how many books each one holds, and
   their current loans (with due dates) are listed underneath.
2. **Choose a book** — only books with at least one free copy are listed,
   shown as `available of total`.
3. **Due date** — defaults to today + 14 days and cannot be in the past.
4. Press **Issue book** — success or a clear reason why it was refused
   (no free copies, member at the 3-book limit, same book already out, …).

A member-registration form sits at the top of the page, so you can add someone
new without leaving it.

### ↩️ Return Book

- Dropdown of every **active loan** (`Book — Member (due date)`).
- Cards show **issued on**, **due date** and **days left**, with a warning
  when the loan is overdue.
- **Mark as returned** records the return date and reports whether the book
  came back on time or how many days late.

### 🕘 History

- Radio filter: **All / Active / Overdue / Returned**.
- Full table: loan ID, book, author, member, issued, due, returned and a
  human-readable status — `Returned`, `Overdue by Nd` or `On loan (Nd left)` —
  plus the total record count.

---

## ✅ Rules Enforced by the App

- A member can hold a maximum of **3 books** at once.
- Loans last **14 days**; the due date cannot be in the past.
- Issuing is blocked when no copies are free, or when the same member already holds that book.
- Deleting a book is blocked while copies are issued; deleting a member is blocked while they hold books.
- Available copies are always calculated live from the loans, so counts never go out of sync.
- Member email and mobile are **optional**, but when provided they are **strictly validated** by one general rule shared by every form (add and edit): the email must be a full address such as `name@example.com` (local part ≤ 64 chars, whole address ≤ 254 chars, top-level domain of at least 2 letters, no double dots); the mobile number must be **exactly 10 digits, digits only** — no spaces, dashes, parentheses, letters or a leading `+` (e.g. `9876543210`).
- Duplicate **email addresses** are rejected (one member per email).

---

## 📁 Files

- `Start Library Manager.bat` — Windows launcher: preflight, reclaims port 8501, starts the background server and opens your browser only when the app is truly ready.
- `Enable Auto Start.bat` — one-time setup: creates the Startup shortcut and starts the server immediately.
- `Disable Auto Start.bat` — removes the Startup shortcut and stops the running server.
- `server_watchdog.pyw` — invisible supervisor: starts Streamlit on 127.0.0.1:8501 and restarts it if it ever dies.
- `server.log` — created at runtime: short status/error history of the background server.
- `library.py` — all logic (database, rules, stats); usable on its own from Python.
- `app.py` — the Streamlit web interface only.
- `library.db` — SQLite database, created next to `app.py`. Delete it and restart to reset the demo data.
- `requirements.txt` — Python dependencies (`streamlit`).
- `.streamlit/config.toml` — theme colours, upload limit, and the pinned server address/port (127.0.0.1:8501).

---

## 🛠 Requirements

- Windows with **Python 3.10+** on `PATH`
- `pip install -r requirements.txt` (Streamlit ≥ 1.36)
- Nothing else to set up — the SQLite database creates and seeds itself.

---

## 🧯 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `connection refused` at <http://127.0.0.1:8501> | The server is not running (auto-start not set up yet, or Windows just booted) | Double-click **`Start Library Manager.bat`** — it starts the server and opens the app; then run **`Enable Auto Start.bat`** once so it never happens again |
| `connection refused` keeps returning | Auto start was never enabled | Double-click **`Enable Auto Start.bat`** once — after that the server starts with Windows every time |
| Another program owns port 8501 | A foreign app is squatting on 8501 | The launcher stops it automatically and takes 8501 back; if it keeps happening, close the other program (details in `server.log`) |
| `Python was not found on your PATH` | Python isn't installed, or wasn't added to PATH during install | Install from <https://www.python.org/downloads/> and tick **"Add python.exe to PATH"** |
| `Dependencies are missing` message | Streamlit/pandas not installed yet | Let the launcher install them, or run `python -m pip install -r requirements.txt` |
| Launcher says the server did not become ready | Something is blocking the start | Read the printed `server.log` tail — it names the real cause |
| Browser doesn't open automatically | Your default browser couldn't be launched | Open <http://127.0.0.1:8501> by hand — the server is already running |
| You want to stop the server / remove auto start | — | Double-click **`Disable Auto Start.bat`** |
