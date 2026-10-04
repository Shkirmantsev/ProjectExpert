from __future__ import annotations
import litellm
from litellm.integrations.custom_logger import CustomLogger
from policy_core import apply_reasoning_policy


# MiniMax documents native Anthropic adaptive thinking for M3, but LiteLLM's
# bundled cost map has no MiniMax-M3 capability entry.  Without this metadata,
# LiteLLM converts adaptive thinking to legacy budgeted thinking and can drop it
# when max_tokens is small. Register the documented capability before requests
# are routed so the native parameter and thinking blocks are preserved.
for _model in ("MiniMax-M3", "anthropic/MiniMax-M3"):
    litellm.model_cost.setdefault(_model, {})["supports_adaptive_thinking"] = True

class HarnessReasoningPolicy(CustomLogger):
    """LiteLLM pre-call hook. Policy mechanics live in policy_core.py for testability."""
    async def async_pre_call_hook(self,user_api_key_dict,cache,data,call_type):
        return apply_reasoning_policy(data)

reasoning_policy=HarnessReasoningPolicy()
