import fs from 'node:fs/promises';
import vm from 'node:vm';
import {Blob,atob,btoa} from 'node:buffer';
import {TextEncoder,TextDecoder} from 'node:util';
import {URL,URLSearchParams} from 'node:url';
class Response {}
import assert from 'node:assert/strict';
const source=await fs.readFile(new URL('./runtime-loader.js',import.meta.url),'utf8');
async function check(protocol,Worker){
 let initializations=0,compilations=0,fetchCalls=0;
 const nativeFetch=()=>{fetchCalls++;throw Error('Unexpected network call')};
 const py={runPython(){},globals:{get(){const fn=()=>{compilations++;return JSON.stringify({ok:true,code:'(lambda: 42)()'})};fn.destroy=()=>{};return fn}}};
 const elements={'runtime-assets':{textContent:JSON.stringify({'pyodide.js':'','pyodide-lock.json':btoa('{}')})},'compiler-source':{textContent:'# compiler'}};
 const context=vm.createContext({$:id=>elements[id],status(){},LIMIT:262144,location:{protocol,search:''},Worker,
  Uint8Array,TextEncoder,TextDecoder,Response,Blob,URL,URLSearchParams,atob,setTimeout,clearTimeout,
  fetch:nativeFetch,oneRuntimeModule:Promise.resolve(()=>{}),loadPyodide:async()=>{initializations++;return py}});
 vm.runInContext(source,context);
 for(let i=0;i<2;i++)assert.equal((await vm.runInContext('compilePython("print(42)")',context)).ok,true);
 assert.equal(initializations,1,'Reuse initialized runtime');
 assert.equal(compilations,2);
 assert.equal(context.fetch,nativeFetch,'Restore main-thread fetch');
 assert.equal(fetchCalls,0);
}
await check('file:',class{constructor(){throw Error('Local file must never create a worker')}});
await check('https:',class{constructor(){throw new Error('SecurityError')}});
await check('https:',class{postMessage(){queueMicrotask(()=>this.onerror({message:'',preventDefault(){}}))}terminate(){}});
await check('https:',undefined);
console.log('PASS: local files, blocked constructors, async worker failure, missing workers, runtime reuse, fetch restoration, and no network calls.');
