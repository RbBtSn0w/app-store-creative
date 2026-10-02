import { ThemeConfig } from './types';

export type StylePresetId =
  | 'liquid_glass'
  | 'swiss_grid'
  | 'midnight_glow'
  | 'quiet_japandi'
  | 'bento_keynote'
  | 'candy_pop'
  | 'neon_athletic'
  | 'magazine_editorial'
  | 'soft_clay'
  | 'pastel_dream'
  | 'vintage_travel'
  | 'cyber_matrix'
  | 'clean_light'
  | 'dark_contrast'
  | 'ocean_gradient'
  | 'sunset_warmth'
  | 'forest_minimal'
  | 'monochrome_bold';

export interface StylePresetDefinition {
  id: StylePresetId;
  name: string;
  category: string;
  theme: Partial<ThemeConfig>;
}

export const STYLE_PRESETS: Record<StylePresetId, StylePresetDefinition> = {
  liquid_glass: {
    id: 'liquid_glass',
    name: 'Liquid Glass Aurora',
    category: 'Premium iOS Utilities & AI',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#0B132B', '#1C2541', '#3A506B', '#5BC0BE'],
        angle: 135,
      },
      headlineColor: '#FFFFFF',
      subheadlineColor: 'rgba(255, 255, 255, 0.85)',
      bezelStyle: 'titanium_natural',
      shadow: 'dramatic',
    },
  },
  swiss_grid: {
    id: 'swiss_grid',
    name: 'Swiss Grid Bold',
    category: 'Finance, Dev Tools & B2B',
    theme: {
      background: {
        type: 'solid',
        colors: ['#000000'],
      },
      headlineColor: '#FFFFFF',
      subheadlineColor: 'rgba(255, 255, 255, 0.7)',
      bezelStyle: 'flat',
      shadow: 'none',
    },
  },
  midnight_glow: {
    id: 'midnight_glow',
    name: 'Midnight Glow Pro',
    category: 'AI, Power Utilities & Dark Mode',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#050508', '#0E1324', '#1A103C'],
        angle: 145,
      },
      headlineColor: '#60A5FA',
      subheadlineColor: 'rgba(255, 255, 255, 0.75)',
      bezelStyle: 'midnight',
      shadow: 'dramatic',
    },
  },
  quiet_japandi: {
    id: 'quiet_japandi',
    name: 'Quiet Japandi',
    category: 'Reading, Notes & Minimalist Wellness',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#E8E5DF', '#D9D5CC'],
        angle: 180,
      },
      headlineColor: '#2B2927',
      subheadlineColor: '#5C5852',
      bezelStyle: 'silver',
      shadow: 'soft',
    },
  },
  bento_keynote: {
    id: 'bento_keynote',
    name: 'Bento Keynote Grid',
    category: 'Productivity & Feature-Dense Apps',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#111827', '#1F2937', '#111827'],
        angle: 135,
      },
      headlineColor: '#F9FAFB',
      subheadlineColor: '#9CA3AF',
      bezelStyle: 'titanium_black',
      shadow: 'dramatic',
    },
  },
  candy_pop: {
    id: 'candy_pop',
    name: 'Candy Pop Social',
    category: 'Social, Friends & Gen-Z',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#FF6B6B', '#FF8E53', '#FFA07A'],
        angle: 125,
      },
      headlineColor: '#FFFFFF',
      subheadlineColor: 'rgba(255, 255, 255, 0.9)',
      bezelStyle: 'silver',
      shadow: 'dramatic',
    },
  },
  neon_athletic: {
    id: 'neon_athletic',
    name: 'Neon Athletic Night',
    category: 'Fitness, Running & Strength',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#0A0A0A', '#171717', '#0F2027'],
        angle: 150,
      },
      headlineColor: '#A3E635',
      subheadlineColor: '#E2E8F0',
      bezelStyle: 'titanium_black',
      shadow: 'dramatic',
    },
  },
  magazine_editorial: {
    id: 'magazine_editorial',
    name: 'Magazine Cover Editorial',
    category: 'Food, Coffee, Travel & Lifestyle',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#FBF9F5', '#F2EFE9'],
        angle: 180,
      },
      headlineColor: '#1A1A1A',
      subheadlineColor: '#4A4A4A',
      bezelStyle: 'silver',
      shadow: 'soft',
    },
  },
  soft_clay: {
    id: 'soft_clay',
    name: 'Soft Clay Wellness',
    category: 'Meditation, Sleep & Journaling',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#2D3748', '#4A5568'],
        angle: 135,
      },
      headlineColor: '#F7FAFC',
      subheadlineColor: '#CBD5E0',
      bezelStyle: 'natural',
      shadow: 'soft',
    },
  },
  pastel_dream: {
    id: 'pastel_dream',
    name: 'Pastel Dream',
    category: 'Couples, Pets & Friendly Tools',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#C4B5FD', '#FBCFE8', '#FDE68A'],
        angle: 135,
      },
      headlineColor: '#1F2937',
      subheadlineColor: '#4B5563',
      bezelStyle: 'silver',
      shadow: 'soft',
    },
  },
  vintage_travel: {
    id: 'vintage_travel',
    name: 'Vintage Travel Poster',
    category: 'Outdoors, Weather & Exploration',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#1E3A8A', '#0D9488', '#F59E0B'],
        angle: 145,
      },
      headlineColor: '#FFFFFF',
      subheadlineColor: 'rgba(255, 255, 255, 0.85)',
      bezelStyle: 'natural',
      shadow: 'dramatic',
    },
  },
  cyber_matrix: {
    id: 'cyber_matrix',
    name: 'Cyber Matrix',
    category: 'Security, Crypto & Dev Tools',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#020617', '#0F172A', '#022C22'],
        angle: 180,
      },
      headlineColor: '#34D399',
      subheadlineColor: '#94A3B8',
      bezelStyle: 'titanium_black',
      shadow: 'dramatic',
    },
  },
  clean_light: {
    id: 'clean_light',
    name: 'Clean Light Minimal',
    category: 'Standard Professional Light Theme',
    theme: {
      background: {
        type: 'solid',
        colors: ['#F8FAFC'],
      },
      headlineColor: '#0F172A',
      subheadlineColor: '#475569',
      bezelStyle: 'silver',
      shadow: 'subtle',
    },
  },
  dark_contrast: {
    id: 'dark_contrast',
    name: 'Dark Contrast OLED',
    category: 'Pure OLED Dark Mode',
    theme: {
      background: {
        type: 'solid',
        colors: ['#09090B'],
      },
      headlineColor: '#FAFAFA',
      subheadlineColor: '#A1A1AA',
      bezelStyle: 'titanium_black',
      shadow: 'dramatic',
    },
  },
  ocean_gradient: {
    id: 'ocean_gradient',
    name: 'Deep Ocean Gradient',
    category: 'Utilities, Analytics & Cloud',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#0F2027', '#203A43', '#2C5364'],
        angle: 135,
      },
      headlineColor: '#38BDF8',
      subheadlineColor: '#E0F2FE',
      bezelStyle: 'natural',
      shadow: 'dramatic',
    },
  },
  sunset_warmth: {
    id: 'sunset_warmth',
    name: 'Sunset Warmth',
    category: 'Creativity, Photography & Art',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#4A0E2E', '#87103F', '#C7384D'],
        angle: 135,
      },
      headlineColor: '#FEF08A',
      subheadlineColor: '#FFE4E6',
      bezelStyle: 'natural',
      shadow: 'dramatic',
    },
  },
  forest_minimal: {
    id: 'forest_minimal',
    name: 'Forest Minimalist',
    category: 'Sustainability, Focus & Reading',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#062C22', '#064E3B', '#022C22'],
        angle: 145,
      },
      headlineColor: '#6EE7B7',
      subheadlineColor: '#A7F3D0',
      bezelStyle: 'titanium_natural',
      shadow: 'dramatic',
    },
  },
  monochrome_bold: {
    id: 'monochrome_bold',
    name: 'Monochrome Bold',
    category: 'Modern Editorial & Architecture',
    theme: {
      background: {
        type: 'gradient',
        colors: ['#18181B', '#27272A', '#18181B'],
        angle: 135,
      },
      headlineColor: '#FFFFFF',
      subheadlineColor: '#A1A1AA',
      bezelStyle: 'flat',
      shadow: 'subtle',
    },
  },
};
