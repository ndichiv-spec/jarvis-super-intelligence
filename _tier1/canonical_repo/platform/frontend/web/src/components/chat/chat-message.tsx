'use client';

import { Bot, UserRound } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useEffect, useRef, useState } from 'react';
import remarkGfm from 'remark-gfm';
import 'maplibre-gl/dist/maplibre-gl.css';
import type {
  ChatMessage,
  SemanticPresentationContract,
} from '@/features/chat/types';
import { interpretPresentation } from '@/features/chat/presentation-adapter.mjs';

interface ChatMessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export function ChatMessageBubble({ message, isStreaming = false }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const messageError = typeof message.error === 'string'
    ? message.error
    : message.error?.message;
  const presentation = interpretPresentation(message.presentation);

  if (isSystem) {
    return (
      <p className="mx-auto max-w-2xl rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-center text-xs text-slate-400">
        {message.content}
      </p>
    );
  }

  return (
    <article className={`flex min-w-0 gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border ${
        isUser
          ? 'border-white/10 bg-white/[0.04] text-slate-300'
          : 'border-cyan-200/10 bg-cyan-200/[0.04] text-cyan-100/80'
      }`}>
        {isUser
          ? <UserRound aria-hidden="true" className="h-3.5 w-3.5" />
          : <Bot aria-hidden="true" className="h-3.5 w-3.5" />}
      </div>
      <div className={`min-w-0 max-w-[min(88%,48rem)] ${isUser ? 'text-right' : ''}`}>
        <div className={`mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-400 ${isUser ? 'justify-end' : ''}`}>
          <span className="font-medium text-slate-400">{isUser ? 'You' : 'JARVIS'}</span>
          {message.model && <span>{message.model}</span>}
          {isStreaming && <span className="text-cyan-100/70">Generating</span>}
          {message.timestamp && (
            <time dateTime={message.timestamp}>
              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </time>
          )}
        </div>
        <div className={`rounded-xl border px-3.5 py-2.5 text-left text-sm leading-relaxed ${
          isUser
            ? 'border-cyan-200/10 bg-cyan-200/[0.045] text-slate-100'
            : 'border-white/[0.07] bg-white/[0.025] text-slate-200'
        }`}>
          {presentation?.kind === 'contract'
            ? <SemanticPresentationView contract={presentation.contract} />
            : presentation?.kind === 'fallback'
              ? (
                <div>
                  <p role="status" className="mb-2 text-xs text-amber-200">
                    {presentation.reason} Showing the conversation fallback.
                  </p>
                  <MarkdownContent text={presentation.text} />
                </div>
              )
              : <MarkdownContent text={message.content} />}
          {messageError && (
            <p role="alert" className="mt-2 border-t border-rose-300/10 pt-2 text-xs text-rose-200">
              {messageError}
            </p>
          )}
        </div>

        {message.tool_calls && message.tool_calls.length > 0 && (
          <ul aria-label="Tool activity" className={`mt-2 space-y-1 ${isUser ? 'text-right' : ''}`}>
            {message.tool_calls.map((tool, index) => (
              <li key={`${tool.name}-${index}`} className="text-xs text-slate-400">
                <span className="font-medium text-slate-400">{tool.name}</span>
                {tool.status && <span> · {tool.status}</span>}
              </li>
            ))}
          </ul>
        )}

        {!presentation && message.sources && message.sources.length > 0 && (
          <details className="mt-2 text-left">
            <summary className="w-fit cursor-pointer text-xs text-slate-400 transition-colors hover:text-slate-200">
              {message.sources.length} source{message.sources.length === 1 ? '' : 's'}
            </summary>
            <ul className="mt-1 space-y-1 pl-3 text-xs text-slate-400">
              {message.sources.map((source, index) => (
                <li key={`${index}-${source}`} className="break-words">{source}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </article>
  );
}

function MarkdownContent({ text }: { text: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none break-words prose-p:my-1.5 prose-headings:my-2 prose-a:text-cyan-200 prose-code:rounded prose-code:bg-black/30 prose-code:px-1 prose-code:py-0.5 prose-code:text-cyan-100 prose-pre:overflow-x-auto prose-pre:border prose-pre:border-white/10 prose-pre:bg-black/30 prose-li:my-0.5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const external = isPublicHttpsUrl(href);
            return (
              <a
                href={external ? href : undefined}
                target={external ? '_blank' : undefined}
                rel={external ? 'noopener noreferrer' : undefined}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function SemanticPresentationView({
  contract,
}: {
  contract: SemanticPresentationContract;
}) {
  const components = new Map(contract.components.map((component) => [component.id, component]));
  return (
    <section aria-label="JARVIS response" aria-live="polite" className="space-y-3">
      {contract.content_hierarchy.map((id) => {
        const component = components.get(id);
        if (!component) return null;
        if (component.type === 'conversation.markdown') {
          return <MarkdownContent key={component.id} text={component.text} />;
        }
        if (component.type === 'research.source_list') {
          if (component.items.length === 0) return null;
          return (
            <section key={component.id} aria-labelledby={`${component.id}-title`}>
              <h3 id={`${component.id}-title`} className="mb-1 font-medium text-slate-200">
                {component.title}
              </h3>
              <ul className="space-y-2">
                {component.items.map((item) => (
                  <li key={item.data_ref} className="break-words">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-cyan-200 underline"
                    >
                      {item.title}
                    </a>
                    {item.snippet && <p className="mt-0.5 text-slate-400">{item.snippet}</p>}
                  </li>
                ))}
              </ul>
            </section>
          );
        }
        if (component.type === 'geospatial.point_map') {
          const point = component.items[0];
          if (!point) return null;
          return (
            <section key={component.id} aria-labelledby={`${component.id}-title`}>
              <h3 id={`${component.id}-title`} className="mb-1 font-medium text-slate-200">
                {component.title}
              </h3>
              <PointMap
                latitude={point.latitude}
                longitude={point.longitude}
                label={point.label}
              />
            </section>
          );
        }
        return (
          <section key={component.id} aria-labelledby={`${component.id}-title`}>
            <h3 id={`${component.id}-title`} className="mb-1 font-medium text-slate-200">
              {component.title}
            </h3>
            {component.items.length > 0 ? (
              <ul className="list-disc space-y-1 pl-5">
                {component.items.map((item, index) => (
                  <li key={`${item.data_ref}-${index}`}>
                    <code>{item.path}:{item.line}</code>
                    {item.text && <span className="ml-2 break-words">{item.text}</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No matching workspace results.</p>
            )}
          </section>
        );
      })}
    </section>
  );
}

function PointMap({
  latitude,
  longitude,
  label,
}: {
  latitude: number;
  longitude: number;
  label: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    let active = true;
    let map: import('maplibre-gl').Map | undefined;

    void import('maplibre-gl').then(({ Map, Marker, NavigationControl }) => {
      if (!active || !containerRef.current) return;
      map = new Map({
        container: containerRef.current,
        style: {
          version: 8,
          sources: {
            streets: {
              type: 'raster',
              tiles: [
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
              ],
              tileSize: 256,
              attribution: 'Tiles &copy; Esri',
            },
          },
          layers: [{ id: 'streets', type: 'raster', source: 'streets' }],
        },
        center: [longitude, latitude],
        zoom: 10,
        attributionControl: { compact: true },
      });
      map.addControl(new NavigationControl(), 'top-right');
      new Marker({ color: '#22d3ee' })
        .setLngLat([longitude, latitude])
        .addTo(map);
      map.on('error', () => setMapError(true));
    }).catch(() => {
      if (active) setMapError(true);
    });

    return () => {
      active = false;
      map?.remove();
    };
  }, [latitude, longitude, label]);

  return (
    <div>
      <div
        ref={containerRef}
        role="img"
        aria-label={`Map centered on user-provided coordinates ${label}`}
        className="h-64 w-full overflow-hidden rounded-lg border border-white/10"
      />
      {mapError && (
        <p role="status" className="mt-2 text-xs text-amber-200">
          Map tiles could not be loaded. The validated user-provided coordinates
          remain available: {label}.
        </p>
      )}
      <p className="mt-1 text-xs text-slate-400">
        User-provided coordinates · map tiles provided by Esri. This is not a live device location.
      </p>
    </div>
  );
}

function isPublicHttpsUrl(value: string | undefined): value is string {
  if (!value) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:'
      && !url.username
      && !url.password
      && !/(token|secret|password|credential|auth|session|signature|^key$|^sig$)/i
        .test(url.search);
  } catch {
    return false;
  }
}
