'use strict';
const videos = Array.from(document.querySelectorAll('video'));
const play = document.querySelector('#play');
const demo = ['superior.mp4', 'inferior.mp4'];
const files = [null, null];
let run = 0, requested = false;
const theme = document.querySelector('#tema');
function setTheme(light) {
  document.documentElement.classList.toggle('claro', light);
  theme.textContent = light ? 'Tema escuro' : 'Tema claro';
  try { localStorage.setItem('tema', light ? 'claro' : 'escuro'); } catch (_) {}
}
let light = false;
try { light = localStorage.getItem('tema') === 'claro'; } catch (_) {}
setTheme(light);
theme.onclick = () => setTheme(!document.documentElement.classList.contains('claro'));
function personal() { return files.some(Boolean); }
function caption() {
  play.textContent = requested ? 'Pausar as duas lentes' : personal() ? 'Reproduzir gravações' : 'Reproduzir teste';
  play.disabled = personal() && !files.every(Boolean);
}
window.pausar = function () {
  run++;
  requested = false;
  videos.forEach(v => v.pause());
  caption();
};
function sources() {
  window.pausar();
  videos.forEach((v, i) => {
    let url = personal() ? files[i] : demo[i];
    v.loop = !personal();
    if (url) v.src = url; else v.removeAttribute('src');
    document.querySelector('#s' + i).textContent = url ? 'Carregando' : 'Escolha um vídeo';
    v.load();
  });
  document.querySelector('#tipo').textContent = personal() ? 'Gravações do aparelho' : 'Prévia local';
  document.querySelector('#nota').textContent = personal() ? 'Os arquivos selecionados são reproduzidos no seu celular.' : 'Os dois vídeos de teste demonstram a reprodução no celular. Para ver a câmera, abra o teste de Wi-Fi.';
  caption();
}
videos.forEach((v, i) => {
  const status = document.querySelector('#s' + i);
  v.onloadedmetadata = () => { if (!requested) status.textContent = 'Pronta'; };
  v.onplaying = () => { status.textContent = 'Reproduzindo'; };
  v.onpause = () => { if (v.currentSrc && !v.error) status.textContent = 'Pausada'; };
  v.onended = () => { status.textContent = 'Concluída'; if (videos.every(x => x.ended)) window.pausar(); };
  v.onerror = () => { window.pausar(); status.textContent = 'Falha ao abrir vídeo'; };
});
play.onclick = async () => {
  if (requested) { window.pausar(); return; }
  const id = ++run;
  if (videos.every(v => v.ended)) videos.forEach(v => { v.currentTime = 0; });
  requested = true; caption();
  try { await Promise.all(videos.map(v => v.play())); }
  catch (_) {
    if (run === id) { window.pausar(); document.querySelector('#nota').textContent = 'Falha na reprodução. Confira os dois arquivos e tente novamente.'; }
  }
};
document.querySelectorAll('input').forEach(input => {
  input.onchange = () => {
    if (!input.files.length) return;
    const i = Number(input.dataset.lens);
    if (files[i]) URL.revokeObjectURL(files[i]);
    files[i] = URL.createObjectURL(input.files[0]); sources();
  };
});
document.querySelector('#reset').onclick = () => {
  files.forEach((f, i) => { if (f) URL.revokeObjectURL(f); files[i] = null; });
  document.querySelectorAll('input').forEach(x => { x.value = ''; });
  sources();
};
document.addEventListener('visibilitychange', () => { if (document.hidden) window.pausar(); });
sources();
