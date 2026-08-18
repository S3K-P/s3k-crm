#!/usr/bin/env bash
# End-to-end persistence check against a running backend.
#
# Creates one record per CRM module, re-reads it through a separate request,
# exercises the business rules, then removes everything it made. It asserts the
# HTTP status of every create before trusting the body, so a failed request can
# never produce a passing "that field is empty" assertion.
#
# Usage:
#   docker compose up -d
#   npm run dev:backend                       # or any host:port you prefer
#   API_BASE=http://localhost:8000 \
#   EMAIL=you@example.com PASSWORD=... \
#   bash backend/scripts/e2e-smoke.sh
#
# It writes only to the organization the supplied account belongs to, and
# deletes each fixture at the end.
set -u
API="${API_BASE:-http://localhost:8000}/api/v1"
EMAIL="${EMAIL:?set EMAIL to a user with CRM permissions}"
PASSWORD="${PASSWORD:?set PASSWORD}"

LOGIN=$(curl -s -m 20 -X POST "$API/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
T=$(node -e "try{console.log(JSON.parse(process.argv[1]).access_token??'')}catch(e){console.log('')}" "$LOGIN")
O=$(node -e "try{console.log(JSON.parse(process.argv[1]).organization_id??'')}catch(e){console.log('')}" "$LOGIN")
if [ -z "$T" ]; then echo "FATAL: login failed against $API"; exit 1; fi
H=(-H "Authorization: Bearer $T" -H "X-Organization-Id: $O" -H "Content-Type: application/json")

pass=0; fail=0
check() { if [ "$1" = "$2" ]; then echo "  PASS $3"; pass=$((pass+1)); else echo "  FAIL $3 (expected '$2' got '$1')"; fail=$((fail+1)); fi }

# field <json> <path>  -> prints the value or empty
field() { node -e "try{const o=JSON.parse(process.argv[1]);console.log(o$2??'')}catch(e){console.log('')}" "$1"; }
# post <url> <body> -> sets BODY and CODE
post() { local r; r=$(curl -s -m 20 "${H[@]}" -w $'\n%{http_code}' -X POST "$API/$1" -d "$2"); CODE="${r##*$'\n'}"; BODY="${r%$'\n'*}"; }
get()  { local r; r=$(curl -s -m 20 "${H[@]}" -w $'\n%{http_code}' "$API/$1"); CODE="${r##*$'\n'}"; BODY="${r%$'\n'*}"; }
patch(){ local r; r=$(curl -s -m 20 "${H[@]}" -w $'\n%{http_code}' -X PATCH "$API/$1" -d "$2"); CODE="${r##*$'\n'}"; BODY="${r%$'\n'*}"; }
code() { curl -s -m 20 -o /dev/null -w '%{http_code}' "${H[@]}" -X "$1" "$API/$2" ${3:+-d "$3"}; }

echo "== PREFLIGHT =="
READY=$(curl -s -m 10 "${API_BASE:-http://localhost:8000}/health/ready")
check "$(field "$READY" ".dependencies.database")" "up" "database reachable"
if [ "$(field "$READY" ".dependencies.database")" != "up" ]; then
  echo "ABORT: database is down; the rest of the suite would report noise."
  exit 1
fi

echo "== ACCOUNTS =="
post "crm/accounts" '{"name":"E2E Verify Ltd","industry":"Testing","city":"Pune"}'
check "$CODE" "201" "create -> 201"
AID=$(field "$BODY" ".id")
get "crm/accounts/$AID"; check "$(field "$BODY" ".name")" "E2E Verify Ltd" "re-read by id"
patch "crm/accounts/$AID" '{"industry":"Verified"}' >/dev/null
get "crm/accounts/$AID"; check "$(field "$BODY" ".industry")" "Verified" "update persisted"
check "$(code POST "crm/accounts" '{"name":"E2E Verify Ltd"}')" "409" "duplicate name warns"

echo "== CONTACTS =="
post "crm/contacts" "{\"first_name\":\"Ada\",\"last_name\":\"Verify\",\"account_id\":\"$AID\",\"email\":\"ada.verify@e2e.test\"}"
check "$CODE" "201" "create -> 201"
CID=$(field "$BODY" ".id")
get "crm/contacts/$CID"
check "$(field "$BODY" ".full_name")" "Ada Verify" "re-read by id"
check "$(field "$BODY" ".account_id")" "$AID" "account FK persisted"
code POST "crm/contacts/$CID/primary" >/dev/null
get "crm/accounts/$AID"; check "$(field "$BODY" ".primary_contact_id")" "$CID" "primary-contact rule"

echo "== LEAD SOURCES =="
post "crm/lead-sources" '{"name":"E2E Channel","category":"Inbound"}'
check "$CODE" "201" "create -> 201"
SID=$(field "$BODY" ".id")
check "$(code POST "crm/lead-sources" '{"name":"E2E Channel"}')" "409" "duplicate name rejected"

echo "== LEADS =="
post "crm/leads" "{\"first_name\":\"Grace\",\"last_name\":\"Prospect\",\"company\":\"E2E Prospect Co\",\"lead_source_id\":\"$SID\"}"
check "$CODE" "201" "create -> 201"
LID=$(field "$BODY" ".id")
check "$(field "$BODY" ".status")" "NEW" "starts at NEW"
check "$(code POST "crm/leads/$LID/status" '{"status":"QUALIFIED"}')" "422" "illegal transition blocked"
code POST "crm/leads/$LID/status" '{"status":"CONTACTED"}' >/dev/null
code POST "crm/leads/$LID/status" '{"status":"QUALIFIED"}' >/dev/null
get "crm/leads/$LID"; check "$(field "$BODY" ".status")" "QUALIFIED" "legal transitions persisted"
get "crm/lead-sources/$SID"; check "$(field "$BODY" ".lead_count")" "1" "derived lead_count"

echo "== LEAD CONVERSION (transactional) =="
post "crm/leads/$LID/convert" '{"create_opportunity":true,"opportunity_name":"E2E Deal","opportunity_value":"5000"}'
check "$CODE" "201" "convert -> 201"
CAID=$(field "$BODY" ".account_id"); CCID=$(field "$BODY" ".contact_id"); COID=$(field "$BODY" ".opportunity_id")
check "$([ -n "$CAID" ] && [ -n "$CCID" ] && [ -n "$COID" ] && echo ok)" "ok" "account+contact+opportunity created"
get "crm/leads/$LID"; check "$(field "$BODY" ".status")" "CONVERTED" "lead marked converted"
check "$(code POST "crm/leads/$LID/convert" '{}')" "409" "re-conversion blocked"

echo "== OPPORTUNITIES =="
get "crm/opportunities/$COID"; check "$(field "$BODY" ".name")" "E2E Deal" "converted deal readable"
get "crm/opportunities/stages"; STAGES="$BODY"
S2=$(field "$STAGES" "[1].id")
LOST=$(node -e "const a=JSON.parse(process.argv[1]);const l=a.find(x=>x.is_lost);console.log(l?l.id:'')" "$STAGES")
code POST "crm/opportunities/$COID/stage" "{\"stage_id\":\"$S2\"}" >/dev/null
get "crm/opportunities/$COID"; check "$(field "$BODY" ".stage_id")" "$S2" "stage change persisted"
get "crm/opportunities/$COID/history"; check "$(field "$BODY" ".length")" "1" "stage history recorded"
check "$(code POST "crm/opportunities/$COID/stage" "{\"stage_id\":\"$LOST\"}")" "422" "lost stage requires reason"

echo "== TASKS =="
post "crm/tasks" "{\"title\":\"E2E task\",\"priority\":\"HIGH\",\"related_entity_type\":\"ACCOUNT\",\"related_entity_id\":\"$AID\"}"
check "$CODE" "201" "create -> 201"
TID=$(field "$BODY" ".id")
check "$(field "$BODY" ".completed_at")" "" "completed_at null while pending"
code POST "crm/tasks/$TID/status" '{"status":"COMPLETED"}' >/dev/null
get "crm/tasks/$TID"
check "$([ -n "$(field "$BODY" ".completed_at")" ] && echo ok)" "ok" "completed_at derived on completion"
check "$(code POST "crm/tasks" '{"title":"bad link","related_entity_type":"ACCOUNT","related_entity_id":"00000000-0000-0000-0000-000000000000"}')" "422" "unknown link target rejected"

echo "== NOTES =="
post "crm/notes" "{\"content\":\"E2E note\",\"related_entity_type\":\"ACCOUNT\",\"related_entity_id\":\"$AID\"}"
check "$CODE" "201" "create -> 201"
NID=$(field "$BODY" ".id")
get "crm/notes?related_entity_type=ACCOUNT&related_entity_id=$AID"
check "$(field "$BODY" ".pagination.total")" "1" "note listed against account"

echo "== ACTIVITIES =="
post "crm/activities" "{\"type\":\"CALL\",\"subject\":\"E2E call\",\"status\":\"COMPLETED\",\"related_entity_type\":\"ACCOUNT\",\"related_entity_id\":\"$AID\"}"
check "$CODE" "201" "create -> 201"
ACTID=$(field "$BODY" ".id")
get "crm/activities/timeline?related_entity_type=ACCOUNT&related_entity_id=$AID"
check "$(field "$BODY" ".length")" "1" "appears on entity timeline"
post "crm/activities" '{"type":"MEETING","subject":"E2E meeting","meeting":{"meeting_type":"VIDEO","start_time":"2026-09-01T10:00:00Z"}}'
check "$CODE" "201" "meeting create -> 201"
MID=$(field "$BODY" ".id")
get "crm/activities/$MID"; check "$(field "$BODY" ".meeting.meeting_type")" "VIDEO" "meeting extension persisted"
check "$(code POST "crm/activities" '{"type":"MEETING","subject":"no detail"}')" "422" "meeting without detail rejected"

echo "== CAMPAIGNS =="
post "crm/campaigns" '{"name":"E2E Campaign","type":"EMAIL"}'
check "$CODE" "201" "create -> 201"
CMID=$(field "$BODY" ".id")
check "$(code POST "crm/campaigns/$CMID/members" "{\"entity_type\":\"CONTACT\",\"entity_id\":\"$CCID\"}")" "201" "member added"
check "$(code POST "crm/campaigns/$CMID/members" "{\"entity_type\":\"CONTACT\",\"entity_id\":\"$CCID\"}")" "409" "duplicate member rejected"

echo "== DASHBOARD REFLECTS REAL DATA =="
get "crm/dashboard/summary"
check "$(field "$BODY" ".kpis.open_opportunities")" "1" "open opportunity counted"
check "$(field "$BODY" ".kpis.new_leads")" "1" "lead counted"

echo "== CLEANUP =="
for u in "crm/campaigns/$CMID" "crm/activities/$ACTID" "crm/activities/$MID" "crm/notes/$NID" "crm/tasks/$TID" "crm/opportunities/$COID" "crm/contacts/$CCID" "crm/contacts/$CID" "crm/leads/$LID" "crm/accounts/$CAID" "crm/accounts/$AID" "crm/lead-sources/$SID"; do
  curl -s -m 20 "${H[@]}" -o /dev/null -X DELETE "$API/$u"
done
get "crm/accounts"; REMAIN=$(field "$BODY" ".pagination.total")
echo "  accounts remaining after cleanup: $REMAIN"

echo ""
echo "PASS=$pass FAIL=$fail"
