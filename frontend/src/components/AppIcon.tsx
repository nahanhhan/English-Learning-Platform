import type { CSSProperties } from 'react'
import type { LucideIcon } from 'lucide-react'

export interface AppIconProps {
  icon: LucideIcon
  size?: number
  strokeWidth?: number
  fill?: string
  className?: string
  style?: CSSProperties
  label?: string
}

/** 统一全站纤细线性图标，保持一致的线条粗细与无障碍属性。 */
export default function AppIcon({
  icon: Icon,
  size = 15,
  strokeWidth = 1.65,
  fill = 'none',
  className,
  style,
  label,
}: AppIconProps) {
  return (
    <Icon
      size={size}
      strokeWidth={strokeWidth}
      absoluteStrokeWidth
      fill={fill}
      className={className}
      style={style}
      aria-hidden={label ? undefined : true}
      aria-label={label}
    />
  )
}
