import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BoardProof | Hardware design review",
  description: "Review circuit, firmware, and PCB changes with traceable evidence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
