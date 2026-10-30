/* Execute the shipped browser script with a minimal DOM and real promise flow. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function browser(options = {}) {
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {value: '', checked: true, disabled: false,
      textContent: '', attrs: {}, listeners: {},
      setAttribute(k, v) { this.attrs[k] = v; },
      addEventListener(k, fn) { this.listeners[k] = fn; },
      add() {},
    });
    return nodes.get(id);
  }
  const requests = [];
  let readyChecks = 0, jobChecks = 0;
  const context = {console, Promise, Date, Option: function () {},
    document: {getElementById: node, addEventListener(_, fn) { this.start = fn; }},
    window: {setInterval() {}, setTimeout(fn) { fn(); }},
    fetch(path, init) {
      requests.push({path, ...init});
      let body = {};
      let status = 200;
      if (path.endsWith('/admin/retrieval')) body = {embedding_model_alias:'gemma',device:'cpu',document_processing_enabled:true};
      else if (path.endsWith('/indexing-status')) body = {ready: ++readyChecks > 2, hydration:{in_progress:true}, indexes:{active_sources:3,retrieval:{execution:{mode:options.mode || 'CPU',backend:'cpu',reason:'Verified deployment CPU profile',source:'selected deployment profile'}}}};
      else if (path.endsWith('/admin/chat')) body = init.method === 'PUT' ? {...JSON.parse(init.body), api_key:undefined,api_key_set:true} : {enabled:false,provider:'openai',base_url:'',model:'',share_context:false,api_key_set:false};
      else if (path.endsWith('/admin/chat/test')) body = {ok:true,message:'Connection successful'};
      else if (path.endsWith('/admin/reindex')) { body = {job_id:'job-123',status:'queued'}; status = 202; }
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
  const b = browser(); await flush();
  assert.equal(b.node('embedding-model-select').value, 'gemma');
  assert.equal(b.node('active-mode').textContent,'Active mode: CPU');
  const hybrid=browser({mode:'Hybrid'}); await flush();
  assert.equal(hybrid.node('active-mode').textContent,'Active mode: Hybrid');
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
  b.node('admin-reindex-button').listeners.click();
  assert.equal(b.node('admin-reindex-button').disabled,true);
  assert.equal(b.node('wizard-result').attrs['aria-busy'],'true');
  await flush(); await flush();
  assert.equal(b.node('admin-reindex-button').disabled,false);
  assert.match(b.node('wizard-result').textContent,/completed/);
  assert.equal(b.requests.filter(r=>r.path.includes('/admin/jobs/')).length,2);
  b.node('wizard-form').listeners.submit({preventDefault(){}});
  assert.equal(b.node('wizard-submit-button').disabled,true);
  await flush(); await flush();
  assert.equal(b.node('wizard-submit-button').disabled,false);
  assert.match(b.node('wizard-result').textContent,/Search index ready/);
  const failed = browser({fail:true}); await flush();
  failed.node('admin-reindex-button').listeners.click(); await flush(); await flush();
  assert.match(failed.node('wizard-result').textContent,/Embedding server unreachable/);
  assert.equal(failed.node('admin-reindex-button').disabled,false);
  b.node('approval-token').value='approval';
  assert.equal(b.node('approval-token').listeners.change,undefined);
  b.node('access-token').value='api-token';b.node('access-token').listeners.change();
  b.node('sources-button').listeners.click(); await flush();
  assert.equal(b.requests.at(-1).headers.Authorization,'Bearer api-token');
  assert.match(b.context.formatResult('wiki-result',{documents:[{path:'page.md',text:'# Useful wiki'}]}),/# Useful wiki/);
  assert.match(b.context.formatResult('query-result',{results:[{metadata:{sourcePath:'brief.md'},snippet:'Evidence',score:0.5}]}),/brief.md.*score 0.5\nEvidence/);
  console.log('PASS: browser indexing progress, completion, failure, auth separation and readable evidence');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
