# JARVIS Frontend Deployment Guide

## Local Development

1. Navigate to the frontend directory:
```bash
cd frontend/web
```

2. Install dependencies:
```bash
npm install
# or
pnpm install
```

3. Set up environment variables (copy from .env.example):
```bash
cp .env.example .env
# Edit .env with your settings
```

4. Start the development server with the backend running:
```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## Replit/Cloud Deployment

### Automatic Configuration (Recommended)

The frontend is configured to work automatically in Replit cloud environments:

1. The Next.js rewrites proxy `/api/*` and `/health` requests to the backend
2. WebSocket connections use relative URLs that auto-detect the host
3. No environment variables needed - defaults handle cloud deployments

### Environment Variables for Cloud

If you need to override defaults:

```bash
# Set these in Replit Secrets or .env file
NEXT_PUBLIC_API_URL=https://your-backend-url.replit.app
NEXT_PUBLIC_WS_URL=wss://your-backend-url.replit.app
```

### Docker Deployment

```bash
# Build the image
docker build -f Dockerfile.frontend -t jarvis-frontend .

# Run the container
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://host.docker.internal:8000 jarvis-frontend
```

## API URL Resolution

The frontend resolves the API URL in this order:

1. **NEXT_PUBLIC_API_URL environment variable** - Explicit override
2. **Relative path in browser** - For cloud deployments using Next.js rewrites
3. **localhost:8000** - Fallback for local development

## WebSocket URL Resolution

WebSocket URLs are resolved dynamically:

1. **NEXT_PUBLIC_WS_URL environment variable** - Explicit override
2. **window.location origin** - Auto-detected from current page URL
   - Uses `wss://` for HTTPS pages
   - Uses `ws://` for HTTP pages

## Common Issues

### "Backend Connection Lost" Banner

This appears when:
- The backend is not running
- Network issues between frontend and backend
- CORS/proxy misconfiguration in cloud environments

**Solutions:**
1. Ensure the backend is running and accessible
2. Check that the API URL is correctly configured
3. Verify WebSocket connections are not blocked

### API Calls Failing

If API calls fail:
1. Check `NEXT_PUBLIC_API_URL` is set correctly
2. Verify the backend health endpoint is accessible
3. Check browser console for CORS errors

### WebSocket Connection Issues

If WebSocket connections fail:
1. Ensure the backend WebSocket endpoint is running
2. Check `NEXT_PUBLIC_WS_URL` configuration
3. Verify the WebSocket path matches the backend configuration