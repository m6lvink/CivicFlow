'use client';

import type { CheckResponse, FindingStatus, OverallStatus } from '@/lib/types';

const STATUS_STYLES: Record<FindingStatus, { text: string; bg: string; label: string }> = {
  PASS: { text: 'text-pass-text', bg: 'bg-pass-bg', label: 'Pass' },
  FLAG: { text: 'text-flag-text', bg: 'bg-flag-bg', label: 'Flag' },
  FAIL: { text: 'text-fail-text', bg: 'bg-fail-bg', label: 'Fail' },
  'N/A': { text: 'text-muted', bg: 'bg-off-white', label: 'N/A' },
};

const OVERALL_STYLES: Record<OverallStatus, { text: string; bg: string; border: string; headline: string }> = {
  READY: {
    text: 'text-fast-text',
    bg: 'bg-fast-bg',
    border: 'border-fast-border',
    headline: 'Ready to file',
  },
  REVIEW: {
    text: 'text-normal-text',
    bg: 'bg-normal-bg',
    border: 'border-normal-border',
    headline: 'Items need review',
  },
  INCOMPLETE: {
    text: 'text-highrisk-text',
    bg: 'bg-highrisk-bg',
    border: 'border-highrisk-border',
    headline: 'Missing required items',
  },
};

interface Props {
  result: CheckResponse | null;
  loading: boolean;
  error: string | null;
}

export default function CheckReport({ result, loading, error }: Props) {
  if (!result && !loading && !error) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-sm text-muted">
        Fill in the permit details and click <strong className="text-ink">Check requirements</strong> to verify DPP submittal readiness.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6">
        <div className="space-y-3 animate-pulse">
          <div className="h-8 w-40 bg-border rounded" />
          <div className="h-4 w-full bg-border rounded" />
          <div className="h-4 w-full bg-border rounded" />
          <div className="h-4 w-3/4 bg-border rounded" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-highrisk-border bg-highrisk-bg p-4 text-sm text-highrisk-text">
        <strong>Check error:</strong> {error}
      </div>
    );
  }

  if (!result) return null;

  const overall = OVERALL_STYLES[result.overall_status];
  const passCount = result.findings.filter(f => f.status === 'PASS').length;
  const flagCount = result.findings.filter(f => f.status === 'FLAG').length;
  const failCount = result.findings.filter(f => f.status === 'FAIL').length;

  return (
    <div className="rounded-lg border border-border bg-surface overflow-hidden">
      <div className={`px-6 py-4 border-b border-border ${overall.bg}`}>
        <div className="flex items-center justify-between">
          <div>
            <div className={`font-serif text-xl font-semibold ${overall.text}`}>
              {overall.headline}
            </div>
            <div className="text-sm text-muted mt-0.5">{result.permit_summary}</div>
          </div>
          <span className={`inline-flex items-center rounded border px-2.5 py-1 text-xs font-semibold
                            ${overall.text} ${overall.bg} ${overall.border}`}>
            {result.overall_status}
          </span>
        </div>

        <div className="flex gap-4 mt-3 text-xs">
          <span className="text-pass-text">{passCount} pass</span>
          <span className="text-flag-text">{flagCount} flag</span>
          {failCount > 0 && <span className="text-fail-text">{failCount} fail</span>}
          {result.metadata_mode && (
            <span className="text-muted ml-auto">
              Metadata only - upload plan sheets for a full document check
            </span>
          )}
        </div>
      </div>

      <div className="divide-y divide-border">
        {result.findings.map(finding => {
          const s = STATUS_STYLES[finding.status];
          return (
            <div key={finding.id} className="px-6 py-3 flex gap-4">
              <span className="shrink-0 text-xs text-muted font-mono w-12 pt-0.5">
                {finding.id}
              </span>

              <span className={`shrink-0 self-start mt-0.5 inline-flex items-center rounded px-1.5 py-0.5
                               text-xs font-semibold ${s.text} ${s.bg}`}>
                {s.label}
              </span>

              <div className="min-w-0 flex-1">
                <div className="text-sm text-ink">{finding.description}</div>
                {finding.rationale && (
                  <div className="text-xs text-muted mt-0.5">{finding.rationale}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {result.warnings.length > 0 && (
        <div className="px-6 py-3 border-t border-border bg-off-white space-y-1">
          {result.warnings.map((w, i) => (
            <p key={i} className="text-xs text-normal-text">{w}</p>
          ))}
        </div>
      )}
    </div>
  );
}
