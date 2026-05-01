import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { DialogProvider } from "@/components/ui/dialog-provider";

export const metadata: Metadata = {
  title: "BYOB Console",
  description: "Management console for a self-hosted vector database system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <DialogProvider>
          <AppShell>{children}</AppShell>
        </DialogProvider>
      </body>
    </html>
  );
}
