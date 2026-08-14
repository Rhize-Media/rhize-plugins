import {homedir} from 'node:os';
import {join} from 'node:path';

export function applicationSupportDirectory(home = homedir()) {
  return join(home, 'Library', 'Application Support', 'Rhize Tasks');
}

export function defaultDatabasePath(home = homedir()) {
  return join(applicationSupportDirectory(home), 'state.sqlite');
}
