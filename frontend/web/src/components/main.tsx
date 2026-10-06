import React from 'react';
import { VersionInfo } from '../types';

interface VersionBadgeProps {
  info: VersionInfo;
  version: string;
}

export const VersionBadge: React.FC<VersionBadgeProps> = ({ info, version }) => {
  if (!info || !info.codename) {
    return null; // Or a placeholder
  }

  return (
    <div className="p-4 bg-slate-900 border border-cyan-500/30 rounded-lg shadow-lg shadow-cyan-500/10">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-xl font-bold text-cyan-400">{info.codename}</h3>
        <span className="px-2 py-1 text-xs font-mono bg-cyan-900/50 text-cyan-300 rounded">v{version}</span>
      </div>
      <p className="text-sm text-slate-400 mb-3 italic">{info.milestone}</p>
      <ul className="space-y-1">
        {info.changes.map((change, i) => (
          <li key={i} className="text-xs text-slate-300 flex items-start"><span className="text-cyan-500 mr-2">▹</span>{change}</li>
        ))}
      </ul>
    </div>
  );
};