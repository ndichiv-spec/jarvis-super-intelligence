'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { format, subDays, parseISO } from 'date-fns';
import { toast } from 'sonner';
import {
  Users, Shield, FileText, Settings, Search, Plus, Edit, Trash2,
  Lock, MoreHorizontal, ChevronDown, ChevronLeft, ChevronRight,
  Download, RefreshCw, X, Check, AlertTriangle, Eye, EyeOff,
  Calendar, Filter, UserPlus, Key, Activity, Globe, Cpu, Database,
  Wrench, Monitor, BarChart3
} from 'lucide-react';
import { jarvisAPI, User as UserType, Role, AuditLogEntry, Permission, TenantSettings } from '@/lib/api';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription, DialogClose } from '@/components/ui/dialog';
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
  inactive: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  suspended: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

// --- Users Tab ---
function UsersTab() {
  const [users, setUsers] = useState<UserType[]>([]);
  const [loading, setLoading] = useState(true);
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

  const [addForm, setAddForm] = useState({ email: '', username: '', password: '', full_name: '', roles: [] as string[] });
  const [editForm, setEditForm] = useState({ roles: [] as string[], status: 'active' as UserType['status'] });

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jarvisAPI.rbac.getUsers(page, perPage, search || undefined);
      setUsers(data.users);
      setTotal(data.total);
    } catch (err: any) {
      toast.error('Failed to load users: ' + (err.message || 'Unknown error'));
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

  useEffect(() => { fetchUsers(); }, [fetchUsers]);
  useEffect(() => { fetchRoles(); }, [fetchRoles]);

  const totalPages = Math.ceil(total / perPage);

  const handleAddUser = async () => {
    if (!addForm.email || !addForm.username || !addForm.password) {
      toast.error('Email, username, and password are required');
      return;
    }
    try {
      await jarvisAPI.rbac.createUser(addForm);
      toast.success('User created successfully');
      setShowAddDialog(false);
      setAddForm({ email: '', username: '', password: '', full_name: '', roles: [] });
      fetchUsers();
    } catch (err: any) {
      toast.error('Failed to create user: ' + (err.message || 'Unknown error'));
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
    } catch (err: any) {
      toast.error('Failed to update user: ' + (err.message || 'Unknown error'));
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
    } catch (err: any) {
      toast.error('Failed to delete user: ' + (err.message || 'Unknown error'));
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
        <Button onClick={() => setShowAddDialog(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Add User
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading users...</span>
        </div>
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
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Roles</TableHead>
                <TableHead>Status</TableHead>
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
                      <TableCell>
                        {user.last_login_at ? format(parseISO(user.last_login_at), 'MMM d, yyyy HH:mm') : 'Never'}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
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
                      </TableCell>
                    </TableRow>
                    {expandedUser === user.id && (
                      <TableRow>
                        <TableCell colSpan={7} className="bg-muted/30">
                          <div className="p-4 space-y-2 text-sm">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                              <div><span className="text-muted-foreground">Username:</span> <span className="font-medium">{user.username}</span></div>
                              <div><span className="text-muted-foreground">Email:</span> <span className="font-medium">{user.email}</span></div>
                              <div><span className="text-muted-foreground">Full Name:</span> <span className="font-medium">{user.full_name || 'N/A'}</span></div>
                              <div><span className="text-muted-foreground">Status:</span> <Badge className={STATUS_COLORS[user.status]}>{user.status}</Badge></div>
                              <div><span className="text-muted-foreground">User ID:</span> <code className="text-xs">{user.id}</code></div>
                              <div><span className="text-muted-foreground">Created:</span> {user.created_at ? format(parseISO(user.created_at), 'PPP') : 'N/A'}</div>
                              <div><span className="text-muted-foreground">Last Login:</span> {user.last_login_at ? format(parseISO(user.last_login_at), 'PPP HH:mm') : 'Never'}</div>
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
      )}

      {/* Add User Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add New User</DialogTitle>
            <DialogDescription>Create a new user account with role assignments.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="add-email">Email *</Label>
                <Input id="add-email" type="email" value={addForm.email} onChange={(e) => setAddForm(f => ({ ...f, email: e.target.value }))} placeholder="user@example.com" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-username">Username *</Label>
                <Input id="add-username" value={addForm.username} onChange={(e) => setAddForm(f => ({ ...f, username: e.target.value }))} placeholder="johndoe" />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="add-password">Password *</Label>
              <div className="relative">
                <Input id="add-password" type={showPassword ? 'text' : 'password'} value={addForm.password} onChange={(e) => setAddForm(f => ({ ...f, password: e.target.value }))} placeholder="Secure password" />
                <Button variant="ghost" size="icon" className="absolute right-0 top-0 h-10 w-10" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="add-fullname">Full Name</Label>
              <Input id="add-fullname" value={addForm.full_name} onChange={(e) => setAddForm(f => ({ ...f, full_name: e.target.value }))} placeholder="John Doe" />
            </div>
            <div className="space-y-2">
              <Label>Roles</Label>
              <div className="flex flex-wrap gap-2">
                {allRoles.map((role) => (
                  <Badge
                    key={role}
                    variant={addForm.roles.includes(role) ? 'default' : 'outline'}
                    className="cursor-pointer"
                    onClick={() => setAddForm(f => ({
                      ...f,
                      roles: f.roles.includes(role) ? f.roles.filter(r => r !== role) : [...f.roles, role]
                    }))}
                  >
                    {addForm.roles.includes(role) && <Check className="mr-1 h-3 w-3" />}
                    {role}
                  </Badge>
                ))}
                {allRoles.length === 0 && <span className="text-muted-foreground text-sm">No roles available</span>}
              </div>
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
                    <SelectItem value="inactive">Inactive</SelectItem>
                    <SelectItem value="suspended">Suspended</SelectItem>
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
function RolesTab() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditorDialog, setShowEditorDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [createForm, setCreateForm] = useState({ name: '', description: '', permissions: [] as string[] });
  const [editForm, setEditForm] = useState({ name: '', description: '', permissions: [] as string[] });

  const fetchRoles = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jarvisAPI.rbac.getRoles();
      setRoles(data.roles);
    } catch (err: any) {
      toast.error('Failed to load roles: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchPermissions = useCallback(async () => {
    try {
      const data = await jarvisAPI.rbac.getPermissions();
      setPermissions(data.permissions);
    } catch {
      // Non-critical, generate from groups
      const generated: Permission[] = [];
      Object.keys(PERMISSION_GROUPS).forEach(resource => {
        ['read', 'write', 'delete', 'admin'].forEach(action => {
          generated.push({ id: `${resource}:${action}`, resource, action, description: `${action} ${resource}` });
        });
      });
      setPermissions(generated);
    }
  }, []);

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
    } catch (err: any) {
      toast.error('Failed to create role: ' + (err.message || 'Unknown error'));
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
    } catch (err: any) {
      toast.error('Failed to update role: ' + (err.message || 'Unknown error'));
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
    } catch (err: any) {
      toast.error('Failed to delete role: ' + (err.message || 'Unknown error'));
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
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Role Management</h2>
        <Button onClick={() => setShowCreateDialog(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Role
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading roles...</span>
        </div>
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
                <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => openEditor(role)}>
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
                    <Button variant="outline" size="sm" className="flex-1" onClick={(e) => { e.stopPropagation(); openEditor(role); }}>
                      <Edit className="mr-1 h-3 w-3" /> Edit
                    </Button>
                    {!role.is_system && (
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
  const [page, setPage] = useState(1);
  const [perPage] = useState(25);
  const [total, setTotal] = useState(0);
  const [dateFrom, setDateFrom] = useState(format(subDays(new Date(), 7), 'yyyy-MM-dd'));
  const [dateTo, setDateTo] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [userId, setUserId] = useState('');
  const [action, setAction] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [users, setUsers] = useState<UserType[]>([]);

  const RESOURCE_TYPES = ['users', 'roles', 'permissions', 'settings', 'knowledge', 'agents', 'system', 'audit_logs'];
  const ACTIONS = ['create', 'update', 'delete', 'login', 'logout', 'assign_role', 'remove_role', 'update_settings'];

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jarvisAPI.rbac.getAuditLogs({ date_from: dateFrom, date_to: dateTo, user_id: userId || undefined, action: action || undefined, resource_type: resourceType || undefined, page, per_page: perPage });
      setLogs(data.logs);
      setTotal(data.total);
    } catch (err: any) {
      toast.error('Failed to load audit logs: ' + (err.message || 'Unknown error'));
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, userId, action, resourceType, page, perPage]);

  const fetchUsers = useCallback(async () => {
    try {
      const data = await jarvisAPI.rbac.getUsers(1, 100);
      setUsers(data.users);
    } catch {
      // Non-critical
    }
  }, []);

  useEffect(() => { fetchLogs(); fetchUsers(); }, [fetchLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchLogs]);

  const totalPages = Math.ceil(total / perPage);

  const handleExport = async () => {
    try {
      const blob = await jarvisAPI.rbac.exportAuditLogs({ date_from: dateFrom, date_to: dateTo, user_id: userId || undefined, action: action || undefined, resource_type: resourceType || undefined });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-${format(new Date(), 'yyyy-MM-dd')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Audit logs exported successfully');
    } catch (err: any) {
      toast.error('Failed to export: ' + (err.message || 'Unknown error'));
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
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="mr-1 h-4 w-4" />
            Export CSV
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
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Date From</Label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Date To</Label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">User</Label>
              <Select value={userId} onValueChange={setUserId}>
                <SelectTrigger><SelectValue placeholder="All users" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All users</SelectItem>
                  {users.map(u => (
                    <SelectItem key={u.id} value={u.id}>{u.full_name || u.username}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Action</Label>
              <Select value={action} onValueChange={setAction}>
                <SelectTrigger><SelectValue placeholder="All actions" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All actions</SelectItem>
                  {ACTIONS.map(a => (
                    <SelectItem key={a} value={a}>{a}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Resource Type</Label>
              <Select value={resourceType} onValueChange={setResourceType}>
                <SelectTrigger><SelectValue placeholder="All types" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All types</SelectItem>
                  {RESOURCE_TYPES.map(r => (
                    <SelectItem key={r} value={r}>{r}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button variant="outline" size="sm" className="w-full" onClick={fetchLogs}>
                Apply Filters
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading logs...</span>
        </div>
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
                <TableHead>User</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>IP Address</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <AnimatePresence>
                {logs.map((log) => (
                  <React.Fragment key={log.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                    >
                      <TableCell>
                        <ChevronDown className={`h-4 w-4 transition-transform ${expandedLog === log.id ? 'rotate-180' : ''}`} />
                      </TableCell>
                      <TableCell className="text-sm font-mono">
                        {format(parseISO(log.created_at), 'MMM d, yyyy HH:mm:ss')}
                      </TableCell>
                      <TableCell className="text-sm">
                        {log.user_name || log.user_email || log.user_id}
                      </TableCell>
                      <TableCell>
                        <Badge className={getActionBadgeClass(log.action)}>{log.action}</Badge>
                      </TableCell>
                      <TableCell className="text-sm">{log.resource_type}</TableCell>
                      <TableCell className="text-sm font-mono text-muted-foreground">{log.ip_address || '-'}</TableCell>
                    </TableRow>
                    {expandedLog === log.id && log.details && (
                      <TableRow>
                        <TableCell colSpan={6} className="bg-muted/30">
                          <div className="p-4">
                            <h4 className="text-sm font-medium mb-2">Details</h4>
                            <pre className="text-xs bg-background rounded-md p-3 overflow-auto max-h-40 border">
                              {JSON.stringify(log.details, null, 2)}
                            </pre>
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
function SettingsTab() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tenant, setTenant] = useState<TenantSettings | null>(null);
  const [maxUsers, setMaxUsers] = useState(100);
  const [maxStorage, setMaxStorage] = useState(10240);
  const [maxApiCalls, setMaxApiCalls] = useState(10000);
  const [settingsJson, setSettingsJson] = useState('{}');
  const [showSaveConfirm, setShowSaveConfirm] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const response = await jarvisAPI.rbac.getTenantSettings();
      setTenant(response);
      setMaxUsers(response.max_users || 100);
      setMaxStorage(response.max_storage_mb || 10240);
      setMaxApiCalls(response.max_api_calls_per_day || 10000);
      setSettingsJson(JSON.stringify(response.settings || {}, null, 2));
    } catch {
      // Fallback mock data
      const mockTenant: TenantSettings = {
        id: 'tenant-001',
        name: 'JARVIS Enterprise',
        slug: 'jarvis-enterprise',
        plan: 'enterprise',
        status: 'active',
        created_at: new Date().toISOString(),
        max_users: 100,
        max_storage_mb: 10240,
        max_api_calls_per_day: 10000,
        settings: {},
      };
      setTenant(mockTenant);
      setSettingsJson('{}');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      await jarvisAPI.rbac.updateTenantSettings({
        max_users: maxUsers,
        max_storage_mb: maxStorage,
        max_api_calls_per_day: maxApiCalls,
        settings: JSON.parse(settingsJson),
      });
      toast.success('Settings saved successfully');
      setShowSaveConfirm(false);
      fetchSettings();
    } catch (err: any) {
      toast.error('Failed to save settings: ' + (err.message || 'Unknown error'));
    } finally {
      setSaving(false);
    }
  };

  const handleJsonChange = (value: string) => {
    setSettingsJson(value);
    try {
      JSON.parse(value);
      setJsonError(null);
    } catch (e: any) {
      setJsonError(e.message);
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

  return (
    <div className="space-y-6">
      {/* Tenant Info Card */}
      {tenant && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Globe className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle>{tenant.name}</CardTitle>
                <CardDescription>{tenant.slug}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Plan</span>
                <Badge variant="default" className="capitalize">{tenant.plan}</Badge>
              </div>
              <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Status</span>
                <Badge className={tenant.status === 'active' ? 'bg-emerald-100 text-emerald-800' : ''}>{tenant.status}</Badge>
              </div>
              <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Created</span>
                <p className="text-sm font-medium">{format(parseISO(tenant.created_at), 'PPP')}</p>
              </div>
              <div className="space-y-1">
                <span className="text-sm text-muted-foreground">Tenant ID</span>
                <p className="text-sm font-mono">{tenant.id}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Quota Management */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Quota Management
          </CardTitle>
          <CardDescription>Configure resource limits for this tenant</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="max-users">Maximum Users</Label>
              <span className="text-sm font-medium">{maxUsers.toLocaleString()}</span>
            </div>
            <Slider id="max-users" value={[maxUsers]} min={10} max={10000} step={10} onValueChange={([v]) => setMaxUsers(v)} />
            <p className="text-xs text-muted-foreground">Maximum number of user accounts allowed</p>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="max-storage">Maximum Storage (MB)</Label>
              <span className="text-sm font-medium">{(maxStorage / 1024).toFixed(1)} GB</span>
            </div>
            <Slider id="max-storage" value={[maxStorage]} min={100} max={102400} step={100} onValueChange={([v]) => setMaxStorage(v)} />
            <p className="text-xs text-muted-foreground">Total storage allocated for documents and files</p>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="max-api">Max API Calls / Day</Label>
              <span className="text-sm font-medium">{maxApiCalls.toLocaleString()}</span>
            </div>
            <Slider id="max-api" value={[maxApiCalls]} min={100} max={1000000} step={100} onValueChange={([v]) => setMaxApiCalls(v)} />
            <p className="text-xs text-muted-foreground">Daily API request limit for this tenant</p>
          </div>
        </CardContent>
      </Card>

      {/* Advanced Settings JSON Editor */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Advanced Configuration
          </CardTitle>
          <CardDescription>Edit tenant settings as JSON</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Textarea
              value={settingsJson}
              onChange={(e) => handleJsonChange(e.target.value)}
              className="font-mono text-sm min-h-[200px] bg-background"
              placeholder='{"feature_flags": {"new_ui": true}}'
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
          <Button onClick={() => setShowSaveConfirm(true)} disabled={!!jsonError || saving}>
            {saving ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save Settings
          </Button>
        </CardFooter>
      </Card>

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
            <div className="flex justify-between"><span className="text-muted-foreground">Max Users:</span> <span className="font-medium">{maxUsers.toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Max Storage:</span> <span className="font-medium">{(maxStorage / 1024).toFixed(1)} GB</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Max API Calls/Day:</span> <span className="font-medium">{maxApiCalls.toLocaleString()}</span></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSaveConfirm(false)}>Cancel</Button>
            <Button onClick={handleSaveSettings} disabled={saving}>
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

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Admin Panel</h1>
          <p className="text-muted-foreground mt-1">Manage users, roles, audit logs, and system settings</p>
        </div>
      </motion.div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-flex">
          <TabsTrigger value="users" className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            <span className="hidden sm:inline">Users</span>
          </TabsTrigger>
          <TabsTrigger value="roles" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            <span className="hidden sm:inline">Roles</span>
          </TabsTrigger>
          <TabsTrigger value="audit" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            <span className="hidden sm:inline">Audit Log</span>
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            <span className="hidden sm:inline">Settings</span>
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
              <UsersTab />
            </TabsContent>
            <TabsContent value="roles" className="mt-0">
              <RolesTab />
            </TabsContent>
            <TabsContent value="audit" className="mt-0">
              <AuditLogTab />
            </TabsContent>
            <TabsContent value="settings" className="mt-0">
              <SettingsTab />
            </TabsContent>
          </motion.div>
        </AnimatePresence>
      </Tabs>
    </div>
  );
}
