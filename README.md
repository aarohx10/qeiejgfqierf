# 5. Deployment on Hetzner

This section outlines the high-level steps to deploy the Sendora AI Voice Infrastructure on a Hetzner Linux VM. This setup assumes a fresh Ubuntu/Debian-based VM.

## 5.1 Prerequisites on Hetzner VM
1.  **SSH Access:** Ensure you can SSH into your Hetzner VM.
2.  **Python 3.9+ & pip:**
    ```bash
    sudo apt update
    sudo apt install python3 python3-pip python3.10-venv -y # Adjust python3.10-venv based on Python version
    ```
3.  **Git:**
    ```bash
    sudo apt install git -y
    ```
4.  **Nginx (for Reverse Proxy):**
    ```bash
    sudo apt install nginx -y
    sudo ufw allow 'Nginx HTTP' # If UFW is active
    ```
5.  **Required System Libraries (for ASR/VAD):**
    * For `faster-whisper` and `pyannote.audio`, you might need `ffmpeg` and other audio processing libraries:
        ```bash
        sudo apt install ffmpeg libsndfile1 -y
        ```

## 5.2 Application Setup
1.  **Clone the Repository:**
    ```bash
    git clone <YOUR_REPO_URL>
    cd ai-voice-caller # Or whatever your repo's directory name is
    ```
2.  **Create Virtual Environment & Install Dependencies:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    ```
3.  **Configure Environment Variables:**
    * Create a `.env` file in the root directory (where `config.py` is located) with all your sensitive API keys and URLs.
    * Example `.env` (replace with your actual values):
        ```
        SUPABASE_URL="[https://your-project-id.supabase.co](https://your-project-id.supabase.co)"
        SUPABASE_ANON_KEY="your-supabase-anon-key"
        REDIS_HOST="localhost" # Or your Redis server IP
        REDIS_PORT=6379
        DEEPGRAM_API_KEY="your-deepgram-api-key"
        GEMINI_API_KEY="your-gemini-api-key"
        ELEVENLABS_API_KEY="your-elevenlabs-api-key"
        ELEVENLABS_VOICE_ID="your-default-voice-id"
        PYANNOTE_AUTH_TOKEN="your-huggingface-token-for-pyannote"
        SIGNALWIRE_PROJECT_ID="your-sw-project-id"
        SIGNALWIRE_API_TOKEN="your-sw-api-token"
        SIGNALWIRE_SPACE_URL="[https://your-space.signalwire.com](https://your-space.signalwire.com)"
        SIGNALWIRE_WEBHOOK_URL_BASE="http://<YOUR_SERVER_PUBLIC_IP_OR_DOMAIN>" # IMPORTANT: This must be publicly accessible!
        MANAGEMENT_API_KEY="your-secret-management-api-key"
        ```
    * **Security Note:** For production, prefer setting these directly as environment variables via `systemd` service files rather than in a `.env` file.

## 5.3 Running the Backends with Gunicorn

We will run both backend applications using Gunicorn with Uvicorn workers for asynchronous support.

1.  **Backend 1: Web Call Server (`src/server.py`)**
    * This serves the React client via WebSockets.
    * Running Port: `8765`
    * Command:
        ```bash
        gunicorn src.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8765 --timeout 120 --log-level info
        ```

2.  **Backend 2: Telephony Orchestrator (`ai_orchestrator.py`)**
    * This handles SignalWire webhooks and API calls.
    * Running Port: `8000`
    * Command:
        ```bash
        gunicorn ai_orchestrator:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 300 --log-level info
        ```

## 5.4 Nginx Configuration (Reverse Proxy)

Nginx will route incoming HTTP/WebSocket traffic to the correct backend application.

1.  **Create Nginx site configuration:**
    ```bash
    sudo nano /etc/nginx/sites-available/sendora_voice_ai
    ```
2.  **Paste the following configuration (replace `your_domain.com` with your IP or domain):**
    ```nginx
    server {
        listen 80;
        server_name your_domain.com <YOUR_SERVER_PUBLIC_IP>; # Replace with your domain/IP

        # --- Backend 2: Telephony Orchestrator (FastAPI) ---
        # Routes for SignalWire webhooks, API trigger, and Management API
        location /signalwire-webhook {
            proxy_pass [http://127.0.0.1:8000](http://127.0.0.1:8000);
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300; # Longer timeout for webhooks
            proxy_send_timeout 300;
        }

        location /trigger-call {
            proxy_pass [http://127.0.0.1:8000](http://127.0.0.1:8000);
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300;
            proxy_send_timeout 300;
        }

        location /manage/ { # For the Management API endpoints
            proxy_pass [http://127.0.0.1:8000](http://127.0.0.1:8000);
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 60;
            proxy_send_timeout 60;
        }

        # --- Backend 1: Web Call Server (WebSocket) ---
        # This routes the WebSocket connections from your React client
        location /ws { # Or whatever path your React client connects to (e.g., /websocket)
            proxy_pass [http://127.0.0.1:8765](http://127.0.0.1:8765); # Or the port src/server.py is running on
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_read_timeout 86400; # Keep WebSocket open for a long time (24 hours)
            proxy_send_timeout 86400;
        }

        # --- Serve Frontend (Optional, if you host client/ on same server) ---
        # location / {
        #     root /path/to/your/ai-voice-caller/client/dist; # Path to your built React app
        #     try_files $uri $uri/ /index.html;
        # }

        # Default fallback for other paths (can be a custom error page or handled by telephony backend)
        location / {
            proxy_pass [http://127.0.0.1:8000](http://127.0.0.1:8000);
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```
3.  **Enable the site and test Nginx config:**
    ```bash
    sudo ln -s /etc/nginx/sites-available/sendora_voice_ai /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl restart nginx
    ```

## 5.5 Process Management (Optional, but Recommended for Production)

Use `systemd` to ensure your Gunicorn processes run continuously and restart automatically.

1.  **Create service files (e.g., `/etc/systemd/system/sendora_web.service` and `/etc/systemd/system/sendora_telephony.service`).**
2.  **Example `sendora_telephony.service`:**
    ```
    [Unit]
    Description=Sendora AI Telephony Backend
    After=network.target

    [Service]
    User=your_username # Replace with your SSH user
    Group=www-data # Or your user's primary group
    WorkingDirectory=/path/to/your/ai-voice-caller # Replace with your repo path
    EnvironmentFile=/path/to/your/ai-voice-caller/.env # Load env vars from .env file
    ExecStart=/path/to/your/ai-voice-caller/venv/bin/gunicorn ai_orchestrator:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 300
    Restart=always
    LimitNOFILE=65535 # Increase file descriptor limit for websockets

    [Install]
    WantedBy=multi-user.target
    ```
    *(Create a similar service file for `sendora_web.service` pointing to `src.main` and port `8765`)*
3.  **Enable and Start Services:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable sendora_web sendora_telephony
    sudo systemctl start sendora_web sendora_telephony
    sudo systemctl status sendora_web sendora_telephony # Check status
    ``` 