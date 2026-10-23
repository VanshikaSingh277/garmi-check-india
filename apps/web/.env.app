# Settings for the Android / iOS build (npm run build:app). The app runs on the phone, so it needs the full address of
# the deployed Thandak API (the server must allow the app's origin - see CORS in apps/api/main.py).
VITE_API_BASE=https://YOUR-THANDAK-SERVER.example.com
# Optional: your own map tile server (OpenStreetMap's public tiles are for light use only)
# VITE_TILE_URL=https://tiles.example.com/{z}/{x}/{y}.png
