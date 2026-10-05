'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const api = require('../static/bible-garden/js/gospel-today.js');
const {humanDate, localDate, midnightDelay, selectDay, orderedReadings, savedChoice, mount, renderReadings, STORAGE_KEY} = api;
assert.equal(humanDate('2026-10-05', 'ru'), 'понедельник, 5 октября 2026');
assert.equal(humanDate('2026-10-05', 'uk'), 'понеділок, 5 жовтня 2026');
assert.throws(() => humanDate('2026-02-30', 'ru'));
assert.throws(() => humanDate('2026-10-05', 'en'));
assert.throws(() => localDate(new Date(NaN)));
const now = new Date(2026, 9, 5, 23, 59, 59);
assert.equal(localDate(now), '2026-10-05'); assert.equal(midnightDelay(now), 1050);
const strings = Object.fromEntries(['out_of_range','loading','error','uncertain','gospel','apostle','ordinary','triodion','pentecostarion','feast','special','royal_hours','no_liturgy','no_liturgy_gospel','no_liturgy_vespers_gospel','presanctified','ordinary_may_be_omitted','ot','language','edition','narrator','missing_text','missing_audio','numbering','nothing_playable','audio_play','audio_pause','audio_again','audio_error','audio_progress'].map(k => [k,k]));
Object.assign(strings, {hour:'hour {hour}',app_hint:'open {book} {chapter}:{verse}',reading_play:'play {reading}',audio_verse:'verse {verse}'});
const editions = {syn: {language:'ru',name:'Synodal',voices:{prudovsky:'Prudovsky',bondarenko:'Bondarenko'}},ubh:{language:'uk',name:'Khomenko',voices:{kozlov_uk:'Kozlov'}},bsb:{language:'en',name:'BSB',voices:{bsb_souer:'Souer'}}};
const config = {lang:'ru',start_year:2026,end_year:2027,strings,editions,defaults:{ru:['syn','prudovsky'],uk:['ubh','kozlov_uk'],en:['bsb','bsb_souer']},audio:{base_url:'https://api.test',site_key:'public+key&test',books:Array.from({length:66},(_,i)=>i===44?52:i+1)}};
const choice = ['syn','prudovsky'];
assert.deepEqual(savedChoice(config,{getItem:()=>null}),choice);
assert.deepEqual(savedChoice(config,{getItem:()=>{throw new Error('privacy');}}),choice);
assert.deepEqual(savedChoice(config,{getItem:()=>JSON.stringify(['syn','bondarenko'])}),['syn','bondarenko']);
assert.throws(() => savedChoice(config,{getItem:()=>'{broken'}));
assert.throws(() => savedChoice(config,{getItem:()=>JSON.stringify(['syn','kozlov_uk'])}));
function daily(date='2026-10-05',translation='syn') {
  const voices = Object.keys(editions[translation].voices);
  const p = (book,label) => ({book,ranges:[[1,1,1,1]],display_ranges:[[1,1,1,1]],label,book_name:label,verses:[[1,1,1,'<script>unsafe</script>']],audio:Object.fromEntries(voices.map(v=>[v,[[10,12]]]))});
  const day = {items:[{kind:'ordinary',apostle:'a',gospel:'g'}],uncertain:false,confirmed_by:['ocu']};
  return {schema_version:2,date,translation,days:{ru:day,uk:day},passages:{a:p(45,'Romans'),g:p(42,'Luke')}};
}
const data = daily();
assert.equal(selectDay(data,data.date,config,choice),data.days.ru);
assert.throws(() => selectDay(data,'2028-01-01',config,choice),RangeError);
assert.throws(() => selectDay(data,'2026-10-06',config,choice));
for (const change of [d=>delete d.passages.a,d=>d.passages.a.audio.prudovsky[0][0]=-1,d=>d.passages.a.verses[0][3]='',d=>d.passages.a.audio={kozlov_uk:[[1,2]]},d=>d.passages.a.unavailable='unknown']) {
  const damaged=structuredClone(data); change(damaged); assert.throws(()=>selectDay(damaged,data.date,config,choice));
}
const absent=structuredClone(data); absent.passages.a={book:45,ranges:[[1,1,1,1]],unavailable:'missing_text'};
assert.equal(selectDay(absent,absent.date,config,choice),absent.days.ru);
const order = orderedReadings({items:[{kind:'ordinary',apostle:'a',gospel:'g',ot:['o1','o2']},{kind:'royal_hours',hours:[{hour:1,apostle:'ha',gospel:'hg'}]},{kind:'feast',gospel_composite:['c1','c2']}]},strings).map(r=>r.id);
assert.deepEqual(order,['a','g','o1','o2','ha','hg','c1','c2']);
class Node {
  constructor(tag,text='') {this.tag=tag;this.textContent=text;this.children=[];this.attrs={};this.listeners={};this.classes=new Set();this.classList={toggle:(k,on)=>on?this.classes.add(k):this.classes.delete(k)};}
  appendChild(child){this.children.push(child);return child;}
  replaceChildren(...children){this.children=children;}
  setAttribute(k,v){this.attrs[k]=v;}
  removeAttribute(k){delete this.attrs[k];}
  getAttribute(k){return this.attrs[k];}
  addEventListener(k,fn){this.listeners[k]=fn;}
  allText(){return this.textContent+this.children.map(c=>c.allText()).join('');}
}
const events={};
const document={hidden:false,createDocumentFragment:()=>new Node('fragment'),createElement:t=>new Node(t),createTextNode:t=>new Node('text',t),addEventListener:(k,fn)=>events[k]=fn,removeEventListener:k=>delete events[k]};
const rendered=renderReadings(document,data.days.ru,data,strings,config.audio,choice);
assert.ok(rendered.allText().includes('<script>unsafe</script>'));
assert.equal(rendered.gospelAudio.playlist.length,2);
assert.ok(rendered.gospelAudio.playlist[0].url.includes('/52/01.mp3?api_key=public%2Bkey%26test'));
assert.ok(rendered.gospelAudio.playlist[1].url.includes('/42/01.mp3'));
assert.deepEqual(rendered.gospelAudio.controls.jumps.map(j=>j.index),[0,1]);
const missing=renderReadings(document,absent.days.ru,absent,strings,config.audio,choice);
assert.equal(missing.gospelAudio.playlist.length,1); assert.ok(missing.allText().includes('missing_text'));
const noAudio=structuredClone(data);noAudio.passages.a.audio.prudovsky=null;
assert.equal(renderReadings(document,noAudio.days.ru,noAudio,strings,config.audio,choice).gospelAudio.playlist.length,1);
const originalTimeout=global.setTimeout,originalClear=global.clearTimeout;
global.setTimeout=()=>1;global.clearTimeout=()=>{};
function rootFor(c){const nodes=Object.fromEntries(['config','status','readings','selectors','date'].map(k=>[`[data-gospel-${k}]`,new Node('div',k==='config'?JSON.stringify(c):'')]));return {nodes,querySelector:k=>nodes[k],nextElementSibling:{querySelector:()=>new Node('p')}};}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  let clock=new Date(2026,9,5,12),calls=[],saved=[];
  const root=rootFor(config);
  const client=mount(root,document,async url=>{calls.push(url);const match=url.match(/(\d{4})\/(\d{2}-\d{2})\/(\w+)\.json/);return {ok:true,json:async()=>daily(`${match[1]}-${match[2]}`,match[3])};},()=>clock,{getItem:()=>null,setItem:(key,value)=>saved.push([key,JSON.parse(value)])});
  await settle();assert.equal(calls[0],'/data/gospel-today/2026/10-05/syn.json');
  await client.refresh();assert.equal(calls.length,1);
  const selects=root.nodes['[data-gospel-selectors]'].children.map(l=>l.children[0]);
  selects[2].value='bondarenko';selects[2].listeners.change();await settle();assert.equal(calls.length,1);
  assert.deepEqual(saved[0],[STORAGE_KEY,['syn','bondarenko']]);
  selects[0].value='uk';selects[0].listeners.change();await settle();assert.equal(calls.at(-1),'/data/gospel-today/2026/10-05/ubh.json');
  assert.equal(root.nodes['[data-gospel-date]'].textContent,humanDate('2026-10-05','ru'));
  clock=new Date(2027,0,1,0);await client.refresh();assert.equal(calls.at(-1),'/data/gospel-today/2027/01-01/ubh.json');
  client.dispose();assert.equal(events.visibilitychange,undefined);
  const originalError=console.error;console.error=()=>{};
  const bad=rootFor(config);const badClient=mount(bad,document,async()=>({ok:false,status:404}),()=>clock,{getItem:()=>null,setItem:()=>{throw new Error('privacy');}});
  await settle();assert.equal(bad.nodes['[data-gospel-status]'].attrs.role,'alert');badClient.dispose();console.error=originalError;
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{global.setTimeout=originalTimeout;global.clearTimeout=originalClear;});
