(function(root){
 'use strict';
 function render(value,page,selected,format){
  const guests=value?.guests;
  if(!Array.isArray(guests))return '<section class="panel pve-list"><h2>Guest inventory unavailable</h2><p>'+(value?.status==='unconfigured'?'PVE is not configured yet':'Waiting for a complete PVE observation')+'</p></section>';
  const size=4,pages=Math.max(1,Math.ceil(guests.length/size)),current=Math.min(page,pages-1),rows=guests.slice(current*size,(current+1)*size);
  return `<section class="panel pve-list"><h2>Proxmox guests <span class="tag">${format.esc(value.provider.toUpperCase())} · ${value.fresh?'Fresh':'Stale'} · ${current+1} / ${pages}</span></h2><div class="pve-rows">${rows.map((guest,i)=>`<div class="pve-row ${current*size+i===selected?'selected':''}"><strong>${guest.type==='lxc'?'CT':'VM'} ${guest.vmid}</strong><span class="pve-name">${format.esc(guest.name)}</span><span>${format.esc(guest.status)}</span><span>CPU ${format.fmt(guest.cpu?.percent_total,'%')}</span><span class="pve-memory">RAM ${format.fmt(guest.memory?.ram?.percent,'%')} · ${format.bytes(guest.memory?.ram?.used)} / ${format.bytes(guest.memory?.ram?.total)} · PVE</span></div>`).join('')||'<p>No guests in the last complete inventory</p>'}</div></section>`;
 }
 root.PVEView={render};
})(window);
