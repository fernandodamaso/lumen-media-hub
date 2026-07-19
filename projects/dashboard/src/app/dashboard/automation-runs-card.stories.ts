import { computed, signal } from '@angular/core';
import { type Meta, type StoryObj } from '@storybook/angular';
import { AutomationFacade, AutomationStatus } from '../automation/automation.facade';
import { AutomationSummary } from '../automation/automation.models';
import { CronRun } from '../reports/reports.models';
import { AutomationRunsCard } from './automation-runs-card';

function createFacade(status: AutomationStatus, runs: CronRun[], error = '') {
  const tasks = signal<CronRun[]>(runs);
  return {
    status: signal<AutomationStatus>(status),
    summary: signal<AutomationSummary | null>(null),
    error: signal(error),
    health: signal({ overall: 'unknown' as const, actionableCount: 0 }),
    tasks,
    latestRuns: computed(() => tasks().slice(0, 3)),
    startPolling: () => {},
    refresh: async () => {},
  };
}

const meta: Meta<AutomationRunsCard> = {
  title: 'Dashboard/AutomationRunsCard',
  component: AutomationRunsCard,
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<AutomationRunsCard>;

const runs: CronRun[] = [
  {
    id: 'cleanup-1',
    jobId: 'cleanup',
    jobTitle: 'Hardlink cleanup',
    status: 'ok',
    triage: 'quiet',
    timestamp: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
    detail: '42 files hardlinked, 18.7 GB saved',
    fatal: null,
    applied: null,
    exitCode: null,
    schedule: 'Maintenance',
  },
  {
    id: 'metadata-1',
    jobId: 'metadata',
    jobTitle: 'Stale metadata',
    status: 'fatal',
    triage: 'actionable',
    timestamp: new Date(Date.now() - 18 * 60 * 1000).toISOString(),
    detail: '',
    fatal: '3 items failed to refresh',
    applied: null,
    exitCode: 1,
    schedule: 'Metadata',
  },
  {
    id: 'watchdog-1',
    jobId: 'watchdog',
    jobTitle: 'Watchdog',
    status: 'ok',
    triage: 'quiet',
    timestamp: new Date(Date.now() - 35 * 60 * 1000).toISOString(),
    detail: 'All services are healthy',
    fatal: null,
    applied: null,
    exitCode: null,
    schedule: 'Monitoring',
  },
];

export const Default: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: AutomationFacade, useValue: createFacade('ready', runs) }],
    },
    template: `<div style="max-width:640px"><mm-automation-runs-card /></div>`,
  }),
};

export const Loading: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: AutomationFacade, useValue: createFacade('loading', []) }],
    },
    template: `<div style="max-width:640px"><mm-automation-runs-card /></div>`,
  }),
};

export const Error: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: AutomationFacade, useValue: createFacade('error', [], 'Automation runs are temporarily unavailable. Try again.') }],
    },
    template: `<div style="max-width:640px"><mm-automation-runs-card /></div>`,
  }),
};

export const Empty: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [{ provide: AutomationFacade, useValue: createFacade('ready', []) }],
    },
    template: `<div style="max-width:640px"><mm-automation-runs-card /></div>`,
  }),
};

export const RetainedRefreshNotice: Story = {
  render: () => ({
    moduleMetadata: {
      providers: [
        {
          provide: AutomationFacade,
          useValue: createFacade(
            'ready',
            runs,
            'Could not refresh automation runs. Showing last loaded history.',
          ),
        },
      ],
    },
    template: `<div style="max-width:640px"><mm-automation-runs-card /></div>`,
  }),
};
