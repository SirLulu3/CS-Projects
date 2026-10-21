// Both backends use the exact same bundled runtime and compiler.
let compilerWorker=null, readyPromise=null, busy=false, pending=null;
let mainRuntime=null;
const decodeAsset=base64=>Uint8Array.from(atob(base64),char=>char.charCodeAt(0));

async function initializeBundledPython(assets,createPyodideModule,compiler){
 const root='https://one-runtime.invalid/';
 const previousFetch=globalThis.fetch;
 globalThis.fetch=async(input,options)=>{
  const url=typeof input==='string'?input:input.url || String(input);
  if(!url.startsWith(root))return previousFetch.call(globalThis,input,options);
  const name=url.slice(root.length);
  if(!assets[name])throw new Error('Missing bundled runtime asset: '+name);
  return new Response(decodeAsset(assets[name]),{headers:{'Content-Type':name.endsWith('.wasm')?'application/wasm':name.endsWith('.json')?'application/json':'application/octet-stream'}});
 };
 try{
  const py=await globalThis.loadPyodide({indexURL:root,createPyodideModule,
   lockFileContents:JSON.parse(new TextDecoder().decode(decodeAsset(assets['pyodide-lock.json'])))});
  py.runPython(compiler);
  return py;
 }finally{globalThis.fetch=previousFetch}
}
function invokeCompiler(py,text){
 const fn=py.globals.get('reduce_python');
 try{return JSON.parse(fn(text))}finally{fn.destroy()}
}
function resetWorker(){if(compilerWorker)compilerWorker.terminate();compilerWorker=null;pending=null}
function startWorker(assets){
 return new Promise((resolve,reject)=>{
  const workerCode=`
   const decodeAsset=${decodeAsset.toString()};
   const initializeBundledPython=${initializeBundledPython.toString()};
   const invokeCompiler=${invokeCompiler.toString()};
   let py;
   onmessage=async({data})=>{
    try{
     if(data.type==='init'){
      const moduleURL=URL.createObjectURL(new Blob([decodeAsset(data.assets['pyodide.asm.mjs'])],{type:'text/javascript'}));
      try{const {default:createPyodideModule}=await import(moduleURL);py=await initializeBundledPython(data.assets,createPyodideModule,data.compiler)}
      finally{URL.revokeObjectURL(moduleURL)}
      postMessage({type:'ready'});
     }else{postMessage({type:'result',result:invokeCompiler(py,data.source)})}
    }catch(error){postMessage({type:'error',error:String(error)})}
   };`;
  const url=URL.createObjectURL(new Blob([decodeAsset(assets['pyodide.js']),'\n',workerCode],{type:'text/javascript'}));
  let worker;
  try{worker=new Worker(url,{type:'module'});compilerWorker=worker}
  catch(error){URL.revokeObjectURL(url);reject(error);return}
  let ready=false;
  const cleanup=()=>{clearTimeout(timer);URL.revokeObjectURL(url)};
  const fail=error=>{
   cleanup();worker.terminate();if(compilerWorker===worker)compilerWorker=null;
   if(!ready)reject(error);
   else{readyPromise=null;if(pending){pending.reject(error);pending=null}}
  };
  const timer=setTimeout(()=>fail(new Error('Worker startup timed out.')),20000);
  worker.onmessage=({data})=>{
   if(data.type==='ready'){ready=true;cleanup();resolve({kind:'worker',worker})}
   else if(data.type==='result'&&pending){const request=pending;pending=null;request.resolve(data.result)}
   else if(data.type==='error')fail(new Error(data.error));
  };
  worker.onerror=event=>{event.preventDefault();fail(new Error(event.message||'Worker startup is blocked.'))};
  worker.postMessage({type:'init',compiler:$('compiler-source').textContent,assets});
 });
}
async function startMainRuntime(assets){
 status('Starting the bundled parser in compatibility mode (no workers)…');
 if(!mainRuntime){
  const creator=await globalThis.oneRuntimeModule;
  mainRuntime=await initializeBundledPython(assets,creator,$('compiler-source').textContent);
 }
 return {kind:'main',py:mainRuntime};
}
function getCompiler(){
 if(readyPromise)return readyPromise;
 readyPromise=(async()=>{
  const assets=JSON.parse($('runtime-assets').textContent);
  // Local files use inline scripts, avoiding opaque-origin blob workers entirely.
  if(location.protocol==='file:'||new URLSearchParams(location.search).has('compat')||typeof Worker==='undefined')return startMainRuntime(assets);
  try{return await startWorker(assets)}catch{return startMainRuntime(assets)}
 })().catch(error=>{readyPromise=null;throw error});
 return readyPromise;
}
async function compilePython(text){
 if(new TextEncoder().encode(text).length>LIMIT)throw new Error('Source exceeds the 256 KiB limit. Please use a smaller script.');
 const backend=await getCompiler();
 if(backend.kind==='main'){
  // Give the browser a frame before synchronous Python AST compilation.
  await new Promise(resolve=>setTimeout(resolve,0));
  return invokeCompiler(backend.py,text);
 }
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{resetWorker();readyPromise=null;reject(new Error('Compilation exceeded 30 seconds. Try a smaller script.'))},30000);
  pending={resolve:value=>{clearTimeout(timer);resolve(value)},reject:error=>{clearTimeout(timer);reject(error)}};
  backend.worker.postMessage({type:'compile',source:text});
 });
}
