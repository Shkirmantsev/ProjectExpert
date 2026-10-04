from __future__ import annotations

import os
from pathlib import Path

import yaml


def enabled(env: dict[str, str], name: str) -> bool:
    return env.get(name, "false").lower() in {"1", "true", "yes", "on"}


def build_config(env: dict[str, str]) -> dict:
    models: list[dict] = []
    local_params: dict[str, dict] = {}
    emitted_names: set[str] = set()

    def add_model(name: str, params: dict) -> None:
        if not name or name in emitted_names:
            return
        models.append({"model_name": name, "litellm_params": params.copy()})
        emitted_names.add(name)

    for i in range(1, 5):
        if not enabled(env, f"LOCAL_MODEL_{i}_ENABLED"):
            continue
        alias = env[f"LOCAL_MODEL_{i}_ALIAS"]
        claude_alias = env[f"LOCAL_MODEL_{i}_CLAUDE_ALIAS"]
        params = {
            "model": "openai/" + env[f"LOCAL_MODEL_{i}_MODEL_ID"],
            "api_base": env["LM_STUDIO_OPENAI_BASE_URL"],
            "api_key": env["LM_STUDIO_API_KEY"],
            "timeout": 3600,
        }
        local_params[alias] = params
        local_params[claude_alias] = params
        add_model(alias, params)
        add_model(claude_alias, params)

    # Claude Code's native /model picker sends Anthropic model IDs rather than
    # custom LOCAL_MODEL_N_CLAUDE_ALIAS values. Duplicate the selected local
    # upstream under those native names so its normal picker works locally.
    for role in ("OPUS", "SONNET", "HAIKU"):
        native_names = env.get(f"CLAUDE_{role}_MODEL_NAME", "").split(",")
        target_alias = env.get(f"CLAUDE_{role}_LOCAL_ALIAS", "").strip()
        if target_alias in local_params:
            for native_name in native_names:
                add_model(native_name.strip(), local_params[target_alias])

    if enabled(env, "MINIMAX_ENABLED"):
        params = {
            # M3's thinking is disabled by default. Its native Anthropic
            # endpoint supports ``thinking: {type: adaptive}`` and preserves
            # thinking blocks for Claude Code, unlike the OpenAI translation.
            "model": "anthropic/" + env["MINIMAX_MODEL_ID"],
            "api_base": env.get(
                "MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic"
            ),
            "api_key": env["MINIMAX_TOKEN_PLAN_KEY"],
            # Keep the provider-level default alongside the request hook:
            # LiteLLM's Anthropic /v1/messages adapter can bypass request
            # extra_body fields during protocol translation.
            "thinking": {"type": "adaptive"},
            "timeout": 3600,
        }
        # Claude Code's picker may send the provider's canonical model ID
        # (for example, ``MiniMax-M3``), whereas generated agents use the
        # harness alias.  All of these names must resolve to the same
        # configured upstream; otherwise an Anthropic-protocol request is
        # rejected before it reaches the OpenAI-compatible MiniMax endpoint.
        add_model(env["MINIMAX_ALIAS"], params)
        add_model(env["MINIMAX_CLAUDE_ALIAS"], params)
        add_model(env["MINIMAX_MODEL_ID"], params)
        add_model("minimax", params)
        add_model("claude-minimax", params)


    return {
        "model_list": models,
        "litellm_settings": {
            "callbacks": ["reasoning_policy.reasoning_policy"],
            "drop_params": True,
            "modify_params": True,
        },
        "general_settings": {
            "master_key": "os.environ/LITELLM_MASTER_KEY",
            "disable_spend_logs": True,
        },
    }


def main() -> None:
    config = build_config(dict(os.environ))
    output = Path(os.getenv("LITELLM_CONFIG_PATH", "/tmp/harness-litellm.yaml"))
    output.write_text(yaml.safe_dump(config, sort_keys=False))
    print("LiteLLM aliases:", ", ".join(model["model_name"] for model in config["model_list"]))


if __name__ == "__main__":
    main()
