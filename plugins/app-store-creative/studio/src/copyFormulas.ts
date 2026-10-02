export interface CopyFormula {
  category: string;
  role: 'Hero' | 'Feature' | 'Benefit' | 'Stats' | 'CTA';
  headline: string;
  subheadline: string;
}

export const COPY_FORMULAS: CopyFormula[] = [
  {
    category: 'Habit & Productivity',
    role: 'Hero',
    headline: 'Build Habits That Last',
    subheadline: 'Effortless tracking designed for daily focus',
  },
  {
    category: 'Habit & Productivity',
    role: 'Feature',
    headline: 'Insights at a Glance',
    subheadline: 'Smart completion heatmaps and streak analytics',
  },
  {
    category: 'Finance & Budget',
    role: 'Hero',
    headline: 'Master Your Money',
    subheadline: 'Instant expense logging with zero friction',
  },
  {
    category: 'Finance & Budget',
    role: 'Stats',
    headline: 'Clarity on Every Dollar',
    subheadline: 'Real-time category breakdown and budget pace',
  },
  {
    category: 'Fitness & Health',
    role: 'Hero',
    headline: 'Crush Every Workout',
    subheadline: 'Precision sets, rest timers and heart rate sync',
  },
  {
    category: 'Fitness & Health',
    role: 'Benefit',
    headline: 'Recovery Powered by Science',
    subheadline: 'Sleep readiness and workout strain scores',
  },
  {
    category: 'AI & Developer Tools',
    role: 'Hero',
    headline: 'Supercharge Your Workflow',
    subheadline: 'Agentic intelligence right in your terminal',
  },
  {
    category: 'AI & Developer Tools',
    role: 'Feature',
    headline: 'Deterministic & Fast',
    subheadline: '100% reproducible releases with zero overhead',
  },
  {
    category: 'Ecosystem & Widgets',
    role: 'CTA',
    headline: 'Right on Your Lock Screen',
    subheadline: 'Interactive widgets and StandBy mode ready',
  },
];
