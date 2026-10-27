"""
Library Management System - Streamlit UI.

All of the functionality (storage, issuing, returning, searching, stats)
lives in library.py. This file only builds the web interface on top of it.

How to run
----------
    pip install -r requirements.txt
    streamlit run app.py

The SQLite database (library.db) is created automatically next to these
files on first start, pre-loaded with a small set of demo books, members
and loans. Delete library.db any time to reset the demo data.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

# Make sure library.py is importable no matter which folder we start from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

import library

st.set_page_config(page_title="Library Manager", layout="wide")

PAGES = ["Dashboard", "Books", "Members", "Issue Book", "Return Book", "History"]


@st.cache_resource
def get_library():
    return library.Library()


lib = get_library()


# ---------------------------------------------------------------------- #
# helpers                                                                #
# ---------------------------------------------------------------------- #
def flash(kind, message):
    """Queue a message that survives the rerun triggered after an action."""
    st.session_state["flash"] = (kind, message)


def show_flash():
    item = st.session_state.pop("flash", None)
    if item:
        (st.success if item[0] == "ok" else st.error)(item[1])


def run_action(result):
    """result = (ok, message[, extra]): queue feedback and refresh the app."""
    flash("ok" if result[0] else "err", result[1])
    st.rerun()


def loan_status(loan, today=None):
    """Human readable status for one loan record."""
    today = today or date.today()
    if loan["return_date"]:
        return "Returned"
    due = date.fromisoformat(loan["due_date"])
    if due < today:
        return "Overdue by {}d".format((today - due).days)
    return "On loan ({}d left)".format((due - today).days)


def books_dataframe(books):
    df = pd.DataFrame(
        [
            {
                "ID": b["id"],
                "Title": b["title"],
                "Author": b["author"],
                "Genre": b["genre"],
                "Year": b["year"],
                "ISBN": b["isbn"],
                "Copies": b["total_copies"],
                "Available": b["available_copies"],
            }
            for b in books
        ]
    )
    st.dataframe(df, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------- #
# pages                                                                  #
# ---------------------------------------------------------------------- #
def page_dashboard():
    st.title("Dashboard")
    s = lib.stats()

    cols = st.columns(6)
    cols[0].metric("Book titles", s["titles"])
    cols[1].metric("Total copies", s["copies"])
    cols[2].metric("Issued now", s["issued"])
    cols[3].metric("Available", s["available"])
    cols[4].metric("Overdue", s["overdue"])
    cols[5].metric("Members", s["members"])

    left, right = st.columns(2)

    with left:
        st.subheader("Copies by author")
        authors = lib.top_authors(7)
        if authors:
            st.bar_chart(pd.DataFrame(authors).set_index("author")["copies"], horizontal=True)
        else:
            st.info("No books yet - add some on the Books page.")

    with right:
        st.subheader("Copies by genre")
        genres = lib.genre_counts()
        if genres:
            st.bar_chart(pd.DataFrame(genres).set_index("genre")["copies"])
        else:
            st.info("No books yet - add some on the Books page.")

    st.subheader("Overdue books")
    overdue = lib.overdue_loans()
    if overdue:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Book": l["title"],
                        "Author": l["author"],
                        "Member": l["member_name"],
                        "Due date": l["due_date"],
                        "Days late": (date.today() - date.fromisoformat(l["due_date"])).days,
                    }
                    for l in overdue
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("Nothing overdue - every issued book is within its due date.")


def page_books():
    st.title("Books")

    with st.expander("Add a new book"):
        with st.form("add_book_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            title = c1.text_input("Title")
            author = c2.text_input("Author")
            isbn = c1.text_input("ISBN (optional)")
            year = c2.number_input("Year", 0, 2100, date.today().year)
            genre = c1.text_input("Genre", value="General")
            copies = c2.number_input("Total copies", 1, 999, 1)
            if st.form_submit_button("Add book", use_container_width=True, type="primary"):
                run_action(lib.add_book(title, author, isbn, int(year), genre, int(copies)))

    st.subheader("Collection")
    f1, f2 = st.columns([3, 1])
    search = f1.text_input("Search", placeholder="Title, author or ISBN...")
    genre_filter = f2.selectbox("Genre", ["All"] + lib.genres())
    books = lib.all_books(search=search, genre=genre_filter)

    if not books:
        if search or genre_filter != "All":
            st.info("No books match your filters.")
        else:
            st.info("The collection is empty - add the first book above.")
        return

    books_dataframe(books)

    all_books = lib.all_books()
    edit_col, del_col = st.columns(2)

    with edit_col.expander("Edit a book"):
        if all_books:
            options = ["[{}] {} - {}".format(b["id"], b["title"], b["author"]) for b in all_books]
            choice = st.selectbox("Book to edit", options)
            book = all_books[options.index(choice)]
            # Keys include the book id so the form re-fills when another book is picked.
            with st.form("edit_book_form_{}".format(book["id"])):
                c1, c2 = st.columns(2)
                title = c1.text_input("Title", value=book["title"], key="eb_t_{}".format(book["id"]))
                author = c2.text_input("Author", value=book["author"], key="eb_a_{}".format(book["id"]))
                isbn = c1.text_input("ISBN", value=book["isbn"], key="eb_i_{}".format(book["id"]))
                year = c2.number_input("Year", 0, 2100,
                                       int(book["year"]) or date.today().year,
                                       key="eb_y_{}".format(book["id"]))
                genre = c1.text_input("Genre", value=book["genre"], key="eb_g_{}".format(book["id"]))
                copies = c2.number_input("Total copies", 1, 999, int(book["total_copies"]),
                                         key="eb_c_{}".format(book["id"]))
                if st.form_submit_button("Save changes", use_container_width=True, type="primary"):
                    run_action(lib.update_book(book["id"], title, author, isbn,
                                               int(year), genre, int(copies)))
        else:
            st.write("Nothing to edit.")

    with del_col.expander("Delete a book"):
        if all_books:
            options = ["[{}] {} - {}".format(b["id"], b["title"], b["author"]) for b in all_books]
            choice = st.selectbox("Book to delete", options)
            book_id = all_books[options.index(choice)]["id"]
            confirm = st.checkbox("Yes, delete this book permanently")
            if st.button("Delete book", disabled=not confirm, type="primary"):
                run_action(lib.delete_book(book_id))
        else:
            st.write("Nothing to delete.")


def member_form(prefix, submit_label):
    """Shared registration form used on the Members and Issue pages."""
    with st.form(prefix, clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name")
        email = c2.text_input("Email", placeholder="name@example.com")
        c2.caption("Optional — must look like name@example.com")
        phone = c1.text_input("Phone", placeholder="+1 555 123 4567")
        c1.caption("Optional — exactly 10 digits (digits only)")
        if st.form_submit_button(submit_label, use_container_width=True, type="primary"):
            run_action(lib.add_member(name, email, phone))


def page_members():
    st.title("Members")

    tab_add, tab_list = st.tabs(["➕ Add New Member", "👥 All Members"])

    with tab_add:
        st.subheader("Register a new member")
        st.caption("Only the name is required - email and phone are optional.")
        member_form("add_member_form", "Add member")

    with tab_list:
        st.subheader("All members")
        search = st.text_input("Search members", placeholder="Name, email or phone...")
        members = lib.all_members(search=search)

        held = {}
        for loan in lib.active_loans():
            held[loan["member_id"]] = held.get(loan["member_id"], 0) + 1

        if not members:
            if search:
                st.info("No members match your search.")
            else:
                st.info("No members yet - register the first one in the 'Add New Member' tab.")
            return

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": m["id"],
                        "Name": m["name"],
                        "Email": m["email"],
                        "Phone": m["phone"],
                        "Joined": m["joined_on"],
                        "Books held": "{} / {}".format(held.get(m["id"], 0),
                                                       library.MAX_BOOKS_PER_MEMBER),
                    }
                    for m in members
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )

        all_members = lib.all_members()
        edit_col, del_col = st.columns(2)

        with edit_col.expander("Edit a member"):
            if all_members:
                options = ["[{}] {}".format(m["id"], m["name"]) for m in all_members]
                choice = st.selectbox("Member to edit", options)
                member = all_members[options.index(choice)]
                with st.form("edit_member_form_{}".format(member["id"])):
                    name = st.text_input("Full name", value=member["name"],
                                         key="em_n_{}".format(member["id"]))
                    email = st.text_input("Email", value=member["email"],
                                          key="em_e_{}".format(member["id"]),
                                          placeholder="name@example.com")
                    st.caption("Optional — must look like name@example.com")
                    phone = st.text_input("Phone", value=member["phone"],
                                          key="em_p_{}".format(member["id"]),
                                          placeholder="+1 555 123 4567")
                    st.caption("Optional — exactly 10 digits (digits only)")
                    if st.form_submit_button("Save changes", use_container_width=True, type="primary"):
                        run_action(lib.update_member(member["id"], name, email, phone))
            else:
                st.write("Nothing to edit.")

        with del_col.expander("Delete a member"):
            if all_members:
                options = ["[{}] {}".format(m["id"], m["name"]) for m in all_members]
                choice = st.selectbox("Member to delete", options)
                member_id = all_members[options.index(choice)]["id"]
                confirm = st.checkbox("Yes, delete this member permanently")
                if st.button("Delete member", disabled=not confirm, type="primary"):
                    run_action(lib.delete_member(member_id))
            else:
                st.write("Nothing to delete.")


def page_issue():
    st.title("Issue a book")

    members = lib.all_members()
    if not members:
        st.info("No members yet - register one below, then come back to issue a book.")
        with st.expander("➕ Add a new member", expanded=True):
            member_form("issue_add_member_form", "Add member")
        return

    with st.expander("➕ New member? Add them here without leaving this page"):
        member_form("issue_add_member_form", "Add member")
        st.caption("Submit the form, then pick the new member from the dropdown below.")

    members = lib.all_members()

    available_books = [b for b in lib.all_books() if b["available_copies"] > 0]
    active = lib.active_loans()
    held = {}
    for loan in active:
        held[loan["member_id"]] = held.get(loan["member_id"], 0) + 1

    left, right = st.columns(2)

    with left:
        st.subheader("1. Choose a member")
        member = st.selectbox(
            "Member",
            members,
            format_func=lambda m: "{} ({} / {} books held)".format(
                m["name"], held.get(m["id"], 0), library.MAX_BOOKS_PER_MEMBER),
        )
        member_loans = [l for l in active if l["member_id"] == member["id"]]
        if member_loans:
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Book": l["title"], "Due date": l["due_date"], "Status": loan_status(l)}
                        for l in member_loans
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("This member currently holds no books.")

    with right:
        st.subheader("2. Choose a book")
        if not available_books:
            st.warning("No copies are available for issue right now.")
        else:
            book = st.selectbox(
                "Available books",
                available_books,
                format_func=lambda b: "{} by {} ({} of {} available)".format(
                    b["title"], b["author"], b["available_copies"], b["total_copies"]),
            )
            st.subheader("3. Due date")
            due = st.date_input(
                "Return by",
                value=date.today() + timedelta(days=library.DEFAULT_LOAN_DAYS),
                min_value=date.today(),
            )
            st.caption("A member may hold up to {} books at a time. "
                       "New loans default to {} days.".format(
                           library.MAX_BOOKS_PER_MEMBER, library.DEFAULT_LOAN_DAYS))
            if st.button("Issue book", type="primary", use_container_width=True):
                run_action(lib.issue_book(book["id"], member["id"], due))


def page_return():
    st.title("Return a book")

    active = lib.active_loans()
    if not active:
        st.info("No books are currently issued.")
        return

    loan = st.selectbox(
        "Issued book",
        active,
        format_func=lambda l: "{} - {} (due {})".format(
            l["title"], l["member_name"], l["due_date"]),
    )

    days_left = (date.fromisoformat(loan["due_date"]) - date.today()).days
    c1, c2, c3 = st.columns(3)
    c1.metric("Issued on", loan["issue_date"])
    c2.metric("Due date", loan["due_date"])
    c3.metric("Days left", days_left)

    if days_left < 0:
        st.warning("This book is {} day(s) overdue.".format(abs(days_left)))
    else:
        st.info("There are {} day(s) left until the due date.".format(days_left))

    if st.button("Mark as returned", type="primary"):
        run_action(lib.return_book(loan["id"]))


def page_history():
    st.title("Loan history")

    status = st.radio("Show", ["All", "Active", "Overdue", "Returned"], horizontal=True)
    rows = lib.loans(status)

    if not rows:
        st.info("No {} loans.".format(status.lower()))
        return

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Loan ID": l["id"],
                    "Book": l["title"],
                    "Author": l["author"],
                    "Member": l["member_name"],
                    "Issued": l["issue_date"],
                    "Due": l["due_date"],
                    "Returned": l["return_date"] or "-",
                    "Status": loan_status(l),
                }
                for l in rows
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.caption("{} record(s).".format(len(rows)))


# ---------------------------------------------------------------------- #
# app entry point                                                        #
# ---------------------------------------------------------------------- #
def main():
    page = st.sidebar.radio("Navigation", PAGES)
    st.sidebar.divider()
    s = lib.stats()
    st.sidebar.caption(
        "{} titles | {} copies | {} members".format(s["titles"], s["copies"], s["members"])
    )

    show_flash()

    if page == "Dashboard":
        page_dashboard()
    elif page == "Books":
        page_books()
    elif page == "Members":
        page_members()
    elif page == "Issue Book":
        page_issue()
    elif page == "Return Book":
        page_return()
    else:
        page_history()


main()
