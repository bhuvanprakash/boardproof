import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BoardProof — Hardware design checks",
  description: "Check hardware connections, reviewed rules, and firmware before a board spin.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
