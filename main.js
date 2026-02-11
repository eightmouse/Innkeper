const { app, BrowserWindow, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let mainWindow;
let pythonProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 700,
    minHeight: 500,
    frame: false,          // ← custom title bar
    backgroundColor: '#0a0c12',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  mainWindow.loadFile('index.html');

  // ── Spawn Python engine ──────────────────────────────
  pythonProcess = spawn('python', [path.join(__dirname, 'engine.py')]);

  // Route stdout to renderer, line-by-line
  let buffer = '';
  pythonProcess.stdout.on('data', (data) => {
    buffer += data.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep the incomplete last chunk

    lines.forEach(line => {
      const clean = line.trim();
      if (!clean) return;
      console.log(`[Python] ${clean}`);

      if (clean.includes('"status": "ready"')) {
        // Engine is up — request character list
        pythonProcess.stdin.write('GET_CHARACTERS\n');
        return;
      }

      if (clean.startsWith('[') || clean.startsWith('{')) {
        try {
          JSON.parse(clean); // validate
          mainWindow.webContents.send('from-python', clean);
        } catch (e) {
          console.warn('Skipping partial JSON:', clean.slice(0, 60));
        }
      }
    });
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python ERR] ${data.toString().trim()}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`[Python] Process exited with code ${code}`);
  });
}

// ── IPC: Renderer → Python ─────────────────────────────
ipcMain.on('to-python', (event, message) => {
  if (pythonProcess && pythonProcess.stdin.writable) {
    console.log(`[→ Python] ${message}`);
    pythonProcess.stdin.write(message + '\n');
  }
});

// ── IPC: Window controls ───────────────────────────────
ipcMain.on('window-close',    () => mainWindow.close());
ipcMain.on('window-minimize', () => mainWindow.minimize());
ipcMain.on('window-maximize', () => {
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
});

ipcMain.on('open-external', (event, url) => {
  shell.openExternal(url);
});

// ── App lifecycle ──────────────────────────────────────
app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.stdin.write('EXIT\n');
    pythonProcess.kill();
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});