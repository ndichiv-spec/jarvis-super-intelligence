import SecurityDashboard from '@/components/sub-dashboards/security-dashboard';

export const metadata = {
  title: 'Security Dashboard | JARVIS',
  description: 'Real-time security monitoring and threat detection',
};

export default function SecurityPage() {
  return <SecurityDashboard />;
}
