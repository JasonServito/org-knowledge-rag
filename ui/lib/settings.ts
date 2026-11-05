// The UI's settings, from the environment (ADR-016 D1; S17-R1 c15). `next.config.ts` reads them
// when Next starts. `next dev` (`make ui`) uses both at each start; `next start` takes the
// forwarder's address from the last `next build` (Next writes rewrites into the build) and the
// timeout at its own start.

export type Settings = {
  apiBaseUrl: string; // where `/api/*` is forwarded: `make serve`, or a window's tunnel
  apiTimeoutS: number; // how long the forwarder waits for the API (~54 s per answer on AWS)
};

export function readSettings(env: Record<string, string | undefined>): Settings {
  // `||`, not `??`: a variable set but empty means the default too.
  const apiTimeoutS = Number(env.API_TIMEOUT_S || 120);
  if (!(apiTimeoutS > 0)) {
    throw new Error("API_TIMEOUT_S must be a number of seconds above 0");
  }
  return { apiBaseUrl: env.API_BASE_URL || "http://127.0.0.1:8000", apiTimeoutS };
}
