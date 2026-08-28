export async function dispatch(handlerName) {
  const handler = await import(`./handlers/${handlerName}.js`);
  return handler.run();
}
