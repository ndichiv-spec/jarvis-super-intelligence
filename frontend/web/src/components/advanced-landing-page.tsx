'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence, useScroll, useTransform } from 'framer-motion';
import { cn } from '@/lib/utils';
import { useAdvancedTheme } from './advanced-theme-system';
import { GlassCard, AdvancedButton, AnimatedBackground } from './advanced-ui-components';
import AdvancedJarvisLogo from './advanced-jarvis-logo';
import { 
  Brain, 
  Zap, 
  Shield, 
  Globe, 
  Cpu, 
  Activity,
  Sparkles,
  ArrowRight,
  Play,
  Code,
  Layers,
  Terminal,
  Star,
  Rocket,
  Infinity,
  LucideIcon
} from 'lucide-react';

interface Feature {
  icon: React.ElementType;
  title: string;
  description: string;
  gradient: string;
}

export const AdvancedLandingPage: React.FC = () => {
  const { theme, currentTheme, setTheme } = useAdvancedTheme();
  const [activeFeature, setActiveFeature] = useState(0);
  const { scrollYProgress } = useScroll();
  
  const heroY = useTransform(scrollYProgress, [0, 1], [0, -100]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);

  const features: Feature[] = [
    {
      icon: Brain,
      title: 'Neural Intelligence',
      description: 'Advanced AI processing with quantum-enhanced neural networks',
      gradient: 'from-blue-500 to-cyan-400'
    },
    {
      icon: Zap,
      title: 'Quantum Speed',
      description: 'Lightning-fast responses powered by quantum computing',
      gradient: 'from-yellow-500 to-orange-400'
    },
    {
      icon: Shield,
      title: 'Autonomous Security',
      description: 'Self-healing security protocols with real-time threat detection',
      gradient: 'from-green-500 to-emerald-400'
    },
    {
      icon: Globe,
      title: 'Global Connectivity',
      description: 'Seamless integration with worldwide networks and systems',
      gradient: 'from-purple-500 to-pink-400'
    },
    {
      icon: Cpu,
      title: 'Advanced Processing',
      description: 'Multi-threaded neural processing with optimized algorithms',
      gradient: 'from-red-500 to-rose-400'
    },
    {
      icon: Activity,
      title: 'Real-time Monitoring',
      description: 'Continuous system optimization and performance tracking',
      gradient: 'from-indigo-500 to-blue-400'
    }
  ];

  const stats = [
    { value: '99.9%', label: 'Uptime', prefix: '' },
    { value: '0.001', label: 'Response Time', prefix: 'ms' },
    { value: '10M+', label: 'Neural Connections', prefix: '' },
    { value: '1000', label: 'AI Models', prefix: '+' }
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveFeature((prev) => (prev + 1) % features.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <AnimatedBackground>
      <div className="min-h-screen">
        {/* Hero Section */}
        <motion.section
          style={{ y: heroY, opacity: heroOpacity }}
          className="relative min-h-screen flex items-center justify-center overflow-hidden"
        >
          {/* Animated particles */}
          <div className="absolute inset-0">
            {[...Array(20)].map((_, i) => (
              <motion.div
                key={i}
                className="absolute w-2 h-2 rounded-full"
                style={{
                  background: theme.colors.primary,
                  boxShadow: `0 0 10px ${theme.colors.glow}`
                }}
                initial={{
                  x: Math.random() * window.innerWidth,
                  y: Math.random() * window.innerHeight,
                  scale: 0
                }}
                animate={{
                  x: [Math.random() * window.innerWidth, Math.random() * window.innerWidth],
                  y: [Math.random() * window.innerHeight, -100],
                  scale: [0, 1, 0]
                }}
                transition={{
                  duration: 10 + Math.random() * 10,
repeat: -1,
                  ease: 'linear'
                }}
              />
            ))}
          </div>

          <div className="relative z-10 text-center px-6 max-w-6xl mx-auto">
            <motion.div
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: 'spring', stiffness: 200, damping: 20 }}
              className="mb-8"
            >
              <AdvancedJarvisLogo variant="quantum" size="2xl" />
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 50 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="text-6xl md:text-8xl font-bold mb-6"
            >
              <span className="bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500 bg-clip-text text-transparent">
                JARVIS
              </span>
              <br />
              <span className="text-4xl md:text-6xl opacity-80">Quantum Intelligence</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="text-xl md:text-2xl mb-12 opacity-80 max-w-3xl mx-auto"
            >
              Experience the next evolution of artificial intelligence with quantum-enhanced processing, 
              autonomous learning, and unparalleled system integration.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 }}
              className="flex flex-col sm:flex-row gap-4 justify-center"
            >
              <AdvancedButton variant="holographic" size="lg" className="px-8 py-4">
                <Rocket className="w-5 h-5 mr-2" />
                Launch Experience
                <ArrowRight className="w-5 h-5 ml-2" />
              </AdvancedButton>
              <AdvancedButton variant="neon" size="lg" className="px-8 py-4">
                <Play className="w-5 h-5 mr-2" />
                Watch Demo
              </AdvancedButton>
            </motion.div>

            {/* Floating stats */}
            <motion.div
              initial={{ opacity: 0, y: 50 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8 }}
              className="grid grid-cols-2 md:grid-cols-4 gap-6 mt-20"
            >
              {stats.map((stat, index) => (
                <motion.div
                  key={stat.label}
                  className="text-center"
                  whileHover={{ scale: 1.1 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                >
                  <div className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent">
                    {stat.prefix}{stat.value}
                  </div>
                  <div className="text-sm opacity-70 mt-1">{stat.label}</div>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </motion.section>

        {/* Features Section */}
        <section className="py-20 px-6">
          <div className="max-w-6xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 50 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-center mb-16"
            >
              <h2 className="text-4xl md:text-5xl font-bold mb-4">
                <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                  Quantum Capabilities
                </span>
              </h2>
              <p className="text-xl opacity-80 max-w-2xl mx-auto">
                Cutting-edge features that redefine what's possible with artificial intelligence
              </p>
            </motion.div>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
              {features.map((feature, index) => (
                <motion.div
                  key={feature.title}
                  initial={{ opacity: 0, y: 50 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: index * 0.1 }}
                >
                  <GlassCard
                    variant={currentTheme.includes('cyberpunk') ? 'cyberpunk' : 'default'}
                    className="h-full p-8 text-center group cursor-pointer"
                    hover={true}
                    glow={true}
                  >
                    <motion.div
                      className={`w-16 h-16 mx-auto mb-6 rounded-full bg-gradient-to-r ${feature.gradient} flex items-center justify-center`}
                      whileHover={{ rotate: 360, scale: 1.1 }}
                      transition={{ duration: 0.5 }}
                    >
                      <feature.icon className="w-8 h-8 text-white" />
                    </motion.div>
                    <h3 className="text-2xl font-bold mb-4 group-hover:text-transparent group-hover:bg-gradient-to-r group-hover:from-blue-400 group-hover:to-purple-600 group-hover:bg-clip-text transition-all duration-300">
                      {feature.title}
                    </h3>
                    <p className="opacity-80 leading-relaxed">
                      {feature.description}
                    </p>
                  </GlassCard>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Interactive Demo Section */}
        <section className="py-20 px-6">
          <div className="max-w-6xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 50 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-center mb-16"
            >
              <h2 className="text-4xl md:text-5xl font-bold mb-4">
                <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
                  Interactive Experience
                </span>
              </h2>
              <p className="text-xl opacity-80 max-w-2xl mx-auto">
                See JARVIS in action with our live demonstration
              </p>
            </motion.div>

            <GlassCard variant="holographic" className="p-12">
              <div className="grid md:grid-cols-2 gap-8 items-center">
                <div>
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={activeFeature}
                      initial={{ opacity: 0, x: -50 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 50 }}
                      transition={{ duration: 0.3 }}
                    >
                      <h3 className="text-3xl font-bold mb-4">
                        {features[activeFeature].title}
                      </h3>
                      <p className="text-lg opacity-80 mb-6">
                        {features[activeFeature].description}
                      </p>
                      <AdvancedButton variant="glow" size="md">
                        <Code className="w-4 h-4 mr-2" />
                        Try It Now
                      </AdvancedButton>
                    </motion.div>
                  </AnimatePresence>

                  {/* Feature indicators */}
                  <div className="flex space-x-2 mt-8">
                    {features.map((_, index) => (
                      <motion.button
                        key={index}
                        className={cn(
                          'w-2 h-2 rounded-full transition-all duration-300',
                          index === activeFeature
                            ? 'bg-gradient-to-r from-blue-500 to-purple-600 w-8'
                            : 'bg-white/30'
                        )}
                        onClick={() => setActiveFeature(index)}
                        whileHover={{ scale: 1.2 }}
                        whileTap={{ scale: 0.8 }}
                      />
                    ))}
                  </div>
                </div>

                <motion.div
                  className="relative"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 20, repeat: -1, ease: 'linear' }}
                >
                  <AdvancedJarvisLogo variant="holographic" size="xl" />
                </motion.div>
              </div>
            </GlassCard>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-20 px-6">
          <div className="max-w-4xl mx-auto text-center">
            <motion.div
              initial={{ opacity: 0, y: 50 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
            >
              <GlassCard variant="cyberpunk" className="p-12">
                <h2 className="text-4xl md:text-5xl font-bold mb-6">
                  <span className="bg-gradient-to-r from-yellow-400 to-orange-500 bg-clip-text text-transparent">
                    Ready to Experience the Future?
                  </span>
                </h2>
                <p className="text-xl opacity-80 mb-8">
                  Join thousands of users who have already upgraded to JARVIS Quantum Intelligence
                </p>
                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                  <AdvancedButton variant="holographic" size="lg" className="px-8 py-4">
                    <Infinity className="w-5 h-5 mr-2" />
                    Start Free Trial
                  </AdvancedButton>
                  <AdvancedButton variant="neon" size="lg" className="px-8 py-4">
                    <Star className="w-5 h-5 mr-2" />
                    View Pricing
                  </AdvancedButton>
                </div>
              </GlassCard>
            </motion.div>
          </div>
        </section>
      </div>
    </AnimatedBackground>
  );
};
