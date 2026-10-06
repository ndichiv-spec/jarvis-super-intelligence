import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Home, Lightbulb, Thermometer, Lock, Wifi, Power } from 'lucide-react';

interface Device {
  id: string;
  name: string;
  type: string;
  status: 'on' | 'off';
  icon: any;
}

export function JarvisSmartHome() {
  const [devices, setDevices] = useState<Device[]>([
    { id: '1', name: 'Living Room Lights', type: 'lighting', status: 'on', icon: Lightbulb },
    { id: '2', name: 'Smart Thermostat', type: 'climate', status: 'on', icon: Thermometer },
    { id: '3', name: 'Front Door Lock', type: 'security', status: 'off', icon: Lock },
    { id: '4', name: 'WiFi Network', type: 'network', status: 'on', icon: Wifi },
    { id: '5', name: 'Kitchen Power', type: 'power', status: 'on', icon: Power },
  ]);

  const toggleDevice = (id: string) => {
    setDevices(prev => prev.map(device =>
      device.id === id ? { ...device, status: device.status === 'on' ? 'off' : 'on' } : device
    ));
  };

  const getDeviceColor = (status: string) => {
    return status === 'on' ? 'bg-green-500' : 'bg-gray-500';
  };

  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-xl">
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center space-x-2">
          <Home className="w-6 h-6 text-blue-400" />
          <h2 className="text-xl font-semibold text-white">Smart Home</h2>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {devices.map((device) => (
            <motion.div
              key={device.id}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: parseInt(device.id) * 0.1 }}
              className="bg-gray-700 p-4 rounded-lg hover:bg-gray-600 transition-colors cursor-pointer"
              onClick={() => toggleDevice(device.id)}
            >
              <div className="flex items-center justify-between mb-3">
                <device.icon className={`w-6 h-6 ${device.status === 'on' ? 'text-blue-400' : 'text-gray-400'}`} />
                <div className={`w-3 h-3 rounded-full ${getDeviceColor(device.status)}`} />
              </div>
              <h3 className="font-medium text-white mb-1">{device.name}</h3>
              <p className="text-sm text-gray-400 capitalize">{device.type}</p>
              <div className="mt-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-400">Status</span>
                  <span className={device.status === 'on' ? 'text-green-400' : 'text-gray-400'}>
                    {device.status.toUpperCase()}
                  </span>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
        
        <div className="mt-6 p-4 bg-gray-700 rounded-lg">
          <h3 className="text-lg font-semibold text-white mb-3">Quick Actions</h3>
          <div className="grid grid-cols-2 gap-2">
            <button className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-2 rounded text-sm transition-colors">
              All Lights On
            </button>
            <button className="bg-gray-600 hover:bg-gray-500 text-white px-3 py-2 rounded text-sm transition-colors">
              All Lights Off
            </button>
            <button className="bg-green-500 hover:bg-green-600 text-white px-3 py-2 rounded text-sm transition-colors">
              Security Mode
            </button>
            <button className="bg-purple-500 hover:bg-purple-600 text-white px-3 py-2 rounded text-sm transition-colors">
              Away Mode
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
