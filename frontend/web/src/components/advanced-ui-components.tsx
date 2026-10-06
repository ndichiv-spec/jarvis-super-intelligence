'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence, useAnimation } from 'framer-motion';
import { cn } from '@/lib/utils';
import { useAdvancedTheme } from './advanced-theme-system';

// Advanced Glass Card Component
interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
  variant?: 'default' | 'neumorphic' | 'holographic' | 'cyberpunk';
}

export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className,
  hover = true,
  glow = true,
  variant = 'default'
}) => {
  const { theme } = useAdvancedTheme();
  const [isHovered, setIsHovered] = useState(false);

  const getCardStyles = () => {
    switch (variant) {
      case 'neumorphic':
        return {
          background: 'linear-gradient(145deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05))',
          boxShadow: isHovered 
            ? '20px 20px 60px rgba(0,0,0,0.5), -20px -20px 60px rgba(255,255,255,0.1)'
            : '10px 10px 30px rgba(0,0,0,0.5), -10px -10px 30px rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.1)'
        };
      case 'holographic':
        return {
          background: `linear-gradient(135deg, ${theme.colors.primary}20, ${theme.colors.secondary}20, ${theme.colors.accent}20)`,
          boxShadow: isHovered 
            ? `0 0 40px ${theme.colors.glow}, inset 0 0 20px rgba(255,255,255,0.1)`
            : `0 0 20px ${theme.colors.glow}, inset 0 0 10px rgba(255,255,255,0.05)`,
          border: `1px solid ${theme.colors.primary}40`,
          backdropFilter: 'blur(10px)'
        };
      case 'cyberpunk':
        return {
          background: 'linear-gradient(135deg, rgba(255,0,128,0.1), rgba(0,255,255,0.1))',
          boxShadow: isHovered 
            ? '0 0 30px rgba(255,0,128,0.5), inset 0 0 15px rgba(0,255,255,0.2)'
            : '0 0 15px rgba(255,0,128,0.3), inset 0 0 8px rgba(0,255,255,0.1)',
          border: '2px solid transparent',
          borderImage: `linear-gradient(45deg, ${theme.colors.primary}, ${theme.colors.secondary}) 1`,
          backdropFilter: 'blur(8px)'
        };
      default:
        return {
          background: 'rgba(255,255,255,0.05)',
          boxShadow: isHovered 
            ? `0 8px 32px 0 ${theme.colors.glow}`
            : `0 4px 16px 0 rgba(0,0,0,0.3)`,
          border: `1px solid ${theme.colors.border}`,
          backdropFilter: 'blur(10px)'
        };
    }
  };

  return (
    <motion.div
      className={cn('rounded-xl p-6 transition-all duration-300', className)}
      style={getCardStyles()}
      onHoverStart={() => hover && setIsHovered(true)}
      onHoverEnd={() => hover && setIsHovered(false)}
      whileHover={hover ? { y: -5, scale: 1.02 } : {}}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
    >
      {children}
    </motion.div>
  );
};

// Advanced Button Component
interface AdvancedButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'secondary' | 'glow' | 'neon' | 'holographic';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  className?: string;
  loading?: boolean;
}

export const AdvancedButton: React.FC<AdvancedButtonProps> = ({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  className,
  loading = false
}) => {
  const { theme } = useAdvancedTheme();
  const [isPressed, setIsPressed] = useState(false);

  const sizeClasses = {
    sm: 'px-4 py-2 text-sm',
    md: 'px-6 py-3 text-base',
    lg: 'px-8 py-4 text-lg'
  };

  const getButtonStyles = () => {
    const baseStyles = {
      overflow: 'hidden',
      transition: 'all 0.3s ease',
      cursor: disabled ? 'not-allowed' : 'pointer'
    };

    switch (variant) {
      case 'glow':
        return {
          ...baseStyles,
          background: `linear-gradient(45deg, ${theme.colors.primary}, ${theme.colors.secondary})`,
          boxShadow: isPressed 
            ? `0 0 20px ${theme.colors.glow}`
            : `0 0 40px ${theme.colors.glow}`,
          border: `1px solid ${theme.colors.primary}`,
          color: '#ffffff'
        };
      case 'neon':
        return {
          ...baseStyles,
          background: 'transparent',
          boxShadow: `0 0 20px ${theme.colors.primary}, inset 0 0 20px rgba(255,255,255,0.1)`,
          border: `2px solid ${theme.colors.primary}`,
          color: theme.colors.primary,
          textShadow: `0 0 10px ${theme.colors.primary}`
        };
      case 'holographic':
        return {
          ...baseStyles,
          background: `linear-gradient(45deg, ${theme.colors.primary}40, ${theme.colors.secondary}40, ${theme.colors.accent}40)`,
          boxShadow: `0 0 30px ${theme.colors.glow}`,
          border: `1px solid transparent`,
          borderImage: `linear-gradient(45deg, ${theme.colors.primary}, ${theme.colors.secondary}, ${theme.colors.accent}) 1`,
          color: '#ffffff',
          backdropFilter: 'blur(10px)'
        };
      case 'secondary':
        return {
          ...baseStyles,
          background: 'rgba(255,255,255,0.1)',
          boxShadow: isPressed 
            ? 'inset 0 2px 4px rgba(0,0,0,0.3)'
            : '0 4px 12px rgba(0,0,0,0.2)',
          border: `1px solid ${theme.colors.border}`,
          color: theme.colors.foreground
        };
      default:
        return {
          ...baseStyles,
          background: `linear-gradient(45deg, ${theme.colors.primary}, ${theme.colors.secondary})`,
          boxShadow: isPressed 
            ? 'inset 0 2px 4px rgba(0,0,0,0.3)'
            : '0 4px 12px rgba(0,0,0,0.3)',
          border: 'none',
          color: '#ffffff'
        };
    }
  };

  return (
    <motion.button
      className={cn(
        'rounded-lg font-medium transition-all duration-300',
        sizeClasses[size],
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
      style={getButtonStyles()}
      onClick={onClick}
      disabled={disabled}
      onTapStart={() => setIsPressed(true)}
      onTap={() => setIsPressed(false)}
      onTapCancel={() => setIsPressed(false)}
      whileHover={!disabled ? { scale: 1.05 } : {}}
      whileTap={!disabled ? { scale: 0.95 } : {}}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
    >
      {loading && (
        <motion.div
          className="absolute inset-0 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
        </motion.div>
      )}
      <span className={loading ? 'opacity-0' : 'opacity-100'}>{children}</span>
    </motion.button>
  );
};

// Animated Background Component
export const AnimatedBackground: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { theme } = useAdvancedTheme();
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  return (
    <div className="relative min-h-screen overflow-hidden" style={{ background: theme.colors.background }}>
      {/* Animated gradient orbs */}
      {isClient && (
        <div className="absolute inset-0">
          {[...Array(6)].map((_, i) => (
            <motion.div
              key={i}
              className="absolute rounded-full"
              style={{
                width: `${300 + i * 50}px`,
                height: `${300 + i * 50}px`,
                background: `radial-gradient(circle, ${theme.colors.primary}20, transparent)`,
                filter: 'blur(40px)'
              }}
              initial={{
                x: Math.random() * (typeof window !== 'undefined' ? window.innerWidth : 1000),
                y: Math.random() * (typeof window !== 'undefined' ? window.innerHeight : 1000),
                scale: 0
              }}
              animate={{
                x: [
                  Math.random() * (typeof window !== 'undefined' ? window.innerWidth : 1000), 
                  Math.random() * (typeof window !== 'undefined' ? window.innerWidth : 1000)
                ],
                y: [
                  Math.random() * (typeof window !== 'undefined' ? window.innerHeight : 1000), 
                  -100
                ],
                scale: [0, 1, 0]
              }}
              transition={{
                duration: 20 + i * 5,
                repeat: Infinity,
                ease: 'easeInOut'
              }}
            />
          ))}
        </div>
      )}

      {/* Grid pattern overlay */}
      <div 
        className="absolute inset-0 opacity-20"
        style={{
          backgroundImage: `
            linear-gradient(${theme.colors.border}20 1px, transparent 1px),
            linear-gradient(90deg, ${theme.colors.border}20 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px'
        }}
      />

      {/* Content */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  );
};

// Floating Action Button
interface FloatingActionButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  size?: 'sm' | 'md' | 'lg';
}

export const FloatingActionButton: React.FC<FloatingActionButtonProps> = ({
  children,
  onClick,
  position = 'bottom-right',
  size = 'md'
}) => {
  const { theme } = useAdvancedTheme();

  const positionClasses = {
    'bottom-right': 'bottom-8 right-8',
    'bottom-left': 'bottom-8 left-8',
    'top-right': 'top-8 right-8',
    'top-left': 'top-8 left-8'
  };

  const sizeClasses = {
    sm: 'w-12 h-12',
    md: 'w-16 h-16',
    lg: 'w-20 h-20'
  };

  return (
    <motion.button
      className={cn(
        'fixed rounded-full shadow-2xl z-50 flex items-center justify-center',
        positionClasses[position],
        sizeClasses[size]
      )}
      style={{
        background: `linear-gradient(45deg, ${theme.colors.primary}, ${theme.colors.secondary})`,
        boxShadow: `0 0 30px ${theme.colors.glow}`
      }}
      onClick={onClick}
      whileHover={{ scale: 1.1, rotate: 15 }}
      whileTap={{ scale: 0.9 }}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
    >
      {children}
    </motion.button>
  );
};

// Advanced Input Component
interface AdvancedInputProps {
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
  type?: 'text' | 'password' | 'email';
  className?: string;
  variant?: 'default' | 'neon' | 'holographic';
}

export const AdvancedInput: React.FC<AdvancedInputProps> = ({
  placeholder,
  value,
  onChange,
  type = 'text',
  className,
  variant = 'default'
}) => {
  const { theme } = useAdvancedTheme();
  const [isFocused, setIsFocused] = useState(false);

  const getInputStyles = () => {
    switch (variant) {
      case 'neon':
        return {
          background: 'rgba(0,0,0,0.5)',
          border: `2px solid ${isFocused ? theme.colors.primary : theme.colors.border}`,
          boxShadow: isFocused ? `0 0 20px ${theme.colors.primary}` : 'none',
          color: theme.colors.foreground,
          backdropFilter: 'blur(10px)'
        };
      case 'holographic':
        return {
          background: `linear-gradient(135deg, ${theme.colors.primary}10, ${theme.colors.secondary}10)`,
          border: `1px solid ${theme.colors.primary}40`,
          boxShadow: isFocused ? `0 0 30px ${theme.colors.glow}` : `0 0 10px ${theme.colors.glow}`,
          color: theme.colors.foreground,
          backdropFilter: 'blur(8px)'
        };
      default:
        return {
          background: 'rgba(255,255,255,0.05)',
          border: `1px solid ${isFocused ? theme.colors.primary : theme.colors.border}`,
          boxShadow: isFocused ? `0 0 15px ${theme.colors.glow}20` : 'none',
          color: theme.colors.foreground,
          backdropFilter: 'blur(10px)'
        };
    }
  };

  return (
    <motion.input
      type={type}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      onFocus={() => setIsFocused(true)}
      onBlur={() => setIsFocused(false)}
      className={cn(
        'w-full px-4 py-3 rounded-lg outline-none transition-all duration-300',
        className
      )}
      style={getInputStyles()}
      whileFocus={{ scale: 1.02 }}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
    />
  );
};
