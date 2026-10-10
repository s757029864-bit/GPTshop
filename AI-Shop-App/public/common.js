export const $ = (s, root=document) => root.querySelector(s);
export const $$ = (s, root=document) => [...root.querySelectorAll(s)];
export const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const money = n => '¥'+(n/100).toFixed(2);
export const date = n => new Date(n*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
export const labels = {pending:'待模拟支付',paid:'已模拟支付 · 待交付',delivered:'已记录演示交付',cancelled:'已取消',refund_requested:'模拟退款申请中',refunded:'已模拟退款'};
export const state = {user:null,csrf:null,setup_needed:false};
export async function api(url,body){
  const response=await fetch(url,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':state.csrf||''},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok){const error=new Error(data.error||'请求失败');error.status=response.status;throw error;}
  return data;
}
export async function me(){Object.assign(state,await api('/api/me'));return state;}
export function toast(message,bad=false){const box=$('#toast');box.textContent=message;box.classList.toggle('error',bad);box.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>box.hidden=true,6000);}
export function bindForm(selector,action){
  $(selector).addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter||$('button[type="submit"]',e.target);if(button)button.disabled=true;const error=$('.form-error',e.target);if(error)error.textContent='';
    try{await action(Object.fromEntries(new FormData(e.target)),e.target);}catch(err){if(error)error.textContent=err.message;toast(err.message,true);}finally{if(button)button.disabled=false;}
  });
}
export function orderCard(o,admin=false){
  const actions=admin ? `${o.status==='paid'?`<button class="primary small" data-order="deliver" data-id="${esc(o.id)}">记录演示交付</button>`:''}${['paid','delivered','refund_requested'].includes(o.status)?`<button class="secondary small" data-order="refund" data-id="${esc(o.id)}">模拟退款</button>`:''}` : `${o.status==='pending'?`<button class="primary small" data-order="pay" data-id="${esc(o.id)}">模拟支付</button><button class="secondary small" data-order="cancel" data-id="${esc(o.id)}">取消订单</button>`:''}${['paid','delivered'].includes(o.status)?`<button class="secondary small" data-order="request_refund" data-id="${esc(o.id)}">申请模拟退款</button>`:''}`;
  return `<article class="panel order"><div class="row between wrap-row"><div><b>${esc(o.id)}</b><p class="muted tiny">${date(o.created)}${admin?' · '+esc(o.nickname)+'（'+esc(o.username)+'）':''}</p></div><span class="badge ${esc(o.status)}">${labels[o.status]}</span></div><div class="order-items">${o.items.map(p=>`<div class="row between"><span>${esc(p.name)} × ${p.qty}</span><span>${money(p.cents*p.qty)}</span></div>`).join('')}</div><div class="row between wrap-row"><strong>合计 ${money(o.total)}</strong><div class="row wrap-row">${actions}</div></div>${o.note?`<div class="delivery"><b>演示交付说明</b><p class="pre">${esc(o.note)}</p></div>`:''}<details><summary>订单进度</summary>${o.events.map(e=>`<p class="tiny">${date(e.created)} · ${esc(e.message)}</p>`).join('')}</details></article>`;
}
export function ticketsHTML(tickets){return tickets.length?tickets.map(t=>`<article class="panel ticket"><div class="row between wrap-row"><h3>#${t.id} ${esc(t.subject)}</h3><span class="badge">${t.status==='answered'?'商家已回复':'待商家回复'}</span></div><p class="tiny muted">${esc(t.nickname)} · ${date(t.created)}</p>${t.messages.map(m=>`<div class="ticket-message ${m.sender==='admin'?'from-admin':''}"><b>${m.sender==='admin'?'商家':'用户'}</b> <span class="tiny muted">${date(m.created)}</span><p class="pre">${esc(m.body)}</p></div>`).join('')}<form class="reply-form" data-id="${t.id}"><label>继续留言<textarea name="body" required maxlength="2000" rows="2" placeholder="请勿提交账户密码或支付密钥"></textarea></label><button class="secondary small" type="submit">发送留言</button></form></article>`).join(''):'<div class="empty"><span>✉</span><h3>暂无咨询记录</h3><p>提交问题后，可以在这里查看商家的回复。</p></div>';}
export function bindReplies(root,refresh){root.addEventListener('submit',async e=>{if(!e.target.matches('.reply-form'))return;e.preventDefault();const button=$('button',e.target);button.disabled=true;try{await api('/api/tickets/reply',{id:Number(e.target.dataset.id),body:new FormData(e.target).get('body')});await refresh();toast('留言已发送');}catch(err){toast(err.message,true);}finally{button.disabled=false;}});}
export function confirmation(title,message,confirmText='确认'){return new Promise(resolve=>{const d=$('#confirmDialog');$('#confirmTitle').textContent=title;$('#confirmMessage').textContent=message;$('#confirmYes').textContent=confirmText;d.returnValue='cancel';d.addEventListener('close',()=>resolve(d.returnValue==='ok'),{once:true});d.showModal();});}
