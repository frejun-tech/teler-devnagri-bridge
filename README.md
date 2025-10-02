# Teler Devnagri Bridge

A reference integration between **Teler** and **Devnagri**, based on media streaming over WebSockets.

## About

This project is a reference implementation to bridge **Teler** and **Devnagri**. It enables real-time media streaming over WebSockets, facilitating live audio interactions.

---

## Features

- Real-time streaming of media via WebSockets
- Bi-directional communication between Teler client and Devnagri Websocket
- Sample structure for deployment (Docker, environment variables)
- Basic error handling and connection management

---

### Prerequisites

Ensure you have the following installed / available:

- Docker & Docker Compose
- Valid API credentials / access:
  - Teler account / API key / endpoints (frejun account)
  - Devnagri API access

---

## Setup

1. **Clone and configure:**

   ```bash
   git clone https://github.com/frejun-tech/teler-devnagri-bridge.git
   cd teler-Devnagri-bridge
   cp .env.example .env
   # Edit .env with your actual values
   ```

2. **Run with Docker:**
   ```bash
   docker compose up -d --build
   ```

## Environment Variables

| Variable           | Description           | Default  |
| ------------------ | --------------------- | -------- |
| `DEVNAGRI_API_KEY` | Your Devnagri API key | Required |
| `TELER_ACCOUNT_ID` | Teler Account Id      | Required |
| `TELER_API_KEY`    | Your Teler API key    | Required |
| `NGROK_AUTHTOKEN`  | Your ngrok auth token | Required |

## API Endpoints

- `GET /` - Health check with server domain
- `GET /health` - Service status
- `GET /ngrok-status` - Current ngrok status and URL
- `POST /api/v1/calls/initiate-call` - Start a new call with dynamic phone numbers
- `POST /api/v1/calls/flow` - Get call flow configuration
- `WebSocket /api/v1/calls/media-stream` - Audio streaming between teler and Devnagri
- `POST /api/v1/webhooks/receiver` - Teler → Devnagri webhook receiver

### Call Initiation Example

```bash
curl -X POST "http://localhost:8000/api/v1/calls/initiate-call" \
  -H "Content-Type: application/json" \
  -d '{
    "from_number": "+1234567890",
    "to_number": "+0987654321"
  }'
```
