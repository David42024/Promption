const compact = text => text.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
const rot13 = text => text.replace(/[a-zA-Z]/g, char => String.fromCharCode(char.charCodeAt(0) +
  (char.toLowerCase() <= 'm' ? 13 : -13)));

export function compileKnownValues(values = []) {
  if (!Array.isArray(values)) throw new TypeError('protectedValues must be a server-owned string array');
  return values.map(value => {
    if (typeof value !== 'string' || compact(value).length < 8) throw new TypeError('Protected values need at least eight letters or digits');
    const variants = [];
    if (value.length <= 4096) {
      const bytes = new TextEncoder().encode(value);
      const encoded = btoa(String.fromCharCode(...bytes));
      variants.push(encoded, encoded.replace(/\+/g, '-').replace(/\//g, '_'),
        [...bytes].map(byte => byte.toString(16).padStart(2,'0')).join(''), [...value].reverse().join(''), rot13(value), encodeURIComponent(value));
    }
    const fragments = /^[A-Za-z0-9_+/=-]{32,256}$/.test(value) && /\d/.test(value);
    const fragmentEncodings = [];
    if (fragments) for(let index=0;index+8<=value.length;index++) {
      const fragment=value.slice(index,index+8);
      if(compact(fragment).length<8)continue;
      fragmentEncodings.push(compact(btoa(fragment)), [...new TextEncoder().encode(fragment)].map(byte=>byte.toString(16).padStart(2,'0')).join(''));
    }
    return Object.freeze({ value: compact(value), variants: variants.map(compact), fragments, fragmentEncodings });
  });
}

export function matchKnownValue(text, compiled) {
  if (!compiled.length) return;
  let decoded = text.replace(/\\u([\da-f]{4})/gi, (_, code) => String.fromCharCode(parseInt(code,16)));
  decoded = decoded.replace(/&#(?:x([\da-f]{1,6})|(\d{1,7}));?/gi, (raw, hex, decimal) => {
    const point = parseInt(hex ?? decimal, hex ? 16 : 10);
    return point <= 0x10ffff ? String.fromCodePoint(point) : raw;
  });
  decoded = decoded.replace(/(?:%[a-f\d]{2})+/gi, raw => { try { return decodeURIComponent(raw); } catch { return raw; } });
  const views = [compact(decoded)];
  for (const token of (decoded.match(/[A-Za-z0-9+/_-]{12,8192}={0,2}/g) ?? []).slice(0,8)) {
    try { views.push(compact(new TextDecoder('utf-8',{ fatal:true }).decode(Uint8Array.from(atob(token.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0))))); } catch {}
  }
  for (const token of (decoded.match(/\b[0-9a-fA-F]{16,8192}\b/g) ?? []).slice(0,8)) {
    try { views.push(compact(new TextDecoder('utf-8',{ fatal:true }).decode(Uint8Array.from(token.match(/../g),hex=>parseInt(hex,16))))); } catch {}
  }
  for (const secret of compiled) {
    if (views.some(view => view.includes(secret.value))) return 'known_secret';
    if (secret.variants.some(value => views.some(view => view.includes(value)))) return 'known_secret_encoding';
    if (secret.fragments && views.some(view => {
      for (let index=0;index+8<=secret.value.length;index++) if(view.includes(secret.value.slice(index,index+8))) return true;
      return false;
    })) return 'known_secret_fragment';
    if (secret.fragmentEncodings.some(value=>views.some(view=>view.includes(value)))) return 'known_secret_fragment';
  }
}
