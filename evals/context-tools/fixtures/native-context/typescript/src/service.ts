import type { User } from "./types";

export function loadUser(user: User): string {
  return user.id;
}
