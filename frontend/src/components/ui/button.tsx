import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import type { ComponentProps } from 'react'
import { twMerge } from 'tailwind-merge'

const variants = cva('button', {
  variants: { variant: { default: 'primary', outline: 'outline', ghost: 'ghost', danger: 'danger' } },
  defaultVariants: { variant: 'default' },
})
export function Button({ asChild, variant, className, ...props }: ComponentProps<'button'> & VariantProps<typeof variants> & {asChild?: boolean}) {
  const Component = asChild ? Slot : 'button'
  return <Component className={twMerge(variants({variant}), className)} {...props} />
}
