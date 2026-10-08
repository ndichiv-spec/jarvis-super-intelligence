import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { NeuralThemeProvider } from "@/lib/neural-theme-engine";
import { Toaster } from "@/components/ui/sonner";
import { ConnectionBanner } from "@/components/connection-banner";
import { AutonomousDashboardProvider } from "@/components/autonomous-dashboard-provider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "JARVIS Super AI - Autonomous Intelligence Platform",
  description: "Superior AI Assistant with autonomous capabilities, self-healing, and enterprise-grade features",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ConnectionBanner />
        <AutonomousDashboardProvider>
          <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem={false}
            disableTransitionOnChange
          >
            <NeuralThemeProvider>
              {children}
              <Toaster richColors position="top-right" />
            </NeuralThemeProvider>
          </ThemeProvider>
        </AutonomousDashboardProvider>
      </body>
    </html>
  );
}
