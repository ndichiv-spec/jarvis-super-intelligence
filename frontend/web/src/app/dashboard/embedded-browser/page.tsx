import EmbeddedBrowser from "@/components/embedded-browser/EmbeddedBrowser";

interface EmbeddedBrowserPageProps {
  searchParams: Promise<{ url?: string | string[] }>;
}

export default async function EmbeddedBrowserPage({ searchParams }: EmbeddedBrowserPageProps) {
  const { url } = await searchParams;
  const initialUrl = Array.isArray(url) ? url[0] : url;
  return <EmbeddedBrowser initialUrl={initialUrl} />;
}
