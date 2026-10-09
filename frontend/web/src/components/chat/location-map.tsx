'use client';

import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { LocateFixed, Minus, Plus } from 'lucide-react';
import type { PresentationIntent } from '@/features/runtime/presentation-contract';
import { API_ENDPOINTS } from '@/config/api';
import { apiClient } from '@/lib/api-client';

interface LocationData {
  latitude: number;
  longitude: number;
  accuracyMeters?: number;
  timestamp: string;
  source: string;
  freshness: {
    capturedAt: string;
    ageSeconds: number;
  };
}

interface LocationMapProps {
  intent: PresentationIntent;
}

interface Center {
  latitude: number;
  longitude: number;
}

export function LocationMap({ intent }: LocationMapProps) {
  const visualization = intent.visualizations?.find((item) => item.type === 'map');
  const resource = visualization?.data.resource;
  const hasAuthorizedResource = Boolean(
    resource?.startsWith('/api/v1/presentation/location/'),
  );
  const [location, setLocation] = useState<LocationData | null>(null);
  const [center, setCenter] = useState<Center | null>(null);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ x: number; y: number; center: Center } | null>(null);
  const moved = useRef(false);

  useEffect(() => {
    if (!resource || !hasAuthorizedResource) return;
    let active = true;
    void apiClient.get<LocationData>(resource).then((result) => {
      if (!active) return;
      setLocation(result);
      setCenter({ latitude: result.latitude, longitude: result.longitude });
    }).catch((requestError: unknown) => {
      if (active) {
        setError(requestError instanceof Error
          ? requestError.message
          : 'The authorized location is no longer available.');
      }
    });
    return () => {
      active = false;
    };
  }, [hasAuthorizedResource, intent.id, resource]);

  useEffect(() => {
    if (!location) return;
    let active = true;
    void apiClient.post(API_ENDPOINTS.presentation.locationRendered(intent.id), {}).catch(() => {
      if (active) setError('The map is visible, but its runtime render event could not be recorded.');
    });
    return () => {
      active = false;
    };
  }, [intent.id, location]);

  if (!visualization) return null;

  const spanLongitude = 30 / zoom;
  const spanLatitude = 15 / zoom;
  const markerX = location && center
    ? 50 + ((location.longitude - center.longitude) / spanLongitude) * 100
    : 50;
  const markerY = location && center
    ? 50 - ((location.latitude - center.latitude) / spanLatitude) * 100
    : 50;
  const accuracyRadius = location?.accuracyMeters
    ? Math.min(
        90,
        Math.max(
          2,
          (location.accuracyMeters / Math.max(1, 111_320 * Math.cos(location.latitude * Math.PI / 180)))
            / spanLongitude * 100,
        ),
      )
    : 0;

  const reportInteraction = (action: 'zoom' | 'pan' | 'recenter') => {
    void apiClient.post(
      API_ENDPOINTS.presentation.locationInteraction(intent.id),
      { action },
    ).catch(() => {
      setError('A map interaction could not be recorded by the runtime.');
    });
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!center || (event.target as HTMLElement).closest('button')) return;
    drag.current = { x: event.clientX, y: event.clientY, center };
    moved.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current || !event.currentTarget.clientWidth || !event.currentTarget.clientHeight) return;
    const deltaX = event.clientX - drag.current.x;
    const deltaY = event.clientY - drag.current.y;
    if (Math.abs(deltaX) + Math.abs(deltaY) < 3) return;
    moved.current = true;
    setCenter({
      longitude: drag.current.center.longitude - (deltaX / event.currentTarget.clientWidth) * spanLongitude,
      latitude: drag.current.center.latitude + (deltaY / event.currentTarget.clientHeight) * spanLatitude,
    });
  };

  const handlePointerUp = () => {
    if (drag.current && moved.current) reportInteraction('pan');
    drag.current = null;
    moved.current = false;
  };

  return (
    <section
      aria-label="Current location geospatial environment"
      className="mt-3 w-full overflow-hidden rounded-xl border border-cyan-300/15 bg-slate-950/80"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.07] px-3 py-2">
        <div>
          <h3 className="text-xs font-medium text-slate-100">Current location</h3>
          <p className="text-[10px] text-slate-400">Private coordinate view · no external map service</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Zoom out"
            disabled={!location}
            onClick={() => {
              setZoom((value) => Math.max(0.5, value / 1.5));
              reportInteraction('zoom');
            }}
            className="rounded-md border border-white/10 p-1.5 text-slate-200 disabled:opacity-40"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            disabled={!location}
            onClick={() => {
              setZoom((value) => Math.min(24, value * 1.5));
              reportInteraction('zoom');
            }}
            className="rounded-md border border-white/10 p-1.5 text-slate-200 disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Recenter map"
            disabled={!location}
            onClick={() => {
              if (location) setCenter({ latitude: location.latitude, longitude: location.longitude });
              reportInteraction('recenter');
            }}
            className="ml-1 inline-flex items-center gap-1.5 rounded-md border border-cyan-200/20 px-2 py-1.5 text-[10px] text-cyan-100 disabled:opacity-40"
          >
            <LocateFixed className="h-3 w-3" />
            Recenter
          </button>
        </div>
      </div>

      <div
        className="h-56 touch-none cursor-grab active:cursor-grabbing sm:h-72"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {location && center ? (
          <svg
            role="img"
            aria-label={`Authorized browser location view, zoom level ${zoom.toFixed(1)}`}
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            className="h-full w-full"
          >
            <rect width="100" height="100" fill="#0b1724" />
            {Array.from({ length: 9 }, (_, index) => {
              const offset = (index + 1) * 10;
              return (
                <g key={offset} stroke="#31516a" strokeOpacity="0.46" strokeWidth="0.22">
                  <path d={`M ${offset} 0 V 100`} />
                  <path d={`M 0 ${offset} H 100`} />
                </g>
              );
            })}
            <path d="M 50 0 V 100 M 0 50 H 100" stroke="#5c8198" strokeOpacity="0.5" strokeWidth="0.28" />
            {markerX >= 0 && markerX <= 100 && markerY >= 0 && markerY <= 100 && (
              <>
                {accuracyRadius > 0 && (
                  <ellipse
                    cx={markerX}
                    cy={markerY}
                    rx={accuracyRadius}
                    ry={Math.min(90, accuracyRadius * 2)}
                    fill="#22d3ee"
                    fillOpacity="0.14"
                    stroke="#67e8f9"
                    strokeOpacity="0.42"
                    strokeWidth="0.25"
                  />
                )}
                <circle cx={markerX} cy={markerY} r="2.2" fill="#22d3ee" fillOpacity="0.3" />
                <circle cx={markerX} cy={markerY} r="0.9" fill="#ecfeff" />
              </>
            )}
          </svg>
        ) : (
          <div role="status" className="flex h-full items-center justify-center text-xs text-slate-400">
            {error
              || (!hasAuthorizedResource
                ? 'The location presentation does not contain an authorized data reference.'
                : 'Loading authorized location…')}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.07] px-3 py-2 text-[10px] text-slate-400">
        <span className="flex flex-wrap gap-x-3 gap-y-1">
          <span>
            {location
              ? `Approx. ${location.latitude.toFixed(4)}°, ${location.longitude.toFixed(4)}°`
              : 'Position unavailable'}
          </span>
          <span>
            {location?.accuracyMeters == null
              ? 'Accuracy estimate not provided'
              : `Estimated accuracy ±${Math.round(location.accuracyMeters)} m`}
          </span>
        </span>
        <span>{location ? `Captured ${new Date(location.timestamp).toLocaleTimeString()}` : 'Waiting for location data'}</span>
      </div>
      {error && location && (
        <p role="status" className="border-t border-amber-200/10 px-3 py-2 text-[10px] text-amber-200">
          {error}
        </p>
      )}
    </section>
  );
}
