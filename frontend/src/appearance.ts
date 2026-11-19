import { theme, type ThemeConfig } from 'antd'

export type Appearance = 'dark' | 'light'

export const appearanceKey = 'elp-appearance-v2'

export const WORKSPACE_FONT_FAMILY =
  "'Google Sans Flex Variable', 'Google Sans Flex', 'Noto Sans SC Variable', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif"

export function readAppearance(): Appearance {
  try {
    return localStorage.getItem(appearanceKey) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function workspaceTheme(appearance: Appearance, motion: boolean): ThemeConfig {
  const dark = appearance === 'dark'
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: dark ? '#0a84ff' : '#007aff',
      colorLink: dark ? '#0a84ff' : '#007aff',
      colorLinkHover: dark ? '#3399ff' : '#0066d6',
      colorSuccess: dark ? '#30d158' : '#248a3d',
      colorWarning: dark ? '#ff9f0a' : '#b25000',
      colorError: dark ? '#ff453a' : '#d70015',
      colorText: dark ? '#f5f5f7' : '#1d1d1f',
      colorTextSecondary: dark ? '#aeaeb2' : '#6e6e73',
      colorTextTertiary: dark ? '#8e8e93' : '#86868b',
      colorBorder: dark ? 'rgba(255, 255, 255, 0.14)' : 'rgba(0, 0, 0, 0.12)',
      colorBorderSecondary: dark ? 'rgba(255, 255, 255, 0.09)' : 'rgba(0, 0, 0, 0.08)',
      colorBgLayout: dark ? '#1c1c1e' : '#f5f5f7',
      colorBgContainer: dark ? '#2c2c2e' : '#ffffff',
      colorBgElevated: dark ? '#2c2c2e' : '#ffffff',
      colorFillSecondary: dark ? '#3a3a3c' : '#f2f2f7',
      colorFillTertiary: dark ? '#242426' : '#e5e5ea',
      fontFamily: WORKSPACE_FONT_FAMILY,
      fontSize: 14,
      controlHeight: 36,
      controlHeightLG: 42,
      controlHeightSM: 28,
      borderRadius: 10,
      borderRadiusLG: 14,
      borderRadiusSM: 8,
      boxShadowSecondary: dark
        ? '0 22px 60px rgba(0, 0, 0, 0.56), 0 0 0 1px rgba(255, 255, 255, 0.12)'
        : '0 18px 48px rgba(0, 0, 0, 0.16), 0 0 0 1px rgba(0, 0, 0, 0.08)',
      motion,
    },
    components: {
      Card: {
        boxShadowTertiary: dark
          ? '0 2px 6px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.05)'
          : '0 1px 2px rgba(0, 0, 0, 0.04), 0 6px 18px rgba(0, 0, 0, 0.035)',
        headerFontSize: 15,
        borderRadiusLG: 14,
      },
      Button: {
        borderRadius: 10,
        borderRadiusLG: 12,
        borderRadiusSM: 8,
        defaultShadow: 'none',
        primaryShadow: 'none',
        dangerShadow: 'none',
      },
      Input: {
        borderRadius: 10,
        borderRadiusLG: 12,
        colorBgContainer: dark ? '#3a3a3c' : '#f2f2f7',
        activeBg: dark ? '#3a3a3c' : '#ffffff',
      },
      Select: {
        borderRadius: 10,
        borderRadiusLG: 12,
        optionSelectedBg: dark ? 'rgba(10, 132, 255, 0.22)' : 'rgba(0, 122, 255, 0.11)',
      },
      InputNumber: {
        borderRadius: 10,
        colorBgContainer: dark ? '#3a3a3c' : '#f2f2f7',
        activeBg: dark ? '#3a3a3c' : '#ffffff',
      },
      Modal: {
        borderRadiusLG: 16,
        contentBg: dark ? '#2c2c2e' : '#ffffff',
        headerBg: dark ? '#2c2c2e' : '#ffffff',
      },
      Table: {
        headerBg: dark ? '#3a3a3c' : '#f2f2f7',
        rowHoverBg: dark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.035)',
        borderColor: dark ? 'rgba(255, 255, 255, 0.09)' : 'rgba(0, 0, 0, 0.08)',
      },
      Segmented: {
        trackBg: dark ? '#242426' : '#e5e5ea',
        trackPadding: 3,
        borderRadius: 10,
        borderRadiusSM: 7.5,
        itemSelectedBg: dark ? '#3a3a3c' : '#ffffff',
        itemSelectedColor: dark ? '#f5f5f7' : '#1d1d1f',
        itemColor: dark ? '#aeaeb2' : '#6e6e73',
        itemHoverColor: dark ? '#f5f5f7' : '#1d1d1f',
        itemHoverBg: 'transparent',
        itemActiveBg: 'transparent',
      },
      Switch: {
        colorPrimary: dark ? '#30d158' : '#34c759',
        colorPrimaryHover: dark ? '#3ad762' : '#2db84e',
        trackHeight: 24,
        trackMinWidth: 42,
        handleSize: 20,
        innerMinMargin: 4,
        innerMaxMargin: 24,
      },
      Tag: {
        borderRadiusSM: 999,
      },
      Progress: {
        defaultColor: dark ? '#0a84ff' : '#007aff',
        remainingColor: dark ? '#242426' : '#e5e5ea',
      },
      Alert: {
        borderRadiusLG: 12,
      },
    },
  }
}
