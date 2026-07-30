import type { Meta, StoryObj } from '@storybook/angular';
import { MmInput } from './input';

const meta: Meta<MmInput> = { title: 'UI/Input', component: MmInput, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmInput>;
export const Text: Story = { args: { kind: 'text', label: 'Title', placeholder: 'Enter a title' } };
export const Textarea: Story = { args: { kind: 'textarea', label: 'Notes', placeholder: 'Optional notes' } };
export const SearchPill: Story = { args: { kind: 'search-pill', placeholder: 'Search movies, shows, people…', shortcutLabel: 'Ctrl+K' } };
