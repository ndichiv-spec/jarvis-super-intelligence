'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, ChevronDown, ChevronUp, Info, History, Link2, Settings,
  Shield, Users, Activity, Calendar, BarChart3,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { glassCard, glassBorder } from '@/lib/design-system';
import type { ResourceStatus, SeverityLevel } from '@/lib/types/platform';

export interface InspectorField {
  key: string;
  label: string;
  value: React.ReactNode;
  type?: 'text' | 'status' | 'badge' | 'date' | 'number' | 'severity' | 'custom';
  icon?: React.ElementType;
}

export interface InspectorSection {
  id: string;
  label: string;
  icon?: React.ElementType;
  fields: InspectorField[];
}

export interface InspectorAction {
  id: string;
  label: string;
  icon?: React.ElementType;
  variant?: 'default' | 'outline' | 'destructive';
  onClick: () => void;
  disabled?: boolean;
}

export interface InspectorObject {
  id: string;
  type: string;
  title: string;
  subtitle?: string;
  status: ResourceStatus;
  sections: InspectorSection[];
  actions?: InspectorAction[];
  relatedObjects?: Array<{ type: string; id: string; label: string; onClick: () => void }>;
}

const SECTION_ICONS: Record<string, React.ElementType> = {
  identity: Info,
  status: Activity,
  activity: History,
  relationships: Link2,
  metadata: Settings,
  permissions: Shield,
  metrics: BarChart3,
  history: Calendar,
};

interface UniversalInspectorProps {
  object: InspectorObject | null;
  open: boolean;
  onClose: () => void;
  anchor?: React.ReactNode;
  width?: string | number;
}

export function UniversalInspector({
  object,
  open,
  onClose,
  anchor,
  width = 380,
}: UniversalInspectorProps) {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

  if (!object) return null;

  const toggleSection = (id: string) => {
    setExpandedSections((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const allSectionsExpanded = object.sections.every((s) => expandedSections[s.id]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            className={`fixed top-16 bottom-4 z-50 flex flex-col overflow-hidden rounded-2xl border ${glassCard} ${glassBorder}`}
            style={{ width, right: 16 }}
            initial={{ x: 100, opacity: 0, scale: 0.95 }}
            animate={{ x: 0, opacity: 1, scale: 1 }}
            exit={{ x: 100, opacity: 0, scale: 0.95 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="border-b border-white/5 p-4">
              <div className="flex items-start justify-between">
                <div className="space-y-0.5">
                  <h2 className="text-sm font-semibold text-foreground">{object.title}</h2>
                  {object.subtitle && (
                    <p className="text-xs text-muted-foreground/60">{object.subtitle}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0 text-muted-foreground/50 hover:text-foreground"
                  onClick={onClose}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={`text-[10px] font-medium ${statusBadgeColor(object.status)}`}
                >
                  {object.status}
                </Badge>
                <Badge variant="secondary" className="text-[10px] font-medium">
                  {object.type}
                </Badge>
              </div>
            </div>

            {/* Sections */}
            <div className="flex-1 overflow-y-auto">
              {object.sections.map((section) => {
                const IconEl = SECTION_ICONS[section.id] || section.icon || Info;
                const isExpanded = expandedSections[section.id] ?? true;
                return (
                  <div key={section.id} className="border-b border-white/5 last:border-0">
                    <button
                      className="flex w-full items-center justify-between px-4 py-2.5 text-left transition-colors hover:bg-white/[0.03]"
                      onClick={() => toggleSection(section.id)}
                    >
                      <div className="flex items-center gap-2">
                        <IconEl className="h-4 w-4 text-muted-foreground/60" />
                        <span className="text-xs font-medium text-muted-foreground/40 uppercase tracking-wider">
                          {section.label}
                        </span>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="h-3 w-3 text-muted-foreground/40" />
                      ) : (
                        <ChevronDown className="h-3 w-3 text-muted-foreground/40" />
                      )}
                    </button>
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="px-4 pb-1"
                        >
                          {section.fields.map((field) => renderField(field))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}

              {/* Related Objects */}
              {object.relatedObjects && object.relatedObjects.length > 0 && (
                <div className="border-b border-white/5">
                  <button
                    className="flex w-full items-center justify-between px-4 py-2.5 text-left transition-colors hover:bg-white/[0.03]"
                    onClick={() => toggleSection('relationships')}
                  >
                    <div className="flex items-center gap-2">
                      <Link2 className="h-4 w-4 text-muted-foreground/60" />
                      <span className="text-xs font-medium text-muted-foreground/40 uppercase tracking-wider">
                        Related
                      </span>
                    </div>
                    {expandedSections.relationships !== false && (
                      <ChevronUp className="h-3 w-3 text-muted-foreground/40" />
                    )}
                  </button>
                  <AnimatePresence>
                    {expandedSections['relationships'] !== false && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="px-4 pb-1 space-y-1"
                      >
                        {object.relatedObjects.map((rel) => (
                          <button
                            key={rel.id}
                            className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-muted-foreground/50 hover:text-foreground hover:bg-white/[0.03] transition-colors"
                            onClick={rel.onClick}
                          >
                            <span className="font-medium">{rel.label}</span>
                            <Badge variant="secondary" className="text-[8px] ml-auto">
                              {rel.type}
                            </Badge>
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>

            {/* Actions */}
            {object.actions && object.actions.length > 0 && (
              <div className="border-t border-white/5 p-3">
                <div className="flex gap-2">
                  {object.actions.map((action) => {
                    const IconEl = action.icon;
                    return (
                      <Button
                        key={action.id}
                        variant={action.variant || 'outline'}
                        size="sm"
                        className="text-xs"
                        onClick={action.onClick}
                        disabled={action.disabled}
                      >
                        {IconEl && <IconEl className="mr-1.5 h-3 w-3" />}
                        {action.label}
                      </Button>
                    );
                  })}
                </div>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function statusBadgeColor(status: ResourceStatus): string {
  if (status === 'completed' || status === 'idle' || status === 'working') return 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10';
  if (status === 'failed' || status === 'offline' || status === 'cancelled') return 'text-red-400 border-red-500/30 bg-red-500/10';
  if (status === 'degraded' || status === 'paused' || status === 'loading' || status === 'queued') return 'text-amber-400 border-amber-500/30 bg-amber-500/10';
  if (status === 'streaming') return 'text-blue-400 border-blue-500/30 bg-blue-500/10';
  if (status === 'unauthorized') return 'text-gray-400 border-gray-500/30 bg-gray-500/10';
  return 'text-gray-400 border-gray-500/30 bg-gray-500/10';
}

function renderField(field: InspectorField) {
  const value = field.value ?? '—';
  return (
    <div key={field.key} className="flex items-start justify-between py-1.5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
        {field.icon && <field.icon className="h-3 w-3" />}
        <span>{field.label}</span>
      </div>
      <div className="text-xs text-foreground text-right max-w-[240px] break-words">
        {value}
      </div>
    </div>
  );
}
