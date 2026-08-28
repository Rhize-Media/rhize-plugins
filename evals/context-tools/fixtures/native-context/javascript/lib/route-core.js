export function route(prompt) {
  return prompt.includes("context") ? "context-engineering" : null;
}
