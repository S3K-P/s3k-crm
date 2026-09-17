#!/usr/bin/env bash
# Provision the three fixed development sign-ins, one per system role.
#
# The addresses and the password below are FIXED and must not drift: they are
# what `frontend/app/login/DevCredentials.tsx` offers on the login page. This
# script is the source of truth for both. Change a value here and you must
# change it there.
#
#   Admin    admin@demo.example      everything, incl. admin screens
#   Manager  manager@demo.example    all CRM records, may delete
#   User     user@demo.example       own records only
#
# Idempotent, and safe to re-run against a database that already has them:
# missing members are created, and every account's password is reset to the
# fixed value, so a rebuilt database always ends up with the same credentials.
#
# Usage:
#   docker compose up -d
#   cd backend && uv run alembic upgrade head
#   npm run dev:backend                       # the API must be running
#   bash backend/scripts/seed-dev-accounts.sh
#
# Development only. These accounts are provisioned nowhere else; never run this
# against a shared or deployed environment.
set -u

API="${API_BASE:-http://localhost:8000}/api/v1"
ORG_NAME="${ORG_NAME:-Demo}"
PASSWORD='DemoPassw0rd!2026'
ADMIN_EMAIL='admin@demo.example'

json() { node -e "try{const o=JSON.parse(process.argv[1]);console.log(o$2??'')}catch(e){console.log('')}" "$1"; }

# --- 1. The organization and its administrator -----------------------------
# `app.bootstrap` is itself idempotent: an existing slug or address is reused
# rather than duplicated, and it grants the CRM entitlement and the default
# pipeline that opportunities need.
echo "==> bootstrapping organization '$ORG_NAME' and $ADMIN_EMAIL"
( cd "$(dirname "$0")/.." && BOOTSTRAP_PASSWORD="$PASSWORD" \
    uv run python -m app.bootstrap --organization "$ORG_NAME" --email "$ADMIN_EMAIL" ) \
  || { echo "FATAL: bootstrap failed"; exit 1; }

LOGIN=$(curl -s -m 20 -X POST "$API/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\"}")
TOKEN=$(json "$LOGIN" .access_token)
if [ -z "$TOKEN" ]; then
  echo "FATAL: could not sign in as $ADMIN_EMAIL against $API — is the backend running?"
  exit 1
fi
H=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")

# --- 2. Role ids ------------------------------------------------------------
ROLES=$(curl -s -m 20 "${H[@]}" "$API/roles")
role_id() { node -e "
try{const r=JSON.parse(process.argv[1]).find(x=>x.name===process.argv[2]);console.log(r?r.id:'')}
catch(e){console.log('')}" "$ROLES" "$1"; }

# --- 3. Manager and User ----------------------------------------------------
# `POST /organizations/current/users` creates the user and the membership but
# does not attach roles, so the grant is a second, explicit call.
seed_member() {
  local email="$1" first="$2" last="$3" role_name="$4"
  local role_id members membership_id existing

  role_id=$(role_id "$role_name")
  if [ -z "$role_id" ]; then echo "  FAIL $email: no '$role_name' role in the catalogue"; return 1; fi

  members=$(curl -s -m 20 "${H[@]}" "$API/organizations/current/members")
  membership_id=$(node -e "
try{const m=JSON.parse(process.argv[1]);const a=Array.isArray(m)?m:(m.data??[]);
const f=a.find(x=>x.email===process.argv[2]);console.log(f?f.id:'')}catch(e){console.log('')}" "$members" "$email")

  if [ -z "$membership_id" ]; then
    local created
    created=$(curl -s -m 20 -X POST "$API/organizations/current/users" "${H[@]}" \
      -d "{\"email\":\"$email\",\"password\":\"$PASSWORD\",\"first_name\":\"$first\",\"last_name\":\"$last\"}")
    membership_id=$(json "$created" .id)
    if [ -z "$membership_id" ]; then echo "  FAIL $email: $created"; return 1; fi
    echo "  created  $email"
  else
    # Already present: reset the password so a re-run always restores the
    # documented credential, whatever it was changed to in the meantime.
    local user_id
    user_id=$(node -e "
try{const m=JSON.parse(process.argv[1]);const a=Array.isArray(m)?m:(m.data??[]);
const f=a.find(x=>x.email===process.argv[2]);console.log(f?f.user_id:'')}catch(e){console.log('')}" "$members" "$email")
    curl -s -m 20 -o /dev/null -X POST "$API/organizations/current/members/$user_id/reset-password" \
      "${H[@]}" -d "{\"new_password\":\"$PASSWORD\"}"
    echo "  reset    $email"
  fi

  # Assigning a role already held is a no-op, so this needs no existence check.
  existing=$(curl -s -m 20 -o /dev/null -w '%{http_code}' -X POST "$API/roles/assignments" \
    "${H[@]}" -d "{\"membership_id\":\"$membership_id\",\"role_id\":\"$role_id\"}")
  if [ "$existing" != "204" ]; then echo "  WARN  $email: role assignment returned $existing"; fi
}

echo "==> seeding members"
seed_member 'manager@demo.example' 'Morgan' 'Reid'  'Manager'
seed_member 'user@demo.example'    'Sam'    'Patel' 'User'

echo
echo "Ready. All three sign in with: $PASSWORD"
curl -s -m 20 "${H[@]}" "$API/organizations/current/members" | node -e "
let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{
try{const m=JSON.parse(s);const a=Array.isArray(m)?m:(m.data??[]);
for(const x of a) console.log('  '+x.email.padEnd(24)+(x.roles??[]).join(', '));}catch(e){}})"
