"""Tests for the portable inference runtime policy.

The policy is the single owner of the backend decision. It must be
hardware independent so it can be tested without a GPU, and it must never
turn an unavailable GPU into a startup failure.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from pi_platform.core.inference import (
    BackendCandidate,
    build_server_argv,
    compose_device_fragment,
    parse_device_list,
    select_profile,
)


CUDA_OUTPUT = (
    "Available devices:\n"
    "  CUDA0: NVIDIA GeForce RTX 4090, CUDA driver version 12.4, "
    "compute capability 8.9, VMM: yes\n"
)
VULKAN_OUTPUT = (
    "Available devices:\n"
    "  Vulkan0: AMD Radeon RX 7900 (RADV NAVI31), device type: DISCRETE_GPU, "
    "driver version 1.3.280, free memory: 16384 MiB\n"
    "  Vulkan1: Intel(R) UHD Graphics (ADL-P GT2), device type: INTEGRATED_GPU\n"
)
LAVAPIPE_OUTPUT = (
    "Available devices:\n"
    "  Vulkan0: llvmpipe (LLVM 15.0.7, 256 bits), device type: CPU, "
    "driver version 1.3.280\n"
)
INTEGRATED_ONLY_OUTPUT = (
    "Available devices:\n"
    "  Vulkan0: Intel(R) UHD Graphics (ADL-P GT2), device type: INTEGRATED_GPU\n"
)
NO_DEVICES_OUTPUT = "Available devices:\n  (none)\n"


def candidate(backend, output, ok=True, exit_code=0):
    return BackendCandidate(
        backend=backend, ok=ok, exit_code=exit_code, output=output
    )


class DeviceListParsingTests(unittest.TestCase):
    def test_cuda_device_is_parsed(self):
        devices = parse_device_list(CUDA_OUTPUT)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "CUDA0")
        self.assertEqual(devices[0].backend, "cuda")
        self.assertFalse(devices[0].is_software)
        self.assertFalse(devices[0].is_integrated)

    def test_vulkan_devices_report_type_and_free_memory(self):
        devices = parse_device_list(VULKAN_OUTPUT)
        self.assertEqual([d.name for d in devices], ["Vulkan0", "Vulkan1"])
        self.assertEqual(devices[0].backend, "vulkan")
        self.assertFalse(devices[0].is_integrated)
        self.assertEqual(devices[0].memory_bytes, 16384 * 1024 * 1024)
        self.assertTrue(devices[1].is_integrated)

    def test_the_measured_device_line_format_is_parsed(self):
        """llama.cpp reports a Vulkan device as
        ``AMD Radeon Graphics (RADV RENOIR) (32334 MiB, 30768 MiB free)``.
        The FREE figure must be used, never the total."""

        output = (
            "Available devices:\n"
            "  Vulkan0: AMD Radeon Graphics (RADV RENOIR) "
            "(32334 MiB, 30768 MiB free)\n"
        )
        devices = parse_device_list(output)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "Vulkan0")
        self.assertFalse(devices[0].is_software)
        self.assertEqual(devices[0].memory_bytes, 30768 * 1024 * 1024)

    def test_the_total_memory_is_never_used_as_the_free_memory(self):
        """A bare ``<N> MiB`` fragment is the total, not the free figure."""

        output = "Available devices:\n  Vulkan0: some device (8192 MiB)\n"
        devices = parse_device_list(output)
        self.assertIsNone(devices[0].memory_bytes)

    def test_no_devices_yields_an_empty_list(self):
        self.assertEqual(parse_device_list(NO_DEVICES_OUTPUT), [])

    def test_software_rasteriser_is_marked(self):
        devices = parse_device_list(LAVAPIPE_OUTPUT)
        self.assertEqual(len(devices), 1)
        self.assertTrue(devices[0].is_software)

    def test_unparseable_output_never_raises(self):
        self.assertEqual(parse_device_list(""), [])
        self.assertEqual(parse_device_list("garbage\nmore garbage\n"), [])


class SelectionPolicyTests(unittest.TestCase):
    def test_cuda_is_preferred_over_vulkan_and_cpu(self):
        profile = select_profile([
            candidate("cuda", CUDA_OUTPUT),
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        self.assertEqual(profile.backend, "cuda")
        self.assertEqual(profile.device, "CUDA0")
        self.assertIn("CUDA0", profile.reason)

    def test_vulkan_is_used_when_cuda_reports_no_device(self):
        profile = select_profile([
            candidate("cuda", NO_DEVICES_OUTPUT),
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        self.assertEqual(profile.backend, "vulkan")
        self.assertEqual(profile.device, "Vulkan0")
        rejected = {item["backend"]: item["reason"] for item in profile.rejected}
        self.assertEqual(rejected["cuda"], "no device reported")

    def test_software_only_device_is_rejected(self):
        profile = select_profile([
            candidate("vulkan", LAVAPIPE_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        self.assertEqual(profile.backend, "cpu")
        rejected = {item["backend"]: item["reason"] for item in profile.rejected}
        self.assertEqual(rejected["vulkan"], "software device only")

    def test_failed_probe_is_rejected(self):
        profile = select_profile([
            candidate("cuda", "", ok=False, exit_code=1),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        self.assertEqual(profile.backend, "cpu")
        rejected = {item["backend"]: item["reason"] for item in profile.rejected}
        self.assertEqual(rejected["cuda"], "probe failed")

    def test_cpu_is_the_final_fallback_and_never_fails(self):
        profile = select_profile([
            candidate("cuda", "", ok=False, exit_code=1),
            candidate("vulkan", "", ok=False, exit_code=1),
        ])
        self.assertEqual(profile.backend, "cpu")
        self.assertIsNone(profile.device)
        self.assertEqual(len(profile.rejected), 2)

    def test_integrated_device_can_be_disallowed(self):
        profile = select_profile(
            [candidate("vulkan", VULKAN_OUTPUT), candidate("cpu", NO_DEVICES_OUTPUT)],
            allow_integrated=False,
        )
        # Vulkan0 is discrete and stays usable; the integrated device is not
        # the selected one.
        self.assertEqual(profile.backend, "vulkan")
        self.assertEqual(profile.device, "Vulkan0")

        only_integrated = select_profile(
            [candidate("vulkan", INTEGRATED_ONLY_OUTPUT),
             candidate("cpu", NO_DEVICES_OUTPUT)],
            allow_integrated=False,
        )
        self.assertEqual(only_integrated.backend, "cpu")
        rejected = {item["backend"]: item["reason"] for item in only_integrated.rejected}
        self.assertEqual(rejected["vulkan"], "integrated device not allowed")

    def test_fit_target_is_derived_from_the_reported_free_memory(self):
        profile = select_profile([
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        # 16384 MiB free * 0.35 = 5734 -> clamped to the 512 MiB ceiling.
        self.assertEqual(profile.fit_target_mib, 512)

        small = select_profile([
            candidate("vulkan", VULKAN_OUTPUT.replace("free memory: 16384 MiB", "free memory: 400 MiB")),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        # 400 * 0.35 = 140 -> clamped up to the 192 MiB floor.
        self.assertEqual(small.fit_target_mib, 192)

    def test_unknown_memory_uses_the_conservative_default(self):
        profile = select_profile([
            candidate("cuda", CUDA_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        self.assertEqual(profile.fit_target_mib, 192)


class LaunchPlanTests(unittest.TestCase):
    def build(self, **kwargs):
        params = dict(
            model_path="/models/embeddinggemma-2-Q8_0.gguf",
            projector_path="/models/mmproj-embeddinggemma-2-Q8_0.gguf",
            alias="test-alias",
        )
        params.update(kwargs)
        return build_server_argv(**params)

    def test_cpu_profile_disables_gpu_devices(self):
        argv = self.build(backend="cpu")
        self.assertIn("--device", argv)
        self.assertEqual(argv[argv.index("--device") + 1], "none")
        self.assertNotIn("--fit", argv)

    def test_gpu_profile_selects_the_device_and_the_fit_budget(self):
        argv = self.build(backend="vulkan", device="Vulkan1", fit_target_mib=256)
        self.assertEqual(argv[argv.index("--device") + 1], "Vulkan1")
        self.assertEqual(argv[argv.index("--fit") + 1], "on")
        self.assertEqual(argv[argv.index("--fit-target") + 1], "256")

    def test_projector_stays_on_the_cpu_exactly_once(self):
        for backend, device in (("cpu", None), ("cuda", "CUDA0"), ("vulkan", "Vulkan0")):
            argv = self.build(backend=backend, device=device)
            self.assertEqual(argv.count("--no-mmproj-offload"), 1, backend)

    def test_the_argument_vector_is_explicit_and_ordered(self):
        argv = self.build(backend="cpu")
        for flag in ("--embeddings", "--model", "--mmproj", "--alias",
                     "--pooling", "--embd-normalize", "--ctx-size",
                     "--batch-size", "--ubatch-size", "--parallel",
                     "--host", "--port", "--api-key-file"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--pooling") + 1], "mean")
        self.assertEqual(argv[argv.index("--embd-normalize") + 1], "2")
        # The flags are explicit; no environment variable names leak in.
        self.assertFalse([item for item in argv if item.startswith("LLAMA_ARG_")])

    def test_compose_fragment_uses_none_for_the_cpu_backend(self):
        profile = select_profile([candidate("cpu", NO_DEVICES_OUTPUT)])
        fragment = compose_device_fragment(profile)
        self.assertEqual(fragment["PI_ACCELERATOR"], "cpu")
        self.assertEqual(fragment["PI_GPU_DEVICE"], "none")
        self.assertEqual(fragment["PI_FIT_TARGET"], "192")

        gpu = select_profile([candidate("cuda", CUDA_OUTPUT), candidate("cpu", NO_DEVICES_OUTPUT)])
        fragment = compose_device_fragment(gpu)
        self.assertEqual(fragment["PI_ACCELERATOR"], "cuda")
        self.assertEqual(fragment["PI_GPU_DEVICE"], "CUDA0")


class ThroughputGateTests(unittest.TestCase):
    """A GPU that works but is slower must not be selected."""

    def test_a_slower_gpu_is_rejected_in_favour_of_the_cpu(self):
        profile = select_profile([
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ], measurements={"cpu": 22.19, "vulkan": 30.77})
        self.assertEqual(profile.backend, "cpu")
        rejected = {item["backend"]: item["reason"] for item in profile.rejected}
        self.assertIn("not faster", rejected["vulkan"])
        self.assertIn("0.72", rejected["vulkan"])

    def test_a_faster_gpu_is_selected(self):
        profile = select_profile([
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ], measurements={"cpu": 30.0, "vulkan": 20.0})
        self.assertEqual(profile.backend, "vulkan")
        self.assertEqual(profile.rejected, ())

    def test_the_threshold_is_configurable(self):
        profile = select_profile([
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ], measurements={"cpu": 22.19, "vulkan": 30.77}, min_gpu_speedup=0.5)
        self.assertEqual(profile.backend, "vulkan")

    def test_an_unmeasured_gpu_is_still_eligible(self):
        """Without a measurement the device evidence decides."""

        profile = select_profile([
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ])
        self.assertEqual(profile.backend, "vulkan")

    def test_a_measurement_without_a_cpu_baseline_is_not_used(self):
        profile = select_profile([
            candidate("vulkan", VULKAN_OUTPUT),
            candidate("cpu", NO_DEVICES_OUTPUT),
        ], measurements={"vulkan": 30.77})
        self.assertEqual(profile.backend, "vulkan")


class InferenceCliTests(unittest.TestCase):
    """The launchers parse the CLI output directly, so it must be stable."""

    def run_plan(self, evidence):
        import base64
        payload = base64.b64encode(json.dumps(evidence).encode()).decode()
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        return subprocess.run(
            [sys.executable, "-m", "pi_platform.cli", "inference", "plan",
             "--evidence-b64", payload],
            capture_output=True, text=True, env=env,
        )

    def test_plan_prints_exactly_one_json_object(self):
        result = self.run_plan({
            "platform": "linux",
            "candidates": [
                {"backend": "cuda", "ok": True, "exit_code": 0, "output": CUDA_OUTPUT},
                {"backend": "cpu", "ok": True, "exit_code": 0, "output": NO_DEVICES_OUTPUT},
            ],
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["backend"], "cuda")
        self.assertEqual(payload["device"], "CUDA0")
        self.assertIn("server_args", payload)
        self.assertIn("compose", payload)
        self.assertEqual(payload["compose"]["PI_GPU_DEVICE"], "CUDA0")

    def test_plan_reports_invalid_evidence_as_one_json_object(self):
        result = self.run_plan({"platform": "linux", "candidates": "not-a-list"})
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)

    def test_plan_applies_the_measured_throughput_gate(self):
        result = self.run_plan({
            "platform": "linux",
            "candidates": [
                {"backend": "vulkan", "ok": True, "exit_code": 0, "output": VULKAN_OUTPUT},
                {"backend": "cpu", "ok": True, "exit_code": 0, "output": NO_DEVICES_OUTPUT},
            ],
            "measurements": {"cpu": 22.19, "vulkan": 30.77},
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["backend"], "cpu")
        self.assertIn("not faster", payload["rejected_text"])

    def test_plan_reports_the_rejected_candidates_as_one_line(self):
        result = self.run_plan({
            "platform": "linux",
            "candidates": [
                {"backend": "cuda", "ok": False, "exit_code": 1, "output": ""},
                {"backend": "cpu", "ok": True, "exit_code": 0, "output": NO_DEVICES_OUTPUT},
            ],
        })
        payload = json.loads(result.stdout)
        self.assertIn("cuda (probe failed)", payload["rejected_text"])

    def test_plan_falls_back_to_cpu_when_every_probe_failed(self):
        result = self.run_plan({
            "platform": "linux",
            "candidates": [
                {"backend": "cuda", "ok": False, "exit_code": 1, "output": ""},
            ],
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["backend"], "cpu")
        self.assertIsNone(payload["device"])


if __name__ == "__main__":
    unittest.main()
