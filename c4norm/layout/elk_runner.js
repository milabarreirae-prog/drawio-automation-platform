/*
 * Runner ELK para c4norm.
 * Lee un grafo ELK (JSON) por stdin, ejecuta el layout 'layered' con ruteo
 * ortogonal y devuelve el grafo con coordenadas + bend points por stdout.
 */
"use strict";

const ELK = require("elkjs");
const elk = new ELK();

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", async () => {
  try {
    const graph = JSON.parse(input.replace(/^﻿/, ""));
    const result = await elk.layout(graph);
    process.stdout.write(JSON.stringify(result));
  } catch (err) {
    process.stderr.write(String((err && err.stack) || err));
    process.exit(1);
  }
});
