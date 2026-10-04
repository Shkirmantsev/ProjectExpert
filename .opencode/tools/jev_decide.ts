import { tool } from "@opencode-ai/plugin/tool"
import { readFile } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"

const OPENROUTER_AUTH_PATH = join(
  process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"),
  "opencode", "auth.json",
)
const OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
const JEV_MODEL = "typesafe/jev-1.13"
const MAX_TEXT = 80
const MAX_RISK_FLAGS = 8

type AuthShape = {
  openrouter?: { type?: string; key?: string }
}

type SanitizedEnvelope = {
  task_kind: string
  scope: string
  change_size: string
  risk_flags: string[]
  ambiguity: string
  failed_attempts: number
  needs_terminal: boolean
  needs_multimodal: boolean
  long_context: boolean
}

async function readOpenRouterApiKey(): Promise<string | null> {
  try {
    const raw = await readFile(OPENROUTER_AUTH_PATH, "utf8")
    const parsed = JSON.parse(raw) as AuthShape
    const key = parsed?.openrouter?.key
    return parsed?.openrouter?.type === "api" && typeof key === "string" && key.length > 0 ? key : null
  } catch {
    return null
  }
}

function sanitize(input: Record<string, unknown>): SanitizedEnvelope {
  const riskFlagsRaw = Array.isArray(input.risk_flags) ? input.risk_flags : []
  return {
    task_kind: String(input.task_kind ?? "").slice(0, MAX_TEXT),
    scope: String(input.scope ?? "unknown"),
    change_size: String(input.change_size ?? "none"),
    risk_flags: riskFlagsRaw
      .slice(0, MAX_RISK_FLAGS)
      .map((value) => String(value).slice(0, MAX_TEXT)),
    ambiguity: String(input.ambiguity ?? "medium"),
    failed_attempts: Math.max(0, Math.min(9, Number(input.failed_attempts ?? 0))),
    needs_terminal: Boolean(input.needs_terminal),
    needs_multimodal: Boolean(input.needs_multimodal),
    long_context: Boolean(input.long_context),
  }
}

function fail(message: Record<string, unknown>): string {
  return JSON.stringify(message)
}

export default tool({
  description:
    "Classify a SANITIZED engineering routing envelope with JEV 1.13 over OpenRouter. " +
    "Never pass source code, file contents, secrets, customer/personal data, " +
    "the full user prompt, or conversation history. " +
    "Reads the OpenRouter credential from the OpenCode auth store in memory only.",

  args: {
    task_kind: tool.schema
      .string()
      .describe("Short category only, e.g. explain, bugfix, refactor, feature, architecture, review."),
    scope: tool.schema
      .enum(["single-file", "few-files", "multi-module", "repository-wide", "unknown"])
      .describe("Scope of the change."),
    change_size: tool.schema
      .enum(["none", "small", "medium", "large"])
      .describe("Magnitude of the change."),
    risk_flags: tool.schema
      .array(tool.schema.string().max(MAX_TEXT))
      .max(MAX_RISK_FLAGS)
      .describe("Short labels only: security, concurrency, migration, transaction, protocol, data-loss, etc."),
    ambiguity: tool.schema
      .enum(["low", "medium", "high"])
      .describe("How well-understood the requirement is."),
    failed_attempts: tool.schema
      .number()
      .int()
      .min(0)
      .max(9)
      .describe("Number of failed prior attempts on this task."),
    needs_terminal: tool.schema.boolean().describe("Whether the task needs shell/terminal access."),
    needs_multimodal: tool.schema.boolean().describe("Whether the task needs multimodal reasoning."),
    long_context: tool.schema.boolean().describe("Whether the task requires long-context handling."),
  },

  async execute(args, context) {
    const apiKey = await readOpenRouterApiKey()
    if (!apiKey) {
      return "OpenRouter is not connected. Run /connect and connect OpenRouter."
    }

    const state = sanitize(args as unknown as Record<string, unknown>)

    const request = {
      model: JEV_MODEL,
      state,
      questions: {
        executor: {
          type: "choice",
          instructions:
            "Choose the least expensive executor likely to solve this engineering task correctly.",
          criteria: {
            m3: "Trivial/read-only/low-risk work, repository discovery, simple one-file correction, or work where MiniMax M3 is sufficient.",
            mimo_flash:
              "Ordinary non-trivial implementation, refactoring, Java/Spring reasoning, normal debugging, or semantic document/code work.",
            deepseek:
              "Difficult terminal/tool-heavy debugging, multimodal/agentic work, an alternate solver after a failed lower-tier attempt, or a task where an independent model family is specifically useful.",
            mimo_pro:
              "Architecture, security boundary, concurrency, distributed/data consistency, transaction correctness, migration/data-loss risk, contradictory requirements, material model disagreement, or repeated failed lower-tier attempts.",
          },
        },
        explore_first: {
          type: "noul",
          instructions:
            "Should the MiniMax M3 parent first gather and compress repository/document evidence before invoking the selected worker?",
          criteria: {
            true: "Relevant files/root cause are not localized, scope is multi-module/repository-wide/unknown, or an expensive worker would otherwise spend context on broad discovery.",
            false: "Relevant scope and evidence are already clear and compact.",
          },
        },
        review_after: {
          type: "noul",
          instructions:
            "After implementation, is an independent DeepSeek verification pass justified by risk, ambiguity, scope, or subtle-regression potential?",
          criteria: {
            true: "Substantive C2/C3 change, difficult integration/debugging, high-impact behavior, non-obvious correctness, or meaningful uncertainty.",
            false: "Read-only, cosmetic, obvious low-risk change, or a focused change with straightforward tests.",
          },
        },
      },
    }

    let response: Response
    try {
      response = await fetch(OPENROUTER_DECISIONS_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
        signal: context.abort,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      return fail({
        status: "unavailable",
        reason: message,
        fallback: "Use deterministic C0-C3 routing in MiniMax M3.",
      })
    }

    if (!response.ok) {
      const errorText = (await response.text()).slice(0, 500)
      return fail({
        status: "unavailable",
        http_status: response.status,
        reason: errorText,
        fallback: "Use deterministic C0-C3 routing in MiniMax M3.",
      })
    }

    const data = (await response.json()) as {
      answers?: {
        executor?: { type?: string; choice?: string; confidence?: number; probabilities?: Record<string, number> }
        explore_first?: { type?: string; noul?: number }
        review_after?: { type?: string; noul?: number }
      }
      model?: string
      provider?: string
      usage?: unknown
    }
    const executor = data?.answers?.executor
    const explore = data?.answers?.explore_first
    const review = data?.answers?.review_after

    if (!executor || executor.type !== "choice") {
      return fail({
        status: "invalid-response",
        fallback: "Use deterministic C0-C3 routing in MiniMax M3.",
      })
    }

    return fail({
      status: "ok",
      executor: executor.choice,
      executorConfidence: executor.confidence ?? 0,
      executorProbabilities: executor.probabilities ?? {},
      exploreProbability: explore?.type === "noul" ? explore.noul : null,
      reviewProbability: review?.type === "noul" ? review.noul : null,
      model: data?.model ?? JEV_MODEL,
      provider: data?.provider ?? null,
      usage: data?.usage ?? null,
    })
  },
})
