import { tool } from "@opencode-ai/plugin"
import { readFile } from "node:fs/promises"
import path from "node:path"

const TERMINAL_STATES = new Set(["completed", "failed", "cancelled", "waiting_for_approval"])

function rootFromContext(context) {
  return context.worktree || context.directory || process.cwd()
}

async function loadRuntime(context) {
  const root = rootFromContext(context)
  const runtimePath = path.join(root, ".generated", "opencode-hermes-runtime.json")
  const keyPath = path.join(root, ".generated", "hermes-api-key")

  let runtime
  try {
    runtime = JSON.parse(await readFile(runtimePath, "utf8"))
  } catch (error) {
    throw new Error(`Hermes runtime config is missing or invalid. Run 'make client-config'. (${error?.message || error})`)
  }

  let apiKey = ""
  try {
    apiKey = (await readFile(keyPath, "utf8")).trim()
  } catch (error) {
    throw new Error(`Hermes API key file is missing. Run 'make client-config'. (${error?.message || error})`)
  }

  if (!runtime.apiBase || !runtime.projectRoot || !apiKey) {
    throw new Error("Hermes runtime config is incomplete. Run 'make check && make client-config'.")
  }
  return { ...runtime, apiKey }
}

function safeErrorBody(body) {
  if (!body) return ""
  if (typeof body === "string") return body.slice(0, 500)
  const msg = body.message || body.detail || body.error?.message || body.error || body.status
  return typeof msg === "string" ? msg.slice(0, 500) : ""
}

async function request(context, method, suffix, payload, deadlineMs) {
  const runtime = await loadRuntime(context)
  const init = {
    method,
    headers: {
      Authorization: `Bearer ${runtime.apiKey}`,
      Accept: "application/json",
    },
  }
  if (payload !== undefined) {
    init.headers["Content-Type"] = "application/json"
    init.body = JSON.stringify(payload)
  }
  const requestDeadline = Math.min(
    deadlineMs ?? Number.POSITIVE_INFINITY,
    Date.now() + 30_000,
  )
  const remaining = requestDeadline - Date.now()
  if (remaining <= 0) throw new Error("Hermes API request deadline exceeded")
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), remaining)
  init.signal = controller.signal
  let response
  let text
  try {
    response = await fetch(`${runtime.apiBase}${suffix}`, init)
    text = await response.text()
  } catch (error) {
    if (controller.signal.aborted) throw new Error("Hermes API request deadline exceeded")
    throw error
  } finally {
    clearTimeout(timer)
  }
  let body = {}
  if (text) {
    try { body = JSON.parse(text) } catch { body = { raw: text.slice(0, 2000) } }
  }
  if (!response.ok) {
    const detail = safeErrorBody(body)
    throw new Error(`Hermes API ${response.status}${detail ? `: ${detail}` : ""}`)
  }
  return { runtime, body }
}

function instructions(projectRoot) {
  return [
    `Authorized project root: ${projectRoot}`,
    `Establish repository context at ${projectRoot} before repository operations and stay within it.`,
    "Use your own native SSH-backed terminal/file/search/vision tools; do not ask OpenCode to proxy ordinary repository files.",
    "Respect AGENTS.md and project-local instructions.",
    "Do not launch Claude Code, OpenCode, Codex, or another coding orchestrator recursively.",
    "Return a concise result with evidence and verification performed.",
  ].join("\n")
}

function compactRun(run) {
  return {
    run_id: run.run_id,
    session_id: run.session_id,
    status: run.status,
    output: run.output,
    error: run.error,
    usage: run.usage,
    last_event: run.last_event,
    approval_events: run.approval_events,
    pending_approvals: run.pending_approvals,
  }
}

async function requireApprovalResolver(context) {
  const { body } = await request(context, "GET", "/v1/capabilities")
  const capabilities = body.features || body.capabilities || body
  if (
    capabilities.run_approval_response !== true ||
    capabilities.resolver_scoped_run_approvals !== true
  ) {
    throw new Error(
      "Hermes worker lacks resolver-backed /v1/runs approvals. Upgrade/apply the harness compatibility patch; unattended auto-approval is not permitted.",
    )
  }
}

function asText(value) {
  return JSON.stringify(value, null, 2)
}

async function poll(context, runId, timeoutSeconds = 120, pollSeconds = 2) {
  const timeout = Math.max(1, Math.min(Number(timeoutSeconds) || 120, 900))
  const interval = Math.max(0.5, Math.min(Number(pollSeconds) || 2, 10))
  const deadline = Date.now() + timeout * 1000
  let last = { run_id: runId, status: "unknown" }

  while (Date.now() < deadline) {
    const { body } = await request(
      context,
      "GET",
      `/v1/runs/${encodeURIComponent(runId)}`,
      undefined,
      deadline,
    )
    last = body
    const status = String(body.status || "").toLowerCase()
    if (TERMINAL_STATES.has(status)) return { ...compactRun(body), wait_timeout: false }
    const sleepMs = Math.min(interval * 1000, Math.max(0, deadline - Date.now()))
    if (sleepMs > 0) await new Promise((resolve) => setTimeout(resolve, sleepMs))
  }
  return { ...compactRun(last), wait_timeout: true }
}

export const delegate = tool({
  description: "Delegate a bounded autonomous repository task to the remote native Hermes Agent. Use for independent repository analysis, implementation, testing, research, review, or another workstream that benefits from Hermes' own SSH-backed tools. This calls Hermes /v1/runs directly; do not use an OpenCode subagent/model-provider to represent Hermes.",
  args: {
    task: tool.schema.string().describe("Complete bounded task for Hermes, including expected result and verification criteria."),
    session_id: tool.schema.string().optional().describe("Existing Hermes session id only when intentionally continuing a previous Hermes session. Omit for a fresh session."),
    wait_seconds: tool.schema.number().optional().describe("How long to wait for a result before returning control. Default 120, max 900."),
  },
  async execute(args, context) {
    const task = String(args.task || "").trim()
    if (!task) throw new Error("task is required")
    await requireApprovalResolver(context)
    const runtime = await loadRuntime(context)
    const payload = {
      input: task,
      instructions: instructions(runtime.projectRoot),
    }
    if (args.session_id?.trim()) payload.session_id = args.session_id.trim()

    // Do not send a model override: /v1/runs honors it as a real provider/model
    // override. The remote Hermes profile remains the source of truth.
    const { body: started } = await request(context, "POST", "/v1/runs", payload)
    if (!started.run_id) return asText(started)

    const final = await poll(context, started.run_id, args.wait_seconds ?? 120, 2)
    if (final.status === "waiting_for_approval") {
      final.notice = "Hermes emitted an approval pause. Show approval details to the user/parent, then resolve this exact run with hermes_approve."
    } else if (final.wait_timeout) {
      final.notice = "Hermes is still running. Use hermes_wait or hermes_status with this run_id instead of starting a duplicate run."
    }
    return asText(final)
  },
})

export const status = tool({
  description: "Get the current status of an existing Hermes run without starting another run.",
  args: { run_id: tool.schema.string().describe("Hermes run id returned by hermes_delegate.") },
  async execute(args, context) {
    const { body } = await request(context, "GET", `/v1/runs/${encodeURIComponent(args.run_id)}`)
    return asText(compactRun(body))
  },
})

export const wait = tool({
  description: "Wait for an existing Hermes run to complete, fail, cancel, pause for approval, or reach the local wait timeout.",
  args: {
    run_id: tool.schema.string().describe("Hermes run id returned by hermes_delegate."),
    timeout_seconds: tool.schema.number().optional().describe("Local wait timeout. Default 120, max 900."),
    poll_seconds: tool.schema.number().optional().describe("Polling interval. Default 2 seconds."),
  },
  async execute(args, context) {
    const result = await poll(context, args.run_id, args.timeout_seconds ?? 120, args.poll_seconds ?? 2)
    if (result.status === "waiting_for_approval") {
      result.notice = "Hermes emitted an approval pause. Show approval details to the user/parent, then resolve this exact run with hermes_approve."
    }
    return asText(result)
  },
})

export const result = tool({
  description: "Fetch the current Hermes run object, including final output when available.",
  args: { run_id: tool.schema.string().describe("Hermes run id returned by hermes_delegate.") },
  async execute(args, context) {
    const { body } = await request(context, "GET", `/v1/runs/${encodeURIComponent(args.run_id)}`)
    return asText(compactRun(body))
  },
})

export const steer = tool({
  description: "Inject additional guidance into an already-running Hermes run at the next safe tool boundary.",
  args: {
    run_id: tool.schema.string().describe("Hermes run id."),
    text: tool.schema.string().describe("Additional guidance for the active Hermes run."),
  },
  async execute(args, context) {
    const text = String(args.text || "").trim()
    if (!text) throw new Error("text is required")
    const { body } = await request(context, "POST", `/v1/runs/${encodeURIComponent(args.run_id)}/steer`, { input: text })
    return asText(body)
  },
})

export const approve = tool({
  description: "Resolve a Hermes approval pause. Call only after explicit user authorization. Choices: once, session, always, deny.",
  args: {
    run_id: tool.schema.string().describe("Hermes run id waiting for approval."),
    choice: tool.schema.string().describe("Approval choice: once, session, always, or deny."),
    resolve_all: tool.schema.boolean().optional().describe("Resolve all currently pending approvals with this choice. Default false."),
  },
  async execute(args, context) {
    const choice = String(args.choice || "").trim().toLowerCase()
    if (!["once", "session", "always", "deny"].includes(choice)) {
      throw new Error("choice must be one of: once, session, always, deny")
    }
    const { body } = await request(context, "POST", `/v1/runs/${encodeURIComponent(args.run_id)}/approval`, {
      choice,
      resolve_all: Boolean(args.resolve_all),
    })
    return asText(body)
  },
})

export const cancel = tool({
  description: "Request cooperative cancellation of an existing Hermes run.",
  args: { run_id: tool.schema.string().describe("Hermes run id to cancel.") },
  async execute(args, context) {
    const { body } = await request(context, "POST", `/v1/runs/${encodeURIComponent(args.run_id)}/stop`, {})
    return asText(body)
  },
})
