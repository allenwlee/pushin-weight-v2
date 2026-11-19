/* Declared loopback performance-fixture serialization only. */
(function () {
  'use strict';
  var prototype = CSSStyleDeclaration.prototype;
  var descriptor = Object.getOwnPropertyDescriptor(prototype, 'setProperty');
  var original = descriptor.value;
  var width = 40;
  function reject(reason) {
    // A bad fixture contract must make declared interaction targets unavailable.
    // Do not let an application catch leave a measurable, silently altered page.
    if (document.documentElement) document.documentElement.remove();
    throw new TypeError('Fixture ping delay rejected: ' + reason);
  }
  function setProperty(property, value, priority) {
    if (property !== '--pw-ping-delay') return Reflect.apply(original, this, arguments);
    if (typeof value !== 'string' || value.length > width + 2) reject('raw length/type');
    var match = /^([+-]?)((?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)ms$/.exec(value);
    if (!match) reject('numeric time shape');
    var sign = match[1];
    var mantissaAndExponent = match[2];
    var numberText = sign + mantissaAndExponent;
    if ((numberText.match(/\d/g) || []).length > width) reject('digit count');
    var number = Number(numberText);
    if (!Number.isFinite(number) || number < -2250 || number > 0) reject('phase range');
    var padded = sign + '0'.repeat(width - numberText.length) + mantissaAndExponent;
    if (padded.length !== width || !Object.is(Number(padded), number)) reject('numeric equivalence');
    var args = Array.prototype.slice.call(arguments);
    args[1] = padded + 'ms';
    return Reflect.apply(original, this, args);
  }
  Object.defineProperty(prototype, 'setProperty', Object.assign({}, descriptor, {value: setProperty}));
})();
