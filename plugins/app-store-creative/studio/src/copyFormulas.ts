export interface CopyFormula {
  category: string;
  role: 'Hero' | 'Feature' | 'Benefit' | 'Stats' | 'Ecosystem' | 'CTA';
  headline: string;
  subheadline: string;
}

export const COPY_FORMULAS: CopyFormula[] = [
  {
    category: 'Developer & macOS Native',
    role: 'Hero',
    headline: 'Instant Recall for Every Clip',
    subheadline: 'Keyboard-driven clipboard history built natively for macOS Sonoma & Sequoia',
  },
  {
    category: 'Developer & macOS Native',
    role: 'Feature',
    headline: 'Code, Colors & Rich Formatting',
    subheadline: 'Syntax-highlighted snippets, hex color previews, and rich text intact',
  },
  {
    category: 'Developer & macOS Native',
    role: 'Benefit',
    headline: 'Zero Context Switching',
    subheadline: 'Summon anywhere with ⌥V, search instantly, and paste without missing a beat',
  },
  {
    category: 'Developer & macOS Native',
    role: 'Stats',
    headline: 'Organized in Smart Collections',
    subheadline: 'Tag snippets, pin daily commands, and keep your workspace clutter-free',
  },
  {
    category: 'Developer & macOS Native',
    role: 'CTA',
    headline: 'Privacy-First & Fully Local',
    subheadline: 'Encrypted on-device storage. No analytics, no cloud syncing, zero tracking',
  },
  {
    category: 'Habit & Productivity',
    role: 'Hero',
    headline: 'Build Habits That Last',
    subheadline: 'Effortless tracking designed for daily focus and momentum',
  },
  {
    category: 'Habit & Productivity',
    role: 'Feature',
    headline: 'Insights at a Glance',
    subheadline: 'Interactive streaks and smart completion heatmaps',
  },
  {
    category: 'Finance & Budget',
    role: 'Hero',
    headline: 'Master Your Cashflow',
    subheadline: 'Instant expense logging with zero friction and smart categorisation',
  },
  {
    category: 'Fitness & Health',
    role: 'Hero',
    headline: 'Precision Workout Tracking',
    subheadline: 'Automated set counting, rest timers, and heart-rate zone sync',
  },
  {
    category: 'AI & Creative Tools',
    role: 'Hero',
    headline: 'Supercharge Your Creative Flow',
    subheadline: 'Generative intelligence seamlessly embedded in your production pipeline',
  },
];
