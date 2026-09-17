import anthropic from '@lobehub/icons-static-svg/icons/anthropic.svg?raw';
import deepseek from '@lobehub/icons-static-svg/icons/deepseek.svg?raw';
import gemini from '@lobehub/icons-static-svg/icons/gemini.svg?raw';
import lmstudio from '@lobehub/icons-static-svg/icons/lmstudio.svg?raw';
import ollama from '@lobehub/icons-static-svg/icons/ollama.svg?raw';
import openai from '@lobehub/icons-static-svg/icons/openai.svg?raw';
import openrouter from '@lobehub/icons-static-svg/icons/openrouter.svg?raw';
import qwen from '@lobehub/icons-static-svg/icons/qwen.svg?raw';

/**
 * Real provider marks from `@lobehub/icons-static-svg` (MIT). They are monochrome and use
 * `currentColor`, so the brand colour is applied by the card rather than baked into the asset.
 */
const MARKS: Record<string, string> = { openai, anthropic, gemini, deepseek, qwen, openrouter, ollama, lmstudio };
const CUSTOM_MARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8.5 12 4l8 4.5v7L12 20l-8-4.5z"/><path d="M12 12v8"/><path d="M4 8.5 12 12l8-3.5"/></svg>';

/** Published brand colours. Local runtimes are monochrome brands, so they follow the theme. */
export const BRAND_COLORS: Record<string, string> = {
  openai: '#10a37f',
  anthropic: '#d97757',
  gemini: '#4285f4',
  deepseek: '#4d6bfe',
  qwen: '#615ced',
  openrouter: '#6467f2',
};

export const brandColor = (id: string) => BRAND_COLORS[id] ?? 'var(--muted)';

export function ProviderIcon({ id }: { id: string }) {
  // The wrapper carries the accessible name of the provider card; the mark itself is decorative.
  const mark = (MARKS[id] ?? CUSTOM_MARK).replace(/<title>[\s\S]*?<\/title>/, '');
  return <span className="provider-icon" aria-hidden="true" dangerouslySetInnerHTML={{ __html: mark }} />;
}
