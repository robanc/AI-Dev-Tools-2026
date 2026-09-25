#!/usr/bin/env bash
set -euo pipefail

# Deliberately does not deploy or invoke AWS/GitHub/Docker. It records a human
# decision and prints the approved manual release-process handoff only.
incident_id="${1:-}"
if [[ ! "$incident_id" =~ ^INC-[0-9]{4}-[0-9]{3}$ ]]; then
  echo "Usage: rollback.sh INC-YYYY-NNN" >&2
  exit 2
fi
printf 'Rollback for %s requires a human operator. Type exactly: AUTHORIZE %s\n' "$incident_id" "$incident_id"
IFS= read -r authorization
if [[ "$authorization" != "AUTHORIZE $incident_id" ]]; then
  echo "Denied: explicit operator authorization was not provided." >&2
  exit 3
fi
cat <<EOF
Operator authorization recorded for $incident_id.
No rollback command was executed. The operator must use the approved
development/production release process, review the target immutable digest,
and record the command and result in the incident record.
EOF
