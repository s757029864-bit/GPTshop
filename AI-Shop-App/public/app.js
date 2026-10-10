import {$,$$,esc,money,date,labels,state,api,me,toast,bindForm,orderCard,ticketsHTML,bindReplies,confirmation} from './common.js';
let products=[],settings={},cart=[],orders=[],filter='all',orderFilter='all',authMode='login',returnTo='',checkoutKey=null;
const viewNames=['home','shop','cart','orders','support','account'];
const view=()=>viewNames.includes(location.hash.slice(1))?location.hash.slice(1):'home';
function empty(title,description,link='#shop',label='浏览商品'){return `<div class="empty"><span>◇</span><h3>${esc(title)}</h3><p>${esc(description)}</p><a class="primary" href="${link}">${label}</a></div>`;}
function loginHint(message){return empty('登录后继续',message,'#account','登录 / 注册');}
function requireLogin(target){if(state.user)return true;returnTo=target;location.hash='account';toast('请先登录或注册，完成后将返回当前页面');return false;}
function card(p){return `<article class="product"><a href="#product-${p.id}" class="product-image" data-detail="${p.id}"><img src="/assets/ai-hero.png" alt="AI 数字服务示意图" loading="lazy"><span class="badge">${p.ios?'iOS 美区':p.category==='other'?'数字服务':p.category.toUpperCase()}</span></a><h3><a href="#product-${p.id}" data-detail="${p.id}">${esc(p.name)}</a></h3><span class="tiny muted">展示套餐 · 仅供模拟体验</span><div class="price-row row between"><span class="price">${money(p.cents)}</span><span class="tiny muted">展示价</span></div><div class="product-actions"><button class="primary" data-add="${p.id}">加入购物车</button><button class="secondary" data-detail="${p.id}">详情</button></div></article>`;}
async function catalog(){({products,settings}=await api('/api/catalog'));$$('[data-site-name]').forEach(x=>x.textContent=settings.site_name);$('#announcement').textContent=settings.announcement;$('#supportHours').textContent=settings.support_hours;renderProducts();}
function renderProducts(){
 $('#homeProducts').innerHTML=products.length?products.map(card).join(''):empty('商品准备中','商家正在更新商品，请稍后查看。');
 let q=$('#search').value.trim().toLowerCase();let visible=products.filter(p=>(p.name+' '+p.description).toLowerCase().includes(q)&&(filter==='all'||(filter==='ios'?p.ios:p.category===filter)));
 if($('#sort').value!=='default')visible.sort((a,b)=>($('#sort').value==='asc'?1:-1)*(a.cents-b.cents));
 $('#shopProducts').innerHTML=visible.length?visible.map(card).join(''):empty('没有找到匹配商品','试试其他关键词或商品分类。');$('#productCount').textContent=`共 ${visible.length} 款商品 · 当前为模拟交易`;
}
async function loadCart(){cart=state.user?(await api('/api/cart')).items:[];$('#cartCount').textContent=cart.reduce((s,p)=>s+p.qty,0);}
function renderCart(){const area=$('#cartContent');if(!state.user){area.innerHTML=loginHint('登录后可以保存购物车，并创建模拟订单。');return;}if(!cart.length){area.innerHTML=empty('购物车还是空的','去发现适合你的数字服务吧。');return;}
 const total=cart.reduce((s,p)=>s+p.cents*p.qty,0);
 area.innerHTML=`<div class="split"><div class="panel">${cart.map(p=>`<article class="cart-line"><div><h3>${esc(p.name)}</h3><span class="tiny muted">单价 ${money(p.cents)}${p.active?'':' · 已下架，请移除'}</span></div><div class="quantity"><button class="secondary small" aria-label="减少 ${esc(p.name)} 数量" data-qty="${p.id}" data-value="${p.qty-1}">−</button><span>${p.qty}</span><button class="secondary small" aria-label="增加 ${esc(p.name)} 数量" data-qty="${p.id}" data-value="${p.qty+1}" ${p.qty>=99||!p.active?'disabled':''}>+</button></div><div class="line-price"><strong>${money(p.cents*p.qty)}</strong><button class="link-button tiny" data-qty="${p.id}" data-value="0">移除</button></div></article>`).join('')}</div><aside class="panel summary"><h3>订单摘要</h3><p class="row between muted"><span>商品数量</span><span>${cart.reduce((s,p)=>s+p.qty,0)} 件</span></p><hr><p class="row between"><span>合计</span><strong class="price">${money(total)}</strong></p><div class="notice">只生成模拟订单，不收取费用，不会充值或开通任何第三方订阅。</div><p><button id="checkout" class="primary wide" ${cart.some(p=>!p.active)?'disabled':''}>创建模拟订单 →</button></p><p class="tiny muted">价格以服务器核实结果为准。订单创建后可单独体验模拟支付。</p></aside></div>`;
}
async function loadOrders(){if(!state.user){orders=[];$('#orderList').innerHTML=loginHint('订单仅对账户本人可见。');return;}orders=(await api('/api/orders')).orders;renderOrders();}
function renderOrders(){const rows=orders.filter(o=>orderFilter==='all'||o.status===orderFilter);$('#orderList').innerHTML=rows.length?rows.map(o=>orderCard(o)).join(''):empty('这里还没有订单','选购商品，体验完整的模拟下单流程。');}
async function loadTickets(){if(!state.user){$('#ticketList').innerHTML=loginHint('登录后可以给商家留言并查看回复。');return;}$('#ticketList').innerHTML=ticketsHTML((await api('/api/tickets')).tickets);}
function account(){
 $('#accountLink').textContent=state.user?state.user.nickname:'登录 / 注册';$('#authPanel').hidden=!!state.user;$('#profilePanel').hidden=!state.user;
 if(state.user){$('#greeting').textContent=`你好，${state.user.nickname}`;$('#usernameLabel').textContent='用户名：'+state.user.username;$('#profileForm [name="nickname"]').value=state.user.nickname;$('#accountStats').innerHTML=`<div class="panel"><strong>${orders.length}</strong><p class="tiny muted">累计模拟订单</p></div><div class="panel"><strong>${orders.filter(o=>o.status==='pending').length}</strong><p class="tiny muted">待模拟支付</p></div><div class="panel"><strong>${orders.filter(o=>o.status==='paid').length}</strong><p class="tiny muted">待演示交付</p></div>`;}
}
async function route(){
 const name=view();$$('[data-view]').forEach(x=>x.hidden=x.dataset.view!==name);$$('nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+name));window.scrollTo({top:0});
 try{if(name==='home'||name==='shop')await catalog();if(name==='cart'){await loadCart();renderCart();}if(name==='orders')await loadOrders();if(name==='support')await loadTickets();if(name==='account'){await loadOrders();account();}}catch(e){toast(e.message,true);}
}
function authTab(mode){authMode=mode;$('#loginTab').classList.toggle('active',mode==='login');$('#registerTab').classList.toggle('active',mode==='register');$('#nicknameField').hidden=mode!=='register';$('#nicknameField input').required=mode==='register';$('#authTitle').textContent=mode==='login'?'欢迎回来':'创建你的账户';$('#authSubmit').textContent=mode==='login'?'登录':'注册并登录';$('#authPassword').minLength=mode==='register'?10:1;$('#authPassword').autocomplete=mode==='register'?'new-password':'current-password';$('#authPassword').placeholder=mode==='register'?'至少 10 个字符':'请输入密码';$('#authForm .form-error').textContent='';}
$('#loginTab').onclick=()=>authTab('login');$('#registerTab').onclick=()=>authTab('register');
bindForm('#authForm',async(data,form)=>{await api('/api/'+authMode,data);await me();await loadCart();account();form.reset();toast(authMode==='login'?'登录成功':'账户创建成功');authTab('login');location.hash=returnTo||'account';returnTo='';await route();});
bindForm('#profileForm',async data=>{await api('/api/profile',data);await me();account();toast('个人资料已保存');});
bindForm('#passwordForm',async(data,form)=>{await api('/api/password',data);await me();form.reset();toast('密码已更新，其他会话已退出');});
$('#logout').onclick=async()=>{try{await api('/api/logout',{});await me();cart=[];orders=[];$('#cartCount').textContent='0';account();toast('已退出登录');}catch(e){toast(e.message,true);}};
$('#search').oninput=renderProducts;$('#sort').onchange=renderProducts;
$('#filters').onclick=e=>{const b=e.target.closest('[data-filter]');if(!b)return;filter=b.dataset.filter;$$('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));renderProducts();};
$('#orderFilters').onclick=e=>{const b=e.target.closest('[data-status]');if(!b)return;orderFilter=b.dataset.status;$$('[data-status]').forEach(x=>x.classList.toggle('active',x===b));if(state.user)renderOrders();};
$('#refreshOrders').onclick=()=>loadOrders().then(()=>toast('订单已更新')).catch(e=>toast(e.message,true));
$('#refreshTickets').onclick=()=>loadTickets().then(()=>toast('咨询记录已更新')).catch(e=>toast(e.message,true));
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-add],[data-detail],[data-qty],[data-close],[data-order],#checkout');if(!button)return;
 e.preventDefault();if(button.dataset.close){$('#'+button.dataset.close).close();return;}
 if(button.dataset.detail){const p=products.find(p=>p.id===Number(button.dataset.detail));if(!p)return;$('#detailTitle').textContent=p.name;$('#detailContent').innerHTML=`<img class="detail-image" src="/assets/ai-hero.png" alt="AI 商品示意图"><div class="row between"><span class="badge">${p.ios?'iOS 美区':p.category.toUpperCase()}</span><strong class="price">${money(p.cents)}</strong></div><p class="pre muted">${esc(p.description)}</p><div class="notice">当前仅供模拟体验，不会开通、充值或交付真实订阅。</div><p><button class="primary wide" data-add="${p.id}">加入购物车</button></p>`;$('#productDialog').showModal();return;}
 button.disabled=true;
 try{
   if(button.dataset.add){if(!requireLogin('shop')){$('#productDialog').close();return;}const id=Number(button.dataset.add);await loadCart();const qty=(cart.find(p=>p.id===id)?.qty||0)+1;await api('/api/cart',{product_id:id,qty});await loadCart();toast('已加入购物车，登录后会持续保存');}
   if(button.dataset.qty){await api('/api/cart',{product_id:Number(button.dataset.qty),qty:Number(button.dataset.value)});checkoutKey=null;await loadCart();renderCart();}
   if(button.id==='checkout'){
     if(!await confirmation('创建模拟订单','将保存当前商品与价格快照。本次操作不收款，也不提供真实订阅服务。','创建订单'))return;
     checkoutKey ||= crypto.randomUUID();await api('/api/orders',{request_key:checkoutKey,expected_total:cart.reduce((s,p)=>s+p.qty*p.cents,0)});checkoutKey=null;await loadCart();location.hash='orders';toast('模拟订单已创建');
   }
   if(button.dataset.order){const action=button.dataset.order;const descriptions={pay:['模拟支付','这将把订单标记为“已模拟支付”，不会打开微信或支付宝，也不会扣款。'],cancel:['取消订单','确定取消这笔待支付订单吗？'],request_refund:['申请模拟退款','申请会交给商家后台处理，不发生真实资金变动。']};const [title,message]=descriptions[action];if(!await confirmation(title,message))return;await api('/api/order/action',{id:button.dataset.id,action});await loadOrders();toast('订单状态已更新');}
 }catch(err){toast(err.message,true);if(err.status===401){await me();account();}if(view()==='cart'){await loadCart().catch(()=>{});renderCart();}}finally{button.disabled=false;}
});
function bubble(message,mine=false){const d=document.createElement('div');d.className='bubble'+(mine?' me':'');d.textContent=message;$('#chatLog').append(d);$('#chatLog').scrollTop=$('#chatLog').scrollHeight;}
function chat(question){bubble(question,true);const q=question.toLowerCase();let answer;if(/支付|充值|付款|收费/.test(q))answer='当前只支持模拟支付，不收取费用、不充值，也不会开通任何第三方订阅。真实支付尚未启用。';else if(/退款/.test(q))answer='在“我的订单”中，对已模拟支付或已记录交付的订单申请模拟退款，商家可在后台处理。不会发生真实资金变动。';else if(/订单|交付/.test(q))answer='登录后打开“我的订单”，可查看状态、订单进度和商家的演示交付说明。订单刷新后仍会保存。';else if(/plus|pro|价格|商品|套餐/.test(q)){const matched=products.filter(p=>q.includes('plus')?p.category==='plus':q.includes('pro')?p.category==='pro':true);answer=matched.length?matched.map(p=>p.name+'：'+money(p.cents)).join('\n')+'\n以上为展示价，仅供模拟体验。':'暂时没有符合条件的上架商品。';}else answer='我是本地规则式客服，可回答套餐价格、订单、支付和退款问题。其他问题请通过“给商家留言”提交，商家会在后台回复。';bubble(answer);}
bubble('你好，欢迎来到智选 AI 商城。可以咨询套餐、订单和模拟支付，也可以给商家留言。');
bindForm('#chatForm',async(_,form)=>{const q=$('#prompt').value.trim();if(q)chat(q);form.reset();});
$$('[data-question]').forEach(b=>b.onclick=()=>chat(b.dataset.question));
bindForm('#ticketForm',async(data,form)=>{if(!requireLogin('support'))return;await api('/api/tickets/new',data);form.reset();await loadTickets();toast('咨询已保存，商家可在后台回复');});
bindReplies($('#ticketList'),loadTickets);
window.addEventListener('hashchange',route);
async function start(){try{await me();await catalog();await loadCart();account();$('#loading').hidden=true;await route();}catch(e){$('#loading').textContent='商城连接失败，请确认启动窗口仍在运行，再刷新重试。';toast(e.message,true);}}
start();
