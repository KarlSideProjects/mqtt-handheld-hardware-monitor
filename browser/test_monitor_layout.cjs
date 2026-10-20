// Run with Playwright available: node browser/test_monitor_layout.cjs
const {chromium}=require('playwright');
const fs=require('node:fs'), path=require('node:path'), http=require('node:http'), assert=require('node:assert/strict');
const root=__dirname;
const actual=process.env.MONITOR_SAMPLE?JSON.parse(fs.readFileSync(process.env.MONITOR_SAMPLE,'utf8')):null;
const host={host:'DB795i',metrics:{cpu:42,gpu:75,ram:65,cpu_temp:66,gpu_temp:62,
 cores:Array.from({length:32},(_,i)=>i*3),ram_used:21*2**30,ram_total:32*2**30,swap:3,
 gpus:[{name:'GPU 1',usage_percent:75,temperature_celsius:62,memory_used_mb:11348,memory_total_mb:16380,memory_percent:69.3},{name:'GPU 2',usage_percent:20,temperature_celsius:58,memory_total_mb:0}],
 network:{per_nic:{eth0:{rate:{rx_bytes_per_s:4e6,tx_bytes_per_s:1e6}},wlan0:{rate:{rx_bytes_per_s:2e5,tx_bytes_per_s:1e5}}}},
 disks:{nvme0n1:{rate:{read_bytes_per_s:3e6,write_bytes_per_s:1e6,read_iops:42,write_iops:20}},sda:{rate:{read_bytes_per_s:1e6,write_bytes_per_s:0,read_iops:4,write_iops:0}}},
 temperatures:{cpu:[{label:'CPU',current:66},{label:'Package',current:64},{label:'NVMe',current:45}]},rx:4.2e6,tx:1.1e6,read:4e6,write:1e6},history:Array.from({length:60},(_,i)=>({cpu:i,gpu:i+10,ram:60,rx:2e6+i*1e4,tx:1e6,read:3e6,write:1e6}))};
const primaryGpu=structuredClone(host.metrics.gpus[0]);
let state={device:{cpu:50,memory:68,temperature:62,battery:42,charging:true,plugged:true,battery_status:'Charging'},connection:'Connected',count:3,page:1,pages:1,paused:true,detail:'DB795i',selected:'DB795i',hosts:[host]};
const listeners=new Set();
const server=http.createServer((req,res)=>{
 if(req.url==='/control'&&req.method==='POST'){let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{const action=JSON.parse(body).action;if(action.startsWith('focus:')){state.focus=action.slice(6);state.panel=state.focus;state.item_page=0}else if(action==='screen'){state.screen_off=!state.screen_off}else if(action==='up'||action==='down'){state.item_page=(state.item_page||0)+(action==='down'?1:-1)}else if(action==='back'){if(state.focus)state.focus=null;else state.detail=null}res.setHeader('Content-Type','application/json');res.end('{}');for(const stream of listeners)stream.write('data: '+JSON.stringify(state)+'\n\n')})}
 else if(req.url==='/status'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(state))}
 else if(req.url==='/events'){res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify(state)+'\n\n');listeners.add(res);req.on('close',()=>{listeners.delete(res);res.end()})}
 else if(req.url==='/assets/hardware-buddy.svg'){res.setHeader('Content-Type','image/svg+xml');res.end(fs.readFileSync(path.join(root,'assets/hardware-buddy.svg')))}
 else if(req.url==='/pve.js'){res.setHeader('Content-Type','application/javascript');res.end(fs.readFileSync(path.join(root,'pve.js')))}
 else res.end(fs.readFileSync(path.join(root,'monitor.html')))
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,args:['--disable-gpu']});
 try{
  const viewport=process.env.MONITOR_VIEWPORT?JSON.parse(process.env.MONITOR_VIEWPORT):{width:1024,height:768};
  const page=await browser.newPage({viewport});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('.distance-detail .reading').first().waitFor();
  await page.locator('#screen-button').click();await page.waitForFunction(()=>document.getElementById('screen-button').textContent==='FN Wake');assert.equal(state.screen_off,true);await page.locator('#screen-button').press('Enter');await page.waitForFunction(()=>document.getElementById('screen-button').textContent==='FN Screen off');assert.equal(state.screen_off,false);
  const devicePosition=await page.locator('#device-status').boundingBox();
  assert.equal(await page.locator('#charge-icon [aria-label=Charging]').count(),1);
  async function fits(){assert.deepEqual(await page.locator('#device-status').boundingBox(),devicePosition,'Local status moved between views');const overflow=await page.evaluate(()=>[...document.querySelectorAll('#device-status,#device-status>div,main,article,.metric,.panel,.item-card,footer,body')].filter(e=>e.scrollHeight>e.clientHeight+2||e.scrollWidth>e.clientWidth+2).map(e=>({tag:e.tagName,cls:e.className,h:e.clientHeight,sh:e.scrollHeight,w:e.clientWidth,sw:e.scrollWidth})));assert.deepEqual(overflow,[],'Screen content overflow: '+state.detail+' / '+state.focus)}
  state.device={...state.device,charging:false,battery:100,battery_status:'Full'};await page.reload();await page.locator('.distance-detail').waitFor();assert.ok((await page.locator('#charge-icon svg').getAttribute('aria-label')).includes('Fully charged'));state.device={...state.device,plugged:false,battery_status:'Discharging'};await page.reload();await page.locator('.distance-detail').waitFor();assert.equal(await page.locator('#charge-icon svg').count(),0);
  await fits();assert.equal(await page.locator('.distance-detail .reading').count(),4);assert.equal(await page.locator('.distance-detail svg').count(),0);assert.equal(await page.locator('.distance-detail .flow-value').count(),4);assert.ok(await page.locator('.reading').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=64));assert.ok(await page.locator('.flow-value').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=48));
  await page.locator('[data-section=cpu]').click();await page.locator('.focus-grid').waitFor();assert.equal(await page.locator('.cores .core').count(),4);assert.equal(state.focus,'cpu');await fits();await page.keyboard.press('Escape');await page.locator('.detail-grid').waitFor();await page.locator('[data-section=gpu]').click();await page.locator('.focus-gpus').waitFor();assert.equal(state.focus,'gpu');await fits();await page.keyboard.press('Escape');await page.locator('.detail-grid').waitFor();
  await page.screenshot({path:path.join(root,'comic-detail-preview.png')});
  const savedMetrics=structuredClone(host.metrics);
  Object.assign(host.metrics,{cpu:100,gpu:100,ram:100,cpu_temp:100,gpu_temp:100,rx:1023*2**20,tx:2**35,read:2**35,write:1023*2**20});
  await page.reload();await page.locator('.distance-detail').waitFor();await fits();Object.assign(host.metrics,savedMetrics);
  // All actual categories must fit for hosts with no GPU, two GPUs, and four GPUs.
  for(const count of [0,4]){state.hosts[0].metrics.gpus=Array.from({length:count},(_,i)=>({...primaryGpu,name:'GPU '+(i+1)}));await page.reload();await page.locator('.detail-grid').waitFor();await fits();assert.equal(await page.locator('.gpu-reading').count(),count)}
  for(const section of ['cpu','gpu','memory','network','disks','temperatures','history']){state.focus=section;await page.reload();await page.locator('main').waitFor();await page.waitForFunction(()=>document.getElementById('main').innerHTML.length>0);await fits();if(section==='cpu')await page.screenshot({path:path.join(root,'comic-cpu-preview.png')})}
  assert.ok(await page.locator('.focus-activity strong').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=32));
  state.focus='gpu';state.item_page=0;await page.reload();await page.locator('.focus-gpus').waitFor();assert.equal(await page.locator('.gpu-card').count(),2);assert.ok((await page.locator('.gpu-name').first().textContent()).includes('GPU 1'));await page.locator('.item-pager button').last().click();await page.waitForFunction(()=>document.querySelector('.gpu-name')?.textContent.includes('GPU 3'));await fits();assert.ok(await page.locator('.gpu-card .sensor').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=24));
  const savedNetwork=host.metrics.network;
  host.metrics.network={per_nic:Object.fromEntries(Array.from({length:17},(_,i)=>['nic'+i,{rate:{rx_bytes_per_s:17-i,tx_bytes_per_s:0}}]))};state.focus='network';state.item_page=0;await page.reload();await page.locator('.item-card').first().waitFor();assert.equal(await page.locator('.item-card').count(),4);assert.equal(await page.locator('.item-card h4').first().textContent(),'nic0');await page.locator('.item-pager button').first().click();await page.waitForFunction(()=>document.querySelector('.item-card h4')?.textContent==='nic16');assert.equal(await page.locator('.item-card').count(),1);await fits();host.metrics.network=savedNetwork;state.item_page=0;
  state.focus=null;
  state.hosts[0].metrics.gpus=[{usage_percent:75,temperature_celsius:62,memory_used_mb:11348,memory_total_mb:16380,memory_percent:69.3}];state.detail=null;state.hosts=Array.from({length:3},(_,i)=>({...host,host:['pve','n100pve','DB795i'][i]}));state.selected='n100pve';await page.reload();await page.locator('article').first().waitFor();await fits();
  await page.screenshot({path:path.join(root,'comic-overview-preview.png')});
  assert.ok(await page.locator('h2').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=30));assert.ok(await page.locator('.metric small').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=20));
  for(const count of [0,2,4]){for(const h of state.hosts)h.metrics.gpus=Array.from({length:count},(_,i)=>({...primaryGpu,usage_percent:100,name:'GPU '+i}));await page.reload();await page.locator('article').first().waitFor();await fits();assert.equal(await page.locator('.overview-gpu-row').count(),count*3)}
  const pveHost={...host,host:'pve-node-a',virtualization:{provider:'pve',status:'ok',fresh:true,guest_count:5,guests:Array.from({length:5},(_,i)=>({id:'lab:qemu:'+ (100+i),type:'qemu',vmid:100+i,name:'guest-'+(100+i),status:i?'stopped':'running',cpu:{percent_total:i?null:25},memory:{ram:{percent:i?null:25,used:i?null:536870912,total:2147483648}}}))}};
  state.hosts=[pveHost];state.selected='pve-node-a';state.detail=null;state.focus=null;await page.reload();await page.locator('article').first().waitFor();await fits();assert.ok((await page.locator('.host-caption').textContent()).includes('PVE 5'));
  state.detail='pve-node-a';state.panel='pve';await page.reload();await page.locator('.pve-entry').waitFor();await fits();assert.equal(await page.locator('.detail-grid>.panel').count(),8);assert.ok(await page.locator('.pve-entry').evaluate(e=>e.classList.contains('selected')));
  state.pve_view='guests';state.pve_page=0;state.pve_selected=0;await page.reload();await page.locator('.pve-row').first().waitFor();await fits();assert.equal(await page.locator('.pve-row').count(),4);assert.ok((await page.locator('.pve-row').first().textContent()).includes('VM 100'));const ram=page.locator('.pve-memory').first();assert.equal((await ram.textContent()).trim(),'RAM 25.0% · 0.5 GiB / 2.0 GiB · PVE');const ramBox=await ram.evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth,overflow:getComputedStyle(e).textOverflow}));assert.ok(ramBox.width>0&&ramBox.scroll<=ramBox.width+1&&ramBox.overflow!=='ellipsis',`PVE RAM text clipped: ${JSON.stringify(ramBox)}`);
  state.pve_page=1;state.pve_selected=4;await page.reload();await page.locator('.pve-row').first().waitFor();await fits();assert.equal(await page.locator('.pve-row').count(),1);assert.ok((await page.locator('.pve-row').first().textContent()).includes('guest-104'));
  if(actual){for(const item of actual.hosts){state.detail=item.host;state.hosts=[item];state.selected=item.host;await page.reload();await page.locator('.detail-grid').waitFor();await fits();for(const section of ['cpu','gpu','memory','network','disks','temperatures','history']){state.focus=section;await page.reload();await page.waitForFunction(()=>document.getElementById('main').innerHTML.length>0);await fits()}state.focus=null}}
  assert.deepEqual(errors,[]);console.log(`PASS: ${viewport.width}×${viewport.height}, no scrolling or clipping, distance readings 64/48px, drill-down cores, 0/2/4 GPUs, three-host overview`);
 }finally{await browser.close();server.closeAllConnections();server.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
