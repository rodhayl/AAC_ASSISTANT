export type AuthStateSnapshot = {
  token?: string | null;
  user?: { id?: number; user_type?: string } | null;
  logout?: () => void | Promise<void>;
};

type AuthStateReader = () => AuthStateSnapshot;

let readAuthState: AuthStateReader = () => ({});

export function registerAuthStateReader(reader: AuthStateReader): void {
  readAuthState = reader;
}

export function getAuthState(): AuthStateSnapshot {
  return readAuthState();
}
