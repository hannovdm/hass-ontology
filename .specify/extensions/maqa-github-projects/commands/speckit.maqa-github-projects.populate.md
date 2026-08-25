---
description: "Populate GitHub Project from specs/*/tasks.md. Creates one draft issue per feature with a markdown task list. Skips features already in the project. Safe to re-run."
---

You are populating a GitHub Project from spec-kit specs. Safe to re-run.

## Step 1 — Read config and set token

```bash
GH_TOKEN="${GH_TOKEN:-$(gh auth token 2>/dev/null)}"
source <(python3 -c "
import re
with open('maqa-github-projects/github-projects-config.yml') as f:
    for line in f:
        m = re.match(r'^(\w+):\s*\"?([^\"#\n]+)\"?', line.strip())
        if m and m.group(2).strip():
            print(f'{m.group(1).upper()}={m.group(2).strip()}')
")
```

## Step 2 — Get existing item titles from project

```bash
EXISTING=$(curl -s -H "Authorization: bearer $GH_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.github.com/graphql \
  -d "{\"query\":\"{ node(id: \\\"$PROJECT_ID\\\") { ... on ProjectV2 { items(first: 100) { nodes { content { ... on DraftIssue { title } ... on Issue { title } } } } } } }\"}" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
items = data['data']['node']['items']['nodes']
for item in items:
    c = item.get('content') or {}
    t = c.get('title','')
    if t: print(t.lower().strip())
")
```

## Step 3 — Discover specs and create items

For each ready spec not already in the project:

Parse title and tasks from `tasks.md` (same logic as maqa-trello populate).

Build body with markdown task list:
```markdown
## Tasks

- [ ] Task one
- [ ] Task two

Deps: none
```

Create draft issue in project:

```bash
curl -s -H "Authorization: bearer $GH_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.github.com/graphql \
  -d "{\"query\":\"mutation { addProjectV2DraftIssue(input: { projectId: \\\"$PROJECT_ID\\\", title: \\\"$TITLE\\\", body: \\\"$BODY\\\" }) { projectItem { id } } }\"}" | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['data']['addProjectV2DraftIssue']['projectItem']['id'])"
```

Set Status field to Todo:

```bash
curl -s -H "Authorization: bearer $GH_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.github.com/graphql \
  -d "{\"query\":\"mutation { updateProjectV2ItemFieldValue(input: { projectId: \\\"$PROJECT_ID\\\", itemId: \\\"$ITEM_ID\\\", fieldId: \\\"$STATUS_FIELD_ID\\\", value: { singleSelectOptionId: \\\"$TODO_OPTION_ID\\\" } }) { projectV2Item { id } } }\"}"
```

## Step 4 — Report

```
populated[N]{name,item_id,tasks}:
  ...
skipped[M]{name,reason}:
  ...
```
