'use client';

import { useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Play } from 'lucide-react';
import DropZone from '@/components/DropZone';
import PermitForm, { EMPTY_PERMIT } from '@/components/PermitForm';
import PredictResult from '@/components/PredictResult';
import CheckReport from '@/components/CheckReport';
import { predict, checkPermit, extractPermit, ApiError } from '@/lib/api';
import type { PermitData, PredictResponse, CheckResponse } from '@/lib/types';

/** Strip empty strings / undefined; the backend fills the rest from training medians */
function cleaned(form: PermitData): PermitData {
  return Object.fromEntries(
    Object.entries(form).filter(([, v]) => v !== '' && v !== undefined)
  ) as PermitData;
}

/** One permit run = one results tab (its own forecast + requirements check) */
interface RunResult {
  id: number;
  label: string;
  predict: PredictResponse | null;
  check: CheckResponse | null;
  predictError: string | null;
  checkError: string | null;
  loading: boolean;
}

export default function Home() {
  const [form, setForm] = useState<PermitData>(EMPTY_PERMIT);
  const [plans, setPlans] = useState<File[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [extracted, setExtracted] = useState(false);
  const [extracting, setExtracting] = useState(false);
  // After extraction fails, skip it on the next Run --> user can proceed with manual fields
  const [skipExtract, setSkipExtract] = useState(false);
  const [extractWarnings, setExtractWarnings] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  // One tab per permit run; new Run appends results instead of overwriting
  const [runs, setRuns] = useState<RunResult[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const nextId = useRef(1);

  const anyRunLoading = runs.some(r => r.loading);
  const busy = extracting || anyRunLoading;
  const hasResults = runs.length > 0;
  const activeRun = runs.find(r => r.id === activeId) ?? null;

  function clearExtractState() {
    setSkipExtract(false);
    setExtracted(false);
    setExtractWarnings([]);
    setForm(EMPTY_PERMIT);   // new doc set: reset permit fields
  }

  async function runForecastAndCheck(permit: PermitData, files: File[]) {
    const id = nextId.current++;
    const address = typeof permit.jobaddress === 'string' ? permit.jobaddress.trim() : '';
    setRuns(prev => [
      ...prev,
      {
        id,
        label: address ? address.slice(0, 28) : `Permit ${prev.length + 1}`,
        predict: null,
        check: null,
        predictError: null,
        checkError: null,
        loading: true,
      },
    ]);
    setActiveId(id);

    const [p, c] = await Promise.allSettled([
      predict(permit),
      checkPermit(permit, files.length ? files : undefined),
    ]);

    setRuns(prev => prev.map(r => (r.id === id ? {
      ...r,
      predict: p.status === 'fulfilled' ? p.value : null,
      predictError: p.status === 'rejected'
        ? (p.reason instanceof Error ? p.reason.message : 'Prediction failed') : null,
      check: c.status === 'fulfilled' ? c.value : null,
      checkError: c.status === 'rejected'
        ? (c.reason instanceof Error ? c.reason.message : 'Requirements check failed') : null,
      loading: false,
    } : r)));
  }

  async function handleRun() {
    setNotice(null);
    const permit = cleaned(form);

    if (plans.length > 0 && !skipExtract) {
      setExtracting(true);
      try {
        const ex = await extractPermit(plans);
        const merged = { ...EMPTY_PERMIT, ...ex.fields };
        setForm(merged);
        setExtractWarnings(ex.warnings);
        setExtracted(true);
        setFormOpen(true);
        setSkipExtract(true);
        setExtracting(false);
        await runForecastAndCheck(cleaned(merged), plans);
        return;
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) {
          setNotice(
            "Automatic document reading isn't available on this server. " +
            'Enter the permit details below, then press Run again.'
          );
        } else {
          setNotice(
            `We couldn't read your documents (${e instanceof Error ? e.message : 'unknown error'}). ` +
            'Enter the permit details below, then press Run again.'
          );
        }
        setFormOpen(true);
        setExtracting(false);
        setSkipExtract(true);
        return;
      }
    } else if (plans.length === 0 && !formOpen) {
      // Nothing to run yet: guide the user instead of predicting on defaults
      setNotice('Add your documents above, or enter the permit details below, then press Run.');
      setFormOpen(true);
      return;
    }

    // Keep files for full review on success; fall back to metadata-only on failed extraction
    await runForecastAndCheck(permit, skipExtract && !extracted ? [] : plans);
  }

  const runLabel = extracting
    ? 'Reading documents…'
    : anyRunLoading
      ? 'Running…'
      : 'Run';

  return (
    <div className="min-h-screen bg-cream">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-6xl px-6 py-4 flex items-baseline justify-between">
          <div>
            <span className="font-serif text-xl font-semibold text-ink">CivicFlow</span>
            <span className="ml-3 text-sm text-muted">Honolulu DPP permit advisor</span>
          </div>
          <span className="text-xs text-subtle border border-border rounded px-2 py-1">
            City &amp; County of Honolulu
          </span>
        </div>
      </header>

      <div className="border-b border-border bg-off-white">
        <div className="mx-auto max-w-6xl px-6 py-3">
          <p className="text-sm text-muted">
            Drop in your permit documents and press Run. We read them, estimate your DPP
            processing time, and check your submittal for completeness.
            Based on 432,000 Honolulu permits filed 2005-2025.
          </p>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className={`grid gap-8 ${hasResults ? 'lg:grid-cols-[440px_1fr]' : 'max-w-xl'}`}>

          {/* Left - documents + details (sticky on desktop when results are shown) */}
          <div className={hasResults ? 'lg:sticky lg:top-6 lg:self-start space-y-4' : 'space-y-4'}>
            <div className="rounded-lg border border-border bg-surface p-6">
              <h1 className="font-serif text-lg font-semibold text-ink mb-4">
                Your permit documents
              </h1>
              <DropZone
                files={plans}
                onAdd={f => {
                  const total = plans.length + f.length;
                  setPlans(prev => [...prev, ...f].slice(0, 4));
                  setNotice(total > 4 ? 'Up to 4 documents per permit - extra files were skipped.' : null);
                  clearExtractState();
                }}
                onRemove={i => { setPlans(prev => prev.filter((_, idx) => idx !== i)); clearExtractState(); }}
                disabled={busy}
              />

              <button
                type="button"
                disabled={busy}
                onClick={handleRun}
                className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded bg-primary
                           px-4 py-3 text-base font-semibold text-white hover:bg-primary-dark
                           active:scale-[0.99] disabled:opacity-50 transition-all duration-150
                           cursor-pointer disabled:cursor-not-allowed"
              >
                <Play size={16} />
                {runLabel}
              </button>

              {notice && (
                <p className="mt-3 text-sm text-normal-text bg-normal-bg border border-normal-border rounded px-3 py-2">
                  {notice}
                </p>
              )}
            </div>

            {/* Permit details: pre-filled by extraction, or manual fallback */}
            <div className="rounded-lg border border-border bg-surface">
              <button
                type="button"
                onClick={() => setFormOpen(o => !o)}
                className="w-full flex items-center justify-between px-6 py-4 text-left cursor-pointer"
                aria-expanded={formOpen}
              >
                <span className="font-serif text-base font-semibold text-ink">
                  {extracted ? 'What we read from your documents' : 'Enter details manually'}
                </span>
                {formOpen
                  ? <ChevronDown size={16} className="text-muted" />
                  : <ChevronRight size={16} className="text-muted" />}
              </button>

              {formOpen && (
                <div className="px-6 pb-6">
                  {extracted && (
                    <p className="mb-4 text-xs text-muted">
                      Review what we read, correct anything that looks off, then press Run again.
                    </p>
                  )}
                  {extractWarnings.length > 0 && (
                    <div className="mb-4 space-y-1">
                      {extractWarnings.map((w, i) => (
                        <p key={i} className="text-xs text-normal-text">{w}</p>
                      ))}
                    </div>
                  )}
                  <PermitForm values={form} onChange={setForm} />
                </div>
              )}
            </div>
          </div>

          {/* Right - Results (one tab per permit run) */}
          {hasResults && (
            <div className="space-y-4">
              {runs.length > 1 && (
                <div className="flex flex-wrap gap-1 border-b border-border">
                  {runs.map(r => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setActiveId(r.id)}
                      className={`px-3 py-2 text-sm rounded-t border-b-2 -mb-px cursor-pointer transition-colors
                        ${r.id === activeId
                          ? 'border-primary text-ink font-semibold'
                          : 'border-transparent text-muted hover:text-ink'}`}
                    >
                      {r.label}{r.loading ? ' …' : ''}
                    </button>
                  ))}
                </div>
              )}

              {activeRun && (
                <div className="space-y-6">
                  <div>
                    <h2 className="font-serif text-base font-semibold text-ink mb-3">
                      Delay forecast
                    </h2>
                    <PredictResult
                      result={activeRun.predict}
                      loading={activeRun.loading}
                      error={activeRun.predictError}
                    />
                  </div>

                  <div>
                    <h2 className="font-serif text-base font-semibold text-ink mb-3">
                      Requirements check
                    </h2>
                    <CheckReport
                      result={activeRun.check}
                      loading={activeRun.loading}
                      error={activeRun.checkError}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      <footer className="border-t border-border mt-16 py-6">
        <div className="mx-auto max-w-6xl px-6 text-xs text-subtle">
          Data: Honolulu Department of Planning &amp; Permitting, 2005-2025.
          Predictions are statistical estimates; contact the DPP directly for official guidance.
        </div>
      </footer>
    </div>
  );
}
