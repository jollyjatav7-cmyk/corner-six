/* 角球六要素：离线快取
   第一次联网打开时把文件存到设备上；之后优先用本机文件（离线也能开），
   有网络时在背景取得新版，下次打开就是新版。换了文件时把版本号加 1。 */
const CACHE = 'corner-six-v6';
const ASSETS = ['./', './index.html', './manifest.webmanifest', './icon-180.png', './icon-192.png', './icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE && k.startsWith('corner-six')).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  // 只管这个 app 自己的文件（同一个网域下还有其他 app）
  const scope = new URL(self.registration.scope).pathname;
  if (!new URL(req.url).pathname.startsWith(scope)) return;
  const key = req.mode === 'navigate' ? './index.html' : req;
  const network = fetch(req).then(res => {
    if (res && res.ok && res.type === 'basic'){
      const copy = res.clone();
      return caches.open(CACHE).then(c => c.put(key, copy)).then(() => res, () => res);
    }
    return res;
  }).catch(() => null);
  e.waitUntil(network);
  e.respondWith(caches.match(key, { ignoreSearch: true }).then(hit => hit || network.then(res =>
    res || new Response('目前离线，而且这个文件还没存到设备上。请先联网打开一次。', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } }))));
});
