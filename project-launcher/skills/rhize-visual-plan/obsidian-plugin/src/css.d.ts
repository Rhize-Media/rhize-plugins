/* Allow `import styles from "...css"` — esbuild's text loader turns the CSS
   file into a default string export. We inject that string as a <style>. */
declare module "*.css" {
  const content: string;
  export default content;
}
