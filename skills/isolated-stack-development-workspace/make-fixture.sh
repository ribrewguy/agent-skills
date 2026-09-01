#!/usr/bin/env bash
# make-fixture.sh <dest> <mode>
# Generates the eval fixture repo "myapp": a Supabase-backed monorepo with a
# main checkout on `develop` and one live worktree at .worktrees/tf-9 on
# feature/tf-9_search.
#
# Modes:
#   base      worktree exists; its config still carries the SHARED project_id
#   isolated  worktree's config already isolated (project_id + ports remapped,
#             --skip-worktree set, analytics disabled)
#   envdrift  isolated, plus apps/api/.env copied from the main checkout and
#             still pointing at the shared stack; a migration exists on the
#             branch that the shared stack does not have
set -euo pipefail
DEST=$1; MODE=$2
rm -rf "$DEST"; mkdir -p "$DEST/supabase" "$DEST/apps/api" "$DEST/apps/web"
cd "$DEST"
git init -q -b develop
cat > supabase/config.toml <<'EOF'
project_id = "myapp"

[api]
port = 54321

[db]
port = 54322
shadow_port = 54320

[studio]
port = 54323

[inbucket]
port = 54324
smtp_port = 54325
pop3_port = 54326

[analytics]
enabled = true
EOF
cat > .isolated-stack.json <<'EOF'
{
  "stackPrefix": "myapp",
  "supabase": { "config": "supabase/config.toml" },
  "apps": [
    { "name": "api", "adapter": "node", "env": "apps/api/.env", "portVar": "API_PORT" },
    { "name": "web", "adapter": "nuxt", "env": "apps/web/.env", "https": true }
  ]
}
EOF
cat > package.json <<'EOF'
{ "name": "myapp", "private": true,
  "scripts": { "dev": "pnpm --filter ./apps/api dev & pnpm --filter ./apps/web dev",
               "db:reset": "supabase db reset" } }
EOF
printf '{ "name": "api", "scripts": { "dev": "node server.js" } }\n' > apps/api/package.json
printf '{ "name": "web", "scripts": { "dev": "nuxt dev" } }\n' > apps/web/package.json
cat > apps/api/.env.example <<'EOF'
SUPABASE_URL=http://127.0.0.1:54321
DB_PORT=54322
API_PORT=3100
SMTP_PORT=54325
EOF
printf 'node_modules/\n.env\n' > .gitignore
git add -A
git -c user.email=fixture@example.com -c user.name=Fixture commit -qm "init myapp"
# The main checkout runs the shared stack; it has a real .env (gitignored).
cp apps/api/.env.example apps/api/.env
git worktree add -q .worktrees/tf-9 -b feature/tf-9_search

WT="$DEST/.worktrees/tf-9"
if [ "$MODE" = "isolated" ] || [ "$MODE" = "envdrift" ]; then
  python3 - "$WT/supabase/config.toml" <<'PY'
import re, sys
path = sys.argv[1]
lines = open(path).read().splitlines(keepends=True)
out, n = [], 0
for ln in lines:
    if re.match(r'^ *project_id *=', ln):
        ln = re.sub(r'=.*$', '= "myapp-feature-tf-9-search"', ln)
    elif re.match(r'^ *[a-z0-9_]*port *= *[0-9]+', ln):
        ln = re.sub(r'= *[0-9]+', f'= {23110 + n}', ln); n += 1
    elif re.match(r'^ *enabled *= *true', ln):
        ln = ln.replace('true', 'false')
    out.append(ln)
open(path, 'w').writelines(out)
PY
  git -C "$WT" update-index --skip-worktree -- supabase/config.toml
fi
if [ "$MODE" = "envdrift" ]; then
  # A migration only this branch has: the shared stack knows nothing of it.
  mkdir -p "$WT/supabase/migrations"
  cat > "$WT/supabase/migrations/20260901000000_search_index.sql" <<'EOF'
create table search_index (id bigint primary key, term text not null);
EOF
  git -C "$WT" add supabase/migrations
  git -C "$WT" -c user.email=fixture@example.com -c user.name=Fixture commit -qm "feat(search): add search_index table [tf-9]"
  # The developer copied the env from the main checkout: every value still
  # points at the shared stack, and nothing errors.
  cp "$DEST/apps/api/.env.example" "$WT/apps/api/.env"
fi
echo "fixture ready: $DEST ($MODE)"
