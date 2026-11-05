import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "orgknow",
};

// The root layout: no fetching here (ADR-016 D1; every page is a client component). Its links
// reach the 2 pages: the answer page and the Decisions page (every stored chain, ADR-016 D4).
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="nav">
          <Link href="/">Ask</Link>
          <Link href="/decisions">Decisions</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
