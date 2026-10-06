import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export function DashboardSkeleton() {
  return (
    <div className="min-h-screen relative overflow-hidden" style={{
      background: `
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 212, 255, 0.08), transparent),
        radial-gradient(ellipse 60% 40% at 80% 60%, rgba(0, 229, 160, 0.05), transparent),
        #030712
      `
    }}>
      {/* Holographic Grid Overlay */}
      <div className="absolute inset-0 opacity-30 holo-grid" />

      <div className="container mx-auto px-6 py-12 max-w-7xl relative z-10">
        {/* Hero Section Skeleton */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mb-8"
        >
          <div className="flex items-center gap-6 mb-6">
            <div className="h-20 w-20 rounded-2xl holo-icon animate-pulse" />
            <div className="flex-1">
              <div className="h-12 w-80 bg-slate-800/50 rounded-lg animate-pulse mb-2" />
              <div className="h-5 w-96 bg-slate-800/30 rounded animate-pulse" />
            </div>
          </div>

          {/* Quick Stats Skeleton */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            {[1, 2, 3, 4].map((i) => (
              <Card key={i} className="glass border-holo">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="h-4 w-24 bg-slate-800/50 rounded animate-pulse mb-3" />
                      <div className="h-8 w-20 bg-slate-800/50 rounded animate-pulse mb-2" />
                      <div className="h-3 w-32 bg-slate-800/30 rounded animate-pulse" />
                    </div>
                    <div className="h-12 w-12 rounded-xl holo-icon animate-pulse" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </motion.div>

        {/* Search & Filter Skeleton */}
        <div className="mb-6 space-y-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1 h-12 holo-input animate-pulse" />
            <div className="h-12 w-full sm:w-96 glass rounded-xl animate-pulse" />
          </div>
        </div>

        {/* Feature Categories Skeleton */}
        <div className="space-y-8">
          {[1, 2, 3].map((catIdx) => (
            <motion.div
              key={catIdx}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: catIdx * 0.1 }}
            >
              <div className="flex items-center gap-4 mb-6">
                <div className="h-12 w-12 rounded-xl holo-icon animate-pulse" />
                <div className="flex-1">
                  <div className="h-7 w-48 bg-slate-800/50 rounded animate-pulse mb-2" />
                  <div className="h-4 w-64 bg-slate-800/30 rounded animate-pulse" />
                </div>
                <div className="h-6 w-24 bg-slate-800/50 rounded animate-pulse" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[1, 2, 3, 4, 5, 6].map((featIdx) => (
                  <Card 
                    key={featIdx} 
                    className="glass border-holo p-5"
                  >
                    <CardContent className="p-0">
                      <div className="flex items-start gap-4">
                        <div className="h-12 w-12 rounded-xl holo-icon animate-pulse flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <div className="h-5 w-32 bg-slate-800/50 rounded animate-pulse" />
                            <div className="h-5 w-12 bg-slate-800/30 rounded animate-pulse" />
                          </div>
                          <div className="h-4 w-full bg-slate-800/30 rounded animate-pulse mb-1" />
                          <div className="h-4 w-3/4 bg-slate-800/30 rounded animate-pulse" />
                        </div>
                        <div className="h-5 w-5 bg-slate-800/30 rounded animate-pulse flex-shrink-0" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </motion.div>
          ))}
        </div>

        {/* Recent Activity Skeleton */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="mt-12"
        >
          <Card className="glass border-holo hud-corners">
            <CardHeader>
              <div className="h-7 w-48 bg-slate-800/50 rounded animate-pulse mb-2" />
              <div className="h-4 w-64 bg-slate-800/30 rounded animate-pulse" />
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="flex items-center gap-4 p-3 rounded-xl glass border-holo">
                    <div className="h-10 w-10 rounded-xl holo-icon animate-pulse" />
                    <div className="flex-1">
                      <div className="h-4 w-48 bg-slate-800/50 rounded animate-pulse mb-2" />
                      <div className="h-3 w-24 bg-slate-800/30 rounded animate-pulse" />
                    </div>
                    <div className="h-6 w-16 bg-slate-800/50 rounded animate-pulse" />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}

export function FeatureCardSkeleton() {
  return (
    <Card className="glass border-holo p-5">
      <CardContent className="p-0">
        <div className="flex items-start gap-4">
          <div className="h-12 w-12 rounded-xl holo-icon animate-pulse flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <div className="h-5 w-32 bg-slate-800/50 rounded animate-pulse" />
            </div>
            <div className="space-y-2">
              <div className="h-4 w-full bg-slate-800/30 rounded animate-pulse" />
              <div className="h-4 w-3/4 bg-slate-800/30 rounded animate-pulse" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
