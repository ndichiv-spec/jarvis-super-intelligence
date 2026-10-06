"use client";

import * as React from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import {
  Paperclip,
  X as XIcon,
  FileText,
  Upload,
  Image as ImageIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/components/real-ai-chat";

/** A file attached to a chat message, with upload state and preview. */
export interface AttachedFile {
  id: string;
  file: File;
  preview: string;
  uploadProgress?: number;
  uploadedUrl?: string;
}

const ALLOWED_FILE_TYPES = {
  "image/*": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
  "text/plain": [".txt", ".md", ".log"],
  "application/pdf": [".pdf"],
  "application/json": [".json"],
  "application/javascript": [".js", ".ts"],
  "text/csv": [".csv"],
};

function isImageFile(file: File): boolean {
  return file.type.startsWith("image/");
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

interface FileAttachmentAreaProps {
  onFilesSelected: (files: File[]) => void;
  onUpload: (file: File, onProgress: (progress: number) => void) => Promise<string | null>;
  maxFiles?: number;
  maxSizeMB?: number;
}

/**
 * FileAttachmentArea
 *
 * A drag-and-drop zone for attaching files to chat messages.
 * Uses react-dropzone for file selection and renders preview thumbnails.
 * Uploads files to `/api/v1/multimodal/upload/image` via the `onUpload` callback.
 */
export default function FileAttachmentArea({
  onFilesSelected,
  onUpload,
  maxFiles = 5,
  maxSizeMB = 10,
}: FileAttachmentAreaProps) {
  const [attachments, setAttachments] = React.useState<AttachedFile[]>([]);
  const maxSize = maxSizeMB * 1024 * 1024;

  const onDrop = (acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.slice(0, maxFiles).map((file) => ({
      id: `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file,
      preview: isImageFile(file) ? URL.createObjectURL(file) : "",
      uploadProgress: 0,
    }));
    setAttachments((prev) => [...prev, ...newFiles]);
    onFilesSelected(newFiles.map((f) => f.file));

    // Upload files one by one
    newFiles.forEach((af) => {
      onUpload(af.file, (progress) => {
        setAttachments((prev) =>
          prev.map((f) =>
            f.id === af.id ? { ...f, uploadProgress: progress } : f
          )
        );
      }).then((url) => {
        if (url) {
          setAttachments((prev) =>
            prev.map((f) =>
              f.id === af.id ? { ...f, uploadedUrl: url } : f
            )
          );
        }
      });
    });
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ALLOWED_FILE_TYPES,
    maxSize,
    maxFiles,
    onDrop,
    onDropRejected: (rejection) => {
      console.warn("File rejected:", rejection);
    },
  });

  const removeFile = (id: string) => {
    const file = attachments.find((f) => f.id === id);
    if (file?.preview) URL.revokeObjectURL(file.preview);
    setAttachments((prev) => prev.filter((f) => f.id !== id));
  };

  const clearAll = () => {
    attachments.forEach((f) => {
      if (f.preview) URL.revokeObjectURL(f.preview);
    });
    setAttachments([]);
  };

  // Cleanup object URLs on unmount
  React.useEffect(() => {
    return () => {
      attachments.forEach((f) => {
        if (f.preview) URL.revokeObjectURL(f.preview);
      });
    };
  }, []);

  return (
    <div className="space-y-2">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-lg p-3 text-center cursor-pointer transition-all
          ${isDragActive
            ? "border-cyan-400 bg-cyan-500/10"
            : "border-white/10 hover:border-cyan-400/40 hover:bg-white/[0.03]"
          }
        `}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-1 text-xs text-gray-400">
          <Upload className="h-4 w-4" />
          <span>
            {isDragActive
              ? "Drop files here..."
              : `Drag & drop or click to attach (${maxFiles} max, ${maxSizeMB}MB each)`}
          </span>
        </div>
      </div>

      {/* File previews */}
      <AnimatePresence>
        {attachments.map((af) => (
          <motion.div
            key={af.id}
            initial={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, height: 0 }}
            className="flex items-center gap-2.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5"
          >
            {af.preview ? (
              <img
                src={af.preview}
                alt={af.file.name}
                className="h-8 w-8 rounded object-cover"
              />
            ) : (
              <FileText className="h-5 w-5 text-cyan-400/50" />
            )}
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">
                {af.file.name}
              </div>
              <div className="text-[10px] text-gray-500 flex items-center gap-2">
                <span>{formatFileSize(af.file.size)}</span>
                {af.uploadProgress !== undefined && af.uploadProgress < 100 && (
                  <span className="text-cyan-400">{af.uploadProgress}%</span>
                )}
                {af.uploadedUrl && (
                  <span className="text-green-400">✓ uploaded</span>
                )}
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0 hover:bg-white/[0.05]"
              onClick={() => removeFile(af.id)}
              title="Remove file"
            >
              <XIcon className="h-3 w-3 text-gray-400 hover:text-red-400" />
            </Button>
          </motion.div>
        ))}
      </AnimatePresence>

      {attachments.length > 0 && (
        <div className="flex justify-end">
          <Button
            variant="link"
            size="sm"
            className="text-xs text-red-400 hover:text-red-300 p-0 h-auto"
            onClick={clearAll}
          >
            Clear all
          </Button>
        </div>
      )}
    </div>
  );
}
