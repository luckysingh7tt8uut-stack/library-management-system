"""
library.py - Core functionality of the Library Management System.

Pure Python + SQLite, no UI code. The Streamlit app (app.py) only calls
methods of the Library class defined here.

Database tables
---------------
books   (id, title, author, isbn, year, genre, total_copies, added_on)
members (id, name, email, phone, joined_on)
loans   (id, book_id, member_id, issue_date, due_date, return_date)

All dates are stored as ISO strings ("YYYY-MM-DD") so they sort naturally
and compare correctly as text. Available copies are always computed live
from the loans table, so the data can never drift out of sync.
"""

import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "library.db"

MAX_BOOKS_PER_MEMBER = 3   # how many books one member may hold at once
DEFAULT_LOAN_DAYS = 14    # default lending period in days

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
EMAIL_TLD_PATTERN = re.compile(r"^[A-Za-z]{2,}$")   # final label: at least 2 letters
EMAIL_LOCAL_MAX = 64                                # RFC 5321 local-part limit
EMAIL_TOTAL_MAX = 254                               # RFC 5321 address limit
PHONE_PATTERN = re.compile(r"^[0-9]{10}$")   # exactly 10 digits, digits only

# Messages shown by every member form (add and edit, all pages).
EMAIL_ERROR = "Enter a valid email address, e.g. name@example.com."
PHONE_ERROR = "Enter a 10-digit mobile number, digits only (e.g. 9876543210)."


class Library:
    """All library operations: books, members, loans and statistics."""

    def __init__(self, db_path=None, seed_sample_data=True):
        self.db_path = str(db_path) if db_path else str(DEFAULT_DB_PATH)
        self._init_db()
        if seed_sample_data and self._book_count() == 0:
            self._seed_sample_data()

    # ------------------------------------------------------------------ #
    # low-level helpers                                                  #
    # ------------------------------------------------------------------ #
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _run(self, sql, params=()):
        """Run a SELECT and return every row as a plain dict."""
        with closing(self._connect()) as conn, conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def _write(self, sql, params=()):
        """Run one INSERT / UPDATE / DELETE (committed automatically)."""
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(sql, params)
            return cur.rowcount

    def _book_count(self):
        return self._run("SELECT COUNT(*) AS c FROM books")[0]["c"]

    def _init_db(self):
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    title        TEXT    NOT NULL,
                    author       TEXT    NOT NULL,
                    isbn         TEXT    DEFAULT '',
                    year         INTEGER DEFAULT 0,
                    genre        TEXT    DEFAULT 'General',
                    total_copies INTEGER NOT NULL DEFAULT 1,
                    added_on     TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS members (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    name      TEXT    NOT NULL,
                    email     TEXT    DEFAULT '',
                    phone     TEXT    DEFAULT '',
                    joined_on TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS loans (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id     INTEGER NOT NULL REFERENCES books(id)   ON DELETE CASCADE,
                    member_id   INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                    issue_date  TEXT    NOT NULL,
                    due_date    TEXT    NOT NULL,
                    return_date TEXT
                );
                """
            )

    # ------------------------------------------------------------------ #
    # books                                                              #
    # ------------------------------------------------------------------ #
    def add_book(self, title, author, isbn="", year=0, genre="General", total_copies=1):
        """Add a new book title. Returns (ok, message)."""
        title, author = title.strip(), author.strip()
        if not title or not author:
            return False, "Title and author are required."
        if int(total_copies) < 1:
            return False, "Total copies must be at least 1."
        self._write(
            "INSERT INTO books (title, author, isbn, year, genre, total_copies, added_on)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, author, isbn.strip(), int(year), genre.strip() or "General",
             int(total_copies), date.today().isoformat()),
        )
        return True, "Book '{}' added.".format(title)

    def all_books(self, search="", genre="All"):
        """List books with live availability. Optional text search and genre filter."""
        sql = """
            SELECT b.*,
                   b.total_copies - (
                       SELECT COUNT(*) FROM loans l
                       WHERE l.book_id = b.id AND l.return_date IS NULL
                   ) AS available_copies
            FROM books b
            WHERE 1 = 1
        """
        params = []
        if search:
            sql += " AND (b.title LIKE ? OR b.author LIKE ? OR b.isbn LIKE ?)"
            like = "%{}%".format(search.strip())
            params += [like, like, like]
        if genre and genre != "All":
            sql += " AND b.genre = ?"
            params.append(genre)
        sql += " ORDER BY b.title COLLATE NOCASE"
        return self._run(sql, params)

    def search_books(self, query=""):
        """Search books by title, author or ISBN."""
        return self.all_books(search=query)

    def get_book(self, book_id):
        rows = self._run("SELECT * FROM books WHERE id = ?", (book_id,))
        return rows[0] if rows else None

    def update_book(self, book_id, title, author, isbn="", year=0, genre="General", total_copies=1):
        """Update an existing book. Copies cannot drop below what is issued."""
        title, author = title.strip(), author.strip()
        if not title or not author:
            return False, "Title and author are required."
        with closing(self._connect()) as conn, conn:
            issued = conn.execute(
                "SELECT COUNT(*) AS c FROM loans WHERE book_id = ? AND return_date IS NULL",
                (book_id,),
            ).fetchone()["c"]
            if int(total_copies) < issued:
                return False, "{} copy/copies are issued right now - total copies cannot be lower.".format(issued)
            changed = conn.execute(
                "UPDATE books SET title = ?, author = ?, isbn = ?, year = ?, genre = ?,"
                " total_copies = ? WHERE id = ?",
                (title, author, isbn.strip(), int(year), genre.strip() or "General",
                 int(total_copies), book_id),
            ).rowcount
        if not changed:
            return False, "Book not found."
        return True, "Book updated."

    def delete_book(self, book_id):
        """Delete a book. Blocked while any copy is still issued."""
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                """SELECT b.title,
                          (SELECT COUNT(*) FROM loans l
                            WHERE l.book_id = b.id AND l.return_date IS NULL) AS active
                   FROM books b WHERE b.id = ?""",
                (book_id,),
            ).fetchone()
            if row is None:
                return False, "Book not found."
            if row["active"] > 0:
                return False, "Cannot delete '{}' - {} copy/copies are currently issued.".format(
                    row["title"], row["active"])
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        return True, "Book deleted (its past loan history was removed too)."

    def genres(self):
        """Distinct genres currently in the collection."""
        return [r["genre"] for r in
                self._run("SELECT DISTINCT genre FROM books ORDER BY genre COLLATE NOCASE")]

    # ------------------------------------------------------------------ #
    # members                                                            #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _member_contact_error(email, phone):
        """The general rule shared by every member form.

        Email and mobile are optional (blank = not provided), but whenever a
        value is given it must be strictly valid:
          - email: full address, no double/edge dots, local part <= 64 chars,
                   whole address <= 254 chars, TLD at least 2 letters
          - mobile: exactly 10 digits, digits only (no spaces, dashes,
                    parentheses or a leading '+')
        Returns an error message string, or None when both values are fine.
        """
        if email:
            local_part = email.split("@", 1)[0]
            if "@" in email:
                tld = email.rsplit("@", 1)[1].rsplit(".", 1)[-1]
            else:
                tld = ""
            if (not EMAIL_PATTERN.fullmatch(email)
                    or ".." in local_part
                    or local_part.startswith(".")
                    or local_part.endswith(".")
                    or len(local_part) > EMAIL_LOCAL_MAX
                    or len(email) > EMAIL_TOTAL_MAX
                    or not EMAIL_TLD_PATTERN.fullmatch(tld)):
                return EMAIL_ERROR
        if phone and not PHONE_PATTERN.fullmatch(phone):
            return PHONE_ERROR
        return None

    def add_member(self, name, email="", phone=""):
        """Register a new member. Returns (ok, message)."""
        name, email, phone = name.strip(), email.strip(), phone.strip()
        if not name:
            return False, "Member name is required."
        contact_error = self._member_contact_error(email, phone)
        if contact_error:
            return False, contact_error
        if email and self._run("SELECT COUNT(*) AS c FROM members WHERE email = ?", (email,))[0]["c"]:
            return False, "A member with this email already exists."
        self._write(
            "INSERT INTO members (name, email, phone, joined_on) VALUES (?, ?, ?, ?)",
            (name, email, phone, date.today().isoformat()),
        )
        return True, "Member '{}' added.".format(name)

    def all_members(self, search=""):
        """List members, optionally filtered by name / email / phone."""
        sql = "SELECT * FROM members WHERE 1 = 1"
        params = []
        if search:
            sql += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)"
            like = "%{}%".format(search.strip())
            params += [like, like, like]
        sql += " ORDER BY name COLLATE NOCASE"
        return self._run(sql, params)

    def get_member(self, member_id):
        rows = self._run("SELECT * FROM members WHERE id = ?", (member_id,))
        return rows[0] if rows else None

    def update_member(self, member_id, name, email="", phone=""):
        name, email, phone = name.strip(), email.strip(), phone.strip()
        if not name:
            return False, "Member name is required."
        contact_error = self._member_contact_error(email, phone)
        if contact_error:
            return False, contact_error
        if email and self._run(
                "SELECT COUNT(*) AS c FROM members WHERE email = ? AND id != ?",
                (email, member_id))[0]["c"]:
            return False, "Another member already uses this email."
        changed = self._write(
            "UPDATE members SET name = ?, email = ?, phone = ? WHERE id = ?",
            (name, email, phone, member_id),
        )
        return (True, "Member updated.") if changed else (False, "Member not found.")

    def delete_member(self, member_id):
        """Delete a member. Blocked while they still hold any book."""
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                """SELECT m.name,
                          (SELECT COUNT(*) FROM loans l
                            WHERE l.member_id = m.id AND l.return_date IS NULL) AS active
                   FROM members m WHERE m.id = ?""",
                (member_id,),
            ).fetchone()
            if row is None:
                return False, "Member not found."
            if row["active"] > 0:
                return False, "{} still holds {} book(s) - collect them first.".format(
                    row["name"], row["active"])
            conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
        return True, "Member deleted (loan history for this member was removed too)."

    # ------------------------------------------------------------------ #
    # issuing and returning                                              #
    # ------------------------------------------------------------------ #
    def issue_book(self, book_id, member_id, due_date=None):
        """Issue a book to a member.

        Rules enforced:
          - the book must have at least one free copy
          - a member may hold at most MAX_BOOKS_PER_MEMBER books
          - a member cannot borrow the same title twice at once
          - the due date cannot be in the past
        Returns (ok, message).
        """
        issue_date = date.today()
        if due_date is None:
            due_date = issue_date + timedelta(days=DEFAULT_LOAN_DAYS)
        if isinstance(due_date, datetime):
            due_date = due_date.date()
        if due_date < issue_date:
            return False, "Due date cannot be before today."

        with closing(self._connect()) as conn, conn:
            book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
            member = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
            if book is None or member is None:
                return False, "Book or member not found."

            held = conn.execute(
                "SELECT COUNT(*) AS c FROM loans WHERE member_id = ? AND return_date IS NULL",
                (member_id,),
            ).fetchone()["c"]
            if held >= MAX_BOOKS_PER_MEMBER:
                return False, "{} already holds {} books (membership limit).".format(
                    member["name"], MAX_BOOKS_PER_MEMBER)

            dup = conn.execute(
                "SELECT COUNT(*) AS c FROM loans WHERE book_id = ? AND member_id = ?"
                " AND return_date IS NULL",
                (book_id, member_id),
            ).fetchone()["c"]
            if dup:
                return False, "{} already has '{}' checked out.".format(member["name"], book["title"])

            issued = conn.execute(
                "SELECT COUNT(*) AS c FROM loans WHERE book_id = ? AND return_date IS NULL",
                (book_id,),
            ).fetchone()["c"]
            if issued >= book["total_copies"]:
                return False, "No copies of '{}' are available right now.".format(book["title"])

            conn.execute(
                "INSERT INTO loans (book_id, member_id, issue_date, due_date) VALUES (?, ?, ?, ?)",
                (book_id, member_id, issue_date.isoformat(), due_date.isoformat()),
            )
        return True, "'{}' issued to {} - due on {}.".format(
            book["title"], member["name"], due_date.isoformat())

    def return_book(self, loan_id):
        """Mark an issued book as returned.

        Returns (ok, message, days_overdue).
        """
        today = date.today()
        with closing(self._connect()) as conn, conn:
            loan = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
            if loan is None:
                return False, "Loan record not found.", 0
            if loan["return_date"]:
                return False, "This book has already been returned.", 0
            conn.execute("UPDATE loans SET return_date = ? WHERE id = ?",
                         (today.isoformat(), loan_id))
        days_overdue = max(0, (today - date.fromisoformat(loan["due_date"])).days)
        if days_overdue:
            return True, "Book returned {} day(s) late.".format(days_overdue), days_overdue
        return True, "Book returned on time.", 0

    def loans(self, status="All"):
        """Loan records joined with book and member names.

        status: 'All' | 'Active' | 'Overdue' | 'Returned'
        """
        sql = """
            SELECT l.id, l.book_id, l.member_id, l.issue_date, l.due_date, l.return_date,
                   b.title, b.author, m.name AS member_name
            FROM loans l
            JOIN books   b ON b.id = l.book_id
            JOIN members m ON m.id = l.member_id
        """
        params, where = [], []
        if status == "Active":
            where.append("l.return_date IS NULL")
        elif status == "Returned":
            where.append("l.return_date IS NOT NULL")
        elif status == "Overdue":
            where.append("l.return_date IS NULL AND l.due_date < ?")
            params.append(date.today().isoformat())
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY l.issue_date DESC, l.id DESC"
        return self._run(sql, params)

    def active_loans(self):
        return self.loans("Active")

    def overdue_loans(self):
        return self.loans("Overdue")

    # ------------------------------------------------------------------ #
    # statistics                                                         #
    # ------------------------------------------------------------------ #
    def stats(self):
        """Key figures for the dashboard."""
        today = date.today().isoformat()
        copies = self._run("SELECT COALESCE(SUM(total_copies), 0) AS c FROM books")[0]["c"]
        issued = self._run("SELECT COUNT(*) AS c FROM loans WHERE return_date IS NULL")[0]["c"]
        return {
            "titles": self._book_count(),
            "copies": copies,
            "available": copies - issued,
            "issued": issued,
            "returned": self._run(
                "SELECT COUNT(*) AS c FROM loans WHERE return_date IS NOT NULL")[0]["c"],
            "overdue": self._run(
                "SELECT COUNT(*) AS c FROM loans WHERE return_date IS NULL AND due_date < ?",
                (today,))[0]["c"],
            "members": self._run("SELECT COUNT(*) AS c FROM members")[0]["c"],
        }

    def top_authors(self, limit=5):
        """Authors with the most copies in the collection."""
        return self._run(
            """SELECT author, COUNT(*) AS titles, SUM(total_copies) AS copies
               FROM books
               GROUP BY author
               ORDER BY copies DESC, author COLLATE NOCASE
               LIMIT ?""",
            (int(limit),),
        )

    def genre_counts(self):
        """Copies per genre."""
        return self._run(
            """SELECT genre, SUM(total_copies) AS copies
               FROM books
               GROUP BY genre
               ORDER BY copies DESC, genre COLLATE NOCASE""")

    # ------------------------------------------------------------------ #
    # demo data                                                          #
    # ------------------------------------------------------------------ #
    def _seed_sample_data(self):
        """Insert a small demo collection so every feature works instantly.

        Includes one on-time active loan, one overdue loan and one already
        returned loan, all dated relative to today.
        """
        today = date.today()
        books = [
            ("The Alchemist", "Paulo Coelho", "9780062315007", 1988, "Fiction", 3),
            ("Clean Code", "Robert C. Martin", "9780132350884", 2008, "Technology", 2),
            ("1984", "George Orwell", "9780451524935", 1949, "Fiction", 4),
            ("A Brief History of Time", "Stephen Hawking", "9780553380163", 1988, "Science", 2),
            ("The Pragmatic Programmer", "Andrew Hunt", "9780135957059", 1999, "Technology", 1),
            ("Pride and Prejudice", "Jane Austen", "9780141439518", 1813, "Fiction", 3),
        ]
        members = [
            ("Alice Johnson", "alice@example.com", "9876543210"),
            ("Bob Smith", "bob@example.com", "9123456780"),
            ("Charlie Lee", "charlie@example.com", "9988776655"),
        ]
        demo_loans = [
            # (book_id, member_id, issue_offset, due_offset, return_offset or None)
            (3, 1, -12, -5, None),    # 1984 -> Alice, due 5 days ago => OVERDUE
            (2, 2, -3, 11, None),    # Clean Code -> Bob, active, on time
            (1, 3, -30, -16, -18),   # Alchemist -> Charlie, returned 2 days late
        ]
        with closing(self._connect()) as conn, conn:
            for title, author, isbn, year, genre, copies in books:
                conn.execute(
                    "INSERT INTO books (title, author, isbn, year, genre, total_copies, added_on)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, author, isbn, year, genre, copies, today.isoformat()),
                )
            for name, email, phone in members:
                conn.execute(
                    "INSERT INTO members (name, email, phone, joined_on) VALUES (?, ?, ?, ?)",
                    (name, email, phone, today.isoformat()),
                )
            for book_id, member_id, issued_ago, due_in, returned_ago in demo_loans:
                conn.execute(
                    "INSERT INTO loans (book_id, member_id, issue_date, due_date, return_date)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (book_id, member_id,
                     (today + timedelta(days=issued_ago)).isoformat(),
                     (today + timedelta(days=due_in)).isoformat(),
                     (today + timedelta(days=returned_ago)).isoformat() if returned_ago is not None else None),
                )
