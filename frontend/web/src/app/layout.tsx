import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { NeuralThemeProvider } from "@/lib/neural-theme-engine";
import { Toaster } from "@/components/ui/sonner";
import { AutonomousDashboardProvider } from "@/components/autonomous-dashboard-provider";
import { MotionProvider } from "@/components/motion-provider";
import { CopilotLauncher } from "@/components/copilot/copilot-launcher";
import { RuntimeBridge } from "@/features/runtime/runtime-bridge";

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
        <AutonomousDashboardProvider>
          <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem={false}
            disableTransitionOnChange
          >
            <NeuralThemeProvider>
              <MotionProvider>
                {children}
                <RuntimeBridge />
                <CopilotLauncher />
                <Toaster richColors position="top-right" />
              </MotionProvider>
            </NeuralThemeProvider>
          </ThemeProvider>
        </AutonomousDashboardProvider>
      </body>
    </html>
  );
}
