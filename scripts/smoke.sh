#!/usr/bin/env bash
# End-to-end smoke test against a running stack (through the webapp's nginx,
# i.e. exactly the path a browser takes).
#
#   BASE_URL=http://localhost:8080 ADMIN_TOKEN=... ./scripts/smoke.sh
set -euo pipefail

cd "$(dirname "$0")/.."
BASE_URL="${BASE_URL:-http://localhost:${WEB_PORT:-8080}}"
API="$BASE_URL/api/v1"
if [[ -z "${ADMIN_TOKEN:-}" && -f .env ]]; then
  ADMIN_TOKEN="$(grep -E '^ADMIN_TOKEN=' .env | cut -d= -f2- || true)"
fi

pass=0
fail=0
ok()   { echo "  ✓ $*"; pass=$((pass + 1)); }
bad()  { echo "  ✗ $*"; fail=$((fail + 1)); }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {'d': d}))" "$1"; }

# POST with JSON; honours 429 Retry-After so the test works with the
# gateway's rate limiter enabled.
post() {
  local out code wait
  for _ in $(seq 1 30); do
    out=$(curl -sS -D /tmp/oj-smoke-headers -X POST "$API$1" -H 'Content-Type: application/json' -d "$2")
    code=$(head -1 /tmp/oj-smoke-headers | awk '{print $2}')
    if [[ "$code" != 429 ]]; then echo "$out"; return; fi
    wait=$(grep -i '^retry-after:' /tmp/oj-smoke-headers | tr -dc '0-9')
    sleep "${wait:-1}"
  done
  echo "$out"
}

# submit <problem_id> <language> <source>  -> prints final verdict
submit() {
  local body id status sub
  body=$(python3 -c 'import json,sys; print(json.dumps({"problem_id": int(sys.argv[1]), "language": sys.argv[2], "source": sys.argv[3], "username": "smoke"}))' "$1" "$2" "$3")
  id=$(post /submissions "$body" | json 'd["id"]')
  for _ in $(seq 1 120); do
    sub=$(curl -sS "$API/submissions/$id")
    status=$(echo "$sub" | json 'd["status"]')
    if [[ "$status" == FINISHED || "$status" == FAILED ]]; then
      echo "$sub" | json 'd["verdict"] + " " + str(d["passed"]) + "/" + str(d["total"])'
      return
    fi
    sleep 0.5
  done
  echo "TIMEOUT"
}

expect_verdict() { # name problem lang expected source
  local got
  got=$(submit "$2" "$3" "$5")
  if [[ "$got" == "$4"* ]]; then ok "$1: $got"; else bad "$1: expected $4, got $got"; fi
}

echo "== health"
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/healthz")" == 200 ]] && ok "webapp up" || bad "webapp down"
status=$(curl -sS "$API/status")
[[ "$(echo "$status" | json 'd["status"]')" == ok ]] && ok "dependencies ready: $status" || bad "status: $status"
[[ "$(curl -s "$BASE_URL/" | grep -c '<title>Online Judge</title>')" == 1 ]] && ok "index.html served" || bad "index.html"

echo "== catalogue"
langs=$(curl -sS "$API/languages" | json '",".join(sorted(l["id"] for l in d))')
[[ "$langs" == "c,cpp,javascript,python" ]] && ok "languages: $langs" || bad "languages: $langs"
APB=$(curl -sS "$API/problems" | json '[p["id"] for p in d if p["slug"]=="a-plus-b"][0]')
REV=$(curl -sS "$API/problems" | json '[p["id"] for p in d if p["slug"]=="reverse-string"][0]')
FIB=$(curl -sS "$API/problems" | json '[p["id"] for p in d if p["slug"]=="fibonacci"][0]')
ok "seeded problems: a-plus-b=$APB reverse-string=$REV fibonacci=$FIB"
samples=$(curl -sS "$API/problems/$APB" | json 'len(d["samples"])')
tcs_hidden=$(curl -sS "$API/problems/$APB" | json '"test_cases" not in d and "expected_output" not in str(d)')
[[ "$samples" == 2 && "$tcs_hidden" == True ]] && ok "problem exposes only samples" || bad "samples=$samples hidden=$tcs_hidden"

echo "== judging (all four languages)"
expect_verdict "python AC"     "$APB" python AC  'a, b = map(int, input().split())
print(a + b)'
expect_verdict "python WA"     "$APB" python WA  'a, b = map(int, input().split())
print(a - b)'
expect_verdict "c AC"          "$APB" c      AC  '#include <stdio.h>
int main(void){ long long a,b; scanf("%lld %lld",&a,&b); printf("%lld\n",a+b); return 0; }'
expect_verdict "cpp AC (fib)"  "$FIB" cpp    AC  '#include <bits/stdc++.h>
int main(){ int n; std::cin>>n; long long a=0,b=1; for(int i=0;i<n;i++){ long long t=a+b; a=b; b=t; } std::cout<<a<<"\n"; }'
expect_verdict "js AC (rev)"   "$REV" javascript AC 'const s = require("fs").readFileSync(0, "utf8").replace(/\n$/, "");
console.log([...s].reverse().join(""));'
expect_verdict "cpp CE"        "$APB" cpp    CE  'int main( {'
expect_verdict "python TLE"    "$APB" python TLE 'while True: pass'
expect_verdict "python RE"     "$APB" python RE  'raise ValueError("boom")'

echo "== custom run"
run=$(post /run '{"language":"python","source":"print(input()[::-1])","stdin":"abc"}')
[[ "$(echo "$run" | json 'd["stdout"]')" == cba ]] && ok "run: $(echo "$run" | json 'd["status"]') stdout=cba" || bad "run: $run"

echo "== sandbox isolation"
net=$(post /run '{"language":"python","source":"import socket\ntry:\n  socket.create_connection((\"dao\",8001),timeout=2); print(\"OPEN\")\nexcept Exception as e: print(\"blocked\")"}' | json 'd["stdout"].strip()')
[[ "$net" == blocked ]] && ok "submitted code cannot reach internal services" || bad "network reachable: $net"

echo "== admin"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/admin/problems" -H 'Content-Type: application/json' -d '{}')
[[ "$code" == 401 || "$code" == 403 ]] && ok "admin without token rejected ($code)" || bad "admin without token: $code"
if [[ -n "${ADMIN_TOKEN:-}" ]]; then
  slug="smoke-$(date +%s)"
  created=$(curl -sS -X POST "$API/admin/problems" -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
    -d "{\"slug\":\"$slug\",\"title\":\"Smoke Square\",\"statement\":\"Print n*n\",\"time_limit_ms\":1000,\"memory_limit_mb\":64,
         \"test_cases\":[{\"input\":\"3\",\"expected_output\":\"9\",\"is_sample\":true},{\"input\":\"12\",\"expected_output\":\"144\"}]}")
  pid=$(echo "$created" | json 'd["id"]')
  ok "created problem #$pid ($slug)"
  expect_verdict "new problem AC" "$pid" python AC 'n=int(input()); print(n*n)'
  code=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$API/admin/problems/$pid" -H "Authorization: Bearer $ADMIN_TOKEN")
  [[ "$code" == 204 ]] && ok "deleted problem #$pid" || bad "delete: $code"
else
  echo "  - ADMIN_TOKEN not set, skipping admin write tests"
fi

echo
echo "passed: $pass  failed: $fail"
[[ $fail -eq 0 ]]
