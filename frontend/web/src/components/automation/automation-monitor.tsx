'use client';

import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { Play, Settings, Clock, AlertCircle, Activity, Bot } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useAutomationStore } from '@/features/automation/store';

export function AutomationMonitor() {
  const { tasks, loadTasks, runTask } = useAutomationStore();

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  return (
    <Card className="border-white/10 bg-white/[0.03]">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Bot className="h-4 w-4 text-cyan-400" />
          Automation Tasks
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[300px]">
          <div className="space-y-2">
            {tasks.map((task) => (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.01] p-3"
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10">
                    {task.trigger_type === 'schedule' ? (
                      <Clock className="h-4 w-4 text-cyan-400" />
                    ) : (
                      <Activity className="h-4 w-4 text-cyan-400" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground/80">{task.name}</span>
                      <Badge className={`text-[9px] ${
                        task.enabled
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-red-500/10 text-red-400 border-red-500/20'
                      }`}>
                        {task.enabled ? 'Active' : 'Disabled'}
                      </Badge>
                    </div>
                    {task.description && (
                      <p className="mt-0.5 text-xs text-muted-foreground/50">{task.description}</p>
                    )}
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground/40">
                      <span>{task.trigger_type}</span>
                      {task.last_run_at && (
                        <>
                          <span>·</span>
                          <span>Last: {new Date(task.last_run_at).toLocaleString()}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground/40 hover:text-foreground"
                  onClick={() => runTask(task.id)}
                  title="Run task"
                >
                  <Play className="h-4 w-4" />
                </Button>
              </motion.div>
            ))}
            {tasks.length === 0 && (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <AlertCircle className="mb-2 h-8 w-8 text-muted-foreground/20" />
                <p className="text-sm text-muted-foreground/40">No automation tasks configured</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
