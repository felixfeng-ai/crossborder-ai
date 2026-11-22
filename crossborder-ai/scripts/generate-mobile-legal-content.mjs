import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const ts = require(
  path.join(root, "frontend", "node_modules", "typescript", "lib", "typescript.js"),
);

function loadTypeScriptModule(filePath, customRequire) {
  const source = fs.readFileSync(filePath, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
  }).outputText;
  const loaded = { exports: {} };
  const execute = new Function(
    "exports",
    "require",
    "module",
    "__filename",
    "__dirname",
    output,
  );
  execute(
    loaded.exports,
    customRequire,
    loaded,
    filePath,
    path.dirname(filePath),
  );
  return loaded.exports;
}

const metaPath = path.join(root, "frontend", "src", "lib", "legalMeta.ts");
const legalPath = path.join(root, "frontend", "src", "lib", "legal.ts");
const meta = loadTypeScriptModule(metaPath, () => {
  throw new Error("legalMeta 不应包含运行时依赖");
});
const legal = loadTypeScriptModule(legalPath, (request) => {
  if (request === "@/lib/legalMeta") return meta;
  throw new Error(`未处理的法务模块依赖：${request}`);
});

if (!Array.isArray(legal.LEGAL_DOCUMENTS)) {
  throw new Error("未从 Web 法务源解析到 LEGAL_DOCUMENTS");
}

const outputPath = path.join(
  root,
  "mobile",
  "src",
  "features",
  "legal",
  "legal-documents.json",
);
fs.writeFileSync(
  outputPath,
  `${JSON.stringify(legal.LEGAL_DOCUMENTS, null, 2)}\n`,
  "utf8",
);
console.log(
  `Generated ${path.relative(root, outputPath)} with ${legal.LEGAL_DOCUMENTS.length} documents`,
);
