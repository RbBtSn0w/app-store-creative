export type CopyRole = 'Hero' | 'Mechanism' | 'Depth' | 'Ecosystem' | 'CTA' | 'Feature' | 'Benefit' | 'Stats';

export interface CopyFormula {
  category: string;
  role: CopyRole;
  headline: string;
  subheadline: string;
}

export const COPY_FORMULAS: CopyFormula[] = [
  // 1. Developer & macOS Native
  {
    category: 'Developer & macOS Native',
    role: 'Hero',
    headline: 'Instant Recall for Every Clip',
    subheadline: 'Keyboard-driven clipboard history built natively for macOS Sonoma & Sequoia',
  },
  {
    category: 'Developer & macOS Native',
    role: 'Mechanism',
    headline: 'Lightning-Fast Fuzzy Search',
    subheadline: 'Instant indexing and keystroke recall without touching the mouse',
  },
  {
    category: 'Developer & macOS Native',
    role: 'Depth',
    headline: 'Syntax & Rich Format Inspector',
    subheadline: 'Syntax-highlighted snippets, hex color previews, and rich formatting intact',
  },
  {
    category: 'Developer & macOS Native',
    role: 'Ecosystem',
    headline: 'System-Wide Quick Summon',
    subheadline: 'Global hotkey ⌥V anywhere, menu bar companion, and Shortcuts integration',
  },
  {
    category: 'Developer & macOS Native',
    role: 'CTA',
    headline: 'Private, Local & Zero Tracking',
    subheadline: 'On-device encrypted database. No analytics, no cloud telemetry, fail-closed security',
  },

  // 2. Productivity & Workflow
  {
    category: 'Productivity & Workflow',
    role: 'Hero',
    headline: 'Focus on What Truly Matters',
    subheadline: 'Streamlined task execution and distraction-free workflow designed for makers',
  },
  {
    category: 'Productivity & Workflow',
    role: 'Mechanism',
    headline: 'Automated Daily Prioritization',
    subheadline: 'Smart scheduling algorithms balance urgent deadlines with deep-work blocks',
  },
  {
    category: 'Productivity & Workflow',
    role: 'Depth',
    headline: 'Deep Work Analytics & Trends',
    subheadline: 'Measure cognitive endurance, identify context switches, and refine focus habits',
  },
  {
    category: 'Productivity & Workflow',
    role: 'Ecosystem',
    headline: 'Seamless Multi-Device Sync',
    subheadline: 'Encrypted end-to-end sync across Mac, iPad, iPhone, and Apple Watch',
  },
  {
    category: 'Productivity & Workflow',
    role: 'CTA',
    headline: 'Reclaim Your Time Today',
    subheadline: 'Experience effortless flow with a frictionless, zero-configuration setup',
  },

  // 3. Finance & Expense
  {
    category: 'Finance & Expense',
    role: 'Hero',
    headline: 'Master Your Personal Cashflow',
    subheadline: 'Real-time financial clarity and intuitive budgeting without spreadsheet chaos',
  },
  {
    category: 'Finance & Expense',
    role: 'Mechanism',
    headline: 'One-Tap Frictionless Logging',
    subheadline: 'Natural language parsing and interactive widgets record expenses in seconds',
  },
  {
    category: 'Finance & Expense',
    role: 'Depth',
    headline: 'Predictive Runway & Projections',
    subheadline: 'Forecast future recurring cashflow and uncover hidden subscription leaks',
  },
  {
    category: 'Finance & Expense',
    role: 'Ecosystem',
    headline: 'Live Activities & Lock Screen',
    subheadline: 'Check remaining daily budget at a glance with glanceable Dynamic Island widgets',
  },
  {
    category: 'Finance & Expense',
    role: 'CTA',
    headline: 'Your Wealth, Completely Private',
    subheadline: 'Zero bank credential storage, strictly sandboxed local vault, 100% confidential',
  },

  // 4. AI & Creative Studio
  {
    category: 'AI & Creative Studio',
    role: 'Hero',
    headline: 'Supercharge Your Creative Flow',
    subheadline: 'Generative intelligence seamlessly embedded in your production pipeline',
  },
  {
    category: 'AI & Creative Studio',
    role: 'Mechanism',
    headline: 'Iterative Canvas Co-Creation',
    subheadline: 'Steer visual compositions with live tactile sliders and intelligent prompt synthesis',
  },
  {
    category: 'AI & Creative Studio',
    role: 'Depth',
    headline: 'Lossless 1:1 Pixel Export',
    subheadline: 'Zero-artifact vector rasterization and exact App Store specification compliance',
  },
  {
    category: 'AI & Creative Studio',
    role: 'Ecosystem',
    headline: 'Scriptable Agent Directives',
    subheadline: 'Bi-directional critique mailbox enables autonomous agent refinement loops',
  },
  {
    category: 'AI & Creative Studio',
    role: 'CTA',
    headline: 'Ship Polished Storefronts Faster',
    subheadline: 'From real product captures to verified delivery packages in minutes',
  },

  // 5. Fitness & Health
  {
    category: 'Fitness & Health',
    role: 'Hero',
    headline: 'Precision Performance Tracking',
    subheadline: 'Automated set counting, rest timers, and biometric zone synchronization',
  },
  {
    category: 'Fitness & Health',
    role: 'Mechanism',
    headline: 'Adaptive Progressive Overload',
    subheadline: 'Dynamic weight suggestions calculated from velocity and rate of perceived exertion',
  },
  {
    category: 'Fitness & Health',
    role: 'Depth',
    headline: 'Comprehensive Recovery Metrics',
    subheadline: 'Heart-rate variability, sleep architecture, and nervous system readiness scores',
  },
  {
    category: 'Fitness & Health',
    role: 'Ecosystem',
    headline: 'Apple HealthKit Native',
    subheadline: 'Two-way synchronization with HealthKit, WorkoutKit, and Apple Watch sensors',
  },
  {
    category: 'Fitness & Health',
    role: 'CTA',
    headline: 'Unlock Your Peak Potential',
    subheadline: 'Start training with scientific rigor and evidence-based performance insights',
  },
];
