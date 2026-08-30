export function route(name) {
  return import(`./handlers/${name}.js`);
}
