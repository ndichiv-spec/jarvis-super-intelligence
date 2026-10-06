"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Compass, Loader2, MapPin, Search, Satellite, Signpost } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { API_ENDPOINTS } from "@/config/api";
import { apiClient } from "@/lib/api-client";

interface Place {
  name: string;
  latitude: number;
  longitude: number;
  type: string;
}

interface GeographyProviders {
  geocoding: { configured: boolean; user_agent_configured: boolean };
  routing: { configured: boolean };
  satellite_imagery: { configured: boolean; provider_license_confirmed: boolean; license_confirmed: boolean };
  attribution: string;
}

interface RouteResult {
  distance_meters: number;
  duration_seconds: number;
  steps: Array<{ instruction: string; distance_meters: number; duration_seconds: number }>;
  source: string;
}

export default function GeographyPage() {
  const [providers, setProviders] = useState<GeographyProviders | null>(null);
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<Place[]>([]);
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [routing, setRouting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mapCenter, setMapCenter] = useState({ latitude: 0, longitude: 0 });

  useEffect(() => {
    let cancelled = false;
    void apiClient.get<GeographyProviders>(API_ENDPOINTS.geography.providers)
      .then((result) => { if (!cancelled) setProviders(result); })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "Could not load map provider status.");
        }
      });
    return () => { cancelled = true; };
  }, []);

  const mapUrl = useMemo(() => {
    const { latitude, longitude } = mapCenter;
    const minLat = Math.max(-85, latitude - 0.08);
    const maxLat = Math.min(85, latitude + 0.08);
    const minLon = Math.max(-180, longitude - 0.12);
    const maxLon = Math.min(180, longitude + 0.12);
    const bbox = `${minLon},${minLat},${maxLon},${maxLat}`;
    const marker = `${latitude},${longitude}`;
    return `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${encodeURIComponent(marker)}`;
  }, [mapCenter]);

  const searchPlaces = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const placeQuery = query.trim();
    if (!placeQuery) return;
    setSearching(true);
    setError(null);
    try {
      const result = await apiClient.get<{ results: Place[] }>(API_ENDPOINTS.geography.geocode, {
        params: { q: placeQuery },
      });
      setPlaces(result.results);
      if (result.results.length === 0) setError("No matching places were returned.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Place search failed.");
    } finally {
      setSearching(false);
    }
  }, [query]);

  const setRouteEndpoint = (place: Place, endpoint: "origin" | "destination") => {
    if (endpoint === "origin") setOrigin(place);
    else setDestination(place);
    setMapCenter({ latitude: place.latitude, longitude: place.longitude });
    setRoute(null);
  };

  const calculateRoute = async () => {
    if (!origin || !destination) return;
    setRouting(true);
    setError(null);
    try {
      const result = await apiClient.post<RouteResult>(API_ENDPOINTS.geography.route, {
        from: { latitude: origin.latitude, longitude: origin.longitude },
        to: { latitude: destination.latitude, longitude: destination.longitude },
      });
      setRoute(result);
      setMapCenter({
        latitude: (origin.latitude + destination.latitude) / 2,
        longitude: (origin.longitude + destination.longitude) / 2,
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Route calculation failed.");
    } finally {
      setRouting(false);
    }
  };

  return (
    <main className="space-y-6 p-6">
      <header>
        <h1 className="flex items-center gap-2 text-3xl font-bold">
          <Satellite className="h-8 w-8 text-cyan-400" />
          Maps & Geography
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Explore a real map, identify coordinates, find places, and request directions from configured providers.
        </p>
      </header>

      {error && <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{error}</p>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><MapPin className="h-5 w-5" /> Interactive map</CardTitle>
            <CardDescription>
              Map data © OpenStreetMap contributors. Satellite imagery requires a separately licensed imagery provider.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <iframe
              key={mapUrl}
              title="OpenStreetMap location map"
              src={mapUrl}
              className="h-[480px] w-full rounded-md border"
              loading="lazy"
              referrerPolicy="no-referrer"
            />
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">OpenStreetMap · © OSM contributors</Badge>
              <span>Satellite imagery layers are not rendered yet. This view does not connect to or control satellites.</span>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Search className="h-5 w-5" /> Find a place</CardTitle>
              <CardDescription>
                {providers?.geocoding.configured && providers.geocoding.user_agent_configured
                  ? "Search is sent to the configured geocoding provider."
                  : "Connect a Nominatim-compatible geocoder in the backend to enable place search."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={searchPlaces} className="flex gap-2">
                <Input
                  aria-label="Place search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="City, address, or landmark"
                  disabled={!providers?.geocoding.configured || !providers.geocoding.user_agent_configured || searching}
                />
                <Button type="submit" disabled={!providers?.geocoding.configured || !providers.geocoding.user_agent_configured || searching || !query.trim()}>
                  {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  <span className="sr-only">Search places</span>
                </Button>
              </form>
              {providers?.geocoding.configured && !providers.geocoding.user_agent_configured && (
                <p className="text-xs text-amber-500">Set an identifiable JARVIS_GEOCODER_USER_AGENT before querying the provider.</p>
              )}
              <div className="max-h-72 space-y-3 overflow-y-auto">
                {places.map((place, index) => (
                  <div key={`${place.latitude}-${place.longitude}-${index}`} className="rounded-md border p-3">
                    <p className="text-sm font-medium">{place.name}</p>
                    <p className="mt-1 font-mono text-xs text-muted-foreground">
                      {place.latitude.toFixed(6)}, {place.longitude.toFixed(6)}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => setRouteEndpoint(place, "origin")}>Set origin</Button>
                      <Button size="sm" variant="outline" onClick={() => setRouteEndpoint(place, "destination")}>Set destination</Button>
                      <Button size="sm" variant="ghost" onClick={() => setMapCenter(place)}>Center map</Button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="space-y-2 text-xs">
                <p><strong>Origin:</strong> {origin?.name ?? "Choose a search result"}</p>
                <p><strong>Destination:</strong> {destination?.name ?? "Choose a search result"}</p>
                <Button
                  onClick={() => void calculateRoute()}
                  disabled={!providers?.routing.configured || !origin || !destination || routing}
                >
                  {routing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Signpost className="mr-2 h-4 w-4" />}
                  Get directions
                </Button>
                {!providers?.routing.configured && (
                  <p className="text-muted-foreground">Directions require a configured OSRM-compatible routing provider.</p>
                )}
              </div>
            </CardContent>
          </Card>

          {route && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Compass className="h-5 w-5" /> Directions</CardTitle>
                <CardDescription>
                  {(route.distance_meters / 1000).toFixed(1)} km · {Math.round(route.duration_seconds / 60)} min · {route.source}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="max-h-64 list-decimal space-y-2 overflow-y-auto pl-5 text-sm">
                  {route.steps.map((step, index) => (
                    <li key={`${index}-${step.instruction}`}>
                      {step.instruction}
                      <span className="ml-2 text-xs text-muted-foreground">
                        {(step.distance_meters / 1000).toFixed(2)} km
                      </span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </main>
  );
}
