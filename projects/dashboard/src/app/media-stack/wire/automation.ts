export type MediaStackAutomationServiceStatusDto =
  | 'healthy'
  | 'degraded'
  | 'down'
  | 'unknown';

export interface MediaStackAutomationServiceDto {
  id: string;
  name: string;
  status: string;
  detail?: string;
  latencyMs?: number | null;
}

export interface MediaStackAutomationPreviewItemDto {
  id: string;
  title: string;
  when?: string;
  kind?: string;
}

export interface MediaStackAutomationProblemDto {
  id: string;
  summary: string;
  serviceId?: string;
  severity?: string;
}

export interface MediaStackAutomationSummaryDto {
  generatedAt: string;
  services?: MediaStackAutomationServiceDto[] | null;
  preview?: MediaStackAutomationPreviewItemDto[] | null;
  problems?: MediaStackAutomationProblemDto[] | null;
  unavailable?: {
    services?: boolean;
    preview?: boolean;
    problems?: boolean;
  };
}
