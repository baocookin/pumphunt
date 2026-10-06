import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "pumphunt",
  description: "pump.fun paper-trading bot dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
