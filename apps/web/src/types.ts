export interface Metric {
  status: 'available' | 'insufficient_data' | 'invalid_input';
  value: number | null;
  unit: string;
  reason: string;
}
export interface Provenance {
  source: string;
  fetched_at: string;
  is_stale: boolean;
  attribution_text: string;
  attribution_url: string;
  licence_url: string | null;
  modifications: string;
  data_status: 'complete' | 'partial' | 'empty';
  missing_reasons: string[];
}
export interface Series {
  time: string[];
  values: Record<string, (number | null)[]>;
  units: Record<string, string>;
}
export interface Weather extends Provenance {
  daily: Series;
  location: {latitude: number; longitude: number};
}
export interface Place {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  admin1: string | null;
  admin2: string | null;
}
export interface Places extends Provenance {places: Place[]}
export interface Citation {title: string; url: string; locator: string; region?: string}
export interface Action {
  explanation: string | null;
  explanation_status: string;
  explanation_sources: string[];
  date: string;
  kind: string;
  reason: string;
  metrics: Record<string, Metric>;
  inputs: {field: string; value: number | null; unit: string; valid_at: string}[];
  citations: Citation[];
  water_balance: {
    coefficient: Metric;
    crop_et_mm: Metric;
    rainfall_shortfall_mm: Metric;
    stage: string | null;
    stage_basis: string | null;
    warning: string;
    citations: Citation[];
  };
}
export interface Plan {
  agent_note: string;
  trace_id: string | null;
  crop: string;
  sowing_date: string | null;
  rule_version: string;
  actions: Action[];
  evidence: Weather;
  limitation: string;
  water_balance_availability: string;
  optional_evidence_notes: string[];
  disabled_parameters: {parameter: string; reason: string}[];
}
export interface Soil extends Provenance {
  properties: {name: string; depth: string; value: number | null; unit: string}[];
}
export interface Flood extends Provenance {daily: Series; limitation: string}
export interface Power extends Provenance {daily: Series; evidence_role: string; limitation: string}
export interface RequestBody {
  api_version: '1.0';
  latitude: number;
  longitude: number;
  crop: string;
  sowing_status: 'growing' | 'not_sown';
  sowing_date: string | null;
  growth_stage: 'flowering' | 'other' | null;
  agronomy_context: {
    district: string;
    allow_fao_reference: boolean;
  };
}
