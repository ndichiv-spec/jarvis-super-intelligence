'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Edit, Trash2, Save, X, Check, Calendar, Clock, Bell } from 'lucide-react';
import { getApiUrl } from '@/lib/runtime-url';

interface Reminder {
  id: string;
  title: string;
  due_date: string;
  completed: number;
  tags: string;
  created_at: string;
  updated_at: string;
}

const authHeaders = (json = false): Record<string, string> => {
  return json ? { 'Content-Type': 'application/json' } : {};
};

const sessionFetch = (input: RequestInfo | URL, init: RequestInit = {}) =>
  fetch(input, { ...init, credentials: 'include' });

export default function JarvisReminders() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [editingReminder, setEditingReminder] = useState<Reminder | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newReminder, setNewReminder] = useState({ title: '', due_date: '', tags: '' });

  useEffect(() => {
    loadReminders();
  }, []);

  const loadReminders = async () => {
    try {
      const response = await sessionFetch(getApiUrl('/api/reminders'), { headers: authHeaders() });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setReminders(data.reminders);
    } catch (error) {
      console.error('Failed to load reminders:', error);
    }
  };

  const createReminder = async () => {
    try {
      const response = await sessionFetch(getApiUrl('/api/reminders'), {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify(newReminder)
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setReminders([...reminders, data].sort((a, b) => 
        new Date(a.due_date).getTime() - new Date(b.due_date).getTime()
      ));
      setNewReminder({ title: '', due_date: '', tags: '' });
      setIsCreating(false);
    } catch (error) {
      console.error('Failed to create reminder:', error);
    }
  };

  const updateReminder = async () => {
    if (!editingReminder) return;
    try {
      const response = await sessionFetch(getApiUrl(`/api/reminders/${encodeURIComponent(editingReminder.id)}`), {
        method: 'PATCH',
        headers: authHeaders(true),
        body: JSON.stringify(editingReminder)
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setReminders(reminders.map(reminder => reminder.id === data.id ? data : reminder).sort((a, b) => 
        new Date(a.due_date).getTime() - new Date(b.due_date).getTime()
      ));
      setEditingReminder(null);
    } catch (error) {
      console.error('Failed to update reminder:', error);
    }
  };

  const deleteReminder = async (id: string) => {
    try {
      await sessionFetch(getApiUrl(`/api/reminders/${encodeURIComponent(id)}`), { method: 'DELETE', headers: authHeaders() });
      setReminders(reminders.filter(reminder => reminder.id !== id));
    } catch (error) {
      console.error('Failed to delete reminder:', error);
    }
  };

  const completeReminder = async (id: string) => {
    try {
      const response = await sessionFetch(getApiUrl(`/api/reminders/${encodeURIComponent(id)}/complete`), {
        method: 'POST',
        headers: authHeaders()
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setReminders(reminders.map(reminder => reminder.id === data.id ? data : reminder));
    } catch (error) {
      console.error('Failed to complete reminder:', error);
    }
  };

  const isOverdue = (dueDate: string) => {
    return new Date(dueDate) < new Date();
  };

  const isToday = (dueDate: string) => {
    const today = new Date();
    const date = new Date(dueDate);
    return today.toDateString() === date.toDateString();
  };

  const upcomingReminders = reminders.filter(r => !r.completed);
  const completedReminders = reminders.filter(r => r.completed);

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-white">Reminders</h1>
          <button
            onClick={() => setIsCreating(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
          >
            <Plus className="mr-2 w-5 h-5" />
            New Reminder
          </button>
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
                placeholder="Reminder title"
                value={newReminder.title}
                onChange={(e) => setNewReminder({ ...newReminder, title: e.target.value })}
                className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
              <div className="mb-4">
                <label className="text-gray-400 text-sm mb-2 block">Due Date & Time</label>
                <input
                  type="datetime-local"
                  value={newReminder.due_date}
                  onChange={(e) => setNewReminder({ ...newReminder, due_date: e.target.value })}
                  className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
              </div>
              <input
                type="text"
                placeholder="Tags (comma-separated)"
                value={newReminder.tags}
                onChange={(e) => setNewReminder({ ...newReminder, tags: e.target.value })}
                className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
              <div className="flex gap-2">
                <button
                  onClick={createReminder}
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

        <div className="mb-8">
          <h2 className="text-xl font-bold text-white mb-4 flex items-center">
            <Bell className="mr-2 w-5 h-5" />
            Upcoming ({upcomingReminders.length})
          </h2>
          <div className="space-y-3">
            {upcomingReminders.map((reminder) => (
              <motion.div
                key={reminder.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                className={`p-4 rounded-lg ${
                  isOverdue(reminder.due_date) ? 'bg-red-900/50 border border-red-600' :
                  isToday(reminder.due_date) ? 'bg-yellow-900/50 border border-yellow-600' :
                  'bg-gray-800'
                }`}
              >
                {editingReminder?.id === reminder.id ? (
                  <div>
                    <input
                      type="text"
                      value={editingReminder.title}
                      onChange={(e) => setEditingReminder({ ...editingReminder, title: e.target.value })}
                      className="w-full bg-gray-700 text-white px-3 py-2 rounded-lg mb-3 focus:outline-none focus:ring-2 focus:ring-blue-600"
                    />
                    <input
                      type="datetime-local"
                      value={editingReminder.due_date}
                      onChange={(e) => setEditingReminder({ ...editingReminder, due_date: e.target.value })}
                      className="w-full bg-gray-700 text-white px-3 py-2 rounded-lg mb-3 focus:outline-none focus:ring-2 focus:ring-blue-600"
                    />
                    <input
                      type="text"
                      value={editingReminder.tags}
                      onChange={(e) => setEditingReminder({ ...editingReminder, tags: e.target.value })}
                      className="w-full bg-gray-700 text-white px-3 py-2 rounded-lg mb-3 focus:outline-none focus:ring-2 focus:ring-blue-600"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={updateReminder}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded flex items-center text-sm"
                      >
                        <Save className="mr-1 w-3 h-3" />
                        Save
                      </button>
                      <button
                        onClick={() => setEditingReminder(null)}
                        className="bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded flex items-center text-sm"
                      >
                        <X className="mr-1 w-3 h-3" />
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-white mb-1">{reminder.title}</h3>
                      <div className="flex items-center text-gray-400 text-sm mb-2">
                        <Calendar className="w-4 h-4 mr-1" />
                        {new Date(reminder.due_date).toLocaleString()}
                      </div>
                      {reminder.tags && (
                        <div className="flex flex-wrap gap-2">
                          {reminder.tags.split(',').map((tag, index) => (
                            <span key={index} className="bg-purple-600 text-white text-xs px-2 py-1 rounded">
                              {tag.trim()}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 ml-4">
                      <button
                        onClick={() => completeReminder(reminder.id)}
                        className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded flex items-center text-sm"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setEditingReminder(reminder)}
                        className="bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded flex items-center text-sm"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => deleteReminder(reminder.id)}
                        className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded flex items-center text-sm"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>

        {completedReminders.length > 0 && (
          <div>
            <h2 className="text-xl font-bold text-white mb-4 flex items-center">
              <Check className="mr-2 w-5 h-5" />
              Completed ({completedReminders.length})
            </h2>
            <div className="space-y-3">
              {completedReminders.map((reminder) => (
                <motion.div
                  key={reminder.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="p-4 rounded-lg bg-gray-800 opacity-60"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-white mb-1 line-through">{reminder.title}</h3>
                      <div className="flex items-center text-gray-400 text-sm">
                        <Calendar className="w-4 h-4 mr-1" />
                        {new Date(reminder.due_date).toLocaleString()}
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
                      <button
                        onClick={() => deleteReminder(reminder.id)}
                        className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded flex items-center text-sm"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        )}

        {upcomingReminders.length === 0 && completedReminders.length === 0 && (
          <div className="text-center text-gray-400 py-12">
            <p>No reminders. Create your first reminder!</p>
          </div>
        )}
      </div>
    </div>
  );
}
