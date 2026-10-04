'use strict';
const assert=require('node:assert/strict');
const {calculate,calendar,chapterTotal,scopeBooks,dailyMinutes,date}=require('../static/bible-garden/js/reading-time.js');
const units={verse:{count:10,seconds:80},paragraph:{count:2,seconds:90},section:{count:1,seconds:95},chapter:{count:1,seconds:98}};
const data={books:[{id:1,chapters:2},{id:40,chapters:3}],voices:{a:{books:{1:{chapters:2,seconds:100,units}}},b:{books:{1:{chapters:2,seconds:200,units}}}}};
const base={scope:'bible',voice:'a',speed:2,pause_unit:'verse',pause:2,multi:false};
assert.equal(calculate(data,{voice:''}),null);
assert.equal(calculate(data,base).minutes_per_chapter,70/2/60);
assert.deepEqual(calculate(data,base).missing,[40]);
assert.equal(calculate(data,base).recorded,2);
assert.equal(calculate(data,{...base,pause_unit:'none'}).minutes_per_chapter,50/2/60);
assert.equal(calculate(data,{...base,multi:true,voice_b:'b',speed_b:1,unit:'verse'}).minutes_per_chapter,160/2/60);
assert.equal(chapterTotal(data,'bible'),5);
assert.equal(chapterTotal(data,'ot'),2);
assert.equal(chapterTotal(data,'nt'),3);
assert.throws(()=>scopeBooks(data,'book'));
for (const speed of [.5,1.1,2.1,NaN]) assert.throws(()=>calculate(data,{...base,speed}));
assert.throws(()=>calculate(data,{...base,pause:61}));
assert.throws(()=>calculate(data,{...base,voice:'missing'}));
assert.deepEqual(calendar(10,'2026-10-04','chapters',3),{chapters:3,days:4,finish:'2026-10-07'});
assert.deepEqual(calendar(10,'2026-10-04','finish','2026-10-09'),{chapters:2,days:5,finish:'2026-10-08'});
assert.equal(calendar(1189,'2026-10-04','chapters',50).days,24);
assert.equal(calendar(3,'2024-02-28','chapters',1).finish,'2024-03-01');
assert.equal(calendar(3,'2026-03-28','chapters',1).finish,'2026-03-30');
assert.equal(calendar(1189,'2026-10-04','finish','2026-10-04').chapters,1189);
for (const chapters of [0,-1,1.5,NaN]) assert.throws(()=>calendar(1189,'2026-10-04','chapters',chapters));
assert.throws(()=>calendar(1189,'2026-10-04','finish','2026-10-03'));
assert.throws(()=>date('2026-02-29'));
assert.throws(()=>calendar(3,'9999-12-31','chapters',1));
const real=JSON.parse(require('node:fs').readFileSync(require('node:path').join(__dirname,'../content/bible-garden/calculator/reading-time.json'),'utf8'));
assert.deepEqual(['bible','ot','nt'].map((scope)=>chapterTotal(real,scope)),[1189,929,260]);
const plan=calendar(chapterTotal(real,'bible'),'2026-10-04','chapters',3);
for (const voice of ['prudovsky','bondarenko','npu_uk']) {
 const audio=calculate(real,{...base,speed:1,pause_unit:'none',voice});
 assert.ok(audio.minutes_per_chapter>0);
 assert.deepEqual(calendar(chapterTotal(real,'bible'),'2026-10-04','chapters',3),plan);
}
assert.equal(calculate(real,{...base,voice:'bondarenko'}).recorded,1050);
assert.equal(calculate(real,{...base,voice:'npu_uk'}).recorded,410);

assert.equal(dailyMinutes({minutes_per_chapter:2},1000,260),520);
assert.equal(dailyMinutes({minutes_per_chapter:2},3,260),6);
assert.equal(dailyMinutes({minutes_per_chapter:2},1000,929),1858);

const ntAudio=calculate(real,{...base,scope:'nt',voice:'bsb_souer',speed:1,pause_unit:'none'});
const ntSeconds=Object.entries(real.voices.bsb_souer.books).filter(([book])=>Number(book)>=40).reduce((sum,[_book,info])=>sum+info.seconds,0);
assert.equal(dailyMinutes(ntAudio,1000,chapterTotal(real,'nt')),Math.round(ntSeconds/60));
