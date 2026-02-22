const path = require('path');
const { execFileSync } = require('child_process');

exports.default = async function (context) {
  if (process.platform !== 'win32') return;

  const exePath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.exe`);
  const iconPath = path.join(__dirname, 'icon.ico');
  const rcedit = path.join(context.appOutDir, '..', '..', 'node_modules', 'rcedit', 'bin', 'rcedit-x64.exe');

  // Try bundled rcedit first, fall back to electron-builder's cached copy
  let rceditPath = rcedit;
  try {
    require.resolve('rcedit');
  } catch {
    const cacheDir = path.join(require('os').homedir(), 'AppData', 'Local', 'electron-builder', 'Cache', 'winCodeSign');
    const fs = require('fs');
    const entries = fs.readdirSync(cacheDir).filter(e => e.startsWith('winCodeSign'));
    if (entries.length > 0) {
      rceditPath = path.join(cacheDir, entries[0], 'rcedit-x64.exe');
    }
  }

  try {
    execFileSync(rceditPath, [exePath, '--set-icon', iconPath]);
    console.log('  • icon set successfully');
  } catch (e) {
    console.error('  • failed to set icon:', e.message);
  }
};
