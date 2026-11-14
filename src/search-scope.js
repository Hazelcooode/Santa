import { safeText as esc } from './model.js';

export function scopeFields(values = {}) {
  const current = values.searchScope || 'country';
  return `<label>Search scope<select name="searchScope">${[['country','Your country / local'],['eu','European Union'],['multiple','Selected countries'],['worldwide','Worldwide']].map(([v,text])=>`<option value="${v}" ${current===v?'selected':''}>${text}</option>`).join('')}</select></label><label>Search country codes (for selected countries)<input name="searchCountries" value="${esc((values.searchCountries||[]).join(', '))}" placeholder="e.g. FI, SE, DE" maxlength="80"></label><p class="live-wide small-text muted">Your country is a real country code, not EU. Search scope is separate: websites may span countries. EU/selected countries guide the query; check delivery, tax and availability yourself. Quotes are compared only in your selected currency; no exchange rates are invented.</p>`;
}

export function readScope(data) {
  return { searchScope: data.get('searchScope') || 'country', searchCountries: String(data.get('searchCountries')||'').split(',').map(s=>s.trim().toUpperCase()).filter(Boolean) };
}
