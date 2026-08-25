import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), "../.."));
const panelRoot = join(root, "custom_components", "ontology", "panel");
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
};

createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const file = pathname.startsWith("/ontology_static/")
    ? normalize(join(panelRoot, pathname.slice("/ontology_static/".length)))
    : normalize(join(root, pathname));
  if (!file.startsWith(root)) {
    response.writeHead(403).end();
    return;
  }
  try {
    if (!statSync(file).isFile()) {
      throw new Error("not a file");
    }
    response.writeHead(200, { "content-type": types[extname(file)] || "application/octet-stream" });
    createReadStream(file).pipe(response);
  } catch {
    response.writeHead(404).end("Not found");
  }
}).listen(4173, "127.0.0.1");