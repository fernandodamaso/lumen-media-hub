#!/usr/bin/env bash

if [ -z "${BASH_VERSION:-}" ] || [ -z "${BASH_SOURCE+x}" ]; then
  echo "install.sh requires Bash" >&2
  exit 2
fi

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "install.sh requires Python 3.10 or newer (python3 was not found)" >&2
  exit 2
fi

python_version="$(python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor)')" || {
  echo "unable to determine Python version" >&2
  exit 2
}
read -r python_major python_minor <<<"${python_version}"
if ! [[ "${python_major:-}" =~ ^[0-9]+$ && "${python_minor:-}" =~ ^[0-9]+$ ]]; then
  echo "unable to determine Python version" >&2
  exit 2
fi
if (( python_major < 3 || (python_major == 3 && python_minor < 10) )); then
  echo "install.sh requires Python 3.10 or newer (found ${python_major}.${python_minor})" >&2
  exit 2
fi

export PYTHONPATH="${script_dir}/installer"
exec python3 -m lumen_installer "$@"
