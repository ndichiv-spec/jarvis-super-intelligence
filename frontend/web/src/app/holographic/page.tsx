import { redirect } from 'next/navigation';

export default function HolographicLegacyRedirectPage() {
  redirect('/dashboard/runtime-status');
}
