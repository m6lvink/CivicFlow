'use client';

import type { PredictResponse, RiskBand } from '@/lib/types';

const BAND_STYLES: Record<RiskBand, { text: string; bg: string; border: string; label: string }> = {
  Fast: {
    text: 'text-fast-text',
    bg: 'bg-fast-bg',
    border: 'border-fast-border',
    label: 'Fast - same-day issuance likely',
  },
  Normal: {
    text: 'text-normal-text',
    bg: 'bg-normal-bg',
    border: 'border-normal-border',
    label: 'Normal - standard review timeline',
  },
  Slow: {
    text: 'text-slow-text',
    bg: 'bg-slow-bg',
    border: 'border-slow-border',
    label: 'Slow - expect extended review',
  },
  'High-risk': {
    text: 'text-highrisk-text',
    bg: 'bg-highrisk-bg',
    border: 'border-highrisk-border',
    label: 'High-risk - significant delays expected',
  },
};

// Human-readable feature name mapping
const FEATURE_LABELS: Record<string, string> = {
  processreviewtype: 'Process routing',
  commercialresidential: 'Project type',
  solar: 'Solar work',
  solarvpinstallation: 'Solar VP installation',
  alteration: 'Alteration scope',
  newbuilding: 'New construction',
  acceptedvalue: 'Accepted value',
  estimatedvalueofwork: 'Estimated value',
  contractor_score: 'Contractor history',
  proposeduse: 'Proposed use',
  typesofconstructionactual: 'Construction type',
  addition: 'Addition scope',
  repair: 'Repair scope',
  numunitsadd: 'Units added',
};

function featureLabel(raw: string): string {
  return FEATURE_LABELS[raw] ?? raw.replace(/_/g, ' ');
}

interface Props {
  result: PredictResponse | null;
  loading: boolean;
  error: string | null;
}

export default function PredictResult({ result, loading, error }: Props) {
  if (!result && !loading && !error) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-sm text-muted">
        Fill in the permit details and click <strong className="text-ink">Predict delay</strong> to see the coarse forecast.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6">
        <div className="space-y-3 animate-pulse">
          <div className="h-12 w-32 bg-border rounded" />
          <div className="h-4 w-24 bg-border rounded" />
          <div className="h-4 w-48 bg-border rounded" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-highrisk-border bg-highrisk-bg p-4 text-sm text-highrisk-text">
      <strong>Prediction error:</strong> {error}
      </div>
    );
  }

  if (!result) return null;

  const band = BAND_STYLES[result.risk_band];
  const maxImportance = Math.max(...result.top_factors.map(f => f.importance), 0.01);

  return (
    <div className="rounded-lg border border-border bg-surface overflow-hidden">
      <div className={`px-6 py-4 border-b border-border ${band.bg}`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className={`font-serif text-5xl font-semibold leading-none ${band.text}`}>
              {Math.round(result.expected_wait_days)}
            </div>
            <div className="mt-1 text-sm text-muted font-sans">rough days estimate</div>
          </div>

          <span className={`mt-1 inline-flex items-center rounded border px-2.5 py-1 text-xs font-semibold
                            ${band.text} ${band.bg} ${band.border}`}>
            {result.risk_band}
          </span>
        </div>

        <p className={`mt-2 text-sm ${band.text}`}>{band.label}</p>
      </div>

      <div className="px-6 py-4 space-y-5">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-muted text-xs uppercase tracking-wider mb-1">Fast-track probability</div>
            <div className="font-semibold text-ink">
              {(result.fast_track_probability * 100).toFixed(1)}%
            </div>
          </div>
          <div>
            <div className="text-muted text-xs uppercase tracking-wider mb-1">Coarse range</div>
            <div className="font-semibold text-ink">
              {Math.round(result.confidence_interval_days.low)}-{Math.round(result.confidence_interval_days.high)} days
            </div>
          </div>
        </div>

        {result.top_factors.length > 0 && (
          <div>
            <div className="text-muted text-xs uppercase tracking-wider mb-3">Top delay factors</div>
            <ul className="space-y-2.5">
              {result.top_factors.slice(0, 6).map(f => (
                <li key={f.feature}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-ink">{featureLabel(f.feature)}</span>
                    <span className="text-muted tabular-nums">{(f.importance * 100).toFixed(1)}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-border overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-500"
                      style={{ width: `${(f.importance / maxImportance) * 100}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
