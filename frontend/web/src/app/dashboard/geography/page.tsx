"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertCircle,
  Check,
  ChevronRight,
  Crosshair,
  LocateFixed,
  Loader2,
  MapPin,
  Navigation,
  Search,
  Signpost,
} from "lucide-react";

import { API_ENDPOINTS } from "@/config/api";
import { apiClient } from "@/lib/api-client";
import { useJarvisRuntime } from "@/features/runtime/store";

interface Place {
  name: string;
  latitude: number;
  longitude: number;
  type: string;
}

interface GeographyProviders {
  geocoding: { configured: boolean; user_agent_configured: boolean };
  routing: { configured: boolean };
  satellite_imagery: {
    configured: boolean;
    provider_license_confirmed: boolean;
    license_confirmed: boolean;
  };
  attribution: string;
}

interface RouteResult {
  distance_meters: number;
  duration_seconds: number;
  steps: Array<{ instruction: string; distance_meters: number; duration_seconds: number }>;
  source: string;
}

interface MapCenter {
  latitude: number;
  longitude: number;
}

type LocationState = "idle" | "requesting" | "located" | "error";

const mapBounds = (center: MapCenter | null) => {
  if (!center) return "-180,-85,180,85";
  const minLat = Math.max(-85, center.latitude - 0.08);
  const maxLat = Math.min(85, center.latitude + 0.08);
  const minLon = Math.max(-180, center.longitude - 0.12);
  const maxLon = Math.min(180, center.longitude + 0.12);
  return `${minLon},${minLat},${maxLon},${maxLat}`;
};

export default function GeographyPage() {
  const [providers, setProviders] = useState<GeographyProviders | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<Place[]>([]);
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [routing, setRouting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mapCenter, setMapCenter] = useState<MapCenter | null>(null);
  const [locationState, setLocationState] = useState<LocationState>("idle");
  const [locationError, setLocationError] = useState<string | null>(null);
  const [location, setLocation] = useState<{
    latitude: number;
    longitude: number;
    accuracy: number;
    acquiredAt: string;
    source: string;
  } | null>(null);
  const [satelliteEnabled, setSatelliteEnabled] = useState<boolean>(false);
  const setPermissionState = useJarvisRuntime((state) => state.setPermissionState);
  const setSelectedObject = useJarvisRuntime((state) => state.setSelectedObject);
  const setCurrentTask = useJarvisRuntime((state) => state.setCurrentTask);

  useEffect(() => {
    let cancelled = false;
    void apiClient.get<GeographyProviders>(API_ENDPOINTS.geography.providers)
      .then((result) => {
        if (!cancelled) {
          setProviders(result);
          setProviderError(null);
        }
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setProviderError(requestError instanceof Error ? requestError.message : "Provider status could not be loaded.");
        }
      });
    return () => { cancelled = true; };
  }, []);

  const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || '';
  const geocodingReady = Boolean(providers?.geocoding.configured && providers.geocoding.user_agent_configured);
  const imageryConfirmed = Boolean(
    providers?.satellite_imagery.configured
    && providers.satellite_imagery.provider_license_confirmed
    && providers.satellite_imagery.license_confirmed,
  );
  const satelliteReady = Boolean(MAPBOX_TOKEN && imageryConfirmed);

  const mapUrl = useMemo(() => {
    const bbox = mapBounds(mapCenter);
    const marker = mapCenter
      ? `&marker=${encodeURIComponent(`${mapCenter.latitude},${mapCenter.longitude}`)}`
      : "";

    if (satelliteEnabled && MAPBOX_TOKEN && imageryConfirmed) {
      if (mapCenter) {
        const lon = mapCenter.longitude;
        const lat = mapCenter.latitude;
        const zoom = 14;
        return `https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/pin-s+ff0000(${lon},${lat})/${lon},${lat},${zoom}/1024x768@2x?access_token=${MAPBOX_TOKEN}`;
      }
      return `https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/0,0,1/1024x512@2x?access_token=${MAPBOX_TOKEN}`;
    }

    return `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik${marker}`;
  }, [mapCenter, satelliteEnabled, imageryConfirmed, MAPBOX_TOKEN]);

  const searchPlaces = useCallback(async (event: FormEvent<HTMLFormElement>) => {
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

  const requestLocation = () => {
    setLocationError(null);
    setLocationState("requesting");
    setPermissionState("geolocation", "requested");
    if (!navigator.geolocation) {
      setLocationState("error");
      setLocationError("This browser does not provide location services.");
      setPermissionState("geolocation", "unknown");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const result = {
          latitude: coords.latitude,
          longitude: coords.longitude,
          accuracy: coords.accuracy,
          acquiredAt: new Date().toISOString(),
          source: "Browser geolocation",
        };
        setLocation(result);
        setMapCenter(result);
        setLocationState("located");
        setPermissionState("geolocation", "granted");
        setSelectedObject({
          environment: "world",
          kind: "location",
          id: `${result.latitude},${result.longitude}`,
          label: "Current browser location",
        });
      },
      (positionError) => {
        setLocationState("error");
        if (positionError.code === positionError.PERMISSION_DENIED) {
          setLocationError("Location permission was denied. Allow it in your browser settings to try again.");
          setPermissionState("geolocation", "denied");
        } else if (positionError.code === positionError.POSITION_UNAVAILABLE) {
          setLocationError("Your position is currently unavailable. Check device location services and try again.");
          setPermissionState("geolocation", "unknown");
        } else if (positionError.code === positionError.TIMEOUT) {
          setLocationError("The location request timed out. Try again when your position is available.");
          setPermissionState("geolocation", "unknown");
        } else {
          setLocationError("Your browser could not determine a location.");
          setPermissionState("geolocation", "unknown");
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  };

  const setRouteEndpoint = (place: Place, endpoint: "origin" | "destination") => {
    if (endpoint === "origin") setOrigin(place);
    else setDestination(place);
    setMapCenter({ latitude: place.latitude, longitude: place.longitude });
    setSelectedObject({
      environment: "world",
      kind: "place",
      id: `${place.latitude},${place.longitude}`,
      label: place.name,
    });
    setRoute(null);
  };

  const calculateRoute = async () => {
    if (!origin || !destination) return;
    setRouting(true);
    setError(null);
    setCurrentTask({
      id: "geospatial-route",
      title: `Route from ${origin.name} to ${destination.name}`,
      status: "running",
      updatedAt: new Date().toISOString(),
    });
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
      setCurrentTask({
        id: "geospatial-route",
        title: `Route from ${origin.name} to ${destination.name}`,
        status: "completed",
        updatedAt: new Date().toISOString(),
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Route calculation failed.");
      setCurrentTask({
        id: "geospatial-route",
        title: `Route from ${origin.name} to ${destination.name}`,
        status: "failed",
        updatedAt: new Date().toISOString(),
      });
    } finally {
      setRouting(false);
    }
  };

  const locationReadout = location
    ? `${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}`
    : null;

  return (
    <main className="min-h-full bg-[#080d15] text-slate-100">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-white/[0.07] bg-[radial-gradient(ellipse_at_12%_0%,rgba(26,116,141,0.13),transparent_38%),#0a1019] px-4 py-5 sm:px-7">
        <div>
          <p className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-200/70">
            <Crosshair aria-hidden="true" className="h-3.5 w-3.5" />
            JARVIS <span className="text-slate-600">/</span> Spatial systems
          </p>
          <h1 className="text-2xl font-medium tracking-[-0.035em] text-white sm:text-3xl">Geospatial Vision</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-slate-400">
            A live OpenStreetMap view with real place search and directions from configured services.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="inline-flex items-center gap-2 rounded-md border border-white/[0.08] bg-white/[0.025] px-3 py-2 text-slate-300">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" aria-hidden="true" />
            OpenStreetMap · Mapnik
          </span>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSatelliteEnabled((s) => !s)}
              disabled={!satelliteReady}
              aria-pressed={satelliteEnabled && satelliteReady}
              className="rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-[11px] text-slate-200 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {satelliteEnabled && satelliteReady ? 'Satellite imagery' : 'Street map'}
            </button>

            <span className="text-xs text-slate-400">
              {satelliteReady
                ? 'Licensed imagery provider ready'
                : !MAPBOX_TOKEN
                  ? 'Satellite requires public imagery token'
                  : 'Satellite provider is not confirmed by the backend'}
            </span>
          </div>
        </div>
      </header>

      <div className="grid min-h-[calc(100vh-128px)] grid-cols-1 xl:grid-cols-[minmax(0,1fr)_356px]">
        <section aria-label="Map view" className="relative min-h-[430px] border-b border-white/[0.07] bg-[#0a1119] xl:min-h-[calc(100vh-128px)] xl:border-b-0 xl:border-r">
          {satelliteEnabled && satelliteReady ? (
            <div
              key={mapUrl}
              role="img"
              aria-label={mapCenter ? "Satellite imagery centered on the selected location" : "Satellite imagery of the world"}
              className="absolute inset-0 h-full w-full bg-cover bg-center"
              style={{ backgroundImage: `url("${mapUrl}")` }}
            />
          ) : (
            <iframe
              key={mapUrl}
              title="OpenStreetMap location map"
              src={mapUrl}
              className="absolute inset-0 h-full w-full border-0"
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          )}
          <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-[#080d15]/75 to-transparent" aria-hidden="true" />
          <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 rounded-md border border-slate-900/10 bg-white/90 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-700 shadow-lg sm:left-6 sm:top-6">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-600" aria-hidden="true" />
            {mapCenter ? "Centered on selected coordinates" : "World view · no location selected"}
          </div>
          <div className="absolute bottom-4 left-4 right-4 flex flex-wrap items-center justify-between gap-2 sm:bottom-6 sm:left-6 sm:right-6">
            <div className="max-w-md rounded-md border border-slate-900/10 bg-white/90 px-3 py-2 text-[10px] leading-relaxed text-slate-700 shadow-lg">
              Map data © <a className="font-semibold underline underline-offset-2" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>.
              {" "}Directions are returned as instructions; this map does not draw a route line.
            </div>
            {mapCenter && (
              <span className="rounded-md border border-slate-900/10 bg-white/90 px-3 py-2 font-mono text-[10px] text-slate-700 shadow-lg">
                {mapCenter.latitude.toFixed(5)}, {mapCenter.longitude.toFixed(5)}
              </span>
            )}
          </div>
        </section>

        <aside aria-label="Geospatial controls" className="flex flex-col gap-5 px-4 py-5 sm:px-6 xl:max-h-[calc(100vh-128px)] xl:overflow-y-auto">
          <section aria-labelledby="location-heading" className="border-b border-white/[0.08] pb-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-cyan-200/55">01 / Location</p>
                <h2 id="location-heading" className="mt-1 text-sm font-semibold text-slate-100">Center the map</h2>
              </div>
              <MapPin aria-hidden="true" className="h-4 w-4 text-cyan-300/75" />
            </div>
            <p className="mb-3 text-xs leading-relaxed text-slate-400">
              Your position is requested once, only when you choose this action. Nothing is tracked in the background.
            </p>
            <button
              type="button"
              onClick={requestLocation}
              disabled={locationState === "requesting"}
              className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md border border-cyan-200/20 bg-cyan-300/[0.09] px-4 text-xs font-semibold text-cyan-100 transition hover:border-cyan-100/35 hover:bg-cyan-300/[0.14] focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200 disabled:cursor-wait disabled:opacity-60"
            >
              {locationState === "requesting"
                ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                : <LocateFixed aria-hidden="true" className="h-4 w-4" />}
              {locationState === "requesting" ? "Requesting location…" : "Use my location"}
            </button>
            {location && locationReadout && (
              <div role="status" className="mt-3 border-l border-cyan-300/50 pl-3">
                <p className="flex items-center gap-1.5 text-[11px] font-medium text-cyan-100">
                  <Check aria-hidden="true" className="h-3.5 w-3.5" />
                  Location received
                </p>
                <p className="mt-1 font-mono text-[11px] text-slate-200">{locationReadout}</p>
                <p className="mt-1 text-[10px] text-slate-500">Reported accuracy: ±{Math.round(location.accuracy)} m</p>
                <p className="mt-1 text-[10px] text-slate-500">
                  Source: {location.source} · {new Date(location.acquiredAt).toLocaleString()}
                </p>
              </div>
            )}
            {locationError && (
              <p role="alert" className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-amber-200">
                <AlertCircle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {locationError}
              </p>
            )}
          </section>

          <section aria-labelledby="search-heading" className="border-b border-white/[0.08] pb-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-indigo-200/55">02 / Geocoding</p>
                <h2 id="search-heading" className="mt-1 text-sm font-semibold text-slate-100">Find a place</h2>
              </div>
              <Search aria-hidden="true" className="h-4 w-4 text-indigo-200/70" />
            </div>
            <form onSubmit={searchPlaces} className="flex gap-2">
              <input
                aria-label="Place search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="City, address, landmark"
                disabled={!geocodingReady || searching}
                className="h-10 min-w-0 flex-1 rounded-md border border-white/[0.11] bg-[#0b121d] px-3 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-200/40 focus:ring-2 focus:ring-cyan-300/10 disabled:opacity-50"
              />
              <button
                type="submit"
                aria-label="Search places"
                disabled={!geocodingReady || searching || !query.trim()}
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-white/[0.11] bg-white/[0.04] text-slate-300 transition hover:bg-white/[0.08] focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {searching ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Search aria-hidden="true" className="h-4 w-4" />}
              </button>
            </form>
            {providers ? (
              <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                {geocodingReady
                  ? "Search uses the configured geocoding provider."
                  : providers.geocoding.configured
                    ? "Geocoding needs an identifiable provider user agent."
                    : "A configured geocoding provider is required to search."}
              </p>
            ) : (
              <p className="mt-2 text-[10px] text-slate-500">{providerError ? "Geocoding status unavailable." : "Checking geocoding availability…"}</p>
            )}
            {places.length > 0 && (
              <ol aria-label="Place search results" className="mt-3 max-h-52 divide-y divide-white/[0.07] overflow-y-auto border-y border-white/[0.07]">
                {places.map((place, index) => (
                  <li key={`${place.latitude}-${place.longitude}-${index}`} className="py-3">
                    <p className="text-xs font-medium leading-relaxed text-slate-200">{place.name}</p>
                    <p className="mt-1 font-mono text-[10px] text-slate-500">
                      {place.latitude.toFixed(5)}, {place.longitude.toFixed(5)}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-[10px]">
                      <button type="button" onClick={() => setRouteEndpoint(place, "origin")} className="text-slate-400 underline decoration-white/20 underline-offset-2 hover:text-cyan-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200">Set origin</button>
                      <button type="button" onClick={() => setRouteEndpoint(place, "destination")} className="text-slate-400 underline decoration-white/20 underline-offset-2 hover:text-cyan-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200">Set destination</button>
                      <button type="button" onClick={() => {
                        setMapCenter(place);
                        setSelectedObject({
                          environment: "world",
                          kind: "place",
                          id: `${place.latitude},${place.longitude}`,
                          label: place.name,
                        });
                      }} className="inline-flex items-center gap-1 text-cyan-200/80 hover:text-cyan-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200">
                        Center <ChevronRight aria-hidden="true" className="h-3 w-3" />
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section aria-labelledby="directions-heading">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-500">03 / Routing</p>
                <h2 id="directions-heading" className="mt-1 text-sm font-semibold text-slate-100">Directions</h2>
              </div>
              <Navigation aria-hidden="true" className="h-4 w-4 text-slate-400" />
            </div>
            <div className="space-y-2.5">
              <p className="truncate border-l border-cyan-300/40 pl-2.5 text-[11px] text-slate-300">
                <span className="mr-1.5 text-[9px] uppercase tracking-wider text-slate-500">From</span>
                {origin?.name ?? "Choose a search result"}
              </p>
              <p className="truncate border-l border-indigo-300/40 pl-2.5 text-[11px] text-slate-300">
                <span className="mr-1.5 text-[9px] uppercase tracking-wider text-slate-500">To</span>
                {destination?.name ?? "Choose a search result"}
              </p>
              <button
                type="button"
                onClick={() => void calculateRoute()}
                disabled={!providers?.routing.configured || !origin || !destination || routing}
                className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-md border border-white/[0.11] bg-white/[0.04] px-3 text-xs font-medium text-slate-200 transition hover:border-white/20 hover:bg-white/[0.07] focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {routing ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Signpost aria-hidden="true" className="h-4 w-4" />}
                {routing ? "Calculating…" : "Get directions"}
              </button>
              <p className="text-[10px] leading-relaxed text-slate-500">
                {providers?.routing.configured
                  ? "Routing provider is configured. Directions are shown as steps; no route is drawn on the map."
                  : "Directions require a configured routing provider."}
              </p>
            </div>
            {route && (
              <div className="mt-4 border-t border-white/[0.08] pt-3">
                <p className="flex items-center justify-between gap-2 text-[11px] text-slate-300">
                  <span>{(route.distance_meters / 1000).toFixed(1)} km</span>
                  <span>{Math.round(route.duration_seconds / 60)} min</span>
                  <span className="truncate text-slate-500">{route.source}</span>
                </p>
                <ol aria-label="Route directions" className="mt-3 max-h-52 space-y-2 overflow-y-auto">
                  {route.steps.map((step, index) => (
                    <li key={`${index}-${step.instruction}`} className="flex gap-2 text-[11px] leading-relaxed text-slate-300">
                      <span className="mt-0.5 font-mono text-[9px] text-slate-500">{String(index + 1).padStart(2, "0")}</span>
                      <span className="min-w-0 flex-1">{step.instruction}<span className="ml-1.5 whitespace-nowrap text-[10px] text-slate-500">{(step.distance_meters / 1000).toFixed(2)} km</span></span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </section>

          <section aria-label="Provider readiness" className="mt-auto border-t border-white/[0.08] pt-4">
            <p className="mb-3 text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-500">Provider readiness</p>
            {providerError ? (
              <p role="status" className="text-[10px] text-amber-200">Status could not be loaded. {providerError}</p>
            ) : providers ? (
              <dl className="space-y-2 text-[10px]">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-500">Geocoding</dt>
                  <dd className={geocodingReady ? "text-emerald-200" : "text-amber-200"}>{geocodingReady ? "Ready" : providers.geocoding.configured ? "Needs user agent" : "Unavailable"}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-500">Routing</dt>
                  <dd className={providers.routing.configured ? "text-emerald-200" : "text-amber-200"}>{providers.routing.configured ? "Ready" : "Unavailable"}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-500">Satellite imagery</dt>
                  <dd className="text-slate-400">{imageryConfirmed ? "Configured · not displayed" : "Unavailable"}</dd>
                </div>
              </dl>
            ) : (
              <p role="status" className="flex items-center gap-2 text-[10px] text-slate-500">
                <Loader2 aria-hidden="true" className="h-3 w-3 animate-spin" />
                Checking configured services…
              </p>
            )}
            {providers?.attribution && (
              <p className="mt-3 text-[9px] leading-relaxed text-slate-600">Provider attribution: {providers.attribution}</p>
            )}
          </section>
        </aside>
      </div>

      {error && (
        <div role="alert" className="fixed bottom-4 left-4 right-4 z-10 mx-auto flex max-w-xl items-start gap-2 rounded-md border border-rose-300/20 bg-[#1b1118] px-4 py-3 text-xs text-rose-100 shadow-xl">
          <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
          <span className="flex-1">{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-rose-100/70 underline underline-offset-2 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-200">Dismiss</button>
        </div>
      )}

      <WorldCapabilityPanel
        satelliteAvailable={satelliteReady}
        geolocationState={locationState}
        geocodingAvailable={geocodingReady}
        routingAvailable={Boolean(providers?.routing.configured)}
      />
    </main>
  );
}

function WorldCapabilityPanel({
  satelliteAvailable,
  geolocationState,
  geocodingAvailable,
  routingAvailable,
}: {
  satelliteAvailable: boolean;
  geolocationState: LocationState;
  geocodingAvailable: boolean;
  routingAvailable: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <div className="fixed bottom-6 left-6 z-40">
        <button
          type="button"
          onClick={() => setOpen((s) => !s)}
          className="inline-flex items-center gap-2 rounded-md bg-white/[0.03] px-3 py-2 text-[11px] text-slate-200 hover:bg-white/[0.05] border border-white/[0.06]"
          title="Inspect world environment capabilities"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.2" />
            <path d="M3 12h18" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          World status
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="mx-4 max-w-3xl rounded-lg border border-white/[0.06] bg-[#041018] p-6 text-slate-100">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold">JARVIS World View</h3>
                <p className="mt-2 text-sm text-slate-400">
                  This view reports connected world capabilities. It does not imply AR, terrain, tracking, or device control that is not available.
                </p>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <CapabilityStatus label="Street map" value="Available · OpenStreetMap" />
                  <CapabilityStatus
                    label="Current location"
                    value={geolocationState === "located"
                      ? "Available · user-authorized"
                      : geolocationState === "requesting"
                        ? "Location request in progress"
                        : geolocationState === "error"
                          ? "Unavailable · request failed"
                          : "Requires user permission"}
                  />
                  <CapabilityStatus label="Satellite imagery" value={satelliteAvailable ? "Available" : "Requires configured imagery provider"} />
                  <CapabilityStatus label="Place search" value={geocodingAvailable ? "Available" : "Requires geocoding provider"} />
                  <CapabilityStatus label="Directions" value={routingAvailable ? "Available · steps only" : "Requires routing provider"} />
                  <CapabilityStatus label="Terrain / 3D Earth" value="Unavailable · no provider connected" />
                  <CapabilityStatus label="AR / device pose" value="Unavailable · no authorized device connector" />
                  <CapabilityStatus label="Weather / environment" value="Unavailable · no provider connected" />
                </dl>
              </div>
              <div className="shrink-0 text-right">
                <div className="mt-4 flex justify-end gap-2">
                  <button onClick={() => setOpen(false)} className="rounded-md border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-[12px] text-slate-200">Close</button>
                </div>
              </div>
            </div>
            <p className="mt-5 text-xs leading-relaxed text-slate-500">
              Location is requested only when you select “Use my location.” Route results are provider instructions; route geometry is not currently rendered.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function CapabilityStatus({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/[0.06] bg-white/[0.02] p-3">
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-xs text-slate-200">{value}</dd>
    </div>
  );
}
