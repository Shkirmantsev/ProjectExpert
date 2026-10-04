from __future__ import annotations
import os

EFFORTS={"none","minimal","low","medium","high","xhigh","max","ultra"}
GUIDANCE={
 "minimal":"Use a very small amount of internal reasoning and answer directly.",
 "low":"Reason briefly and check the most likely failure mode.",
 "medium":"Reason carefully, verify assumptions, and check important edge cases.",
 "high":"Use substantial internal reasoning; compare alternatives and verify edge cases before answering.",
 "xhigh":"Use very deep internal reasoning, independent cross-checks, and explicit verification before answering.",
 "max":"Use the deepest practical reasoning and verification available before answering.",
 "ultra":"Use the deepest practical reasoning and verification available before answering.",
}

def normalize_effort(data:dict)->str:
    raw=data.get("reasoning_effort") or data.get("reasoningEffort") or os.getenv("DEFAULT_REASONING_EFFORT","medium")
    value=str(raw).lower()
    return value if value in EFFORTS else "medium"

def prepend_system(data:dict,text:str)->None:
    msgs=list(data.get("messages") or [])
    if msgs and isinstance(msgs[0],dict) and msgs[0].get("role")=="system":
        msgs[0]=dict(msgs[0]); msgs[0]["content"]=str(msgs[0].get("content",""))+"\n\n"+text
    else:
        msgs.insert(0,{"role":"system","content":text})
    data["messages"]=msgs

def local_slot(model:str)->int|None:
    for role in ("OPUS", "SONNET", "HAIKU"):
        native_names=os.getenv(f"CLAUDE_{role}_MODEL_NAME","").split(",")
        target_alias=os.getenv(f"CLAUDE_{role}_LOCAL_ALIAS","")
        if not any(name.strip() and name.strip() in model for name in native_names) or not target_alias:
            continue
        for i in range(1,5):
            if target_alias in {
              os.getenv(f"LOCAL_MODEL_{i}_ALIAS",""),
              os.getenv(f"LOCAL_MODEL_{i}_CLAUDE_ALIAS",""),
            }:
                return i
    for i in range(1,5):
        aliases={
          os.getenv(f"LOCAL_MODEL_{i}_ALIAS",""),
          os.getenv(f"LOCAL_MODEL_{i}_CLAUDE_ALIAS",""),
          os.getenv(f"LOCAL_MODEL_{i}_MODEL_ID",""),
        }
        if any(a and a in model for a in aliases): return i
    return None

def is_minimax(model:str)->bool:
    candidates=[
      os.getenv("MINIMAX_ALIAS","minimax"),
      os.getenv("MINIMAX_CLAUDE_ALIAS","claude-minimax"),
      os.getenv("MINIMAX_MODEL_ID","MiniMax-M3"),
      "minimax",
      "claude-minimax",
    ]
    return any(x and x in model for x in candidates)

def clamp_local_output(data:dict, slot:int)->None:
    """Bound local reasoning-model output so interactive clients do not time out."""
    raw_limit=os.getenv(f"LOCAL_MODEL_{slot}_MAX_OUTPUT_TOKENS","4096")
    try:
        limit=max(1,int(raw_limit))
    except ValueError:
        limit=4096
    for key in ("max_tokens","max_completion_tokens"):
        value=data.get(key)
        if isinstance(value,(int,float)):
            data[key]=min(max(1,int(value)),limit)
            return
    data["max_tokens"]=limit

def apply_reasoning_policy(data:dict)->dict:
    model=str(data.get("model",""))
    effort=normalize_effort(data)
    if is_minimax(model):
        extra=dict(data.get("extra_body") or {})
        # MiniMax-M3 defaults thinking to off. Use its native Anthropic
        # parameter rather than OpenAI's reasoning_split translation, so
        # Claude Code receives actual thinking blocks. Override any client
        # attempt to disable thinking for these forced-adaptive aliases.
        extra.pop("thinking", None)
        extra.pop("reasoning_split", None)
        if extra:
            data["extra_body"]=extra
        else:
            data.pop("extra_body", None)
        data["thinking"]={"type":"adaptive"}
        data.pop("reasoning_effort",None)
        data.pop("reasoningEffort",None)
        return data
    slot=local_slot(model)
    if slot:
        clamp_local_output(data,slot)
        mode=os.getenv(f"LOCAL_MODEL_{slot}_REASONING_MODE","system-guidance").lower()
        if mode in {"system-guidance","native+system-guidance"} and effort!="none":
            prepend_system(data,GUIDANCE.get(effort,GUIDANCE["medium"]))
        if mode in {"native","native+system-guidance"}:
            extra=dict(data.get("extra_body") or {})
            ctk=dict(extra.get("chat_template_kwargs") or {})
            ctk["enable_thinking"]=(effort!="none")
            extra["chat_template_kwargs"]=ctk
            data["extra_body"]=extra
        data.pop("reasoning_effort",None)
        data.pop("reasoningEffort",None)
    return data
