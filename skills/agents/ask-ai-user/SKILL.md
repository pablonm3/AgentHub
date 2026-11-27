---
name: ask-ai-user
description: Give a piece of work to another AI user of AgentHub (Data Scientist, Engineer, DevOps) as a child task of this task, write to it, and handle what comes back — its questions, the gates of its harness run, its result. Also how to behave in a task another AI user created for you. Use when part of the work belongs to another AI user's role, or when a message "from <AI user> (task <id>)" arrives.
---

# Working with the other AI users

AgentHub has three AI users: Data Scientist, Engineer and DevOps. From your task you can give a
piece of work to one of the others. AgentHub creates a **child task** for it, linked to your task
(its **parent**). The child answers to your task, not to Pablo, and you answer it or ask Pablo.

## When to ask, and when not

- Ask when a part of the work belongs to another AI user's role (deployments and servers to DevOps,
  research and data to Data Scientist, code to Engineer) and you cannot or should not do it yourself.
- Do not ask for what you can do in this session, and do not ask to pass a decision that is Pablo's.
- Each exchange is a turn on both sides and spends account usage: ask once, with everything the
  other AI user needs (the goal, what you know, what you want back, where to find the files).

## Creating a child task

```bash
agenthub task create --to DevOps "Check that deploy/deploy_app.sh still restarts the app; tell me what you find."
agenthub task create --to "Data Scientist" --file request.md
```

- `--to` takes a handle, name or id in any case (`DevOps`, `"Data Scientist"`, `data_scientist`).
  You cannot ask yourself or Pablo.
- The request is the words after the options, or a file with `--file`.
- The command prints the child task's id. On a ticket, the child is on the same ticket, with the
  ticket's model, and AgentHub posts a comment by you on the ticket that announces it. The ticket's
  assignee and stage do not change.
- If that AI user already has an open task on the ticket that this task created, the request goes
  to that task instead. If it has an open task on the ticket that another task started, AgentHub
  refuses (one open task per AI user per ticket): tell Pablo in your message.

## Writing to a child task

```bash
agenthub task send 14 "Yes, use the staging server."
agenthub task send 14 --file answer.md
```

Only your own child tasks take your messages. The child runs its next turn with it.

## What comes back

Everything a child sends reaches you as a new turn, headed `Message from <AI user> (task <id>):`,
with a line by AgentHub at the end that says what it is:

- **a question**: the child waits for your answer;
- **a gate of its harness run** (GATE 1: spec and plan review, GATE 2: result review): the run stays
  paused until you or Pablo answer, and your reply releases it;
- **its result**: the child ended its work done. It still takes messages.

A child's messages are posted as its comments on the ticket too, but Pablo does not get them in his
Activity tab: they are addressed to you.

## Answering: yourself, or ask Pablo

- Answer yourself, a gate included, when Pablo's ticket, comments or messages already settle the
  matter: `agenthub task send <id> "<answer>"`. At a gate, say plainly whether the run may go on
  and what to change; AgentHub writes your reply into the gate's decision file, naming your task.
- Otherwise end your turn `waiting_on_user` and ask Pablo in your message, quoting what the child
  asked. When he answers, pass his answer on with `agenthub task send <id> "<his answer>"`.
- When you only wait for the child to finish, end your turn `waiting_on_child`, not
  `waiting_on_user`: the task then shows as waiting on that AI user, not on Pablo.

## In a task another AI user created for you

The first message says who asked and from which task. Then:

- Do what the request asks; the ticket is context, not your assignment.
- Your turn's `message`, your questions, and the gates and questions of a harness run you start go
  to that task, not to Pablo. `waiting_on_user` means you need its answer; `done` sends it your result.
- Its answers reach you as `Message from <AI user> (task <id>)`. Pablo can still write in your task;
  his messages count as before.
