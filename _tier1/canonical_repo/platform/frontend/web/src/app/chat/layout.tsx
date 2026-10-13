import { AuthenticatedShell } from '@/components/layout/authenticated-shell';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}
