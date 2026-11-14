let previewApi;
export async function request(path, { method = 'GET', body, ...options } = {}) {
  if(typeof window!=='undefined' && window.SOLA_LOCAL_PREVIEW && !window.TAIMI_BACKEND){if(!previewApi){const {createPreviewApi}=await import('./preview-api.js');previewApi=createPreviewApi(localStorage);}return previewApi(path,{method,body});}
  const response = await fetch('/api/v1' + path, { credentials: 'same-origin', ...options, method,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
  if (response.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.hash); throw Error('Please sign in.'); }
  const data = await response.json();
  if (!response.ok) { const details=data.error?.details;const extra=typeof details?.reason==='string' ? details.reason : Array.isArray(details) ? details.map(d=>`${(d.loc||[]).filter(x=>x!=='body').join('.')}: ${d.msg}`).join('; ') : '';const error = Error((data.error?.message || 'Request failed.')+(extra?' '+extra:'')); error.code = data.error?.code; error.status = response.status; throw error; }
  return data;
}
