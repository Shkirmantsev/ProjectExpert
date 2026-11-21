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
        var message = parsed && parsed.error;
        if (message && typeof message === 'object') { message = message.message; }
        throw new Error((typeof message === 'string' ? message : 'The request could not be completed') + ' (HTTP ' + response.status + ')');
      }
      return parsed;
    });
  });
}

function formatResult(targetId, result) {
  if (targetId === 'knowledge-sync-result' && result && typeof result === 'object') {
    var report = result.result || result;
    if (report.state === 'requires-reindex') {
      return 'Restore needs a local update.\n' + (report.importedSources || 0) +
        ' sources imported. No source parsing or new embeddings were run. Choose Reindex to complete missing work.';
    }
    if (report.state === 'portable-restored') {
      var restored = report.portable_import || report;
      return 'Knowledge restored. Local search is ready.\n' + (restored.importedSources || 0) +
        ' sources imported · ' + (restored.importedVectors || 0) + ' embeddings restored.';
    }
    if (report.state === 'no-exportable-sources') {
      return 'No independently safe export context is available.\nLocal search and MCP keep the complete context. Reindex once after first enabling sharing.' +
        (report.cleanupRequired ? '\nPreviously generated files need owner-reviewed cleanup before sharing.' : '');
    }
    if (report.stagingId) {
      return (report.state === 'published' ? 'Safe Git files published. Commit and push when you are ready.' : 'Safe export ready for your review.') +
        '\n' + report.sources + ' complete sources · ' + (report.safeContextCount || 0) + ' safe text fragments · ' + (report.excludedSourceCount || 0) + ' sources kept fully or partly local · ' +
        (report.fileCount || 0) + ' text files · ' + ((report.totalBytes || 0) / 1048576).toFixed(2) + ' MiB' +
        (report.changedPaths && report.changedPaths.length ? '\nChanged files:\n' + report.changedPaths.join('\n') : '\nNo file changes.');
    }
    if (typeof report.share_enabled === 'boolean') {
      return 'Sharing preferences saved. Safe Git export is ' + (report.share_enabled ? 'enabled.' : 'disabled.') +
        '\nAutomatic export is ' + (report.post_reindex_export ? 'enabled for the approved session.' : 'off.');
    }
    if (report.state === 'source-review-saved') { return 'Classification saved for ' + (report.reviewedCount || 1) + ' file(s): ' + report.classification + '.'; }
    if ('new_vectors' in report || 'source_parse_misses' in report) {
      return 'Local knowledge update completed.\n' + (report.source_parse_misses || 0) + ' sources processed · ' +
        (report.source_parse_hits || 0) + ' reused · ' + (report.new_vectors || 0) + ' new embeddings.';
    }
    return report.message || 'Processing project knowledge…';
  }
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
    if (targetId === "query-result" && !result.answer) {
      return "No generated answer. Search evidence is available below." + explanation + "\n\nRetrieved sources:\n" + evidence;
    }
    return answer + evidence + explanation;
  }
  return result;
}

function run(targetId, action) {
  show(targetId, targetId === "query-result" ? "Searching project evidence… If chat is enabled, a local model can take several minutes to generate an answer (up to 10 minutes)." : "working…");
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
  if (window.location && window.location.protocol === 'file:') {
    show('deployment-status', 'Design preview — styles are available, but this file is not a running application. Open the live server to use search and knowledge actions.');
    show('active-mode', 'Preview only — no runtime connected');
    show('runtime-help', 'GPU selection belongs to the running server, not this design preview.');
    document.getElementById('preview-live-link').hidden = false;
    if (document.querySelectorAll) {
      document.querySelectorAll('button, input, select').forEach(function (control) { control.disabled = true; });
    }
    return;
  }
  call('GET', API + '/ui-version').then(function (identity) {
    show('deployment-status', identity.knowledge_operations === false ?
      'Current UI loaded; knowledge operations are not configured. Start the application through the platform launcher.' : identity.ui_contract === 'knowledge-sync/2' ?
      'Connected · knowledge workflow · build ' + identity.ui_build.slice(0, 10) :
      'Older application detected. Update the application image and deployment kit to use the current knowledge workflow.');
  }).catch(function () {
    show('deployment-status', 'This server does not identify the current UI build. Update its application image and deployment kit; a browser refresh cannot install new application code.');
  });
  var reloadProtected = [];
  var tokenField = document.getElementById("access-token");
  if (tokenField) {
    tokenField.addEventListener("change", function () {
      accessToken = tokenField.value.trim();
      reloadProtected.forEach(function (reload) { reload(); });
    });
    call("GET", API + "/auth-status").then(function (auth) {
      tokenField.disabled = !auth.token_required;
      document.getElementById('api-access-panel').hidden = !auth.token_required;
      document.getElementById('local-access-notice').hidden = !auth.local_owner_access;
      show("access-token-help", auth.token_required ?
        "API authentication is enabled. Enter PI_UI_TOKEN provided by the operator, from the private deployment environment. It protects ProjectExpert API access; it is not an LLM key or an approval token. Kept only in this tab's memory." :
        "No API token required: PI_UI_TOKEN is not configured. Leave this field empty. This optional password protects ProjectExpert API access; it is not needed for local embedding search. The operator can enable it in the private deployment environment.");
    }).catch(function (error) { show("access-token-help", error.message); });
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
      show("bootstrap-status", status.ready ? 'Local search is ready.' :
        (status.hydration && status.hydration.reason || 'Preparing local knowledge. Progress appears here.'));
      var retrieval = status.indexes && status.indexes.retrieval;
      var execution = retrieval && retrieval.execution;
      show("active-mode", "Active mode: " + (execution ? execution.mode : "not ready"));
      show("active-mode-detail", execution ? ("Backend: " + execution.backend + " · " +
        (!status.ready ? "Index refresh in progress or failed; details below. " : "") +
        (execution.device ? "Device: " + execution.device + " · " : "") +
        execution.reason +
        (execution.requested_device === "auto" ? " Requested: Auto. " + (execution.rejected || []).map(function (item) { return item.backend + ": " + item.reason; }).join("; ") : "") +
        " Source: " + execution.source + ". Scope: embedding inference; chat model hardware is managed by its provider.") : "Waiting for an embedding runtime. Auto is a request, not a device.");
    }).catch(function (error) {
      show("bootstrap-status", String(error));
    });
  }
  refreshBootstrapStatus();
  reloadProtected.push(refreshBootstrapStatus);
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
    function loadChat() {
      return call("GET", API + "/admin/chat").then(fillChat).catch(function (error) { show("chat-status", error.message); });
    }
    loadChat();
    reloadProtected.push(loadChat);
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
  function waitForJob(jobId, deadline, targetId) {
    return call("GET", API + "/admin/jobs/" + encodeURIComponent(jobId)).then(function (job) {
      show(targetId || 'wizard-result', formatResult(targetId || 'wizard-result', job));
      if (job.status === "failed") { throw new Error(job.message); }
      if (job.status === "completed") { return job; }
      if (Date.now() > deadline) { throw new Error("Job still running. Check indexing status and container logs."); }
      return pause().then(function () { return waitForJob(jobId, deadline, targetId); });
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
  var knowledgeProposal = null;
  function knowledgeJob(operation, payload) {
    var button = document.getElementById('knowledge-publish-button');
    button.hidden = true;
    return call('POST', API + '/admin/knowledge/' + operation, payload || {}).then(function (job) {
      return waitForJob(job.job_id, Date.now() + 30 * 60 * 1000, 'knowledge-sync-result');
    }).then(function (job) {
      show('knowledge-sync-result', formatResult('knowledge-sync-result', job));
      knowledgeProposal = job.result && job.result.stagingId ? job.result : null;
      button.hidden = !knowledgeProposal || operation === 'publish';
      refreshBootstrapStatus();
      return job;
    });
  }
  function knowledgeAction(operation, payload) {
    var buttons = ['knowledge-restore-button', 'admin-reindex-button', 'knowledge-export-button', 'knowledge-publish-button'];
    buttons.forEach(function (id) { document.getElementById(id).disabled = true; });
    var output = document.getElementById('knowledge-sync-result');
    output.setAttribute('aria-busy', 'true');
    return run('knowledge-sync-result', function () { return knowledgeJob(operation, payload); }).then(function () {
      output.setAttribute('aria-busy', 'false');
      buttons.forEach(function (id) { document.getElementById(id).disabled = false; });
    });
  }
  function loadKnowledgeSettings() {
    return call('GET', API + '/admin/knowledge/settings').then(function (settings) {
      document.getElementById('knowledge-share').checked = settings.share_enabled;
      document.getElementById('knowledge-auto').checked = settings.post_reindex_export;
      document.getElementById('knowledge-vectors').checked = settings.include_vectors;
    }).catch(function (error) { show('knowledge-sync-result', error.message); });
  }
  if (document.getElementById('knowledge-restore-button')) {
    loadKnowledgeSettings();
    reloadProtected.push(loadKnowledgeSettings);
    ['restore', 'export'].forEach(function (operation) {
      document.getElementById('knowledge-' + operation + '-button').addEventListener('click', function () {
        knowledgeAction(operation);
      });
    });
    document.getElementById('knowledge-save').addEventListener('click', function () {
      run('knowledge-sync-result', function () {
        return call('PUT', API + '/admin/knowledge/settings', {
          share_enabled: document.getElementById('knowledge-share').checked,
          post_reindex_export: document.getElementById('knowledge-auto').checked,
          include_vectors: document.getElementById('knowledge-vectors').checked
        });
      });
    });
    document.getElementById('knowledge-publish-button').addEventListener('click', function () {
      if (!knowledgeProposal) { return; }
      knowledgeAction('publish', {
        stagingId: knowledgeProposal.stagingId, snapshotId: knowledgeProposal.snapshotId
      });
    });
  }
  var wizardForm = document.getElementById("wizard-form");
  if (wizardForm) {
    var runtimeCaps = null;
    function fillDevices(selected) {
      if (!runtimeCaps || !runtimeCaps.devices) { return; }
      var model = document.getElementById("embedding-model-select").value;
      var devices = runtimeCaps.devices[model] || ["auto", "cpu"];
      var select = document.getElementById("embedding-device-select");
      select.innerHTML = "";
      var labels = {auto:"Auto (measure CPU/GPU; select faster)",cpu:"CPU",vulkan:"GPU / Vulkan",cuda:"GPU / CUDA",mps:"GPU / Apple Metal"};
      devices.forEach(function (device) { select.add(new Option(labels[device], device)); });
      select.value = devices.indexOf(selected) >= 0 ? selected : "auto";
      select.disabled = model === 'gemma' && !runtimeCaps.managed_control;
      if (select.disabled) {
        show('runtime-help', 'This external embedding runtime has no live controller. Its host deployment selects CPU/GPU. Upgrade the managed deployment kit to enable hardware changes here.');
      } else {
        show('runtime-help', runtimeCaps.message || 'Apply saves settings and updates the local index.');
      }
    }
    document.getElementById("embedding-model-select").addEventListener("change", function () { fillDevices("auto"); });
    function loadRuntimeSettings() {
      return call("GET", API + "/admin/runtime").then(function (caps) {
        runtimeCaps = caps;
        var select = document.getElementById("embedding-model-select");
        if (caps.models) {
          select.innerHTML = "";
          caps.models.forEach(function (model) { select.add(new Option(model.label, model.value)); });
        }
        show("runtime-help", caps.message || "Apply saves server settings and rebuilds the index.");
        return call("GET", API + "/admin/retrieval");
      }).then(function (settings) {
      var select = document.getElementById("embedding-model-select");
      select.value = settings.embedding_model_alias;
      fillDevices(settings.device);
      document.getElementById("embedding-device-select").value = settings.device;
      document.getElementById("docling-enabled-checkbox").checked = settings.document_processing_enabled;
      show("wizard-result", 'Model preferences loaded. Apply to update the local index.');
      }).catch(function (error) { show("wizard-result", error.message); });
    }
    var encodingRules = document.getElementById('source-encoding-rules');
    var encodingChoices = [];
    var encodingPolicy = null;
    function addEncodingRule(rule) {
      var row = document.createElement('p');
      var pattern = document.createElement('input');
      pattern.type = 'text';
      pattern.setAttribute('aria-label', 'Repository file pattern');
      pattern.placeholder = 'Repository file pattern';
      pattern.value = rule.pattern || '';
      var encoding = document.createElement('select');
      encoding.setAttribute('aria-label', 'Fallback encoding');
      encoding.add(new Option('Choose encoding', ''));
      encodingChoices.forEach(function (name) { encoding.add(new Option(name, name)); });
      if (rule.encoding && encodingChoices.indexOf(rule.encoding) < 0) {
        encoding.add(new Option(rule.encoding, rule.encoding));
      }
      encoding.value = rule.encoding || '';
      pattern.addEventListener('input', function () { rule.pattern = pattern.value.trim(); });
      encoding.addEventListener('change', function () { rule.encoding = encoding.value; });
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = 'Remove rule';
      remove.addEventListener('click', function () {
        encodingPolicy.rules.splice(encodingPolicy.rules.indexOf(rule), 1);
        row.remove();
      });
      row.appendChild(pattern);
      row.appendChild(encoding);
      row.appendChild(remove);
      encodingRules.appendChild(row);
    }
    var encodingAdd = document.getElementById('source-encoding-add');
    encodingAdd.addEventListener('click', function () {
      if (!encodingPolicy || encodingPolicy.rules.length >= 256) return;
      var rule = {pattern: '', encoding: ''};
      encodingPolicy.rules.push(rule);
      addEncodingRule(rule);
    });
    function loadSourceEncodings() {
      return call('GET', API + '/admin/source-encodings').then(function (data) {
        encodingPolicy = data.policy;
        encodingPolicy.rules = encodingPolicy.rules || [];
        encodingChoices = data.encodings || [];
        encodingRules.textContent = '';
        encodingPolicy.rules.forEach(addEncodingRule);
        encodingAdd.disabled = false;
        if (data.retry) { show('source-encoding-result', 'The last indexing attempt needs attention. Review encoding rules, then run Reindex.'); }
      }).catch(function (error) { show('source-encoding-result', error.message); });
    }
    ['preview', 'save'].forEach(function (action) {
      document.getElementById('source-encoding-' + action).addEventListener('click', function () {
        if (!encodingPolicy) return;
        if (encodingPolicy.rules.some(function (rule) { return !rule.pattern || !rule.encoding; })) {
          show('source-encoding-result', 'Enter a file pattern and choose an encoding for each rule.');
          return;
        }
        show('source-encoding-result', 'Checking source encodings…');
        call(action === 'save' ? 'PUT' : 'POST', API + '/admin/source-encodings', encodingPolicy)
          .then(function (data) {
            show('source-encoding-result', data.decoded + ' of ' + data.matched + ' matching files decoded. ' +
              data.failed + ' failed. ' + (data.saved ? 'Rules saved. Run Reindex to apply them.' : 'Review the result before saving.'));
          })
          .catch(function (error) { show('source-encoding-result', error.message); });
      });
    });
    loadSourceEncodings();
    reloadProtected.push(loadSourceEncodings);
    loadRuntimeSettings();
    reloadProtected.push(loadRuntimeSettings);

    wizardForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var payload = {
        embedding_model_alias: document.getElementById("embedding-model-select").value,
        device: document.getElementById("embedding-device-select").value,
        document_processing_enabled: Boolean(document.getElementById("docling-enabled-checkbox").checked)
      };
      indexAction(function () {
        return call("POST", API + "/wizard", payload).then(function (job) {
          return job.job_id ? waitForJob(job.job_id, Date.now() + 30 * 60 * 1000) :
            waitForIndex(Date.now() + 30 * 60 * 1000);
        });
      });
    });
    document.getElementById("admin-reindex-button").addEventListener("click", function () {
      knowledgeAction('reindex');
    });
  }
});
