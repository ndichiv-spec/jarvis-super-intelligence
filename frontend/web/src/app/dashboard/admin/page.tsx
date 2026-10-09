'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { format, parseISO, isValid } from 'date-fns';
import { toast } from 'sonner';
import {
  Users, Shield, FileText, Settings, Search, Plus, Edit, Trash2,
  Lock, ChevronDown, ChevronLeft, ChevronRight,
  Download, RefreshCw, Check, AlertTriangle, Eye, EyeOff,
  Filter, UserPlus, Key, Globe, Cpu, Database,
  Wrench, Monitor, BarChart3
} from 'lucide-react';
import { jarvisAPI, User as UserType, Role, AuditLogEntry, Permission, TenantSettings } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Label } from '@/components/ui/label';

// --- Utility types ---
const getErrorMessage = (error: unknown, fallback = 'Unknown error'): string => {
  if (error instanceof Error) {
    const status = getErrorStatus(error);
    if (status === 401) return `Session expired: ${error.message}`;
    if (status === 403) return `Permission denied: ${error.message}`;
    if (status && status >= 500) return `Server error (${status}): ${error.message}`;
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) return error;
  return fallback;
};

const getErrorStatus = (error: unknown): number | undefined =>
  error && typeof error === 'object' && 'status' in error
    ? Number((error as { status?: unknown }).status)
    : undefined;

function RequestFailure({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = getErrorStatus(error);
  const heading = status === 401
    ? 'Session expired'
    : status === 403
      ? 'Permission denied'
      : status && status >= 500
        ? `Server error (${status})`
        : 'Unable to load this data';
  const description = status === 401
    ? 'Sign in again to access this resource.'
    : status === 403
      ? 'Your account does not have the required permission. Ask the tenant owner for access.'
      : getErrorMessage(error, 'The service is unavailable. Retry to check again.');

  return (
    <Card role="alert" className="border-destructive/40">
      <CardContent className="flex flex-col items-start gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-medium">{heading}</p>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <Button variant="outline" onClick={onRetry} className="shrink-0">
          <RefreshCw className="mr-2 h-4 w-4" /> Retry
        </Button>
      </CardContent>
    </Card>
  );
}

type PermissionResource = 'chat' | 'agents' | 'system' | 'knowledge' | 'monitoring' | 'tools' | 'users' | 'tenants' | 'roles';

const PERMISSION_GROUPS: Record<PermissionResource, { icon: React.ReactNode; label: string }> = {
  chat: { icon: <Monitor className="h-4 w-4" />, label: 'Chat' },
  agents: { icon: <Cpu className="h-4 w-4" />, label: 'Agents' },
  system: { icon: <Settings className="h-4 w-4" />, label: 'System' },
  knowledge: { icon: <Database className="h-4 w-4" />, label: 'Knowledge' },
  monitoring: { icon: <BarChart3 className="h-4 w-4" />, label: 'Monitoring' },
  tools: { icon: <Wrench className="h-4 w-4" />, label: 'Tools' },
  users: { icon: <Users className="h-4 w-4" />, label: 'Users' },
  tenants: { icon: <Globe className="h-4 w-4" />, label: 'Tenants' },
  roles: { icon: <Key className="h-4 w-4" />, label: 'Roles' },
};

const ACTION_COLORS: Record<string, string> = {
  create: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  update: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  delete: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  login: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  pending_authorization: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  suspended: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  disabled: 'bg-slate-100 text-slate-800 dark:bg-slate-900/30 dark:text-slate-300',
};

// --- Users Tab ---
function UsersTab({ canManage }: { canManage: boolean }) {
  const [users, setUsers] = useState<UserType[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [total, setTotal] = useState(0);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserType | null>(null);
  const [expandedUser, setExpandedUser] = useState<string | null>(null);
  const [allRoles, setAllRoles] = useState<string[]>([]);
  const [showPassword, setShowPassword] = useState(false);

  const [addForm, setAddForm] = useState({ email: '', username: '', password: '', full_name: '' });
  const [editForm, setEditForm] = useState({ roles: [] as string[], status: 'active' as UserType['status'] });

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jarvisAPI.rbac.getUsers(page, perPage, search || undefined);
      setUsers(data.users);
      setTotal(data.total);
      setLoadError(null);
    } catch (err: unknown) {
      setLoadError(err);
      setUsers([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, perPage, search]);

  const fetchRoles = useCallback(async () => {
    try {
      const data = await jarvisAPI.rbac.getRoles();
      setAllRoles(data.roles.map(r => r.name));
    } catch {
      // Non-critical
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchUsers(); }, [fetchUsers]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchRoles(); }, [fetchRoles]);

  const totalPages = Math.ceil(total / perPage);
  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addForm.email.trim());

  const handleAddUser = async () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addForm.email.trim())) {
      toast.error('Enter a valid email address');
      return;
    }
    if (addForm.username.trim().length < 2 || addForm.username.length > 64) {
      toast.error('Username must be between 2 and 64 characters');
      return;
    }
    if (addForm.password.length < 12 || addForm.password.length > 256) {
      toast.error('Password must be between 12 and 256 characters');
      return;
    }
    if (addForm.full_name.length > 120) {
      toast.error('Full name must be 120 characters or fewer');
      return;
    }
    try {
      await jarvisAPI.rbac.createUser({
        email: addForm.email.trim(),
        username: addForm.username.trim(),
        password: addForm.password,
        ...(addForm.full_name.trim() ? { full_name: addForm.full_name.trim() } : {}),
      });
      toast.success('Invitation created. The account is pending email verification and owner authorization.');
      setShowAddDialog(false);
      setAddForm({ email: '', username: '', password: '', full_name: '' });
      await fetchUsers();
    } catch (err: unknown) {
      toast.error('Failed to create user: ' + getErrorMessage(err));
    }
  };

  const handleEditUser = async () => {
    if (!selectedUser) return;
    try {
      await jarvisAPI.rbac.updateUser(selectedUser.id, { roles: editForm.roles, status: editForm.status });
      toast.success('User updated successfully');
      setShowEditDialog(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (err: unknown) {
      toast.error('Failed to update user: ' + getErrorMessage(err));
    }
  };

  const handleDeleteUser = async () => {
    if (!selectedUser) return;
    try {
      await jarvisAPI.rbac.deleteUser(selectedUser.id);
      toast.success('User deleted successfully');
      setShowDeleteDialog(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (err: unknown) {
      toast.error('Failed to delete user: ' + getErrorMessage(err));
    }
  };

  const openEdit = (user: UserType) => {
    setSelectedUser(user);
    setEditForm({ roles: user.roles, status: user.status });
    setShowEditDialog(true);
  };

  const openDelete = (user: UserType) => {
    setSelectedUser(user);
    setShowDeleteDialog(true);
  };

  return (
    <div className="space-y-4">
      {!canManage && (
        <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          Read-only view. Creating, editing, and deleting users is restricted to the configured tenant owner.
        </p>
      )}
      <div className="flex items-center justify-between">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search users..."
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchUsers()}
          />
        </div>
        {canManage && <Button onClick={() => setShowAddDialog(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Add User
        </Button>}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading users...</span>
        </div>
      ) : loadError ? (
        <RequestFailure error={loadError} onRetry={() => void fetchUsers()} />
      ) : users.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <Users className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">No users found</h3>
            <p className="text-sm text-muted-foreground mt-1">
              {search ? 'Try adjusting your search' : 'Add your first user to get started'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
        <div className="hidden md:block">
        <Card className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Roles</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Verified</TableHead>
                <TableHead>Last Login</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <AnimatePresence>
                {users.map((user) => (
                  <React.Fragment key={user.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setExpandedUser(expandedUser === user.id ? null : user.id)}
                    >
                      <TableCell>
                        <ChevronDown className={`h-4 w-4 transition-transform ${expandedUser === user.id ? 'rotate-180' : ''}`} />
                      </TableCell>
                      <TableCell className="font-medium">{user.full_name || user.username}</TableCell>
                      <TableCell>{user.email}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {user.roles.map((role) => (
                            <Badge key={role} variant="secondary" className="text-xs">{role}</Badge>
                          ))}
                          {user.roles.length === 0 && <span className="text-muted-foreground text-xs">None</span>}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge className={STATUS_COLORS[user.status] || ''}>{user.status}</Badge>
                      </TableCell>
                      <TableCell>{user.email_verified ? 'Verified' : 'Unverified'}</TableCell>
                      <TableCell>
                        {user.last_login_at && isValid(parseISO(user.last_login_at)) ? format(parseISO(user.last_login_at), 'MMM d, yyyy HH:mm') : 'Never'}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        {canManage && (
                        <div className="flex gap-1">
                          <TooltipProvider>
                            <Tooltip><TooltipTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(user)}>
                                <Edit className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger><TooltipContent>Edit user</TooltipContent></Tooltip>
                          </TooltipProvider>
                          <TooltipProvider>
                            <Tooltip><TooltipTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => openDelete(user)}>
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger><TooltipContent>Delete user</TooltipContent></Tooltip>
                          </TooltipProvider>
                        </div>
                        )}
                      </TableCell>
                    </TableRow>
                    {expandedUser === user.id && (
                      <TableRow>
                        <TableCell colSpan={8} className="bg-muted/30">
                          <div className="p-4 space-y-2 text-sm">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                              <div><span className="text-muted-foreground">Username:</span> <span className="font-medium">{user.username}</span></div>
                              <div><span className="text-muted-foreground">Email:</span> <span className="font-medium">{user.email}</span></div>
                              <div><span className="text-muted-foreground">Full Name:</span> <span className="font-medium">{user.full_name || 'N/A'}</span></div>
                              <div><span className="text-muted-foreground">Status:</span> <Badge className={STATUS_COLORS[user.status]}>{user.status}</Badge></div>
                              <div><span className="text-muted-foreground">User ID:</span> <code className="text-xs">{user.id}</code></div>
                              <div><span className="text-muted-foreground">Created:</span> {user.created_at && isValid(parseISO(user.created_at)) ? format(parseISO(user.created_at), 'PPP') : 'N/A'}</div>
                              <div><span className="text-muted-foreground">Last Login:</span> {user.last_login_at && isValid(parseISO(user.last_login_at)) ? format(parseISO(user.last_login_at), 'PPP HH:mm') : 'Never'}</div>
                              <div><span className="text-muted-foreground">Roles:</span> {user.roles.length > 0 ? user.roles.join(', ') : 'None'}</div>
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))}
              </AnimatePresence>
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-4 border-t">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>Showing {(page - 1) * perPage + 1}-{Math.min(page * perPage, total)} of {total}</span>
              <Select value={perPage.toString()} onValueChange={(v) => { setPerPage(Number(v)); setPage(1); }}>
                <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">10 / page</SelectItem>
                  <SelectItem value="25">25 / page</SelectItem>
                  <SelectItem value="50">50 / page</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm">Page {page} of {totalPages || 1}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Card>
        </div>
        <div className="grid gap-3 md:hidden">
          {users.map((user) => (
            <Card key={user.id}>
              <CardContent className="space-y-3 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{user.full_name || user.username}</p>
                    <p className="break-all text-sm text-muted-foreground">{user.email}</p>
                  </div>
                  <Badge className={STATUS_COLORS[user.status] || ''}>{user.status.replaceAll('_', ' ')}</Badge>
                </div>
                <div className="flex flex-wrap gap-1">
                  {user.roles.map((role) => <Badge key={role} variant="secondary">{role}</Badge>)}
                  <Badge variant="outline">{user.email_verified ? 'Verified' : 'Unverified'}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Last login: {user.last_login_at && isValid(parseISO(user.last_login_at)) ? format(parseISO(user.last_login_at), 'MMM d, yyyy HH:mm') : 'Never'}
                </p>
                {canManage && <div className="flex gap-2 border-t pt-3">
                  <Button variant="outline" size="sm" onClick={() => openEdit(user)}><Edit className="mr-1 h-3.5 w-3.5" /> Edit</Button>
                  <Button variant="outline" size="sm" className="text-destructive" onClick={() => openDelete(user)}><Trash2 className="mr-1 h-3.5 w-3.5" /> Delete</Button>
                </div>}
              </CardContent>
            </Card>
          ))}
          {users.length > 0 && <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Page {page} of {totalPages || 1}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}><ChevronLeft className="h-4 w-4" /></Button>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}><ChevronRight className="h-4 w-4" /></Button>
            </div>
          </div>}
        </div>
        </>
      )}

      {/* Add User Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add New User</DialogTitle>
            <DialogDescription>New accounts receive the default user role and remain pending until email verification and owner authorization.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="add-email">Email *</Label>
                <Input id="add-email" type="email" value={addForm.email} onChange={(e) => setAddForm(f => ({ ...f, email: e.target.value }))} placeholder="user@example.com" />
                {addForm.email && !emailValid && <p className="text-xs text-destructive">Enter a valid email address.</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-username">Username *</Label>
                <Input id="add-username" value={addForm.username} onChange={(e) => setAddForm(f => ({ ...f, username: e.target.value }))} placeholder="johndoe" minLength={2} maxLength={64} />
                {addForm.username && addForm.username.trim().length < 2 && <p className="text-xs text-destructive">Username must contain at least 2 characters.</p>}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="add-password">Password *</Label>
              <div className="relative">
                <Input id="add-password" type={showPassword ? 'text' : 'password'} value={addForm.password} onChange={(e) => setAddForm(f => ({ ...f, password: e.target.value }))} placeholder="At least 12 characters" minLength={12} maxLength={256} />
                <Button variant="ghost" size="icon" className="absolute right-0 top-0 h-10 w-10" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              {addForm.password && addForm.password.length < 12 && <p className="text-xs text-destructive">Use at least 12 characters.</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="add-fullname">Full Name</Label>
              <Input id="add-fullname" value={addForm.full_name} onChange={(e) => setAddForm(f => ({ ...f, full_name: e.target.value }))} placeholder="John Doe" maxLength={120} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)}>Cancel</Button>
            <Button onClick={handleAddUser}>Create User</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>Modify roles and status for {selectedUser?.full_name || selectedUser?.username}.</DialogDescription>
          </DialogHeader>
          {selectedUser && (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>Roles</Label>
                <div className="flex flex-wrap gap-2">
                  {allRoles.map((role) => (
                    <Badge
                      key={role}
                      variant={editForm.roles.includes(role) ? 'default' : 'outline'}
                      className="cursor-pointer"
                      onClick={() => setEditForm(f => ({
                        ...f,
                        roles: f.roles.includes(role) ? f.roles.filter(r => r !== role) : [...f.roles, role]
                      }))}
                    >
                      {editForm.roles.includes(role) && <Check className="mr-1 h-3 w-3" />}
                      {role}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={editForm.status} onValueChange={(v) => setEditForm(f => ({ ...f, status: v as UserType['status'] }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="pending_authorization">Pending authorization</SelectItem>
                    <SelectItem value="suspended">Suspended</SelectItem>
                    <SelectItem value="disabled">Disabled</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>Cancel</Button>
            <Button onClick={handleEditUser}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Delete User
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{selectedUser?.full_name || selectedUser?.username}</strong>? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteUser}>Delete User</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// --- Roles Tab ---
function RolesTab({ canManage }: { canManage: boolean }) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditorDialog, setShowEditorDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [permissionError, setPermissionError] = useState<unknown>(null);
  const [createForm, setCreateForm] = useState({ name: '', description: '', permissions: [] as string[] });
  const [editForm, setEditForm] = useState({ name: '', description: '', permissions: [] as string[] });

  const fetchRoles = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jarvisAPI.rbac.getRoles();
      setRoles(data.roles);
      setLoadError(null);
    } catch (err: unknown) {
      setLoadError(err);
      setRoles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchPermissions = useCallback(async () => {
    try {
      const data = await jarvisAPI.rbac.getPermissions();
      setPermissions(data.permissions);
      setPermissionError(null);
    } catch (error: unknown) {
      setPermissionError(error);
      setPermissions([]);
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchRoles(); fetchPermissions(); }, [fetchRoles, fetchPermissions]);

  const handleCreateRole = async () => {
    if (!createForm.name) {
      toast.error('Role name is required');
      return;
    }
    try {
      await jarvisAPI.rbac.createRole(createForm);
      toast.success('Role created successfully');
      setShowCreateDialog(false);
      setCreateForm({ name: '', description: '', permissions: [] });
      fetchRoles();
    } catch (err: unknown) {
      toast.error('Failed to create role: ' + getErrorMessage(err));
    }
  };

  const handleUpdateRole = async () => {
    if (!selectedRole) return;
    try {
      await jarvisAPI.rbac.updateRole(selectedRole.id, { name: editForm.name, description: editForm.description, permissions: editForm.permissions });
      toast.success('Role updated successfully');
      setShowEditorDialog(false);
      setSelectedRole(null);
      fetchRoles();
    } catch (err: unknown) {
      toast.error('Failed to update role: ' + getErrorMessage(err));
    }
  };

  const handleDeleteRole = async () => {
    if (!selectedRole) return;
    if (selectedRole.is_system) {
      toast.error('Cannot delete system roles');
      setShowDeleteDialog(false);
      return;
    }
    try {
      await jarvisAPI.rbac.deleteRole(selectedRole.id);
      toast.success('Role deleted successfully');
      setShowDeleteDialog(false);
      setSelectedRole(null);
      fetchRoles();
    } catch (err: unknown) {
      toast.error('Failed to delete role: ' + getErrorMessage(err));
    }
  };

  const openEditor = (role: Role) => {
    setSelectedRole(role);
    setEditForm({ name: role.name, description: role.description || '', permissions: [...role.permissions] });
    setShowEditorDialog(true);
  };

  const togglePermission = (permId: string) => {
    setEditForm(f => ({
      ...f,
      permissions: f.permissions.includes(permId) ? f.permissions.filter(p => p !== permId) : [...f.permissions, permId]
    }));
  };

  const groupedPermissions = useMemo(() => {
    const groups: Record<string, Permission[]> = {};
    permissions.forEach(p => {
      if (!groups[p.resource]) groups[p.resource] = [];
      groups[p.resource].push(p);
    });
    return groups;
  }, [permissions]);

  return (
    <div className="space-y-4">
      {!canManage && <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">Read-only view. Role mutations are restricted to the configured tenant owner.</p>}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Role Management</h2>
        {canManage && <Button onClick={() => setShowCreateDialog(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Role
        </Button>}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading roles...</span>
        </div>
      ) : loadError ? (
        <RequestFailure error={loadError} onRetry={() => void fetchRoles()} />
      ) : roles.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <Shield className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">No roles found</h3>
            <p className="text-sm text-muted-foreground mt-1">Create your first role to get started</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence>
            {roles.map((role) => (
              <motion.div
                key={role.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
              >
                <Card className={canManage ? 'cursor-pointer hover:shadow-md transition-shadow' : ''} onClick={() => canManage && openEditor(role)}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <Shield className="h-5 w-5 text-primary" />
                        <CardTitle className="text-base">{role.name}</CardTitle>
                        {role.is_system && (
                          <TooltipProvider>
                            <Tooltip><TooltipTrigger asChild>
                              <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                            </TooltipTrigger><TooltipContent>System role - cannot delete</TooltipContent></Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                    </div>
                    <CardDescription className="line-clamp-2">{role.description || 'No description'}</CardDescription>
                  </CardHeader>
                  <CardContent className="pb-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{role.permissions.length} permissions</span>
                      <span className="text-muted-foreground">{role.user_count || 0} users</span>
                    </div>
                  </CardContent>
                  <CardFooter className="pt-0 gap-2">
                    {canManage && <Button variant="outline" size="sm" className="flex-1" onClick={(e) => { e.stopPropagation(); openEditor(role); }}>
                      <Edit className="mr-1 h-3 w-3" /> Edit
                    </Button>}
                    {canManage && !role.is_system && (
                      <Button variant="outline" size="sm" className="text-destructive hover:text-destructive" onClick={(e) => {
                        e.stopPropagation();
                        setSelectedRole(role);
                        setShowDeleteDialog(true);
                      }}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </CardFooter>
                </Card>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Create Role Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create New Role</DialogTitle>
            <DialogDescription>Define a new role with specific permissions.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="role-name">Role Name *</Label>
              <Input id="role-name" value={createForm.name} onChange={(e) => setCreateForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g., Content Manager" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role-desc">Description</Label>
              <Textarea id="role-desc" value={createForm.description} onChange={(e) => setCreateForm(f => ({ ...f, description: e.target.value }))} placeholder="Describe the role's purpose..." rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>Cancel</Button>
            <Button onClick={handleCreateRole}>Create Role</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Role Editor Dialog */}
      <Dialog open={showEditorDialog} onOpenChange={setShowEditorDialog}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Edit Role: {selectedRole?.name}</DialogTitle>
            <DialogDescription>Modify role details and permissions.</DialogDescription>
          </DialogHeader>
          {selectedRole && (
            <div className="space-y-4 overflow-y-auto flex-1 pr-2">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-role-name">Role Name</Label>
                  <Input id="edit-role-name" value={editForm.name} onChange={(e) => setEditForm(f => ({ ...f, name: e.target.value }))} />
                </div>
                <div className="space-y-2">
                  <Label>Permission Count</Label>
                  <div className="h-10 flex items-center px-3 rounded-md border bg-muted text-sm font-medium">
                    {editForm.permissions.length} permissions
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-role-desc">Description</Label>
                <Textarea id="edit-role-desc" value={editForm.description} onChange={(e) => setEditForm(f => ({ ...f, description: e.target.value }))} rows={2} />
              </div>
              <div className="space-y-3">
                <Label>Permissions</Label>
                {permissionError !== null && <RequestFailure error={permissionError} onRetry={() => void fetchPermissions()} />}
                {permissionError === null && permissions.length === 0 && <p className="text-sm text-muted-foreground">No permissions were returned by the permission catalog.</p>}
                {Object.entries(PERMISSION_GROUPS).map(([resource, config]) => {
                  const resourcePerms = groupedPermissions[resource] || [];
                  if (resourcePerms.length === 0) return null;
                  return (
                    <Card key={resource} className="overflow-hidden">
                      <CardHeader className="py-3 px-4 bg-muted/30">
                        <div className="flex items-center gap-2">
                          {config.icon}
                          <CardTitle className="text-sm">{config.label}</CardTitle>
                          <Badge variant="secondary" className="text-xs ml-auto">
                            {resourcePerms.filter(p => editForm.permissions.includes(p.id)).length}/{resourcePerms.length}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="py-2 px-4">
                        <div className="grid grid-cols-2 gap-2">
                          {resourcePerms.map((perm) => (
                            <label key={perm.id} className="flex items-center gap-2 cursor-pointer text-sm hover:bg-muted/50 rounded px-2 py-1">
                              <Switch
                                checked={editForm.permissions.includes(perm.id)}
                                onCheckedChange={() => togglePermission(perm.id)}
                                className="scale-75"
                              />
                              <span className="capitalize">{perm.action}</span>
                            </label>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </div>
          )}
          <DialogFooter className="border-t pt-4 mt-2">
            <Button variant="outline" onClick={() => setShowEditorDialog(false)}>Cancel</Button>
            <Button onClick={handleUpdateRole}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Role Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Delete Role
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the role <strong>{selectedRole?.name}</strong>? Users assigned to this role will lose these permissions.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteRole}>Delete Role</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// --- Audit Log Tab ---
function AuditLogTab() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [page, setPage] = useState(1);
  const [perPage] = useState(25);
  const [total, setTotal] = useState(0);
  const [userId, setUserId] = useState('');
  const [action, setAction] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jarvisAPI.rbac.getAuditLogs({ user_id: userId.trim() || undefined, action: action.trim() || undefined, resource_type: resourceType.trim() || undefined, page, per_page: perPage });
      setLogs(data.logs);
      setTotal(data.total);
      setLoadError(null);
    } catch (err: unknown) {
      setLoadError(err);
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [userId, action, resourceType, page, perPage]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchLogs]);

  const totalPages = Math.ceil(total / perPage);

  const handleExport = async () => {
    try {
      const blob = await jarvisAPI.rbac.exportAuditLogs();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-all-${format(new Date(), 'yyyy-MM-dd')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('All audit logs exported. The server export does not apply page filters.');
    } catch (err: unknown) {
      toast.error('Failed to export: ' + getErrorMessage(err));
    }
  };

  const getActionBadgeClass = (action: string): string => {
    const lower = action.toLowerCase();
    for (const [key, cls] of Object.entries(ACTION_COLORS)) {
      if (lower.includes(key)) return cls;
    }
    return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Audit Log</h2>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 text-sm">
            <Switch checked={autoRefresh} onCheckedChange={setAutoRefresh} id="auto-refresh" />
            <Label htmlFor="auto-refresh" className="flex items-center gap-1 cursor-pointer">
              <RefreshCw className={`h-3 w-3 ${autoRefresh ? 'animate-spin' : ''}`} />
              Auto-refresh
            </Label>
          </div>
          <Button variant="outline" size="sm" onClick={handleExport} title="Exports all server audit records, not the current filtered page">
            <Download className="mr-1 h-4 w-4" />
            Export all CSV
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="py-4">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">Filters</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="mb-3 text-xs text-muted-foreground">Filters apply to this paginated list. “Export all CSV” downloads all audit records because the server export endpoint does not accept filters.</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1">
              <Label className="text-xs">Actor ID</Label>
              <Input value={userId} onChange={(e) => { setPage(1); setUserId(e.target.value); }} placeholder="Exact actor ID" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Action</Label>
              <Input value={action} onChange={(e) => { setPage(1); setAction(e.target.value); }} placeholder="Exact action value" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Resource type</Label>
              <Input value={resourceType} onChange={(e) => { setPage(1); setResourceType(e.target.value); }} placeholder="Exact resource type" />
            </div>
            <div className="flex items-end">
              <Button variant="outline" size="sm" className="w-full" onClick={() => void fetchLogs()}>Apply filters</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading logs...</span>
        </div>
      ) : loadError ? (
        <RequestFailure error={loadError} onRetry={() => void fetchLogs()} />
      ) : logs.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">No audit logs found</h3>
            <p className="text-sm text-muted-foreground mt-1">Try adjusting your filters or date range</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead>Timestamp</TableHead>
                <TableHead>Actor ID</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Resource ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <AnimatePresence>
                {logs.map((log) => (
                  <React.Fragment key={log.id}>
                    <TableRow>
                      <TableCell>
                        <Button variant="ghost" size="icon" aria-label={`${expandedLog === log.id ? 'Collapse' : 'Expand'} audit record`} onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}>
                          <ChevronDown className={`h-4 w-4 transition-transform ${expandedLog === log.id ? 'rotate-180' : ''}`} />
                        </Button>
                      </TableCell>
                      <TableCell className="text-sm font-mono">
                        {isValid(parseISO(log.timestamp)) ? format(parseISO(log.timestamp), 'MMM d, yyyy HH:mm:ss') : 'Timestamp unavailable'}
                      </TableCell>
                      <TableCell className="text-sm font-mono">{log.actor_id || 'Unknown actor'}</TableCell>
                      <TableCell>
                        <Badge className={getActionBadgeClass(log.action)}>{log.action}</Badge>
                      </TableCell>
                      <TableCell className="text-sm">{log.resource_type}</TableCell>
                      <TableCell className="text-sm font-mono text-muted-foreground">{log.resource_id || '—'}</TableCell>
                    </TableRow>
                    {expandedLog === log.id && (
                      <TableRow>
                        <TableCell colSpan={6} className="bg-muted/30">
                          <div className="p-4">
                            <h4 className="text-sm font-medium mb-2">Record identifiers</h4>
                            <p className="break-all font-mono text-xs">Event ID: {log.id}</p>
                            <p className="break-all font-mono text-xs">Resource ID: {log.resource_id || 'Not reported'}</p>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))}
              </AnimatePresence>
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-4 border-t">
            <div className="text-sm text-muted-foreground">
              Showing {(page - 1) * perPage + 1}-{Math.min(page * perPage, total)} of {total} entries
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm">Page {page} of {totalPages || 1}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

// --- Settings Tab ---
function SettingsTab({ canManage }: { canManage: boolean }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tenant, setTenant] = useState<TenantSettings | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [maxUsers, setMaxUsers] = useState<number | null>(null);
  const [maxStorage, setMaxStorage] = useState<number | null>(null);
  const [maxApiCalls, setMaxApiCalls] = useState<number | null>(null);
  const [settingsJson, setSettingsJson] = useState<string | null>(null);
  const [showSaveConfirm, setShowSaveConfirm] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const response = await jarvisAPI.rbac.getTenantSettings();
      setTenant(response);
      setMaxUsers(response.max_users ?? null);
      setMaxStorage(response.max_storage_mb ?? null);
      setMaxApiCalls(response.max_api_calls_per_day ?? null);
      setSettingsJson(response.settings === undefined ? null : JSON.stringify(response.settings, null, 2));
      setLoadError(null);
    } catch (error: unknown) {
      setTenant(null);
      setMaxUsers(null);
      setMaxStorage(null);
      setMaxApiCalls(null);
      setSettingsJson(null);
      setLoadError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const payload: Partial<Pick<TenantSettings, 'max_users' | 'max_storage_mb' | 'max_api_calls_per_day' | 'settings'>> = {};
      if (maxUsers !== null) payload.max_users = maxUsers;
      if (maxStorage !== null) payload.max_storage_mb = maxStorage;
      if (maxApiCalls !== null) payload.max_api_calls_per_day = maxApiCalls;
      if (settingsJson !== null) payload.settings = JSON.parse(settingsJson);
      await jarvisAPI.rbac.updateTenantSettings(payload);
      toast.success('Settings saved successfully');
      setShowSaveConfirm(false);
      await fetchSettings();
    } catch (err: unknown) {
      toast.error('Failed to save settings: ' + getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleJsonChange = (value: string) => {
    setSettingsJson(value);
    try {
      JSON.parse(value);
      setJsonError(null);
    } catch (e: unknown) {
      setJsonError(getErrorMessage(e));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading settings...</span>
      </div>
    );
  }

  if (loadError) {
    return <RequestFailure error={loadError} onRetry={() => void fetchSettings()} />;
  }

  if (!tenant || Object.keys(tenant).length === 0) {
    return (
      <Card>
        <CardContent className="space-y-3 py-8">
          <p className="font-medium">No tenant settings were returned</p>
          <p className="text-sm text-muted-foreground">This is an empty server response, not a default tenant configuration. Settings cannot be edited until the server reports supported fields.</p>
          <Button variant="outline" onClick={() => void fetchSettings()}><RefreshCw className="mr-2 h-4 w-4" /> Retry</Button>
        </CardContent>
      </Card>
    );
  }
  const hasSupportedSettings = Boolean(
    tenant.name || tenant.slug || tenant.plan || tenant.status || tenant.created_at || tenant.id
    || tenant.max_users !== undefined || tenant.max_storage_mb !== undefined
    || tenant.max_api_calls_per_day !== undefined || tenant.settings !== undefined
  );
  if (!hasSupportedSettings) {
    return (
      <Card>
        <CardContent className="space-y-3 py-8">
          <p className="font-medium">No supported tenant settings were reported</p>
          <p className="text-sm text-muted-foreground">The response did not contain tenant identity, quota, or advanced settings fields, so no editable values are shown.</p>
          <Button variant="outline" onClick={() => void fetchSettings()}><RefreshCw className="mr-2 h-4 w-4" /> Retry</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Tenant Info Card */}
      {[tenant.name, tenant.slug, tenant.plan, tenant.status, tenant.created_at, tenant.id].some(Boolean) && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Globe className="h-5 w-5 text-primary" />
              </div>
              <div>
                {tenant.name && <CardTitle>{tenant.name}</CardTitle>}
                {tenant.slug && <CardDescription>{tenant.slug}</CardDescription>}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {tenant.plan && <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Plan</span>
                <Badge variant="default" className="capitalize">{tenant.plan}</Badge>
              </div>}
              {tenant.status && <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Status</span>
                <Badge className={tenant.status === 'active' ? 'bg-emerald-100 text-emerald-800' : ''}>{tenant.status}</Badge>
              </div>}
              {tenant.created_at && isValid(parseISO(tenant.created_at)) && <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Created</span>
                <p className="text-sm font-medium">{format(parseISO(tenant.created_at), 'PPP')}</p>
              </div>}
              {tenant.id && <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Tenant ID</span>
                <p className="text-sm font-mono">{tenant.id}</p>
              </div>}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Quota Management */}
      {[maxUsers, maxStorage, maxApiCalls].some((value) => value !== null) && <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Quota Management
          </CardTitle>
          <CardDescription>Configure resource limits for this tenant</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {!canManage && <p className="text-sm text-muted-foreground">Read-only view. Saving tenant settings is restricted to the configured tenant owner.</p>}
          {maxUsers !== null && <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="max-users">Maximum Users</Label>
              <span className="text-sm font-medium">{maxUsers.toLocaleString()}</span>
            </div>
            <Slider id="max-users" value={[maxUsers]} min={10} max={10000} step={10} disabled={!canManage} onValueChange={([v]) => setMaxUsers(v)} />
            <p className="text-xs text-muted-foreground">Maximum number of user accounts allowed</p>
          </div>}
          {maxStorage !== null && <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="max-storage">Maximum Storage (MB)</Label>
              <span className="text-sm font-medium">{(maxStorage / 1024).toFixed(1)} GB</span>
            </div>
            <Slider id="max-storage" value={[maxStorage]} min={100} max={102400} step={100} disabled={!canManage} onValueChange={([v]) => setMaxStorage(v)} />
            <p className="text-xs text-muted-foreground">Total storage allocated for documents and files</p>
          </div>}
          {maxApiCalls !== null && <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="max-api">Max API Calls / Day</Label>
              <span className="text-sm font-medium">{maxApiCalls.toLocaleString()}</span>
            </div>
            <Slider id="max-api" value={[maxApiCalls]} min={100} max={1000000} step={100} disabled={!canManage} onValueChange={([v]) => setMaxApiCalls(v)} />
            <p className="text-xs text-muted-foreground">Daily API request limit for this tenant</p>
          </div>}
        </CardContent>
        {canManage && <CardFooter className="border-t px-6 py-4">
          <Button onClick={() => setShowSaveConfirm(true)} disabled={saving || !!jsonError}>
            Save tenant limits
          </Button>
        </CardFooter>}
      </Card>}

      {/* Advanced Settings JSON Editor */}
      {settingsJson !== null && <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Advanced Configuration
          </CardTitle>
          <CardDescription>Edit tenant settings as JSON</CardDescription>
        </CardHeader>
        <CardContent>
          {!canManage && <p className="mb-3 text-sm text-muted-foreground">Read-only view. Saving tenant settings is restricted to the configured tenant owner.</p>}
          <div className="space-y-2">
            <Textarea
              value={settingsJson}
              onChange={(e) => handleJsonChange(e.target.value)}
              className="font-mono text-sm min-h-[200px] bg-background"
              disabled={!canManage}
            />
            {jsonError && (
              <p className="text-sm text-destructive flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                Invalid JSON: {jsonError}
              </p>
            )}
          </div>
        </CardContent>
        <CardFooter className="border-t px-6 py-4">
          {canManage && <Button onClick={() => setShowSaveConfirm(true)} disabled={!!jsonError || saving}>
            {saving ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save Settings
          </Button>}
        </CardFooter>
      </Card>}

      {/* Save Confirmation Dialog */}
      <Dialog open={showSaveConfirm} onOpenChange={setShowSaveConfirm}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Confirm Settings Change
            </DialogTitle>
            <DialogDescription>
              This will update the tenant quotas and advanced settings. Changes will take effect immediately.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 text-sm py-2">
            {maxUsers !== null && <div className="flex justify-between"><span className="text-muted-foreground">Max Users:</span> <span className="font-medium">{maxUsers.toLocaleString()}</span></div>}
            {maxStorage !== null && <div className="flex justify-between"><span className="text-muted-foreground">Max Storage:</span> <span className="font-medium">{(maxStorage / 1024).toFixed(1)} GB</span></div>}
            {maxApiCalls !== null && <div className="flex justify-between"><span className="text-muted-foreground">Max API Calls/Day:</span> <span className="font-medium">{maxApiCalls.toLocaleString()}</span></div>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSaveConfirm(false)}>Cancel</Button>
            <Button onClick={handleSaveSettings} disabled={saving || !canManage}>
              {saving && <RefreshCw className="mr-2 h-4 w-4 animate-spin" />}
              Confirm Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// --- Main Admin Page ---
export default function AdminPage() {
  const [activeTab, setActiveTab] = useState('users');
  const identityId = useAuthStore((state) => state.user?.id);
  const identityEmail = useAuthStore((state) => state.user?.email);
  const [ownerCheck, setOwnerCheck] = useState<{ identityId: string | null; canManage: boolean; error: unknown }>({
    identityId: null,
    canManage: false,
    error: null,
  });
  const canManage = Boolean(identityId && ownerCheck.identityId === identityId && ownerCheck.canManage);
  const ownerCheckError = identityId && ownerCheck.identityId === identityId ? ownerCheck.error : null;

  const checkOwnerAccess = useCallback(async () => {
    if (!identityId || !identityEmail) {
      setOwnerCheck({ identityId: identityId ?? null, canManage: false, error: new Error('Authenticated identity details are unavailable.') });
      return;
    }
    try {
      const result = await jarvisAPI.rbac.getUsers(1, 1, identityEmail);
      const currentUser = result.users.find((user) => user.id === identityId);
      setOwnerCheck({ identityId, canManage: Boolean(currentUser?.roles.includes('owner')), error: null });
    } catch (error: unknown) {
      setOwnerCheck({ identityId, canManage: false, error });
    }
  }, [identityEmail, identityId]);

  useEffect(() => {
    // The authenticated identity payload omits roles; read the server's user record before showing owner-only actions.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void checkOwnerAccess();
  }, [checkOwnerAccess]);

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Identity & governance</h1>
          <p className="text-muted-foreground mt-1">Users, roles, audit records, and tenant configuration</p>
          {!canManage && (
            <div className="mt-2 space-y-1 text-sm text-muted-foreground">
              <p>Read access is checked by each server endpoint. Mutation controls are shown only after the server confirms the configured owner role.</p>
              {ownerCheckError !== null && <p role="status">Owner role could not be verified: {getErrorMessage(ownerCheckError)} <Button variant="link" className="h-auto p-0" onClick={() => void checkOwnerAccess()}>Retry check</Button></p>}
            </div>
          )}
        </div>
      </motion.div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-flex">
          <TabsTrigger value="users" className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            <span>Users</span>
          </TabsTrigger>
          <TabsTrigger value="roles" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            <span>Roles</span>
          </TabsTrigger>
          <TabsTrigger value="audit" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            <span>Audit Log</span>
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            <span>Settings</span>
          </TabsTrigger>
        </TabsList>

        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.2 }}
          >
            <TabsContent value="users" className="mt-0">
              <UsersTab canManage={canManage} />
            </TabsContent>
            <TabsContent value="roles" className="mt-0">
              <RolesTab canManage={canManage} />
            </TabsContent>
            <TabsContent value="audit" className="mt-0">
              <AuditLogTab />
            </TabsContent>
            <TabsContent value="settings" className="mt-0">
              <SettingsTab canManage={canManage} />
            </TabsContent>
          </motion.div>
        </AnimatePresence>
      </Tabs>
    </div>
  );
}
