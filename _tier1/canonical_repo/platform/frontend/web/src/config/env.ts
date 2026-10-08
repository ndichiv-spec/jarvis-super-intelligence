const env = {
  API_URL: process.env.NEXT_PUBLIC_API_URL || '',
  WS_URL: process.env.NEXT_PUBLIC_WS_URL || '',
  SOCKET_URL: process.env.NEXT_PUBLIC_SOCKET_URL || '',
  APP_NAME: process.env.NEXT_PUBLIC_APP_NAME || 'JARVIS AI',
  APP_VERSION: process.env.NEXT_PUBLIC_APP_VERSION || '3.0.0',
  APP_URL: process.env.NEXT_PUBLIC_APP_URL || '',
  ENVIRONMENT: process.env.NEXT_PUBLIC_ENVIRONMENT || 'development',
  ENABLE_ANALYTICS: process.env.NEXT_PUBLIC_ENABLE_ANALYTICS === 'true',
  ENABLE_DEV_TOOLS: process.env.NEXT_PUBLIC_ENABLE_DEV_TOOLS === 'true',
  REQUEST_TIMEOUT: parseInt(process.env.NEXT_PUBLIC_REQUEST_TIMEOUT || '30000', 10),
  WS_RECONNECT_ATTEMPTS: parseInt(process.env.NEXT_PUBLIC_WS_RECONNECT_ATTEMPTS || '10', 10),
  WS_RECONNECT_INTERVAL: parseInt(process.env.NEXT_PUBLIC_WS_RECONNECT_INTERVAL || '3000', 10),
  get isDevelopment() { return this.ENVIRONMENT === 'development'; },
  get isProduction() { return this.ENVIRONMENT === 'production'; },
  get isTest() { return this.ENVIRONMENT === 'test'; },
};

export default env;
