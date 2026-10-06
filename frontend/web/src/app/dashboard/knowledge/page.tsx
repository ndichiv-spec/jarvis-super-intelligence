"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Search,
  Plus,
  Edit,
  Trash2,
  Tags,
  ChevronDown,
  ChevronUp,
  Loader2,
  AlertCircle,
  Calendar,
  FileText,
  Layers,
  GitBranch,
  X,
  Sparkles,
  ArrowDownUp,
} from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { toast } from "sonner";

import {
  jarvisAPI,
  type KnowledgeEntry,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PatternEntry {
  pattern: string;
  response: string;
  category?: string;
}

interface EntryFormData {
  key: string;
  value: string;
  category: string;
  tags: string;
}

type SortOption = "newest" | "oldest" | "az";

const INITIAL_FORM: EntryFormData = {
  key: "",
  value: "",
  category: "infrastructure",
  tags: "",
};

const CATEGORY_COLORS: Record<string, string> = {
  general: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  command: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  fact: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  procedure: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  concept: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  troubleshooting: "bg-red-500/15 text-red-400 border-red-500/30",
  infrastructure: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  architecture: "bg-pink-500/15 text-pink-400 border-pink-500/30",
  deployment: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  security: "bg-red-500/15 text-red-400 border-red-500/30",
  performance: "bg-green-500/15 text-green-400 border-green-500/30",
  configuration: "bg-indigo-500/15 text-indigo-400 border-indigo-500/30",
};

function getCategoryColor(category?: string | null): string {
  const key = (category || "").toLowerCase();
  return CATEGORY_COLORS[key] || "bg-muted text-muted-foreground border-border";
}

const TRUNCATE_LENGTH = 120;

// ─── Stat Card ───────────────────────────────────────────────────────────────

function StatCard({
  title,
  value,
  icon: Icon,
  description,
  progressValue,
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  description?: string;
  progressValue?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card className="border border-white/10 bg-[#0d151c]">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            {title}
          </CardTitle>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{value}</div>
          {description && (
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          )}
          {progressValue !== undefined && (
            <Progress value={progressValue} className="mt-2 h-1" />
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ─── Empty State ─────────────────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col items-center justify-center py-16 px-4"
    >
      <div className="relative mb-6">
        <div className="absolute inset-0 blur-3xl bg-primary/20 rounded-full" />
        <div className="relative flex items-center justify-center w-24 h-24 rounded-full bg-primary/10 border border-primary/20">
          <BookOpen className="h-10 w-10 text-primary" />
        </div>
      </div>
      <h3 className="text-xl font-semibold mb-2">No knowledge entries yet</h3>
      <p className="text-muted-foreground text-center max-w-md mb-6">
        Start building your knowledge base by adding entries. Organize commands,
        facts, procedures, and more for quick reference.
      </p>
      <Button onClick={onAdd} className="gap-2">
        <Plus className="h-4 w-4" />
        Add your first entry
      </Button>
    </motion.div>
  );
}

// ─── Knowledge Card ──────────────────────────────────────────────────────────

function KnowledgeCard({
  entry,
  index,
  expanded,
  onToggleExpand,
  onEdit,
  onDelete,
}: {
  entry: KnowledgeEntry;
  index: number;
  expanded: boolean;
  onToggleExpand: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const isLong = entry.value.length > TRUNCATE_LENGTH;
  const displayValue =
    expanded || !isLong ? entry.value : entry.value.slice(0, TRUNCATE_LENGTH) + "...";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.25, delay: index * 0.05 }}
    >
      <Card
        className={`cursor-pointer border border-white/10 bg-[#0d151c] transition-colors duration-200 hover:border-cyan-300/40 ${
          expanded ? "border-cyan-300/40 ring-1 ring-cyan-300/10" : ""
        }`}
        onClick={onToggleExpand}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <FileText className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
              <CardTitle className="text-sm font-semibold truncate">
                {entry.key}
              </CardTitle>
            </div>
            <Badge
              variant="outline"
              className={`text-[10px] flex-shrink-0 ${getCategoryColor(entry.category)}`}
            >
              {entry.category}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-3">
          {/* Value preview / full */}
          <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap break-words">
            {displayValue}
          </div>

          {isLong && (
            <button
              className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
              onClick={(e) => {
                e.stopPropagation();
                onToggleExpand();
              }}
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3 w-3" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3" />
                  Read more
                </>
              )}
            </button>
          )}

          {/* Tags */}
          {entry.tags && entry.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <Tags className="h-3 w-3 text-muted-foreground mt-0.5" />
              {entry.tags.map((tag) => (
                <Badge
                  key={tag}
                  variant="secondary"
                  className="text-[10px] px-1.5 py-0 h-5"
                >
                  {tag}
                </Badge>
              ))}
            </div>
          )}

          {/* Meta + Actions */}
          <div className="flex items-center justify-between pt-2 border-t border-border/50">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Calendar className="h-3 w-3" />
              <span>
                {entry.created_at
                  ? formatDistanceToNow(new Date(entry.created_at), {
                      addSuffix: true,
                    })
                  : "Unknown"}
              </span>
            </div>
            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              {entry.read_only ? (
                <span className="px-2 text-[10px] uppercase tracking-wider text-slate-500">Shared · read only</span>
              ) : (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-foreground"
                    aria-label={`Edit knowledge entry ${entry.key}`}
                    onClick={onEdit}
                  >
                    <Edit className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    aria-label={`Delete knowledge entry ${entry.key}`}
                    onClick={onDelete}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ─── Entry Dialog (Add / Edit) ───────────────────────────────────────────────

function EntryDialog({
  open,
  onOpenChange,
  onSubmit,
  editingEntry,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: EntryFormData) => Promise<void>;
  editingEntry: KnowledgeEntry | null;
}) {
  const [form, setForm] = useState<EntryFormData>(INITIAL_FORM);
  const [errors, setErrors] = useState<Partial<Record<keyof EntryFormData, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (editingEntry) {
      setForm({
        key: editingEntry.key,
        value: editingEntry.value,
        category: editingEntry.category,
        tags: editingEntry.tags.join(", "),
      });
    } else {
      setForm(INITIAL_FORM);
    }
    setErrors({});
  }, [editingEntry, open]);

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof EntryFormData, string>> = {};

    if (!form.key.trim()) {
      newErrors.key = "Key is required";
    } else if (form.key.length < 2) {
      newErrors.key = "Key must be at least 2 characters";
    }

    if (!form.value.trim()) {
      newErrors.value = "Value is required";
    } else if (form.value.length < 5) {
      newErrors.value = "Value must be at least 5 characters";
    }

    if (!form.category.trim()) {
      newErrors.category = "Category is required";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const tags = form.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await onSubmit({ ...form, tags: tags.join(", ") });
      setForm(INITIAL_FORM);
      setErrors({});
      onOpenChange(false);
    } catch (error: any) {
      toast.error(`Failed to ${editingEntry ? "update" : "add"} entry: ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const updateField = <K extends keyof EntryFormData>(
    field: K,
    value: EntryFormData[K]
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const isEditing = editingEntry !== null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Edit Knowledge Entry" : "Add Knowledge Entry"}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? "Update the details of this knowledge entry."
              : "Add a new piece of knowledge to the knowledge base."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Key */}
          <div className="space-y-2">
            <Label htmlFor="entry-key">
              Key <span className="text-red-400">*</span>
            </Label>
            <Input
              id="entry-key"
              placeholder="e.g., deploy_command, api_base_url"
              value={form.key}
              onChange={(e) => updateField("key", e.target.value)}
              className={errors.key ? "border-red-500" : ""}
              disabled={isEditing}
            />
            {errors.key && (
              <p className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {errors.key}
              </p>
            )}
            {isEditing && (
              <p className="text-xs text-muted-foreground">
                Key cannot be changed after creation.
              </p>
            )}
          </div>

          {/* Value */}
          <div className="space-y-2">
            <Label htmlFor="entry-value">
              Value <span className="text-red-400">*</span>
            </Label>
            <Textarea
              id="entry-value"
              placeholder="The knowledge content..."
              value={form.value}
              onChange={(e) => updateField("value", e.target.value)}
              rows={6}
              className={errors.value ? "border-red-500" : ""}
            />
            {errors.value && (
              <p className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {errors.value}
              </p>
            )}
          </div>

          {/* Category */}
          <div className="space-y-2">
            <Label htmlFor="entry-category">
              Category <span className="text-red-400">*</span>
            </Label>
            <Select
              value={form.category}
              onValueChange={(v) => updateField("category", v)}
            >
              <SelectTrigger id="entry-category" className={errors.category ? "border-red-500" : ""}>
                <SelectValue placeholder="Select a category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="general">General</SelectItem>
                <SelectItem value="command">Command</SelectItem>
                <SelectItem value="fact">Fact</SelectItem>
                <SelectItem value="procedure">Procedure</SelectItem>
                <SelectItem value="concept">Concept</SelectItem>
                <SelectItem value="troubleshooting">Troubleshooting</SelectItem>
              </SelectContent>
            </Select>
            {errors.category && (
              <p className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {errors.category}
              </p>
            )}
          </div>

          {/* Tags */}
          <div className="space-y-2">
            <Label htmlFor="entry-tags">Tags</Label>
            <Input
              id="entry-tags"
              placeholder="e.g., deployment, api, production"
              value={form.tags}
              onChange={(e) => updateField("tags", e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Separate tags with commas.
            </p>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  {isEditing ? "Updating..." : "Adding..."}
                </>
              ) : (
                <>
                  {isEditing ? <Edit className="h-4 w-4 mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
                  {isEditing ? "Update Entry" : "Add Entry"}
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Delete Confirmation Dialog ──────────────────────────────────────────────

function DeleteConfirmDialog({
  open,
  onOpenChange,
  entryKey,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entryKey: string;
  onConfirm: () => Promise<void>;
}) {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleConfirm = async () => {
    setIsDeleting(true);
    try {
      await onConfirm();
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            Delete Entry
          </DialogTitle>
          <DialogDescription>
            Are you sure you want to delete &quot;{entryKey}&quot;? This action
            cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-1" />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 className="h-4 w-4 mr-1" />
                Delete
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Patterns Section ────────────────────────────────────────────────────────

function PatternsSection({
  patterns,
  isLoading,
  error,
  onAddPattern,
}: {
  patterns: PatternEntry[];
  isLoading: boolean;
  error: string | null;
  onAddPattern: (pattern: string, response: string) => Promise<void>;
}) {
  const [collapsed, setCollapsed] = useState(true);
  const [newPattern, setNewPattern] = useState("");
  const [newResponse, setNewResponse] = useState("");
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = async () => {
    if (!newPattern.trim() || !newResponse.trim()) {
      toast.error("Both pattern and response are required");
      return;
    }
    setIsAdding(true);
    try {
      await onAddPattern(newPattern.trim(), newResponse.trim());
      setNewPattern("");
      setNewResponse("");
    } catch (error: any) {
      toast.error(`Failed to add pattern: ${error.message}`);
    } finally {
      setIsAdding(false);
    }
  };

  return (
    <Card className="border border-white/10 bg-[#0d151c]">
      <CardHeader
        className="cursor-pointer select-none"
        onClick={() => setCollapsed((c) => !c)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-lg">Learned Patterns</CardTitle>
              <CardDescription>
                Pattern-response pairs learned from interactions
              </CardDescription>
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={collapsed ? "Expand learned patterns" : "Collapse learned patterns"}
            aria-expanded={!collapsed}
          >
            {collapsed ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronUp className="h-4 w-4" />
            )}
          </Button>
        </div>
      </CardHeader>

      <AnimatePresence>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <CardContent className="space-y-4">
              {/* Add new pattern form */}
              <div className="space-y-3 border border-white/10 bg-[#080d12] p-4">
                <h4 className="text-sm font-medium flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-amber-400" />
                  Add New Pattern
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="pattern-input" className="text-xs">
                      Pattern
                    </Label>
                    <Input
                      id="pattern-input"
                      placeholder="e.g., what is the time"
                      value={newPattern}
                      onChange={(e) => setNewPattern(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pattern-response" className="text-xs">
                      Response
                    </Label>
                    <Input
                      id="pattern-response"
                      placeholder="e.g., The current time is..."
                      value={newResponse}
                      onChange={(e) => setNewResponse(e.target.value)}
                    />
                  </div>
                </div>
                <Button
                  size="sm"
                  onClick={handleAdd}
                  disabled={isAdding || !newPattern.trim() || !newResponse.trim()}
                  className="gap-1"
                >
                  {isAdding ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Plus className="h-3.5 w-3.5" />
                  )}
                  {isAdding ? "Adding..." : "Add Pattern"}
                </Button>
              </div>

              {/* Pattern list */}
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                </div>
              ) : error ? (
                <div role="alert" className="border border-destructive/30 bg-destructive/5 px-4 py-6 text-center text-sm text-destructive">
                  Could not load learned patterns: {error}
                </div>
              ) : patterns.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  No learned patterns yet. Patterns are automatically learned
                  from interactions.
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {patterns.map((p, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.03 }}
                      className="grid grid-cols-[1fr_auto_1fr] items-start gap-3 border border-white/10 bg-[#080d12] p-3"
                    >
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">
                          Pattern
                        </p>
                        <code className="text-sm font-mono text-foreground break-all">
                          {p.pattern}
                        </code>
                      </div>
                      <ArrowDownUp className="h-4 w-4 text-muted-foreground mt-4 flex-shrink-0" />
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">
                          Response
                        </p>
                        <p className="text-sm text-foreground break-words">
                          {p.response}
                        </p>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </CardContent>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [patterns, setPatterns] = useState<PatternEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPatternsLoading, setIsPatternsLoading] = useState(true);
  const [entriesError, setEntriesError] = useState<string | null>(null);
  const [patternsError, setPatternsError] = useState<string | null>(null);

  // Search & filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [sortBy, setSortBy] = useState<SortOption>("newest");

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<KnowledgeEntry | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingEntry, setDeletingEntry] = useState<KnowledgeEntry | null>(null);

  // Expanded cards
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // ── Fetch data ───────────────────────────────────────────────────────────

  const fetchEntries = useCallback(async () => {
    setIsLoading(true);
    setEntriesError(null);
    try {
      const data = await jarvisAPI.getKnowledgeEntries(
        categoryFilter !== "all" ? categoryFilter : undefined
      );
      const results = Array.isArray(data)
        ? data
        : Array.isArray(data?.entries)
        ? data.entries
        : Array.isArray(data?.results)
        ? data.results
        : [];
      setEntries(results);
    } catch (error: any) {
      toast.error(`Failed to load knowledge entries: ${error.message}`);
      setEntriesError(error instanceof Error ? error.message : "Knowledge entries are temporarily unavailable.");
    } finally {
      setIsLoading(false);
    }
  }, [categoryFilter]);

  const fetchPatterns = useCallback(async () => {
    setIsPatternsLoading(true);
    setPatternsError(null);
    try {
      const data = await jarvisAPI.getKnowledgePatterns();
      const results = Array.isArray(data)
        ? data
        : Array.isArray(data?.patterns)
        ? data.patterns
        : Array.isArray(data?.results)
        ? data.results
        : null;
      if (results) {
        setPatterns(results);
      } else {
        setPatterns([]);
        setPatternsError("Pattern details are unavailable in the response from this service.");
      }
    } catch (error: unknown) {
      setPatterns([]);
      setPatternsError(error instanceof Error ? error.message : "Patterns are temporarily unavailable.");
    } finally {
      setIsPatternsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
    fetchPatterns();
  }, [fetchEntries, fetchPatterns]);

  // ── Debounced search ─────────────────────────────────────────────────────

  useEffect(() => {
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => {
      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    };
  }, [searchQuery]);

  // ── Filtered & sorted entries ────────────────────────────────────────────

  const filteredEntries = useMemo(() => {
    let result = [...entries];

    // Filter by category
    if (categoryFilter !== "all") {
      result = result.filter(
        (e) => e.category?.toLowerCase() === categoryFilter.toLowerCase()
      );
    }

    // Filter by search query
    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase();
      result = result.filter(
        (e) =>
          e.key.toLowerCase().includes(q) ||
          e.value.toLowerCase().includes(q) ||
          e.tags?.some((t) => t.toLowerCase().includes(q)) ||
          e.category?.toLowerCase().includes(q)
      );
    }

    // Sort
    switch (sortBy) {
      case "newest":
        result.sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        break;
      case "oldest":
        result.sort(
          (a, b) =>
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
        break;
      case "az":
        result.sort((a, b) => a.key.localeCompare(b.key));
        break;
    }

    return result;
  }, [entries, categoryFilter, debouncedSearch, sortBy]);

  // ── Derived stats ────────────────────────────────────────────────────────

  const categories = useMemo(
    () => Array.from(new Set(entries.map((e) => e.category).filter(Boolean))),
    [entries]
  );

  const totalTags = useMemo(
    () => new Set(entries.flatMap((e) => e.tags || [])).size,
    [entries]
  );

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleToggleExpand = (key: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleAddEntry = async (data: EntryFormData) => {
    const tags = data.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    await jarvisAPI.addKnowledge(data.key, data.value, data.category, tags);
    toast.success(`Entry "${data.key}" added successfully`);
    setEditingEntry(null);
    await fetchEntries();
    await fetchPatterns();
  };

  const handleEditEntry = async (data: EntryFormData) => {
    if (!editingEntry) return;
    const tags = data.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    // The key is locked while editing; the backend POST safely replaces that key.
    await jarvisAPI.addKnowledge(data.key, data.value, data.category, tags);
    toast.success(`Entry "${data.key}" updated successfully`);
    setEditingEntry(null);
    await fetchEntries();
    await fetchPatterns();
  };

  const handleOpenEdit = (entry: KnowledgeEntry) => {
    setEditingEntry(entry);
    setDialogOpen(true);
  };

  const handleOpenDelete = (entry: KnowledgeEntry) => {
    setDeletingEntry(entry);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!deletingEntry) return;
    await jarvisAPI.deleteKnowledge(deletingEntry.key);
    toast.success(`Entry "${deletingEntry.key}" deleted`);
    setDeletingEntry(null);
    setDeleteDialogOpen(false);
    await fetchEntries();
    await fetchPatterns();
  };

  const handleAddPattern = async (pattern: string, response: string) => {
    // Patterns are learned automatically; we add it as a knowledge entry
    await jarvisAPI.addKnowledge(
      `pattern:${pattern}`,
      response,
      "pattern",
      ["learned", "auto"]
    );
    toast.success("Pattern added");
    await fetchPatterns();
  };

  const handleOpenAddDialog = () => {
    setEditingEntry(null);
    setDialogOpen(true);
  };

  // ── All unique categories for filter dropdown ────────────────────────────

  const allCategories = useMemo(
    () => Array.from(new Set(entries.map((e) => e.category).filter(Boolean))).sort(),
    [entries]
  );

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <main className="min-h-full bg-[#080d12] px-4 py-8 text-slate-100 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-6xl space-y-7">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center border border-white/10 bg-[#0d151c]">
              <BookOpen className="h-5 w-5 text-cyan-300" />
            </div>
            JARVIS Knowledge Studio
          </h1>
          <p className="text-muted-foreground mt-1">
            Unified knowledge library, operational playbooks, and trusted system context for production work.
          </p>
        </div>
        <Button onClick={handleOpenAddDialog} className="flex-shrink-0 gap-2 bg-cyan-300 text-slate-950 hover:bg-cyan-200">
          <Plus className="h-4 w-4" />
          Add knowledge item
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Entries"
          value={isLoading ? "Loading" : entriesError ? "Unavailable" : entries.length}
          icon={Layers}
          description="Knowledge entries"
        />
        <StatCard
          title="Categories"
          value={isLoading ? "Loading" : entriesError ? "Unavailable" : categories.length}
          icon={BookOpen}
          description="Unique categories"
        />
        <StatCard
          title="Tags"
          value={isLoading ? "Loading" : entriesError ? "Unavailable" : totalTags}
          icon={Tags}
          description="Unique tags"
        />
        <StatCard
          title="Patterns"
          value={isPatternsLoading ? "Loading" : patternsError ? "Unavailable" : patterns.length}
          icon={GitBranch}
          description="Learned patterns"
        />
      </div>

      {/* Search & Filter Bar */}
      <Card className="border border-white/10 bg-[#0d151c]">
        <CardContent className="pt-5">
          <div className="flex flex-col sm:flex-row gap-3">
            {/* Search */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search entries by key, value, tag, or category..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
              {searchQuery && (
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label="Clear knowledge search"
                  onClick={() => setSearchQuery("")}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Category filter */}
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="w-full sm:w-[180px]">
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {allCategories.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {cat}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Sort */}
            <Select
              value={sortBy}
              onValueChange={(v) => setSortBy(v as SortOption)}
            >
              <SelectTrigger className="w-full sm:w-[160px]">
                <SelectValue placeholder="Sort" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="newest">Newest first</SelectItem>
                <SelectItem value="oldest">Oldest first</SelectItem>
                <SelectItem value="az">A-Z</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {entriesError && (
        <div role="alert" className="flex flex-col gap-3 border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-medium">Knowledge entries could not be loaded.</p>
            <p className="mt-1 text-xs text-destructive/80">{entriesError} {entries.length > 0 ? "Showing the last available entries." : ""}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void fetchEntries()} disabled={isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Retry
          </Button>
        </div>
      )}

      {/* Entries Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : entriesError && entries.length === 0 ? null : filteredEntries.length === 0 ? (
        searchQuery || categoryFilter !== "all" ? (
          <Card className="border border-white/10 bg-[#0d151c]">
            <CardContent className="py-12 text-center">
              <Search className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
              <h3 className="text-lg font-semibold mb-1">No results found</h3>
              <p className="text-muted-foreground text-sm">
                Try adjusting your search or filter criteria.
              </p>
            </CardContent>
          </Card>
        ) : (
          <EmptyState onAdd={handleOpenAddDialog} />
        )
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <AnimatePresence mode="popLayout">
            {filteredEntries.map((entry, index) => (
              <KnowledgeCard
                key={entry.key}
                entry={entry}
                index={index}
                expanded={expandedKeys.has(entry.key)}
                onToggleExpand={() => handleToggleExpand(entry.key)}
                onEdit={() => handleOpenEdit(entry)}
                onDelete={() => handleOpenDelete(entry)}
              />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Patterns Section */}
      <PatternsSection
        patterns={patterns}
        isLoading={isPatternsLoading}
        error={patternsError}
        onAddPattern={handleAddPattern}
      />

      {/* Add / Edit Dialog */}
      <EntryDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSubmit={editingEntry ? handleEditEntry : handleAddEntry}
        editingEntry={editingEntry}
      />

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        entryKey={deletingEntry?.key || ""}
        onConfirm={handleConfirmDelete}
      />
      </div>
    </main>
  );
}
