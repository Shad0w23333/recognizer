#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
# Isolate the original native CI dependencies in this job's temporary directory.
ci_venv="${RUNNER_TEMP:?RUNNER_TEMP is required}/recognizer-python-3.12"
uv venv --allow-existing --python 3.12 "$ci_venv"
source "$ci_venv/bin/activate"
export TOKENIZERS_PARALLELISM=false
export RECOGNIZER_NUM_THREADS=4
uv pip install -r requirements.txt -r requirements-test.txt -e . build==1.3.0
uv pip check

# Preserve the original browser/model prerequisites and the native Build suite.
python -m playwright install chromium
python -m patchright install chromium
ruff check .
ruff format .
mypy .
python .github/scripts/download-models.py
pytest --reruns 5 --only-rerun TimeoutError -v --ignore tests/test_recaptcha_sites.py \
  --junitxml="$RUNNER_TEMP/ci-artifacts/pytest.xml"
python -m build --sdist --wheel --installer uv

shopt -s nullglob
wheels=(dist/*.whl)
sdists=(dist/*.tar.gz)
if (( ${#wheels[@]} == 0 || ${#sdists[@]} == 0 )); then
  echo 'The native package build did not produce both a wheel and source distribution.' >&2
  exit 1
fi
for product in "${wheels[@]}" "${sdists[@]}"; do test -s "$product"; done
