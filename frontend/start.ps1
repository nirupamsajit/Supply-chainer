$env:PATH = "C:\Program Files\nodejs;" + $env:PATH
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies..."
    npm install
}
Write-Host "Starting Vite..."
npm run dev
