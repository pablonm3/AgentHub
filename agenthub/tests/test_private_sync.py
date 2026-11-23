"""The private folder is committed and pushed to `main` of its remote (AC37)."""

import subprocess

from agenthub.private_sync import PrivateSync


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def _remote_files(remote):
    return _git(remote, "ls-tree", "-r", "--name-only", "main").splitlines()


def test_a_file_written_during_a_turn_is_on_the_remote_after_the_turn(app, env):
    env.scenario(commands=[f"echo note > {env.private}/note_from_turn.md"])
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "write a note", "model": "opus"})
    app.wait_task(task["id"])
    assert "note_from_turn.md" in _remote_files(env.private_remote)
    assert _git(env.private, "status", "--porcelain") == ""
    assert f"task {task['id']} (Engineer)" in _git(env.private_remote, "log", "-1", "--format=%s", "main")


def test_a_commit_that_was_not_pushed_gets_pushed(env):
    (env.private / "committed.md").write_text("x\n")
    _git(env.private, "add", "-A")
    _git(env.private, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "by the session")
    result = PrivateSync(env.private).sync("unused message")
    assert result.pushed and not result.changed and result.error is None
    assert "committed.md" in _remote_files(env.private_remote)


def test_nothing_to_do_pushes_nothing(env):
    result = PrivateSync(env.private).sync("nothing")
    assert (result.changed, result.pushed, result.error) == (False, False, None)


def test_a_rejected_push_is_reported_and_nothing_is_discarded(env, tmp_path):
    # the remote refuses every update
    hook = env.private_remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho refused by the test >&2\nexit 1\n")
    hook.chmod(0o755)
    (env.private / "kept.md").write_text("keep me\n")
    result = PrivateSync(env.private).sync("try")
    assert result.error and not result.pushed
    assert (env.private / "kept.md").exists()
    assert _git(env.private, "log", "-1", "--format=%s") == "try"
