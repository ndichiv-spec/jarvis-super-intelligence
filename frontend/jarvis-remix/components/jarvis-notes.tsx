import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { StickyNote, Plus, Edit, Trash2, Save } from 'lucide-react';

interface Note {
  id: string;
  title: string;
  content: string;
  timestamp: Date;
  category: string;
}

export function JarvisNotes() {
  const [notes, setNotes] = useState<Note[]>([
    {
      id: '1',
      title: 'System Configuration',
      content: 'JARVIS AI system is running at optimal capacity. All neural networks operational.',
      timestamp: new Date(),
      category: 'System'
    },
    {
      id: '2',
      title: 'Development Notes',
      content: 'Implementing new features for enhanced user experience.',
      timestamp: new Date(),
      category: 'Development'
    }
  ]);
  
  const [newNote, setNewNote] = useState({ title: '', content: '', category: 'General' });
  const [isCreating, setIsCreating] = useState(false);

  const handleCreateNote = () => {
    if (newNote.title.trim() && newNote.content.trim()) {
      const note: Note = {
        id: Date.now().toString(),
        title: newNote.title,
        content: newNote.content,
        category: newNote.category,
        timestamp: new Date()
      };
      
      setNotes(prev => [note, ...prev]);
      setNewNote({ title: '', content: '', category: 'General' });
      setIsCreating(false);
    }
  };

  const handleDeleteNote = (id: string) => {
    setNotes(prev => prev.filter(note => note.id !== id));
  };

  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-xl">
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <StickyNote className="w-6 h-6 text-yellow-400" />
            <h2 className="text-xl font-semibold text-white">Notes</h2>
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
              placeholder="Note title..."
              value={newNote.title}
              onChange={(e) => setNewNote(prev => ({ ...prev, title: e.target.value }))}
              className="w-full bg-gray-600 text-white px-3 py-2 rounded mb-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <textarea
              placeholder="Note content..."
              value={newNote.content}
              onChange={(e) => setNewNote(prev => ({ ...prev, content: e.target.value }))}
              className="w-full bg-gray-600 text-white px-3 py-2 rounded mb-2 h-24 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <select
              value={newNote.category}
              onChange={(e) => setNewNote(prev => ({ ...prev, category: e.target.value }))}
              className="w-full bg-gray-600 text-white px-3 py-2 rounded mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="General">General</option>
              <option value="System">System</option>
              <option value="Development">Development</option>
              <option value="Ideas">Ideas</option>
            </select>
            <div className="flex space-x-2">
              <button
                onClick={handleCreateNote}
                className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded transition-colors flex items-center space-x-1"
              >
                <Save className="w-3 h-3" />
                <span>Save</span>
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
          {notes.map((note) => (
            <motion.div
              key={note.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="p-4 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-white">{note.title}</h3>
                <div className="flex space-x-1">
                  <button className="text-gray-400 hover:text-white transition-colors">
                    <Edit className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteNote(note.id)}
                    className="text-red-400 hover:text-red-300 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <p className="text-gray-300 text-sm mb-2">{note.content}</p>
              <div className="flex items-center justify-between">
                <span className="text-xs bg-gray-600 px-2 py-1 rounded text-gray-300">
                  {note.category}
                </span>
                <span className="text-xs text-gray-400">
                  {note.timestamp.toLocaleString()}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
