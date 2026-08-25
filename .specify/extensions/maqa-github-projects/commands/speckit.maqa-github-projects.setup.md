---
description: "Bootstrap GitHub Projects v2 config for MAQA. Reads your projects and Status field options via GraphQL and generates maqa-github-projects/github-projects-config.yml. Run once per project."
---

You are setting up GitHub Projects v2 integration for MAQA.

## Prerequisites check

```bash
GH_TOKEN="${GH_TOKEN:-$(gh auth token 2>/dev/null)}"
[ -n "$GH_TOKEN" ] && echo "Token: set" || echo "ERROR: GH_TOKEN not set and gh CLI not authenticated. Run: gh auth login"
```

Stop if no token.

## Step 1 — List accessible projects

Ask user for owner (org or username), then list their projects:

```bash
OWNER="<org-or-username>"
curl -s -H "Authorization: bearer $GH_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.github.com/graphql \
  -d "{\"query\":\"{ user(login: \\\"$OWNER\\\") { projectsV2(first: 20) { nodes { number title id } } } }\"}" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
nodes = data.get('data',{}).get('user',{}).get('projectsV2',{}).get('nodes',[])
for p in nodes:
    print(f\"#{p['number']} — {p['title']} ({p['id']})\")
"
```

If owner is an org, replace `user` with `organization` in the query.

## Step 2 — Get Status field and options

```bash
PROJECT_ID="<selected project node ID>"
curl -s -H "Authorization: bearer $GH_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.github.com/graphql \
  -d "{\"query\":\"{ node(id: \\\"$PROJECT_ID\\\") { ... on ProjectV2 { fields(first: 20) { nodes { ... on ProjectV2SingleSelectField { id name options { id name } } } } } } }\"}" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
fields = data['data']['node']['fields']['nodes']
for f in fields:
    if 'options' in f:
        print(f\"Field: {f['name']} ({f['id']})\")
        for o in f['options']:
            print(f\"  {o['id']} — {o['name']}\")
"
```

Map Status field options to: Todo, In Progress, In Review, Done. Ask user to confirm.

## Step 3 — Write config

```bash
mkdir -p maqa-github-projects
cat > maqa-github-projects/github-projects-config.yml << EOF
# MAQA GitHub Projects Configuration — generated $(date -Iseconds)
owner: "$OWNER"
project_number: "$PROJECT_NUMBER"
project_id: "$PROJECT_ID"
status_field_id: "$STATUS_FIELD_ID"
todo_option_id: "$TODO_ID"
in_progress_option_id: "$IN_PROGRESS_ID"
in_review_option_id: "$IN_REVIEW_ID"
done_option_id: "$DONE_ID"
linked_repo: ""
EOF
```

## Done

Report mapped options and tell user to run `/speckit.maqa.coordinator`.
