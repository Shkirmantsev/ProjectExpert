/* Execute the shipped browser script with a minimal DOM and real promise flow. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function browser(options = {}) {
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {value: '', checked: true, disabled: false,
      textContent: '', attrs: {}, listeners: {}, children: [],
      setAttribute(k, v) { this.attrs[k] = v; },
      addEventListener(k, fn) { this.listeners[k] = fn; },
      add() {},
      appendChild(child) { this.children.push(child); },
      remove() {},
    });
    return nodes.get(id);
  }
  const requests = [];
  let readyChecks = 0, jobChecks = 0, knowledgeChecks = 0;
  const context = {console, Promise, Date, Option: function () {},
    document: {body: node('body'), getElementById: node, createElement() { return node(Symbol()); },
      querySelectorAll() { return ['query-text', 'source-encoding-add', 'source-encoding-preview', 'source-encoding-save'].map(node); },
      addEventListener(_, fn) { this.start = fn; }},
    window: {location:{protocol:options.preview ? 'file:':'http:'},
      setInterval() {}, setTimeout(fn) { fn(); }},
    fetch(path, init) {
      requests.push({path, ...init});
      let body = {};
      let status = 200;
      if (path.endsWith('/admin/retrieval')) body = {embedding_model_alias:'gemma',device:'cpu',document_processing_enabled:true};
      else if (path.endsWith('/admin/source-encodings')) {
        if (options.auth && !init.headers.Authorization) {
          status = 401;
          body = {error:'Authentication required'};
        } else {
          body = init.method === 'GET'
            ? {policy:{schema_version:1, rules:[]}, encodings:['cp1251','cp1252']}
            : {matched:1, decoded:1, failed:0, saved:init.method === 'PUT'};
        }
      }
      else if (path.endsWith('/admin/runtime')) body = {managed_control:options.managed !== false,models:[{value:'gemma',label:'Managed Gemma'},{value:'gemma-torch',label:'Native Gemma'}],devices:{gemma:['auto','cpu','vulkan'], 'gemma-torch':['auto','cpu']},message:'Applies runtime changes'};
      else if (path.endsWith('/ui-version')) body = {ui_contract:'knowledge-sync/2',ui_build:'fixture-build'};
      else if (path.endsWith('/auth-status')) body = {token_required:options.auth || false,local_owner_access:!options.auth,admin_access:!options.auth};
      else if (path.endsWith('/wizard')) {body = {job_id:'apply-123'}; status=202;}
      else if (path.endsWith('/indexing-status')) body = {ready: Boolean(options.coverage) || ++readyChecks > 2, hydration:{in_progress:true}, indexes:{active_sources:3,retrieval:{execution:{mode:options.mode || 'CPU',backend:'cpu',reason:'Verified deployment CPU profile',source:'selected deployment profile'},source_coverage:options.coverage}}};
      else if (path.endsWith('/admin/chat')) body = init.method === 'PUT' ? {...JSON.parse(init.body), api_key:undefined,api_key_set:true} : {enabled:false,provider:'openai',base_url:'',model:'',share_context:false,api_key_set:false};
      else if (path.endsWith('/admin/chat/test')) body = {ok:true,message:'Connection successful'};
      else if (path.endsWith('/admin/reindex')) { body = {job_id:'job-123',status:'queued'}; status = 202; }
      else if (path.endsWith('/knowledge/settings')) body = init.method === 'PUT' ? JSON.parse(init.body) : {share_enabled:false,post_reindex_export:false,include_vectors:false};
      else if (/\/knowledge\/(restore|reindex|export|publish)$/.test(path)) { body = {job_id:'knowledge-' + path.split('/').at(-1)}; status=202; }
      else if (path.includes('/admin/jobs/knowledge-')) {
        if (options.fail) body={status:'failed',message:'Embedding server unreachable'};
        else if (path.endsWith('reindex')) body=++knowledgeChecks === 1 ? {status:'running'} : {status:'completed',result:{new_vectors:0,source_parse_misses:0}};
        else body = {status:'completed',result:path.endsWith('restore') ? {state:'requires-reindex'} : {stagingId:'proposal-123',snapshotId:'snapshot-123',sources:2,excludedSourceCount:1,changedPaths:['objects/hash.jsonl'],...(path.endsWith('publish') ? {state:'published'}:{})}};
      }
      else if (path.includes('/admin/jobs/')) body = options.fail ? {status:'failed',message:'Embedding server unreachable'} : {status:++jobChecks > 1 ? 'completed':'running',message:'Indexing'};
      return Promise.resolve({ok:status < 400,status,text:() => Promise.resolve(JSON.stringify(body))});
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('pi_platform/adapters/ui/static/app.js', 'utf8'), context);
  context.document.start();
  return {node, requests, context};
}
async function flush() { for (let i=0;i<12;i++) await Promise.resolve(); }
async function main() {
  const preview=browser({preview:true});await flush();
  assert.equal(preview.requests.length,0,'File preview must not call unavailable APIs');
  assert.match(preview.node('deployment-status').textContent,/preview/i);
  assert.equal(preview.node('body').attrs['data-file-preview'], 'true');
  assert.equal(preview.node('preview-live-link').hidden, false);
  assert.equal(preview.node('query-text').disabled, true);
  assert.equal(preview.node('source-encoding-preview').disabled, true);
  const open = browser();await flush();
  assert.equal(open.node('api-access-panel').hidden,true);
  assert.equal(open.node('local-access-notice').hidden,false);
  assert.equal(open.requests.find(r => r.path.endsWith('/knowledge/settings')).headers.Authorization,undefined);
  const external=browser({managed:false});await flush();
  assert.equal(external.node('embedding-device-select').disabled,true,'Uncontrolled remote hardware must not look switchable');
  assert.match(external.node('runtime-help').textContent,/external|controller/i);
  const b = browser();
  assert.equal(b.node('source-encoding-preview').disabled, true);
  assert.equal(b.node('source-encoding-save').disabled, true);
  await flush();
  assert.equal(b.node('source-encoding-preview').disabled, false);
  assert.equal(b.node('source-encoding-save').disabled, false);
  assert.equal(b.node('embedding-model-select').value, 'gemma');
  assert.equal(b.node('access-token').disabled,true);
  assert.match(b.node('access-token-help').textContent,/No API token required/);
  b.node('source-encoding-add').listeners.click();
  const [pattern, encoding] = b.node('source-encoding-rules').children[0].children;
  pattern.value = 'db/**/*.sql'; pattern.listeners.input();
  encoding.value = 'cp1251'; encoding.listeners.change();
  b.node('source-encoding-preview').listeners.click(); await flush();
  const previewRequest = b.requests.find(r => r.method === 'POST' && r.path.endsWith('/admin/source-encodings'));
  assert.deepEqual(JSON.parse(previewRequest.body), {
    schema_version:1, rules:[{pattern:'db/**/*.sql',encoding:'cp1251'}],
  });
  assert.match(b.node('source-encoding-result').textContent,/1 of 1 matching files decoded/);
  b.node('source-encoding-save').listeners.click(); await flush();
  assert.match(b.node('source-encoding-result').textContent, /Rules saved. Update the local index/);
  const secured=browser({auth:true});await flush();
  assert.equal(secured.node('access-token').disabled,false);
  assert.equal(secured.node('source-encoding-save').disabled, true);
  assert.match(secured.node('source-encoding-result').textContent, /Authentication required/);
  assert.match(secured.node('access-token-help').textContent,/PI_UI_TOKEN/);
  assert.equal(b.node('active-mode').textContent,'Embedding device: CPU');
  const hybrid=browser({mode:'Hybrid'}); await flush();
  assert.equal(hybrid.node('active-mode').textContent,'Embedding device: Hybrid');
  const partial = browser({coverage: {eligible: 16000, indexed: 15960, skipped: 40}});
  await flush();
  assert.match(partial.node('bootstrap-status').textContent, /15960 of 16000 sources indexed. 40 skipped/);
  b.node('chat-enabled').checked=true;
  b.node('chat-share-context').checked=true;
  b.node('chat-base-url').value='http://host.docker.internal:1234/v1';
  b.node('chat-model').value='local-chat';b.node('chat-key').value='fixture-secret';
  b.node('chat-form').listeners.submit({preventDefault(){}});
  assert.equal(b.node('chat-save').disabled,true);
  await flush();await flush();
  assert.equal(b.node('chat-save').disabled,false);
  assert.equal(b.node('chat-key').value,'');
  assert.match(b.node('chat-status').textContent,/Generated answers enabled/);
  assert.doesNotMatch(b.node('chat-status').textContent,/fixture-secret/);
  b.node('chat-test').listeners.click();await flush();
  assert.match(b.node('chat-status').textContent,/Connection successful/);
  assert.match(b.context.formatResult('query-result',{answer:'Generated answer [1]',results:[],explanations:['provider failed']}),/Generated answer/);
  const fallback = b.context.formatResult('query-result', {
    answer: null,
    results: [{metadata:{sourcePath:'brief.md'},snippet:'Evidence',score:0.5}],
    explanations: ['Chat unavailable: timed out waiting for the local model.'],
  });
  assert.match(fallback, /^No generated answer/);
  assert.ok(fallback.indexOf('timed out') < fallback.indexOf('brief.md'));
  assert.doesNotMatch(b.context.formatResult('retrieve-result', {
    results: [{metadata:{sourcePath:'brief.md'},snippet:'Evidence',score:0.5}],
  }), /No generated answer/);
  b.node('admin-reindex-button').listeners.click();
  assert.equal(b.node('admin-reindex-button').disabled,true);
  assert.equal(b.node('knowledge-sync-result').attrs['aria-busy'],'true');
  await flush(); await flush();
  assert.equal(b.node('admin-reindex-button').disabled,false);
  assert.match(b.node('knowledge-sync-result').textContent,/completed/);
  assert.equal(b.requests.filter(r=>r.path.includes('/admin/jobs/')).length,2);
  b.node('wizard-form').listeners.submit({preventDefault(){}});
  assert.equal(b.node('wizard-submit-button').disabled,true);
  await flush(); await flush();
  assert.equal(b.node('wizard-submit-button').disabled,false);
  assert.match(b.node('wizard-result').textContent,/completed/);
  assert.ok(b.requests.some(r=>r.path.endsWith('/admin/jobs/apply-123')));
  const failed = browser({fail:true}); await flush();
  failed.node('admin-reindex-button').listeners.click(); await flush(); await flush();
  assert.match(failed.node('knowledge-sync-result').textContent,/Embedding server unreachable/);
  assert.equal(failed.node('admin-reindex-button').disabled,false);
  secured.node('access-token').value = 'api-token';
  secured.node('api-access-form').listeners.submit({preventDefault(){}});
  await flush(); await flush();
  assert.equal(secured.node('source-encoding-save').disabled, false);
  secured.node('sources-button').listeners.click(); await flush();
  assert.equal(secured.requests.at(-1).headers.Authorization, 'Bearer api-token');
  assert.equal(secured.node('access-token').value, '');
  assert.match(b.context.formatResult('wiki-result',{documents:[{path:'page.md',text:'# Useful wiki'}]}),/# Useful wiki/);
  assert.match(b.context.formatResult('query-result',{results:[{metadata:{sourcePath:'brief.md'},snippet:'Evidence',score:0.5}]}),/brief.md.*score 0.5\nEvidence/);
  b.node('knowledge-restore-button').listeners.click();await flush();await flush();
  assert.match(b.node('knowledge-sync-result').textContent,/Restore needs a local update/);
  b.node('knowledge-share').checked=true;
  b.node('knowledge-save').listeners.click();await flush();
  const preferences = b.requests.find(r=>r.path.endsWith('/knowledge/settings') && r.method==='PUT');
  assert.deepEqual(JSON.parse(preferences.body),{share_enabled:true,post_reindex_export:false,include_vectors:false});
  b.node('knowledge-export-button').listeners.click();await flush();await flush();
  assert.equal(b.node('knowledge-publish-button').hidden,false);
  assert.match(b.node('knowledge-sync-result').textContent,/objects\/hash.jsonl/);
  b.node('knowledge-publish-button').listeners.click();await flush();await flush();
  const publish = b.requests.find(r=>r.path.endsWith('/knowledge/publish'));
  assert.deepEqual(JSON.parse(publish.body),{stagingId:'proposal-123',snapshotId:'snapshot-123'});
  assert.equal(b.node('knowledge-publish-button').hidden,true);
  assert.equal(b.node('api-access-panel').hidden, true);
  assert.equal(b.node('local-access-notice').hidden, false);
  console.log('PASS: browser indexing progress, completion, failure, auth separation and readable evidence');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
