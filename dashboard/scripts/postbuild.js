// Next.js 16 static export RSC payload fix
// Browser requests __next.X.__PAGE__.txt but file is at __next.X/__PAGE__.txt
const fs = require("fs");
const path = require("path");

const outDir = path.join(__dirname, "..", "out");

function fixRscPaths(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // Check for __next.X/__PAGE__.txt pattern
      if (entry.name.startsWith("__next.")) {
        const inner = path.join(full, "__PAGE__.txt");
        if (fs.existsSync(inner)) {
          const dotName = entry.name + ".__PAGE__.txt";
          const dotPath = path.join(dir, dotName);
          fs.copyFileSync(inner, dotPath);
          console.log(`Copied: ${dotName}`);
        }
      }
      fixRscPaths(full);
    }
  }
}

fixRscPaths(outDir);
console.log("Postbuild RSC fix complete.");
