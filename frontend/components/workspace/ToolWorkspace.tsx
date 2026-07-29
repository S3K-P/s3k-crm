'use client';

import { type ReactNode } from 'react';
import SourcesRail from '@/components/workspace/SourcesRail';
import RecentRail from '@/components/workspace/RecentRail';

interface Props {
  children: ReactNode;
  /** Override the right rail entirely. Pass null to hide it. */
  right?: ReactNode;
  /** Hide the left Sources rail (rare — most tool pages keep it). */
  hideSources?: boolean;
}

/**
 * 3-pane workspace body for tool pages: [ Sources | center form | Recent ].
 * Each pane scrolls independently.
 *
 * Usage — page root must be full height so the rails can scroll independently:
 *   <div className="flex h-full flex-col">
 *     <Header />
 *     <ToolWorkspace>{/* PageHeader + form *​/}</ToolWorkspace>
 *   </div>
 */
export default function ToolWorkspace({ children, right, hideSources }: Props) {
  return (
    <div className="flex min-h-0 flex-1">
      {!hideSources && <SourcesRail />}
      <main className="flex-1 overflow-y-auto">{children}</main>
      {right === undefined ? (hideSources ? null : <RecentRail />) : right}
    </div>
  );
}
