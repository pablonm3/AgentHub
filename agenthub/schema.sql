-- AgentHub database at version 2, applied by db.Database to an empty file (PRAGMA user_version 0).
-- An older file is brought here by migrations/; a migrated file and a fresh one have the same tables.

CREATE TABLE users (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('human', 'ai')),
    handle   TEXT NOT NULL UNIQUE,
    initials TEXT NOT NULL,
    color    TEXT NOT NULL,
    prompt   TEXT
);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- project: a name registered in private/harness.yaml; NULL is "No project". Shown as AH-<id>.
CREATE TABLE tickets (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    stage       TEXT NOT NULL,
    position    REAL NOT NULL,
    assignee_id TEXT NOT NULL REFERENCES users(id),
    model       TEXT NOT NULL,
    project     TEXT,
    labels      TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- task_id: the task that posted the comment (AI comments only).
-- in_activity: 0 for a comment posted by a child task while it answered to its parent task
CREATE TABLE comments (
    id          INTEGER PRIMARY KEY,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    author_id   TEXT NOT NULL REFERENCES users(id),
    body        TEXT NOT NULL,
    task_id     INTEGER,
    reply_to_id INTEGER,
    created_at  TEXT NOT NULL,
    in_activity INTEGER NOT NULL DEFAULT 1
);

-- origin_comment_id: the comment that started a mention task, or that announces a child task (origin ai_user)
-- parent_task_id: the task whose session created this one (origin ai_user)
-- waiting_on_task_id: the child task a waiting parent said it waits for; NULL unless status is waiting_on_user
CREATE TABLE tasks (
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

-- at most one open task of one AI user on one ticket (AC4, AC45)
CREATE UNIQUE INDEX one_open_task_per_ai_user_and_ticket ON tasks(ticket_id, ai_user_id)
    WHERE ticket_id IS NOT NULL AND status <> 'archived';

-- one row per AI turn; the token columns hold this turn's own use
CREATE TABLE turns (
    id                    INTEGER PRIMARY KEY,
    task_id               INTEGER NOT NULL REFERENCES tasks(id),
    started_at            INTEGER NOT NULL,
    ended_at              INTEGER,
    last_event_at         INTEGER,
    model                 TEXT,
    session_id            TEXT,
    outcome               TEXT CHECK (outcome IN ('completed', 'stopped', 'failed', 'interrupted')),
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens     INTEGER NOT NULL DEFAULT 0
);

-- kind: user (Pablo) | ai_user (another task's AI user) | notice | assistant | tool | reply | system | error
-- a user, ai_user or notice row with turn_id NULL is queued, not yet delivered
-- turn_id -1 (NO_TURN in tasks.py): delivered, but not part of a model turn (system, error, gate events)
-- comment_id: the ticket comment this user event delivers (one comment can reach several tasks)
-- from_task_id: the task that sent an ai_user row
CREATE TABLE task_events (
    id           INTEGER PRIMARY KEY,
    task_id      INTEGER NOT NULL REFERENCES tasks(id),
    turn_id      INTEGER,
    comment_id   INTEGER,
    kind         TEXT NOT NULL,
    text         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    from_task_id INTEGER
);
CREATE INDEX task_events_by_task ON task_events(task_id, id);

-- the token columns hold the sum over the run's step executions
-- status: running | paused | done | failed | blocked (from state.json) | stopped (by Pablo) | interrupted (by a restart)
-- pending_kind: gate | question, while the paused run waits on an answer (NULL otherwise)
CREATE TABLE harness_runs (
    run_id                TEXT PRIMARY KEY,
    task_id               INTEGER NOT NULL REFERENCES tasks(id),
    workflow              TEXT NOT NULL,
    feature               TEXT NOT NULL,
    project               TEXT NOT NULL,
    status                TEXT NOT NULL,
    pid                   INTEGER,
    pending_kind          TEXT,
    pending_decision_file TEXT,
    pending_posted_at     TEXT,
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
    started_at            TEXT NOT NULL,
    ended_at              TEXT
);
