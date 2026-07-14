import {
  DiscoverAction,
  DiscoverItem,
  DiscoverRequestPayload,
  ExternalDiscover,
  ExternalDiscoverItem,
  HermesDiscover,
} from '../../discover/discover.models';
import {
  MediaStackDiscoverActionDto,
  MediaStackDiscoverItemDto,
  MediaStackDiscoverRequestPayloadDto,
  MediaStackExternalDiscoverDto,
  MediaStackExternalDiscoverItemDto,
  MediaStackHermesDiscoverDto,
} from '../wire/discover';

export const mapDiscoverItem = (dto: MediaStackDiscoverItemDto): DiscoverItem => ({ ...dto });

export const mapExternalDiscoverItem = (dto: MediaStackExternalDiscoverItemDto): ExternalDiscoverItem => ({
  ...dto,
});

export const mapHermesDiscover = (dto: MediaStackHermesDiscoverDto): HermesDiscover => ({
  ok: dto.ok,
  items: (dto.items ?? []).map(mapDiscoverItem),
  pending_request_sync: dto.pending_request_sync,
  generation_request: dto.generation_request,
  error: dto.error,
});

export const mapExternalDiscover = (dto: MediaStackExternalDiscoverDto): ExternalDiscover => ({
  ok: dto.ok,
  items: (dto.items ?? []).map(mapExternalDiscoverItem),
  error: dto.error,
});

export const mapDiscoverAction = (dto: MediaStackDiscoverActionDto): DiscoverAction => ({ ...dto });

export const toDiscoverRequestPayloadDto = (
  payload: DiscoverRequestPayload,
): MediaStackDiscoverRequestPayloadDto => ({ ...payload });
