import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "pumphunt",
  description: "pump.fun on-chain recorder and survivor-entry research dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
