#!/usr/bin/env bash
set -euo pipefail
if [[ -x work/offline-venv/bin/python ]]; then
  PY=work/offline-venv/bin/python
else
  PY=work/linux_runtime/venv/bin/python
fi
gcc -Wall -Werror -nostdlib -fno-builtin -std=gnu11 -Wfatal-errors -Wno-pointer-to-int-cast -shared -fPIC -Iwork/carrotpilot/opendbc_repo/opendbc/safety/board -Iwork/carrotpilot/opendbc_repo/opendbc/safety work/safety_validation/probe.c -o work/safety_validation/libsafety_root_verified.so
$PY work/safety_validation/verify_compiled.py work/safety_validation/libsafety_root_verified.so --output work/safety_validation/root_core.json --exhaustive
$PY work/safety_validation/verify_offsets.py work/safety_validation/libsafety_root_verified.so --output work/safety_validation/root_offsets.json
$PY work/safety_validation/verify_timing.py work/safety_validation/libsafety_root_verified.so --output work/safety_validation/root_timing.json
$PY work/safety_validation/verify_brand_steering.py work/safety_validation/libsafety_root_verified.so --output work/safety_validation/root_brand_steering.json
$PY work/safety_validation/run_upstream_tests.py work/safety_validation/libsafety_root_verified.so work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_toyota.py work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_tesla.py work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_ford.py work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_volkswagen_mqb.py work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_volkswagen_pq.py work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_rivian.py --junit work/safety_validation/root_primary.xml --quiet-c
