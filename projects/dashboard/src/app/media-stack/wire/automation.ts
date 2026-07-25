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
  /** Episode/movie rows when the problem is an aggregate missing/wanted summary. */
  items?: MediaStackAutomationProblemItemDto[] | null;
  /** Total count from the service block when items may be truncated. */
  itemCount?: number | null;
}

export interface MediaStackAutomationProblemItemDto {
  title: string;
  when?: string;
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
