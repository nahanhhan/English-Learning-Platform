import { theme, type ThemeConfig } from 'antd'

export type Appearance = 'dark' | 'light'

export const appearanceKey = 'elp-appearance'

export function readAppearance(): Appearance {
  try {
    return localStorage.getItem(appearanceKey) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function workspaceTheme(appearance: Appearance, motion: boolean): ThemeConfig {
  const dark = appearance === 'dark'
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: dark ? '#7168e8' : '#574ac7',
      colorLink: dark ? '#aca6ff' : '#574ac7',
      colorLinkHover: dark ? '#c8c3ff' : '#493cb4',
      colorText: dark ? '#ebebee' : '#232328',
      colorTextSecondary: dark ? '#a2a2ac' : '#60606d',
      colorTextTertiary: dark ? '#8c8c98' : '#6b6b77',
      colorBorder: dark ? '#34343c' : '#d9d9e0',
      colorBorderSecondary: dark ? '#28282e' : '#e4e4eb',
      colorBgLayout: dark ? '#131316' : '#fafafb',
      colorBgContainer: dark ? '#19191d' : '#ffffff',
      colorBgElevated: dark ? '#222227' : '#ffffff',
      fontFamily: "Inter, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
      fontSize: 13,
      controlHeight: 32,
      borderRadius: 6,
      motion,
    },
    components: {
      Card: { boxShadowTertiary: 'none', headerFontSize: 14 },
      Table: { headerBg: dark ? '#1b1b20' : '#f5f5f7', rowHoverBg: dark ? '#232328' : '#f3f3f6' },
      Segmented: {
        trackBg: dark ? '#1d1d22' : '#eeeef2',
        itemSelectedBg: dark ? '#33333b' : '#ffffff',
        itemSelectedColor: dark ? '#f1f1f4' : '#27272d',
      },
    },
  }
}
