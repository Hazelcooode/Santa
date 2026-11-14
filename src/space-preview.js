import { retryProductImage } from './product-images.js';
import { request } from './api-client.js';
import { safeText as esc } from './model.js';
import { sadAvatarSvg } from './art.js';

let active = null;
export function closeVisualPreview() { active?.close(); }

// Deliberately no localStorage, saved-media API or persistent upload queue here.
export function openVisualPreview({ offers, watchId, saveToken, kind = 'space', optionId }) {
  closeVisualPreview();
  const previousFocus = document.activeElement;
  const dialog = document.createElement('dialog');
  dialog.className = 'space-preview-dialog sola-screen';
  dialog.setAttribute('aria-labelledby', 'space-preview-title');
  const choices = offers.filter(o => o.id);
  let closed = false, working = false, jobId = null, photo = null, photoUrl = null, timer, expiry, photoVersion = 0;
  let chosen = choices.find(o => o.id === optionId) || choices[0];
  const isSpace = kind === 'space';
  dialog.innerHTML = `<div class="space-preview-head"><div><span class="ui-tag">CLOUDINARY STUDIO</span><h2 id="space-preview-title">${isSpace ? 'Preview in your space' : 'See it from both sides'}</h2></div><button class="button secondary" type="button" data-close aria-label="Close preview">✕</button></div>
    <p class="ui-note">${isSpace ? 'Choose a product, select how you want to use it, and upload your photo. Add a short instruction for more precise placement.' : 'Generate a three-second view: 45° left, then 45° right, on a warm beige studio background.'}</p>
    <p class="space-ai-warning" role="note"><strong>AI-generated visualization.</strong> Results can be low quality or completely unrealistic, especially for clothing and shoes. Fit, proportions, details and unseen surfaces may be wrong. This is not a reliable fitting tool.</p>
    <div class="space-preview-layout"><div class="space-preview-controls"><label class="field"><span>Choose a product</span><select data-product>${choices.map(o => `<option value="${esc(o.id)}" ${o.id === chosen?.id ? 'selected' : ''}>${esc(o.title)}</option>`).join('')}</select></label>
    <div class="space-product-image" data-product-image></div>
    ${isSpace ? `<label class="field"><span>How will you use it?</span><select data-preview-mode><option value="room">Item in a room / furniture</option><option value="clothing">Clothing, shoes &amp; accessories</option><option value="other">Other placement</option></select></label><p class="ui-note" data-mode-hint>Show the surface or existing object you want to replace.</p><label class="field"><span>What should change? <small>(optional)</small></span><textarea data-placement maxlength="500" rows="3" placeholder="e.g. Replace the chair beside the desk; keep everything else."></textarea></label><label class="space-photo-upload field"><span>Your photo</span><input data-photo type="file" accept="image/jpeg,image/png,image/webp"><small>JPEG, PNG or WebP · up to 12 MB. Resized on your device before upload.</small></label><img class="space-room-photo" data-room hidden alt="Your selected photo">` : ''}
    <button class="button dark" data-generate ${isSpace || !chosen ? 'disabled' : ''}>${isSpace ? 'Create my preview' : 'Generate 3D turn'}</button>
    <p class="ui-note">AI visualization. Size and unseen surfaces are approximate; product details may change. ${isSpace ? 'Your photo is processed temporarily by Cloudinary. Closing this dialog requests deletion. Abandoned sessions expire after 15 minutes; provider outages may delay deletion.' : 'An inferred view, not a scanned 3D model. Some objects may not turn accurately.'}</p></div>
    <section class="space-preview-output" aria-label="Preview output"><div data-output><div class="space-preview-empty">${sadAvatarSvg()}<h3>${isSpace ? 'A little imagination. Your actual space.' : 'A new perspective on your shortlist.'}</h3><p>${isSpace ? 'Your preview will appear here.' : 'Generate only when you want a closer look.'}</p></div></div><p data-status role="status" aria-live="polite"></p><div class="ui-actions" data-result-actions hidden></div></section></div>`;
  document.body.append(dialog);
  const status = dialog.querySelector('[data-status]'), generate = dialog.querySelector('[data-generate]');
  const productImage = dialog.querySelector('[data-product-image]');
  function lockControls(disabled) {
    for (const field of dialog.querySelectorAll('[data-product],[data-photo],[data-preview-mode],[data-placement]')) field.disabled = disabled;
  }
  function showProduct() {
    productImage.innerHTML = chosen?.thumbnail ? `<img src="${esc(chosen.thumbnail)}" alt="${esc(chosen.title)}">` : sadAvatarSvg();
    productImage.querySelector('img')?.addEventListener('error', () => { retryProductImage(productImage.querySelector('img'),()=>{productImage.innerHTML = sadAvatarSvg();}); });
  }
  const removeJob = id => request('/visual-previews/' + encodeURIComponent(id), { method: 'DELETE', keepalive: true }).catch(() => {});
  const session = { close() {
    if (closed) return;
    closed = true; photoVersion++;
    clearTimeout(timer); clearTimeout(expiry);
    if (jobId) removeJob(jobId);
    photo = null;
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    dialog.querySelector('video')?.pause();
    dialog.querySelectorAll('img,video,source').forEach(el => el.removeAttribute('src'));
    dialog.remove();
    window.removeEventListener('pagehide', session.close);
    if (active === session) active = null;
    if (previousFocus?.isConnected) previousFocus.focus();
  }};
  active = session;
  window.addEventListener('pagehide', session.close);
  dialog.querySelector('[data-close]').onclick = session.close;
  dialog.addEventListener('cancel', e => { e.preventDefault(); session.close(); });
  dialog.addEventListener('click', e => { if (e.target === dialog) session.close(); });
  dialog.querySelector('[data-product]').onchange = e => { chosen = choices.find(o => o.id === e.target.value); showProduct(); };
  dialog.querySelector('[data-preview-mode]')?.addEventListener('change', event => {
    const mode = event.target.value;
    dialog.querySelector('[data-mode-hint]').textContent = mode === 'clothing'
      ? 'For shoes, show both feet clearly to replace a matching pair. Keep the target clothing area visible. AI try-on is experimental and can look unrealistic.'
      : mode === 'room' ? 'Show the surface or existing object you want to replace.' : 'Describe what to replace or add, how many, and where it belongs.';
    dialog.querySelector('[data-placement]').placeholder = mode === 'clothing'
      ? 'e.g. Replace both shoes with a matching left/right pair. Keep my jeans and pose.'
      : mode === 'room' ? 'e.g. Replace the chair beside the desk; keep everything else.' : 'e.g. Replace the two cups on the table with this matching pair.';
  });
  dialog.querySelector('[data-photo]')?.addEventListener('change', async e => {
    const version = ++photoVersion;
    const file = e.target.files[0];
    photo = null; generate.disabled = true;
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    const image = dialog.querySelector('[data-room]'); image.hidden = true; image.removeAttribute('src');
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 12 * 1024 * 1024) {
      status.textContent = 'Choose a JPEG, PNG or WebP photo smaller than 12 MB.'; return;
    }
    let bitmap;
    try {
      status.textContent = 'Preparing your photo on this device…';
      bitmap = await createImageBitmap(file);
      if (closed || version !== photoVersion) return;
      if (bitmap.width * bitmap.height > 60_000_000) throw Error('Use a photo smaller than 60 megapixels.');
      const scale = Math.min(1, 1920 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale)); canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      // Re-encoding removes EXIF/GPS metadata before sending anything to the server.
      photo = canvas.toDataURL('image/jpeg', 0.88);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.88));
      canvas.width = canvas.height = 0;
      if (closed || version !== photoVersion) { if (closed) photo = null; return; }
      photoUrl = URL.createObjectURL(blob); image.src = photoUrl; image.hidden = false;
      status.textContent = 'Photo ready. Generate when you are ready.'; generate.disabled = !chosen;
    } catch (err) { status.textContent = err.message || 'This photo could not be decoded.'; }
    finally { bitmap?.close(); }
  });
  async function poll() {
    if (closed) return;
    try {
      const job = await request('/visual-previews/' + encodeURIComponent(jobId));
      if (closed) return;
      if (job.status === 'failed') throw Error(job.error || 'Cloudinary could not generate this preview.');
      if (job.status !== 'ready') { timer = setTimeout(poll, 2500); return; }
      status.textContent = job.notice;
      const output = dialog.querySelector('[data-output]');
      output.innerHTML = isSpace ? `<img class="space-generated-image" src="${esc(job.url)}" alt="AI visualization of your chosen product in your environment">` : `<video class="space-generated-video" controls playsinline preload="metadata"><source src="${esc(job.url)}" type="video/mp4"></video>`;
      output.querySelector('img,video').addEventListener('error', () => {
        status.textContent = 'Cloudinary is still preparing delivery. Retry loading the preview.';
        const retry = document.createElement('button'); retry.className = 'button secondary'; retry.textContent = 'Retry loading';
        retry.onclick = () => { retry.remove(); const el = output.querySelector('img,video'); if (isSpace) el.src = job.url + '?retry=' + Date.now(); else el.load(); };
        dialog.querySelector('[data-result-actions]').append(retry);
      });
      const actions = dialog.querySelector('[data-result-actions]'); actions.hidden = false;
      actions.innerHTML = `<a class="button dark" download="sola-preview.${isSpace ? 'png' : 'mp4'}" href="${esc(job.url)}?download=true">Download ${isSpace ? 'image' : 'video'}</a><span class="ui-note">Download to keep a copy. This preview is not added to your account.</span>`;
      working = false;
    } catch (err) {
      status.textContent = err.message; working = false; generate.disabled = false;
      dialog.querySelector('[data-output]').innerHTML = `<div class="space-preview-empty"><h3>Preview could not be created</h3><p>${esc(err.message)}</p></div>`;
      lockControls(false);
    }
  }
  generate.onclick = async () => {
    if (working || !chosen || (isSpace && !photo)) return;
    working = true; generate.disabled = true;
    lockControls(true);
    status.textContent = isSpace ? 'Cloudinary is placing your product into the scene…' : 'Cloudinary is generating the object’s side views. This can take a few minutes…';
    if (jobId) removeJob(jobId);
    try {
      const job = await request('/visual-previews', { method: 'POST', body: { kind, optionId: chosen.id, watchId, saveToken, ...(isSpace ? { imageData: photo, previewMode: dialog.querySelector('[data-preview-mode]').value, instructions: dialog.querySelector('[data-placement]').value.trim() } : {}) } });
      if (closed) { removeJob(job.id); return; }
      jobId = job.id;
      // The server independently enforces expiry even if the browser disappears.
      expiry = setTimeout(session.close, 14 * 60 * 1000);
      poll();
    } catch (err) {
      if (closed) return;
      status.textContent = err.message; working = false; generate.disabled = false;
      lockControls(false);
    }
  };
  showProduct(); dialog.showModal();
}
