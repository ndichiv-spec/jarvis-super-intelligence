"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { FeatureCollection, Point } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap, Marker as MapLibreMarker, StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  Crosshair,
  Loader2,
  MapPin,
  MessageSquare,
  Navigation,
  Newspaper,
  Satellite,
  Search,
  Sparkles,
  Waypoints,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  jarvisAPI,
  type GeographyCapabilityStatus,
  type GeographySourceVerification,
} from "@/lib/api";

type Basemap = "aerial" | "nasa" | "streets";
type Coordinates = { latitude: number; longitude: number };

interface PublicEventProperties {
  title: string;
  magnitude: number;
  time: number;
  url: string;
}

interface NewsArticle {
  title: string;
  url: string;
  domain: string;
  seen: string;
}

type PublicEvents = FeatureCollection<Point, PublicEventProperties>;

function nasaImageryStyle(): StyleSpecification {
  const date = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  return {
    version: 8,
    sources: {
      nasa: {
        type: "raster",
        tiles: [`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`],
        tileSize: 256,
        maxzoom: 9,
        attribution: "NASA Global Imagery Browse Services (GIBS), EOSDIS",
      },
    },
    layers: [{ id: "nasa", type: "raster", source: "nasa" }],
  };
}

const BASEMAPS: Record<Basemap, StyleSpecification> = {
  aerial: {
    version: 8,
    sources: {
      imagery: {
        type: "raster",
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        tileSize: 256,
        attribution: "Tiles &copy; Esri — Sources: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
      },
    },
    layers: [{ id: "imagery", type: "raster", source: "imagery" }],
  },
  streets: {
    version: 8,
    sources: {
      streets: {
        type: "raster",
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"],
        tileSize: 256,
        attribution: "Tiles &copy; Esri",
      },
    },
    layers: [{ id: "streets", type: "raster", source: "streets" }],
  },
  nasa: nasaImageryStyle(),
};

const EMPTY_EVENTS: PublicEvents = { type: "FeatureCollection", features: [] };

function coordinatesFromQuery(query: string): Coordinates | null {
  const match = query.trim().match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/);
  if (!match) return null;
  const latitude = Number(match[1]);
  const longitude = Number(match[2]);
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
  return { latitude, longitude };
}

export default function LocationsPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<MapLibreMarker | null>(null);
  const basemapRef = useRef<Basemap>("aerial");
  const eventLayerUpdaterRef = useRef<(map: MapLibreMap) => void>(() => {});
  const [basemap, setBasemap] = useState<Basemap>("aerial");
  const [query, setQuery] = useState("");
  const [question, setQuestion] = useState("");
  const [selected, setSelected] = useState<{ coords: Coordinates; label: string } | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [answer, setAnswer] = useState("");
  const [geographyCapabilities, setGeographyCapabilities] = useState<GeographyCapabilityStatus[] | null>(null);
  const [geographyError, setGeographyError] = useState("");
  const [events, setEvents] = useState<PublicEvents>(EMPTY_EVENTS);
  const [eventsError, setEventsError] = useState("");
  const [isLoadingEvents, setIsLoadingEvents] = useState(true);
  const [showEvents, setShowEvents] = useState(true);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [newsError, setNewsError] = useState("");
  const [isLoadingNews, setIsLoadingNews] = useState(false);
  const [sourceVerification, setSourceVerification] = useState<GeographySourceVerification | null>(null);
  const [isVerifyingSources, setIsVerifyingSources] = useState(false);

  const ensureEventLayer = useCallback((map: MapLibreMap) => {
    if (!map.getSource("public-events")) {
      map.addSource("public-events", { type: "geojson", data: events });
    }
    if (!map.getLayer("public-events-points")) {
      map.addLayer({
        id: "public-events-points",
        source: "public-events",
        type: "circle",
        paint: {
          "circle-color": ["interpolate", ["linear"], ["get", "magnitude"], 0, "#22d3ee", 4, "#facc15", 6, "#fb7185"],
          "circle-radius": ["interpolate", ["linear"], ["get", "magnitude"], 0, 5, 7, 13],
          "circle-stroke-color": "#07111d",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.88,
        },
      });
    }
    const source = map.getSource("public-events");
    if (source?.type === "geojson") {
      (source as GeoJSONSource).setData(events);
    }
    map.setLayoutProperty("public-events-points", "visibility", showEvents ? "visible" : "none");
  }, [events, showEvents]);

  useEffect(() => {
    eventLayerUpdaterRef.current = ensureEventLayer;
  }, [ensureEventLayer]);

  useEffect(() => {
    let active = true;
    void jarvisAPI.getGeographyCapabilities()
      .then((capabilities) => {
        if (active) setGeographyCapabilities(capabilities);
      })
      .catch((error: unknown) => {
        if (active) setGeographyError(error instanceof Error ? error.message : "Geography capability status unavailable");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson", {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`USGS feed returned HTTP ${response.status}`);
        return await response.json() as {
          features?: Array<{
            geometry?: { type?: string; coordinates?: number[] };
            properties?: { title?: string; mag?: number | null; time?: number; url?: string };
          }>;
        };
      })
      .then((data) => {
        const features = (data.features ?? []).flatMap((feature) => {
          const coordinates = feature.geometry?.coordinates;
          const properties = feature.properties;
          if (
            feature.geometry?.type !== "Point"
            || !coordinates
            || coordinates.length < 2
            || !properties
            || !Number.isFinite(coordinates[0])
            || !Number.isFinite(coordinates[1])
          ) return [];
          return [{
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [coordinates[0], coordinates[1]] as [number, number] },
            properties: {
              title: properties.title || "Earthquake event",
              magnitude: typeof properties.mag === "number" ? properties.mag : 0,
              time: typeof properties.time === "number" ? properties.time : 0,
              url: properties.url || "https://earthquake.usgs.gov/earthquakes/",
            },
          }];
        });
        setEvents({ type: "FeatureCollection", features });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setEventsError(error instanceof Error ? error.message : "USGS public events feed is unavailable");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingEvents(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    let active = true;
    let map: MapLibreMap | null = null;
    let marker: MapLibreMarker | null = null;

    void import("maplibre-gl").then(({ Map, Marker, NavigationControl }) => {
      if (!active || !containerRef.current) return;
      const createdMap = new Map({
        container: containerRef.current,
        style: BASEMAPS[basemapRef.current],
        center: [0, 20],
        zoom: 2,
        attributionControl: { compact: true },
      });
      createdMap.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
      marker = new Marker({ color: "#22d3ee" });
      createdMap.on("style.load", () => eventLayerUpdaterRef.current(createdMap));
      createdMap.once("load", () => eventLayerUpdaterRef.current(createdMap));
      createdMap.on("click", "public-events-points", (event) => {
        const feature = event.features?.[0];
        const properties = feature?.properties;
        const point = feature?.geometry;
        if (!properties || point?.type !== "Point") return;
        const longitude = point.coordinates[0];
        const latitude = point.coordinates[1];
        const title = typeof properties.title === "string" ? properties.title : "Earthquake event";
        const magnitude = typeof properties.magnitude === "number" ? properties.magnitude : 0;
        setSelected({
          coords: { latitude, longitude },
          label: `${title} · M${magnitude.toFixed(1)}`,
        });
      });
      createdMap.on("mouseenter", "public-events-points", () => {
        createdMap.getCanvas().style.setProperty("cursor", "pointer");
      });
      createdMap.on("mouseleave", "public-events-points", () => {
        createdMap.getCanvas().style.removeProperty("cursor");
      });
      map = createdMap;
      mapRef.current = createdMap;
      markerRef.current = marker;
    });

    return () => {
      active = false;
      marker?.remove();
      map?.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
  }, []);

  const placeMarker = useCallback((coords: Coordinates, label: string, zoom = 13) => {
    const map = mapRef.current;
    const marker = markerRef.current;
    if (!map || !marker) {
      toast.error("The map is still loading");
      return;
    }
    marker.setLngLat([coords.longitude, coords.latitude]).addTo(map);
    map.flyTo({ center: [coords.longitude, coords.latitude], zoom, essential: true });
    setSelected({ coords, label });
  }, []);

  useEffect(() => {
    const previousBasemap = basemapRef.current;
    basemapRef.current = basemap;
    if (previousBasemap !== basemap) {
      mapRef.current?.setStyle(BASEMAPS[basemap]);
    }
  }, [basemap]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.isStyleLoaded()) ensureEventLayer(map);
  }, [ensureEventLayer]);

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = query.trim();
    if (!value) return;

    const directCoordinates = coordinatesFromQuery(value);
    if (directCoordinates) {
      placeMarker(directCoordinates, `${directCoordinates.latitude.toFixed(5)}, ${directCoordinates.longitude.toFixed(5)}`);
      return;
    }

    setIsSearching(true);
    try {
      const params = new URLSearchParams({ q: value, format: "jsonv2", limit: "1" });
      const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`Place search failed (${response.status})`);
      const results = await response.json() as Array<{ lat: string; lon: string; display_name: string }>;
      const result = results[0];
      if (!result) {
        toast.error("No matching place was found");
        return;
      }
      const coords = { latitude: Number(result.lat), longitude: Number(result.lon) };
      placeMarker(coords, result.display_name);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Place search failed");
    } finally {
      setIsSearching(false);
    }
  };

  const locateMe = () => {
    if (!navigator.geolocation) {
      toast.error("Location access is not supported by this browser");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        placeMarker({ latitude: coords.latitude, longitude: coords.longitude }, "Your current location", 15);
      },
      (error) => toast.error(`Could not get your location: ${error.message}`),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const applyMapCommands = async (prompt: string): Promise<{ actions: string[]; location?: { coords: Coordinates; label: string } }> => {
    const actions: string[] = [];
    if (/\b(nasa|viirs)\b/i.test(prompt) && basemap !== "nasa") {
      setBasemap("nasa");
      actions.push("Switched the map to public NASA VIIRS browse imagery.");
    } else if (/\b(street|roads?)\b/i.test(prompt) && basemap !== "streets") {
      setBasemap("streets");
      actions.push("Switched the map to the street layer.");
    } else if (/\b(aerial|satellite|imagery)\b/i.test(prompt) && basemap !== "aerial") {
      setBasemap("aerial");
      actions.push("Switched the map to Esri aerial imagery.");
    }

    if (/\b(?:show|enable|turn on)\b.*\b(?:earthquakes?|seismic|public events)\b/i.test(prompt) && !showEvents) {
      setShowEvents(true);
      actions.push("Enabled the public USGS earthquake layer.");
    } else if (/\b(?:hide|disable|turn off)\b.*\b(?:earthquakes?|seismic|public events)\b/i.test(prompt) && showEvents) {
      setShowEvents(false);
      actions.push("Disabled the public USGS earthquake layer.");
    }

    const coordinateMatch = prompt.match(/(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)/);
    if (coordinateMatch) {
      const coords = coordinatesFromQuery(coordinateMatch[0]);
      if (coords) {
        const label = `${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`;
        placeMarker(coords, label);
        actions.push(`Centered the map on ${label}.`);
        return { actions, location: { coords, label } };
      }
    }

    const placeMatch = prompt.match(/\b(?:zoom|center|locate|fly)\s+(?:to|on|in)\s+([a-z][\w ,.'-]{1,70})/i);
    const place = placeMatch?.[1]?.trim().replace(/[?.!,;]+$/, "");
    if (place) {
      const params = new URLSearchParams({ q: place, format: "jsonv2", limit: "1" });
      const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`Place search failed (${response.status})`);
      const results = await response.json() as Array<{ lat: string; lon: string; display_name: string }>;
      const result = results[0];
      if (result) {
        const coords = { latitude: Number(result.lat), longitude: Number(result.lon) };
        placeMarker(coords, result.display_name);
        actions.push(`Centered the map on ${result.display_name}.`);
        return { actions, location: { coords, label: result.display_name } };
      }
    }
    return { actions };
  };

  const askJarvis = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const prompt = question.trim();
    if (!prompt) return;
    setIsAsking(true);
    setAnswer("");
    try {
      const mapCommands = await applyMapCommands(prompt);
      const contextLocation = mapCommands.location || selected;
      const context = contextLocation
        ? `Selected map location: ${contextLocation.label} (${contextLocation.coords.latitude}, ${contextLocation.coords.longitude}).`
        : "No specific map location is selected.";
      const publicEvents = events.features
        .filter((feature) => {
          if (!selected) return true;
          const [longitude, latitude] = feature.geometry.coordinates;
          return Math.abs(latitude - selected.coords.latitude) <= 5
            && Math.abs(longitude - selected.coords.longitude) <= 5;
        })
        .slice(0, 8)
        .map(({ properties, geometry }) => ({
          title: properties.title,
          magnitude: properties.magnitude,
          time: new Date(properties.time).toISOString(),
          coordinates: geometry.coordinates,
          source: properties.url,
        }));
      const result = await jarvisAPI.starkChat({
        message: prompt,
        context: {
          surface: "locations",
          map_context: context,
          map_actions_applied: mapCommands.actions,
          geography_capabilities: geographyCapabilities?.map(({ capability_id, status }) => ({ capability_id, status })),
          public_data: {
            earthquake_source: "USGS all earthquakes, past 7 days",
            events: publicEvents,
            news: news.slice(0, 5),
          },
          response_guidance: "Act as a careful geography expert. Use only provided public data or sources you can verify. Cite source URLs for event and news claims, and identify missing or stale data. Do not claim classified, military, private, or real-time intelligence access, and do not provide target selection or operational military guidance.",
        },
      });
      if (!result.success) throw new Error(result.response || "JARVIS could not answer");
      setAnswer(result.response);
      setQuestion("");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "JARVIS request failed");
    } finally {
      setIsAsking(false);
    }
  };

  const loadNews = async () => {
    setIsLoadingNews(true);
    setNewsError("");
    try {
      const topic = selected?.label.split(" · ")[0] || "world";
      const params = new URLSearchParams({
        query: `(${topic} OR world)`,
        mode: "ArtList",
        format: "json",
        maxrecords: "5",
        sort: "HybridRel",
      });
      const response = await fetch(`https://api.gdeltproject.org/api/v2/doc/doc?${params}`);
      if (!response.ok) throw new Error(`GDELT returned HTTP ${response.status}`);
      const payload = await response.json() as {
        articles?: Array<{ title?: string; url?: string; domain?: string; seendate?: string }>;
      };
      const articles = (payload.articles ?? []).flatMap((article) => {
        if (!article.title || !article.url) return [];
        try {
          const url = new URL(article.url);
          if (url.protocol !== "https:" && url.protocol !== "http:") return [];
          return [{
            title: article.title,
            url: url.toString(),
            domain: article.domain || url.hostname,
            seen: article.seendate || "",
          }];
        } catch {
          return [];
        }
      });
      setNews(articles);
    } catch (error) {
      setNewsError(error instanceof Error ? error.message : "Public news feed is unavailable");
    } finally {
      setIsLoadingNews(false);
    }
  };

  const verifySources = async () => {
    setIsVerifyingSources(true);
    try {
      setSourceVerification(await jarvisAPI.verifyGeographySources());
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "JARVIS could not verify public data sources");
    } finally {
      setIsVerifyingSources(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-[1680px] flex-col gap-5 px-4 py-5 md:px-6">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200/70">JARVIS · Locations workspace</p>
          <h1 className="mt-1 text-2xl font-semibold text-white md:text-3xl">Map &amp; locations</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">
            Search a place or coordinates, inspect public map layers, and ask JARVIS about the selected area.
          </p>
        </div>
        <div role="group" aria-label="Map sources" className="flex flex-wrap gap-2">
          <Button aria-pressed={basemap === "aerial"} variant={basemap === "aerial" ? "default" : "outline"} onClick={() => setBasemap("aerial")}>
            <Satellite className="mr-2 h-4 w-4" /> Esri imagery
          </Button>
          <Button aria-pressed={basemap === "nasa"} variant={basemap === "nasa" ? "default" : "outline"} onClick={() => setBasemap("nasa")}>
            <Satellite className="mr-2 h-4 w-4" /> NASA VIIRS
          </Button>
          <Button aria-pressed={basemap === "streets"} variant={basemap === "streets" ? "default" : "outline"} onClick={() => setBasemap("streets")}>
            <Waypoints className="mr-2 h-4 w-4" /> Streets
          </Button>
        </div>
      </header>

      <div className="grid flex-1 gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="overflow-hidden border-white/10 bg-[#0b111b]">
          <CardHeader className="border-b border-white/[0.07]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg text-white">
                  <Satellite className="h-5 w-5 text-cyan-300" /> Interactive map
                </CardTitle>
                <CardDescription className="mt-1">
                  {basemap === "nasa"
                    ? "NASA VIIRS corrected true-color browse imagery · about two days behind · coarse resolution"
                    : basemap === "aerial"
                      ? "Esri World Imagery · coverage and update frequency vary by area"
                      : "Esri World Street Map"}
                  {" · "}Map controls powered by MapLibre
                </CardDescription>
              </div>
              <Badge variant="outline">{basemap === "nasa" ? "NASA VIIRS · public" : basemap === "aerial" ? "Esri World Imagery" : "Esri street map"}</Badge>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div ref={containerRef} role="region" className="h-[55vh] min-h-[380px] w-full bg-slate-950" aria-label="Interactive map" />
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.07] px-4 py-3 text-xs text-slate-400">
              <span className="flex items-center gap-2">
                <MapPin className="h-3.5 w-3.5 text-cyan-300" />
                {selected ? selected.label : "Search for a place or use your location"}
              </span>
              <span className="basis-full leading-relaxed sm:basis-auto sm:text-right">
                {basemap === "nasa"
                  ? "NASA Global Imagery Browse Services (GIBS), EOSDIS"
                  : basemap === "aerial"
                    ? "Tiles © Esri · Sources: Esri, Maxar, Earthstar Geographics, GIS User Community"
                    : "Tiles © Esri"}
                {" · "}Place search © OpenStreetMap contributors
              </span>
            </div>
            <p className="border-t border-white/[0.06] px-4 py-2.5 text-[11px] leading-relaxed text-slate-500">
              Imagery is not live satellite control. This workspace does not provide street-level photos, terrain/3D views, or routing.
            </p>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-5">
          <Card className="border-white/10 bg-[#0b111b]">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base text-white">
                <Waypoints className="h-4 w-4 text-cyan-300" /> Public data layers
              </CardTitle>
              <CardDescription>Recent global seismicity and sourced current-affairs headlines.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button type="button" variant="outline" className="w-full" onClick={() => void verifySources()} disabled={isVerifyingSources}>
                {isVerifyingSources ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                Verify sources with JARVIS Python service
              </Button>
              {sourceVerification && (
                <div className="space-y-2 rounded-lg border border-white/[0.07] p-3" aria-live="polite">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-200">Source check: {sourceVerification.status}</span>
                    <span className="text-slate-400">{sourceVerification.available}/{sourceVerification.total} reachable</span>
                  </div>
                  <ul className="space-y-1.5">
                    {sourceVerification.sources.map((source) => (
                      <li key={source.id} className="flex items-start justify-between gap-2 text-[11px]">
                        <span className="text-slate-300">{source.label}</span>
                        <span className={source.status === "available" ? "shrink-0 text-emerald-200" : "shrink-0 text-amber-200"}>
                          {source.status}{source.latency_ms >= 0 ? ` · ${source.latency_ms} ms` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-[10px] text-slate-500">Checked {new Date(sourceVerification.checked_at).toLocaleString()} · results show connectivity, not data accuracy.</p>
                </div>
              )}
              <Button
                type="button"
                variant={showEvents ? "default" : "outline"}
                className="w-full justify-between"
                aria-pressed={showEvents}
                onClick={() => setShowEvents((visible) => !visible)}
              >
                <span>USGS earthquakes · past 7 days</span>
                <Badge variant="outline">
                  {isLoadingEvents ? "Loading" : eventsError ? "Unavailable" : events.features.length.toLocaleString()}
                </Badge>
              </Button>
              {eventsError && <p role="status" className="text-xs text-amber-200">{eventsError}</p>}
              <Button type="button" variant="outline" className="w-full" onClick={() => void loadNews()} disabled={isLoadingNews}>
                {isLoadingNews ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Newspaper className="mr-2 h-4 w-4" />}
                {selected ? "News near selected place" : "Load world news"}
              </Button>
              {newsError && <p role="status" className="text-xs text-amber-200">{newsError}</p>}
              {news.length > 0 && (
                <ul className="max-h-48 space-y-2 overflow-y-auto">
                  {news.map((article) => (
                    <li key={article.url} className="rounded-md border border-white/[0.07] p-2.5">
                      <a href={article.url} target="_blank" rel="noopener noreferrer" className="text-xs font-medium leading-relaxed text-cyan-100 hover:underline">
                        {article.title}
                      </a>
                      <p className="mt-1 text-[11px] text-slate-500">{article.domain}{article.seen ? ` · ${article.seen}` : ""}</p>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] leading-relaxed text-slate-500">
                Public, non-classified sources only. Imagery is for general geographic awareness, not tactical or targeting use.
              </p>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-[#0b111b]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base text-white">
                <Search className="h-4 w-4 text-cyan-300" /> Locate
              </CardTitle>
              <CardDescription>Search for a place or enter latitude, longitude.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <form onSubmit={handleSearch} className="flex gap-2">
                <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="City, address, or 40.7, -74.0" />
                <Button type="submit" size="icon" disabled={isSearching || !query.trim()} aria-label="Search location">
                  {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                </Button>
              </form>
              <Button type="button" variant="outline" className="w-full" onClick={locateMe}>
                <Crosshair className="mr-2 h-4 w-4" /> Center on my location
              </Button>
              <p className="text-xs leading-relaxed text-slate-500">
                Place names use OpenStreetMap search; coordinates can be entered directly. The base map provider is Esri.
              </p>
              {selected && (
                <div className="rounded-lg border border-cyan-200/10 bg-cyan-200/[0.04] p-3 text-xs text-slate-300">
                  <p className="font-medium text-cyan-100">Selected coordinates</p>
                  <p className="mt-1">{selected.coords.latitude.toFixed(6)}, {selected.coords.longitude.toFixed(6)}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="flex-1 border-white/10 bg-[#0b111b]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base text-white">
                <Sparkles className="h-4 w-4 text-cyan-300" /> JARVIS map assistant
              </CardTitle>
              <CardDescription>Ask about a place; JARVIS receives the selected map context.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <form onSubmit={askJarvis} className="space-y-2">
                <Input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What should I know about this area?" />
                <Button type="submit" disabled={isAsking || !question.trim()} className="w-full">
                  {isAsking ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MessageSquare className="mr-2 h-4 w-4" />}
                  Ask JARVIS
                </Button>
              </form>
              {answer && (
                <div className="max-h-64 overflow-y-auto rounded-lg border border-white/10 bg-black/20 p-3 text-sm leading-relaxed text-slate-300" aria-live="polite">
                  {answer}
                </div>
              )}
              <div className="rounded-lg border border-white/[0.07] bg-black/10 p-3 text-xs text-slate-400">
                <p className="font-medium text-slate-200">JARVIS geography runtime</p>
                {geographyCapabilities ? (
                  <>
                    <p className="mt-1">
                      {geographyCapabilities.filter((capability) => capability.supports_offline && capability.status.toLowerCase() === "available").length} offline tools available
                    </p>
                    <p className="mt-1">
                      Online place search: {geographyCapabilities.find((capability) => capability.capability_id === "geography.place_search")?.status ?? "not reported"}
                    </p>
                  </>
                ) : (
                  <p role={geographyError ? "alert" : "status"} className="mt-1">
                    {geographyError || "Loading backend capability status..."}
                  </p>
                )}
              </div>
              <p className="flex items-start gap-2 text-xs leading-relaxed text-slate-500">
                <Navigation className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Your browser only shares location after you select “Center on my location.”
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
