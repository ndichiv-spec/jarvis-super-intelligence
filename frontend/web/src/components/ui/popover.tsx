"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

const Popover = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<"div"> & { placement?: string }
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("z-50 w-fit rounded-md border bg-popover text-popover-foreground shadow-md outline-none")} {...props} />
))
Popover.displayName = "Popover"

const PopoverTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ComponentPropsWithoutRef<"button">
>(({ className, ...props }, ref) => (
  <button ref={ref} className={cn(className)} {...props} />
))
PopoverTrigger.displayName = "PopoverTrigger"

const PopoverContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<"div"> & { align?: string; sideOffset?: number; className?: string }
>(({ className, align = "center", sideOffset = 4, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "z-50 w-64 rounded-md border bg-popover p-2 text-popover-foreground shadow-md outline-none",
      "data-[state=open]:data-[side=bottom]:slide-in-from-top-2",
      className
    )}
    {...props}
  />
))
PopoverContent.displayName = "PopoverContent"

export { Popover, PopoverTrigger, PopoverContent }
