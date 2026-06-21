'use client';

import { useState, useEffect } from 'react';
import type { PermitData, SchemaResponse } from '@/lib/types';
import { getSchema } from '@/lib/api';

// Trained categories; must match the encoder or they encode to -1
// Fallback only; live list is fetched from GET /schema on mount
const FALLBACK_PERMIT_TYPES = [
  '1 - New',
  '2 - Addition, alteration or repair (units added)',
  '3 - Addition, alteration or repair (units subtracted)',
  '4 - Addition, alteration or repair (no change in units)',
  '7 - Demolition',
  '8 - Moved in/out of parcel',
  '9 - Ohana',
];

// Must match config.SERVE_COLLECTED_COLS --> train and serve features align
const WORK_FLAGS: Array<{ key: keyof PermitData; label: string }> = [
  { key: 'solar', label: 'Solar PV' },
  { key: 'solarvpinstallation', label: 'Solar VP install' },
  { key: 'newbuilding', label: 'New building' },
  { key: 'addition', label: 'Addition' },
  { key: 'alteration', label: 'Alteration' },
  { key: 'demolition', label: 'Demolition' },
  { key: 'repair', label: 'Repair' },
  { key: 'electricalwork', label: 'Electrical' },
  { key: 'plumbingwork', label: 'Plumbing' },
  { key: 'retainingwall', label: 'Retaining wall' },
  { key: 'shellonly', label: 'Shell only' },
  { key: 'foundationonly', label: 'Foundation only' },
  { key: 'pool', label: 'Pool / spa' },
  { key: 'fence', label: 'Fence' },
  { key: 'ohana', label: 'Ohana unit' },
  { key: 'accessorydwellingunitadu', label: 'ADU' },
];

export const EMPTY_PERMIT: PermitData = {
  buildingpermittype: '',
  commercialresidential: 'Residential',
  proposeduse: '',
  estimatedvalueofwork: undefined,
  jobaddress: '',
  applicant: '',
  planmaker: '',
  solar: false,
  solarvpinstallation: false,
  newbuilding: false,
  addition: false,
  alteration: false,
  demolition: false,
  repair: false,
  electricalwork: false,
  plumbingwork: false,
  retainingwall: false,
  shellonly: false,
  foundationonly: false,
  pool: false,
  fence: false,
  ohana: false,
  accessorydwellingunitadu: false,
};

interface Props {
  values: PermitData;
  onChange: (values: PermitData) => void;
}

export default function PermitForm({ values, onChange }: Props) {
  const [schema, setSchema] = useState<SchemaResponse | null>(null);

  // Fetch the model's input schema --> dropdowns only show trained categories
  useEffect(() => {
    let active = true;
    getSchema()
      .then(s => { if (active) setSchema(s); })
      .catch(() => { /* Keep fallbacks */ });
    return () => { active = false; };
  }, []);

  const permitTypeOptions = schema?.categorical?.buildingpermittype ?? FALLBACK_PERMIT_TYPES;

  function setField<K extends keyof PermitData>(key: K, value: PermitData[K]) {
    onChange({ ...values, [key]: value });
  }

  const labelCls = 'block text-sm font-medium text-ink mb-1';
  const inputCls =
    'w-full rounded border border-border bg-surface px-3 py-2 text-sm text-ink ' +
    'placeholder:text-subtle focus:border-primary focus:ring-1 focus:ring-primary outline-none';
  const selectCls = inputCls + ' cursor-pointer';

  return (
    <form
      onSubmit={e => e.preventDefault()}
      className="space-y-6"
      aria-label="Permit details form"
    >
      <fieldset className="space-y-4">
        <legend className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">
          Permit Classification
        </legend>

        {/* Commercial / Residential */}
        <div>
          <span className={labelCls}>Project type</span>
          <div className="flex gap-4 mt-1">
            {(['Residential', 'Commercial'] as const).map(v => (
              <label key={v} className="flex items-center gap-2 cursor-pointer text-sm text-ink">
                <input
                  type="radio"
                  name="commercialresidential"
                  value={v}
                  checked={values.commercialresidential === v}
                  onChange={() => setField('commercialresidential', v)}
                  className="accent-primary"
                />
                {v}
              </label>
            ))}
          </div>
        </div>

        {/* Permit type */}
        <div>
          <label htmlFor="buildingpermittype" className={labelCls}>
            Permit type
          </label>
          <select
            id="buildingpermittype"
            className={selectCls}
            value={values.buildingpermittype ?? ''}
            onChange={e => setField('buildingpermittype', e.target.value)}
          >
            <option value="">Select permit type…</option>
            {permitTypeOptions.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </div>

        {/* Proposed use: free text for context only; not a model input --> never affects the result */}
        <div>
          <label htmlFor="proposeduse" className={labelCls}>
            Proposed use
          </label>
          <input
            id="proposeduse"
            type="text"
            className={inputCls}
            placeholder="e.g. Single Family Dwelling"
            value={values.proposeduse ?? ''}
            onChange={e => setField('proposeduse', e.target.value)}
          />
          <p className="mt-1 text-xs text-muted">
            Free text; does not need to match an exact permit category.
          </p>
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">
          Work Details
        </legend>

        {/* Estimated value */}
        <div>
          <label htmlFor="estimatedvalue" className={labelCls}>
            Estimated value of work
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted text-sm select-none">$</span>
            <input
              id="estimatedvalue"
              type="number"
              min={0}
              step={1000}
              className={inputCls + ' pl-7'}
              placeholder="25,000"
              value={values.estimatedvalueofwork ?? ''}
              onChange={e => setField('estimatedvalueofwork', e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
        </div>

        {/* Job address */}
        <div>
          <label htmlFor="jobaddress" className={labelCls}>
            Job address
          </label>
          <input
            id="jobaddress"
            type="text"
            className={inputCls}
            placeholder="123 Kamehameha Hwy, Kaneohe 96744"
            value={values.jobaddress ?? ''}
            onChange={e => setField('jobaddress', e.target.value)}
          />
        </div>

        {/* Work-type flags */}
        <div>
          <span className={labelCls}>Work scope</span>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 mt-1">
            {WORK_FLAGS.map(({ key, label }) => (
              <label key={key} className="flex items-center gap-2 cursor-pointer text-sm text-ink">
                <input
                  type="checkbox"
                  checked={Boolean(values[key])}
                  onChange={e => setField(key, e.target.checked as PermitData[typeof key])}
                  className="accent-primary rounded"
                />
                {label}
              </label>
            ))}
          </div>
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-xs font-semibold uppercase tracking-widest text-muted mb-3">
          Parties <span className="normal-case font-normal">(optional)</span>
        </legend>

        <div>
          <label htmlFor="applicant" className={labelCls}>Applicant</label>
          <input
            id="applicant"
            type="text"
            className={inputCls}
            placeholder="Jane Smith"
            value={values.applicant ?? ''}
            onChange={e => setField('applicant', e.target.value)}
          />
        </div>

        <div>
          <label htmlFor="planmaker" className={labelCls}>Plan maker / architect</label>
          <input
            id="planmaker"
            type="text"
            className={inputCls}
            placeholder="Blueprint Architecture Inc"
            value={values.planmaker ?? ''}
            onChange={e => setField('planmaker', e.target.value)}
          />
        </div>
      </fieldset>
    </form>
  );
}
