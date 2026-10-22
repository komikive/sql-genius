#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_URL="${SQL_AGENT_DEMO_UI_URL:-http://127.0.0.1:3001}"
API_HEALTH_URL="${SQL_AGENT_DEMO_API_HEALTH_URL:-http://127.0.0.1:8000/health}"
LAB_RUNTIME_HOST="${SQL_AGENT_DEMO_LAB_RUNTIME_HOST:-postgres}"
LAB_API_BASE_URL="${SQL_AGENT_DEMO_LAB_API_BASE_URL:-http://127.0.0.1:8000}"
OVERVIEW_URL="${UI_URL}/overview"
WORKBENCH_URL="${UI_URL}/workbench"
DATASOURCES_URL="${UI_URL}/admin/datasources"
SKILLS_URL="${UI_URL}/admin/skills"

wait_for_url() {
  local name="$1"
  local url="$2"
  local retries="${3:-40}"
  local delay="${4:-2}"

  for ((i = 1; i <= retries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready: $url"
      return 0
    fi
    sleep "$delay"
  done

  echo "Timed out waiting for $name: $url" >&2
  return 1
}

provision_demo_labs() {
  if [[ "${SQL_AGENT_DEMO_SKIP_LABS:-0}" == "1" ]]; then
    echo "Skipping demo lab provisioning because SQL_AGENT_DEMO_SKIP_LABS=1"
    return 0
  fi

  local -a cmd=(
    docker compose exec -T backend
    uv run python provision_complex_postgres_labs.py
    --runtime-host "$LAB_RUNTIME_HOST"
    --api-base-url "$LAB_API_BASE_URL"
  )

  if [[ "${SQL_AGENT_DEMO_LABS_WITH_ONBOARDING:-0}" != "1" ]]; then
    cmd+=(--skip-onboarding)
  fi

  echo "Ensuring demo lab databases and datasource registrations..."
  "${cmd[@]}"
}

clean_demo_history() {
  if [[ "${SQL_AGENT_DEMO_CLEAN_HISTORY:-0}" != "1" ]]; then
    return 0
  fi

  echo "Cleaning Workbench history, execution logs, learning signals, and LangGraph checkpoints..."
  docker compose exec -T postgres sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
DELETE FROM learning_signals;
DELETE FROM sql_execution_history;
DELETE FROM thread_conversation_turns;
DELETE FROM thread_context_summaries;
DELETE FROM admin_sessions;
DELETE FROM checkpoint_writes;
DELETE FROM checkpoint_blobs;
DELETE FROM checkpoints;
SQL
}

print_rehearsal_steps() {
  cat <<'EOF'

Defense rehearsal flow
1. Open Overview and frame the system as a single LangGraph workflow.
2. In Workbench, ask an ambiguous question to trigger clarification.
3. Resume with a specific finance or sales question and narrate skill activation plus evidence retrieval.
4. Inspect generated SQL, call out the SELECT-only guard, then execute it.
5. Open Datasources and Skills to show the admin surfaces behind the workflow.

URLs
- UI: $UI_URL
- API health: $API_HEALTH_URL

Lab provisioning defaults
- `./scripts/demo.sh up` now auto-checks and provisions the three demo lab databases.
- Set `SQL_AGENT_DEMO_SKIP_LABS=1` to skip this step.
- Set `SQL_AGENT_DEMO_LABS_WITH_ONBOARDING=1` to also trigger datasource onboarding.
- Set `SQL_AGENT_DEMO_CLEAN_HISTORY=1` to clear Workbench history before rehearsal.

EOF
}

cmd="${1:-up}"

case "$cmd" in
  up)
    cd "$ROOT_DIR"
    docker compose up -d --build
    wait_for_url "API" "$API_HEALTH_URL"
    clean_demo_history
    provision_demo_labs
    wait_for_url "Web UI" "$UI_URL"
    wait_for_url "Overview route" "$OVERVIEW_URL"
    wait_for_url "Workbench route" "$WORKBENCH_URL"
    wait_for_url "Datasources route" "$DATASOURCES_URL"
    wait_for_url "Skills route" "$SKILLS_URL"
    docker compose ps
    print_rehearsal_steps
    ;;
  check|status)
    wait_for_url "API" "$API_HEALTH_URL" 1 0
    wait_for_url "Web UI" "$UI_URL" 1 0
    wait_for_url "Overview route" "$OVERVIEW_URL" 1 0
    wait_for_url "Workbench route" "$WORKBENCH_URL" 1 0
    wait_for_url "Datasources route" "$DATASOURCES_URL" 1 0
    wait_for_url "Skills route" "$SKILLS_URL" 1 0
    print_rehearsal_steps
    ;;
  down)
    cd "$ROOT_DIR"
    docker compose down
    ;;
  *)
    cat <<EOF >&2
Usage: scripts/demo.sh [up|check|status|down]

  up      Build and start the compose stack, then auto-provision demo labs.
  check   Validate that API and UI are already reachable.
  status  Same as check.
  down    Stop the compose stack.
EOF
    exit 1
    ;;
esac
