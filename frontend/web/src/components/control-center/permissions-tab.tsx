"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Users,
  Shield,
  RefreshCw,
  AlertCircle,
  Check,
  X,
  Clock,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";

interface RbacUser {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  roles: string[];
  status: string;
  is_active: boolean;
  created_at: string;
}

interface PermissionEntry {
  resource: string;
  action: string;
  description: string;
}

export function PermissionsTab() {
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [permissions, setPermissions] = useState<PermissionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [usersData, permsData] = await Promise.all([
        // /users and /permissions return wrapped/paginated objects, not bare
        // arrays: { users, total, page, per_page } and { permissions: [...] }.
        // The UI lists every user, so request a wide page (default is only 20)
        // and normalize the wrapped payloads into arrays before use.
        apiClient.get<{ users: RbacUser[]; total?: number }>("/api/v1/rbac/users?per_page=200"),
        apiClient.get<{ permissions: PermissionEntry[] }>("/api/v1/rbac/permissions"),
      ]);
      setUsers(Array.isArray(usersData?.users) ? usersData.users : []);
      setPermissions(Array.isArray(permsData?.permissions) ? permsData.permissions : []);
    } catch (err: any) {
      setError(err.message || "Failed to load permissions data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  if (loading) {
    return <PermissionsSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadData()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Permissions</h2>
        <Button variant="outline" size="sm" onClick={() => void loadData()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {/* Users */}
      <section>
        <h3 className="text-md font-medium mb-3 flex items-center gap-2">
          <Users className="h-4 w-4 text-primary" />
          Users
        </h3>
        <Card>
          <CardHeader>
            <CardTitle>Users & Roles</CardTitle>
            <CardDescription>
              {users.length} users with {users.filter(u => u.roles.includes("admin")).length} admin(s)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {users.map((u) => (
                <UserRow key={u.id} user={u} />
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Permissions reference */}
      <section>
        <h3 className="text-md font-medium mb-3 flex items-center gap-2">
          <Shield className="h-4 w-4 text-primary" />
          Permission Catalog
        </h3>
        <Card>
          <CardHeader>
            <CardTitle>Available Permissions</CardTitle>
            <CardDescription>
              {permissions.length} fine-grained permissions defined
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {permissions.map((p, i) => (
                <div key={`${p.resource}:${p.action}:${i}`} className="flex items-center justify-between py-2 border-b border-border/30 last:border-0">
                  <div>
                    <code className="text-sm">{p.resource}:{p.action}</code>
                    <p className="text-xs text-muted-foreground">{p.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function UserRow({ user }: { user: RbacUser }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <div className="flex items-center justify-between py-2 border-b border-border/30 last:border-0">
        <div className="space-y-1">
          <div className="font-medium text-sm">{user.full_name || user.username}</div>
          <div className="text-xs text-muted-foreground">{user.email}</div>
          <div className="flex gap-1">
            {user.roles.map((r) => (
              <Badge key={r} variant={r === "admin" ? "default" : "secondary"} className="text-xs">
                {r}
              </Badge>
            ))}
          </div>
        </div>
        <Badge variant={user.is_active ? "default" : "outline"}>
          {user.is_active ? "Active" : "Inactive"}
        </Badge>
      </div>
    </motion.div>
  );
}

function PermissionsSkeleton() {
  return (
    <div className="space-y-6">
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i}>
          <CardHeader>
            <div className="h-5 bg-muted/30 rounded animate-pulse w-48" />
            <div className="h-4 bg-muted/30 rounded animate-pulse w-32 mt-1" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, j) => (
                <div key={j} className="h-12 bg-muted/30 rounded animate-pulse" />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
