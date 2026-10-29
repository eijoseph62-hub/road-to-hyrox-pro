'use strict';
const $ = id => document.getElementById(id);
let token = '', ready = false, busy = false, messages = [];
const greeting = $('messages').firstElementChild.cloneNode(true);
function setReady() { $('send').disabled = !ready || !token || busy; }
function add(role, content) {
  const card = document.createElement('article'); card.className = role === 'user' ? 'user' : 'coach';
  const label = document.createElement('span'); label.textContent = role === 'user' ? 'YOU' : 'SAYAKA';
  const text = document.createElement('p'); text.textContent = content;
  card.append(label, text); $('messages').append(card); card.scrollIntoView({block: 'nearest', behavior: 'smooth'});
}
fetch('/api/status').then(r => { if (!r.ok) throw Error(); return r.json(); }).then(s => {
  ready = s.configured === true;
  $('status').textContent = ready ? 'テキスト会話に接続できます。アクセスコードを入力してください。' : '画面の準備は完了しています。会話用サーバーの接続設定はまだ完了していません。';
  $('connect').disabled = !ready; setReady();
}).catch(() => { $('status').textContent = 'このページでは会話用サーバーに接続できません。公開サイトの静的配信だけでは会話は動作しません。'; $('connect').disabled = true; });
$('connect').addEventListener('click', () => {
  token = $('access').value.trim(); $('access').value = '';
  $('error').textContent = token ? '' : 'アクセスコードを入力してください。'; setReady();
});
document.querySelectorAll('[data-prompt]').forEach(b => b.addEventListener('click', () => { $('question').value = b.dataset.prompt; $('question').focus(); }));
$('reset').addEventListener('click', () => { if (busy) return; messages = []; $('messages').replaceChildren(greeting.cloneNode(true)); $('error').textContent = ''; });
$('chat-form').addEventListener('submit', async e => {
  e.preventDefault(); if (busy || !token || !ready) return;
  const content = $('question').value.trim(); if (!content) return;
  const pending = [...messages.slice(-10), {role:'user', content}];
  add('user', content); $('question').value = ''; busy = true; $('error').textContent = ''; setReady();
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch('/api/chat', {method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${token}`},body:JSON.stringify({messages:pending}),signal:controller.signal});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || '送信できませんでした。');
    messages = [...pending,{role:'assistant',content:result.reply}]; add('assistant', result.reply);
  } catch (error) { $('error').textContent = error.name === 'AbortError' ? '応答に時間がかかっています。送信結果を確認してから再試行してください。' : error.message; $('question').value = content; }
  finally { clearTimeout(timeout); busy = false; setReady(); }
});
