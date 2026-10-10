import {$,$$,esc,money,date,state,api,me,toast,bindForm,orderCard,ticketsHTML,bindReplies,confirmation} from './common.js';
let data={products:[],orders:[],users:[],settings:{}},tickets=[];
const sections=['overview','products','orders','customers','tickets','settings'];
function route(){const name=sections.includes(location.hash.slice(1))?location.hash.slice(1):'overview';$$('[data-admin-view]').forEach(x=>x.hidden=x.dataset.adminView!==name);$$('.sidebar a').forEach(x=>x.classList.toggle('active',x.hash==='#'+name));window.scrollTo({top:0});}
function authUI(){
 const admin=state.user?.role==='admin';$('#adminShell').hidden=!admin;$('#adminAuth').hidden=admin;$('#adminLogout').hidden=!state.user;$('#adminName').textContent=state.user?state.user.nickname:'';$('#denied').hidden=!state.user||admin;
 const setup=state.setup_needed;$('#setupKeyField').hidden=!setup;$('#setupKeyField input').required=setup;$('#adminNicknameField').hidden=!setup;$('#adminNicknameField input').required=setup;$('#adminAuthTitle').textContent=setup?'首次设置管理员':'管理员登录';$('#adminAuthHelp').textContent=setup?'使用本机初始化码设置你自己的管理员账户。用户名和密码由你决定。':'只有管理员账户可以进入。普通用户请前往商城登录。';$('#adminAuthSubmit').textContent=setup?'创建管理员账户':'进入管理后台';$('#adminAuthForm [name="password"]').minLength=setup?10:1;$('#adminAuthForm [name="password"]').autocomplete=setup?'new-password':'current-password';
}
async function refresh(){
 if(state.user?.role!=='admin')return;
 [data,{tickets}]=await Promise.all([api('/api/admin'),api('/api/tickets')]);render();
}
function renderOrders(){const q=$('#adminOrderSearch').value.trim().toLowerCase(),status=$('#adminOrderStatus').value;const visible=data.orders.filter(o=>(status==='all'||o.status===status)&&(o.id+' '+o.username+' '+o.nickname).toLowerCase().includes(q));$('#adminOrders').innerHTML=visible.length?visible.map(o=>orderCard(o,true)).join(''):'<div class="empty"><h3>暂无匹配订单</h3><p>用户创建订单后会显示在这里。</p></div>';}
function render(){
 const simulated=data.orders.filter(o=>['paid','delivered','refund_requested'].includes(o.status)).reduce((s,o)=>s+o.total,0);
 $('#stats').innerHTML=[['上架商品',data.products.filter(p=>p.active).length],['待演示交付',data.orders.filter(o=>o.status==='paid').length],['待回复咨询',tickets.filter(t=>t.status==='open').length],['模拟成交金额',money(simulated)]].map(([title,value])=>`<div class="panel stat"><span class="muted tiny">${title}</span><strong>${value}</strong></div>`).join('');
 $('#recentOrders').innerHTML=data.orders.length?data.orders.slice(0,3).map(o=>orderCard(o,true)).join(''):'<div class="empty"><h3>还没有订单</h3><p>可以从用户端创建一笔模拟订单，体验处理流程。</p></div>';
 $('#productRows').innerHTML=data.products.map(p=>`<tr><td><b>${esc(p.name)}</b><p class="tiny muted">#${p.id} · ${p.ios?'iOS 美区':'通用'}</p></td><td>${money(p.cents)}</td><td>${esc(p.category.toUpperCase())}</td><td><span class="badge">${p.active?'已上架':'已下架'}</span></td><td><div class="row"><button class="secondary small" data-edit="${p.id}">编辑</button><button class="link-button tiny" data-toggle="${p.id}">${p.active?'下架':'上架'}</button></div></td></tr>`).join('');
 $('#customerRows').innerHTML=data.users.map(u=>`<tr><td><b>${esc(u.username)}</b><p class="tiny muted">${esc(u.nickname)}</p></td><td>${u.role==='admin'?'管理员':'用户'}</td><td>${date(u.created)}</td><td>${data.orders.filter(o=>o.user_id===u.id).length}</td></tr>`).join('');
 $('#adminTickets').innerHTML=ticketsHTML(tickets);
 for(const [k,v] of Object.entries(data.settings)){$(`#settingsForm [name="${k}"]`).value=v;}
 renderOrders();
}
function editProduct(id){const p=data.products.find(p=>p.id===id);const f=$('#productForm');f.reset();$('.form-error',f).textContent='';f.elements.id.value=p?.id||'';$('#editProductTitle').textContent=p?'编辑商品':'添加商品';for(const key of ['name','category','ios','active','description']){if(p)f.elements[key].value=p[key];}f.elements.price.value=p?(p.cents/100).toFixed(2):'';$('#editProductDialog').showModal();}
bindForm('#adminAuthForm',async values=>{await api(state.setup_needed?'/api/setup':'/api/login',values);await me();authUI();if(state.user?.role!=='admin')throw Error('该账户没有管理员权限');$('#adminAuthForm').reset();await refresh();route();toast('已进入管理后台');});
$('#adminLogout').onclick=async()=>{try{await api('/api/logout',{});await me();data={products:[],orders:[],users:[],settings:{}};tickets=[];authUI();toast('已退出管理后台');}catch(e){toast(e.message,true);}};
bindForm('#productForm',async values=>{const price=Number(values.price);if(!Number.isFinite(price)||price<=0)throw Error('请输入有效价格');await api('/api/admin/product',{id:values.id?Number(values.id):null,name:values.name,cents:Math.round(price*100),category:values.category,ios:Number(values.ios),active:Number(values.active),description:values.description});$('#editProductDialog').close();await refresh();toast('商品已保存，用户端刷新即可看到');});
bindForm('#deliveryForm',async values=>{await api('/api/admin/order',{id:values.id,action:'deliver',note:values.note});$('#deliveryDialog').close();await refresh();toast('演示交付已记录，用户可查看说明');});
bindForm('#settingsForm',async values=>{await api('/api/admin/settings',values);await refresh();toast('商城设置已保存');});
bindForm('#adminPasswordForm',async(values,form)=>{await api('/api/password',values);await me();form.reset();toast('管理员密码已更新，其他会话已退出');});
bindReplies($('#adminTickets'),refresh);
$('#newProduct').onclick=()=>editProduct(null);
$('#adminOrderSearch').oninput=renderOrders;$('#adminOrderStatus').onchange=renderOrders;
document.addEventListener('click',async e=>{const b=e.target.closest('[data-close],[data-edit],[data-toggle],[data-order],[data-refresh]');if(!b)return;if(b.dataset.close){$('#'+b.dataset.close).close();return;}if(b.dataset.edit){editProduct(Number(b.dataset.edit));return;}b.disabled=true;try{
 if(b.hasAttribute('data-refresh')){await refresh();toast('数据已更新');}
 if(b.dataset.toggle){const p=data.products.find(x=>x.id===Number(b.dataset.toggle));if(!await confirmation(p.active?'下架商品':'上架商品',p.active?'下架后用户端不再展示此商品，历史订单不受影响。':'上架后此商品将显示在用户端。'))return;await api('/api/admin/product',{...p,active:p.active?0:1});await refresh();toast('商品状态已更新');}
 if(b.dataset.order==='deliver'){const f=$('#deliveryForm');f.reset();$('.form-error',f).textContent='';f.elements.id.value=b.dataset.id;$('#deliveryDialog').showModal();}
 if(b.dataset.order==='refund'){if(!await confirmation('确认模拟退款','订单将标记为已模拟退款，不发生任何真实资金变动。','确认模拟退款'))return;await api('/api/admin/order',{id:b.dataset.id,action:'refund'});await refresh();toast('模拟退款已完成');}
 }catch(err){toast(err.message,true);if(err.status===401||err.status===403){await me();authUI();}}finally{b.disabled=false;}});
window.addEventListener('hashchange',route);
async function start(){try{await me();authUI();await refresh();route();}catch(e){toast('无法连接后台：'+e.message,true);}}
start();
