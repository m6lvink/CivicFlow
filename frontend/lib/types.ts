// TypeScript types for CivicFlow API responses

export interface PermitData {
  buildingpermittype?: string;
  commercialresidential?: string;
  proposeduse?: string;
  estimatedvalueofwork?: number;
  jobaddress?: string;
  applicant?: string;
  planmaker?: string;
  solar?: boolean;
  solarvpinstallation?: boolean;
  newbuilding?: boolean;
  addition?: boolean;
  alteration?: boolean;
  demolition?: boolean;
  repair?: boolean;
  electricalwork?: boolean;
  plumbingwork?: boolean;
  retainingwall?: boolean;
  shellonly?: boolean;
  foundationonly?: boolean;
  pool?: boolean;
  fence?: boolean;
  ohana?: boolean;
  accessorydwellingunitadu?: boolean;
}

export type RiskBand = 'Fast' | 'Normal' | 'Slow' | 'High-risk';
export type FindingStatus = 'PASS' | 'FLAG' | 'FAIL' | 'N/A';
export type OverallStatus = 'READY' | 'REVIEW' | 'INCOMPLETE';

export interface PredictResponse {
  expected_wait_days: number;
  risk_band: RiskBand;
  fast_track_probability: number;
  confidence_interval_days: { low: number; high: number };
  top_factors: Array<{ feature: string; importance: number }>;
}

export interface Finding {
  id: string;
  description: string;
  status: FindingStatus;
  rationale: string;
}

export interface CheckResponse {
  overall_status: OverallStatus;
  permit_summary: string;
  metadata_mode: boolean;
  findings: Finding[];
  warnings: string[];
}

export interface HealthResponse {
  status: string;
  models_loaded: boolean;
}

export interface ExtractResponse {
  fields: PermitData;
  warnings: string[];
}

export interface SchemaResponse {
  categorical: Record<string, string[]>;
  high_cardinality: Record<string, number>;
  flags: string[];
  numeric: string[];
}
