"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { CreditCard, TrendingUp, AlertTriangle, CheckCircle, Download, Zap, Users, Search, Mic, Image, Video, Database } from "lucide-react";

interface UsageData {
  api_calls: { used: number; limit: number; percent: number };
  transformer_calls: { used: number; limit: number; percent: number };
  web_searches: { used: number; limit: number; percent: number };
  storage_mb: { used: number; limit: number; percent: number };
  voice_minutes: { used: number; limit: number; percent: number };
  image_generations: { used: number; limit: number; percent: number };
}

interface PlanInfo {
  name: string;
  price: number;
  features: string[];
}

const PLANS: PlanInfo[] = [
  {
    name: "Free",
    price: 0,
    features: ["1,000 API calls/mo", "100 AI generations/mo", "Web search", "Basic support"],
  },
  {
    name: "Starter",
    price: 19,
    features: ["10,000 API calls/mo", "1,000 AI generations/mo", "Voice API", "Priority support"],
  },
  {
    name: "Professional",
    price: 49,
    features: ["100,000 API calls/mo", "10,000 AI generations/mo", "Custom agents", "24/7 support"],
  },
  {
    name: "Enterprise",
    price: 199,
    features: ["Unlimited API calls", "Unlimited generations", "SSO", "Dedicated support", "Custom SLA"],
  },
];

export default function BillingPage() {
  const [currentPlan, setCurrentPlan] = useState("Free");
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUsage();
  }, []);

  const fetchUsage = async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/api/v1/billing/usage`
      );
      const data = await response.json();
      setUsage(data.usage);
      setCurrentPlan(data.plan || "Free");
    } catch (error) {
      console.error("Failed to fetch usage:", error);
    } finally {
      setLoading(false);
    }
  };

  const changePlan = async (plan: string) => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/api/v1/billing/plan`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan }),
        }
      );
      const data = await response.json();
      if (data.success) {
        setCurrentPlan(plan);
        toast.success(`Plan changed to ${plan}`);
      }
    } catch (error) {
      toast.error("Failed to change plan");
    }
  };

  const getUsageIcon = (type: string) => {
    switch (type) {
      case "api_calls": return <Zap className="w-5 h-5" />;
      case "transformer_calls": return <TrendingUp className="w-5 h-5" />;
      case "web_searches": return <Search className="w-5 h-5" />;
      case "storage_mb": return <Database className="w-5 h-5" />;
      case "voice_minutes": return <Mic className="w-5 h-5" />;
      case "image_generations": return <Image className="w-5 h-5" />;
      default: return <Zap className="w-5 h-5" />;
    }
  };

  const getUsageLabel = (type: string) => {
    const labels: Record<string, string> = {
      api_calls: "API Calls",
      transformer_calls: "AI Generations",
      web_searches: "Web Searches",
      storage_mb: "Storage",
      voice_minutes: "Voice Minutes",
      image_generations: "Image Generations",
    };
    return labels[type] || type;
  };

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-3 rounded-xl bg-gradient-to-br from-green-500 to-emerald-500">
          <CreditCard className="w-8 h-8 text-white" />
        </div>
        <div>
          <h1 className="text-3xl font-bold">Billing & Usage</h1>
          <p className="text-muted-foreground">Manage your subscription and monitor usage</p>
        </div>
      </div>

      <Tabs defaultValue="usage" className="space-y-4">
        <TabsList>
          <TabsTrigger value="usage">Current Usage</TabsTrigger>
          <TabsTrigger value="plans">Subscription Plans</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
        </TabsList>

        <TabsContent value="usage">
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Current Plan: {currentPlan}</CardTitle>
              <CardDescription>Billing period: This month</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {usage && Object.entries(usage).map(([key, data]) => (
                  <Card key={key} className="bg-muted/50">
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {getUsageIcon(key)}
                          <span className="font-medium">{getUsageLabel(key)}</span>
                        </div>
                        {data.percent > 90 && (
                          <AlertTriangle className="w-4 h-4 text-yellow-500" />
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      <Progress value={Math.min(data.percent, 100)} className="mb-2" />
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">
                          {data.used.toLocaleString()} used
                        </span>
                        <span className="text-muted-foreground">
                          {data.limit === -1 ? "Unlimited" : `${data.limit.toLocaleString()} limit`}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="plans">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {PLANS.map((plan) => (
              <Card key={plan.name} className={currentPlan === plan.name ? "border-green-500 border-2" : ""}>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    {plan.name}
                    {currentPlan === plan.name && (
                      <Badge variant="default">Current</Badge>
                    )}
                  </CardTitle>
                  <CardDescription>
                    <span className="text-3xl font-bold">${plan.price}</span>
                    {plan.price > 0 && <span>/month</span>}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 mb-4">
                    {plan.features.map((feature, idx) => (
                      <li key={idx} className="flex items-center gap-2 text-sm">
                        <CheckCircle className="w-4 h-4 text-green-500" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <Button
                    className="w-full"
                    variant={currentPlan === plan.name ? "outline" : "default"}
                    onClick={() => changePlan(plan.name)}
                    disabled={currentPlan === plan.name}
                  >
                    {currentPlan === plan.name ? "Current Plan" : "Upgrade"}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="invoices">
          <Card>
            <CardHeader>
              <CardTitle>Invoice History</CardTitle>
              <CardDescription>View and download past invoices</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                <CreditCard className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No invoices yet</p>
                <p className="text-sm">Invoices will appear here after your first billing cycle</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}