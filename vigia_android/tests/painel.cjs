const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const elements = new Map();
function el(id) { if (!elements.has(id)) elements.set(id, {}); return elements.get(id); }
const videos = [0,1].map(() => ({
  paused: true, load() {}, pause() { this.paused=true; }, play() { this.paused=false; return Promise.resolve(); },
  removeAttribute(k) { delete this[k]; }
}));
const inputs = [0,1].map(i=>({dataset:{lens:String(i)},files:[]}));
const classes=new Set(), prefs=new Map();
const document = {documentElement:{classList:{toggle:(k,on)=>on?classes.add(k):classes.delete(k),contains:k=>classes.has(k)}},
  querySelector:el,querySelectorAll:q=>q==='video'?videos:inputs,addEventListener(){}};
const context={document,localStorage:{getItem:k=>prefs.get(k),setItem:(k,v)=>prefs.set(k,v)},URL:{createObjectURL:f=>'blob:'+f.name,revokeObjectURL(){}},window:{}};
runInNewContext(readFileSync(require('node:path').join(__dirname, '../app/src/main/assets/painel.js'), 'utf8'),context);
(async ()=>{
  assert.deepEqual(videos.map(v=>v.src),['superior.mp4','inferior.mp4']);
  const play=el('#play'); await play.onclick(); assert(videos.every(v=>!v.paused)); await play.onclick();assert(videos.every(v=>v.paused));
  el('#tema').onclick();assert.equal(prefs.get('tema'),'claro');
  inputs[0].files=[{name:'sup.mp4'}];inputs[0].onchange();assert(play.disabled);
  inputs[1].files=[{name:'inf.mp4'}];inputs[1].onchange();assert(!play.disabled);assert(videos.every(v=>!v.loop));
  await play.onclick();context.window.pausar();assert(videos.every(v=>v.paused));
  el('#reset').onclick();assert(videos.every(v=>v.loop));assert.equal(el('#tipo').textContent,'Prévia local');
  videos[1].play=()=>Promise.reject(Error());await play.onclick();assert(videos.every(v=>v.paused));
  console.log('OK: dual-source selection, pause/resume, theme, failure recovery and demo reset.');
})().catch(e=>{console.error(e);process.exit(1)});
