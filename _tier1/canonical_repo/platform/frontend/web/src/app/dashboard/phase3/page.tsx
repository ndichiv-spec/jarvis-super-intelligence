"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Brain, Database, Download, Plug, AlertTriangle, ArrowUpRight } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const unavailable = "This screen is not connected to a live service. No sample counts, jobs, plugin states, or install status are available.";

function UnavailablePanel({ children }: { children: ReactNode }) {
  return (
    <Card className="border-amber-400/20 bg-white/[0.02]">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-amber-100">
          <AlertTriangle className="h-5 w-5 text-amber-400" />
          {children}
        </CardTitle>
        <CardDescription>{unavailable}</CardDescription>
      </CardHeader>
    </Card>
  );
}

export default function Phase3Page() {
  const [activeTab, setActiveTab] = useState("finetune");

  return (
    <div className="space-y-6 p-6">
      <motion.header initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-3xl font-bold">Advanced Systems</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Training, datasets, extensions, and installation capabilities.
        </p>
      </motion.header>

      <div role="status" className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-100">
        Training dataset and run APIs exist but are not integrated here. Use the Extensions Center for connected extension state.
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="finetune"><Brain className="mr-2 h-4 w-4" />Fine-Tuning</TabsTrigger>
          <TabsTrigger value="dataset"><Database className="mr-2 h-4 w-4" />Datasets</TabsTrigger>
          <TabsTrigger value="plugins"><Plug className="mr-2 h-4 w-4" />Extensions</TabsTrigger>
          <TabsTrigger value="pwa"><Download className="mr-2 h-4 w-4" />PWA</TabsTrigger>
        </TabsList>
        <TabsContent value="finetune" className="mt-4">
          <UnavailablePanel>Training runs unavailable</UnavailablePanel>
        </TabsContent>
        <TabsContent value="dataset" className="mt-4">
          <UnavailablePanel>Dataset inventory unavailable</UnavailablePanel>
        </TabsContent>
        <TabsContent value="plugins" className="mt-4">
          <Card className="bg-white/[0.02]">
            <CardHeader>
              <CardTitle>Extension lifecycle</CardTitle>
              <CardDescription>Connection and runtime state is maintained by the Extensions Center.</CardDescription>
            </CardHeader>
            <CardContent>
              <Link
                href="/dashboard/extensions"
                className="inline-flex items-center gap-2 text-sm text-primary underline-offset-4 hover:underline"
              >
                Open Extensions Center <ArrowUpRight className="h-4 w-4" />
              </Link>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="pwa" className="mt-4">
          <UnavailablePanel>PWA installation status unavailable</UnavailablePanel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
