import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Bell, Plus, Clock, Calendar, Check, X } from 'lucide-react';

interface Reminder {
  id: string;
  title: string;
  description: string;
  timestamp: Date;
  priority: 'low' | 'medium' | 'high';
  completed: boolean;
}

export function JarvisReminders() {
  const [reminders, setReminders] = useState<Reminder[]>([
    {
      id: '1',
      title: 'System Backup',
      description: 'Perform complete system backup and data verification',
      timestamp: new Date(Date.now() + 3600000),
      priority: 'high',
      completed: false
    },
    {
      id: '2',
      title: 'AI Model Update',
      description: 'Update neural network models with latest training data',
      timestamp: new Date(Date.now() + 7200000),
      priority: 'medium',
      completed: false
    }
  ]);
  
  const [newReminder, setNewReminder] = useState({
    title: '',
    description: '',
    priority: 'medium' as 'low' | 'medium' | 'high'
  });
  const [isCreating, setIsCreating] = useState(false);

  const handleCreateReminder = () => {
    if (newReminder.title.trim()) {
      const reminder: Reminder = {
        id: Date.now().toString(),
        title: newReminder.title,
        description: newReminder.description,
        timestamp: new Date(),
        priority: newReminder.priority,
        completed: false
      };
      
      setReminders(prev => [reminder, ...prev]);
      setNewReminder({ title: '', description: '', priority: 'medium' });
      setIsCreating(false);
    }
  };

  const handleToggleComplete = (id: string) => {
    setReminders(prev => prev.map(reminder =>
      reminder.id === id ? { ...reminder, completed: !reminder.completed } : reminder
    ));
  };

  const handleDeleteReminder = (id: string) => {
    setReminders(prev => prev.filter(reminder => reminder.id !== id));
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'bg-red-500';
      case 'medium': return 'bg-yellow-500';
      case 'low': return 'bg-green-500';
      default: return 'bg-gray-500';
    }
  };

  const formatTimeRemaining = (timestamp: Date) => {
    const now = new Date();
    const diff = timestamp.getTime() - now.getTime();
    const hours = Math.floor(diff / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m`;
    } else {
      return 'Now';
    }
  };

  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-xl">
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Bell className="w-6 h-6 text-red-400" />
            <h2 className="text-xl font-semibold text-white">Reminders</h2>
          </div>
          <button
            onClick={() => setIsCreating(true)}
            className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        {isCreating && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 p-4 bg-gray-700 rounded-lg"
          >
            <input
              type="text"
              placeholder="Reminder title..."
              value={newReminder.title}
              onChange={(e) => setNewReminder(prev => ({ ...prev, title: e.target.value }))}
              className="w-full bg-gray-600 text-white px-3 py-2 rounded mb-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <textarea
              placeholder="Description (optional)..."
              value={newReminder.description}
              onChange={(e) => setNewReminder(prev => ({ ...prev, description: e.target.value }))}
              className="w-full bg-gray-600 text-white px-3 py-2 rounded mb-2 h-16 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <select
              value={newReminder.priority}
              onChange={(e) => setNewReminder(prev => ({ ...prev, priority: e.target.value as 'low' | 'medium' | 'high' }))}
              className="w-full bg-gray-600 text-white px-3 py-2 rounded mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="low">Low Priority</option>
              <option value="medium">Medium Priority</option>
              <option value="high">High Priority</option>
            </select>
            <div className="flex space-x-2">
              <button
                onClick={handleCreateReminder}
                className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded transition-colors"
              >
                Create
              </button>
              <button
                onClick={() => setIsCreating(false)}
                className="bg-gray-500 hover:bg-gray-600 text-white px-3 py-1 rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        )}
        
        <div className="space-y-3">
          {reminders.map((reminder) => (
            <motion.div
              key={reminder.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className={`p-4 rounded-lg border transition-all ${
                reminder.completed 
                  ? 'bg-gray-700 border-gray-600 opacity-60' 
                  : 'bg-gray-700 border-gray-600 hover:border-gray-500'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-start space-x-3 flex-1">
                  <button
                    onClick={() => handleToggleComplete(reminder.id)}
                    className={`mt-1 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                      reminder.completed
                        ? 'bg-green-500 border-green-500'
                        : 'border-gray-400 hover:border-gray-300'
                    }`}
                  >
                    {reminder.completed && <Check className="w-3 h-3 text-white" />}
                  </button>
                  <div className="flex-1">
                    <h3 className={`font-semibold ${reminder.completed ? 'text-gray-400 line-through' : 'text-white'}`}>
                      {reminder.title}
                    </h3>
                    {reminder.description && (
                      <p className="text-gray-400 text-sm mt-1">{reminder.description}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <span className={`px-2 py-1 rounded text-xs text-white ${getPriorityColor(reminder.priority)}`}>
                    {reminder.priority}
                  </span>
                  <button
                    onClick={() => handleDeleteReminder(reminder.id)}
                    className="text-red-400 hover:text-red-300 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div className="flex items-center space-x-4 text-xs text-gray-400 ml-8">
                <div className="flex items-center space-x-1">
                  <Clock className="w-3 h-3" />
                  <span>{formatTimeRemaining(reminder.timestamp)}</span>
                </div>
                <div className="flex items-center space-x-1">
                  <Calendar className="w-3 h-3" />
                  <span>{reminder.timestamp.toLocaleDateString()}</span>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
