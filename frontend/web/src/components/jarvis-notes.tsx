'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Edit, Trash2, Save, X, Search, Tag } from 'lucide-react';
import { getApiUrl } from '@/lib/runtime-url';

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string;
  created_at: string;
  updated_at: string;
}

const authHeaders = (json = false): Record<string, string> => {
  return json ? { 'Content-Type': 'application/json' } : {};
};

const sessionFetch = (input: RequestInfo | URL, init: RequestInit = {}) =>
  fetch(input, { ...init, credentials: 'include' });

export default function JarvisNotes() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [editingNote, setEditingNote] = useState<Note | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newNote, setNewNote] = useState({ title: '', content: '', tags: '' });

  useEffect(() => {
    loadNotes();
  }, []);

  const loadNotes = async () => {
    try {
      const response = await sessionFetch(getApiUrl('/api/notes'), { headers: authHeaders() });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setNotes(data.notes);
    } catch (error) {
      console.error('Failed to load notes:', error);
    }
  };

  const createNote = async () => {
    try {
      const response = await sessionFetch(getApiUrl('/api/notes'), {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify(newNote)
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setNotes([data, ...notes]);
      setNewNote({ title: '', content: '', tags: '' });
      setIsCreating(false);
    } catch (error) {
      console.error('Failed to create note:', error);
    }
  };

  const updateNote = async () => {
    if (!editingNote) return;
    try {
      const response = await sessionFetch(getApiUrl(`/api/notes/${encodeURIComponent(editingNote.id)}`), {
        method: 'PATCH',
        headers: authHeaders(true),
        body: JSON.stringify(editingNote)
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setNotes(notes.map(note => note.id === data.id ? data : note));
      setEditingNote(null);
    } catch (error) {
      console.error('Failed to update note:', error);
    }
  };

  const deleteNote = async (id: string) => {
    try {
      await sessionFetch(getApiUrl(`/api/notes/${encodeURIComponent(id)}`), { method: 'DELETE', headers: authHeaders() });
      setNotes(notes.filter(note => note.id !== id));
    } catch (error) {
      console.error('Failed to delete note:', error);
    }
  };

  const filteredNotes = notes.filter(note =>
    note.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    note.content.toLowerCase().includes(searchTerm.toLowerCase()) ||
    note.tags.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-white">Notes</h1>
          <button
            onClick={() => setIsCreating(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
          >
            <Plus className="mr-2 w-5 h-5" />
            New Note
          </button>
        </div>

        <div className="mb-6">
          <div className="relative">
            <Search className="absolute left-3 top-3 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search notes..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-gray-800 text-white pl-10 pr-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
            />
          </div>
        </div>

        <AnimatePresence>
          {isCreating && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="mb-6 bg-gray-800 p-6 rounded-lg"
            >
              <input
                type="text"
                placeholder="Note title"
                value={newNote.title}
                onChange={(e) => setNewNote({ ...newNote, title: e.target.value })}
                className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
              <textarea
                placeholder="Note content"
                value={newNote.content}
                onChange={(e) => setNewNote({ ...newNote, content: e.target.value })}
                rows={4}
                className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
              <input
                type="text"
                placeholder="Tags (comma-separated)"
                value={newNote.tags}
                onChange={(e) => setNewNote({ ...newNote, tags: e.target.value })}
                className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
              <div className="flex gap-2">
                <button
                  onClick={createNote}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
                >
                  <Save className="mr-2 w-4 h-4" />
                  Save
                </button>
                <button
                  onClick={() => setIsCreating(false)}
                  className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg flex items-center"
                >
                  <X className="mr-2 w-4 h-4" />
                  Cancel
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredNotes.map((note) => (
            <motion.div
              key={note.id}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors"
            >
              {editingNote?.id === note.id ? (
                <div>
                  <input
                    type="text"
                    value={editingNote.title}
                    onChange={(e) => setEditingNote({ ...editingNote, title: e.target.value })}
                    className="w-full bg-gray-700 text-white px-3 py-2 rounded-lg mb-3 focus:outline-none focus:ring-2 focus:ring-blue-600"
                  />
                  <textarea
                    value={editingNote.content}
                    onChange={(e) => setEditingNote({ ...editingNote, content: e.target.value })}
                    rows={4}
                    className="w-full bg-gray-700 text-white px-3 py-2 rounded-lg mb-3 focus:outline-none focus:ring-2 focus:ring-blue-600"
                  />
                  <input
                    type="text"
                    value={editingNote.tags}
                    onChange={(e) => setEditingNote({ ...editingNote, tags: e.target.value })}
                    className="w-full bg-gray-700 text-white px-3 py-2 rounded-lg mb-3 focus:outline-none focus:ring-2 focus:ring-blue-600"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={updateNote}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded flex items-center text-sm"
                    >
                      <Save className="mr-1 w-3 h-3" />
                      Save
                    </button>
                    <button
                      onClick={() => setEditingNote(null)}
                      className="bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded flex items-center text-sm"
                    >
                      <X className="mr-1 w-3 h-3" />
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <h3 className="text-xl font-bold text-white mb-2">{note.title}</h3>
                  <p className="text-gray-300 mb-4 line-clamp-3">{note.content}</p>
                  {note.tags && (
                    <div className="flex flex-wrap gap-2 mb-4">
                      {note.tags.split(',').map((tag, index) => (
                        <span key={index} className="bg-purple-600 text-white text-xs px-2 py-1 rounded flex items-center">
                          <Tag className="w-3 h-3 mr-1" />
                          {tag.trim()}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="text-gray-500 text-sm mb-4">
                    {new Date(note.updated_at).toLocaleDateString()}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setEditingNote(note)}
                      className="bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded flex items-center text-sm"
                    >
                      <Edit className="mr-1 w-3 h-3" />
                      Edit
                    </button>
                    <button
                      onClick={() => deleteNote(note.id)}
                      className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded flex items-center text-sm"
                    >
                      <Trash2 className="mr-1 w-3 h-3" />
                      Delete
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          ))}
        </div>

        {filteredNotes.length === 0 && (
          <div className="text-center text-gray-400 py-12">
            <p>No notes found. Create your first note!</p>
          </div>
        )}
      </div>
    </div>
  );
}
