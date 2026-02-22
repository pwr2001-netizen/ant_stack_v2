# ant_stack_v2 (Discovery Stable + Golden Locked)

## Root
- Project root: `~/ant_stack_v2`
- Legacy (read/execute only): `~/ant_stack`

## What is locked
- Discovery pipeline entrypoint: `bin/run_discovery.sh`
- Golden outputs: `tests/golden/out_us.txt`, `tests/golden/out_kr.txt`
- Test runner (diff): `bin/run_tests.sh`

## Quick commands
- Smoke: `bin/smoke.sh`
- Tests: `bin/run_tests.sh`

## Rules (헌법 v2 관점)
- v2에서만 수정/운영한다. legacy는 참조/실행만.
- Golden은 자동 갱신 금지. 의도적으로 바꿀 때만 수동 재생성.
- 출력 경로 단일 진실: `config/paths.json` + `var/discovery/*`
