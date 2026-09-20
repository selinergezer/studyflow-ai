// Run with NOTEBOOK_TEST_TOOLS pointing to a temporary playwright/esbuild install.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const frontend = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(path.join(process.env.NOTEBOOK_TEST_TOOLS ?? frontend, 'package.json'));
const {build} = require('esbuild');
const {chromium} = require('playwright');
const bundle = await build({stdin:{resolveDir:frontend,loader:'tsx',contents:`
import React from 'react'; import {createRoot} from 'react-dom/client';
import QuizPanel from './components/documents/QuizPanel';
import CourseWorkspace from './components/courses/CourseWorkspace';
import {LanguageProvider} from './providers/LanguageProvider';
const root = createRoot(document.getElementById('root'));
window.mount = (course=false) => root.render(<LanguageProvider>{course ? <CourseWorkspace courseId={1}/> : <QuizPanel documentId="10"/>}</LanguageProvider>);
window.unmount = () => root.unmount(); window.mount(window.courseMode);
`},jsx:"automatic",bundle:true,write:false,tsconfig:path.join(frontend,'tsconfig.json'),define:{'process.env':'{}','process.env.NODE_ENV':'"development"','process.env.NEXT_PUBLIC_API_URL':'"http://ui.test"','process.env.NEXT_PUBLIC_API_TIMING':'"false"'}});
const browser=await chromium.launch({headless:true});
try {
 for (const courseMode of [false,true]) {
  const page=await browser.newPage();
  page.on("pageerror", error => console.error(error.message));
  await page.route('http://ui.test/',r=>r.fulfill({contentType:'text/html',body:'<div id="root"></div>'}));
  await page.goto('http://ui.test/');
  await page.evaluate((mode)=>{
   window.courseMode=mode; localStorage.setItem('access_token','synthetic'); window.calls=[]; window.deleteError=false;
   window.fetch=async (url,init={})=>{
    window.calls.push({url:String(url),method:init.method??'GET'});
    const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
    if(String(url).includes('/generate/stream')) return new Response(new ReadableStream({start(c){window.stream=c; init.signal.addEventListener('abort',()=>{window.aborted=true;try{c.error(new DOMException('Aborted','AbortError'));}catch{}});}}));
    if(init.method==='DELETE') return json({detail:'Silme başarısız'},window.deleteError?500:200);
    if(String(url).endsWith('/courses/'))return json([{id:1,name:'Test kurs'}]);
    if(String(url).endsWith('/documents/'))return json([{id:10,course_id:1,filename:'test.pdf',page_count:144}]);
    return json({id:42,document_id:10,questions:Array.from({length:5},(_,i)=>({id:i+1,question_text:'Soru '+(i+1),option_a:'A',option_b:'B'}))});
   };
   window.send=(event,data)=>window.stream.enqueue(new TextEncoder().encode('event: '+event+'\ndata: '+JSON.stringify(data)+'\n\n'));
  },courseMode);
  await page.addScriptTag({content:bundle.outputFiles[0].text});
  if(!courseMode){
   await page.getByRole('button',{name:'5',exact:true}).click();
   const start=page.getByRole('button',{name:/Sınavı Oluştur/});
   await start.evaluate(b=>{b.click();b.click();});
   assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.url.includes('/generate/stream')).length),1);
   await page.getByText('0 / 5 soru hazırlandı',{exact:true}).waitFor();
   for(let i=1;i<=2;i++){
    await page.evaluate(i=>window.send('question',{index:i,question_text:'Soru '+i,option_a:'A',option_b:'B'}),i);
    await page.getByText('Sınav hazırlanıyor... '+i+'/5',{exact:true}).waitFor();
   }
   await page.evaluate(()=>window.send('error',{message:'Test retry'}));
   await page.getByRole('alert').filter({hasText:'Test retry'}).waitFor();
   await start.click();
   assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.url.includes('/generate/stream')).length),2);
   for(let i=1;i<=5;i++)await page.evaluate(i=>window.send('question',{index:i,question_text:'Soru '+i,option_a:'A',option_b:'B'}),i);
   await page.evaluate(()=>{window.send('done',{quiz_id:42});window.stream.close();});
   await page.getByRole('heading',{name:'Soru 1',exact:true}).waitFor();
   await page.waitForFunction(()=>window.calls.some(c=>c.url.endsWith('/quizzes/42')));
   console.log('PASS accepted-only progress, duplicate click, error retry, completion');
  }else{
   const del=page.getByRole('button',{name:'test.pdf — Sil'});
   await del.waitFor();
   page.once('dialog',d=>d.dismiss());await del.click();
   assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.method==='DELETE').length),0);
   await page.evaluate(()=>window.deleteError=true);
   page.once('dialog',d=>d.accept());await del.click();
   await page.getByRole('alert').waitFor();assert.equal(await del.count(),1);
   assert.equal(page.url(),'http://ui.test/');
   await page.evaluate(()=>window.deleteError=false);
   page.once('dialog',d=>d.accept());await del.click();
   await del.waitFor({state:'detached'});
   assert.equal(await page.locator('.course-workspace-stat strong').textContent(),'0');
   assert.equal(page.url(),'http://ui.test/');
   console.log('PASS delete cancel, error retention, success removal/count, no navigation');
  }
  await page.close();
 }
}finally{await browser.close();}
