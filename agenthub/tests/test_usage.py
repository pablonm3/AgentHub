"""The account's usage left: the server's last figure of each limit, from AI user turns, in the bootstrap
(fake `claude`; the run-step path is in test_harness_bridge.py)."""

import json
import queue
import time
from datetime import datetime, timezone

from agenthub.tests.serve_fake import default_scenario
from agenthub.usage import SETTING

WEEK, FABLE, FIVE_HOUR = "seven_day", "seven_day_overage_included", "five_hour"


def _future(days: float = 4) -> int:
    return int(time.time() + days * 86400)


def _fig(limit: str, used: float | None, resets_at: int, read_at: str, reached: bool = False) -> dict:
    return {"limit": limit, "used": used, "resets_at": resets_at, "reached": reached, "read_at": read_at}


def _usage(app) -> list[dict]:
    return app.get("/api/bootstrap")["usage"]


def _by_limit(app) -> dict[str, dict]:
    return {f["limit"]: f for f in _usage(app)}


def _topics(q: queue.Queue) -> list[str]:
    topics = []
    while True:
        try:
            topics.append(q.get_nowait()["topic"])
        except queue.Empty:
            return topics


def _window(used: object, resets_at: int) -> dict:
    return {"utilization": used, "resetsAt": resets_at, "status": "allowed"}


def _info(resets_at: int, **windows: dict) -> dict:
    return {"status": "allowed", "resetsAt": resets_at, "rateLimitType": WEEK, "unifiedWindows": windows}


def _manual_task(app, message: str = "hello") -> int:
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": message, "model": "fable"})
    app.wait_task(task["id"])
    return task["id"]


def _say(app, task_id: int, text: str) -> dict:
    app.post(f"/api/tasks/{task_id}/messages", {"text": text})
    return app.wait_task(task_id)


def test_a_new_app_knows_no_usage(app) -> None:
    # Constraint: with no figure ever reported the header says the usage left is not known (AC6), and the API
    #             answers an empty list (AC11).
    # Input: GET /api/bootstrap of a new app.
    # Expected output: "usage" is [].
    assert _usage(app) == []


def test_recorded_figures_are_in_the_bootstrap_and_published_once(app) -> None:
    # Constraint: the API lists one entry per known figure with its five fields (AC11, AC13); an open page
    #             learns of a new figure through the live topic `usage`, and the 2 s re-read of an unchanged
    #             state.json must not publish again; an older figure never replaces a newer one.
    # Input: record Week and 5 h; the same list again; Week read earlier; Week read later with a new share.
    # Expected output: both figures, ordered by limit name; one `usage` message; False and no message for the
    #                  repeat and the older figure; the later one replaces Week and publishes.
    resets = _future()
    week = _fig(WEEK, 0.22, resets, "2026-11-25T14:03:07Z")
    five = _fig(FIVE_HOUR, 0.10, _future(0.1), "2026-11-25T14:03:07Z")
    q = app.hub.events.subscribe()
    assert app.hub.usage.record([week, five])
    assert _usage(app) == [five, week]
    assert _topics(q) == ["usage"]
    assert not app.hub.usage.record([week, five])
    assert not app.hub.usage.record([{**week, "used": 0.5, "read_at": "2026-11-25T13:00:00Z"}])
    assert _topics(q) == []
    later = {**week, "used": 0.24, "read_at": "2026-11-25T15:00:00Z"}
    assert app.hub.usage.record([later])
    assert _by_limit(app)[WEEK] == later
    assert _topics(q) == ["usage"]


def test_the_fable_figure_stays_when_a_later_event_does_not_carry_it(app) -> None:
    # Constraint: a newer figure replaces only the one of its own limit (AC15).
    # Input: Week and Fable week read at 11:40, then Week alone read at 14:03.
    # Expected output: Week has the new share and read_at; Fable week is unchanged, read at 11:40.
    resets = _future()
    fable = _fig(FABLE, 0.37, resets, "2026-11-25T11:40:12Z")
    app.hub.usage.record([_fig(WEEK, 0.22, resets, "2026-11-25T11:40:12Z"), fable])
    week = _fig(WEEK, 0.24, resets, "2026-11-25T14:03:07Z")
    assert app.hub.usage.record([week])
    assert _by_limit(app) == {WEEK: week, FABLE: fable}


def test_figures_survive_a_restart(app) -> None:
    # Constraint: after a restart the header shows the same figures before any new turn or step (AC7).
    # Input: two figures recorded, then a rebuilt app on the same data.
    # Expected output: the rebuilt app's bootstrap lists the same two figures.
    resets = _future()
    app.hub.usage.record([_fig(WEEK, 0.22, resets, "2026-11-25T14:03:07Z"), _fig(FABLE, 0.37, resets, "2026-11-25T11:40:12Z")])
    before = _usage(app)
    again = app.rebuild()
    try:
        assert _usage(again) == before and len(before) == 2
    finally:
        again.hub.shutdown()


def test_a_figure_whose_period_ended_is_no_longer_answered(app) -> None:
    # Constraint: a figure whose reset time has passed is no longer shown, a reached one included; with none
    #             left the answer is the not-known state (AC8, AC11).
    # Input: Week resetting in 4 days and 5 h already reset; then 5 h reached and Week, both already reset.
    # Expected output: only Week first; [] after the second recording.
    past = int(time.time()) - 60
    week = _fig(WEEK, 0.22, _future(), "2026-11-25T14:03:07Z")
    app.hub.usage.record([week, _fig(FIVE_HOUR, 0.9, past, "2026-11-25T14:03:07Z")])
    assert _usage(app) == [week]
    app.hub.usage.record([_fig(WEEK, 0.3, past, "2026-11-25T15:00:00Z"),
                          _fig(FIVE_HOUR, None, past, "2026-11-25T15:00:00Z", reached=True)])
    assert _usage(app) == []


def test_malformed_figures_are_left_out(app) -> None:
    # Constraint: figures from another process's state.json are checked; a bad one never reaches the API and
    #             never removes a good one (AC10).
    # Input: a list with one malformed and one good figure; then a text, None and a dict instead of a list;
    #        then figures with a text share, a share of 22, a boolean reset time and a null share not reached.
    # Expected output: the good figure kept; False and the row unchanged for everything else.
    resets = _future()
    good = _fig(WEEK, 0.22, resets, "2026-11-25T14:03:07Z")
    assert app.hub.usage.record([{"limit": FABLE, "used": 0.37}, good])
    assert _usage(app) == [good]
    row = app.hub.db.setting(SETTING)
    later = "2026-11-25T15:00:00Z"
    for bad in ("seven_day", None, good, [_fig(WEEK, "0.3", resets, later)], [_fig(WEEK, 22, resets, later)],
                [{**_fig(WEEK, 0.3, resets, later), "resets_at": True}], [_fig(WEEK, None, resets, later)]):
        assert not app.hub.usage.record(bad)
    assert app.hub.db.setting(SETTING) == row


def test_a_turn_reports_both_weekly_figures(app, env) -> None:
    # Constraint: an AI user's turn updates the figures on the server and tells open pages (AC4 server half,
    #             AC11); a fable session reports Week and Fable week together (AC14).
    # Input: the fake turn emits the two-window event of a fable session (0.22 and 0.37); one manual task.
    # Expected output: both figures with the event's reset time, not reached, read in the last seconds;
    #                  a `usage` message was published.
    resets = _future()
    env.scenario(rate_limit_info=_info(resets, seven_day=_window(0.22, resets), seven_day_overage_included=_window(0.37, resets)))
    q = app.hub.events.subscribe()
    _manual_task(app)
    usage = _by_limit(app)
    assert {k: (f["used"], f["resets_at"], f["reached"]) for k, f in usage.items()} == {
        WEEK: (0.22, resets, False), FABLE: (0.37, resets, False)}
    for f in usage.values():
        read = datetime.strptime(f["read_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert 0 <= (datetime.now(timezone.utc) - read).total_seconds() < 30
    assert "usage" in _topics(q)


def test_a_later_turn_on_another_model_keeps_the_fable_figure(app, env) -> None:
    # Constraint: an event without the Fable window updates Week and leaves Fable week with its own age (AC15).
    # Input: two turns of one task: the fable event (0.22, 0.37), then a Week-only event (0.24).
    # Expected output: Week 0.24; Fable week still 0.37 with the read_at it had after the first turn.
    resets = _future()
    env.scenario(turns=[
        {"rate_limit_info": _info(resets, seven_day=_window(0.22, resets), seven_day_overage_included=_window(0.37, resets))},
        {"rate_limit_info": _info(resets, seven_day=_window(0.24, resets))},
    ])
    task_id = _manual_task(app)
    fable = _by_limit(app)[FABLE]
    time.sleep(1.1)  # read_at has whole seconds: the second turn's figure is read later
    _say(app, task_id, "again")
    usage = _by_limit(app)
    assert usage[WEEK]["used"] == 0.24 and usage[WEEK]["read_at"] > fable["read_at"]
    assert usage[FABLE] == fable


def test_a_turn_that_hits_the_limit_shows_it_reached(app, env) -> None:
    # Constraint: a rejection with a readable reset time shows its limit reached, with that reset time (AC9);
    #             the rejection the harness fake emits reports no share, so `used` is null.
    # Input: the fake turn emits {"status": "rejected", "resetsAt": R, "rateLimitType": "five_hour"}.
    # Expected output: one entry five_hour, reached, used None, resets_at R.
    resets = _future(0.05)
    env.scenario(rate_limit_info={"status": "rejected", "resetsAt": resets, "rateLimitType": FIVE_HOUR})
    _manual_task(app)
    [entry] = _usage(app)
    assert (entry["limit"], entry["reached"], entry["used"], entry["resets_at"]) == (FIVE_HOUR, True, None, resets)


def test_unreadable_events_change_nothing_and_the_turn_goes_on(app, env) -> None:
    # Constraint: a rejection without a reset time keeps the last figures (AC9); an unreadable window keeps the
    #             last figure of its limit, and the turn continues as today (AC10).
    # Input: a turn with a good Week figure; then a turn whose event is a rejection with no reset time; then
    #        one whose only window has utilization "x".
    # Expected output: usage unchanged after each, read_at included; each turn posts its reply.
    resets = _future()
    env.scenario(turns=[
        {"rate_limit_info": _info(resets, seven_day=_window(0.22, resets))},
        {"rate_limit_info": {"status": "rejected", "rateLimitType": FIVE_HOUR}},
        {"rate_limit_info": _info(resets, seven_day=_window("x", resets))},
    ])
    task_id = _manual_task(app)
    first = _usage(app)
    assert [f["used"] for f in first] == [0.22]
    for text in ("second", "third"):
        time.sleep(1.1)
        task = _say(app, task_id, text)
        assert _usage(app) == first
    replies = [e["text"] for e in task["events"] if e["kind"] == "reply"]
    assert len(replies) == 3 and replies[-1].startswith("Fake reply 3")


def test_fake_mode_shows_week_78_percent_left(app, env) -> None:
    # Constraint: fake mode shows a figure without spending account usage (AC12).
    # Input: the scenario fake mode writes (serve_fake.default_scenario) and one turn.
    # Expected output: Week with used 0.22 (78% left) and Fable week 0.37 in the bootstrap.
    (env.fake_dir / "scenario.json").write_text(json.dumps(default_scenario()))
    _manual_task(app)
    usage = _by_limit(app)
    assert (usage[WEEK]["used"], usage[FABLE]["used"]) == (0.22, 0.37)
