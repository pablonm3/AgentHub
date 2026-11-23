"""The orchestrator (spec section 5): sequences steps, keeps state, routes, houses the chats.

No intelligence of its own. Each AI step is a fresh `claude -p`; a question to the human
pauses the run with a decision file (or, with `on_question: chat`, opens an interactive
session; 5.7) and routing afterwards is derived from which artifact versions appeared,
never from what the skill says.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from . import worktree as wt
from .claude_runner import StepResult, base_env, run_chat, run_step, session_tokens, write_chat_settings, write_step_settings
from .config import DEFAULTS_FALLBACK, Manifest, Step, Workflow, load_defaults, load_manifest, load_workflow
from .link import link_worktree
from .naming import (
    body_without_frontmatter,
    count_severities,
    highest_version,
    latest,
    next_run_number,
    next_version,
    parse_run_cost,
    read_frontmatter,
    resolve_reads,
    run_id as make_run_id,
    severities_line,
    split_run_id,
    version_suffix,
    versioned,
)
from .notify import notify
from .observability import Observability, telemetry_env_disabled
from .paths import Layout
from .render import render
from .runlog import write_log
from .state import State, now_iso
from .tickets import load_ticket

# Re-entry after a question chat, by which artifact got a new version (spec 5.7 table).
CHAT_REENTRY_DEFAULT = {"spec": "6", "plan": "9", "ticket": "4"}
TEMPLATE_PLACEHOLDER = "TODO(onboard)"


RATE_LIMIT_MARGIN_S = 60  # wait this long past the reset time before continuing the session
RATE_LIMIT_RETRY_S = 15 * 60  # the wait when the stream gave no reset time
RATE_LIMIT_MAX_WAIT_S = 6 * 3600  # a reset further away (the weekly limit) fails the run instead of sleeping


class RunError(Exception):
    pass


class SessionLost(Exception):
    """A continued session stopped again with an error: the step starts over in a new session."""


def _sleep_until(epoch: float) -> None:
    """Sleep in short slices, so Ctrl-C ends the wait at once."""
    while (left := epoch - time.time()) > 0:
        time.sleep(min(left, 30))


def _local_time(epoch: float) -> str:
    """HH:MM for a time within a day of now, with the date otherwise."""
    fmt = "%H:%M" if abs(epoch - time.time()) < 24 * 3600 else "%Y-%m-%d %H:%M"
    return time.strftime(fmt, time.localtime(epoch))


def _session_cost(before: float | None, reported: float | None) -> float | None:
    """Cost of an execution after one more attempt in its session.

    A continued session reports its whole total, earlier attempts included, so the new figure
    replaces the old one. A figure below the old one cannot be a running total (the earlier
    process was killed before it saved its spend), so it is added.
    """
    if reported is None:
        return before
    if before is None or reported >= before:
        return reported
    return before + reported


@dataclass
class ChatOutcome:
    next_step: str | None = None
    reset_iteration: bool = False
    spec_revision: bool = False
    inject_answer: str | None = None
    paused: bool = False
    blocked: str | None = None
    changed: list[str] | None = None


@dataclass
class ReviewScope:
    """What one execution of a step with an `incremental_prompt` covers (spec 5.4).

    `since` is set for an incremental execution: the commit the step's last finished execution
    reviewed. Without it the step runs its ordinary prompt over the whole branch.
    """

    head: str
    spec_version: int
    reason: str
    since: str = ""
    previous: Path | None = None
    new_commits: int = 0
    new_lines: int = 0
    branch_lines: int = 0

    @property
    def incremental(self) -> bool:
        return bool(self.since)

    def record(self) -> dict[str, Any]:
        """The part kept in state.json; the next execution compares against `head` and `spec_version`."""
        return {
            "kind": "incremental" if self.incremental else "full",
            "head": self.head,
            "spec_version": self.spec_version,
            "since": self.since or None,
            "reason": self.reason,
        }


class Orchestrator:
    def __init__(
        self,
        layout: Layout,
        manifest: Manifest,
        wf: Workflow,
        state: State,
        quiet: bool = False,
    ):
        self.layout = layout
        self.manifest = manifest
        self.wf = wf
        self.state = state
        self.defaults: dict[str, Any] = state["defaults"]
        self.project = manifest.project(state["project"])
        self.obs = Observability(layout, manifest.observability)
        self.quiet = quiet
        self.run_dir = layout.run_dir(state.run_id)
        self.log_dir = layout.run_log_dir(state.run_id)
        self.worktree = layout.worktree(self.project.name, state.run_id)
        self.settings_file = self.log_dir / "step_settings.json"
        self.chat_settings_file = self.log_dir / "chat_settings.json"

    def _write_settings(self) -> None:
        """The Claude Code settings of the run's steps and chats; written by start and resume, so that
        constructing an orchestrator (pending_question) writes nothing."""
        write_step_settings(self.layout, self.settings_file)
        write_chat_settings(self.layout, self.chat_settings_file)

    # ================================================================== construction
    @classmethod
    def start(cls, layout: Layout, workflow_name: str, feature: str, overrides: dict | None = None, quiet: bool = False) -> "Orchestrator":
        """Step 2: allocate the run, freeze the ticket, create state, worktree, link, setup."""
        manifest = load_manifest(layout)
        wf = load_workflow(layout, workflow_name)
        ticket = load_ticket(layout, feature)
        project = manifest.project(ticket.project)
        agentsmd = layout.private_path(project.agentsmd)
        if not agentsmd.is_file():
            raise SystemExit(f"harness: {project.agentsmd} is missing; run `agenthub-harness project add {project.name}` first")
        if TEMPLATE_PLACEHOLDER in agentsmd.read_text():
            raise SystemExit(
                f"harness: {project.agentsmd} still has {TEMPLATE_PLACEHOLDER} placeholders; "
                f"finish `agenthub-harness project add {project.name}` before starting a run"
            )
        defaults = load_defaults(layout, workflow_name, project_defaults=project.defaults, overrides=overrides)
        base_branch = ticket.base_branch or project.default_base
        n = next_run_number(layout, feature)
        rid = make_run_id(feature, n)
        run_dir = layout.run_dir(rid)
        if run_dir.exists():
            raise SystemExit(f"harness: {layout.rel(run_dir)} already exists (run-number collision); refusing to overwrite")
        run_dir.mkdir(parents=True)
        layout.run_log_dir(rid).mkdir()
        frozen = run_dir / f"ticket_{feature}_{n}.md"
        shutil.copyfile(ticket.path, frozen)
        state = State.new(
            layout.state_file(rid),
            run_id=rid,
            workflow=wf.name,
            feature=feature,
            n=n,
            project=project.name,
            base_branch=base_branch,
            harness_commit=wt.harness_commit(layout),
            defaults=defaults,
            step_ids=[s.id for s in wf.steps],
        )
        state.step("1").update({"status": "done", "ended": now_iso()})
        state.save()
        orch = cls(layout, manifest, wf, state, quiet=quiet)
        orch._write_settings()
        print(f"run {rid} created · {layout.rel(run_dir)}")
        orch._check_collector()
        orch._step2_prepare_worktree()
        return orch

    @classmethod
    def resume(cls, layout: Layout, run_id: str, quiet: bool = False) -> "Orchestrator":
        split_run_id(run_id)
        state = State.load(layout.state_file(run_id))
        if state.status in ("done", "blocked"):
            raise SystemExit(f"harness: run {run_id} is {state.status}; nothing to resume")
        manifest = load_manifest(layout)
        wf = load_workflow(layout, state["workflow"])
        orch = cls(layout, manifest, wf, state, quiet=quiet)
        orch._write_settings()
        print(f"resuming {run_id} at step {state.current} (was {state.status})")
        # an execution still marked running was interrupted; the step continues its session when it
        # can (spec 5.8) and otherwise runs again as the next _v<k>
        for exe in state["executions"]:
            if exe.get("status") == "running":
                exe["status"] = "interrupted"
                exe["ended"] = exe.get("ended") or now_iso()
                state.step(exe["step"])["status"] = "failed"
        if not state.get("pending_chat"):
            state["status"] = "running"
            state["error"] = None
        state.save()
        orch._check_collector()
        if state.current == "2":
            orch._step2_prepare_worktree()
        return orch

    # ================================================================== step 2
    def _step2_prepare_worktree(self) -> None:
        st = self.state
        exe = st.begin_step("2", None, [f"tickets/{st.feature}.md"], [self.layout.rel(self.worktree)])
        st.save()
        base = wt.ensure_base_clone(self.layout, self.project)
        print(f"git fetch in {self.layout.rel(base)}")
        wt.fetch(base)
        wt.add_worktree(base, self.worktree, st["branch"], st["base_branch"])
        for line in link_worktree(self.layout, self.manifest, self.project.name, self.worktree):
            if not self.quiet:
                print("  " + line)
        setup_log = self.log_dir / "02-setup.txt"
        while True:
            ok, failing, tail = wt.run_setup(self.worktree, self.project.setup, setup_log)
            if ok:
                break
            print(f"setup failed: {failing}\n{tail}")
            question = (
                f"The project setup command `{failing}` failed in the new worktree "
                f"{self.worktree}. Output tail:\n\n```\n{tail}\n```\n\n"
                "Help the human fix the cause (see the project AGENTS.md for how secrets and the dev "
                "server are reached). Do not edit the worktree code. When the cause is fixed, record it in the decision "
                "file and resume the run; the orchestrator re-runs the setup list from the start."
            )
            outcome = self.ask_human(
                asking_step="2",
                kind="setup",
                reason=f"setup command failed: {failing}",
                question=question,
                chat_skill=None,
                chat_prompt_rel=self.wf.raw.get("setup_chat_prompt"),
            )
            if outcome.paused:
                st.end_step(exe, "failed", outcome=f"setup failed: {failing}")
                st.save()
                return
        st.end_step(exe, "done", outcome="worktree ready")
        st["current"] = self.wf.first_ai_or_gate()
        st.save()

    # ================================================================== main loop
    def run(self) -> str:
        """Drive the run until it ends or pauses. Returns the final status."""
        st = self.state
        try:
            if st.status == "paused" and st.get("pending_chat"):
                self._resume_pending_chat()
            while st.status in ("running",):
                sid = st.current
                if sid is None:
                    raise RunError("state has no current step")
                step = self.wf.step(sid)
                if step.gate:
                    self._handle_gate(step)
                elif step.actor == "orchestrator":
                    self._handle_action(step)
                elif step.actor == "human":
                    self._advance(step.id)
                else:
                    self._run_ai_step(step)
                st.save()
        except RunError as e:
            st.finish("failed", str(e))
            st.save()
            print(f"✖ run failed: {e}")
        except KeyboardInterrupt:
            if st.status == "running":
                st["status"] = "paused"
                st["pending_chat"] = None
                st.save()
                print("\ninterrupted; `agenthub-harness resume` continues the current step")
        finally:
            st.save()
            self._write_run_log()
        return st.status

    def _advance(self, sid: str) -> None:
        nxt = self.wf.next_after(sid)
        if nxt is None:
            self.state.finish("done")
        else:
            self.state["current"] = nxt

    # ================================================================== AI steps
    def _should_skip(self, step: Step) -> str | None:
        if not step.skip_when:
            return None
        key = step.skip_when.split(".", 1)[-1]
        value = self.defaults.get(key)
        if value == "never":
            return f"defaults.{key}: never"
        if value == "auto":
            print(f"   note: defaults.{key} is `auto` but no auto threshold is defined; running the step")
        return None

    def _run_ai_step(self, step: Step) -> None:
        st = self.state
        reason = self._should_skip(step)
        if reason:
            st.mark_skipped(step.id, reason)
            self._advance(step.id)
            return
        exe = self._continuable_execution(step)
        started_over = False
        while True:
            if exe:
                outputs = self._outputs_of(step, exe)
                self._probe_telemetry(step.id)
                self._print_status()
                prompt = self._continue(step, exe, outputs)
            else:
                exe, outputs, prompt = self._begin_execution(step)
            st.save()
            try:
                res = self._run_attempts(step, exe, outputs, prompt)
                break
            except SessionLost as lost:
                if started_over:
                    raise RunError(str(lost)) from None
                print(f"   {lost}; starting step {step.id} again in a new session")
                started_over = True
                exe = None
        self._finish_execution(step, exe, outputs, res)

    def _begin_execution(self, step: Step) -> tuple[dict, dict[str, Path], str]:
        """Start a new execution of a step: resolve its inputs, name its outputs, render its prompt."""
        st = self.state
        k = st.execution_count(step.id) + 1
        scope = self._review_scope(step) if step.incremental_prompt else None
        inputs = self._resolve_inputs(step)
        if scope and scope.previous:
            inputs["previous_report"] = [scope.previous]
        outputs = self._compute_outputs(step, k)
        for p in outputs.values():
            if p.exists():
                raise RunError(
                    f"step {step.id} would write {self.layout.rel(p)} but it already exists; "
                    "a computed output name can only collide through a bug (run number or execution counter)"
                )
        self._probe_telemetry(step.id)
        self._print_status()
        in_list = [self.layout.rel(p) for ps in inputs.values() for p in ps]
        out_list = [self.layout.rel(p) for p in outputs.values()]
        exe = st.begin_step(step.id, step.skill, in_list, out_list)
        transcript = self.log_dir / f"{step.id.zfill(2)}{version_suffix(k)}.jsonl"
        exe["transcript"] = self.layout.rel(transcript)
        if scope:
            exe["scope"] = scope.record()
        if step.writes_commit:
            exe["head_before"] = wt.head(self.worktree)

        prompt = self._render_prompt(step, inputs, outputs, k, scope)
        answer = st.get("injected_answer")
        if answer and answer.get("step") == step.id:
            st["injected_answer"] = None

        print(f"▶ {step.id} {step.skill} (execution {k}, iteration {st['iteration']})")
        if scope and (scope.incremental or k > 1):
            print(f"   scope: {'incremental' if scope.incremental else 'whole branch'} ({scope.reason})")
        return exe, outputs, prompt

    # ------------------------------------------------------------ continuing a stopped execution (spec 5.8)
    def _may_continue(self, exe: dict) -> bool:
        """Whether a stopped execution can go on in its own session instead of starting over."""
        return bool(
            self.wf.raw.get("continue_prompt")
            and exe.get("session_id")
            and exe.get("continuable", True)
            and (exe.get("attempts") or 1) <= int(self._default("step_continuations"))
        )

    def _continuable_execution(self, step: Step) -> dict | None:
        """The step's last execution when it stopped unfinished and its session can be continued."""
        executions = self.state.executions_of(step.id)
        last = executions[-1] if executions else None
        if not last or last.get("status") not in ("failed", "interrupted") or not self._may_continue(last):
            return None
        outputs = self._outputs_of(step, last)
        if outputs and all(p.exists() for p in outputs.values()):
            return None
        return last

    def _outputs_of(self, step: Step, exe: dict) -> dict[str, Path]:
        """The output paths an execution was given, by the names of the step's `writes`."""
        return {name: self.layout.root / rel for name, rel in zip(step.writes, exe.get("out") or [])}

    def _continue(self, step: Step, exe: dict, outputs: dict[str, Path]) -> str:
        """Reopen a stopped execution as one more attempt; returns the message that continues its session."""
        stop_reason = exe.get("stop_reason") or "the process was interrupted"
        self.state.reopen_step(exe)
        print(
            f"▶ {step.id} {step.skill} (execution {exe['k']}, attempt {exe['attempts']}: "
            f"continuing session {exe['session_id'][:8]})"
        )
        vars_ = self._vars(k=exe["k"])
        vars_.update(
            {
                "step_id": step.id,
                "skill": step.skill or "",
                "attempt": exe["attempts"],
                "stop_reason": stop_reason,
                "outputs": "\n".join(f"- {name}: {p}" for name, p in outputs.items())
                or "- (none: this step commits to the worktree)",
            }
        )
        return Template(self.wf.prompt_text(self.wf.raw["continue_prompt"])).safe_substitute(vars_)

    def _run_attempts(self, step: Step, exe: dict, outputs: dict[str, Path], prompt: str) -> StepResult:
        """Run an execution until its outputs exist.

        Its session is continued, as one more attempt of the same execution, after the usage limit
        has reset and once when it ended without an output. A continued session that stops with an
        error raises SessionLost. Any other failure ends the run; `agenthub-harness resume` continues the session.
        """
        st = self.state

        def remember_session(session_id: str) -> None:
            exe["session_id"] = session_id
            st.save()

        while True:
            continuing = (exe.get("attempts") or 1) > 1
            res = run_step(
                layout=self.layout,
                prompt=prompt,
                cwd=self.worktree,
                transcript=self.layout.root / exe["transcript"],
                settings_file=self.settings_file,
                env=self._step_env(step, exe["k"]),
                mcp_config=self._mcp_config_for(step, exe["k"]),
                permission_mode=self.defaults.get("permission_mode", "bypassPermissions"),
                model=self._model_for(step),
                max_budget_usd=self.defaults.get("max_budget_usd"),
                timeout_s=self._timeout_for(step),
                quiet=self.quiet,
                resume_session=exe["session_id"] if continuing else None,
                on_session=remember_session,
            )
            exe["cost_usd"] = _session_cost(exe.get("cost_usd"), res.cost_usd)
            exe["tokens"] = session_tokens(exe.get("tokens"), res.tokens)
            exe["num_turns"] = res.num_turns
            missing = [self.layout.rel(p) for p in outputs.values() if not p.exists()]
            if res.ok and not missing:
                return res

            go_on = False
            if res.timed_out:
                outcome, stop_reason = "timed out", "it ran past the step's time limit and was stopped"
                error = f"step {step.id} timed out"
            elif res.rate_limited:
                resets = f", resets {_local_time(res.rate_limit_resets_at)}" if res.rate_limit_resets_at else ""
                outcome, stop_reason = f"usage limit reached{resets}", "the account's usage limit was reached"
                how = "continues the step in its session" if self._may_continue(exe) else "starts the step again"
                error = f"step {step.id}: {outcome}; `agenthub-harness resume {st.run_id}` {how}"
            elif not res.ok:
                outcome = f"claude exited {res.returncode}" + (": " + res.result_text[:200] if res.result_text else "")
                stop_reason = f"the process ended with an error ({outcome})"
                error = f"step {step.id} failed (exit {res.returncode})"
            else:
                outcome = f"missing output: {', '.join(missing)}"
                stop_reason = f"it ended without writing {', '.join(missing)}"
                error = f"step {step.id} ended without writing {', '.join(missing)}"
            st.end_step(exe, "failed", outcome=outcome, stop_reason=stop_reason)
            st.save()

            if res.rate_limited:
                go_on = self._may_continue(exe) and self._wait_for_limit(step, res.rate_limit_resets_at)
            elif res.ok:
                # ended normally without its output: ask its session for it, once per execution
                go_on = self._may_continue(exe) and not exe.get("asked_for_output")
                exe["asked_for_output"] = True
                exe["continuable"] = go_on
                if go_on:
                    print(f"   step {step.id} ended without writing {', '.join(missing)}; asking its session for it")
            elif continuing:
                # the session was continued and stopped again for a reason of its own: do not reuse it
                exe["continuable"] = False
                st.save()
                if not res.timed_out:
                    raise SessionLost(f"session {str(exe['session_id'])[:8]} could not be continued ({outcome})")
            if not go_on:
                st.save()
                raise RunError(error)
            prompt = self._continue(step, exe, outputs)
            st.save()

    def _wait_for_limit(self, step: Step, resets_at: int | None) -> bool:
        """Sleep until the usage limit resets. False when the run does not wait: `on_rate_limit`
        is `pause`, or the reset is further away than RATE_LIMIT_MAX_WAIT_S."""
        st = self.state
        if self._default("on_rate_limit") != "wait":
            return False
        now = time.time()
        until = max(resets_at or now + RATE_LIMIT_RETRY_S, now) + RATE_LIMIT_MARGIN_S
        if until - now > RATE_LIMIT_MAX_WAIT_S:
            print(f"   usage limit resets {_local_time(until)}: too far away to wait for")
            return False
        message = f"usage limit reached at step {step.id}; continuing its session at {_local_time(until)}"
        print(f"⏳ {message}")
        notify(f"harness · {st.run_id}", message)
        st["limit_wait"] = {"step": step.id, "until": until}
        st.save()
        try:
            _sleep_until(until)
        finally:
            st["limit_wait"] = None
            st.save()
        self._check_collector(quiet=True)
        return True

    def _finish_execution(self, step: Step, exe: dict, outputs: dict[str, Path], res: StepResult) -> None:
        """Record the outcome of an execution whose outputs exist, then route."""
        st = self.state
        commits = wt.count_commits(self.worktree, exe["head_before"]) if exe.get("head_before") else None
        primary = next(iter(outputs.values()), None)
        fm = read_frontmatter(primary) if primary and primary.suffix == ".md" else {}
        cost = parse_run_cost(primary) if primary and primary.suffix == ".md" else None
        outcome = self._outcome_text(step, fm, primary, commits)
        scope = exe.get("scope") or {}
        if scope.get("kind") == "incremental":
            outcome += f" · incremental since {scope['since'][:8]}"
        st.end_step(exe, "done", outcome=outcome, project_cost=cost, commits=commits)
        if commits is not None:
            st.step(step.id)["commits"] = (st.step(step.id).get("commits") or 0) + commits
            if step.writes_commit and commits == 0:
                print(f"   note: step {step.id} made no commit")
        st.save()
        print(f"✔ {step.id} {step.skill} · {outcome}" + (f" · ${exe['cost_usd']:.2f}" if exe.get("cost_usd") else ""))
        self._route_after(step, fm, primary)

    def _review_scope(self, step: Step) -> ReviewScope:
        """Whether this execution covers the whole branch or only the commits made since the
        step's last finished execution (spec 5.4).

        Whole branch when the run asks for it, when no finished execution recorded its commit,
        after a new spec version, and when more lines changed since then than the limits allow.
        """
        head = wt.head(self.worktree)
        spec_version = highest_version(self._base("spec"))

        def full(reason: str) -> ReviewScope:
            return ReviewScope(head=head, spec_version=spec_version, reason=reason)

        if self._default("review_scope") == "full":
            return full("defaults.review_scope: full")
        last = next(
            (e for e in reversed(self.state.executions_of(step.id)) if e.get("status") == "done" and e.get("scope")),
            None,
        )
        if last is None:
            return full("no finished review to build on")
        since = last["scope"]["head"]
        previous = self.layout.root / last["out"][0]
        if last["scope"]["spec_version"] != spec_version:
            return full(f"the spec changed since the last review: v{last['scope']['spec_version']} → v{spec_version}")
        if not previous.is_file():
            return full(f"the last review's report {self.layout.rel(previous)} is missing")
        if not wt.is_ancestor(self.worktree, since):
            return full(f"the last reviewed commit {since[:8]} is no longer in the branch history")
        new_lines = wt.changed_lines(self.worktree, f"{since}..HEAD")
        branch_lines = wt.branch_changed_lines(self.worktree, self.state["base_branch"])
        if new_lines is None or branch_lines is None:
            return full("git could not size the change since the last review")
        max_lines = int(self._default("review_incremental_max_lines"))
        max_share = float(self._default("review_incremental_max_share"))
        limit = min(max_lines, int(max_share * branch_lines))
        size = f"{new_lines} lines changed since the last review at {since[:8]}"
        if new_lines > limit:
            return full(
                f"{size}; the limit is {limit}, the lower of review_incremental_max_lines ({max_lines}) "
                f"and {max_share:.0%} of the branch's {branch_lines} lines"
            )
        return ReviewScope(
            head=head,
            spec_version=spec_version,
            reason=f"{size}; limit {limit}",
            since=since,
            previous=previous,
            new_commits=wt.count_commits(self.worktree, since),
            new_lines=new_lines,
            branch_lines=branch_lines,
        )

    def _default(self, key: str) -> Any:
        """A run default; a run started before the key existed gets its built-in value."""
        return self.defaults.get(key, DEFAULTS_FALLBACK[key])

    def _route_after(self, step: Step, fm: dict, primary: Path | None) -> None:
        st = self.state
        status = str(fm.get("status", "")).strip().lower().replace(" ", "_")
        if step.on_status and status in step.on_status:
            target = step.on_status[status]
            if target == "chat":
                question = str(fm.get("question") or f"Step {step.id} ({step.skill}) reported status `{status}`.")
                outcome = self.ask_human(
                    asking_step=step.id,
                    kind="question",
                    reason=f"{step.skill}: {status}",
                    question=question,
                    chat_skill=step.chat_skill or step.skill,
                    chat_prompt_rel=step.chat_prompt,
                    artifact=primary,
                )
                self._apply_chat_outcome(outcome, step.id)
                return
            st["current"] = target
            return
        if step.on_decision:
            decision = str(fm.get("decision", "")).strip().lower()
            if decision not in step.on_decision:
                raise RunError(f"step {step.id} wrote decision {decision!r}; expected one of {sorted(step.on_decision)}")
            target = step.on_decision[decision]
            if target == "chat":
                question = str(fm.get("question") or f"{step.skill} decided `{decision}` but left no question")
                outcome = self.ask_human(
                    asking_step=step.id,
                    kind="question",
                    reason=f"{step.skill}: {decision}",
                    question=question,
                    chat_skill=step.chat_skill or step.skill,
                    chat_prompt_rel=step.chat_prompt,
                    artifact=primary,
                    decision=decision,
                )
                self._apply_chat_outcome(outcome, step.id)
                return
            loops_back = self.wf.steps.index(self.wf.step(target)) < self.wf.steps.index(step)
            if loops_back:
                if st["iteration"] >= st["max_iterations"]:
                    question = (
                        f"The build loop reached its cap ({st['max_iterations']} iterations) and triage still asks for a new plan. "
                        f"Latest plan: {self.layout.rel(latest(self._base('plan')) or Path(''))}. "
                        "Decide with the human: adjust the spec or plan (written as a new version), raise the cap, or stop."
                    )
                    outcome = self.ask_human(
                        asking_step=step.id,
                        kind="question",
                        reason=f"loop cap {st['max_iterations']} reached",
                        question=question,
                        chat_skill=step.chat_skill or step.skill,
                        chat_prompt_rel=step.chat_prompt,
                        artifact=primary,
                        decision="loop_cap",
                    )
                    self._apply_chat_outcome(outcome, step.id)
                    return
                st["iteration"] += 1
            st["current"] = target
            return
        self._advance(step.id)

    # ================================================================== gates and chats
    def _handle_gate(self, step: Step) -> None:
        st = self.state
        self._print_status()
        message = Template(step.message or f"GATE {step.id}: review the run artifacts, then say you are done to continue.").safe_substitute(self._vars())
        st.gate_reached(step.id)
        st.save()
        outcome = self.ask_human(
            asking_step=step.id,
            kind="gate",
            reason=step.label,
            question=message,
            chat_skill=step.chat_skill,
            chat_prompt_rel=step.chat_prompt,
        )
        if outcome.paused:
            return
        self._route_after_gate(step, outcome)

    def _route_after_gate(self, step: Step, outcome: ChatOutcome) -> None:
        """Gate routing: `on_new_version` in the step maps a changed artifact to a re-entry step;
        the earliest step wins (ticket before spec before plan); nothing changed → next step."""
        st = self.state
        st.gate_released(step.id)
        reentry = {str(k): str(v) for k, v in (step.raw.get("on_new_version") or {}).items()}
        for kind in ("ticket", "spec", "plan"):
            if kind in (outcome.changed or []) and kind in reentry:
                st["current"] = reentry[kind]
                if kind == "spec":
                    st["iteration"] = 1
                    st["spec_revisions"] += 1
                print(f"   {kind} changed in the gate → re-entering at step {st['current']}")
                return
        self._advance(step.id)

    def ask_human(
        self,
        *,
        asking_step: str,
        kind: str,
        reason: str,
        question: str,
        chat_skill: str | None,
        chat_prompt_rel: str | None,
        artifact: Path | None = None,
        decision: str | None = None,
    ) -> ChatOutcome:
        """Notify, pause with a decision file (or open the chat with `on_question: chat`), then route by what changed (5.7)."""
        st = self.state
        notify(f"harness · {st.run_id}", reason)
        before = self._snapshot_versions()
        decision_path = versioned(self._base("decision"), next_version(self._base("decision")))
        # decision files always carry _v<k>
        if "_v" not in decision_path.name:
            decision_path = decision_path.with_name(decision_path.stem + "_v1" + decision_path.suffix)
        pending = {
            "kind": kind,
            "step": asking_step,
            "reason": reason,
            "question": question,
            "chat_skill": chat_skill,
            "chat_prompt": chat_prompt_rel,
            "artifact": self.layout.rel(artifact) if artifact else None,
            "decision": decision,
            "decision_file": self.layout.rel(decision_path),
            "before": before,
            "asked": now_iso(),
        }
        st["pending_chat"] = pending
        if kind != "gate":
            st["waiting_on_human"] = asking_step
        if self.defaults.get("on_question") == "pause":
            self._write_question_file(decision_path, pending)
            st["status"] = "paused"
            st.save()
            print(
                f"⏸ paused: {reason}. Question recorded in {self.layout.rel(decision_path)}: record the answer there "
                f"(`## Answer`, frontmatter `answered: true`), then `agenthub-harness resume {st.run_id}`"
                + (" with the gate released by AgentHub." if kind == "gate" else ".")
            )
            return ChatOutcome(paused=True)
        return self._open_chat(pending)

    def _resume_pending_chat(self) -> None:
        """Route a paused run from the answer in its decision file.

        Without a recorded answer the run stays paused, unless `on_question` is `chat`, which opens
        the chat. A gate goes on only when AgentHub released it: HARNESS_GATE_RELEASE names its
        decision file, which AgentHub sets once the human replied.
        """
        pending = self.state["pending_chat"]
        decision_name = Path(pending["decision_file"]).name
        if pending["kind"] == "gate" and os.environ.get("HARNESS_GATE_RELEASE") != decision_name:
            print(f"   GATE {pending['step']} is not released (HARNESS_GATE_RELEASE must name {decision_name}); the run stays paused")
            return
        recorded = self._answer_recorded(pending)
        if not recorded and self._default("on_question") == "pause":
            print(f"   no answer recorded in {pending['decision_file']} (`answered: true`); the run stays paused")
            return
        self.state["status"] = "running"
        if recorded:
            # the human answered outside a chat (an interface session filled in the decision file)
            print(f"   answer already recorded in {pending['decision_file']}; no chat opened")
            outcome = self._chat_outcome(pending)
        else:
            outcome = self._open_chat(pending)
        if pending["kind"] == "gate":
            if not outcome.paused:
                self._route_after_gate(self.wf.step(pending["step"]), outcome)
        elif pending["kind"] == "setup":
            if not outcome.paused:
                self.state["current"] = "2"
                self._step2_prepare_worktree()
        else:
            self._apply_chat_outcome(outcome, pending["step"])

    def _open_chat(self, pending: dict) -> ChatOutcome:
        st = self.state
        st["status"] = "waiting_on_human"
        st.save()
        prompt = self._render_chat_prompt(pending)
        print(
            f"\n💬 opening a chat for: {pending['reason']}\n"
            "   tell the chat when you are done: it records your answer, the chat closes and the run continues by itself.\n"
            "   /exit or Ctrl+D also ends it.\n"
        )
        env = self._step_env(None, 0, chat_step=pending["step"])
        # read by the chat's Stop hook (hooks/chat_done.py), which creates the marker once the answer is recorded
        done_marker = self.log_dir / "chat_done"
        env["HARNESS_DECISION_FILE"] = str(self.layout.root / pending["decision_file"])
        env["HARNESS_CHAT_DONE_MARKER"] = str(done_marker)
        run_chat(
            layout=self.layout,
            prompt=prompt,
            cwd=self.worktree,
            settings_file=self.chat_settings_file,
            env=env,
            permission_mode=self.defaults.get("chat_permission_mode", "auto"),
            model=self._model_for(None),
            name=f"{st.run_id} · {pending['reason']}",
            done_marker=done_marker,
        )
        self._check_collector(quiet=True)
        return self._chat_outcome(pending)

    def _answer_recorded(self, pending: dict) -> bool:
        decision_file = self.layout.root / pending["decision_file"]
        return read_frontmatter(decision_file).get("answered") is True

    def _chat_outcome(self, pending: dict) -> ChatOutcome:
        """What the human decided, read from the files: new artifact versions and the decision file (5.7)."""
        st = self.state
        after = self._snapshot_versions()
        changed = [k for k in ("ticket", "spec", "plan") if after[k] > pending["before"][k]]
        decision_file = self.layout.root / pending["decision_file"]
        answered = self._answer_recorded(pending)
        st["pending_chat"] = None
        st["waiting_on_human"] = None
        st["status"] = "running"
        if decision_file.exists():
            self._record_decision(pending, decision_file)
        if pending["kind"] in ("gate", "setup"):
            return ChatOutcome(changed=changed)
        # question chats: 5.7 table
        reentry = {**CHAT_REENTRY_DEFAULT, **{str(k): str(v) for k, v in (self.wf.raw.get("chat_reentry") or {}).items()}}
        for kind in ("spec", "plan", "ticket"):
            if kind in changed:
                return ChatOutcome(
                    next_step=reentry[kind],
                    reset_iteration=(kind == "spec"),
                    spec_revision=(kind == "spec"),
                    changed=changed,
                )
        if answered:
            answer_text = body_without_frontmatter(decision_file)
            # a second spec_issue for the same question ends the run as blocked
            qhash = hashlib.sha1((pending["step"] + "|" + pending["question"]).encode()).hexdigest()[:12]
            history = st["question_history"]
            repeated = any(h["hash"] == qhash and h.get("answered") for h in history)
            history.append({"step": pending["step"], "hash": qhash, "answered": True, "at": now_iso(), "decision": pending.get("decision")})
            if repeated and pending.get("decision") == "spec_issue":
                return ChatOutcome(blocked="the same spec question was raised twice without a change to spec or plan")
            return ChatOutcome(next_step=pending["step"], inject_answer=answer_text, changed=changed)
        # nothing written and no answer: pause
        st["pending_chat"] = pending
        st["status"] = "paused"
        print("   the chat ended without a decision; run paused. `agenthub-harness resume` reopens the same question.")
        return ChatOutcome(paused=True)

    def _apply_chat_outcome(self, outcome: ChatOutcome, asking_step: str) -> None:
        st = self.state
        if outcome.paused:
            return
        if outcome.blocked:
            st.finish("blocked", outcome.blocked)
            print(f"✖ blocked: {outcome.blocked}")
            return
        if outcome.reset_iteration:
            st["iteration"] = 1
        if outcome.spec_revision:
            st["spec_revisions"] += 1
        if outcome.inject_answer is not None:
            st["injected_answer"] = {"step": asking_step, "text": outcome.inject_answer}
        st["current"] = outcome.next_step or self.wf.next_after(asking_step)
        print(f"   → re-entering at step {st['current']}" + (f" ({', '.join(outcome.changed)} changed)" if outcome.changed else ""))

    def _record_decision(self, pending: dict, decision_file: Path) -> None:
        """Attach the decision file to the asking step's latest execution so the run log links it."""
        rel = self.layout.rel(decision_file)
        for exe in reversed(self.state["executions"]):
            if exe["step"] == pending["step"]:
                outs = exe.setdefault("out", [])
                if rel not in outs:
                    outs.append(rel)
                return
        self.state["executions"].append(
            {
                "step": pending["step"],
                "skill": pending.get("chat_skill"),
                "iteration": self.state["iteration"],
                "k": 0,
                "started": pending["asked"],
                "ended": now_iso(),
                "status": "done",
                "in": [],
                "out": [rel],
                "outcome": f"chat: {pending['reason']}",
                "transcript": None,
                "project_cost": None,
            }
        )

    def _write_question_file(self, path: Path, pending: dict) -> None:
        path.write_text(
            "---\n"
            f"run_id: {self.state.run_id}\n"
            f"step: '{pending['step']}'\n"
            f"kind: {pending['kind']}\n"
            f"asked: {pending['asked']}\n"
            "answered: false\n"
            "---\n"
            f"# Question from step {pending['step']}\n\n{pending['question']}\n\n"
            "## Answer\n\n_(pending: the run paused. Write the answer here, set `answered: true` above, then resume the run "
            f"with `agenthub harness resume {self.state.run_id}`)_\n"
        )

    # ================================================================== orchestrator steps
    def _handle_action(self, step: Step) -> None:
        st = self.state
        reason = self._should_skip(step)
        if reason:
            st.mark_skipped(step.id, reason)
            self._advance(step.id)
            return
        exe = st.begin_step(step.id, None, [], [])
        if step.action == "run_log":
            path = self._write_run_log()
            st.end_step(exe, "done", outcome="written", out=[self.layout.rel(path)])
        elif step.action == "push_branch":
            self._push_branch(step, exe)
        else:
            st.end_step(exe, "done", outcome=step.action or "noop")
        self._advance(step.id)

    def _push_branch(self, step: Step, exe: dict) -> None:
        """Publish the feature branch to origin. A failed push fails the run; `agenthub-harness resume` retries the step."""
        st = self.state
        branch = st["branch"]
        st.save()
        try:
            sha = wt.push_branch(self.worktree, branch)
        except wt.GitError as e:
            st.end_step(exe, "failed", outcome="push failed")
            raise RunError(f"step {step.id}: {str(e).removeprefix('harness: ')}") from None
        outcome = f"pushed origin/{branch} at {sha}"
        st.end_step(exe, "done", outcome=outcome)
        print(f"✔ {step.id} {step.label} · {outcome}")

    def _write_run_log(self) -> Path:
        commits = wt.merge_base_count(self.worktree, self.state["base_branch"]) if self.worktree.exists() else None
        return write_log(self.layout, self.state, self.wf, commits)

    # ================================================================== helpers
    def _base(self, stem: str, ext: str = ".md") -> Path:
        return self.run_dir / f"{stem}_{self.state.feature}_{self.state.n}{ext}"

    def _snapshot_versions(self) -> dict[str, int]:
        return {k: highest_version(self._base(k)) for k in ("ticket", "spec", "plan")}

    def _resolve_inputs(self, step: Step) -> dict[str, list[Path]]:
        out: dict[str, list[Path]] = {}
        for name, pattern in step.reads.items():
            pat = Template(pattern).safe_substitute(self._vars())
            out[name] = resolve_reads(self.layout.data_root, pat)
        return out

    def _compute_outputs(self, step: Step, k: int) -> dict[str, Path]:
        """Resolve write patterns to unique paths (spec section 1).

        Every repeated execution gets `_v<k>` whatever the reason for the repeat, so the
        suffix is applied to each write; `${v}` in a pattern only documents it. `_v${k}`
        marks files that are numbered from the first execution on (decision files).
        """
        out: dict[str, Path] = {}
        vars_ = {kk: vv for kk, vv in self._vars(k=k).items() if kk not in ("v", "k")}
        for name, pattern in step.writes.items():
            always_numbered = "${k}" in pattern
            base_text = pattern.replace("_v${k}", "").replace("${k}", "").replace("${v}", "")
            base = self.layout.data_root / Template(base_text).safe_substitute(vars_)
            ver = next_version(base, k)
            if always_numbered:
                out[name] = base.with_name(f"{base.stem}_v{ver}{base.suffix}")
            else:
                out[name] = versioned(base, ver)
        return out

    def _vars(self, k: int | None = None) -> dict[str, Any]:
        st = self.state
        v: dict[str, Any] = {
            "feature": st.feature,
            "n": st.n,
            "run_id": st.run_id,
            "project": st["project"],
            "base_branch": st["base_branch"],
            "branch": st["branch"],
            "workflow": st["workflow"],
            "worktree": str(self.worktree),
            "run_dir": str(self.run_dir),
            "run_dir_rel": self.layout.rel(self.run_dir),
            "harness_root": str(self.layout.root),
            "agentsmd": str(self.layout.private_path(self.project.agentsmd)),
            "templates": str(self.wf.dir / "templates"),
            "iteration": st["iteration"],
            "max_iterations": st["max_iterations"],
            "k": k if k is not None else "",
            "v": "",
        }
        for key, val in self.defaults.items():
            if not isinstance(val, (dict, list)):
                v[f"def_{key}"] = val
        for kind in ("ticket", "spec", "plan", "context", "testing", "plan_short"):
            lat = latest(self._base(kind))
            v[f"{kind}_latest"] = str(lat) if lat else "(none)"
        # next plan version, for steps that may write a new plan (triage on new_plan)
        for kind in ("plan", "plan_short"):
            base = self._base(kind)
            v[f"{kind}_next"] = str(versioned(base, max(highest_version(base) + 1, 2)))
        return v

    def _render_prompt(
        self, step: Step, inputs: dict[str, list[Path]], outputs: dict[str, Path], k: int, scope: ReviewScope | None = None
    ) -> str:
        vars_ = self._vars(k=k)
        in_lines = []
        for name, ps in inputs.items():
            vars_[f"in_{name}"] = ", ".join(str(p) for p in ps) if ps else "(none)"
            for p in ps:
                in_lines.append(f"- {name}: {p}")
        for name, p in outputs.items():
            vars_[f"out_{name}"] = str(p)
        vars_["inputs"] = "\n".join(in_lines) if in_lines else "- (none)"
        vars_["outputs"] = "\n".join(f"- {name}: {p}" for name, p in outputs.items()) or "- (none: this step commits to the worktree)"
        answer = self.state.get("injected_answer")
        vars_["answer"] = ""
        if answer and answer.get("step") == step.id:
            vars_["answer"] = (
                "\n## Answer from the human\n\nThe human answered the question this step raised earlier. "
                "Take it as settled:\n\n" + answer["text"].strip() + "\n"
            )
        prompt_rel = step.prompt
        if scope and scope.incremental:
            prompt_rel = step.incremental_prompt
            vars_.update(
                {
                    "since_commit": scope.since,
                    "since_commit_short": scope.since[:8],
                    "new_commits": scope.new_commits,
                    "new_lines": scope.new_lines,
                    "branch_lines": scope.branch_lines,
                }
            )
        text = self.wf.prompt_text(prompt_rel) if prompt_rel else self._generic_step_prompt(step)
        return Template(text).safe_substitute(vars_)

    def _generic_step_prompt(self, step: Step) -> str:
        return (
            f"Invoke the `{step.skill}` skill non-interactively for run ${{run_id}}.\n\n"
            "Inputs:\n${inputs}\n\nOutputs to write:\n${outputs}\n${answer}"
        )

    def _render_chat_prompt(self, pending: dict) -> str:
        vars_ = self._vars()
        vars_.update(
            {
                "question": pending["question"],
                "reason": pending["reason"],
                "decision_file": str(self.layout.root / pending["decision_file"]),
                "artifact": str(self.layout.root / pending["artifact"]) if pending.get("artifact") else "(none)",
                "chat_skill": pending.get("chat_skill") or "(none)",
                "asking_step": pending["step"],
            }
        )
        if pending.get("chat_prompt"):
            text = self.wf.prompt_text(pending["chat_prompt"])
        else:
            text = (
                "The coding harness paused run ${run_id} (${reason}) on a question for the human. AgentHub shows it to "
                "the human (Pablo), and his reply reaches you as a ticket comment.\n"
                + ("Load the `${chat_skill}` skill in chat mode.\n" if pending.get("chat_skill") else "")
                + "\nQuestion for the human:\n\n${question}\n\n"
                "Rules: discuss with him through your replies, then propose any edit to the spec, the latest plan or the "
                "ticket copy as a diff and apply it only on his explicit approval, always as a NEW version file (next "
                "_v<k>), never in place. Never edit code or test cases. When he has decided, record in ${decision_file} the "
                "question, his answer under `## Answer` and every approved diff, and set `answered: true` in its "
                "frontmatter. Write that file last and never earlier, then run `agenthub harness resume ${run_id}`: the "
                "run continues from the file."
            )
        return Template(text).safe_substitute(vars_)

    def _outcome_text(self, step: Step, fm: dict, primary: Path | None, commits: int | None) -> str:
        if fm.get("summary"):
            return str(fm["summary"]).strip()
        if primary is None:
            return f"{commits} commit(s)" if commits is not None else "done"
        name = primary.name
        if name.startswith(("review_", "readability_")):
            return severities_line(count_severities(primary))
        if name.startswith("context_"):
            return str(fm.get("status", "written"))
        if name.startswith("decision_"):
            return f"decision: {fm.get('decision', '?')}"
        if name.startswith("testing_feedback_"):
            if "passed" in fm and "total" in fm:
                return f"{fm['passed']}/{fm['total']} pass"
        if name.startswith("spec_"):
            ac = fm.get("acceptance_criteria")
            if ac is None:
                ac = len(re.findall(r"^AC\d+\.", primary.read_text(errors='replace'), re.M))
            oq = fm.get("open_questions")
            return f"{ac} acceptance criteria" + (f", {oq} open question(s)" if oq else "")
        if name.startswith("reviews_applied_"):
            a, s = fm.get("applied") or {}, fm.get("skipped") or {}
            if isinstance(a, dict) and isinstance(s, dict):
                return " · ".join(f"{r} {a.get(r, 0)}/{a.get(r, 0) + s.get(r, 0)} applied" for r in ("review", "readability"))
        if commits is not None:
            return f"{commits} commit(s)"
        return "written"

    def _model_for(self, step: Step | None) -> str | None:
        model = self.defaults.get("model") or {}
        if isinstance(model, str):
            return model
        per_step = {str(kk): str(vv) for kk, vv in (model.get("steps") or {}).items()}
        if step and step.id in per_step:
            return per_step[step.id]
        return model.get("default") or None

    def _effort_for(self, step: Step) -> str | None:
        """Reasoning effort of a step's `claude -p` process and its subagents (spec 5.4); None leaves the
        human's own Claude Code settings in charge, as for a run started before the workflow set one."""
        effort = self._default("effort") or {}
        if isinstance(effort, str):
            return effort
        per_step = {str(kk): str(vv) for kk, vv in (effort.get("steps") or {}).items()}
        return per_step.get(step.id) or effort.get("default") or None

    def _timeout_for(self, step: Step) -> float | None:
        t = self.defaults.get("timeouts") or {}
        minutes = None
        if isinstance(t, dict):
            minutes = t.get(step.id) or (t.get(int(step.id)) if step.id.isdigit() else None) or t.get("default")
        return float(minutes) * 60 if minutes else None

    def _mcp_config_for(self, step: Step, k: int) -> Path | None:
        """Write the step's MCP servers to runs/<run-id>/log/mcp_<step>.json; None when it declares none."""
        if not step.mcp_servers:
            return None
        vars_ = self._vars(k=k)

        def fill(value: Any) -> Any:
            if isinstance(value, str):
                return Template(value).safe_substitute(vars_)
            if isinstance(value, list):
                return [fill(x) for x in value]
            if isinstance(value, dict):
                return {kk: fill(vv) for kk, vv in value.items()}
            return value

        path = self.log_dir / f"mcp_{step.id.zfill(2)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": fill(step.mcp_servers)}, indent=2) + "\n")
        return path

    def _step_env(self, step: Step | None, k: int, chat_step: str | None = None) -> dict[str, str]:
        st = self.state
        extra: dict[str, str] = {
            "HARNESS_RUN_ID": st.run_id,
            "HARNESS_RUN_DIR": str(self.run_dir),
            "HARNESS_WORKTREE": str(self.worktree),
            "HARNESS_STEP": step.id if step else "chat",
            "HARNESS_CHAT_STEP": chat_step or "",
            "HARNESS_SKILL": (step.skill if step else "") or "",
            "HARNESS_ITERATION": str(st["iteration"]),
            "HARNESS_EXECUTION": str(k),
        }
        effort = self._effort_for(step) if step else None
        if effort:
            # the variable outranks the per-model levels of the human's own settings and `--effort`,
            # and it holds for the subagents the step starts, whatever model they run on
            extra["CLAUDE_CODE_EFFORT_LEVEL"] = effort
        tel = st.get("telemetry") or {}
        if tel.get("active") and not telemetry_env_disabled():
            attrs = {
                "app": "agenthub",
                "run_id": st.run_id,
                "feature": st.feature,
                "run_n": str(st.n),
                "step": step.id if step else "chat",
                "skill": (step.skill if step else "chat") or "chat",
                "iteration": str(st["iteration"]),
                "workflow": st["workflow"],
                "project": st["project"],
            }
            # the AgentHub task and AI user the run belongs to, set by the server when it spawns the run
            for attr, var in (("task_id", "AGENTHUB_TASK_ID"), ("ai_user", "AGENTHUB_AI_USER")):
                if os.environ.get(var):
                    attrs[attr] = os.environ[var]
            extra.update(self.obs.step_env(attrs))
        return base_env(self.layout, self.defaults.get("auth", "account"), extra)

    # ================================================================== telemetry
    def _check_collector(self, quiet: bool = False) -> None:
        """Whether steps send telemetry: the external collector must answer; nothing is started (5.6)."""
        tel = self.state["telemetry"]
        if self.obs.mode == "off" or telemetry_env_disabled():
            tel.update({"active": False, "reason": "off in harness.yaml" if self.obs.mode == "off" else "HARNESS_NO_TELEMETRY"})
            if not quiet:
                print(f"telemetry: off ({tel['reason']})")
            return
        if self.obs.collector_up():
            tel.update({"active": True, "reason": None})
            if not quiet:
                print("telemetry: on")
        else:
            reason = f"collector on port {self.obs.collector_port} not answering"
            tel.update({"active": False, "reason": reason})
            print(f"⚠ telemetry: off — {reason}. The run continues without it; the run log will say so.")
        self.state.save()

    def _probe_telemetry(self, step_id: str) -> None:
        tel = self.state["telemetry"]
        if self.obs.mode == "off" or telemetry_env_disabled():
            return
        if self.obs.collector_up():
            if not tel.get("active"):
                tel.update({"active": True, "reason": None})
            return
        if tel.get("active"):
            tel.update({"active": False, "since_step": step_id, "reason": "collector stopped answering"})
            print(f"⚠ telemetry: collector not answering from step {step_id} on; data from here is lost")

    def _print_status(self) -> None:
        if not self.quiet:
            print("\n" + render(self.state, self.wf) + "\n")




def pending_question(layout: Layout, run_id: str) -> dict | None:
    """What a paused run waits for, None when it waits for nothing. Read-only: writes no file.

    `kind` is gate, question or setup (as in the decision file's frontmatter), `decision_file` the
    absolute path of the file the answer goes in, `chat_prompt` the prompt the orchestrator would
    open the chat with.
    """
    split_run_id(run_id)
    state = State.load(layout.state_file(run_id))
    pending = state.get("pending_chat")
    if state.status != "paused" or not pending:
        return None
    # only for _render_chat_prompt; constructing an Orchestrator writes no file
    orch = Orchestrator(layout, load_manifest(layout), load_workflow(layout, state["workflow"]), state, quiet=True)
    return {
        "kind": pending["kind"],
        "step": pending["step"],
        "reason": pending["reason"],
        "question": pending["question"],
        "decision_file": str(layout.root / pending["decision_file"]),
        "chat_prompt": orch._render_chat_prompt(pending),
    }
