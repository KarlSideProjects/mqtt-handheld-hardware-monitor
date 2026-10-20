// Run: node browser/test_monitor_ui.cjs
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'monitor.html'), 'utf8')
  .split('<script>')[1].split('let updating=false;')[0];
const pve = fs.readFileSync(path.join(__dirname, 'pve.js'), 'utf8');
const context = {};
context.window = context;
vm.runInNewContext(pve, context);
vm.runInNewContext(source + `
if (esc('<script>') !== '&lt;script&gt;') throw Error('Unsafe host');
if (fmt(null, '%') !== '—') throw Error('Missing metric shown as zero');
let sample = {host: '<test>', metrics: {cpu: 42, gpu: null, ram: 60,
 cpu_temp: 55, gpu_temp: null, cores: Array(32).fill(42), gpus: [], disks: {},
 network: {}, temperatures: {}}, history: [{cpu: 42, gpu: null, ram: 60}]};
let html = overview(sample, '<test>');
if (html.includes('<test>') || !html.includes('&lt;test&gt;')) throw Error('Unsafe overview');
let ranked=busiest([10,99,null,30,80,5,70,NaN]);
if(ranked.map(c=>c.index).join(',')!=='1,4,6,3') throw Error('Busiest core ranking');
if(busiest(Array(32).fill(42)).length!==4 || detail(sample).includes('C32 42.0%') || detail(sample).includes('class="gauge"') || !detail(sample).includes('class="reading"')) throw Error('Compact CPU detail');
for(const label of ['CPU','GPU','Memory','Network','Disk I/O','Temperatures','Activity trails']) if(!detail(sample).includes(label)) throw Error('Missing detail category '+label);
if(busiest([null,undefined,NaN]).length) throw Error('Unknown cores ranked as zero');
if(gauge(null,'#fff','GPU').includes('NaN') || bar(-5,'#fff').includes('width:-')) throw Error('Invalid graphical metric');
if (graph([{cpu: null}, {cpu: 42}], 'cpu', '#fff').includes('NaN')) throw Error('Invalid graph');
let gpu = {memory_used_mb: 11348, memory_total_mb: 16380, memory_percent: 69.3};
if(vram(gpu)!=='11.1 / 16.0 GiB' || vramPercent(gpu)!=='69.3%') throw Error('Wrong VRAM units');
if(vram({memory_total_mb:0,memory_percent:0})!=='—' || vramPercent({memory_total_mb:0,memory_percent:0})!=='—') throw Error('Unknown VRAM shown as zero');
if(vram({memory_percent:42})!=='42.0%') throw Error('Percent-only sender unsupported');
if(!gpuCard({...gpu,name:'<gpu>',usage_percent:50},0).includes('&lt;gpu&gt;') || !gpuCard(gpu,0).includes('69.3%')) throw Error('Unsafe or incomplete GPU instrument');
if(mainVram([gpu,{memory_total_mb:0}])!==gpu) throw Error('Wrong overview GPU');
sample.metrics.gpus=[{usage_percent:20,memory_used_mb:8192,memory_total_mb:16384},{usage_percent:95,memory_used_mb:1024,memory_total_mb:4096}];
if(!detail(sample).includes('1.0 / 4.0 GiB') || !detail(sample).includes('8.0 / 16.0 GiB') || !detail(sample).includes('95.0%') || !detail(sample).includes('20.0%')) throw Error('Per-GPU load or VRAM missing');
if(!flowReading('Read',2**31).includes('GiB/s') || flowReading('Read',null).includes('NaN')) throw Error('Invalid flow units or missing data');
let guest={type:'qemu',vmid:100,name:'<img src=x>',status:'running',vcpus:2,cpu:{percent_total:25},memory:{ram:{percent:25,used:536870912,total:2147483648}},network_io:{total:{rate:{rx_bytes_per_s:1048576,tx_bytes_per_s:null}}},disk_io:{total:{rate:{read_bytes_per_s:512,write_bytes_per_s:null}}},history:[{cpu:null,ram:25,rx:null,tx:null,read:null,write:null},{cpu:25,ram:25,rx:1048576,tx:null,read:512,write:null}]};
let guestHtml=PVEView.render({provider:'pve',fresh:true,guests:[guest]},0,0,{esc,fmt,bytes});
if(guestHtml.includes('<img') || !guestHtml.includes('&lt;img') || !guestHtml.includes('VM 100') || !guestHtml.includes('PVE')) throw Error('Unsafe or incomplete PVE guest list');
let guestDetail=PVEView.render({provider:'pve',fresh:true,guests:[guest]},0,0,{esc,fmt,bytes,rate,graph},true);
if(guestDetail.includes('<img') || !guestDetail.includes('&lt;img') || !guestDetail.includes('vCPU') || !guestDetail.includes('<strong>2</strong>') || !guestDetail.includes('PVE statistics') || !guestDetail.includes('1.00 MiB/s') || guestDetail.includes('NaN')) throw Error('Unsafe or incomplete PVE guest detail');
guest.history=[{cpu:20},{cpu:null},{cpu:40}];
guestDetail=PVEView.render({provider:'pve',fresh:true,guests:[guest]},0,0,{esc,fmt,bytes,rate,graph},true);
if((guestDetail.match(/<polyline/g)||[]).length!==2) throw Error('Unknown trend gaps were connected');
if(!PVEView.render({status:'error'},0,0,{esc,fmt,bytes}).includes('Guest inventory unavailable')) throw Error('Missing PVE unknown inventory state');
if(!PVEView.render({status:'unconfigured'},0,0,{esc,fmt,bytes}).includes('not configured yet')) throw Error('Missing PVE setup state');
`, context);
console.log('PASS: host escaping, missing metrics, top 4 of 32 cores, all metric categories, sparse history, VRAM');
