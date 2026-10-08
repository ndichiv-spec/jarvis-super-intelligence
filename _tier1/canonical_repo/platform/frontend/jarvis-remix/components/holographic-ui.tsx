import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform, useSpring, useAnimation } from 'framer-motion';
import { 
  Sparkles, Eye, EyeOff, Zap, Brain, Cpu, Activity, Layers, 
  Volume2, VolumeX, Mic, MicOff, Video, VideoOff, 
  Settings, Settings2, Maximize, Minimize, RotateCw, 
  Box, Package, PackageOpen, Archive,
  Monitor, MonitorSpeaker, Smartphone, Tablet, Watch,
  Camera, CameraOff, Scan, ScanLine, Fingerprint,
  Globe, Map, MapPin, Compass, Navigation, Navigation2,
  Radio, RadioTower, Tv,
  Wifi, WifiOff,
  Shield, ShieldCheck, ShieldX, ShieldAlert,
  Lock, LockOpen, LockKeyhole,
  Key, KeyRound,
  Battery, BatteryLow, BatteryMedium, BatteryFull, BatteryCharging,
  Power, PowerOff, PowerCircle, PowerSquare,
  Thermometer, ThermometerSun,
  Wind, Droplets, Cloud, CloudRain, CloudSnow, CloudLightning,
  Sun, Sunset, Sunrise, Moon, MoonStar,
  Star, StarHalf, StarOff,
  Heart, HeartHandshake, HeartPulse,
  ZapOff,
  Gauge, GaugeCircle,
  Timer, TimerReset, TimerOff,
  Clock, Clock1, Clock2, Clock3, Clock4, Clock5, Clock6, Clock7, Clock8, Clock9, Clock10, Clock11, Clock12,
  AlarmClock, AlarmClockOff,
  Calendar, CalendarDays, CalendarRange, CalendarCheck, CalendarX,
  Birthday, BirthdayCake,
  Gift, GiftOpen,
  Award, AwardOff,
  Trophy, TrophyOff,
  Medal, MedalOff,
  Alien, Ghost, Skull,
  Bot, BotOff,
  Robot, RobotOff,
  Android, AndroidOff,
  Apple, AppleOff,
  Windows, WindowsOff,
  Linux, LinuxOff,
  Chrome, ChromeOff,
  Firefox, FirefoxOff,
  Safari, SafariOff,
  Edge, EdgeOff,
  Opera, OperaOff,
  Brave, BraveOff,
  Tor, TorOff,
  Vpn, VpnOff,
  Router, RouterOff,
  Modem, ModemOff,
  Server, ServerOff,
  Database, DatabaseOff,
  HardDrive, HardDriveOff,
  MemoryStick, MemoryStickOff,
  FloppyDisk, FloppyDiskOff,
  Usb, UsbOff,
  SdCard, SdCardOff,
  SimCard, SimCardOff,
  Dvd, DvdOff,
  Disc, Disc2, Disc3,
  Play, PlayCircle, PlaySquare,
  Pause, PauseCircle, PauseSquare,
  Stop, StopCircle, StopSquare,
  SkipBack, SkipForward,
  Replay, Replay2,
  Shuffle, ShuffleOff,
  Repeat, RepeatOff,
  Repeat1, Repeat2,
  Volume, Volume1,
  VolumeOff,
  Speaker, SpeakerOff,
  Headphones, HeadphonesOff,
  Face, FaceSmile, FaceFrown, FaceMeh,
  Smile, SmilePlus, SmileMinus,
  Frown, FrownPlus, FrownMinus,
  Meh, MehPlus, MehMinus,
  Laugh, LaughPlus, LaughMinus,
  Angry, AngryPlus, AngryMinus,
  Dizzy, DizzyPlus, DizzyMinus,
  Sad, SadPlus, SadMinus,
  Surprised, SurprisedPlus, SurprisedMinus,
  Kiss, KissPlus, KissMinus,
  HeartPlus, HeartMinus,
  StarPlus, StarMinus,
  ThumbsUp, ThumbsDown,
  Hand, HandMetal, HandPeace, HandOk, HandHelp,
  Pointer, PointerOff,
  MousePointer, MousePointer2, MousePointerClick,
  Touch, TouchOff,
  Swipe, SwipeLeft, SwipeRight, SwipeUp, SwipeDown,
  Pin, PinOff,
  MapPinOff,
  NavigationOff,
  Compass2, CompassOff,
  Radar, RadarOff,
  Satellite, SatelliteOff,
  Globe2,
  Earth, EarthOff,
  Rocket, RocketOff,
  Plane, PlaneOff,
  Car, CarOff,
  Train, TrainOff,
  Ship, ShipOff,
  Bike, BikeOff,
  Bus, BusOff,
  Truck, TruckOff,
  Ambulance, AmbulanceOff,
  Helicopter, HelicopterOff,
  Anchor, AnchorOff,
  LifeBuoy,
  Flag, FlagOff,
  FlagTriangleLeft, FlagTriangleRight,
  FlagSquare, FlagSquareOff,
  FlagCircle, FlagCircleOff,
  FlagHexagon, FlagHexagonOff,
  FlagPentagon, FlagPentagonOff,
  FlagOctagon, FlagOctagonOff,
  FlagStar, FlagStarOff,
  FlagHeart, FlagHeartOff,
  FlagShield, FlagShieldOff,
  FlagSword, FlagSwordOff,
  FlagWand, FlagWandOff,
  FlagCrown, FlagCrownOff,
  FlagDiamond, FlagDiamondOff,
  FlagTriangle, FlagTriangleOff,
  FlagCircleDot, FlagCircleDotOff,
  FlagSquareDot, FlagSquareDotOff,
  FlagHexagonDot, FlagHexagonDotOff,
  FlagPentagonDot, FlagPentagonDotOff,
  FlagOctagonDot, FlagOctagonDotOff,
  FlagStarDot, FlagStarDotOff,
  FlagHeartDot, FlagHeartDotOff,
  FlagShieldDot, FlagShieldDotOff,
  FlagSwordDot, FlagSwordDotOff,
  FlagWandDot, FlagWandDotOff,
  FlagCrownDot, FlagCrownDotOff,
  FlagDiamondDot, FlagDiamondDotOff,
  FlagTriangleDot, FlagTriangleDotOff,
  FlagCirclePlus, FlagCirclePlusOff,
  FlagSquarePlus, FlagSquarePlusOff,
  FlagHexagonPlus, FlagHexagonPlusOff,
  FlagPentagonPlus, FlagPentagonPlusOff,
  FlagOctagonPlus, FlagOctagonPlusOff,
  FlagStarPlus, FlagStarPlusOff,
  FlagHeartPlus, FlagHeartPlusOff,
  FlagShieldPlus, FlagShieldPlusOff,
  FlagSwordPlus, FlagSwordPlusOff,
  FlagWandPlus, FlagWandPlusOff,
  FlagCrownPlus, FlagCrownPlusOff,
  FlagDiamondPlus, FlagDiamondPlusOff,
  FlagTrianglePlus, FlagTrianglePlusOff,
  FlagCircleMinus, FlagCircleMinusOff,
  FlagSquareMinus, FlagSquareMinusOff,
  FlagHexagonMinus, FlagHexagonMinusOff,
  FlagPentagonMinus, FlagPentagonMinusOff,
  FlagOctagonMinus, FlagOctagonMinusOff,
  FlagStarMinus, FlagStarMinusOff,
  FlagHeartMinus, FlagHeartMinusOff,
  FlagShieldMinus, FlagShieldMinusOff,
  FlagSwordMinus, FlagSwordMinusOff,
  FlagWandMinus, FlagWandMinusOff,
  FlagCrownMinus, FlagCrownMinusOff,
  FlagDiamondMinus, FlagDiamondMinusOff,
  FlagTriangleMinus, FlagTriangleMinusOff,
  FlagCircleX, FlagCircleXOff,
  FlagSquareX, FlagSquareXOff,
  FlagHexagonX, FlagHexagonXOff,
  FlagPentagonX, FlagPentagonXOff,
  FlagOctagonX, FlagOctagonXOff,
  FlagStarX, FlagStarXOff,
  FlagHeartX, FlagHeartXOff,
  FlagShieldX, FlagShieldXOff,
  FlagSwordX, FlagSwordXOff,
  FlagWandX, FlagWandXOff,
  FlagCrownX, FlagCrownXOff,
  FlagDiamondX, FlagDiamondXOff,
  FlagTriangleX, FlagTriangleXOff,
  FlagCircleCheck, FlagCircleCheckOff,
  FlagSquareCheck, FlagSquareCheckOff,
  FlagHexagonCheck, FlagHexagonCheckOff,
  FlagPentagonCheck, FlagPentagonCheckOff,
  FlagOctagonCheck, FlagOctagonCheckOff,
  FlagStarCheck, FlagStarCheckOff,
  FlagHeartCheck, FlagHeartCheckOff,
  FlagShieldCheck, FlagShieldCheckOff,
  FlagSwordCheck, FlagSwordCheckOff,
  FlagWandCheck, FlagWandCheckOff,
  FlagCrownCheck, FlagCrownCheckOff,
  FlagDiamondCheck, FlagDiamondCheckOff,
  FlagTriangleCheck, FlagTriangleCheckOff,
} from 'lucide-react';

interface HolographicLayer {
  id: string;
  name: string;
  type: '2d' | '3d' | 'ar' | 'vr' | 'mr';
  opacity: number;
  rotation: { x: number; y: number; z: number };
  scale: number;
  position: { x: number; y: number; z: number };
  visible: boolean;
  content: string;
}

interface HolographicEffect {
  id: string;
  name: string;
  type: 'glitch' | 'scanline' | 'particle' | 'wave' | 'distortion' | 'flicker';
  intensity: number;
  color: string;
  speed: number;
  active: boolean;
}

interface HolographicControl {
  id: string;
  name: string;
  type: 'slider' | 'toggle' | 'button' | 'select';
  value: any;
  min?: number;
  max?: number;
  options?: string[];
  icon: any;
}

export function HolographicUI() {
  const [layers, setLayers] = useState<HolographicLayer[]>([
    {
      id: '1',
      name: 'Base Layer',
      type: '3d',
      opacity: 1,
      rotation: { x: 0, y: 0, z: 0 },
      scale: 1,
      position: { x: 0, y: 0, z: 0 },
      visible: true,
      content: 'JARVIS Core Interface'
    },
    {
      id: '2',
      name: 'Data Overlay',
      type: 'ar',
      opacity: 0.8,
      rotation: { x: 0, y: 0, z: 0 },
      scale: 1,
      position: { x: 0, y: 0, z: 0 },
      visible: true,
      content: 'Real-time Data Stream'
    },
    {
      id: '3',
      name: 'Neural Network',
      type: '3d',
      opacity: 0.6,
      rotation: { x: 0, y: 0, z: 0 },
      scale: 1,
      position: { x: 0, y: 0, z: 0 },
      visible: false,
      content: 'Neural Pathways'
    }
  ]);

  const [effects, setEffects] = useState<HolographicEffect[]>([
    {
      id: '1',
      name: 'Scanline Effect',
      type: 'scanline',
      intensity: 0.3,
      color: '#00ffff',
      speed: 1,
      active: true
    },
    {
      id: '2',
      name: 'Glitch Effect',
      type: 'glitch',
      intensity: 0.1,
      color: '#ff00ff',
      speed: 2,
      active: false
    },
    {
      id: '3',
      name: 'Particle Effect',
      type: 'particle',
      intensity: 0.5,
      color: '#00ff00',
      speed: 0.5,
      active: true
    }
  ]);

  const [controls, setControls] = useState<HolographicControl[]>([
    {
      id: '1',
      name: 'Brightness',
      type: 'slider',
      value: 0.8,
      min: 0,
      max: 1,
      icon: Sun
    },
    {
      id: '2',
      name: 'Contrast',
      type: 'slider',
      value: 0.7,
      min: 0,
      max: 1,
      icon: Zap
    },
    {
      id: '3',
      name: 'Saturation',
      type: 'slider',
      value: 0.9,
      min: 0,
      max: 1,
      icon: Droplets
    },
    {
      id: '4',
      name: 'Holographic Mode',
      type: 'toggle',
      value: true,
      icon: Eye
    },
    {
      id: '5',
      name: 'Auto-Rotate',
      type: 'toggle',
      value: false,
      icon: RotateCw
    }
  ]);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [gestureEnabled, setGestureEnabled] = useState(true);
  const [depth, setDepth] = useState(50);
  const [perspective, setPerspective] = useState(1000);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hologramCanvasRef = useRef<HTMLCanvasElement>(null);
  const effectCanvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const rotateX = useTransform(mouseY, [0, 400], [10, -10]);
  const rotateY = useTransform(mouseX, [0, 400], [-10, 10]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const drawHologram = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Draw holographic grid
      ctx.strokeStyle = 'rgba(0, 255, 255, 0.3)';
      ctx.lineWidth = 1;
      
      for (let x = 0; x < canvas.width; x += 20) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      
      for (let y = 0; y < canvas.height; y += 20) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      // Draw holographic layers
      layers.filter(layer => layer.visible).forEach((layer, index) => {
        ctx.save();
        ctx.globalAlpha = layer.opacity;
        
        const centerX = canvas.width / 2 + layer.position.x;
        const centerY = canvas.height / 2 + layer.position.y;
        
        ctx.translate(centerX, centerY);
        ctx.rotate(layer.rotation.z * Math.PI / 180);
        ctx.scale(layer.scale, layer.scale);
        
        // Draw layer content
        ctx.fillStyle = `hsl(${180 + index * 60}, 70%, 50%)`;
        ctx.fillRect(-100, -50, 200, 100);
        
        ctx.fillStyle = '#ffffff';
        ctx.font = '14px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(layer.content, 0, 0);
        
        ctx.restore();
      });
    };

    drawHologram();
    animationRef.current = requestAnimationFrame(drawHologram);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [layers]);

  useEffect(() => {
    const canvas = hologramCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw3DHologram = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Create 3D effect with perspective
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      
      // Draw 3D cube wireframe
      const size = 100;
      const depth = 50;
      
      ctx.strokeStyle = 'rgba(0, 255, 255, 0.8)';
      ctx.lineWidth = 2;
      
      // Front face
      ctx.strokeRect(centerX - size/2, centerY - size/2, size, size);
      
      // Back face
      ctx.strokeRect(centerX - size/2 + depth, centerY - size/2 + depth, size, size);
      
      // Connecting lines
      ctx.beginPath();
      ctx.moveTo(centerX - size/2, centerY - size/2);
      ctx.lineTo(centerX - size/2 + depth, centerY - size/2 + depth);
      ctx.moveTo(centerX + size/2, centerY - size/2);
      ctx.lineTo(centerX + size/2 + depth, centerY - size/2 + depth);
      ctx.moveTo(centerX - size/2, centerY + size/2);
      ctx.lineTo(centerX - size/2 + depth, centerY + size/2 + depth);
      ctx.moveTo(centerX + size/2, centerY + size/2);
      ctx.lineTo(centerX + size/2 + depth, centerY + size/2 + depth);
      ctx.stroke();
      
      // Add glow effect
      ctx.shadowBlur = 20;
      ctx.shadowColor = '#00ffff';
      ctx.stroke();
    };

    const interval = setInterval(draw3DHologram, 50);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const canvas = effectCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const drawEffects = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      effects.filter(effect => effect.active).forEach(effect => {
        switch (effect.type) {
          case 'scanline':
            for (let y = 0; y < canvas.height; y += 4) {
              ctx.fillStyle = `${effect.color}${Math.floor(effect.intensity * 255).toString(16).padStart(2, '0')}`;
              ctx.fillRect(0, y, canvas.width, 2);
            }
            break;
            
          case 'particle':
            for (let i = 0; i < 50; i++) {
              const x = Math.random() * canvas.width;
              const y = Math.random() * canvas.height;
              const size = Math.random() * 3 + 1;
              
              ctx.fillStyle = `${effect.color}${Math.floor(effect.intensity * 255).toString(16).padStart(2, '0')}`;
              ctx.beginPath();
              ctx.arc(x, y, size, 0, Math.PI * 2);
              ctx.fill();
            }
            break;
            
          case 'glitch':
            for (let i = 0; i < 5; i++) {
              const x = Math.random() * canvas.width;
              const y = Math.random() * canvas.height;
              const width = Math.random() * 100 + 50;
              const height = Math.random() * 10 + 5;
              
              ctx.fillStyle = `${effect.color}${Math.floor(effect.intensity * 255).toString(16).padStart(2, '0')}`;
              ctx.fillRect(x, y, width, height);
            }
            break;
        }
      });
    };

    const interval = setInterval(drawEffects, 100);
    return () => clearInterval(interval);
  }, [effects]);

  const toggleLayer = (layerId: string) => {
    setLayers(prev => prev.map(layer => 
      layer.id === layerId ? { ...layer, visible: !layer.visible } : layer
    ));
  };

  const toggleEffect = (effectId: string) => {
    setEffects(prev => prev.map(effect => 
      effect.id === effectId ? { ...effect, active: !effect.active } : effect
    ));
  };

  const updateControl = (controlId: string, value: any) => {
    setControls(prev => prev.map(control => 
      control.id === controlId ? { ...control, value } : control
    ));
  };

  const rotateLayer = (layerId: string, axis: 'x' | 'y' | 'z', value: number) => {
    setLayers(prev => prev.map(layer => 
      layer.id === layerId ? { 
        ...layer, 
        rotation: { ...layer.rotation, [axis]: value }
      } : layer
    ));
  };

  return (
    <div className="min-h-screen bg-black text-white relative overflow-hidden">
      {/* Holographic Background */}
      <div className="absolute inset-0">
        <canvas
          ref={canvasRef}
          width={typeof window !== 'undefined' ? window.innerWidth : 1920}
          height={typeof window !== 'undefined' ? window.innerHeight : 1080}
          className="absolute inset-0"
        />
        <canvas
          ref={hologramCanvasRef}
          width={typeof window !== 'undefined' ? window.innerWidth : 1920}
          height={typeof window !== 'undefined' ? window.innerHeight : 1080}
          className="absolute inset-0"
        />
        <canvas
          ref={effectCanvasRef}
          width={typeof window !== 'undefined' ? window.innerWidth : 1920}
          height={typeof window !== 'undefined' ? window.innerHeight : 1080}
          className="absolute inset-0"
        />
      </div>

      {/* Main Content */}
      <div className="relative z-10 flex">
        {/* Holographic Control Panel */}
        <motion.div
          style={{ rotateX, rotateY }}
          className="w-80 bg-gradient-to-b from-cyan-900/20 to-blue-900/20 backdrop-blur-xl border-r border-cyan-500/30 p-6"
        >
          <div className="mb-8">
            <motion.h1 
              className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent flex items-center"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 200 }}
            >
              <Sparkles className="w-10 h-10 mr-3 text-cyan-400" />
              Holographic UI
            </motion.h1>
            <p className="text-gray-400 text-sm mt-2">Advanced 3D Interface Control</p>
          </div>

          {/* Status Indicators */}
          <div className="mb-6 space-y-3">
            <div className="flex items-center justify-between bg-black/30 p-3 rounded-lg">
              <span className="text-sm text-gray-400">Holographic Mode</span>
              <div className={`w-3 h-3 rounded-full ${controls.find(c => c.name === 'Holographic Mode')?.value ? 'bg-cyan-400 animate-pulse' : 'bg-gray-400'}`} />
            </div>
            <div className="flex items-center justify-between bg-black/30 p-3 rounded-lg">
              <span className="text-sm text-gray-400">Gesture Control</span>
              <div className={`w-3 h-3 rounded-full ${gestureEnabled ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`} />
            </div>
            <div className="flex items-center justify-between bg-black/30 p-3 rounded-lg">
              <span className="text-sm text-gray-400">Voice Interface</span>
              <div className={`w-3 h-3 rounded-full ${voiceEnabled ? 'bg-purple-400 animate-pulse' : 'bg-gray-400'}`} />
            </div>
            <div className="flex items-center justify-between bg-black/30 p-3 rounded-lg">
              <span className="text-sm text-gray-400">Recording</span>
              <div className={`w-3 h-3 rounded-full ${isRecording ? 'bg-red-400 animate-pulse' : 'bg-gray-400'}`} />
            </div>
          </div>

          {/* Layer Controls */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-white mb-3">Holographic Layers</h3>
            <div className="space-y-2">
              {layers.map((layer) => (
                <div key={layer.id} className="bg-black/30 p-3 rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-white text-sm">{layer.name}</span>
                    <button
                      onClick={() => toggleLayer(layer.id)}
                      className={`p-1 rounded ${layer.visible ? 'bg-cyan-600' : 'bg-gray-600'}`}
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="text-xs text-gray-400 mb-2">
                    Type: {layer.type} | Opacity: {(layer.opacity * 100).toFixed(0)}%
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-gray-400 w-8">X:</span>
                      <input
                        type="range"
                        min="-180"
                        max="180"
                        value={layer.rotation.x}
                        onChange={(e) => rotateLayer(layer.id, 'x', parseFloat(e.target.value))}
                        className="flex-1"
                      />
                      <span className="text-xs text-cyan-400 w-8">{layer.rotation.x}°</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-gray-400 w-8">Y:</span>
                      <input
                        type="range"
                        min="-180"
                        max="180"
                        value={layer.rotation.y}
                        onChange={(e) => rotateLayer(layer.id, 'y', parseFloat(e.target.value))}
                        className="flex-1"
                      />
                      <span className="text-xs text-cyan-400 w-8">{layer.rotation.y}°</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-gray-400 w-8">Z:</span>
                      <input
                        type="range"
                        min="-180"
                        max="180"
                        value={layer.rotation.z}
                        onChange={(e) => rotateLayer(layer.id, 'z', parseFloat(e.target.value))}
                        className="flex-1"
                      />
                      <span className="text-xs text-cyan-400 w-8">{layer.rotation.z}°</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Effect Controls */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-white mb-3">Visual Effects</h3>
            <div className="space-y-2">
              {effects.map((effect) => (
                <div key={effect.id} className="bg-black/30 p-3 rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-white text-sm">{effect.name}</span>
                    <button
                      onClick={() => toggleEffect(effect.id)}
                      className={`p-1 rounded ${effect.active ? 'bg-purple-600' : 'bg-gray-600'}`}
                    >
                      <Sparkles className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs text-gray-400">Intensity:</span>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.1"
                      value={effect.intensity}
                      onChange={(e) => setEffects(prev => prev.map(e => 
                        e.id === effect.id ? { ...e, intensity: parseFloat(e.target.value) } : e
                      ))}
                      className="flex-1"
                    />
                    <span className="text-xs text-purple-400">{(effect.intensity * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="space-y-3">
            <motion.button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-lg bg-cyan-600 hover:bg-cyan-700"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {isFullscreen ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
              <span>{isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}</span>
            </motion.button>
            
            <motion.button
              onClick={() => setIsRecording(!isRecording)}
              className={`w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-lg ${
                isRecording ? 'bg-red-600 hover:bg-red-700' : 'bg-gray-700 hover:bg-gray-600'
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Video className="w-5 h-5" />
              <span>{isRecording ? 'Stop Recording' : 'Start Recording'}</span>
            </motion.button>
            
            <motion.button
              onClick={() => setVoiceEnabled(!voiceEnabled)}
              className={`w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-lg ${
                voiceEnabled ? 'bg-purple-600 hover:bg-purple-700' : 'bg-gray-700 hover:bg-gray-600'
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {voiceEnabled ? <Mic className="w-5 h-5" /> : <MicOff className="w-5 h-5" />}
              <span>{voiceEnabled ? 'Voice Active' : 'Enable Voice'}</span>
            </motion.button>
          </div>
        </motion.div>

        {/* Holographic Display Area */}
        <div className="flex-1 flex items-center justify-center">
          <motion.div
            className="relative"
            style={{ 
              perspective: `${perspective}px`,
              transformStyle: 'preserve-3d'
            }}
          >
            <motion.div
              className="w-96 h-96 relative"
              style={{
                transform: `rotateX(${rotateX.get()}deg) rotateY(${rotateY.get()}deg)`,
                transformStyle: 'preserve-3d'
              }}
            >
              {/* Central Holographic Display */}
              <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/20 to-blue-500/20 rounded-2xl border border-cyan-400/50 backdrop-blur-lg flex items-center justify-center">
                <div className="text-center">
                  <Sparkles className="w-16 h-16 text-cyan-400 mx-auto mb-4 animate-pulse" />
                  <h2 className="text-2xl font-bold text-white mb-2">Holographic Interface</h2>
                  <p className="text-gray-400">Advanced 3D Visualization</p>
                </div>
              </div>
              
              {/* Floating Elements */}
              <motion.div
                className="absolute -top-10 -left-10 w-20 h-20 bg-purple-500/30 rounded-full border border-purple-400/50"
                animate={{
                  y: [0, -10, 0],
                  rotate: [0, 180, 360]
                }}
                transition={{
                  duration: 4,
                  repeat: Infinity,
                  ease: "easeInOut"
                }}
              />
              
              <motion.div
                className="absolute -top-10 -right-10 w-16 h-16 bg-green-500/30 rounded-full border border-green-400/50"
                animate={{
                  x: [0, 10, 0],
                  rotate: [0, -180, -360]
                }}
                transition={{
                  duration: 3,
                  repeat: Infinity,
                  ease: "easeInOut"
                }}
              />
              
              <motion.div
                className="absolute -bottom-10 -left-10 w-24 h-24 bg-blue-500/30 rounded-full border border-blue-400/50"
                animate={{
                  y: [0, 10, 0],
                  scale: [1, 1.1, 1]
                }}
                transition={{
                  duration: 5,
                  repeat: Infinity,
                  ease: "easeInOut"
                }}
              />
              
              <motion.div
                className="absolute -bottom-10 -right-10 w-12 h-12 bg-red-500/30 rounded-full border border-red-400/50"
                animate={{
                  x: [0, -10, 0],
                  y: [0, -5, 0]
                }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  ease: "easeInOut"
                }}
              />
            </motion.div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
