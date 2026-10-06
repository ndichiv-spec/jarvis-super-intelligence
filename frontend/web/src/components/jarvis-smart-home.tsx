'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Home, Lightbulb, Thermometer, Lock, Tv, Fan, Droplets, 
  Power, PowerOff, Settings, Wifi, WifiOff, RefreshCw, Plus,
  ChevronRight, ChevronDown, Activity, Zap, Battery, Volume2
} from 'lucide-react';

interface SmartDevice {
  id: string;
  name: string;
  type: 'light' | 'thermostat' | 'lock' | 'tv' | 'fan' | 'sensor';
  status: 'on' | 'off';
  value?: number;
  unit?: string;
  icon: any;
  room: string;
  battery?: number;
}

const DEVICES: SmartDevice[] = [
  {
    id: '1',
    name: 'Living Room Light',
    type: 'light',
    status: 'on',
    value: 75,
    unit: '%',
    icon: Lightbulb,
    room: 'Living Room',
    battery: 100
  },
  {
    id: '2',
    name: 'Bedroom Thermostat',
    type: 'thermostat',
    status: 'on',
    value: 22,
    unit: '°C',
    icon: Thermometer,
    room: 'Bedroom',
    battery: 85
  },
  {
    id: '3',
    name: 'Front Door Lock',
    type: 'lock',
    status: 'off',
    icon: Lock,
    room: 'Entrance',
    battery: 92
  },
  {
    id: '4',
    name: 'Smart TV',
    type: 'tv',
    status: 'off',
    icon: Tv,
    room: 'Living Room',
    battery: 78
  },
  {
    id: '5',
    name: 'Ceiling Fan',
    type: 'fan',
    status: 'on',
    value: 3,
    unit: 'speed',
    icon: Fan,
    room: 'Bedroom',
    battery: 100
  },
  {
    id: '6',
    name: 'Water Sensor',
    type: 'sensor',
    status: 'on',
    value: 45,
    unit: '%',
    icon: Droplets,
    room: 'Bathroom',
    battery: 95
  }
];

const ROOMS = ['All Rooms', 'Living Room', 'Bedroom', 'Entrance', 'Bathroom', 'Kitchen'];

export default function JarvisSmartHome() {
  const [devices, setDevices] = useState<SmartDevice[]>(DEVICES);
  const [selectedRoom, setSelectedRoom] = useState('All Rooms');
  const [selectedDevice, setSelectedDevice] = useState<SmartDevice | null>(null);
  const [isOnline, setIsOnline] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => {
      setLastUpdate(new Date());
      // Simulate real-time updates
      setDevices(prev => prev.map(device => {
        if (device.type === 'sensor' && device.status === 'on') {
          return {
            ...device,
            value: Math.floor(Math.random() * 30) + 40
          };
        }
        return device;
      }));
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const toggleDevice = (deviceId: string) => {
    setDevices(prev => prev.map(device => {
      if (device.id === deviceId) {
        return {
          ...device,
          status: device.status === 'on' ? 'off' : 'on'
        };
      }
      return device;
    }));
  };

  const adjustValue = (deviceId: string, newValue: number) => {
    setDevices(prev => prev.map(device => {
      if (device.id === deviceId) {
        return {
          ...device,
          value: newValue
        };
      }
      return device;
    }));
  };

  const filteredDevices = selectedRoom === 'All Rooms' 
    ? devices 
    : devices.filter(d => d.room === selectedRoom);

  const onCount = devices.filter(d => d.status === 'on').length;
  const offCount = devices.filter(d => d.status === 'off').length;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl font-bold mb-2 flex items-center">
                <Home className="mr-3 w-10 h-10 text-blue-400" />
                Smart Home Control
              </h1>
              <p className="text-gray-400 flex items-center">
                {isOnline ? (
                  <>
                    <Wifi className="w-4 h-4 mr-2 text-green-400" />
                    Connected • Last update: {lastUpdate.toLocaleTimeString()}
                  </>
                ) : (
                  <>
                    <WifiOff className="w-4 h-4 mr-2 text-red-400" />
                    Disconnected
                  </>
                )}
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setIsOnline(!isOnline)}
              className={`px-4 py-2 rounded-lg ${isOnline ? 'bg-green-600' : 'bg-red-600'} hover:opacity-90`}
            >
              {isOnline ? <Power className="w-5 h-5" /> : <PowerOff className="w-5 h-5" />}
            </motion.button>
          </div>
        </motion.div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-gradient-to-br from-blue-600 to-blue-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{devices.length}</div>
            <div className="text-blue-200">Total Devices</div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1 }}
            className="bg-gradient-to-br from-green-600 to-green-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{onCount}</div>
            <div className="text-green-200">Active</div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2 }}
            className="bg-gradient-to-br from-gray-600 to-gray-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{offCount}</div>
            <div className="text-gray-200">Inactive</div>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="bg-gradient-to-br from-purple-600 to-purple-800 p-6 rounded-xl"
          >
            <div className="text-3xl font-bold">{ROOMS.length - 1}</div>
            <div className="text-purple-200">Rooms</div>
          </motion.div>
        </div>

        {/* Room Filter */}
        <div className="mb-6 flex flex-wrap gap-2">
          {ROOMS.map(room => (
            <motion.button
              key={room}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setSelectedRoom(room)}
              className={`px-4 py-2 rounded-lg ${
                selectedRoom === room 
                  ? 'bg-blue-600' 
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              {room}
            </motion.button>
          ))}
        </div>

        {/* Devices Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredDevices.map((device, index) => {
            const Icon = device.icon;
            return (
              <motion.div
                key={device.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                whileHover={{ scale: 1.03, y: -5 }}
                onClick={() => setSelectedDevice(device)}
                className="cursor-pointer"
              >
                <div className="relative">
                  <div className={`absolute inset-0 bg-gradient-to-r ${
                    device.status === 'on' 
                      ? 'from-blue-600 to-purple-600' 
                      : 'from-gray-600 to-gray-700'
                  } rounded-2xl blur-xl opacity-50`}></div>
                  <div className="relative bg-gray-900/80 backdrop-blur-xl p-6 rounded-2xl border border-gray-700/50">
                    <div className="flex items-start justify-between mb-4">
                      <div className={`w-14 h-14 bg-gradient-to-br ${
                        device.status === 'on' 
                          ? 'from-blue-600 to-purple-600' 
                          : 'from-gray-600 to-gray-700'
                      } rounded-xl flex items-center justify-center`}>
                        <Icon className={`w-7 h-7 ${device.status === 'on' ? 'text-white' : 'text-gray-400'}`} />
                      </div>
                      <div className="flex items-center space-x-2">
                        {device.battery && (
                          <div className="flex items-center text-xs text-gray-400">
                            <Battery className="w-3 h-3 mr-1" />
                            {device.battery}%
                          </div>
                        )}
                        <motion.button
                          whileTap={{ scale: 0.9 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleDevice(device.id);
                          }}
                          className={`p-2 rounded-lg ${
                            device.status === 'on' 
                              ? 'bg-green-600' 
                              : 'bg-gray-700'
                          }`}
                        >
                          {device.status === 'on' ? <Power className="w-4 h-4" /> : <PowerOff className="w-4 h-4" />}
                        </motion.button>
                      </div>
                    </div>
                    <h3 className="text-xl font-bold mb-1">{device.name}</h3>
                    <p className="text-gray-400 text-sm mb-3">{device.room}</p>
                    {device.value !== undefined && (
                      <div className="flex items-center justify-between">
                        <span className="text-2xl font-bold text-blue-400">
                          {device.value}{device.unit}
                        </span>
                        {device.type === 'light' && (
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={device.value}
                            onChange={(e) => {
                              e.stopPropagation();
                              adjustValue(device.id, parseInt(e.target.value));
                            }}
                            className="w-24"
                          />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Add Device Button */}
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="fixed bottom-8 right-8 w-16 h-16 bg-gradient-to-br from-blue-600 to-purple-600 rounded-full flex items-center justify-center shadow-2xl"
        >
          <Plus className="w-8 h-8" />
        </motion.button>

        {/* Device Detail Modal */}
        <AnimatePresence>
          {selectedDevice && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
              onClick={() => setSelectedDevice(null)}
            >
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                className="bg-gray-900 p-8 rounded-2xl max-w-2xl w-full border border-gray-700"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center">
                    <div className={`w-16 h-16 bg-gradient-to-br ${
                      selectedDevice.status === 'on' 
                        ? 'from-blue-600 to-purple-600' 
                        : 'from-gray-600 to-gray-700'
                    } rounded-xl flex items-center justify-center mr-4`}>
                      {React.createElement(selectedDevice.icon, { 
                        className: 'w-8 h-8',
                        ...(selectedDevice.status === 'off' && { className: 'w-8 h-8 text-gray-400' })
                      })}
                    </div>
                    <div>
                      <h2 className="text-2xl font-bold">{selectedDevice.name}</h2>
                      <p className="text-gray-400">{selectedDevice.room}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedDevice(null)}
                    className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
                  >
                    <Settings className="w-6 h-6" />
                  </button>
                </div>

                <div className="space-y-4">
                  <div className="bg-gray-800 p-4 rounded-xl">
                    <h3 className="font-semibold mb-2">Status</h3>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <div className={`w-3 h-3 rounded-full mr-2 ${
                          selectedDevice.status === 'on' 
                            ? 'bg-green-500 animate-pulse' 
                            : 'bg-gray-500'
                        }`}></div>
                        <span>{selectedDevice.status === 'on' ? 'Active' : 'Inactive'}</span>
                      </div>
                      <motion.button
                        whileTap={{ scale: 0.9 }}
                        onClick={() => toggleDevice(selectedDevice.id)}
                        className={`px-4 py-2 rounded-lg ${
                          selectedDevice.status === 'on' 
                            ? 'bg-red-600 hover:bg-red-700' 
                            : 'bg-green-600 hover:bg-green-700'
                        }`}
                      >
                        {selectedDevice.status === 'on' ? 'Turn Off' : 'Turn On'}
                      </motion.button>
                    </div>
                  </div>

                  {selectedDevice.value !== undefined && (
                    <div className="bg-gray-800 p-4 rounded-xl">
                      <h3 className="font-semibold mb-2">Value Control</h3>
                      <div className="flex items-center space-x-4">
                        <input
                          type="range"
                          min="0"
                          max={selectedDevice.type === 'thermostat' ? 30 : 100}
                          value={selectedDevice.value}
                          onChange={(e) => adjustValue(selectedDevice.id, parseInt(e.target.value))}
                          className="flex-1"
                        />
                        <span className="text-2xl font-bold text-blue-400">
                          {selectedDevice.value}{selectedDevice.unit}
                        </span>
                      </div>
                    </div>
                  )}

                  {selectedDevice.battery && (
                    <div className="bg-gray-800 p-4 rounded-xl">
                      <h3 className="font-semibold mb-2">Battery Level</h3>
                      <div className="flex items-center space-x-4">
                        <div className="flex-1 bg-gray-700 rounded-full h-2">
                          <div 
                            className={`h-2 rounded-full ${
                              selectedDevice.battery > 50 
                                ? 'bg-green-600' 
                                : selectedDevice.battery > 20 
                                  ? 'bg-yellow-600' 
                                  : 'bg-red-600'
                            }`}
                            style={{ width: `${selectedDevice.battery}%` }}
                          ></div>
                        </div>
                        <span className="text-blue-400">{selectedDevice.battery}%</span>
                      </div>
                    </div>
                  )}

                  <div className="bg-gray-800 p-4 rounded-xl">
                    <h3 className="font-semibold mb-2">Device Info</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <div className="text-gray-400">Type</div>
                        <div className="capitalize">{selectedDevice.type}</div>
                      </div>
                      <div>
                        <div className="text-gray-400">ID</div>
                        <div>{selectedDevice.id}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
