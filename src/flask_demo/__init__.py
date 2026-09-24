import os
import sqlite3

from flask import Flask, abort, g, redirect, render_template, request, url_for

SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    assignee TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# `who` 篩選值：空字串＝不篩選，UNASSIGNED＝只看未指派
UNASSIGNED = "__none__"


def clean_assignee(value: str | None) -> str | None:
    value = (value or "").strip()[:50]
    return value or None


def migrate(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    columns = {row["name"] for row in db.execute("PRAGMA table_info(todos)")}
    if "assignee" not in columns:
        db.execute("ALTER TABLE todos ADD COLUMN assignee TEXT")
        db.commit()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(DATABASE=os.path.join(app.instance_path, "todos.sqlite3"))
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc: BaseException | None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        migrate(get_db())

    def back_to_index():
        return redirect(
            url_for("index", show=request.args.get("show", "all"), who=request.args.get("who", ""))
        )

    @app.get("/")
    def index():
        show = request.args.get("show", "all")
        who = request.args.get("who", "")
        clauses, params = [], []
        if show == "active":
            clauses.append("done = 0")
        elif show == "done":
            clauses.append("done = 1")
        if who == UNASSIGNED:
            clauses.append("assignee IS NULL")
        elif who:
            clauses.append("assignee = ?")
            params.append(who)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        db = get_db()
        todos = db.execute(f"SELECT * FROM todos {where} ORDER BY done, id DESC", params).fetchall()
        counts = db.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM todos"
        ).fetchone()
        people = [
            row["assignee"]
            for row in db.execute(
                "SELECT DISTINCT assignee FROM todos WHERE assignee IS NOT NULL ORDER BY assignee"
            )
        ]
        return render_template(
            "index.html",
            todos=todos,
            show=show,
            who=who,
            counts=counts,
            people=people,
            unassigned=UNASSIGNED,
        )

    @app.post("/todos")
    def create():
        title = request.form.get("title", "").strip()
        if title:
            db = get_db()
            db.execute(
                "INSERT INTO todos (title, assignee) VALUES (?, ?)",
                (title[:200], clean_assignee(request.form.get("assignee"))),
            )
            db.commit()
        return back_to_index()

    @app.post("/todos/<int:todo_id>/toggle")
    def toggle(todo_id: int):
        db = get_db()
        cur = db.execute("UPDATE todos SET done = 1 - done WHERE id = ?", (todo_id,))
        if cur.rowcount == 0:
            abort(404)
        db.commit()
        return back_to_index()

    @app.post("/todos/<int:todo_id>/assign")
    def assign(todo_id: int):
        db = get_db()
        cur = db.execute(
            "UPDATE todos SET assignee = ? WHERE id = ?",
            (clean_assignee(request.form.get("assignee")), todo_id),
        )
        if cur.rowcount == 0:
            abort(404)
        db.commit()
        return back_to_index()

    @app.post("/todos/<int:todo_id>/delete")
    def delete(todo_id: int):
        db = get_db()
        cur = db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        if cur.rowcount == 0:
            abort(404)
        db.commit()
        return back_to_index()

    @app.post("/todos/clear-done")
    def clear_done():
        db = get_db()
        db.execute("DELETE FROM todos WHERE done = 1")
        db.commit()
        return back_to_index()

    return app


def main() -> None:
    create_app().run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5001")),
        debug=True,
    )
