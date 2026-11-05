import type { NextConfig } from "next";

import { readSettings } from "./lib/settings";

const settings = readSettings(process.env);

const nextConfig: NextConfig = {
  // No AGENTS.md: `next dev` writes one when it detects an AI coding agent (S17-R1 c2: no extras).
  agentRules: false,
  // The forwarder (ADR-016 D1): the browser calls `/api/*` on the UI's own address and Next
  // passes each request on to the API, so the API needs no CORS. The API's status, body and
  // headers (X-Request-ID) come back unchanged.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${settings.apiBaseUrl}/:path*` }];
  },
  experimental: {
    // In ms. Next's default is 30 s (node_modules/next/dist/server/lib/router-utils/
    // proxy-request.js), shorter than an answer on the AWS server. Past it, Next answers its own
    // plain-text 500.
    proxyTimeout: settings.apiTimeoutS * 1000,
  },
};

export default nextConfig;
