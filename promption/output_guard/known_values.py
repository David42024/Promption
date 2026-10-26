"""Known-value matching with explicit encodings and bounded opaque-token fragments."""
import base64
import codecs
import html
import re
import unicodedata
from urllib.parse import quote, unquote

from promption.encoded_evidence import decoded_views


def compact(value):
    return ''.join(char for char in unicodedata.normalize('NFKC', value).casefold() if char.isalnum())


def known_value_match(text, values):
    values=tuple(values)
    if not values:
        return None
    raw=unquote(html.unescape(text or ''))
    raw=re.sub(r'\\u([0-9a-fA-F]{4})',lambda match:chr(int(match.group(1),16)),raw)
    decoded,_=decoded_views(raw,origin='tool')
    views=[compact(raw),*(compact(value) for _,value in decoded)]
    for match in list(re.finditer(r'\b[0-9a-fA-F]{16,8192}\b',raw))[:8]:
        try: views.append(compact(bytes.fromhex(match.group()).decode('utf-8')))
        except (ValueError,UnicodeError): pass
    for value in values:
        if not isinstance(value,str):
            raise TypeError('protected_values must contain strings')
        needle=compact(value)
        if len(needle)<8:
            raise ValueError('protected_values must contain at least eight letters or digits')
        if any(needle in view for view in views):
            return 'known_secret'
        if len(value)<=4096:
            data=value.encode('utf-8')
            encoded=[base64.b64encode(data).decode(),base64.urlsafe_b64encode(data).decode(),
                     data.hex(),value[::-1],codecs.encode(value,'rot_13'),quote(value,safe='')]
            if any(compact(variant) in view for variant in encoded for view in views):
                return 'known_secret_encoding'
        opaque=bool(re.fullmatch(r'[A-Za-z0-9_+/=-]{32,256}',value) and re.search(r'\d',value))
        if opaque and any(needle[index:index+8] in view for index in range(len(needle)-7) for view in views):
            return 'known_secret_fragment'
        if opaque:
            for index in range(len(value)-7):
                fragment=value[index:index+8]
                if len(compact(fragment))<8:
                    continue
                variants=[base64.b64encode(fragment.encode()).decode(),fragment.encode().hex()]
                if any(compact(variant) in view for variant in variants for view in views):
                    return 'known_secret_fragment'
    return None
