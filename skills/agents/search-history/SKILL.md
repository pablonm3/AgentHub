---
name: search-history
description: Search every ticket, comment and task chat of AgentHub — archived tasks included — for a phrase, and get the ticket and task where it occurs. Use when Pablo asks about something that was said, decided or found in another ticket, comment or task, or when you need earlier work of the team.
---

# Search AgentHub's history

```bash
agenthub search "<phrase>"
```

- The search is case-insensitive and matches the phrase as written, as a substring. Search for the
  most specific words (a code name, an id, a file name), not for a whole question; try a shorter or
  different phrase when nothing is found.
- It looks in ticket titles and descriptions, in every comment, and in the chat history of every
  task (Pablo's messages, the AI users' replies and working notes), archived tasks included.
- Each hit names where it matched, the ticket (`AH-<n>` and title), and the task (id, title, AI user,
  status) when the phrase is in a task's chat or in a comment a task posted. A hit in a ticket or a
  comment also lists the tasks attached to that ticket.
- In your answer, name for each phrase the ticket by key and title, and the task by id and title when
  the phrase is in a task. Say plainly when a phrase was not found.
