import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, StyleSheet, Alert, SafeAreaView, StatusBar, Modal } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import * as Speech from 'expo-speech';
import * as Audio from 'expo-av';
import * as LocalAuthentication from 'expo-local-authentication';
import axios from 'axios';

// Request interceptor: attach JWT bearer token to all requests
axios.interceptors.request.use(
  async (config) => {
    const token = await AsyncStorage.getItem('jarvis_token');
    if (token && token !== 'demo') {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: handle 401 gracefully
axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token expired — clear auth
      await AsyncStorage.removeItem('jarvis_token');
      await AsyncStorage.removeItem('jarvis_refresh_token');
    }
    return Promise.reject(error);
  }
);

const CONFIGURED_API_URL = process.env.EXPO_PUBLIC_JARVIS_API_URL?.trim();
if (!CONFIGURED_API_URL && !__DEV__) {
  throw new Error('Set EXPO_PUBLIC_JARVIS_API_URL to the deployed JARVIS Core URL.');
}
const API_URL = CONFIGURED_API_URL || 'http://localhost:8000';
const API_BASE = `${API_URL}/api/v1`;
const CHAT_API = `${API_URL}/api`;

const Stack = createNativeStackNavigator();

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface Agent {
  id: string;
  name: string;
  role: string;
  status: 'active' | 'idle' | 'error';
  capabilities: string[];
}

function LoginScreen({ navigation }: any) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [biometricEnabled, setBiometricEnabled] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    checkBiometric();
    loadSavedCredentials();
  }, []);

  const checkBiometric = async () => {
    const compatible = await LocalAuthentication.hasHardwareAsync();
    const enrolled = await LocalAuthentication.isEnrolledAsync();
    setBiometricEnabled(compatible && enrolled);
  };

  const loadSavedCredentials = async () => {
    try {
      const savedUsername = await AsyncStorage.getItem('jarvis_username');
      if (savedUsername) setUsername(savedUsername);
    } catch (e) {}
  };

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      Alert.alert('Error', 'Please enter username and password');
      return;
    }
    setLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/auth/login`, {
        identifier: username,
        password,
      });
      if (response.data.access_token && response.data.user?.id) {
        const token = response.data.access_token;
        await AsyncStorage.setItem('jarvis_token', token);
        if (response.data.refresh_token) {
          await AsyncStorage.setItem('jarvis_refresh_token', response.data.refresh_token);
        }
        await AsyncStorage.setItem('jarvis_username', username);
        await AsyncStorage.setItem('jarvis_user_id', response.data.user.id);
        navigation.replace('Chat');
      } else {
        Alert.alert('Login Error', 'The server returned an incomplete login response.');
      }
    } catch (error: any) {
      if (error.response?.status === 401) {
        Alert.alert('Login Failed', 'The username or password is incorrect.');
      } else {
        Alert.alert('Connection Error', 'JARVIS could not authenticate. Check the API address and try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleBiometricLogin = async () => {
    try {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Authenticate to access JARVIS',
      });
      if (result.success) {
        const token = await AsyncStorage.getItem('jarvis_token');
        if (token && token !== 'demo') {
          navigation.replace('Chat');
        }
      }
    } catch (e) {
      Alert.alert('Error', 'Biometric authentication failed');
    }
  };

  return (
    <SafeAreaView style={styles.loginContainer}>
      <StatusBar barStyle="light-content" />
      <View style={styles.loginContent}>
        <Text style={styles.loginLogo}>J</Text>
        <Text style={styles.loginTitle}>JARVIS</Text>
        <Text style={styles.loginSubtitle}>Intelligent Assistant</Text>

        <View style={styles.loginForm}>
          <TextInput
            style={styles.loginInput}
            value={username}
            onChangeText={setUsername}
            placeholder="Username"
            placeholderTextColor="#4a6"
            autoCapitalize="none"
          />
          <View style={styles.passwordContainer}>
            <TextInput
              style={[styles.loginInput, styles.passwordInput]}
              value={password}
              onChangeText={setPassword}
              placeholder="Password"
              placeholderTextColor="#4a6"
              secureTextEntry={!showPassword}
            />
            <TouchableOpacity style={styles.showPasswordBtn} onPress={() => setShowPassword(!showPassword)}>
              <Text style={styles.showPasswordText}>{showPassword ? '🙈' : '👁️'}</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={[styles.loginButton, loading && styles.loginButtonDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#000" />
            ) : (
              <Text style={styles.loginButtonText}>ACCESS JARVIS</Text>
            )}
          </TouchableOpacity>

          {biometricEnabled && (
            <TouchableOpacity style={styles.biometricButton} onPress={handleBiometricLogin}>
              <Text style={styles.biometricText}>Use Biometric Auth</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}

function ChatScreen({ navigation }: any) {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [userId, setUserId] = useState('');

  useEffect(() => {
    loadUser();
  }, []);

  const loadUser = async () => {
    const uid = await AsyncStorage.getItem('jarvis_user_id');
    if (uid) setUserId(uid);
  };

  const sendMessage = async () => {
    if (!message.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setMessage('');
    setLoading(true);

    try {
      const response = await axios.post(`${CHAT_API}/chat`, { message: userMessage.content });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.data.response || response.data.message || 'I am ready, sir.',
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error: any) {
      const fallbackMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Systems online. How may I assist you?',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, fallbackMsg]);
    } finally {
      setLoading(false);
    }
  };

  const speakResponse = async (text: string) => {
    setSpeaking(true);
    Speech.stop();
    Speech.speak(text, {
      language: 'en-US',
      pitch: 1.0,
      rate: 0.9,
      onDone: () => setSpeaking(false),
      onError: () => setSpeaking(false),
    });
  };

  const clearChat = () => {
    setMessages([]);
  };

  const logout = async () => {
    const refreshToken = await AsyncStorage.getItem('jarvis_refresh_token');
    let serverRevoked = true;
    try {
      await axios.post(`${API_BASE}/auth/logout`, { refresh_token: refreshToken });
    } catch {
      serverRevoked = false;
    }
    await AsyncStorage.clear();
    if (!serverRevoked) {
      Alert.alert('Signed out locally', 'The server could not be reached to revoke this session.');
    }
    navigation.replace('Login');
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" />
      <View style={styles.header}>
        <Text style={styles.headerTitle}>JARVIS</Text>
        <View style={styles.headerButtons}>
          <TouchableOpacity onPress={clearChat}>
            <Text style={styles.headerButton}>Clear</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={logout} style={styles.logoutButton}>
            <Text style={styles.logoutText}>Logout</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView style={styles.chatContainer} contentContainerStyle={styles.chatContent}>
        {messages.map((msg) => (
          <View key={msg.id} style={[styles.messageBubble, msg.role === 'user' ? styles.userBubble : styles.assistantBubble]}>
            <Text style={styles.messageText}>{msg.content}</Text>
            {!speaking && msg.role === 'assistant' && (
              <TouchableOpacity onPress={() => speakResponse(msg.content)} style={styles.speakButton}>
                <Text style={styles.speakButtonText}>🔊</Text>
              </TouchableOpacity>
            )}
          </View>
        ))}
        {loading && (
          <View style={[styles.messageBubble, styles.assistantBubble]}>
            <ActivityIndicator size="small" color="#00ff00" />
          </View>
        )}
      </ScrollView>

      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={message}
          onChangeText={setMessage}
          placeholder="Ask JARVIS..."
          placeholderTextColor="#4a6"
          multiline
          onSubmitEditing={sendMessage}
        />
        <TouchableOpacity onPress={sendMessage} style={[styles.sendButton, loading && styles.sendButtonDisabled]} disabled={loading}>
          <Text style={styles.sendButtonText}>➤</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

function VoiceScreen({ navigation }: any) {
  const [listening, setListening] = useState(false);
  const [transcribedText, setTranscribedText] = useState('');
  const [responseText, setResponseText] = useState('');

  const listenAndRespond = async () => {
    setListening(true);
    setTranscribedText('');
    setResponseText('');

    try {
      const result = await axios.post(`${API_BASE}/voice/listen`, {
        timeout: 5,
        phrase_time_limit: 10,
      });

      if (result.data.recognized && result.data.transcript) {
        setTranscribedText(result.data.transcript);

        const aiResponse = await axios.post(`${CHAT_API}/chat`, {
          message: result.data.transcript,
        });

        const response = aiResponse.data.reply || aiResponse.data.message;
        setResponseText(response);

        Speech.speak(response, { language: 'en-US', rate: 0.9 });
      } else {
        setTranscribedText(result.data.note || 'Speech recognition is not configured on this server.');
      }
    } catch (error: any) {
      setTranscribedText('Voice recognition is currently unavailable.');
    } finally {
      setListening(false);
    }
  };

  const speakText = async () => {
    if (!responseText) return;
    Speech.speak(responseText, { language: 'en-US', rate: 0.9 });
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Voice Control</Text>
      </View>

      <View style={styles.content}>
        <TouchableOpacity
          style={[styles.voiceButton, listening && styles.voiceButtonActive]}
          onPress={listenAndRespond}
          disabled={listening}
        >
          <Text style={styles.voiceButtonText}>{listening ? 'Listening...' : '🎤 Hold to Talk'}</Text>
        </TouchableOpacity>

        {transcribedText ? (
          <View style={styles.resultCard}>
            <Text style={styles.resultLabel}>You said:</Text>
            <Text style={styles.resultText}>{transcribedText}</Text>
          </View>
        ) : null}

        {responseText ? (
          <View style={styles.resultCard}>
            <Text style={styles.resultLabel}>JARVIS:</Text>
            <Text style={styles.resultText}>{responseText}</Text>
            <TouchableOpacity onPress={speakText} style={styles.resultSpeakBtn}>
              <Text style={styles.resultSpeakText}>🔊 Play</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

function AgentsScreen({ navigation }: any) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);

  const fetchAgents = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE}/agents`);
      if (response.data.agents) {
        setAgents(response.data.agents);
      }
    } catch {
      Alert.alert('Agents Unavailable', 'JARVIS could not load the live agent registry.');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return '#00ff00';
      case 'idle': return '#ffaa00';
      case 'error': return '#ff4444';
      default: return '#888';
    }
  };

  const getAgentIcon = (role: string) => {
    switch (role) {
      case 'coding': return '💻';
      case 'research': return '🔍';
      case 'data': return '📊';
      case 'file': return '📁';
      default: return '🤖';
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Agents</Text>
        <TouchableOpacity onPress={fetchAgents}>
          <Text style={styles.headerButton}>Refresh</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.agentsContainer} contentContainerStyle={styles.agentsContent}>
        {loading && <ActivityIndicator size="small" color="#00ff00" style={styles.loader} />}

        {agents.map((agent) => (
          <TouchableOpacity
            key={agent.id}
            style={[styles.agentCard, agent.status === 'active' && styles.agentCardActive]}
            onPress={() => setSelectedAgent(agent)}
          >
            <View style={styles.agentIconContainer}>
              <Text style={styles.agentIcon}>{getAgentIcon(agent.role)}</Text>
            </View>
            <View style={styles.agentInfo}>
              <Text style={styles.agentName}>{agent.name}</Text>
              <Text style={styles.agentDescription}>
                {agent.role} · {(agent.capabilities || []).join(', ')}
              </Text>
            </View>
            <View style={[styles.agentStatus, { backgroundColor: getStatusColor(agent.status) }]}>
              <Text style={styles.agentStatusText}>{agent.status.toUpperCase()}</Text>
            </View>
          </TouchableOpacity>
        ))}

        <Text style={styles.agentHint}>Status and capabilities are read from the live agent registry.</Text>
      </ScrollView>

      <Modal visible={!!selectedAgent} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            {selectedAgent && (
              <>
                <Text style={styles.modalTitle}>{selectedAgent.name}</Text>
                <Text style={styles.modalDescription}>
                  {selectedAgent.role} · {(selectedAgent.capabilities || []).join(', ')}
                </Text>
                <View style={styles.modalStatusRow}>
                  <Text style={styles.modalLabel}>Status:</Text>
                  <Text style={[styles.modalStatus, { color: getStatusColor(selectedAgent.status) }]}>
                    {selectedAgent.status.toUpperCase()}
                  </Text>
                </View>
                <TouchableOpacity style={styles.modalCloseBtn} onPress={() => setSelectedAgent(null)}>
                  <Text style={styles.modalCloseText}>Close</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function SettingsScreen({ navigation }: any) {
  const [apiUrl, setApiUrl] = useState(API_URL);
  const [voiceRate, setVoiceRate] = useState('0.9');
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [offlineMode, setOfflineMode] = useState(false);
  const [userId, setUserId] = useState('');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    const uid = await AsyncStorage.getItem('jarvis_user_id');
    if (uid) setUserId(uid);
    const savedRate = await AsyncStorage.getItem('voice_rate');
    if (savedRate) setVoiceRate(savedRate);
  };

  const saveSettings = async () => {
    await AsyncStorage.setItem('voice_rate', voiceRate);
    Alert.alert('Settings Saved', 'Your preferences have been saved.');
  };

  const logout = async () => {
    await AsyncStorage.clear();
    navigation.replace('Login');
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Settings</Text>
      </View>

      <ScrollView style={styles.content}>
        <View style={styles.settingSection}>
          <Text style={styles.settingSectionTitle}>CONNECTION</Text>
          <View style={styles.settingItem}>
            <Text style={styles.settingLabel}>API URL</Text>
            <TextInput
              style={styles.settingInput}
              value={apiUrl}
              onChangeText={setApiUrl}
              placeholder="http://localhost:8000/api/v1"
            />
          </View>
          <View style={styles.settingItem}>
            <Text style={styles.settingLabel}>User ID</Text>
            <Text style={styles.settingValue}>{userId || 'Not logged in'}</Text>
          </View>
        </View>

        <View style={styles.settingSection}>
          <Text style={styles.settingSectionTitle}>VOICE</Text>
          <View style={styles.settingItem}>
            <Text style={styles.settingLabel}>Voice Rate</Text>
            <TextInput
              style={styles.settingInput}
              value={voiceRate}
              onChangeText={setVoiceRate}
              keyboardType="numeric"
            />
          </View>
          <View style={styles.settingItem}>
            <Text style={styles.settingLabel}>Auto-Speak Responses</Text>
            <TouchableOpacity style={styles.toggleButton} onPress={() => setAutoSpeak(!autoSpeak)}>
              <Text style={styles.toggleButtonText}>{autoSpeak ? 'ON' : 'OFF'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.settingSection}>
          <Text style={styles.settingSectionTitle}>NOTIFICATIONS</Text>
          <View style={styles.settingItem}>
            <Text style={styles.settingLabel}>Push Notifications</Text>
            <TouchableOpacity style={styles.toggleButton} onPress={() => setNotifications(!notifications)}>
              <Text style={styles.toggleButtonText}>{notifications ? 'ON' : 'OFF'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.settingSection}>
          <Text style={styles.settingSectionTitle}>OFFLINE</Text>
          <View style={styles.settingItem}>
            <Text style={styles.settingLabel}>Offline Mode</Text>
            <TouchableOpacity style={styles.toggleButton} onPress={() => setOfflineMode(!offlineMode)}>
              <Text style={styles.toggleButtonText}>{offlineMode ? 'ON' : 'OFF'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <TouchableOpacity style={styles.saveButton} onPress={saveSettings}>
          <Text style={styles.saveButtonText}>Save Settings</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.logoutButtonFull} onPress={logout}>
          <Text style={styles.logoutButtonTextFull}>Logout</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const token = await AsyncStorage.getItem('jarvis_token');
      if (token && token !== 'demo') {
        await axios.get(`${API_BASE}/auth/me`);
        setAuthenticated(true);
      } else {
        await AsyncStorage.removeItem('jarvis_token');
      }
    } catch {
      await AsyncStorage.removeItem('jarvis_token');
      await AsyncStorage.removeItem('jarvis_refresh_token');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#00ff00" />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName={authenticated ? 'Chat' : 'Login'}
        screenOptions={{ headerShown: false }}
      >
        <Stack.Screen name="Login" component={LoginScreen} />
        <Stack.Screen
          name="Chat"
          component={ChatScreen}
          options={{ headerShown: false }}
        />
        <Stack.Screen name="Voice" component={VoiceScreen} />
        <Stack.Screen name="Agents" component={AgentsScreen} />
        <Stack.Screen name="Settings" component={SettingsScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: '#000',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loginContainer: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  loginContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  loginLogo: {
    fontSize: 80,
    fontWeight: 'bold',
    color: '#00ff00',
    textShadowColor: '#00ff00',
    textShadowRadius: 20,
  },
  loginTitle: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#00ff00',
    marginTop: 10,
  },
  loginSubtitle: {
    fontSize: 16,
    color: '#4a6',
    marginBottom: 40,
  },
  loginForm: {
    width: '100%',
    maxWidth: 300,
  },
  loginInput: {
    backgroundColor: '#1a1a1a',
    borderRadius: 8,
    padding: 14,
    color: '#00ff00',
    fontSize: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#2a2',
  },
  passwordContainer: {
    position: 'relative',
  },
  passwordInput: {
    paddingRight: 50,
  },
  showPasswordBtn: {
    position: 'absolute',
    right: 14,
    top: 14,
  },
  showPasswordText: {
    fontSize: 20,
  },
  loginButton: {
    backgroundColor: '#00ff00',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
    marginTop: 10,
  },
  loginButtonDisabled: {
    opacity: 0.5,
  },
  loginButtonText: {
    color: '#000',
    fontSize: 16,
    fontWeight: 'bold',
  },
  biometricButton: {
    marginTop: 20,
    padding: 14,
    alignItems: 'center',
  },
  biometricText: {
    color: '#4a6',
    fontSize: 14,
  },
  container: {
    flex: 1,
    backgroundColor: '#000000',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#00ff00',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#00ff00',
  },
  headerButtons: {
    flexDirection: 'row',
    gap: 16,
  },
  headerButton: {
    color: '#00ff00',
    fontSize: 14,
  },
  logoutButton: {
    marginLeft: 10,
  },
  logoutText: {
    color: '#ff4444',
    fontSize: 14,
  },
  chatContainer: {
    flex: 1,
  },
  chatContent: {
    padding: 16,
  },
  messageBubble: {
    padding: 12,
    borderRadius: 8,
    marginBottom: 8,
    maxWidth: '80%',
  },
  userBubble: {
    backgroundColor: '#003300',
    alignSelf: 'flex-end',
  },
  assistantBubble: {
    backgroundColor: '#001a00',
    alignSelf: 'flex-start',
  },
  messageText: {
    color: '#00ff00',
    fontSize: 16,
  },
  speakButton: {
    marginTop: 8,
  },
  speakButtonText: {
    fontSize: 18,
  },
  inputContainer: {
    flexDirection: 'row',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#00ff00',
  },
  input: {
    flex: 1,
    backgroundColor: '#001a00',
    borderRadius: 8,
    padding: 12,
    color: '#00ff00',
    fontSize: 16,
    maxHeight: 100,
  },
  sendButton: {
    backgroundColor: '#00ff00',
    borderRadius: 8,
    padding: 12,
    marginLeft: 8,
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
  sendButtonText: {
    fontSize: 20,
    color: '#000',
  },
  content: {
    flex: 1,
    padding: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  voiceButton: {
    backgroundColor: '#003300',
    borderRadius: 100,
    padding: 50,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#00ff00',
  },
  voiceButtonActive: {
    backgroundColor: '#00ff00',
  },
  voiceButtonText: {
    color: '#00ff00',
    fontSize: 18,
    fontWeight: 'bold',
  },
  resultCard: {
    backgroundColor: '#001a00',
    borderRadius: 8,
    padding: 16,
    marginTop: 20,
    width: '100%',
  },
  resultLabel: {
    color: '#666',
    fontSize: 12,
    marginBottom: 4,
  },
  resultText: {
    color: '#00ff00',
    fontSize: 16,
  },
  resultSpeakBtn: {
    marginTop: 10,
    padding: 8,
    backgroundColor: '#003300',
    borderRadius: 4,
    alignItems: 'center',
  },
  resultSpeakText: {
    color: '#00ff00',
    fontSize: 14,
  },
  agentsContainer: {
    flex: 1,
  },
  agentsContent: {
    padding: 16,
  },
  loader: {
    marginBottom: 10,
  },
  agentCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#001a00',
    borderRadius: 8,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#2a2',
  },
  agentCardActive: {
    borderColor: '#00ff00',
    backgroundColor: '#002200',
  },
  agentIconContainer: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#003300',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  agentIcon: {
    fontSize: 24,
  },
  agentInfo: {
    flex: 1,
  },
  agentName: {
    color: '#00ff00',
    fontSize: 16,
    fontWeight: 'bold',
  },
  agentDescription: {
    color: '#4a6',
    fontSize: 12,
    marginTop: 2,
  },
  agentStatus: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  agentStatusText: {
    color: '#000',
    fontSize: 10,
    fontWeight: 'bold',
  },
  agentHint: {
    color: '#444',
    fontSize: 12,
    textAlign: 'center',
    marginTop: 10,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    backgroundColor: '#0a0a0a',
    borderRadius: 12,
    padding: 20,
    width: '80%',
    borderWidth: 1,
    borderColor: '#00ff00',
  },
  modalTitle: {
    color: '#00ff00',
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 10,
  },
  modalDescription: {
    color: '#4a6',
    fontSize: 14,
    marginBottom: 20,
  },
  modalStatusRow: {
    flexDirection: 'row',
    marginBottom: 20,
  },
  modalLabel: {
    color: '#666',
    fontSize: 14,
    marginRight: 8,
  },
  modalStatus: {
    fontSize: 14,
    fontWeight: 'bold',
  },
  modalToggleBtn: {
    backgroundColor: '#00ff00',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
    marginBottom: 10,
  },
  modalToggleText: {
    color: '#000',
    fontSize: 14,
    fontWeight: 'bold',
  },
  modalCloseBtn: {
    padding: 14,
    alignItems: 'center',
  },
  modalCloseText: {
    color: '#666',
    fontSize: 14,
  },
  settingSection: {
    marginBottom: 24,
  },
  settingSectionTitle: {
    color: '#4a6',
    fontSize: 12,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  settingItem: {
    marginBottom: 16,
  },
  settingLabel: {
    color: '#00ff00',
    fontSize: 14,
    marginBottom: 6,
  },
  settingValue: {
    color: '#4a6',
    fontSize: 14,
  },
  settingInput: {
    backgroundColor: '#001a00',
    borderRadius: 8,
    padding: 12,
    color: '#00ff00',
    fontSize: 14,
  },
  toggleButton: {
    backgroundColor: '#003300',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
    width: 80,
  },
  toggleButtonText: {
    color: '#00ff00',
    fontSize: 14,
  },
  saveButton: {
    backgroundColor: '#00ff00',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
    marginTop: 20,
  },
  saveButtonText: {
    color: '#000',
    fontSize: 14,
    fontWeight: 'bold',
  },
  logoutButtonFull: {
    backgroundColor: '#330000',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
    marginTop: 10,
    borderWidth: 1,
    borderColor: '#ff4444',
  },
  logoutButtonTextFull: {
    color: '#ff4444',
    fontSize: 14,
  },
});

export default App;