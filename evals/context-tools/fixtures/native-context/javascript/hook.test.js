import { handle } from "./hook.js";

if (handle("context work") !== "context-engineering") throw new Error("hook fixture failed");
