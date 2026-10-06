import express, { Express, Request, Response } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import dotenv from 'dotenv';

dotenv.config();

const app: Express = express();
const PORT = process.env.PORT || 8000;

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());

// Health check endpoint
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'ok', message: 'Jarvis Cloud is running', timestamp: new Date().toISOString() });
});

// Welcome endpoint
app.get('/', (req: Request, res: Response) => {
  res.json({ 
    message: 'Welcome to Jarvis Cloud',
    version: '1.0.0',
    port: PORT
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`✅ Jarvis Cloud is running on port ${PORT}`);
  console.log(`📍 Health check: http://localhost:${PORT}/health`);
  console.log(`🌐 API base: http://localhost:${PORT}/`);
});
