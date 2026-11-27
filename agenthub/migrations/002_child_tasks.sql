-- Version 1 → 2: a task can have a parent task (origin ai_user), a waiting parent names the child it
-- waits for, a chat line names the task that sent it, a comment says whether Activity lists it.
-- Run by db.Database in one transaction with foreign keys off; SQLite cannot change the CHECK of
-- tasks.origin in place, so tasks is rebuilt with every row and id kept.

CREATE TABLE tasks_v2 (
    id                 INTEGER PRIMARY KEY,
    ticket_id          INTEGER REFERENCES tickets(id),
    ai_user_id         TEXT NOT NULL REFERENCES users(id),
    origin             TEXT NOT NULL CHECK (origin IN ('assignment', 'mention', 'manual', 'ai_user')),
    origin_comment_id  INTEGER,
    parent_task_id     INTEGER REFERENCES tasks(id),
    title              TEXT,
    title_source       TEXT CHECK (title_source IN ('ai', 'human')),
    model              TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('running', 'waiting_on_user', 'done', 'archived')),
    status_reason      TEXT,
    waiting_on_task_id INTEGER REFERENCES tasks(id),
    session_id         TEXT,
    system_prompt      TEXT NOT NULL,
    token              TEXT NOT NULL UNIQUE,
    running_ms         INTEGER NOT NULL DEFAULT 0,
    running_since      INTEGER,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

INSERT INTO tasks_v2 (id, ticket_id, ai_user_id, origin, origin_comment_id, title, title_source, model, status,
                      status_reason, session_id, system_prompt, token, running_ms, running_since, created_at, updated_at)
SELECT id, ticket_id, ai_user_id, origin, origin_comment_id, title, title_source, model, status,
       status_reason, session_id, system_prompt, token, running_ms, running_since, created_at, updated_at
FROM tasks;

DROP TABLE tasks;
ALTER TABLE tasks_v2 RENAME TO tasks;

CREATE UNIQUE INDEX one_open_task_per_ai_user_and_ticket ON tasks(ticket_id, ai_user_id)
    WHERE ticket_id IS NOT NULL AND status <> 'archived';

ALTER TABLE task_events ADD COLUMN from_task_id INTEGER;
ALTER TABLE comments ADD COLUMN in_activity INTEGER NOT NULL DEFAULT 1;
