/* Project Intelligence UI — vanilla browser JavaScript.
 *
 * Consumes only the ten documented UI API operations (§44.3). No bundler, no
 * module loader, no Node.js at runtime. The access token is optional: when the
 * deployment requires one the operator pastes it once and it is kept in memory.
 */
"use strict";

var API = "/api/v1";
var accessToken = "";

function headers(extra) {
  var result = { "Content-Type": "application/json" };
  if (accessToken) { result.Authorization = "Bearer " + accessToken; }
  if (extra) { Object.keys(extra).forEach(function (k) { result[k] = extra[k]; }); }
  return result;
}

function show(id, value) {
  var node = document.getElementById(id);
  if (node) { node.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2); }
}

function call(method, path, body) {
  var init = { method: method, headers: headers() };
  if (body !== undefined) { init.body = JSON.stringify(body); }
  return fetch(path, init).then(function (response) {
    return response.text().then(function (text) {
      var parsed = text;
      try { parsed = JSON.parse(text); } catch (err) { /* keep raw text */ }
      if (!response.ok) {
        throw new Error("HTTP " + response.status + ": " + JSON.stringify(parsed));
      }
      return parsed;
    });
  });
}

function formatResult(targetId, result) {
  if (targetId === "wiki-result" && result.documents) {
    return result.documents.length ? result.documents.map(function (doc) {
      return doc.path + "\n\n" + doc.text;
    }).join("\n\n────────────────\n\n") : "No matching curated Wiki pages. Ask your MCP agent to create reviewed pages from project evidence.";
  }
  if ((targetId === "query-result" || targetId === "retrieve-result") && result.results) {
    var evidence = result.results.length ? result.results.slice(0, 10).map(function (hit, i) {
      var meta = hit.metadata || {};
      return "[" + (i + 1) + "] " + (meta.sourcePath || meta.documentId || hit.chunkId) +
        (meta.page ? " · page " + meta.page : "") +
        " · score " + hit.score + "\n" + (hit.snippet || "");
    }).join("\n\n") : "No matching evidence. Check indexing status or try a more specific question.";
    var answer = result.answer ? "Answer (generated from retrieved evidence):\n" + result.answer + "\n\nSources:\n" : "";
    var explanation = result.explanations ? "\n\n" + result.explanations.join("\n") : "";
    return answer + evidence + explanation;
  }
  return result;
}

function run(targetId, action) {
  show(targetId, "working…");
  return action().then(function (result) {
    show(targetId, formatResult(targetId, result));
  }).catch(function (error) {
    show(targetId, error.message);
  });
}

function bindForm(formId, buttonId, targetId, buildBody) {
  var form = document.getElementById(formId);
  var button = document.getElementById(buttonId);
  if (!form || !button) { return; }
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    run(targetId, function () { return call("POST", API + form.dataset.endpoint, buildBody()); });
  });
}

function bindButton(buttonId, targetId, action) {
  var button = document.getElementById(buttonId);
  if (!button) { return; }
  button.addEventListener("click", function () { run(targetId, action); });
}

document.addEventListener("DOMContentLoaded", function () {
  var tokenField = document.getElementById("access-token");
  if (tokenField) {
    tokenField.addEventListener("change", function () { accessToken = tokenField.value.trim(); });
  }

  bindButton("sources-button", "sources-result", function () { return call("GET", API + "/sources"); });
  bindButton("version-button", "version-result", function () { return call("GET", API + "/project-version"); });
  bindButton("indexing-button", "indexing-result", function () { return call("GET", API + "/indexing-status"); });
  bindButton("knowledge-button", "knowledge-result", function () { return call("GET", API + "/knowledge-status"); });

  bindButton("retrieve-button", "retrieve-result", function () {
    return call("POST", API + "/retrieve", { text: document.getElementById("query-text").value, top_k: 10 });
  });

  var queryForm = document.getElementById("query-form");
  queryForm.addEventListener("submit", function (event) {
    event.preventDefault();
    run("query-result", function () {
      return call("POST", API + "/query", { text: document.getElementById("query-text").value, top_k: 10 });
    });
  });

  var graphForm = document.getElementById("graph-form");
  graphForm.addEventListener("submit", function (event) {
    event.preventDefault();
    run("graph-result", function () {
      return call("POST", API + "/graph", { entity: document.getElementById("graph-entity").value, depth: 1 });
    });
  });

  var wikiForm = document.getElementById("wiki-form");
  wikiForm.addEventListener("submit", function (event) {
    event.preventDefault();
    run("wiki-result", function () {
      return call("POST", API + "/wiki", { query: document.getElementById("wiki-query").value });
    });
  });

  var materializeForm = document.getElementById("materialize-form");
  materializeForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var token = document.getElementById("approval-token").value.trim();
    run("materialize-result", function () {
      return call("POST", API + "/materialize", { approval_token: token });
    });
  });

  var delegationForm = document.getElementById("delegation-form");
  delegationForm.addEventListener("submit", function (event) {
    event.preventDefault();
    run("delegation-result", function () {
      return call("POST", API + "/agent-delegation", {
        task: document.getElementById("delegation-task").value,
        target: document.getElementById("delegation-target").value || undefined
      });
    });
  });

  function refreshBootstrapStatus() {
    call("GET", API + "/indexing-status").then(function (status) {
      show("bootstrap-status", status);
      var retrieval = status.indexes && status.indexes.retrieval;
      var execution = retrieval && retrieval.execution;
      show("active-mode", "Active mode: " + (execution ? execution.mode : "not ready"));
      show("active-mode-detail", execution ? ("Backend: " + execution.backend + " · " +
        (execution.device ? "Device: " + execution.device + " · " : "") +
        execution.reason + " Source: " + execution.source + ". Scope: embedding inference; chat model hardware is managed by its provider.") : "Waiting for an embedding runtime. Auto is a request, not a device.");
    }).catch(function (error) {
      show("bootstrap-status", String(error));
    });
  }
  refreshBootstrapStatus();
  window.setInterval(refreshBootstrapStatus, 3000);

  // ---- Optional server-side chat connection ----------------------------
  var chatForm = document.getElementById("chat-form");
  if (chatForm) {
    function chatHelp() {
      show("chat-help", document.getElementById("chat-provider").value === "anthropic" ?
        "Anthropic: use https://api.anthropic.com/v1, an available Claude model ID and an Anthropic API key. A Claude Code login/subscription is not an API endpoint or API key." :
        "LM Studio: start its server and load a chat model. From Docker use http://host.docker.internal:1234/v1 and the exact loaded model ID. The server must accept connections from Docker. For another server enter its OpenAI-compatible /v1 base URL. This is a chat model, separate from Gemma embeddings.");
    }
    function fillChat(settings) {
      document.getElementById("chat-enabled").checked = settings.enabled;
      document.getElementById("chat-provider").value = settings.provider;
      document.getElementById("chat-base-url").value = settings.base_url;
      document.getElementById("chat-model").value = settings.model;
      document.getElementById("chat-share-context").checked = settings.share_context;
      document.getElementById("chat-key").value = "";
      document.getElementById("chat-clear-key").checked = false;
      show("chat-status", (settings.enabled ? "Generated answers enabled" : "Search only; chat disabled") +
        ". Saved on server; no restart required. Provider key: " + (settings.api_key_set ? "saved (hidden)" : "not set") +
        ". Test the saved connection to verify availability.");
      chatHelp();
    }
    call("GET", API + "/admin/chat").then(fillChat).catch(function (error) { show("chat-status", error.message); });
    document.getElementById("chat-provider").addEventListener("change", chatHelp);
    chatForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var saveButton = document.getElementById("chat-save");
      saveButton.disabled = true;
      show("chat-status", "Saving server configuration…");
      call("PUT", API + "/admin/chat", {
        enabled: Boolean(document.getElementById("chat-enabled").checked),
        provider: document.getElementById("chat-provider").value,
        base_url: document.getElementById("chat-base-url").value,
        model: document.getElementById("chat-model").value,
        api_key: document.getElementById("chat-key").value,
        clear_api_key: Boolean(document.getElementById("chat-clear-key").checked),
        share_context: Boolean(document.getElementById("chat-share-context").checked)
      }).then(fillChat).catch(function (error) {
        show("chat-status", error.message);
      }).then(function () { saveButton.disabled = false; });
    });
    document.getElementById("chat-test").addEventListener("click", function () {
      var button = document.getElementById("chat-test");
      button.disabled = true;
      run("chat-status", function () { return call("POST", API + "/admin/chat/test", {}); }).then(function () { button.disabled = false; });
    });
  }

  // ---- First-start wizard and observable indexing jobs -----------------
  function pause() { return new Promise(function (resolve) { window.setTimeout(resolve, 1000); }); }
  function waitForIndex(deadline) {
    return call("GET", API + "/indexing-status").then(function (status) {
      show("bootstrap-status", status);
      if (status.ready) { return { status: "completed", message: "Search index ready", indexes: status.indexes }; }
      if (!status.hydration.in_progress) { throw new Error(status.hydration.reason || "Indexing failed; inspect container logs."); }
      if (Date.now() > deadline) { throw new Error("Indexing still running. Check indexing status and container logs."); }
      return pause().then(function () { return waitForIndex(deadline); });
    });
  }
  function waitForJob(jobId, deadline) {
    return call("GET", API + "/admin/jobs/" + encodeURIComponent(jobId)).then(function (job) {
      show("wizard-result", job);
      if (job.status === "failed") { throw new Error(job.message); }
      if (job.status === "completed") { return job; }
      if (Date.now() > deadline) { throw new Error("Job still running. Check indexing status and container logs."); }
      return pause().then(function () { return waitForJob(jobId, deadline); });
    });
  }
  function indexAction(action) {
    var buttons = [document.getElementById("wizard-submit-button"), document.getElementById("admin-reindex-button")];
    var output = document.getElementById("wizard-result");
    buttons.forEach(function (button) { button.disabled = true; });
    output.setAttribute("aria-busy", "true");
    return run("wizard-result", action).then(function () {
      output.setAttribute("aria-busy", "false");
      buttons.forEach(function (button) { button.disabled = false; });
      refreshBootstrapStatus();
    });
  }
  var wizardForm = document.getElementById("wizard-form");
  if (wizardForm) {
    call("GET", API + "/admin/retrieval").then(function (settings) {
      var select = document.getElementById("embedding-model-select");
      // Two bindings of one checkpoint; native is an explicit operator opt-in.
      // A managed deployment never offers unconfigured alternative models.
      if (settings.embedding_model_alias === "gemma-torch") {
        select.add(new Option("EmbeddingGemma 2 (configured native Transformers binding)", "gemma-torch"));
      }
      select.value = settings.embedding_model_alias;
      document.getElementById("embedding-device-select").value = settings.device;
      document.getElementById("docling-enabled-checkbox").checked = settings.document_processing_enabled;
      show("wizard-result", settings);
    }).catch(function (error) { show("wizard-result", error.message); });

    wizardForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var payload = {
        embedding_model_alias: document.getElementById("embedding-model-select").value,
        device: document.getElementById("embedding-device-select").value,
        document_processing_enabled: Boolean(document.getElementById("docling-enabled-checkbox").checked)
      };
      indexAction(function () {
        return call("POST", API + "/wizard", payload).then(function () {
          return waitForIndex(Date.now() + 30 * 60 * 1000);
        });
      });
    });
    document.getElementById("admin-reindex-button").addEventListener("click", function () {
      indexAction(function () {
        return call("POST", API + "/admin/reindex", {}).then(function (job) {
          return waitForJob(job.job_id, Date.now() + 30 * 60 * 1000);
        });
      });
    });
  }
});
