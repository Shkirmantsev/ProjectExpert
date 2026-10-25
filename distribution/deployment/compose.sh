#!/usr/bin/env bash
# Linux deployment launcher. Thin wrapper: it collects probe evidence and
# applies the decision produced by `python -m pi_platform.cli inference plan`.
# The GPU is an optimisation -- an unavailable or unusable GPU degrades to the
# validated CPU profile and never aborts the deployment. A GPU that works but
# is SLOWER than the CPU baseline is also not selected.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

read_env() { sed -n "s/^$1=//p" deployment.env | tail -1; }

requested="${PI_ACCELERATOR:-$(read_env PI_ACCELERATOR)}"
requested="${requested:-auto}"
model="${PI_EMBEDDING_MODEL:-$(read_env PI_EMBEDDING_MODEL)}"
model="${model:-gemma}"
pinned_device="${PI_GPU_DEVICE:-}"
benchmark_iterations="${PI_BENCHMARK_ITERATIONS:-20}"

case "$model" in
  gemma|gemma-gguf) model=gemma ;;
  gemma-torch) ;;
  *)
    echo "PI_EMBEDDING_MODEL '$model' is not supported. Use 'gemma' (EmbeddingGemma 2 Q8_0 GGUF, the default) or 'gemma-torch'. Retired aliases (qwen, qwen-gguf, qwen3) are no longer selectable." >&2
    exit 2
    ;;
esac
case "$requested" in
  auto|cpu|vulkan|cuda) ;;
  *) echo 'PI_ACCELERATOR must be auto, cpu, vulkan or cuda' >&2; exit 2 ;;
esac

files=(-f compose.yaml)
if [ "$model" = gemma-torch ]; then
  # Native PyTorch binding: no llama.cpp sidecar, no runtime probing.
  export PI_EMBEDDING_DEVICE="${PI_EMBEDDING_DEVICE:-cpu}"
  exec docker compose --env-file deployment.env "${files[@]}" "$@"
fi

# The Gemma sidecar topology is the default; the backend overlay supplies the
# device (and the GPU fit budget).
files+=(-f compose.accelerator.yaml)

is_up=0
case " $* " in *" up "*) is_up=1 ;; esac

# ---------------------------------------------------------------------------
# Evidence helpers (portable bash; no Python required on the host).
# ---------------------------------------------------------------------------
json_escape() {
  local s=$1
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/\\r}
  s=${s//$'\t'/\\t}
  printf '%s' "$s" | tr -d '\000-\010\013\014\016-\037'
}

candidates=""
add_candidate() { # backend ok exit_code output
  local entry
  entry="{\"backend\": \"$1\", \"ok\": $2, \"exit_code\": $3, \"output\": \"$(json_escape "$4")\"}"
  if [ -n "$candidates" ]; then
    candidates="$candidates, $entry"
  else
    candidates="$entry"
  fi
}

measurements=""
add_measurement() { # backend median_ms
  local entry
  entry="\"$1\": $2"
  if [ -n "$measurements" ]; then
    measurements="$measurements, $entry"
  else
    measurements="$entry"
  fi
}

b64_encode() {
  if command -v base64 >/dev/null 2>&1 && printf 'x' | base64 --wrap=0 >/dev/null 2>&1; then
    base64 --wrap=0
  elif command -v openssl >/dev/null 2>&1; then
    openssl base64 -A
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import base64,sys; sys.stdout.write(base64.b64encode(sys.stdin.buffer.read()).decode("ascii"))'
  else
    echo 'No portable base64 encoder found (need GNU base64 --wrap=0, openssl base64 -A, or python3). Install one and retry.' >&2
    return 1
  fi
}

probe_rc=0
probe_output=""
probe_backend() { # backend
  probe_rc=0
  probe_output=$(docker compose --env-file deployment.env -f compose.yaml \
    -f compose.accelerator.yaml -f "compose.$1.yaml" \
    run --rm --no-deps -T embeddings --list-devices 2>&1) || probe_rc=$?
}

apply_decision() { # backend device fit_target
  export PI_ACCELERATOR="$1"
  export PI_GPU_DEVICE="$2"
  export PI_FIT_TARGET="$3"
}

# ---------------------------------------------------------------------------
# Measurement: the GPU is selected only when it is measurably faster than the
# CPU baseline. Each candidate runtime is started, measured and stopped again
# before the winner is started for real.
# ---------------------------------------------------------------------------
benchmark_backend() { # backend -> prints the median latency in ms
  local backend="$1"
  local median=""
  docker compose --env-file deployment.env -f compose.yaml \
    -f compose.accelerator.yaml -f "compose.$backend.yaml" \
    up -d --wait embeddings >/dev/null 2>&1 || return 1
  median=$(docker compose --env-file deployment.env -f compose.yaml \
    run --rm --no-deps -T production \
    inference benchmark \
    --endpoint http://embeddings:8769 --iterations "$benchmark_iterations" \
    2>/dev/null \
    | sed -n 's/^[[:space:]]*"median_ms":[[:space:]]*\([0-9.]*\).*$/\1/p' | head -1)
  docker compose --env-file deployment.env -f compose.yaml \
    -f compose.accelerator.yaml -f "compose.$backend.yaml" \
    stop embeddings >/dev/null 2>&1 || true
  [ -n "$median" ] || return 1
  printf '%s' "$median"
}

# ---------------------------------------------------------------------------
# Non-start commands (config, logs, down, stop, ps, ...) resolve "auto" to the
# CPU profile without probing. `up` performs real backend detection.
# ---------------------------------------------------------------------------
if [ "$is_up" != 1 ]; then
  backend="$requested"
  if [ "$backend" = auto ]; then backend=cpu; fi
  files+=(-f "compose.$backend.yaml")
  if [ "$backend" = cpu ]; then
    apply_decision cpu none "${PI_FIT_TARGET:-192}"
  else
    apply_decision "$backend" "${PI_GPU_DEVICE:-$( [ "$backend" = cuda ] && echo CUDA0 || echo Vulkan0 )}" "${PI_FIT_TARGET:-192}"
  fi
  exec docker compose --env-file deployment.env "${files[@]}" "$@"
fi

# ---------------------------------------------------------------------------
# Startup: collect probe evidence per candidate backend, measure the validated
# candidates, then ask the Python policy for the decision. Candidate order
# follows cuda -> vulkan -> cpu. Cheap host hints only SKIP an expensive
# probe; they never select a backend.
# ---------------------------------------------------------------------------
targets=""
if [ "$requested" = auto ]; then
  targets="cuda vulkan cpu"
else
  # An explicit selection is validated against itself only, so a failed
  # explicit backend falls back to CPU rather than to another GPU.
  targets="$requested cpu"
fi

skip_cuda=0
skip_vulkan=0
if ! command -v nvidia-smi >/dev/null 2>&1 && [ ! -e /proc/driver/nvidia ]; then
  skip_cuda=1
fi
if [ ! -d /dev/dri ]; then
  skip_vulkan=1
fi

out_cuda=""
out_vulkan=""
out_cpu=""
fallback_rejected=""
probed_cuda=0
probed_vulkan=0
for backend in $targets; do
  skip=0
  note=""
  if [ "$requested" != "$backend" ]; then
    if [ "$backend" = cuda ] && [ "$skip_cuda" = 1 ]; then
      skip=1
      note="(probe skipped: no NVIDIA evidence on the host (no nvidia-smi, no /proc/driver/nvidia))"
    fi
    if [ "$backend" = vulkan ] && [ "$skip_vulkan" = 1 ]; then
      skip=1
      note="(probe skipped: /dev/dri is absent on the host)"
    fi
  fi
  if [ "$skip" = 1 ]; then
    add_candidate "$backend" false -1 "$note"
    if [ -n "$fallback_rejected" ]; then
      fallback_rejected="$fallback_rejected; $backend (probe skipped)"
    else
      fallback_rejected="$backend (probe skipped)"
    fi
    continue
  fi
  probe_backend "$backend"
  add_candidate "$backend" "$([ "$probe_rc" = 0 ] && echo true || echo false)" "$probe_rc" "$probe_output"
  if [ "$probe_rc" != 0 ]; then
    if [ -n "$fallback_rejected" ]; then
      fallback_rejected="$fallback_rejected; $backend (probe failed)"
    else
      fallback_rejected="$backend (probe failed)"
    fi
  else
    case "$backend" in
      cuda) probed_cuda=1 ;;
      vulkan) probed_vulkan=1 ;;
    esac
  fi
  case "$backend" in
    cuda) out_cuda="$probe_output" ;;
    vulkan) out_vulkan="$probe_output" ;;
    cpu) out_cpu="$probe_output" ;;
  esac
done

# Measure the validated candidates. The measurement is what decides whether a
# GPU profile is worth selecting: a GPU that works but is slower is an
# optimisation that costs time. An explicit backend selection is the
# operator's decision and is not second-guessed by a benchmark.
if [ "$requested" = auto ]; then
  if [ "$probed_cuda" = 1 ]; then
    median=$(benchmark_backend cuda || true)
    [ -n "$median" ] && add_measurement cuda "$median"
  fi
  if [ "$probed_vulkan" = 1 ]; then
    median=$(benchmark_backend vulkan || true)
    [ -n "$median" ] && add_measurement vulkan "$median"
  fi
  median=$(benchmark_backend cpu || true)
  [ -n "$median" ] && add_measurement cpu "$median"
fi

evidence="{\"platform\": \"linux\", \"candidates\": [$candidates]"
[ -n "$measurements" ] && evidence="$evidence, \"measurements\": {$measurements}"
evidence="$evidence}"

b64=$(printf '%s' "$evidence" | b64_encode) || exit 2

plan_rc=0
plan=$(docker compose --env-file deployment.env -f compose.yaml \
  run --rm --no-deps -T production \
  inference plan --evidence-b64 "$b64") || plan_rc=$?

# Extract the decision JSON object from the container output. Compose may add
# its own lines around it, so the object is delimited rather than assumed to
# be the whole output. The CLI prints the object at column 0 and indents
# every nested brace, so the outer braces delimit the object exactly.
plan_json=$(printf '%s\n' "$plan" | sed -n '/^{/,/^}/p')

decision_backend=""
decision_device=""
decision_fit=""
if [ "$plan_rc" = 0 ] && printf '%s\n' "$plan_json" \
     | grep -Eq '^[[:space:]]*"ok":[[:space:]]*true,?[[:space:]]*$'; then
  decision_backend=$(printf '%s\n' "$plan_json" \
    | sed -n 's/^[[:space:]]*"backend":[[:space:]]*"\([^"]*\)".*$/\1/p' | head -1) || true
  decision_device=$(printf '%s\n' "$plan_json" \
    | sed -n 's/^[[:space:]]*"device":[[:space:]]*"\([^"]*\)".*$/\1/p' | head -1) || true
  decision_fit=$(printf '%s\n' "$plan_json" \
    | sed -n 's/^[[:space:]]*"fit_target_mib":[[:space:]]*\([0-9][0-9]*\).*$/\1/p' | head -1) || true
fi
case "$decision_backend" in
  cpu|vulkan|cuda) ;;
  *)
    echo 'Warning: the inference plan was unavailable or invalid; falling back to the validated CPU profile.' >&2
    decision_backend=cpu
    decision_device=""
    decision_fit=192
    ;;
esac

# An explicit PI_GPU_DEVICE is honoured only when the runtime actually
# reported that device for the selected backend; otherwise it is ignored
# with a warning (the decision is never overridden blindly).
if [ -n "$pinned_device" ] && [ "$decision_backend" != cpu ]; then
  selected_output=""
  case "$decision_backend" in
    cuda) selected_output="$out_cuda" ;;
    vulkan) selected_output="$out_vulkan" ;;
  esac
  if printf '%s\n' "$selected_output" | grep -q "^[[:space:]]*${pinned_device}:"; then
    decision_device="$pinned_device"
  else
    echo "Warning: PI_GPU_DEVICE=$pinned_device was not reported by the $decision_backend runtime; using the detected device '${decision_device:-default}' instead." >&2
  fi
fi

# The rejected candidates are reported as one pre-rendered line so the
# launcher never has to parse the nested JSON array.
rejected_text=$(printf '%s\n' "$plan_json" \
  | sed -n 's/^[[:space:]]*"rejected_text":[[:space:]]*"\(.*\)",\{0,1\}$/\1/p' | head -1) || true
if [ -z "$rejected_text" ]; then
  rejected_text="$fallback_rejected"
fi

if [ "$decision_backend" = cpu ]; then
  decision_device=""
  decision_fit="${decision_fit:-192}"
  echo "Selected inference backend: cpu (CPU profile, fit target ${decision_fit} MiB)"
else
  echo "Selected inference backend: $decision_backend (device ${decision_device:-default}, fit target ${decision_fit:-192} MiB)"
fi
if [ -n "$measurements" ]; then
  echo "Measured median latency: $measurements"
fi
if [ -n "$rejected_text" ]; then
  echo "Rejected inference candidates: $rejected_text"
else
  echo "Rejected inference candidates: none"
fi
if [ "$requested" != auto ] && [ "$requested" != "$decision_backend" ]; then
  echo "Warning: explicit PI_ACCELERATOR=$requested failed to validate; falling back to the validated CPU profile." >&2
fi

apply_decision "$decision_backend" "${decision_device:-none}" "${decision_fit:-192}"
files+=(-f "compose.$decision_backend.yaml")
exec docker compose --env-file deployment.env "${files[@]}" "$@"
