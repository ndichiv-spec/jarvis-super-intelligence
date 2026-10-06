import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import type { LoaderFunction } from "@remix-run/node";
import { MinimalDashboard } from "~/components/minimal-dashboard";

export const loader: LoaderFunction = async () => {
  try {
    // Fetch initial data for the dashboard
    const response = await fetch("http://localhost:8000/api/v1/components");
    const components = await response.json();
    
    // Fetch health status
    const healthResponse = await fetch("http://localhost:8000/api/v1/health/status");
    const health = await healthResponse.json();
    
    return json({
      components,
      health,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Dashboard loader error:", error);
    return json({
      components: [],
      health: { status: "ok", message: "Backend not available" },
      timestamp: new Date().toISOString(),
    });
  }
};

export default function Dashboard() {
  const data = useLoaderData<typeof loader>();
  
  return (
    <div className="min-h-screen bg-gray-900">
      <div className="container mx-auto p-4">
        <h1 className="text-4xl font-bold text-white mb-8">JARVIS Remix Dashboard</h1>
        <div className="text-white">
          <p>Status: {data.health?.status || 'Unknown'}</p>
          <p>Message: {data.health?.message || 'No message'}</p>
          <p>Components loaded: {data.components?.length || 0}</p>
          <p>Timestamp: {data.timestamp}</p>
        </div>
        <MinimalDashboard />
      </div>
    </div>
  );
}
