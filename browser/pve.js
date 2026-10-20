(function(root){
 'use strict';
 function statusBadge(status){
  const states={running:['on','ON','Running'],stopped:['off','OFF','Stopped'],exited:['off','OFF','Exited'],dead:['off','DEAD','Dead'],created:['off','NEW','Created'],restarting:['paused','RESTART','Restarting'],removing:['paused','REMOVE','Removing'],paused:['paused','PAUSED','Suspended'],suspended:['paused','PAUSED','Suspended']};
  const state=Object.prototype.hasOwnProperty.call(states,status)?states[status]:['unknown','UNKNOWN','Unknown'];
  return `<span class="pve-state pve-state-${state[0]}"><b>${state[1]}</b><span>${state[2]}</span></span>`;
 }
 function identity(guest){return guest.type==='docker'?(guest.container_id??'').slice(0,12):(guest.type==='lxc'?'CT':'VM')+' '+guest.vmid}
 function detail(guest,format){
  const docker=guest.type==='docker',basis=docker?'Cache excluded':'PVE statistics';
  const ram=guest.memory?.ram??{},network=guest.network_io?.total?.rate??{},disk=guest.disk_io?.total?.rate??{},history=guest.history??[];
  const reading=(label,value,suffix='')=>`<div class="pve-reading"><small>${label}</small><strong>${format.fmt(value,suffix)}</strong></div>`;
  const flow=(label,value)=>`<div class="pve-reading"><small>${label}</small><strong>${format.rate(value)}</strong></div>`;
  const trail=(label,key,color,limit=100)=>`<div class="pve-trend"><small>${label}</small>${format.graph(history,key,color,limit)}</div>`;
  return `<section class="panel pve-detail"><h2><span class="pve-title">${docker?'Docker ':''}${format.esc(identity(guest))} · ${format.esc(guest.name)}</span>${statusBadge(guest.status)}</h2><div class="pve-readings">${reading('CPU',guest.cpu?.percent_total,'%')}<div class="pve-reading ${docker?'docker-identity':''}"><small>${docker?'Container ID':'vCPU'}</small><strong>${docker?format.esc(identity(guest)):Number.isInteger(guest.vcpus)?guest.vcpus:'—'}</strong></div><div class="pve-reading pve-memory-reading"><small>RAM · ${basis}</small><strong>${format.fmt(ram.percent,'%')} · ${format.bytes(ram.used)} / ${format.bytes(ram.total)}</strong></div>${flow('Network receive',network.rx_bytes_per_s)}${flow('Network send',network.tx_bytes_per_s)}${flow('Disk read',disk.read_bytes_per_s)}${flow('Disk write',disk.write_bytes_per_s)}</div><div class="pve-trends">${trail('CPU','cpu','#4b91c9',docker?null:100)}${trail(docker?'RAM · Docker':'RAM · PVE','ram','#379d7a')}${trail('Network receive','rx','#9860bd',null)}${trail('Network send','tx','#9860bd',null)}${trail('Disk read','read','#cf8541',null)}${trail('Disk write','write','#cf8541',null)}</div></section>`;
 }
 function render(value,page,selected,format,guestDetail=false){
  const guests=value?.guests,docker=value?.provider==='docker',label=docker?'Docker containers':'Proxmox guests';
  if(!Array.isArray(guests))return '<section class="panel pve-list"><h2>Guest inventory unavailable</h2><p>'+(value?.status==='unconfigured'?'PVE is not configured yet':docker?'Waiting for a complete Docker observation':'Waiting for a complete PVE observation')+'</p></section>';
  if(guestDetail&&guests[selected])return detail(guests[selected],format);
  const size=4,pages=Math.max(1,Math.ceil(guests.length/size)),current=Math.min(page,pages-1),rows=guests.slice(current*size,(current+1)*size);
  return `<section class="panel pve-list"><h2>${label} <span class="tag">${format.esc(value.provider.toUpperCase())} · ${value.fresh?'Fresh':'Stale'} · ${current+1} / ${pages}</span></h2><div class="pve-rows">${rows.map((guest,i)=>`<div class="pve-row ${current*size+i===selected?'selected':''}"><strong class="${docker?'docker-id':''}">${format.esc(identity(guest))}</strong><span class="pve-name">${format.esc(guest.name)}</span>${statusBadge(guest.status)}<span>CPU ${format.fmt(guest.cpu?.percent_total,'%')}</span><span class="pve-memory">RAM ${format.fmt(guest.memory?.ram?.percent,'%')} · ${format.bytes(guest.memory?.ram?.used)} / ${format.bytes(guest.memory?.ram?.total)} · ${docker?'Docker':'PVE'}</span></div>`).join('')||`<p>No ${docker?'containers':'guests'} in the last complete inventory</p>`}</div></section>`;
 }
 root.PVEView={render};
})(window);
