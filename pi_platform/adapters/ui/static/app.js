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

function run(targetId, action) {
  show(targetId, "working…");
  return action().then(function (result) {
    show(targetId, result);
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
  var tokenField = document.getElementById("approval-token");
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

  // ---- Model settings panel -------------------------------------------
  // The platform ships with a local model endpoint so chat-completions work
  // out of the box. The user can point the UI at any other OpenAI-compatible
  // endpoint; the change is persisted in localStorage and re-applied on
  // every page load. The shim re-reads ``PI_OPENAI_BASE_URL`` and
  // ``PI_OPENAI_MODEL`` only at process start, so changes here are a
  // client-side hint until the operator restarts the platform with the
  // matching environment variables — surfaced clearly in the status box.
  var MODEL_STORAGE_KEY = "pi_model_settings_v1";
  var DEFAULT_BASE_URL = "http://local-llm:8767/v1";
  var DEFAULT_MODEL = "project-intelligence";

  function loadModelSettings() {
    try {
      var raw = window.localStorage.getItem(MODEL_STORAGE_KEY);
      return raw ? JSON.parse(raw) : { base_url: DEFAULT_BASE_URL, model: DEFAULT_MODEL };
    } catch (err) {
      return { base_url: DEFAULT_BASE_URL, model: DEFAULT_MODEL };
    }
  }

  function saveModelSettings(baseUrl, model) {
    var payload = {
      base_url: (baseUrl || DEFAULT_BASE_URL).trim(),
      model: (model || DEFAULT_MODEL).trim(),
    };
    window.localStorage.setItem(MODEL_STORAGE_KEY, JSON.stringify(payload));
    return payload;
  }

  function describeConfiguration(settings) {
    return [
      "active model:    " + settings.model,
      "active endpoint: " + settings.base_url,
      "",
      "Persisted in this browser only. To apply across all clients, set",
      "PI_OPENAI_BASE_URL and PI_OPENAI_MODEL in the platform environment",
      "and restart the container."
    ].join("\n");
  }

  var modelForm = document.getElementById("model-form");
  if (modelForm) {
    var current = loadModelSettings();
    document.getElementById("model-base-url").value = current.base_url;
    document.getElementById("model-name").value = current.model;
    show("model-status", describeConfiguration(current));

    modelForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var saved = saveModelSettings(
        document.getElementById("model-base-url").value,
        document.getElementById("model-name").value,
      );
      show("model-status", describeConfiguration(saved));
    });

    var resetButton = document.getElementById("model-reset");
    if (resetButton) {
      resetButton.addEventListener("click", function () {
        document.getElementById("model-base-url").value = DEFAULT_BASE_URL;
        document.getElementById("model-name").value = DEFAULT_MODEL;
        var saved = saveModelSettings(DEFAULT_BASE_URL, DEFAULT_MODEL);
        show("model-status", describeConfiguration(saved));
      });
    }
  }

  function refreshBootstrapStatus() {
    call("GET", API + "/indexing-status").then(function (status) {
      show("bootstrap-status", status);
    }).catch(function (error) {
      show("bootstrap-status", String(error));
    });
  }
  refreshBootstrapStatus();
  window.setInterval(refreshBootstrapStatus, 3000);

  // ---- First-start wizard & semantic model administration ---------------
  var wizardForm = document.getElementById("wizard-form");
  if (wizardForm) {
    call("GET", API + "/admin/retrieval").then(function (settings) {
      if (settings && settings.embedding_model_alias) {
        document.getElementById("embedding-model-select").value = settings.embedding_model_alias;
      }
      if (settings && settings.device) {
        document.getElementById("embedding-device-select").value = settings.device;
      }
      if (settings && typeof settings.document_processing_enabled === "boolean") {
        document.getElementById("docling-enabled-checkbox").checked = settings.document_processing_enabled;
      }
      show("wizard-result", settings);
    }).catch(function () { /* keep default message */ });

    wizardForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var payload = {
        embedding_model_alias: document.getElementById("embedding-model-select").value,
        device: document.getElementById("embedding-device-select").value,
        document_processing_enabled: Boolean(document.getElementById("docling-enabled-checkbox").checked),
        bootstrap_state: "not-started"
      };
      run("wizard-result", function () {
        return call("POST", API + "/wizard", payload);
      });
    });

    bindButton("admin-reindex-button", "wizard-result", function () {
      return call("POST", API + "/admin/reindex", {});
    });
  }
});