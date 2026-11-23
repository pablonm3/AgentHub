"""Report links: served, rendered, confined, appended when missing, alive after a restart (AC32)."""

import json


NOTEBOOK = {
    "cells": [{"cell_type": "markdown", "metadata": {}, "source": ["# Findings notebook\n"]},
              {"cell_type": "code", "metadata": {}, "execution_count": 1, "outputs": [], "source": ["1 + 1"]}],
    "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
}


def _write_reports(app, task_id):
    folder = app.hub.sessions.reports_dir(task_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "page.html").write_text("<h1>Interactive app</h1>")
    (folder / "summary.md").write_text("# Summary\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    (folder / "analysis.ipynb").write_text(json.dumps(NOTEBOOK))
    return folder


def test_the_three_formats_are_served_and_rendered(app):
    _write_reports(app, 7)
    html = app.client.get("/reports/7/page.html")
    assert html.status_code == 200 and "Interactive app" in html.text and html.headers["content-type"].startswith("text/html")
    md = app.client.get("/reports/7/summary.md")
    assert "<h1>Summary</h1>" in md.text and "<table>" in md.text
    nb = app.client.get("/reports/7/analysis.ipynb")
    assert nb.status_code == 200 and "Findings notebook" in nb.text and "download the notebook" in nb.text
    raw = app.client.get("/reports/7/analysis.ipynb?raw=1")
    assert json.loads(raw.content)["nbformat"] == 4


def test_a_path_outside_the_folder_is_refused(app):
    _write_reports(app, 7)
    (app.config.reports_dir / "secret.txt").write_text("no")
    assert app.client.get("/reports/7/..%2Fsecret.txt").status_code in (403, 404)
    assert app.client.get("/reports/7/missing.md").status_code == 404


def test_a_report_written_in_a_turn_gets_its_link(live, env):
    env.scenario(commands=['echo "# r" > "$AGENTHUB_REPORTS_DIR/result.md"'], message="Here are the findings.")
    task = live.post("/api/tasks", {"ai_user_id": "data_scientist", "message": "research", "model": "opus"})
    t = live.wait_task(task["id"])
    reply = [e["text"] for e in t["events"] if e["kind"] == "reply"][-1]
    url = f"http://127.0.0.1:{live.port}/reports/{task['id']}/result.md"
    assert reply.startswith("Here are the findings.") and url in reply
    again = live.rebuild()
    assert again.client.get(f"/reports/{task['id']}/result.md").status_code == 200
    again.hub.shutdown()


def test_a_report_already_linked_is_not_repeated(live, env):
    task_id_guess = 1
    url = f"http://127.0.0.1:{live.port}/reports/{task_id_guess}/x.md"
    env.scenario(commands=['echo x > "$AGENTHUB_REPORTS_DIR/x.md"'], message=f"See [x]({url}).")
    task = live.post("/api/tasks", {"ai_user_id": "data_scientist", "message": "r", "model": "opus"})
    assert task["id"] == task_id_guess
    reply = [e["text"] for e in live.wait_task(task["id"])["events"] if e["kind"] == "reply"][-1]
    assert "Reports:" not in reply
