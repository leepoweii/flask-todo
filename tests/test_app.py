import pytest

from flask_demo import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3")})
    return app.test_client()


def test_empty_list(client):
    assert "這裡沒有項目" in client.get("/").get_data(as_text=True)


def test_add_toggle_delete(client):
    client.post("/todos", data={"title": "買牛奶"})
    page = client.get("/").get_data(as_text=True)
    assert "買牛奶" in page and "共 1 項，完成 0 項" in page

    client.post("/todos/1/toggle")
    assert "完成 1 項" in client.get("/").get_data(as_text=True)
    assert "買牛奶" not in client.get("/?show=active").get_data(as_text=True)
    assert "買牛奶" in client.get("/?show=done").get_data(as_text=True)

    client.post("/todos/1/delete")
    assert "共 0 項" in client.get("/").get_data(as_text=True)


def test_blank_title_ignored(client):
    client.post("/todos", data={"title": "   "})
    assert "共 0 項" in client.get("/").get_data(as_text=True)


def test_clear_done(client):
    for title in ("a", "b", "c"):
        client.post("/todos", data={"title": title})
    client.post("/todos/1/toggle")
    client.post("/todos/3/toggle")
    client.post("/todos/clear-done")
    assert "共 1 項，完成 0 項" in client.get("/").get_data(as_text=True)


def test_missing_todo_404(client):
    assert client.post("/todos/99/toggle").status_code == 404
    assert client.post("/todos/99/delete").status_code == 404


def test_title_is_escaped(client):
    client.post("/todos", data={"title": "<script>x</script>"})
    assert "<script>x</script>" not in client.get("/").get_data(as_text=True)


def test_create_with_assignee_and_filter(client):
    client.post("/todos", data={"title": "寫報告", "assignee": " 小明 "})
    client.post("/todos", data={"title": "訂會議室", "assignee": "小華"})
    client.post("/todos", data={"title": "沒人做"})

    mine = client.get("/?who=小明").get_data(as_text=True)
    assert "寫報告" in mine and "訂會議室" not in mine and "沒人做" not in mine

    nobody = client.get("/?who=__none__").get_data(as_text=True)
    assert "沒人做" in nobody and "寫報告" not in nobody


def test_reassign_and_unassign(client):
    client.post("/todos", data={"title": "寫報告", "assignee": "小明"})
    client.post("/todos/1/assign", data={"assignee": "小華"})
    assert "寫報告" in client.get("/?who=小華").get_data(as_text=True)
    assert "寫報告" not in client.get("/?who=小明").get_data(as_text=True)

    client.post("/todos/1/assign", data={"assignee": "   "})
    assert "寫報告" in client.get("/?who=__none__").get_data(as_text=True)


def test_assign_missing_todo_404(client):
    assert client.post("/todos/99/assign", data={"assignee": "小明"}).status_code == 404


def test_filters_combine_and_survive_redirect(client):
    client.post("/todos", data={"title": "a", "assignee": "小明"})
    client.post("/todos", data={"title": "b", "assignee": "小明"})
    res = client.post("/todos/1/toggle?show=active&who=小明")
    assert "show=active" in res.location and "who=" in res.location
    page = client.get("/?show=active&who=小明").get_data(as_text=True)
    assert '<span class="title">b</span>' in page and '<span class="title">a</span>' not in page


def test_migrates_old_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
        " done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute("INSERT INTO todos (title) VALUES ('舊資料')")
    db.commit()
    db.close()

    client = create_app({"TESTING": True, "DATABASE": str(path)}).test_client()
    assert "舊資料" in client.get("/?who=__none__").get_data(as_text=True)
    client.post("/todos/1/assign", data={"assignee": "小明"})
    assert "舊資料" in client.get("/?who=小明").get_data(as_text=True)
