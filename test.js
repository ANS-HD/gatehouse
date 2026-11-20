function Foo() {}

const a = new Foo();

Foo.prototype = {};

const b = new Foo();

console.log(a instanceof Object);
console.log(a instanceof Foo);
console.log(b instanceof Foo);