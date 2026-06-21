'use client';

import { useRef, useState } from 'react';
import { Upload, FileText, X } from 'lucide-react';

const ACCEPTED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.webp'];

function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some(ext => name.endsWith(ext));
}

interface Props {
  files: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  disabled?: boolean;
}

export default function DropZone({ files, onAdd, onRemove, disabled }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function addFiles(list: FileList | File[]) {
    const accepted = Array.from(list).filter(isAccepted);
    if (accepted.length) onAdd(accepted);
  }

  return (
    <div className="space-y-3">
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors
                    ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-primary hover:bg-primary-light'}
                    ${dragOver ? 'border-primary bg-primary-light' : 'border-border'}`}
        onClick={() => !disabled && fileRef.current?.click()}
        onKeyDown={e => e.key === 'Enter' && !disabled && fileRef.current?.click()}
        onDragOver={e => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => {
          e.preventDefault();
          setDragOver(false);
          if (!disabled && e.dataTransfer.files) addFiles(e.dataTransfer.files);
        }}
        role="button"
        tabIndex={0}
        aria-label="Drop or upload permit documents"
      >
        <Upload className="mx-auto mb-3 text-muted" size={28} />
        <p className="text-sm font-medium text-ink">
          Drop your permit documents here
        </p>
        <p className="text-sm text-muted mt-1">
          or click to browse: application forms, plan sheets, anything you have
        </p>
        <p className="text-xs text-subtle mt-2">PDF, PNG, JPG, WEBP</p>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(',')}
        multiple
        disabled={disabled}
        className="hidden"
        onChange={e => {
          if (e.target.files) {
            addFiles(e.target.files);
            e.target.value = '';
          }
        }}
      />

      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center justify-between text-sm bg-surface border border-border rounded px-3 py-1.5"
            >
              <span className="flex items-center gap-2 text-ink truncate">
                <FileText size={14} className="shrink-0 text-muted" />
                <span className="truncate max-w-[260px]">{f.name}</span>
              </span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onRemove(i)}
                className="ml-2 text-muted hover:text-primary disabled:opacity-50 disabled:hover:text-muted transition-colors"
                aria-label={`Remove ${f.name}`}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
