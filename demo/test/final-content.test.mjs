import test from 'node:test';
import assert from 'node:assert/strict';
import { finalContentText } from '../lib/ai/finalContent.js';

test('only visible structured text is delivered', () => {
  assert.equal(finalContentText([{type:'reasoning', text:'private'},
    {type:'text', text:'Hola'}, {type:'text', channel:'analysis', text:'plan'}]), 'Hola');
  assert.equal(finalContentText({text:'unknown object'}), '');
  assert.equal(finalContentText('We should compare prices.'), 'We should compare prices.');
});
